"""
Configuration-related exceptions for the Tarsy Bot system.

This module centralizes all configuration-related exceptions to provide
consistent error handling across configuration loading, validation, and parsing.
"""


class ConfigurationError(Exception):
    """
    Raised when configuration loading or validation fails.
    
    This exception is used for all configuration-related errors including:
    - File loading issues (permissions, not found, etc.)
    - YAML parsing errors
    - Pydantic validation failures
    - Configuration conflicts
    - Missing dependencies
    """
    pass
