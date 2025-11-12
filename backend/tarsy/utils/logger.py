"""
Logging configuration and utilities for tarsy.
"""

import logging
import sys


class HealthEndpointFilter(logging.Filter):
    """
    Filter to suppress logging of successful health and monitoring endpoint requests.
    
    This filter prevents frequently-polled monitoring endpoints from cluttering logs:
    - /health - Kubernetes health probes
    - /api/v1/system/warnings - Dashboard warning polling
    
    Only logs requests that have errors or return non-200 status codes.
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter out successful monitoring endpoint requests.
        
        Args:
            record: Log record to filter
            
        Returns:
            False to suppress the log record, True to allow it through
        """
        # Check if this is an access log record from uvicorn
        if hasattr(record, 'args') and record.args:
            # uvicorn access log format: (client, method, path, http_version, status_code)
            # Example: ('127.0.0.1:12345', 'GET', '/health', 'HTTP/1.1', 200)
            try:
                # Get the request details
                if len(record.args) >= 5:
                    method = record.args[1] if len(record.args) > 1 else ""
                    path = record.args[2] if len(record.args) > 2 else ""
                    status_code = record.args[4] if len(record.args) > 4 else 0
                    
                    # Filter out successful monitoring endpoint requests (status 200)
                    # Still log errors (4xx, 5xx) and warnings (3xx)
                    if method == "GET" and path in ("/health", "/api/v1/system/warnings"):
                        # Only suppress successful requests (200-299)
                        if isinstance(status_code, int) and 200 <= status_code < 300:
                            return False  # Suppress this log
            except (IndexError, TypeError, AttributeError):
                # If we can't parse the log record, let it through
                pass
        
        return True  # Allow all other logs


class ConnectionClosedFilter(logging.Filter):
    """
    Filter to suppress routine WebSocket connection closed messages.
    
    This filter prevents normal WebSocket disconnections from cluttering logs
    since we already log disconnections at DEBUG level in our own code.
    """
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter out routine "connection closed" messages.
        
        Args:
            record: Log record to filter
            
        Returns:
            False to suppress the log record, True to allow it through
        """
        # Suppress "connection closed" info messages (routine disconnections)
        if record.levelno == logging.INFO and record.getMessage() == "connection closed":
            return False
        
        return True


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
    
    # Suppress verbose httpx logging (only show warnings and errors)
    # httpx logs every HTTP request at INFO level by default, which clutters logs
    logging.getLogger('httpx').setLevel(logging.WARNING)
    
    # Suppress SQLAlchemy engine logging (only show warnings and errors)
    # This prevents SQL statements (especially NOTIFY with large payloads) from cluttering logs
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    
    # Add filter to uvicorn.access logger to suppress monitoring endpoint noise
    # This prevents frequently-polled endpoints (health checks, warnings) from cluttering logs
    uvicorn_access_logger = logging.getLogger('uvicorn.access')
    uvicorn_access_logger.addFilter(HealthEndpointFilter())
    
    # Add filter to uvicorn.error logger to suppress routine WebSocket disconnections
    # This prevents "connection closed" messages from cluttering logs
    uvicorn_error_logger = logging.getLogger('uvicorn.error')
    uvicorn_error_logger.addFilter(ConnectionClosedFilter())
    
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