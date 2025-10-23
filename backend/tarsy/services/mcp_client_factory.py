"""
MCP Client Factory for creating isolated MCP client instances.

This factory creates fresh MCP client instances on-demand, ensuring
each alert session gets its own isolated client to avoid cross-context
cancel scope issues.
"""

from tarsy.config.settings import Settings
from tarsy.integrations.mcp.client import MCPClient
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class MCPClientFactory:
    """Factory for creating isolated MCP client instances."""

    def __init__(self, settings: Settings, mcp_registry: MCPServerRegistry):
        """
        Initialize the MCP client factory.

        Args:
            settings: Application settings
            mcp_registry: MCP server registry (shared across all clients)
        """
        self.settings = settings
        self.mcp_registry = mcp_registry

    async def create_client(self) -> MCPClient:
        """
        Create and initialize a new MCP client instance.

        Each client is isolated and should be used for a single alert session.
        The client must be closed after use to cleanup resources.

        Returns:
            Initialized MCPClient instance

        Raises:
            Exception: If client initialization fails
        """
        logger.debug("Creating new MCP client instance")

        # Create fresh client with shared registry
        client = MCPClient(
            settings=self.settings,
            mcp_registry=self.mcp_registry,
            summarizer=None,  # Summarizer will be set by agent when needed
        )

        # Initialize the client (connects to MCP servers)
        await client.initialize()

        logger.debug("MCP client instance created and initialized")
        return client

