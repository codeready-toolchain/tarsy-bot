"""
Configuration loading and validation for agent and MCP server configurations.

This module provides centralized configuration loading, validation, and parsing logic
for configuration-based agents. It handles file loading, Pydantic validation,
conflict detection, and MCP server reference validation.
"""

import os
from typing import Any, Dict
import yaml
from pydantic import ValidationError

from ..models.agent_config import CombinedConfigModel
from ..utils.logger import get_module_logger
from .builtin_config import (
    get_builtin_agent_class_names,
    get_builtin_mcp_server_ids,
    get_builtin_chain_definitions
)
from .exceptions import ConfigurationError

logger = get_module_logger(__name__)


class ConfigurationLoader:
    """
    Centralized configuration loader with validation and conflict detection.
    
    This class handles loading agent and MCP server configurations from YAML files,
    validates them with Pydantic models, and detects conflicts with built-in components.
    """
    
    def __init__(self, config_file_path: str):
        """
        Initialize the configuration loader.
        
        Args:
            config_file_path: Path to the YAML configuration file
        """
        self.config_file_path = config_file_path
        
        # Built-in constants imported from central configuration
        self.BUILTIN_AGENT_CLASSES = get_builtin_agent_class_names()
        self.BUILTIN_MCP_SERVERS = get_builtin_mcp_server_ids()
        self.BUILTIN_CHAINS = set(get_builtin_chain_definitions().keys())
        
        logger.info(f"Initialized ConfigurationLoader with file path: {config_file_path}")
        logger.debug(f"Built-in agent classes: {self.BUILTIN_AGENT_CLASSES}")
        logger.debug(f"Built-in MCP servers: {self.BUILTIN_MCP_SERVERS}")
        logger.debug(f"Built-in chains: {self.BUILTIN_CHAINS}")
    
    def load_and_validate(self) -> CombinedConfigModel:
        """
        Load, parse and validate configuration file.
        
        This is the main entry point for configuration loading. It handles:
        - File existence checking (graceful fallback for missing files)
        - YAML parsing (fail-fast for malformed YAML)
        - Pydantic validation (fail-fast for invalid structure)
        - MCP server reference validation
        - Conflict detection (naming and alert type conflicts)
        
        Returns:
            CombinedConfigModel: Validated configuration object
            
        Raises:
            ConfigurationError: For any validation failures
        """
        logger.info(f"Loading configuration from: {self.config_file_path}")
        
        # Handle missing file gracefully - use built-in only
        if not os.path.exists(self.config_file_path):
            logger.info(f"Configuration file not found: {self.config_file_path}. Using built-in components only.")
            return CombinedConfigModel(agents={}, mcp_servers={})
        
        try:
            # Validate configuration file path
            self._validate_config_file_path()
            
            # Load and parse YAML with enhanced error handling
            logger.debug("Reading and parsing YAML configuration file")
            raw_config = self._load_yaml_file()
            
            # Handle empty or None file content
            if raw_config is None:
                logger.info("Configuration file is empty. Using built-in components only.")
                return CombinedConfigModel(agents={}, mcp_servers={})
            
            # Handle non-dictionary content (invalid root structure)
            if not isinstance(raw_config, dict):
                raise ConfigurationError(
                    f"Configuration file root must be a dictionary/object, got {type(raw_config).__name__}. "
                    f"Expected format: agents: {{...}}, mcp_servers: {{...}}"
                )
            
            # Validate with Pydantic models with enhanced error reporting
            logger.debug("Validating configuration structure with Pydantic models")
            config = self._validate_configuration_structure(raw_config)
            
            logger.info(f"Successfully parsed configuration: {len(config.agents)} agents, {len(config.mcp_servers)} MCP servers")
            
            # Enhanced validation steps
            logger.debug("Validating MCP server references")
            self._validate_mcp_server_references(config)
            
            logger.debug("Detecting circular dependencies")
            self._detect_circular_dependencies(config)
            
            logger.debug("Checking for configuration overrides")
            self._log_configuration_overrides(config)
            
            logger.debug("Validating configuration completeness")
            self._validate_configuration_completeness(config)
            
            logger.info("Configuration validation completed successfully")
            return config
            
        except PermissionError as e:
            error_msg = (
                f"Permission denied accessing configuration file {self.config_file_path}: {e}. "
                f"Please check file permissions and ensure the application has read access."
            )
            logger.error(error_msg)
            raise ConfigurationError(error_msg)
        except FileNotFoundError:
            # This should not happen due to earlier check, but handle gracefully
            logger.warning(f"Configuration file {self.config_file_path} disappeared during loading")
            return CombinedConfigModel(agents={}, mcp_servers={})
        except yaml.YAMLError as e:
            error_msg = self._format_yaml_error(e)
            logger.error(error_msg)
            raise ConfigurationError(error_msg)
        except ValidationError as e:
            error_msg = self._format_validation_error(e)
            logger.error(error_msg)
            raise ConfigurationError(error_msg)
        except ConfigurationError:
            # Re-raise ConfigurationErrors without wrapping
            raise
        except Exception as e:
            error_msg = (
                f"Unexpected error loading configuration from {self.config_file_path}: {e}. "
                f"Please verify the file exists, is readable, and contains valid YAML."
            )
            logger.error(error_msg)
            raise ConfigurationError(error_msg)

    def get_chain_configs(self) -> Dict[str, Dict[str, Any]]:
        """
        Get chain configurations from the loaded YAML file.
        
        Returns:
            Dictionary of chain configurations mapped by chain ID
        """
        try:
            config = self.load_and_validate()
            
            # Convert ChainConfigModel instances to dictionaries
            chain_configs = {}
            for chain_id, chain_config in config.agent_chains.items():
                chain_configs[chain_id] = {
                    "alert_types": chain_config.alert_types,
                    "stages": [
                        {
                            "name": stage.name,
                            "agent": stage.agent,
                            "iteration_strategy": stage.iteration_strategy
                        }
                        for stage in chain_config.stages
                    ],
                    "description": chain_config.description
                }
            
            return chain_configs
            
        except Exception as e:
            logger.warning(f"Failed to load chain configurations: {e}")
            return {}
    
    def _validate_mcp_server_references(self, config: CombinedConfigModel) -> None:
        """
        Validate all agent MCP server references exist in unified registry.
        
        This method ensures that all MCP servers referenced by configured agents
        exist in either the built-in MCP servers or the configured MCP servers.
        
        Args:
            config: The parsed configuration to validate
            
        Raises:
            ConfigurationError: If any agent references a non-existent MCP server
        """
        # Get all available MCP servers (built-in + configured)
        available_servers = set(self.BUILTIN_MCP_SERVERS)
        available_servers.update(config.mcp_servers.keys())
        
        logger.debug(f"Available MCP servers for validation: {available_servers}")
        
        # Validate each agent's MCP server references
        for agent_name, agent_config in config.agents.items():
            logger.debug(f"Validating MCP server references for agent '{agent_name}': {agent_config.mcp_servers}")
            
            for server_id in agent_config.mcp_servers:
                if server_id not in available_servers:
                    error_msg = (
                        f"Agent '{agent_name}' references unknown MCP server '{server_id}'. "
                        f"Available servers: {sorted(available_servers)}"
                    )
                    logger.error(error_msg)
                    raise ConfigurationError(error_msg)
        
        logger.debug("All MCP server references validated successfully")
    
    def _log_configuration_overrides(self, config: CombinedConfigModel) -> None:
        """
        Log info about configuration overrides.
        
        This method logs when configured items override built-in items,
        allowing users to customize built-in agents, MCP servers, and chains
        via agents.yaml configuration.
        
        Args:
            config: The parsed configuration to validate
        """
        # Log agent overrides
        for agent_name in config.agents.keys():
            if agent_name in self.BUILTIN_AGENT_CLASSES:
                logger.info(f"Configured agent '{agent_name}' will override built-in agent class")
        
        # Log MCP server overrides
        for server_id in config.mcp_servers.keys():
            if server_id in self.BUILTIN_MCP_SERVERS:
                logger.info(f"Configured MCP server '{server_id}' will override built-in MCP server")
        
        # Log chain overrides
        for chain_id in config.agent_chains.keys():
            if chain_id in self.BUILTIN_CHAINS:
                logger.info(f"Configured chain '{chain_id}' will override built-in chain")
        
        logger.debug("Configuration override check completed")
    
    def _validate_config_file_path(self) -> None:
        """
        Validate the configuration file path and accessibility.
        
        Raises:
            ConfigurationError: If the path is invalid or inaccessible
        """
        try:
            # Check if the path exists
            if not os.path.exists(self.config_file_path):
                return  # Missing file is handled gracefully elsewhere
            
            # Check if it's a file (not a directory)
            if not os.path.isfile(self.config_file_path):
                raise ConfigurationError(
                    f"Configuration path {self.config_file_path} is not a file. "
                    f"Please provide a path to a YAML configuration file."
                )
            
            # Check if it's readable
            if not os.access(self.config_file_path, os.R_OK):
                raise ConfigurationError(
                    f"Configuration file {self.config_file_path} is not readable. "
                    f"Please check file permissions."
                )
                
        except OSError as e:
            raise ConfigurationError(
                f"Error accessing configuration file {self.config_file_path}: {e}"
            )
    
    def _load_yaml_file(self) -> dict:
        """
        Load YAML file with enhanced error handling.
        
        Returns:
            Parsed YAML content as dictionary
            
        Raises:
            ConfigurationError: For YAML parsing errors with detailed messages
        """
        try:
            with open(self.config_file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except UnicodeDecodeError as e:
            raise ConfigurationError(
                f"Configuration file {self.config_file_path} contains invalid UTF-8 encoding: {e}. "
                f"Please ensure the file is saved with UTF-8 encoding."
            )
        except yaml.YAMLError as e:
            # Re-raise with more context (will be caught and formatted by main handler)
            raise
    
    def _validate_configuration_structure(self, raw_config: dict) -> CombinedConfigModel:
        """
        Validate configuration structure with enhanced error reporting.
        
        Args:
            raw_config: Raw configuration dictionary from YAML
            
        Returns:
            Validated CombinedConfigModel instance
            
        Raises:
            ValidationError: For Pydantic validation errors
        """
        try:
            # Pre-process raw_config to inject chain_id fields into agent_chains
            processed_config = raw_config.copy()
            
            if "agent_chains" in processed_config and processed_config["agent_chains"]:
                updated_chains = {}
                for chain_id, chain_data in processed_config["agent_chains"].items():
                    # Only mutate dict entries, pass through others unchanged for Pydantic validation
                    if isinstance(chain_data, dict):
                        # Add chain_id field to each chain configuration
                        updated_chain_data = chain_data.copy()
                        updated_chain_data["chain_id"] = chain_id
                        updated_chains[chain_id] = updated_chain_data
                    else:
                        # Pass through non-dict values unchanged so Pydantic can validate and surface errors
                        updated_chains[chain_id] = chain_data
                processed_config["agent_chains"] = updated_chains
            
            return CombinedConfigModel(**processed_config)
        except ValidationError as e:
            # Add context and re-raise (will be caught and formatted by main handler)
            logger.debug(f"Pydantic validation failed with {len(e.errors())} errors")
            raise
    
    def _detect_circular_dependencies(self, config: CombinedConfigModel) -> None:
        """
        Detect circular dependencies in MCP server references.
        
        Currently, MCP servers don't reference each other, so this is a placeholder
        for future functionality if MCP servers can depend on each other.
        
        Args:
            config: The parsed configuration to validate
            
        Raises:
            ConfigurationError: If circular dependencies are detected
        """
        # For now, this is a placeholder since MCP servers don't reference each other
        # in the current design. This method is here for future extensibility.
        logger.debug("Circular dependency detection: No MCP server interdependencies in current design")
        pass
    
    def _validate_configuration_completeness(self, config: CombinedConfigModel) -> None:
        """
        Validate that the configuration is complete and makes sense.
        
        Args:
            config: The parsed configuration to validate
            
        Raises:
            ConfigurationError: If configuration is incomplete or inconsistent
        """
        # Check for agents without required fields (should be caught by Pydantic, but double-check)
        for agent_name, agent_config in config.agents.items():
            if not agent_config.mcp_servers:
                raise ConfigurationError(
                    f"Agent '{agent_name}' has no MCP servers configured. "
                    f"Each agent must use at least one MCP server."
                )
        
        # Check for MCP servers without required fields (should be caught by Pydantic, but double-check)
        for server_id, server_config in config.mcp_servers.items():
            if not server_config.transport:
                raise ConfigurationError(
                    f"MCP server '{server_id}' has no transport configured. "
                    f"Each MCP server must have transport configuration."
                )
        
        # Warn about disabled MCP servers that are still referenced
        disabled_servers = {
            server_id for server_id, server_config in config.mcp_servers.items()
            if not server_config.enabled
        }
        
        if disabled_servers:
            for agent_name, agent_config in config.agents.items():
                referenced_disabled = set(agent_config.mcp_servers) & disabled_servers
                if referenced_disabled:
                    logger.warning(
                        f"Agent '{agent_name}' references disabled MCP servers: {referenced_disabled}. "
                        f"This may cause runtime failures when processing alerts."
                    )
        
        logger.debug("Configuration completeness validation passed")
    
    def _format_yaml_error(self, error: yaml.YAMLError) -> str:
        """
        Format YAML parsing errors with helpful context and suggestions.
        
        Args:
            error: The YAML parsing error
            
        Returns:
            Formatted error message with context and suggestions
        """
        base_msg = f"Invalid YAML format in {self.config_file_path}"
        
        if hasattr(error, 'problem_mark') and error.problem_mark:
            line = error.problem_mark.line + 1  # Convert to 1-based line numbers
            column = error.problem_mark.column + 1
            base_msg += f" at line {line}, column {column}"
        
        base_msg += f": {error}"
        
        # Add helpful suggestions based on common YAML errors
        error_str = str(error).lower()
        suggestions = []
        
        if 'mapping values are not allowed here' in error_str:
            suggestions.append("Check for missing colons (:) after dictionary keys")
            suggestions.append("Ensure proper indentation for nested structures")
        elif 'could not find expected' in error_str:
            suggestions.append("Check for unmatched brackets, quotes, or braces")
            suggestions.append("Verify that all opened structures are properly closed")
        elif 'found character that cannot start any token' in error_str:
            suggestions.append("Check for invalid characters or encoding issues")
            suggestions.append("Ensure the file is saved with UTF-8 encoding")
        
        if suggestions:
            base_msg += "\n\nSuggestions:"
            for suggestion in suggestions:
                base_msg += f"\n  - {suggestion}"
        
        base_msg += f"\n\nPlease validate your YAML syntax using an online YAML validator or check the example configuration at config/agents.yaml.example"
        
        return base_msg
    
    def _format_validation_error(self, error: ValidationError) -> str:
        """
        Format Pydantic validation errors with helpful context and suggestions.
        
        Args:
            error: The Pydantic validation error
            
        Returns:
            Formatted error message with context and field-specific guidance
        """
        base_msg = f"Configuration validation failed for {self.config_file_path}"
        error_details = []
        
        for err in error.errors():
            field_path = ' -> '.join(str(x) for x in err['loc']) if err['loc'] else 'root'
            error_type = err['type']
            error_msg = err['msg']
            
            detail = f"Field '{field_path}': {error_msg}"
            
            # Add specific suggestions based on error types
            if error_type == 'missing':
                detail += f" (This field is required)"
            elif error_type == 'too_short':
                detail += f" (Lists must have at least 1 item)"
            elif error_type == 'string_type':
                detail += f" (Expected text/string value)"
            elif error_type == 'bool_parsing':
                detail += f" (Expected true/false boolean value)"
            elif error_type == 'dict_type':
                detail += f" (Expected dictionary/object structure)"
            
            error_details.append(detail)
        
        if error_details:
            base_msg += f"\n\nValidation errors ({len(error_details)} total):"
            for detail in error_details:
                base_msg += f"\n  - {detail}"
        
        base_msg += f"\n\nPlease check the example configuration at config/agents.yaml.example for the correct format."
        
        return base_msg 