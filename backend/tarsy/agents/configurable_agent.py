"""
Configuration-based agent implementation.

This module provides the ConfigurableAgent class which extends BaseAgent
to use configuration data instead of hardcoded behavior. This allows
creating agents through YAML configuration files without writing Python code.
"""

from typing import Callable, List, Optional

from ..integrations.llm.client import LLMClient
from ..integrations.mcp.client import MCPClient
from ..models.agent_config import AgentConfigModel
from ..services.mcp_server_registry import MCPServerRegistry
from ..utils.logger import get_module_logger
from .base_agent import BaseAgent
from .constants import IterationStrategy

logger = get_module_logger(__name__)


class ConfigurableAgent(BaseAgent):
    """
    Configuration-driven agent that extends BaseAgent.
    
    This agent reads its behavior from an AgentConfigModel instead of
    hardcoded methods. It maintains full compatibility with BaseAgent's
    processing logic and prompt building while allowing configuration-based
    customization of MCP servers and instructions.
    """
    
    def __init__(
        self,
        config: Optional[AgentConfigModel],
        llm_client: Optional[LLMClient],
        mcp_client: Optional[MCPClient],
        mcp_registry: Optional[MCPServerRegistry],
        agent_name: Optional[str] = None,
        progress_callback: Optional[Callable] = None
    ):
        """
        Initialize the configurable agent with configuration and dependencies.
        
        Args:
            config: Agent configuration model containing behavior specifications (validated for None)
            llm_client: Client for LLM interactions (validated for None)
            mcp_client: Client for MCP server interactions (validated for None)
            mcp_registry: Registry of MCP server configurations (validated for None)
            agent_name: Optional name for the agent (used for identification)
            progress_callback: Optional callback for progress updates
            
        Raises:
            ValueError: If configuration is invalid or dependencies are missing
        """
        try:
            # Validate configuration and dependencies before initialization
            self._validate_initialization_parameters(config, llm_client, mcp_client, mcp_registry)
            
            # Extract iteration strategy from config (defaults to REACT)
            strategy_str = getattr(config, 'iteration_strategy', None)
            iteration_strategy = IterationStrategy(strategy_str) if strategy_str else IterationStrategy.REACT
            
            # Initialize base agent with dependency injection
            super().__init__(llm_client, mcp_client, mcp_registry, progress_callback, iteration_strategy)
            
            # Store configuration for behavior customization
            self._config = config
            self._provided_agent_name = agent_name
            
            # Generate a descriptive agent name from config
            self._agent_name = self._generate_agent_name()
            
            # Validate that all configured MCP servers are available
            self._validate_mcp_server_availability()
            
            logger.info(f"Initialized ConfigurableAgent '{self._agent_name}' with "
                       f"{len(config.alert_types)} alert types and "
                       f"{len(config.mcp_servers)} MCP servers")
            logger.debug(f"Alert types: {config.alert_types}")
            logger.debug(f"MCP servers: {config.mcp_servers}")
            logger.debug(f"Custom instructions length: {len(config.custom_instructions)} characters")
            
        except Exception as e:
            # Enhance error context for configuration issues
            error_msg = f"Failed to initialize ConfigurableAgent: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e
    
    def _generate_agent_name(self) -> str:
        """
        Generate a descriptive name for logging and identification.
        
        Returns:
            Descriptive agent name based on provided name or configuration
        """
        # Use provided agent name if available
        if self._provided_agent_name:
            return f"ConfigurableAgent({self._provided_agent_name})"
        # Otherwise use the first alert type as the primary identifier
        elif self._config.alert_types:
            primary_alert = self._config.alert_types[0]
            return f"ConfigurableAgent({primary_alert})"
        else:
            return "ConfigurableAgent(unknown)"
    
    @property
    def agent_name(self) -> str:
        """Get the agent name for identification."""
        return self._provided_agent_name if self._provided_agent_name else ""
    
    def get_supported_alert_types(self) -> List[str]:
        """
        Get the alert types this configured agent can handle.
        
        This method provides visibility into what alert types this
        agent instance is configured to handle.
        
        Returns:
            List of alert types from configuration
        """
        return self._config.alert_types.copy()
    
    def __str__(self) -> str:
        """
        String representation for debugging and logging.
        
        Returns:
            Human-readable string describing this agent
        """
        return (f"ConfigurableAgent(alert_types={self._config.alert_types}, "
                f"mcp_servers={self._config.mcp_servers})")
    
    def __repr__(self) -> str:
        """
        Official string representation for debugging.
        
        Returns:
            Detailed string representation for debugging
        """
        return (f"ConfigurableAgent(config=AgentConfigModel("
                f"alert_types={self._config.alert_types!r}, "
                f"mcp_servers={self._config.mcp_servers!r}, "
                f"custom_instructions={self._config.custom_instructions!r}))")
    
    def _validate_initialization_parameters(
        self,
        config: Optional[AgentConfigModel],
        llm_client: Optional[LLMClient],
        mcp_client: Optional[MCPClient],
        mcp_registry: Optional[MCPServerRegistry]
    ) -> None:
        """
        Validate initialization parameters before creating the agent.
        
        Args:
            config: Agent configuration model (None values are explicitly validated)
            llm_client: LLM client instance (None values are explicitly validated)
            mcp_client: MCP client instance (None values are explicitly validated)
            mcp_registry: MCP server registry instance (None values are explicitly validated)
            
        Raises:
            ValueError: If any parameter is invalid or missing
        """
        errors = []
        
        # Validate configuration (fail-fast for None as per EP-0006 requirements)
        if config is None:
            errors.append("Agent configuration is required and cannot be None")
        else:
            if not config.alert_types:
                errors.append("Agent configuration must specify at least one alert type")
            if not config.mcp_servers:
                errors.append("Agent configuration must specify at least one MCP server")
        
        # Validate dependencies (fail-fast for None dependencies)
        if llm_client is None:
            errors.append("LLM client is required and cannot be None")
        if mcp_client is None:
            errors.append("MCP client is required and cannot be None")
        if mcp_registry is None:
            errors.append("MCP registry is required and cannot be None")
        
        if errors:
            raise ValueError(
                f"ConfigurableAgent initialization failed due to invalid parameters: "
                f"{', '.join(errors)}"
            )
    
    def _validate_mcp_server_availability(self) -> None:
        """
        Validate that all MCP servers referenced in the configuration are available.
        
        Raises:
            ValueError: If any referenced MCP server is not available
        """
        for server_id in self._config.mcp_servers:
            self.mcp_registry.get_server_config(server_id)
    
    def mcp_servers(self) -> List[str]:
        """
        Return the list of MCP server IDs this agent requires.
        
        This overrides the abstract method from BaseAgent to return
        the MCP servers specified in the agent's configuration.
        
        Returns:
            List of MCP server IDs from configuration
            
        Raises:
            RuntimeError: If the agent is not properly initialized
        """
        try:
            if not hasattr(self, '_config') or self._config is None:
                raise RuntimeError(
                    "ConfigurableAgent is not properly initialized - configuration is missing"
                )
            return self._config.mcp_servers
        except Exception as e:
            logger.error(f"Error retrieving MCP servers for {self._agent_name}: {e}")
            raise RuntimeError(f"Failed to retrieve MCP servers: {e}") from e
    
    def custom_instructions(self) -> str:
        """
        Return agent-specific custom instructions.
        
        This overrides the abstract method from BaseAgent to return
        the custom instructions specified in the agent's configuration.
        
        Returns:
            Custom instructions from configuration (can be empty string)
            
        Raises:
            RuntimeError: If the agent is not properly initialized
        """
        try:
            if not hasattr(self, '_config') or self._config is None:
                raise RuntimeError(
                    "ConfigurableAgent is not properly initialized - configuration is missing"
                )
            return self._config.custom_instructions
        except Exception as e:
            logger.error(f"Error retrieving custom instructions for {self._agent_name}: {e}")
            raise RuntimeError(f"Failed to retrieve custom instructions: {e}") from e
    
    @property
    def config(self) -> AgentConfigModel:
        """
        Return the agent's configuration model.
        
        Returns:
            The AgentConfigModel instance containing the agent's configuration
            
        Raises:
            RuntimeError: If the agent is not properly initialized
        """
        if not hasattr(self, '_config') or self._config is None:
            raise RuntimeError(
                "ConfigurableAgent is not properly initialized - configuration is missing"
            )
        return self._config
     