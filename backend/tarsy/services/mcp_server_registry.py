"""
MCP Server Registry for managing MCP server configurations.

This module provides a simple static registry for MCP server configurations
with embedded LLM instructions. The registry is loaded once at startup and
serves as the single source of truth for all MCP server configurations,
including both built-in and configured servers.
"""

from typing import Dict, List, Optional

from ..models.agent_config import MCPServerConfigModel as MCPServerConfig
from ..utils.logger import get_module_logger
from ..config.builtin_config import BUILTIN_MCP_SERVERS
from ..utils.template_resolver import TemplateResolver, TemplateResolutionError
from ..config.settings import Settings

# Import for type hints only (avoid circular imports)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..models.agent_config import MCPServerConfigModel

logger = get_module_logger(__name__)


class MCPServerRegistry:
    """
    Static registry for MCP server configurations.
    
    This class manages all MCP server configurations in the system,
    providing a simple dictionary-based lookup mechanism. The registry
    is immutable after initialization to ensure consistency.
    
    This is the SINGLE SOURCE OF TRUTH for all MCP server configurations.
    """
    
    # Built-in server configurations imported from central configuration
    _DEFAULT_SERVERS = BUILTIN_MCP_SERVERS
    
    def __init__(
        self, 
        config: Optional[Dict[str, Dict]] = None,
        configured_servers: Optional[Dict[str, "MCPServerConfigModel"]] = None,
        settings: Optional[Settings] = None
    ):
        """
        Initialize the MCP server registry with configurations.
        
        Args:
            config: Optional dictionary of server configurations.
                   If None, uses default configurations defined in the registry.
            configured_servers: Optional dictionary of configured MCP servers to include.
                              These are merged with the built-in servers.
            settings: Optional Settings instance for template variable defaults.
        """
        # Static servers - no runtime changes, just a dictionary
        self.static_servers: Dict[str, MCPServerConfig] = {}
        
        # Initialize template resolver for environment variable expansion with settings defaults
        self.template_resolver = TemplateResolver(settings=settings)
        
        # Start with built-in server configurations (config parameter or defaults)
        server_configs = config or self._DEFAULT_SERVERS
        
        # Convert built-in servers to MCPServerConfig objects with template resolution
        for server_id, server_config in server_configs.items():
            try:
                logger.debug(f"Resolving templates for MCP server '{server_id}'")
                logger.debug(f"Original config: {server_config}")
                
                # Apply template resolution to built-in server configuration
                resolved_config = self.template_resolver.resolve_configuration(server_config)
                
                logger.debug(f"Resolved config for '{server_id}': {resolved_config}")
                
                self.static_servers[server_id] = MCPServerConfig(**resolved_config)
                logger.debug(f"Successfully added built-in MCP server with template resolution: {server_id}")
            except TemplateResolutionError as e:
                logger.error(f"Template resolution failed for built-in MCP server '{server_id}': {e}")
                # Use original config without template resolution as fallback
                self.static_servers[server_id] = MCPServerConfig(**server_config)
                logger.warning(f"Using original configuration for '{server_id}' due to template resolution failure")
        
        # Add configured servers if provided
        if configured_servers:
            for server_id, server_config in configured_servers.items():
                try:
                    # Convert MCPServerConfigModel to dict and apply template resolution
                    server_dict = server_config.model_dump()
                    resolved_dict = self.template_resolver.resolve_configuration(server_dict)
                    self.static_servers[server_id] = MCPServerConfig(**resolved_dict)
                    logger.debug(f"Added configured MCP server with template resolution: {server_id}")
                except TemplateResolutionError as e:
                    logger.error(f"Template resolution failed for configured MCP server '{server_id}': {e}")
                    # Use original config without template resolution as fallback
                    server_dict = server_config.model_dump()
                    self.static_servers[server_id] = MCPServerConfig(**server_dict)
                    logger.warning(f"Using original configuration for '{server_id}' due to template resolution failure")
            
            logger.info(f"Added {len(configured_servers)} configured MCP servers")
        
        logger.info(f"Initialized MCP Server Registry with {len(self.static_servers)} total servers")
    
    def get_server_configs(self, server_ids: List[str]) -> List[MCPServerConfig]:
        """
        Get MCP server configurations for the specified server IDs.
        Simple dictionary lookup - no complex logic.
        
        Args:
            server_ids: List of server IDs to retrieve configurations for
            
        Returns:
            List of MCPServerConfig objects for the requested servers
        """
        return [
            self.static_servers[server_id] 
            for server_id in server_ids 
            if server_id in self.static_servers
        ]
    
    def get_server_config(self, server_id: str) -> MCPServerConfig:
        """
        Get configuration for a single MCP server.
        
        Args:
            server_id: The server ID to retrieve
            
        Returns:
            MCPServerConfig for the requested server
            
        Raises:
            ValueError: If server_id is not found
        """
        server_config = self.static_servers.get(server_id)
        
        if server_config is None:
            # Fail-fast with technical error details
            available_servers = list(self.static_servers.keys())
            error_msg = f"MCP server '{server_id}' not found. Available: {', '.join(available_servers)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.debug(f"Found MCP server config for '{server_id}' (type: {server_config.server_type}, enabled: {server_config.enabled})")
        return server_config
    
    def get_server_config_safe(self, server_id: str) -> Optional[MCPServerConfig]:
        """
        Get configuration for a single MCP server without failing.
        Used by MCP client for optional server lookups where None is acceptable.
        
        Args:
            server_id: The server ID to retrieve
            
        Returns:
            MCPServerConfig if found, None otherwise
        """
        return self.static_servers.get(server_id)
    
    def get_all_server_ids(self) -> List[str]:
        """
        Get all server IDs that are configured in the registry.
        
        Returns:
            List of all server IDs
        """
        return list(self.static_servers.keys()) 