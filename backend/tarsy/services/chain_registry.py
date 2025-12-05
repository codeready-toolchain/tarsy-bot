"""
ChainRegistry for sequential agent chains.

This module provides chain-based lookup system that maps alert types
to chain definitions. It loads built-in chains and YAML chains, validates
chain_id uniqueness, and provides chain lookup functionality for alert types.
"""

from typing import Dict, Optional
from tarsy.config.agent_config import ConfigurationLoader
from tarsy.config.builtin_config import get_builtin_chain_definitions, DEFAULT_ALERT_TYPE
from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class ChainRegistry:
    """
    Registry for chain definitions with built-in and YAML chain support.
    
    Provides chain-based lookup system that maps alert types to chain
    definitions for sequential agent processing.
    """
    
    def __init__(self, config_loader: Optional[ConfigurationLoader] = None):
        """
        Initialize the chain registry.
        
        Args:
            config_loader: Optional configuration loader for YAML chains
        """
        # Load built-in chains (always available)
        self.builtin_chains = self._load_builtin_chains()
        
        # Load YAML chains and default alert type (if configuration provided)
        self.yaml_chains = self._load_yaml_chains(config_loader) if config_loader else {}
        self.default_alert_type = self._load_default_alert_type(config_loader)
        
        # Check chain_id uniqueness - YAML chains can override built-in chains
        self.overridden_chain_ids = self._validate_chain_id_uniqueness()
        
        # Build unified alert type mappings (YAML chains override built-in for same alert_type)
        self.alert_type_mappings = self._build_alert_type_mappings()
        
        # Validate that default alert type is available
        self._validate_default_alert_type()
        
        logger.info(
            f"ChainRegistry initialized with {len(self.builtin_chains)} built-in chains "
            f"and {len(self.yaml_chains)} YAML chains, default alert type: '{self.default_alert_type}'"
        )
    
    def _load_builtin_chains(self) -> Dict[str, ChainConfigModel]:
        """Load built-in chain definitions."""
        builtin_chain_data = get_builtin_chain_definitions()
        builtin_chains = {}
        
        for chain_id, chain_data in builtin_chain_data.items():
            try:
                # Convert dictionary data to ChainConfigModel with proper stage objects
                chain_def = ChainConfigModel(
                    chain_id=chain_id,
                    alert_types=chain_data["alert_types"],
                    stages=[
                        ChainStageConfigModel(name=stage["name"], agent=stage["agent"], iteration_strategy=stage.get("iteration_strategy"))
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
    
    def _load_yaml_chains(self, config_loader: ConfigurationLoader) -> Dict[str, ChainConfigModel]:
        """Load YAML chain definitions."""
        try:
            chain_configs = config_loader.get_chain_configs()
            yaml_chains = {}
            
            for chain_id, chain_data in chain_configs.items():
                try:
                    # Convert dictionary data to ChainConfigModel with proper stage objects  
                    chain_def = ChainConfigModel(
                        chain_id=chain_id,
                        alert_types=chain_data["alert_types"],
                        stages=[
                            ChainStageConfigModel(name=stage["name"], agent=stage["agent"], iteration_strategy=stage.get("iteration_strategy"))
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
    
    def _load_default_alert_type(self, config_loader: Optional[ConfigurationLoader]) -> str:
        """
        Load default alert type from configuration or use built-in default.
        
        Args:
            config_loader: Optional configuration loader
            
        Returns:
            Default alert type (from config or DEFAULT_ALERT_TYPE constant)
            
        Raises:
            Exception: If config file exists but cannot be loaded/validated
        """
        if config_loader:
            config = config_loader.load_and_validate()
            if config.default_alert_type:
                logger.info(f"Using configured default alert type: '{config.default_alert_type}'")
                return config.default_alert_type
        
        logger.info(f"Using built-in default alert type: '{DEFAULT_ALERT_TYPE}'")
        return DEFAULT_ALERT_TYPE
    
    def _validate_chain_id_uniqueness(self) -> set[str]:
        """
        Check for chain_id conflicts between built-in and YAML chains.
        
        YAML chains are allowed to override built-in chains with the same chain_id.
        A warning is logged when an override occurs.
        
        Returns:
            Set of chain_ids that are overridden by YAML chains
        """
        builtin_ids = set(self.builtin_chains.keys())
        yaml_ids = set(self.yaml_chains.keys())
        
        overridden_chain_ids = builtin_ids & yaml_ids
        if overridden_chain_ids:
            for chain_id in sorted(overridden_chain_ids):
                logger.warning(
                    f"YAML chain '{chain_id}' overrides built-in chain with the same ID"
                )
        
        logger.info(
            f"Chain ID check: {len(builtin_ids)} built-in, {len(yaml_ids)} YAML chains, "
            f"{len(overridden_chain_ids)} overrides"
        )
        return overridden_chain_ids
    
    def _build_alert_type_mappings(self) -> Dict[str, str]:
        """
        Build unified alert type to chain_id mappings.
        
        YAML chains can override built-in chains for the same alert_type.
        Conflicts within the same source (built-in vs built-in, or YAML vs YAML) 
        still raise errors.
        """
        mappings = {}
        overridden_alert_types: list[tuple[str, str, str]] = []  # (alert_type, old_chain, new_chain)
        
        # Add built-in chain mappings first
        for chain_id, chain_def in self.builtin_chains.items():
            for alert_type in chain_def.alert_types:
                if alert_type in mappings:
                    existing_chain = mappings[alert_type]
                    raise ValueError(
                        f"Alert type '{alert_type}' conflicts: handled by both "
                        f"built-in chain '{existing_chain}' and built-in chain '{chain_id}'"
                    )
                mappings[alert_type] = chain_id
        
        # Add YAML chain mappings (can override built-in, but not other YAML chains)
        for chain_id, chain_def in self.yaml_chains.items():
            for alert_type in chain_def.alert_types:
                if alert_type in mappings:
                    existing_chain = mappings[alert_type]
                    
                    # Allow YAML to override built-in chains
                    if existing_chain in self.builtin_chains:
                        overridden_alert_types.append((alert_type, existing_chain, chain_id))
                        mappings[alert_type] = chain_id
                    else:
                        # YAML vs YAML conflict - not allowed
                        raise ValueError(
                            f"Alert type '{alert_type}' conflicts: handled by both "
                            f"YAML chain '{existing_chain}' and YAML chain '{chain_id}'"
                        )
                else:
                    mappings[alert_type] = chain_id
        
        # Log overrides
        for alert_type, old_chain, new_chain in overridden_alert_types:
            logger.warning(
                f"Alert type '{alert_type}': YAML chain '{new_chain}' overrides "
                f"built-in chain '{old_chain}'"
            )
        
        logger.info(
            f"Built alert type mappings for {len(mappings)} alert types "
            f"({len(overridden_alert_types)} overrides)"
        )
        return mappings
    
    def _validate_default_alert_type(self) -> None:
        """
        Validate that the default alert type exists in available alert types.
        
        Raises:
            ValueError: If default alert type is not available in any chain
        """
        if self.default_alert_type not in self.alert_type_mappings:
            available_types = sorted(self.alert_type_mappings.keys())
            raise ValueError(
                f"Default alert type '{self.default_alert_type}' is not available in any chain definition. "
                f"Available alert types: {', '.join(available_types)}"
            )
        
        logger.debug(f"Default alert type '{self.default_alert_type}' validation passed")
    
    def get_chain_for_alert_type(self, alert_type: str) -> ChainConfigModel:
        """
        Always returns a chain. Single agents become 1-stage chains.
        
        Args:
            alert_type: The alert type to find a chain for
            
        Returns:
            ChainConfigModel for the alert type
            
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
        
        # Return chain from appropriate source (YAML takes precedence over built-in)
        chain_def = self.yaml_chains.get(chain_id) or self.builtin_chains.get(chain_id)
        if not chain_def:
            raise ValueError(f"Chain '{chain_id}' not found in registry")
        
        return chain_def
    
    def list_available_alert_types(self) -> list[str]:
        """Get list of all available alert types."""
        return sorted(self.alert_type_mappings.keys())
    
    def get_default_alert_type(self) -> str:
        """
        Get the default alert type for clietns.
        
        Returns:
            Default alert type (from config or DEFAULT_ALERT_TYPE constant)
        """
        return self.default_alert_type
    
    def list_available_chains(self) -> list[str]:
        """Get list of all available chain IDs."""
        all_chains = set(self.builtin_chains.keys()) | set(self.yaml_chains.keys())
        return sorted(all_chains)
    
    def get_chain_by_id(self, chain_id: str) -> Optional[ChainConfigModel]:
        """Get a specific chain by its ID (YAML takes precedence over built-in)."""
        return self.yaml_chains.get(chain_id) or self.builtin_chains.get(chain_id)