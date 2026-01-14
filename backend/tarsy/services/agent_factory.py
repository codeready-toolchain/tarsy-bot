"""
Agent Factory for creating specialized agent instances.

This module provides a factory for instantiating agent classes with
proper dependency injection. It maintains a static registry of available
agent classes and handles creation of both traditional agents and
configuration-based agents.
"""

import importlib

# Import for type hints only (avoid circular imports)
from typing import TYPE_CHECKING, Dict, Optional, Type

from tarsy.agents.base_agent import BaseAgent
from tarsy.config.builtin_config import (
    get_builtin_agent_config,
    get_builtin_agent_import_mapping,
)
from tarsy.integrations.llm.manager import LLMManager
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.constants import IterationStrategy
from tarsy.utils.logger import get_module_logger

from .mcp_server_registry import MCPServerRegistry

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
        llm_manager: LLMManager,
        mcp_registry: MCPServerRegistry,
        agent_configs: Optional[Dict[str, "AgentConfigModel"]] = None
    ):
        """
        Initialize the agent factory with dependencies.
        
        Args:
            llm_manager: LLM manager for accessing LLM clients (both LangChain and native thinking)
            mcp_registry: Registry of MCP server configurations (REQUIRED)
            agent_configs: Optional dictionary of configured agents for ConfigurableAgent creation
            
        Note:
            MCP client is NOT stored - it must be provided per agent creation
            to ensure proper isolation between alert sessions.
        """
        self.llm_manager = llm_manager
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
    

    def create_agent(self, agent_name: str, mcp_client: MCPClient) -> BaseAgent:
        """
        Create an agent instance with dependency injection.
        
        Supports both traditional BaseAgent subclasses and configured agents.
        Configured agents are checked first since they're more specific.
        
        Args:
            agent_name: Name of the agent (configured agents take precedence over built-in)
            mcp_client: Session-scoped MCP client for this agent instance
            
        Returns:
            Instantiated agent with injected dependencies
            
        Raises:
            ValueError: If the agent is not found in configured or built-in agents
        """
        try:
            # Check configured agents first (they're more specific and can override built-ins)
            if self.agent_configs and agent_name in self.agent_configs:
                return self._create_configured_agent(agent_name, mcp_client)
            
            # Check built-in agents second
            if agent_name in self.static_agent_classes:
                return self._create_traditional_agent(agent_name, mcp_client)
            
            # Generate helpful error message
            available_agents = []
            if self.agent_configs:
                available_agents.extend(self.agent_configs.keys())
            available_agents.extend(self.static_agent_classes.keys())
            
            raise ValueError(f"Unknown agent '{agent_name}'. Available: {available_agents}")
            
        except Exception as e:
            # Enhance error context for debugging
            logger.error(f"Failed to create agent '{agent_name}': {e}")
            raise

    def get_agent(
        self, 
        agent_identifier: str, 
        mcp_client: MCPClient, 
        iteration_strategy: Optional[str] = None,
        llm_provider: Optional[str] = None,
        max_iterations: Optional[int] = None,
        force_conclusion: Optional[bool] = None
    ) -> BaseAgent:
        """
        Get agent instance by identifier with optional strategy and provider overrides.
        
        All agent usage is chain-based (single-agent flows are chains with one stage).
        Always creates a unique instance to prevent race conditions between stages.
        
        Args:
            agent_identifier: Agent name (e.g., "KubernetesAgent" for builtin or "ArgoCDAgent" for configured)
            mcp_client: Session-scoped MCP client for this agent instance
            iteration_strategy: Strategy to use for this stage (overrides agent default)
            llm_provider: Optional LLM provider name for this agent (overrides global default)
            max_iterations: Optional max iterations override (from hierarchy resolution)
            force_conclusion: Optional force conclusion override (from hierarchy resolution)
        
        Returns:
            Agent instance configured with appropriate strategy and provider
        """
        # Create agent using existing create_agent method with session-scoped client
        agent = self.create_agent(agent_identifier, mcp_client)
        
        # Override strategy if provided
        if iteration_strategy:
            try:
                strategy_enum = IterationStrategy(iteration_strategy)
                agent.set_iteration_strategy(strategy_enum)
            except ValueError:
                logger.warning(f"Invalid iteration strategy '{iteration_strategy}', using agent default")
        
        # Set LLM provider override if provided
        if llm_provider:
            agent.set_llm_provider(llm_provider)
            logger.debug(f"Agent {agent_identifier} configured with LLM provider: {llm_provider}")
        
        # Set max_iterations override if provided
        if max_iterations is not None:
            agent.set_max_iterations(max_iterations)
        
        # Set force_conclusion override if provided
        if force_conclusion is not None:
            agent.set_force_conclusion(force_conclusion)
        
        return agent
    
    def _create_traditional_agent(self, agent_class_name: str, mcp_client: MCPClient) -> BaseAgent:
        """
        Create a traditional BaseAgent subclass instance.
        
        Args:
            agent_class_name: Name of the agent class to instantiate
            mcp_client: Session-scoped MCP client for this agent instance
            
        Returns:
            Instantiated traditional agent
            
        Raises:
            ValueError: If agent creation fails
        """
        try:
            agent_class = self.static_agent_classes[agent_class_name]
            
            # Validate dependencies before creation
            self._validate_dependencies_for_traditional_agent(agent_class_name)
            
            # All built-in agents now extend BaseAgent with standard constructor
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
                llm_manager=self.llm_manager,
                mcp_client=mcp_client,
                mcp_registry=self.mcp_registry,
                iteration_strategy=iteration_strategy
            )
            
            logger.info(f"Created traditional agent instance: {agent_class_name}")
            return agent
            
        except TypeError as e:
            raise ValueError(f"Constructor error for '{agent_class_name}': {e}")
        except Exception as e:
            raise ValueError(f"Failed to create '{agent_class_name}': {e}")
    
    def _create_configured_agent(self, agent_name: str, mcp_client: MCPClient) -> BaseAgent:
        """
        Create a ConfigurableAgent instance.
        
        Args:
            agent_name: Name of the configured agent (no prefix required)
            mcp_client: Session-scoped MCP client for this agent instance
            
        Returns:
            Instantiated configured agent
            
        Raises:
            ValueError: If agent creation fails
        """
        try:
            if not self.agent_configs or agent_name not in self.agent_configs:
                available_configs = list(self.agent_configs.keys()) if self.agent_configs else []
                raise ValueError(f"Unknown configured agent '{agent_name}'. Available: {available_configs}")
            
            # Validate dependencies before creation
            self._validate_dependencies_for_configured_agent(agent_name)
            
            # Import ConfigurableAgent here to avoid circular imports
            from ..agents.configurable_agent import ConfigurableAgent
            
            agent = ConfigurableAgent(
                config=self.agent_configs[agent_name],
                llm_manager=self.llm_manager,
                mcp_client=mcp_client,
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
        
        if self.llm_manager is None:
            errors.append("LLM manager is not initialized")
        
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
        
        if self.llm_manager is None:
            errors.append("LLM manager is not initialized")
        
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