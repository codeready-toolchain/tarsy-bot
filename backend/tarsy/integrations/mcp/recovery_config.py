"""Configuration constants for MCP recovery and retry logic.

This module centralizes all configuration values related to MCP operation
timeouts, retry behavior, and HTTP status code classification.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MCPRecoveryConfig:
    """Configuration for MCP recovery behavior.
    
    Attributes:
        RETRY_LIMIT: Maximum number of retry attempts per operation (default: 1)
        REINIT_TIMEOUT_SECONDS: Timeout for session reinitialization in seconds (default: 10.0)
        OPERATION_TIMEOUT_SECONDS: Timeout for individual MCP operations in seconds (default: 60)
        RETRY_BACKOFF_MIN: Minimum backoff delay for rate-limited retries in seconds (default: 0.25)
        RETRY_BACKOFF_MAX: Maximum backoff delay for rate-limited retries in seconds (default: 0.75)
    """

    RETRY_LIMIT: int = 1
    REINIT_TIMEOUT_SECONDS: float = 10.0
    OPERATION_TIMEOUT_SECONDS: int = 60
    RETRY_BACKOFF_MIN: float = 0.25
    RETRY_BACKOFF_MAX: float = 0.75


# Default singleton instance used throughout the application
DEFAULT_RECOVERY_CONFIG = MCPRecoveryConfig()


# HTTP Status Code Classifications
# These sets define how different HTTP status codes are handled during recovery

# HTTP 404: Session not found - recreate the session
HTTP_STATUS_SESSION_LOST = frozenset({404})

# HTTP 502, 503, 504: Gateway/upstream errors - recreate session and retry
HTTP_STATUS_UPSTREAM_ERROR = frozenset({502, 503, 504})

# HTTP 429: Rate limited - retry with same session after backoff
HTTP_STATUS_RATE_LIMITED = frozenset({429})

# HTTP 401, 403: Authentication/authorization errors - do not retry
HTTP_STATUS_AUTH_ERROR = frozenset({401, 403})

