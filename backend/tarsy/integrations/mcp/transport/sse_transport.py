"""SSE transport implementation using official MCP SDK."""

from contextlib import AsyncExitStack
from typing import Optional
from mcp import ClientSession
from mcp.client.sse import sse_client

from .factory import MCPTransport
from tarsy.models.mcp_transport_config import SSETransportConfig
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class SSETransport(MCPTransport):
    """SSE transport wrapper using official MCP SDK SSE client."""
    
    def __init__(self, server_id: str, config: SSETransportConfig):
        """
        Initialize SSE transport.
        
        Args:
            server_id: Unique identifier for the server
            config: SSE transport configuration
        """
        self.server_id = server_id
        self.config = config
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self._connected = False
    
    async def create_session(self) -> ClientSession:
        """Create SSE session using official MCP SDK pattern."""
        if self.session:
            return self.session
        
        logger.info(f"Creating SSE session for server: {self.server_id}")
        
        # Prepare headers with bearer token if configured
        headers = dict(self.config.headers or {})
        if self.config.bearer_token:
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"
        
        # Create SSE client context using MCP SDK
        sse_context = sse_client(
            url=str(self.config.url),
            headers=headers if headers else None,
            timeout=self.config.timeout,
            sse_read_timeout=self.config.sse_read_timeout,
        )
        
        # Enter the context to get the streams
        streams = await self.exit_stack.enter_async_context(sse_context)
        read_stream, write_stream = streams
        
        # Create ClientSession as async context manager
        session_context = ClientSession(read_stream, write_stream)
        session = await self.exit_stack.enter_async_context(session_context)
        
        # Initialize the connection
        logger.info(f"Initializing SSE session for server: {self.server_id}")
        await session.initialize()
        logger.info(f"SSE session initialization completed for server: {self.server_id}")
        
        self.session = session
        self._connected = True
        logger.info(f"SSE session created and initialized for server: {self.server_id}")
        return self.session
    
    async def close(self):
        """Close SSE transport (handled automatically by exit_stack)."""
        if self._connected:
            logger.info(f"Closing SSE transport for server: {self.server_id}")
            try:
                await self.exit_stack.aclose()
            except Exception as e:
                logger.error(f"Error closing SSE transport for {self.server_id}: {e}")
            finally:
                self._connected = False
                self.session = None
    
    @property
    def is_connected(self) -> bool:
        """Check if SSE transport is connected."""
        return self._connected and self.session is not None
