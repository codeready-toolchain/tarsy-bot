"""
Template resolution utilities for MCP server configurations.

This module provides template variable expansion using environment variables
for MCP server configuration parameters, supporting the ${VARIABLE_NAME} syntax.
"""

import os
import re
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    from tarsy.config.settings import Settings

logger = get_module_logger(__name__)

# Regex pattern for matching ${VARIABLE_NAME} templates
TEMPLATE_PATTERN = re.compile(r'\$\{([A-Z_][A-Z0-9_]*)\}')


class TemplateResolutionError(Exception):
    """Raised when template variable resolution fails."""
    pass


class TemplateResolver:
    """
    Utility class for resolving template variables in MCP server configurations.
    
    Supports ${VARIABLE_NAME} syntax with environment variable expansion.
    Provides comprehensive error handling, validation, and settings-based defaults.
    """
    
    def __init__(self, settings: Optional["Settings"] = None):
        """
        Initialize the template resolver.
        
        Args:
            settings: Optional Settings instance for template variable defaults.
                     If None, only environment variables will be used.
        """
        self.settings = settings
        self._template_cache: Dict[str, str] = {}
        
    def resolve_configuration(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve all template variables in a configuration dictionary.
        
        Args:
            config: Configuration dictionary that may contain template variables
            
        Returns:
            Configuration dictionary with template variables resolved
            
        Raises:
            TemplateResolutionError: If template resolution fails
        """
        logger.debug("Resolving templates in configuration")
        
        try:
            # Always validate all templates first before resolving
            missing_vars = self.validate_templates(config)
            if missing_vars:
                missing_list = ", ".join(missing_vars)
                raise TemplateResolutionError(
                    f"Missing required environment variables for template resolution: {missing_list}. "
                    f"Please set these variables in your .env file or environment."
                )
            
            resolved_config = self._resolve_recursive(config)
            logger.debug("Template resolution completed successfully")
            return resolved_config
        except Exception as e:
            logger.error(f"Template resolution failed: {e}")
            if isinstance(e, TemplateResolutionError):
                raise
            raise TemplateResolutionError(f"Unexpected error during template resolution: {e}") from e
    
    def _resolve_recursive(self, obj: Any) -> Any:
        """
        Recursively resolve templates in nested data structures.
        
        Args:
            obj: Object to resolve templates in (dict, list, string, or other)
            
        Returns:
            Object with templates resolved
        """
        if isinstance(obj, dict):
            return {key: self._resolve_recursive(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_recursive(item) for item in obj]
        elif isinstance(obj, str):
            return self._resolve_string_templates(obj)
        else:
            # Return other types unchanged (int, bool, None, etc.)
            return obj
    
    def _resolve_string_templates(self, text: str) -> str:
        """
        Resolve template variables in a string.
        
        Args:
            text: String that may contain ${VARIABLE_NAME} templates
            
        Returns:
            String with template variables resolved
        """
        if not isinstance(text, str):
            return text
            
        # Find all template variables in the string
        matches = TEMPLATE_PATTERN.findall(text)
        if not matches:
            return text
        
        logger.debug("Found %s template variable(s) in string", len(matches))
        
        resolved_text = text
        
        # Replace all template variables
        for var_name in matches:
            # Check cache first
            if var_name in self._template_cache:
                var_value = self._template_cache[var_name]
            else:
                # Resolve variable value (should always succeed due to pre-validation)
                var_value = self._resolve_variable(var_name)
                self._template_cache[var_name] = var_value
            
            # Replace the template variable
            template_pattern = f"${{{var_name}}}"
            resolved_text = resolved_text.replace(template_pattern, var_value)
        
        logger.debug("Template successfully resolved")
        return resolved_text
    
    def _resolve_variable(self, var_name: str) -> str:
        """
        Resolve a single template variable using environment variables and settings defaults.
        
        Args:
            var_name: Name of the template variable to resolve
            
        Returns:
            Resolved variable value
            
        Raises:
            TemplateResolutionError: If variable cannot be resolved
        """
        # 1. Try environment variable first
        env_value = os.getenv(var_name)
        if env_value is not None:
            logger.debug(f"Resolved template variable {var_name} from environment")
            return env_value
        
        # 2. Try settings default if available
        if self.settings:
            default_value = self.settings.get_template_default(var_name)
            if default_value is not None:
                logger.info(f"Using default value for template variable {var_name}: {default_value}")
                return default_value
        
        # 3. Variable not found - this should not happen due to pre-validation
        raise TemplateResolutionError(f"Template variable {var_name} not found and no default available")
    
    def validate_templates(self, config: Dict[str, Any]) -> List[str]:
        """
        Validate that all template variables in a configuration can be resolved.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            List of missing environment variable names (empty if all can be resolved)
        """
        missing_vars = set()
        self._collect_missing_variables(config, missing_vars)
        return sorted(list(missing_vars))
    
    def _collect_missing_variables(self, obj: Any, missing_vars: Set[str]) -> None:
        """
        Recursively collect missing template variables from nested structures.
        
        Args:
            obj: Object to check for missing variables
            missing_vars: Set to collect missing variable names
        """
        if isinstance(obj, dict):
            for value in obj.values():
                self._collect_missing_variables(value, missing_vars)
        elif isinstance(obj, list):
            for item in obj:
                self._collect_missing_variables(item, missing_vars)
        elif isinstance(obj, str):
            matches = TEMPLATE_PATTERN.findall(obj)
            for var_name in matches:
                if not self._can_resolve_variable(var_name):
                    missing_vars.add(var_name)
    
    def _can_resolve_variable(self, var_name: str) -> bool:
        """
        Check if a template variable can be resolved (either from env or settings default).
        
        Args:
            var_name: Name of the template variable
            
        Returns:
            True if variable can be resolved, False otherwise
        """
        # Check environment variable
        if os.getenv(var_name) is not None:
            return True
        
        # Check settings default
        if self.settings and self.settings.get_template_default(var_name) is not None:
            return True
        
        return False
    
    def get_template_variables(self, config: Dict[str, Any]) -> List[str]:
        """
        Extract all template variable names from a configuration.
        
        Args:
            config: Configuration dictionary to analyze
            
        Returns:
            List of unique template variable names found
        """
        template_vars = set()
        self._collect_template_variables(config, template_vars)
        return sorted(list(template_vars))
    
    def _collect_template_variables(self, obj: Any, template_vars: Set[str]) -> None:
        """
        Recursively collect template variable names from nested structures.
        
        Args:
            obj: Object to extract variable names from
            template_vars: Set to collect variable names
        """
        if isinstance(obj, dict):
            for value in obj.values():
                self._collect_template_variables(value, template_vars)
        elif isinstance(obj, list):
            for item in obj:
                self._collect_template_variables(item, template_vars)
        elif isinstance(obj, str):
            matches = TEMPLATE_PATTERN.findall(obj)
            template_vars.update(matches)


# Convenience functions for common use cases
def resolve_mcp_server_config(server_config: Dict[str, Any], settings: Optional["Settings"] = None) -> Dict[str, Any]:
    """
    Convenience function to resolve templates in a single MCP server configuration.
    
    Args:
        server_config: MCP server configuration dictionary
        settings: Optional Settings instance for template variable defaults
        
    Returns:
        Configuration dictionary with templates resolved
        
    Raises:
        TemplateResolutionError: If template resolution fails
    """
    resolver = TemplateResolver(settings=settings)
    return resolver.resolve_configuration(server_config)


def validate_mcp_server_templates(server_config: Dict[str, Any], settings: Optional["Settings"] = None) -> List[str]:
    """
    Convenience function to validate templates in a single MCP server configuration.
    
    Args:
        server_config: MCP server configuration dictionary
        settings: Optional Settings instance for template variable defaults
        
    Returns:
        List of missing environment variable names
    """
    resolver = TemplateResolver(settings=settings)
    return resolver.validate_templates(server_config)