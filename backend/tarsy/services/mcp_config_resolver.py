"""
Configuration resolution service for hierarchical MCP server settings.

This module provides centralized logic for resolving mcp_servers settings across
the configuration hierarchy: agent → chain → stage → parallel agent
(highest precedence).

The resolve_mcp_servers() function in mcp_config_resolver.py implements this
hierarchy, where each level can override settings from lower-precedence levels.

NOTE: Alert-level MCP override (ChainContext.mcp / MCPSelectionConfig) is handled
separately in BaseAgent._get_available_tools() and takes precedence over ALL
configuration-level settings resolved by this service.
"""

from typing import List, Optional

from tarsy.models.agent_config import (
    AgentConfigModel,
    ChainConfigModel,
    ChainStageConfigModel,
    ParallelAgentConfig,
)
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class MCPConfigResolver:
    """
    Resolver for hierarchical MCP server configuration settings.
    
    Implements the precedence order for CONFIGURATION-LEVEL MCP settings:
    parallel_agent → stage → chain → agent (lowest precedence)
    
    Each level can override the settings from lower levels. If a level
    doesn't specify a value (None), the next lower level's value is used.
    
    NOTE: This resolver only handles configuration-level MCP settings.
    Alert-level override (ChainContext.mcp) is the highest priority and
    is handled separately in BaseAgent._get_available_tools().
    """
    
    @staticmethod
    def resolve_mcp_servers(
        agent_config: Optional[AgentConfigModel] = None,
        chain_config: Optional[ChainConfigModel] = None,
        stage_config: Optional[ChainStageConfigModel] = None,
        parallel_agent_config: Optional[ParallelAgentConfig] = None,
    ) -> Optional[List[str]]:
        """
        Resolve MCP servers from configuration hierarchy.
        
        Priority (highest to lowest):
        1. parallel_agent_config.mcp_servers (highest configuration priority)
        2. stage_config.mcp_servers
        3. chain_config.mcp_servers
        4. agent_config.mcp_servers (lowest configuration priority)
        
        Args:
            agent_config: Optional agent-level configuration
            chain_config: Optional chain-level configuration
            stage_config: Optional stage-level configuration
            parallel_agent_config: Optional parallel agent configuration (highest precedence)
            
        Returns:
            List of MCP server IDs if configured at any level, or None if not specified
            at any configuration level. None allows agent default mcp_servers() method
            to be used.
            
        NOTE: Alert-level ChainContext.mcp override (if present) will supersede
        this resolved configuration in BaseAgent._get_available_tools().
        
        Example:
            >>> from tarsy.models.agent_config import ChainConfigModel
            >>> chain_config = ChainConfigModel(
            ...     chain_id="test",
            ...     alert_types=["test"],
            ...     stages=[...],
            ...     mcp_servers=["kubernetes-server"]
            ... )
            >>> servers = MCPConfigResolver.resolve_mcp_servers(chain_config=chain_config)
            >>> print(servers)  # ["kubernetes-server"]
        """
        mcp_servers = None
        
        logger.debug("Resolving MCP servers from configuration hierarchy")
        
        # Start with agent-level configuration (lowest priority)
        if agent_config is not None and agent_config.mcp_servers is not None:
            mcp_servers = agent_config.mcp_servers
            logger.debug(f"Agent-level MCP servers: {mcp_servers}")
        
        # Apply chain-level overrides if present
        if chain_config is not None and chain_config.mcp_servers is not None:
            mcp_servers = chain_config.mcp_servers
            logger.debug(f"Chain-level override: mcp_servers={mcp_servers}")
        
        # Apply stage-level overrides if present
        if stage_config is not None and stage_config.mcp_servers is not None:
            mcp_servers = stage_config.mcp_servers
            logger.debug(f"Stage-level override: mcp_servers={mcp_servers}")
        
        # Apply parallel agent-level overrides if present (highest configuration precedence)
        if parallel_agent_config is not None and parallel_agent_config.mcp_servers is not None:
            mcp_servers = parallel_agent_config.mcp_servers
            logger.debug(f"Parallel agent-level override: mcp_servers={mcp_servers}")
        
        if mcp_servers is not None:
            logger.info(f"Resolved MCP servers from configuration: {mcp_servers}")
        else:
            logger.debug("No MCP servers configured at any level - will use agent default")
        
        return mcp_servers
