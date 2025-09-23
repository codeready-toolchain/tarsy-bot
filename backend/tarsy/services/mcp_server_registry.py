"""
MCP Server Registry for managing MCP server configurations.

This module provides a simple static registry for MCP server configurations
with embedded LLM instructions. The registry is loaded once at startup and
serves as the single source of truth for all MCP server configurations,
including both built-in and configured servers.
"""

from typing import Any, Dict, List, Optional

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
                logger.debug("Resolving templates for MCP server '%s'", server_id)
                
                # Create sanitized summary for logging (avoid exposing sensitive data)
                original_summary = self._create_config_summary(server_config, server_id)
                logger.debug("Original config summary: %s", original_summary)
                
                # Apply template resolution to built-in server configuration
                resolved_config = self.template_resolver.resolve_configuration(server_config)
                
                # Create sanitized summary of resolved config
                resolved_summary = self._create_config_summary(resolved_config, server_id)
                logger.debug("Resolved config summary: %s", resolved_summary)
                
                server_instance = MCPServerConfig(**resolved_config)
                self.static_servers[server_id] = server_instance
                
                # Log validated transport type
                transport_type = server_instance.transport.type
                logger.info("Successfully added built-in MCP server '%s' with %s transport", 
                           server_id, transport_type)
            except TemplateResolutionError as e:
                logger.error("Template resolution failed for built-in MCP server '%s': %s", server_id, e)
                # Use original config without template resolution as fallback
                fallback_instance = MCPServerConfig(**server_config)
                self.static_servers[server_id] = fallback_instance
                
                # Log validated transport type even for fallback
                transport_type = fallback_instance.transport.type
                logger.warning("Using original configuration for '%s' with %s transport due to template resolution failure", 
                             server_id, transport_type)
        
        # Add configured servers if provided
        if configured_servers:
            for server_id, server_config in configured_servers.items():
                try:
                    # Convert MCPServerConfigModel to dict and apply template resolution
                    server_dict = server_config.model_dump()
                    resolved_dict = self.template_resolver.resolve_configuration(server_dict)
                    configured_instance = MCPServerConfig(**resolved_dict)
                    self.static_servers[server_id] = configured_instance
                    
                    # Log validated transport type
                    transport_type = configured_instance.transport.type
                    logger.info("Added configured MCP server '%s' with %s transport", server_id, transport_type)
                except TemplateResolutionError as e:
                    logger.error("Template resolution failed for configured MCP server '%s': %s", server_id, e)
                    # Use original config without template resolution as fallback
                    server_dict = server_config.model_dump()
                    fallback_configured_instance = MCPServerConfig(**server_dict)
                    self.static_servers[server_id] = fallback_configured_instance
                    
                    # Log validated transport type even for fallback
                    transport_type = fallback_configured_instance.transport.type
                    logger.warning("Using original configuration for '%s' with %s transport due to template resolution failure", 
                                 server_id, transport_type)
            
            logger.info("Added %d configured MCP servers", len(configured_servers))
        
        logger.info("Initialized MCP Server Registry with %d total servers", len(self.static_servers))
    
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
            available_list = ', '.join(available_servers)
            error_msg = f"MCP server '{server_id}' not found. Available: {available_list}"
            logger.error("MCP server '%s' not found. Available: %s", server_id, available_list)
            raise ValueError(error_msg)
        
        logger.debug("Found MCP server config for '%s' (type: %s, enabled: %s)", 
                     server_id, server_config.server_type, server_config.enabled)
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
    
    def _create_config_summary(self, config: Dict[str, Any], server_id: str) -> Dict[str, Any]:
        """
        Create a sanitized summary of server configuration for logging.
        
        Removes sensitive data like bearer tokens and environment variable values 
        to prevent secret leakage in debug logs.
        
        Args:
            config: Server configuration dictionary
            server_id: Server identifier for context
            
        Returns:
            Sanitized configuration summary safe for logging
        """
        summary = {
            "server_id": server_id,
            "server_type": config.get("server_type", "unknown"),
            "enabled": config.get("enabled", True)
        }
        
        # Safely include transport configuration without sensitive data
        if "transport" in config:
            transport = config["transport"]
            transport_summary = {
                "type": transport.get("type", "unknown")
            }
            
            # Include transport-specific details without sensitive information
            if transport.get("type") == "stdio":
                transport_summary.update({
                    "command": transport.get("command"),
                    "args": transport.get("args", [])
                })
                
                # For env, only show keys to avoid exposing sensitive values
                if "env" in transport and transport["env"]:
                    env_keys = sorted(transport["env"].keys())
                    transport_summary["env_keys"] = env_keys
                else:
                    transport_summary["env_keys"] = []
                    
            elif transport.get("type") == "http":
                transport_summary.update({
                    "url": transport.get("url"),
                    "timeout": transport.get("timeout", 30),
                    "verify_ssl": transport.get("verify_ssl", True),
                    "has_bearer_token": "bearer_token" in transport and transport["bearer_token"] is not None
                })
                
                # For headers, only show keys to avoid exposing sensitive values
                if "headers" in transport and transport["headers"]:
                    header_keys = sorted(transport["headers"].keys())
                    transport_summary["header_keys"] = header_keys
                else:
                    transport_summary["header_keys"] = []
            
            summary["transport"] = transport_summary
        
        return summary 