"""HTTP transport implementation using official MCP SDK."""

from contextlib import AsyncExitStack
from typing import Optional, Dict
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from .factory import MCPTransport
from tarsy.models.mcp_transport_config import HTTPTransportConfig
from tarsy.utils.logger import get_module_logger

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
        """Create HTTP session using MCP SDK."""
        if self.session:
            return self.session
        
        logger.info(f"Creating HTTP session for server: {self.server_id}")
        
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
        from contextlib import asynccontextmanager
        from collections.abc import AsyncGenerator
        
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
    
    async def close(self):
        """Close HTTP transport (handled automatically by exit_stack)."""
        import asyncio
        
        if self._connected:
            logger.info(f"Closing HTTP transport for server: {self.server_id}")
            try:
                # Shield from cancellation to prevent cancel scope errors from propagating
                # This prevents HTTP transport cleanup errors from cancelling parent tasks
                await asyncio.shield(self.exit_stack.aclose())
            except asyncio.CancelledError:
                # Cancellation during cleanup should not propagate
                # Log but don't raise - this allows parent tasks to continue
                logger.warning(f"HTTP transport cleanup was cancelled for {self.server_id} (non-critical)")
            except Exception as e:
                # Log other errors but don't raise them - cleanup is best-effort
                # Cancel scope errors from MCP SDK should not kill the parent session
                logger.error(f"Error closing HTTP transport for {self.server_id}: {e}")
            finally:
                self._connected = False
                self.session = None
    
    @property
    def is_connected(self) -> bool:
        """Check if HTTP transport is connected."""
        return self._connected and self.session is not None
