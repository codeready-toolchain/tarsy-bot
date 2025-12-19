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

from .factory import MCPTransport

logger = get_module_logger(__name__)


_CANCEL_SCOPE_MISMATCH_MESSAGE = "Attempted to exit cancel scope in a different task than it was entered in"


def _is_cancel_scope_mismatch_error(exc: BaseException) -> bool:
    """Detect the known AnyIO cancel-scope cleanup bug (safe to suppress during teardown only)."""
    return isinstance(exc, RuntimeError) and _CANCEL_SCOPE_MISMATCH_MESSAGE in str(exc)


def _is_safe_teardown_error(exc: BaseException) -> bool:
    """
    Determine if an exception raised during transport teardown is safe to suppress.

    We only suppress:
    - The known AnyIO cancel-scope mismatch RuntimeError
    - Expected connection/stream shutdown errors that can be produced by MCP SDK task groups

    Anything else is re-raised to avoid hiding real bugs.
    """
    if _is_cancel_scope_mismatch_error(exc):
        return True

    if isinstance(exc, BaseExceptionGroup):
        return all(_is_safe_teardown_error(e) for e in exc.exceptions)

    if isinstance(exc, (httpx.ConnectError, httpx.TransportError, GeneratorExit)):
        return True

    return False


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
            
            # Create HTTP client context using MCP SDK
            http_context = streamablehttp_client(
                url=str(self.config.url),
                headers=request_headers if request_headers else None,
                timeout=self.config.timeout,
                httpx_client_factory=custom_client_factory,
            )
            
            # Enter the context to get the streams and session ID callback
            streams = await self.exit_stack.enter_async_context(http_context)
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
                if _is_safe_teardown_error(eg):
                    logger.debug(
                        "HTTP transport cleanup error for %s (suppressed): %s",
                        self.server_id,
                        type(eg).__name__,
                    )
                else:
                    raise
            except Exception as e:
                if _is_safe_teardown_error(e):
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
