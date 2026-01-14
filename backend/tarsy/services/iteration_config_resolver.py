"""
Configuration resolution service for hierarchical iteration settings.

This module provides centralized logic for resolving max_iterations and
force_conclusion_at_max_iterations settings across the configuration hierarchy:
system → agent → chain → stage → parallel agent (highest precedence).
"""

from typing import Optional, Tuple

from tarsy.config.settings import Settings
from tarsy.models.agent_config import (
    AgentConfigModel,
    ChainConfigModel,
    ChainStageConfigModel,
    ParallelAgentConfig,
)
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class IterationConfigResolver:
    """
    Resolver for hierarchical iteration configuration settings.
    
    Implements the precedence order:
    parallel_agent → stage → chain → agent → system (lowest precedence)
    
    Each level can override the settings from lower levels. If a level
    doesn't specify a value (None), the next lower level's value is used.
    """
    
    @staticmethod
    def resolve_iteration_config(
        system_settings: Settings,
        agent_config: Optional[AgentConfigModel] = None,
        chain_config: Optional[ChainConfigModel] = None,
        stage_config: Optional[ChainStageConfigModel] = None,
        parallel_agent_config: Optional[ParallelAgentConfig] = None,
    ) -> Tuple[int, bool]:
        """
        Resolve max_iterations and force_conclusion_at_max_iterations from hierarchy.
        
        Args:
            system_settings: System-level settings (always present, lowest precedence)
            agent_config: Optional agent-level configuration
            chain_config: Optional chain-level configuration
            stage_config: Optional stage-level configuration
            parallel_agent_config: Optional parallel agent configuration (highest precedence)
            
        Returns:
            Tuple of (max_iterations, force_conclusion_at_max_iterations)
            
        Example:
            >>> from tarsy.config.settings import get_settings
            >>> settings = get_settings()
            >>> max_iter, force_conclude = IterationConfigResolver.resolve_iteration_config(
            ...     system_settings=settings,
            ...     stage_config=stage_config  # Override at stage level
            ... )
        """
        # Start with system defaults (always present)
        max_iterations = system_settings.max_llm_mcp_iterations
        force_conclusion = system_settings.force_conclusion_at_max_iterations
        
        logger.debug(
            f"Resolving iteration config - System defaults: "
            f"max_iterations={max_iterations}, force_conclusion={force_conclusion}"
        )
        
        # Apply agent-level overrides if present
        if agent_config is not None:
            if agent_config.max_iterations is not None:
                max_iterations = agent_config.max_iterations
                logger.debug(f"Agent override: max_iterations={max_iterations}")
            if agent_config.force_conclusion_at_max_iterations is not None:
                force_conclusion = agent_config.force_conclusion_at_max_iterations
                logger.debug(f"Agent override: force_conclusion={force_conclusion}")
        
        # Apply chain-level overrides if present
        if chain_config is not None:
            if chain_config.max_iterations is not None:
                max_iterations = chain_config.max_iterations
                logger.debug(f"Chain override: max_iterations={max_iterations}")
            if chain_config.force_conclusion_at_max_iterations is not None:
                force_conclusion = chain_config.force_conclusion_at_max_iterations
                logger.debug(f"Chain override: force_conclusion={force_conclusion}")
        
        # Apply stage-level overrides if present
        if stage_config is not None:
            if stage_config.max_iterations is not None:
                max_iterations = stage_config.max_iterations
                logger.debug(f"Stage override: max_iterations={max_iterations}")
            if stage_config.force_conclusion_at_max_iterations is not None:
                force_conclusion = stage_config.force_conclusion_at_max_iterations
                logger.debug(f"Stage override: force_conclusion={force_conclusion}")
        
        # Apply parallel agent-level overrides if present (highest precedence)
        if parallel_agent_config is not None:
            if parallel_agent_config.max_iterations is not None:
                max_iterations = parallel_agent_config.max_iterations
                logger.debug(f"Parallel agent override: max_iterations={max_iterations}")
            if parallel_agent_config.force_conclusion_at_max_iterations is not None:
                force_conclusion = parallel_agent_config.force_conclusion_at_max_iterations
                logger.debug(f"Parallel agent override: force_conclusion={force_conclusion}")
        
        logger.info(
            f"Resolved iteration config: max_iterations={max_iterations}, "
            f"force_conclusion={force_conclusion}"
        )
        
        return max_iterations, force_conclusion
