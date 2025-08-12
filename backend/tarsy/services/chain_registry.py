"""
ChainRegistry for sequential agent chains.

This module replaces AgentRegistry with chain-based lookup system.
It loads built-in chains and YAML chains, validates chain_id uniqueness,
and provides chain lookup functionality for alert types.
"""

from typing import Dict, Optional
from tarsy.config.agent_config import ConfigurationLoader
from tarsy.config.builtin_config import get_builtin_chain_definitions
from tarsy.models.chains import ChainDefinitionModel, ChainStageModel
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class ChainRegistry:
    """
    Registry for chain definitions with built-in and YAML chain support.
    
    Replaces AgentRegistry with chain-based lookup system that maps
    alert types to chain definitions instead of individual agents.
    """
    
    def __init__(self, config_loader: Optional[ConfigurationLoader] = None):
        """
        Initialize the chain registry.
        
        Args:
            config_loader: Optional configuration loader for YAML chains
        """
        # Load built-in chains (always available)
        self.builtin_chains = self._load_builtin_chains()
        
        # Load YAML chains (if configuration provided)
        self.yaml_chains = self._load_yaml_chains(config_loader) if config_loader else {}
        
        # Validate chain_id uniqueness across built-in and YAML chains
        self._validate_chain_id_uniqueness()
        
        # Build unified alert type mappings (STRICT - no conflicts allowed)
        self.alert_type_mappings = self._build_alert_type_mappings()
        
        logger.info(
            f"ChainRegistry initialized with {len(self.builtin_chains)} built-in chains "
            f"and {len(self.yaml_chains)} YAML chains"
        )
    
    def _load_builtin_chains(self) -> Dict[str, ChainDefinitionModel]:
        """Load built-in chain definitions."""
        builtin_chain_data = get_builtin_chain_definitions()
        builtin_chains = {}
        
        for chain_id, chain_data in builtin_chain_data.items():
            try:
                # Convert dictionary data to ChainDefinitionModel with proper stage objects
                from tarsy.models.chains import ChainStageModel
                chain_def = ChainDefinitionModel(
                    chain_id=chain_id,
                    alert_types=chain_data["alert_types"],
                    stages=[
                        ChainStageModel(name=stage["name"], agent=stage["agent"], iteration_strategy=stage.get("iteration_strategy"))
                        for stage in chain_data["stages"]
                    ],
                    description=chain_data.get("description")
                )
                builtin_chains[chain_id] = chain_def
                logger.debug(f"Loaded built-in chain: {chain_id}")
                
            except Exception as e:
                logger.error(f"Failed to load built-in chain {chain_id}: {e}")
                continue
        
        logger.info(f"Loaded {len(builtin_chains)} built-in chains")
        return builtin_chains
    
    def _load_yaml_chains(self, config_loader: ConfigurationLoader) -> Dict[str, ChainDefinitionModel]:
        """Load YAML chain definitions."""
        try:
            chain_configs = config_loader.get_chain_configs()
            yaml_chains = {}
            
            for chain_id, chain_data in chain_configs.items():
                try:
                    # Convert dictionary data to ChainDefinitionModel with proper stage objects
                    chain_def = ChainDefinitionModel(
                        chain_id=chain_id,
                        alert_types=chain_data["alert_types"],
                        stages=[
                            ChainStageModel(name=stage["name"], agent=stage["agent"], iteration_strategy=stage.get("iteration_strategy"))
                            for stage in chain_data["stages"]
                        ],
                        description=chain_data.get("description")
                    )
                    yaml_chains[chain_id] = chain_def
                    logger.debug(f"Loaded YAML chain: {chain_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to load YAML chain {chain_id}: {e}")
                    continue
            
            logger.info(f"Loaded {len(yaml_chains)} YAML chains")
            return yaml_chains
            
        except Exception as e:
            logger.warning(f"Failed to load YAML chains: {e}")
            return {}
    
    def _validate_chain_id_uniqueness(self):
        """Ensure chain_ids are unique across built-in and YAML chains."""
        builtin_ids = set(self.builtin_chains.keys())
        yaml_ids = set(self.yaml_chains.keys())
        
        conflicts = builtin_ids & yaml_ids
        if conflicts:
            conflict_list = sorted(conflicts)
            raise ValueError(
                f"Chain ID conflicts detected between built-in and YAML chains: {conflict_list}. "
                f"Each chain_id must be unique across all chain sources."
            )
        
        logger.info(f"Chain ID validation passed: {len(builtin_ids)} built-in, {len(yaml_ids)} YAML chains")
    
    def _build_alert_type_mappings(self) -> Dict[str, str]:
        """Build unified alert type to chain_id mappings."""
        mappings = {}
        
        # Add built-in chain mappings
        for chain_id, chain_def in self.builtin_chains.items():
            for alert_type in chain_def.alert_types:
                if alert_type in mappings:
                    existing_chain = mappings[alert_type]
                    raise ValueError(
                        f"Alert type '{alert_type}' conflicts: handled by both "
                        f"built-in chain '{existing_chain}' and built-in chain '{chain_id}'"
                    )
                mappings[alert_type] = chain_id
        
        # Add YAML chain mappings (check for conflicts)
        for chain_id, chain_def in self.yaml_chains.items():
            for alert_type in chain_def.alert_types:
                if alert_type in mappings:
                    existing_chain = mappings[alert_type]
                    existing_source = "built-in" if existing_chain in self.builtin_chains else "YAML"
                    raise ValueError(
                        f"Alert type '{alert_type}' conflicts: handled by both "
                        f"{existing_source} chain '{existing_chain}' and YAML chain '{chain_id}'"
                    )
                mappings[alert_type] = chain_id
        
        logger.info(f"Built alert type mappings for {len(mappings)} alert types")
        return mappings
    
    def get_chain_for_alert_type(self, alert_type: str) -> ChainDefinitionModel:
        """
        Always returns a chain. Single agents become 1-stage chains.
        
        Args:
            alert_type: The alert type to find a chain for
            
        Returns:
            ChainDefinitionModel for the alert type
            
        Raises:
            ValueError: If no chain is found for the alert type
        """
        chain_id = self.alert_type_mappings.get(alert_type)
        if not chain_id:
            available_types = sorted(self.alert_type_mappings.keys())
            raise ValueError(
                f"No chain found for alert type '{alert_type}'. "
                f"Available: {', '.join(available_types)}"
            )
        
        # Return chain from appropriate source (built-in or YAML)
        chain_def = self.builtin_chains.get(chain_id) or self.yaml_chains.get(chain_id)
        if not chain_def:
            raise ValueError(f"Chain '{chain_id}' not found in registry")
        
        return chain_def
    
    def list_available_alert_types(self) -> list[str]:
        """Get list of all available alert types."""
        return sorted(self.alert_type_mappings.keys())
    
    def list_available_chains(self) -> list[str]:
        """Get list of all available chain IDs."""
        all_chains = set(self.builtin_chains.keys()) | set(self.yaml_chains.keys())
        return sorted(all_chains)
    
    def get_chain_by_id(self, chain_id: str) -> Optional[ChainDefinitionModel]:
        """Get a specific chain by its ID."""
        return self.builtin_chains.get(chain_id) or self.yaml_chains.get(chain_id)