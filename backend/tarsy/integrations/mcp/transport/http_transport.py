"""HTTP transport implementation using official MCP SDK."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from typing import Dict, Optional

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from tarsy.models.mcp_transport_config import HTTPTransportConfig
from tarsy.utils.logger import get_module_logger

from .error_handling import is_safe_teardown_error
from .factory import MCPTransport

logger = get_module_logger(__name__)


class HTTPTransport(MCPTransport):
    """HTTP transport wrapper using MCP SDK streamable HTTP client."""
    
    def __init__(self, server_id: str, config: HTTPTransportConfig):
        """
        Initialize HTTP transport.
        
        Args:
            server_id: Unique identifier for the server
            config: HTTP transport configuration
        """
        self.server_id = server_id
        self.config = config
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self._connected = False
    
    async def create_session(self) -> ClientSession:
        """Create HTTP session using MCP SDK.
        
        Raises:
            Exception: If session creation fails (connection errors, timeouts, etc.)
        """
        if self.session:
            return self.session
        
        logger.info(f"Creating HTTP session for server: {self.server_id}")
        
        # Wrap in a new task to isolate anyio cancel scopes from parent context
        # This prevents "Attempted to exit cancel scope in a different task" errors
        # when MCP SDK cleanup runs after connection failures
        return await asyncio.create_task(self._create_session_impl())
    
    async def _create_session_impl(self) -> ClientSession:
        """Internal implementation of session creation, isolated in its own task."""
        try:
            # Prepare headers with bearer token if configured
            request_headers = dict(self.config.headers or {})
            if self.config.bearer_token:
                request_headers["Authorization"] = f"Bearer {self.config.bearer_token}"
            
            if not self.config.verify_ssl:
                logger.warning(
                    f"SSL verification disabled for server: {self.server_id}. "
                    "This is insecure and should only be used in development."
                )
            
            # Create custom httpx client factory that respects verify_ssl setting
            # Note: streamablehttp_client uses this factory with async with, expecting a context manager
            @asynccontextmanager
            async def custom_client_factory(
                headers: Optional[Dict[str, str]] = None,
                timeout: Optional[httpx.Timeout] = None,
                auth: Optional[httpx.Auth] = None
            ) -> AsyncGenerator[httpx.AsyncClient, None]:
                """Custom httpx client factory with configurable SSL verification."""
                async with httpx.AsyncClient(
                    headers=headers,
                    timeout=timeout,
                    auth=auth,
                    verify=self.config.verify_ssl,  # Use configured SSL verification setting
                ) as client:
                    yield client
            
            # Create HTTP client context using MCP SDK.
            #
            # NOTE: streamablehttp_client() is implemented as an async generator-based
            # context manager. If __aenter__ fails (e.g. connect error while the server
            # is down), the context is not registered in our AsyncExitStack, and the
            # generator would otherwise be finalized by GC. In Python 3.13 + AnyIO,
            # that can surface as noisy:
            #   "Task exception was never retrieved" +
            #   RuntimeError("Attempted to exit cancel scope in a different task...")
            #
            # To avoid that, we manually manage __aenter__/__aexit__ and ensure
            # best-effort cleanup happens in the *same task* as the failed __aenter__.
            http_context = streamablehttp_client(
                url=str(self.config.url),
                headers=request_headers if request_headers else None,
                timeout=self.config.timeout,
                httpx_client_factory=custom_client_factory,
            )
            
            # Enter the context to get the streams and session ID callback
            try:
                streams = await http_context.__aenter__()
            except BaseException as e:
                # Best-effort cleanup to prevent leaked async-generator finalizers.
                try:
                    await http_context.__aexit__(type(e), e, e.__traceback__)
                except BaseExceptionGroup as eg:
                    if not is_safe_teardown_error(eg):
                        raise
                except BaseException as exit_err:
                    if not is_safe_teardown_error(exit_err):
                        raise
                raise
            self.exit_stack.push_async_exit(http_context)
            read_stream, write_stream, get_session_id_callback = streams
            
            # Create ClientSession as async context manager
            session_context = ClientSession(read_stream, write_stream)
            session = await self.exit_stack.enter_async_context(session_context)
            
            # Initialize the connection
            logger.info(f"Initializing session for server: {self.server_id}")
            await session.initialize()
            logger.info(f"Session initialization completed for server: {self.server_id}")
            
            self.session = session
            self._connected = True
            logger.info(f"HTTP session created and initialized for server: {self.server_id}")
            return self.session
            
        except BaseExceptionGroup as eg:
            # Handle anyio/MCP SDK exception groups (connection failures wrapped in task groups)
            # Extract error messages from all sub-exceptions
            errors = [f"{type(e).__name__}: {e}" for e in eg.exceptions]
            logger.error(f"HTTP transport creation failed for {self.server_id} with grouped errors: {errors}")
            with suppress(BaseException):
                await self.exit_stack.aclose()
            raise Exception(f"Failed to create HTTP session - {'; '.join(errors)}") from None
        except Exception as e:
            # Catch all other errors (connection failures, timeouts, etc.)
            # Clean up any partial state before propagating
            logger.error(f"HTTP transport creation failed for {self.server_id}: {type(e).__name__}: {e}")
            with suppress(BaseException):
                await self.exit_stack.aclose()
            raise Exception(f"Failed to create HTTP session: {type(e).__name__}: {e}") from e
    
    async def close(self):
        """Close HTTP transport (handled automatically by exit_stack).
        
        We intentionally only suppress a very narrow set of *known safe* teardown
        errors (primarily the AnyIO cancel-scope mismatch RuntimeError).
        """
        if self._connected:
            logger.info(f"Closing HTTP transport for server: {self.server_id}")
            try:
                await self.exit_stack.aclose()
            except BaseExceptionGroup as eg:
                if is_safe_teardown_error(eg):
                    logger.debug(
                        "HTTP transport cleanup error for %s (suppressed): %s",
                        self.server_id,
                        type(eg).__name__,
                    )
                else:
                    raise
            except Exception as e:
                if is_safe_teardown_error(e):
                    logger.debug(
                        "HTTP transport cleanup error for %s (suppressed): %s",
                        self.server_id,
                        type(e).__name__,
                    )
                else:
                    raise
            finally:
                self._connected = False
                self.session = None
    
    @property
    def is_connected(self) -> bool:
        """Check if HTTP transport is connected."""
        return self._connected and self.session is not None
