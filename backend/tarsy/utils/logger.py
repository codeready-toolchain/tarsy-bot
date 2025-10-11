"""
Logging configuration and utilities for tarsy.
"""

import logging
import sys


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure logging to stdout/stderr only.
    
    Args:
        log_level: The log level to use (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        
    Raises:
        ValueError: If log_level is not a valid logging level name
    """
    # Validate and convert log level to numeric value
    log_level_upper = log_level.upper()
    if log_level_upper not in logging._nameToLevel:
        raise ValueError(f"Invalid log level: {log_level}")
    
    numeric_level = logging._nameToLevel[log_level_upper]
    
    # Root logger configuration
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.StreamHandler(sys.stdout)  # stdout/stderr only
        ],
        force=True  # Override any existing configuration
    )
    
    # Set levels for specific loggers to match root level
    logging.getLogger('tarsy').setLevel(numeric_level)
    logging.getLogger('uvicorn').setLevel(logging.INFO)
    
    # Remove any file handlers if present (cleanup from previous configuration)
    for handler in logging.root.handlers[:]:
        if isinstance(handler, logging.FileHandler):
            logging.root.removeHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Args:
        name: The name of the logger, typically the module name
        
    Returns:
        logging.Logger: Configured logger instance
    """
    # Ensure the name starts with our application prefix
    if not name.startswith("tarsy"):
        name = f"tarsy.{name}"
    
    return logging.getLogger(name)


def get_module_logger(module_name: str) -> logging.Logger:
    """
    Get a logger for a specific module.
    
    Args:
        module_name: The module name (e.g., __name__)
        
    Returns:
        logging.Logger: Configured logger instance
    """
    if module_name.startswith("tarsy."):
        module_name = module_name[6:]  # Remove 'tarsy.' prefix (6 characters)
    
    return get_logger(module_name) 