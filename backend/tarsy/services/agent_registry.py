"""
Agent Registry for mapping alert types to specialized agent classes.

This module provides a simple static registry that maps alert types to
their corresponding agent class names. The registry is loaded once at
startup with predefined mappings and optional configured agents.
"""

from typing import Dict, Optional

from tarsy.utils.logger import get_module_logger
from tarsy.config.builtin_config import BUILTIN_CHAIN_DEFINITIONS

# Import for type hints only (avoid circular imports)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..models.agent_config import AgentConfigModel

logger = get_module_logger(__name__)


def _extract_alert_type_mappings_from_chains() -> Dict[str, str]:
    """
    Extract alert type to agent mappings from built-in chain definitions.
    
    For single-stage chains, maps alert types to the agent in that stage.
    For multi-stage chains, maps alert types to the agent in the first stage.
    
    Returns:
        Dictionary mapping alert types to agent class names
    """
    mappings = {}
    
    for chain_id, chain_config in BUILTIN_CHAIN_DEFINITIONS.items():
        alert_types = chain_config.get("alert_types", [])
        stages = chain_config.get("stages", [])
        
        if alert_types and stages:
            # Use the agent from the first stage
            first_stage_agent = stages[0].get("agent")
            if first_stage_agent:
                for alert_type in alert_types:
                    mappings[alert_type] = first_stage_agent
                    logger.debug(f"Mapped alert type '{alert_type}' to agent '{first_stage_agent}' from chain '{chain_id}'")
    
    return mappings


class AgentRegistry:
    """
    Static registry for alert type to agent class mappings.
    
    This class maintains a simple dictionary mapping from alert types
    to agent class names or configured agent identifiers. The registry 
    is immutable after initialization to ensure consistency.
    
    Supports both built-in agent classes (e.g., "KubernetesAgent") and
    configured agents (e.g., "ConfigurableAgent:security-agent").
    """
    
    # Built-in mappings extracted from chain definitions
    _DEFAULT_MAPPINGS = _extract_alert_type_mappings_from_chains()
    
    def __init__(
        self, 
        config: Optional[Dict[str, str]] = None,
        agent_configs: Optional[Dict[str, "AgentConfigModel"]] = None
    ):
        """
        Initialize the agent registry with mappings.
        
        Args:
            config: Optional dictionary mapping alert types to agent class names.
                   If None, uses default mappings defined in the registry.
            agent_configs: Optional dictionary of configured agents to include.
                          These are converted to alert type mappings automatically.
        """
        # Start with built-in mappings (config parameter or defaults)
        self.static_mappings: Dict[str, str] = config or self._DEFAULT_MAPPINGS.copy()
        

        # Add configured agent mappings if provided
        if agent_configs:
            configured_mappings = self._create_configured_mappings(agent_configs)
            self.static_mappings.update(configured_mappings)
            logger.info(f"Added {len(configured_mappings)} configured agent mappings")
            
        logger.info(f"Initialized Agent Registry with {len(self.static_mappings)} total mappings")
    
    def _create_configured_mappings(self, agent_configs: Dict[str, "AgentConfigModel"]) -> Dict[str, str]:
        """
        Convert agent configurations to alert type mappings.
        
        This method creates mappings from alert types to configured agent identifiers
        in the format "ConfigurableAgent:agent-name".
        
        Args:
            agent_configs: Dictionary of agent configurations
            
        Returns:
            Dictionary mapping alert types to configured agent identifiers
        """
        mappings = {}
        
        for agent_name, agent_config in agent_configs.items():
            for alert_type in agent_config.alert_types:
                # Map alert type to configured agent identifier
                mappings[alert_type] = f"ConfigurableAgent:{agent_name}"
                logger.debug(f"Mapped alert type '{alert_type}' to ConfigurableAgent:{agent_name}")
                
        return mappings
    
    def get_agent_for_alert_type(self, alert_type: str) -> str:
        """
        Get the agent class name for a given alert type.
        
        Args:
            alert_type: The type of alert to find an agent for
            
        Returns:
            Agent class name for the requested alert type
            
        Raises:
            ValueError: If alert_type is not found
        """
        agent_name = self.static_mappings.get(alert_type)
        
        if agent_name is None:
            # Fail-fast with technical error details
            available_types = list(self.static_mappings.keys())
            error_msg = f"No agent for alert type '{alert_type}'. Available: {', '.join(available_types)}"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.debug(f"Found agent '{agent_name}' for alert type '{alert_type}'")
        return agent_name
    

    def get_supported_alert_types(self) -> list[str]:
        """
        Get all alert types that have registered agents.
        
        Returns:
            List of supported alert types
        """
        return list(self.static_mappings.keys()) 