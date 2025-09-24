"""Stdio transport implementation - wrapper around existing MCP SDK functionality."""

from contextlib import AsyncExitStack
from typing import Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .factory import MCPTransport
from tarsy.models.mcp_transport_config import StdioTransportConfig
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class StdioTransport(MCPTransport):
    """Stdio transport wrapper to integrate existing functionality into unified transport architecture."""
    
    def __init__(self, server_id: str, config: StdioTransportConfig, exit_stack: AsyncExitStack) -> None:
        """
        Initialize stdio transport.
        
        Args:
            server_id: Unique identifier for the server
            config: Stdio transport configuration
            exit_stack: AsyncExitStack for resource management
        """
        self.server_id = server_id
        self.config = config
        self.exit_stack = exit_stack
        self.session: Optional[ClientSession] = None
        self._connected = False
    
    async def create_session(self) -> ClientSession:
        """Create stdio session using existing MCP SDK."""
        if self.session:
            return self.session
        
        logger.info(f"Creating stdio session for server: {self.server_id}")
        
        # Create stdio parameters from config
        stdio_params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args or [],
            env=self.config.env or {}
        )
        
        # Use existing MCP SDK stdio client with exit_stack management
        stdio_context = stdio_client(stdio_params)
        
        # Enter the context to get the streams
        streams = await self.exit_stack.enter_async_context(stdio_context)
        read_stream, write_stream = streams
        
        # Create ClientSession as async context manager
        session_context = ClientSession(read_stream, write_stream)
        session = await self.exit_stack.enter_async_context(session_context)
        
        # Initialize the connection
        logger.info(f"Initializing stdio session for server: {self.server_id}")
        await session.initialize()
        logger.info(f"Stdio session initialization completed for server: {self.server_id}")
        
        self.session = session
        self._connected = True
        logger.info(f"Stdio session created for server: {self.server_id}")
        return self.session
    
    async def close(self) -> None:
        """Close stdio transport and cleanup all owned resources."""
        if self._connected:
            logger.info(f"Closing stdio transport for server: {self.server_id}")
            
            try:
                # Close all async context managers managed by exit_stack
                # This will properly cleanup stdio streams, client session, and subprocess
                await self.exit_stack.aclose()
                logger.info(f"Successfully closed all resources for server: {self.server_id}")
            except Exception as e:
                logger.error(f"Failed to close resources for server {self.server_id}: {e}")
            
            # Set flags to indicate transport is closed
            self._connected = False
            self.session = None
    
    @property
    def is_connected(self) -> bool:
        """Check if stdio transport is connected."""
        return self._connected and self.session is not None
