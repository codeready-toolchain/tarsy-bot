"""MCP transport factory for creating transport instances."""

from abc import ABC, abstractmethod
from typing import Optional, Any
from mcp import ClientSession

from tarsy.models.mcp_transport_config import (
    TransportConfig,
    TRANSPORT_STDIO,
    TRANSPORT_HTTP,
    TRANSPORT_SSE,
)
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)

class MCPTransport(ABC):
    """Abstract base class for MCP transports."""
    
    @abstractmethod
    async def create_session(self) -> ClientSession:
        """Create and initialize an MCP session."""
        pass
    
    @abstractmethod
    async def close(self):
        """Close the transport connection."""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if transport is connected."""
        pass


class MCPTransportFactory:
    """Factory for creating MCP transport instances."""
    
    @staticmethod
    def create_transport(
        server_id: str,
        transport: TransportConfig,
        exit_stack: Optional[Any] = None
    ) -> MCPTransport:
        """
        Create appropriate transport instance based on configuration.
        
        Args:
            server_id: Unique identifier for the server
            transport: Transport-specific configuration
            exit_stack: Optional AsyncExitStack for resource management
            
        Returns:
            MCPTransport instance
            
        Raises:
            ValueError: If transport type is not supported
        """
        transport_type = transport.type
        
        if transport_type == TRANSPORT_STDIO:
            from .stdio_transport import StdioTransport
            return StdioTransport(server_id, transport, exit_stack)
        elif transport_type == TRANSPORT_HTTP:
            from .http_transport import HTTPTransport
            return HTTPTransport(server_id, transport)
        elif transport_type == TRANSPORT_SSE:
            from .sse_transport import SSETransport
            return SSETransport(server_id, transport)
        else:
            raise ValueError(f"Unsupported transport type: {transport_type}")
