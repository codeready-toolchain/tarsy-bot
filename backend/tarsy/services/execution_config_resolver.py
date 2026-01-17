"""
Unified configuration resolution for agent execution.

This module provides centralized logic for resolving all hierarchical configuration
settings (iteration config, MCP servers, LLM provider, iteration strategy) into a
single AgentExecutionConfig object.

Resolves settings across the configuration hierarchy:
system → agent → chain → stage → parallel agent (highest precedence)
"""

from typing import Optional, Union

from tarsy.config.settings import Settings
from tarsy.models.agent_config import (
    AgentConfigModel,
    ChainConfigModel,
    ChainStageConfigModel,
    IterationStrategy,
    ParallelAgentConfig,
)
from tarsy.models.agent_execution_config import AgentExecutionConfig
from tarsy.services.iteration_config_resolver import IterationConfigResolver
from tarsy.services.mcp_config_resolver import MCPConfigResolver
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class ExecutionConfigResolver:
    """
    Resolver for unified agent execution configuration.
    
    Consolidates resolution of all hierarchical configuration settings:
    - max_iterations / force_conclusion (via IterationConfigResolver)
    - mcp_servers (via MCPConfigResolver)
    - llm_provider (inline resolution)
    - iteration_strategy (inline resolution)
    
    Returns a single AgentExecutionConfig object with all resolved settings.
    """
    
    @staticmethod
    def resolve_config(
        system_settings: Settings,
        agent_config: Optional[AgentConfigModel] = None,
        chain_config: Optional[ChainConfigModel] = None,
        stage_config: Optional[ChainStageConfigModel] = None,
        parallel_agent_config: Optional[ParallelAgentConfig] = None,
    ) -> AgentExecutionConfig:
        """
        Resolve all configuration settings from hierarchy into aggregate object.
        
        Args:
            system_settings: System-level settings (always present, lowest precedence)
            agent_config: Optional agent-level configuration
            chain_config: Optional chain-level configuration
            stage_config: Optional stage-level configuration
            parallel_agent_config: Optional parallel agent configuration (highest precedence)
            
        Returns:
            AgentExecutionConfig with all resolved settings
            
        Example:
            >>> from tarsy.config.settings import get_settings
            >>> settings = get_settings()
            >>> config = ExecutionConfigResolver.resolve_config(
            ...     system_settings=settings,
            ...     stage_config=stage_config
            ... )
            >>> print(config.llm_provider, config.mcp_servers)
        """
        logger.debug("Resolving unified agent execution configuration")
        
        # Resolve iteration configuration (max_iterations, force_conclusion)
        max_iterations, force_conclusion = IterationConfigResolver.resolve_iteration_config(
            system_settings=system_settings,
            agent_config=agent_config,
            chain_config=chain_config,
            stage_config=stage_config,
            parallel_agent_config=parallel_agent_config,
        )
        
        # Resolve MCP servers
        mcp_servers = MCPConfigResolver.resolve_mcp_servers(
            agent_config=agent_config,
            chain_config=chain_config,
            stage_config=stage_config,
            parallel_agent_config=parallel_agent_config,
        )
        
        # Resolve LLM provider (same precedence pattern)
        llm_provider = ExecutionConfigResolver._resolve_llm_provider(
            chain_config=chain_config,
            stage_config=stage_config,
            parallel_agent_config=parallel_agent_config,
        )
        
        # Resolve iteration strategy (same precedence pattern)
        iteration_strategy = ExecutionConfigResolver._resolve_iteration_strategy(
            agent_config=agent_config,
            stage_config=stage_config,
            parallel_agent_config=parallel_agent_config,
        )
        
        config = AgentExecutionConfig(
            llm_provider=llm_provider,
            iteration_strategy=iteration_strategy,
            max_iterations=max_iterations,
            force_conclusion=force_conclusion,
            mcp_servers=mcp_servers,
        )
        
        logger.info(
            f"Resolved execution config: llm_provider={config.llm_provider}, "
            f"iteration_strategy={config.iteration_strategy}, "
            f"max_iterations={config.max_iterations}, "
            f"force_conclusion={config.force_conclusion}, "
            f"mcp_servers={config.mcp_servers}"
        )
        
        return config
    
    @staticmethod
    def _resolve_llm_provider(
        chain_config: Optional[ChainConfigModel] = None,
        stage_config: Optional[ChainStageConfigModel] = None,
        parallel_agent_config: Optional[ParallelAgentConfig] = None,
    ) -> Optional[str]:
        """
        Resolve LLM provider from configuration hierarchy.
        
        Priority (highest to lowest):
        1. parallel_agent_config.llm_provider
        2. stage_config.llm_provider
        3. chain_config.llm_provider
        
        Note: Agent-level LLM provider is not supported (agents don't have this field).
        System-level default is handled by LLMManager when llm_provider is None.
        
        Args:
            chain_config: Optional chain-level configuration
            stage_config: Optional stage-level configuration
            parallel_agent_config: Optional parallel agent configuration
            
        Returns:
            LLM provider name if configured, or None (system default will be used)
        """
        llm_provider = None
        
        # Start with chain-level
        if chain_config is not None and chain_config.llm_provider is not None:
            llm_provider = chain_config.llm_provider
            logger.debug(f"Chain-level LLM provider: {llm_provider}")
        
        # Apply stage-level override if present
        if stage_config is not None and stage_config.llm_provider is not None:
            llm_provider = stage_config.llm_provider
            logger.debug(f"Stage-level LLM provider override: {llm_provider}")
        
        # Apply parallel agent-level override if present (highest precedence)
        if parallel_agent_config is not None and parallel_agent_config.llm_provider is not None:
            llm_provider = parallel_agent_config.llm_provider
            logger.debug(f"Parallel agent-level LLM provider override: {llm_provider}")
        
        return llm_provider
    
    @staticmethod
    def _resolve_iteration_strategy(
        agent_config: Optional[AgentConfigModel] = None,
        stage_config: Optional[ChainStageConfigModel] = None,
        parallel_agent_config: Optional[ParallelAgentConfig] = None,
    ) -> Optional[str]:
        """
        Resolve iteration strategy from configuration hierarchy.
        
        Priority (highest to lowest):
        1. parallel_agent_config.iteration_strategy
        2. stage_config.iteration_strategy
        3. agent_config.iteration_strategy
        
        Note: Chain-level iteration_strategy is not supported.
        
        Args:
            agent_config: Optional agent-level configuration
            stage_config: Optional stage-level configuration
            parallel_agent_config: Optional parallel agent configuration
            
        Returns:
            Iteration strategy string if configured, or None (agent default will be used)
        """
        iteration_strategy = None
        
        # Start with agent-level
        if agent_config is not None and agent_config.iteration_strategy is not None:
            iteration_strategy = ExecutionConfigResolver._normalize_iteration_strategy(
                agent_config.iteration_strategy
            )
            logger.debug(f"Agent-level iteration strategy: {iteration_strategy}")
        
        # Apply stage-level override if present
        if stage_config is not None and stage_config.iteration_strategy is not None:
            iteration_strategy = ExecutionConfigResolver._normalize_iteration_strategy(
                stage_config.iteration_strategy
            )
            logger.debug(f"Stage-level iteration strategy override: {iteration_strategy}")
        
        # Apply parallel agent-level override if present (highest precedence)
        if parallel_agent_config is not None and parallel_agent_config.iteration_strategy is not None:
            iteration_strategy = ExecutionConfigResolver._normalize_iteration_strategy(
                parallel_agent_config.iteration_strategy
            )
            logger.debug(f"Parallel agent-level iteration strategy override: {iteration_strategy}")
        
        return iteration_strategy
    
    @staticmethod
    def _normalize_iteration_strategy(
        strategy: Union[str, IterationStrategy, None]
    ) -> Optional[str]:
        """
        Normalize iteration strategy to string representation.
        
        Handles both IterationStrategy enum values and plain strings to prevent
        Enum leakage into downstream components.
        
        Args:
            strategy: Strategy as IterationStrategy enum or string, or None
            
        Returns:
            Normalized string representation or None
        """
        if strategy is None:
            return None
        
        if isinstance(strategy, IterationStrategy):
            return strategy.value
        
        return str(strategy)
