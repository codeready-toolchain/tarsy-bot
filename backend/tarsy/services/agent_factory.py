"""
Agent Factory for creating specialized agent instances.

This module provides a factory for instantiating agent classes with
proper dependency injection. It maintains a static registry of available
agent classes and handles creation of both traditional agents and
configuration-based agents.
"""

import importlib
from typing import Any, Dict, Optional, Type

from tarsy.agents.base_agent import BaseAgent
from tarsy.integrations.llm.client import LLMClient
from tarsy.integrations.mcp.client import MCPClient
from tarsy.utils.logger import get_module_logger
from tarsy.config.builtin_config import get_builtin_agent_import_mapping, get_builtin_agent_config
from tarsy.agents.constants import IterationStrategy

from .mcp_server_registry import MCPServerRegistry

# Import for type hints only (avoid circular imports)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..models.agent_config import AgentConfigModel

logger = get_module_logger(__name__)


class AgentFactory:
    """
    Factory for creating agent instances with dependency injection.
    
    This class maintains a static registry of agent classes and provides
    methods to instantiate both traditional BaseAgent subclasses and
    configuration-based agents with all required dependencies.
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        mcp_client: MCPClient,
        mcp_registry: MCPServerRegistry,
        agent_configs: Optional[Dict[str, "AgentConfigModel"]] = None
    ):
        """
        Initialize the agent factory with dependencies.
        
        Args:
            llm_client: Client for LLM interactions
            mcp_client: Client for MCP server interactions
            mcp_registry: Registry of MCP server configurations (REQUIRED)
            agent_configs: Optional dictionary of configured agents for ConfigurableAgent creation
        """
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.mcp_registry = mcp_registry
        self.agent_configs = agent_configs
        
        # Static registry of available agent classes - loaded from central configuration
        self.static_agent_classes: Dict[str, Type[BaseAgent]] = {}
        self._load_builtin_agent_classes()
        
        configured_count = len(self.agent_configs) if self.agent_configs else 0
        logger.info(f"Initialized Agent Factory with {len(self.static_agent_classes)} built-in agent classes and {configured_count} configured agents")
    
    def _load_builtin_agent_classes(self) -> None:
        """
        Dynamically load built-in agent classes from central configuration.
        Uses import paths to avoid circular imports.
        """
        
        for class_name, import_path in get_builtin_agent_import_mapping().items():
            try:
                # Parse module and class name from import path
                module_path, class_name_from_path = import_path.rsplit('.', 1)
                
                # Dynamically import the module and get the class
                module = importlib.import_module(module_path)
                agent_class = getattr(module, class_name_from_path)
                
                # Store in registry
                self.static_agent_classes[class_name] = agent_class
                
                logger.debug(f"Loaded built-in agent class: {class_name}")
                
            except (ImportError, AttributeError) as e:
                logger.error(f"Failed to load built-in agent class '{class_name}' from '{import_path}': {e}")
                # Fail fast for built-in agents - they should always be available
                raise ValueError(f"Built-in agent '{class_name}' could not be loaded: {e}")
    

    def create_agent(self, agent_class_name: str) -> BaseAgent:
        """
        Create an agent instance with dependency injection.
        
        Supports both traditional BaseAgent subclasses and configured agents.
        Configured agents are identified by the format "ConfigurableAgent:agent-name".
        
        Args:
            agent_class_name: Name of the agent class or configured agent identifier
            
        Returns:
            Instantiated agent with injected dependencies
            
        Raises:
            ValueError: If the agent class is not registered or configured
        """
        try:
            # Handle traditional BaseAgent subclasses
            if agent_class_name in self.static_agent_classes:
                return self._create_traditional_agent(agent_class_name)
            
            # Handle configured agents (format: "ConfigurableAgent:agent-name")
            if agent_class_name.startswith("ConfigurableAgent:"):
                return self._create_configured_agent(agent_class_name)
            
            # Simple technical error message
            configurable_agents = [f"ConfigurableAgent:{name}" for name in self.agent_configs.keys()] if self.agent_configs else []
            all_available = list(self.static_agent_classes.keys()) + configurable_agents
            raise ValueError(f"Unknown agent '{agent_class_name}'. Available: {all_available}")
            
        except Exception as e:
            # Enhance error context for debugging
            logger.error(f"Failed to create agent '{agent_class_name}': {e}")
            raise
    
    def _create_traditional_agent(self, agent_class_name: str) -> BaseAgent:
        """
        Create a traditional BaseAgent subclass instance.
        
        Args:
            agent_class_name: Name of the agent class to instantiate
            
        Returns:
            Instantiated traditional agent
            
        Raises:
            ValueError: If agent creation fails
        """
        try:
            agent_class = self.static_agent_classes[agent_class_name]
            
            # Validate dependencies before creation
            self._validate_dependencies_for_traditional_agent(agent_class_name)
            
            # Get iteration strategy from built-in configuration
            agent_config = get_builtin_agent_config(agent_class_name)
            strategy_value = agent_config.get("iteration_strategy", IterationStrategy.REACT)
            # Convert string from builtin config to IterationStrategy enum and validate
            try:
                iteration_strategy = IterationStrategy(strategy_value)
            except ValueError:
                allowed = ", ".join([s.value for s in IterationStrategy])
                raise ValueError(
                    f"Invalid iteration strategy '{strategy_value}' for built-in agent '{agent_class_name}'. "
                    f"Allowed values: {allowed}"
                )
            
            agent = agent_class(
                llm_client=self.llm_client,
                mcp_client=self.mcp_client,
                mcp_registry=self.mcp_registry,
                iteration_strategy=iteration_strategy
            )
            
            logger.info(f"Created traditional agent instance: {agent_class_name}")
            return agent
            
        except TypeError as e:
            raise ValueError(f"Constructor error for '{agent_class_name}': {e}")
        except Exception as e:
            raise ValueError(f"Failed to create '{agent_class_name}': {e}")
    
    def _create_configured_agent(self, agent_class_name: str) -> BaseAgent:
        """
        Create a ConfigurableAgent instance.
        
        Args:
            agent_class_name: Configured agent identifier (format: "ConfigurableAgent:agent-name")
            
        Returns:
            Instantiated configured agent
            
        Raises:
            ValueError: If agent creation fails
        """
        try:
            agent_name = agent_class_name.split(":", 1)[1]
            
            if not self.agent_configs or agent_name not in self.agent_configs:
                available_configs = list(self.agent_configs.keys()) if self.agent_configs else []
                raise ValueError(f"Unknown configured agent '{agent_name}'. Available: {available_configs}")
            
            # Validate dependencies before creation
            self._validate_dependencies_for_configured_agent(agent_name)
            
            # Import ConfigurableAgent here to avoid circular imports
            from ..agents.configurable_agent import ConfigurableAgent
            
            agent = ConfigurableAgent(
                config=self.agent_configs[agent_name],
                llm_client=self.llm_client,
                mcp_client=self.mcp_client,
                mcp_registry=self.mcp_registry,
                agent_name=agent_name
            )
            
            logger.info(f"Created configured agent instance: {agent_name}")
            return agent
            
        except ValueError:
            # Re-raise ValueError exceptions (they have good error messages)
            raise
        except TypeError as e:
            raise ValueError(f"Constructor error for configured agent '{agent_name}': {e}")
        except Exception as e:
            raise ValueError(f"Failed to create configured agent '{agent_name}': {e}")
    
    def _validate_dependencies_for_traditional_agent(self, agent_class_name: str) -> None:
        """
        Validate that all dependencies are available for traditional agent creation.
        
        Args:
            agent_class_name: Name of the agent class
            
        Raises:
            ValueError: If any required dependency is missing
        """
        errors = []
        
        if self.llm_client is None:
            errors.append("LLM client is not initialized")
        
        if self.mcp_client is None:
            errors.append("MCP client is not initialized")
        
        if self.mcp_registry is None:
            errors.append("MCP registry is not initialized")
        
        if errors:
            raise ValueError(f"Missing dependencies for '{agent_class_name}': {', '.join(errors)}")
    
    def _validate_dependencies_for_configured_agent(self, agent_name: str) -> None:
        """
        Validate that all dependencies are available for configured agent creation.
        
        Args:
            agent_name: Name of the configured agent
            
        Raises:
            ValueError: If any required dependency is missing
        """
        errors = []
        
        if self.llm_client is None:
            errors.append("LLM client is not initialized")
        
        if self.mcp_client is None:
            errors.append("MCP client is not initialized")
        
        if self.mcp_registry is None:
            errors.append("MCP registry is not initialized")
        
        # Validate that agent configuration is valid
        agent_config = self.agent_configs[agent_name]
        
        # Check that all referenced MCP servers exist in the registry
        try:
            for server_id in agent_config.mcp_servers:
                self.mcp_registry.get_server_config(server_id)
        except ValueError as e:
            errors.append(f"Agent '{agent_name}': {str(e)}")
        
        if errors:
            raise ValueError(f"Dependency issues for configured agent '{agent_name}': {', '.join(errors)}") 