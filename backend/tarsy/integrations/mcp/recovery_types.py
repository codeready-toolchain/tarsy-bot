"""Type definitions for MCP recovery logic.

This module defines the core types used by the MCP client's recovery system
to classify failures and determine appropriate retry/recovery actions.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RecoveryAction(str, Enum):
    """Actions to take when an MCP operation fails.
    
    Attributes:
        RETRY_WITH_NEW_SESSION: Recreate the MCP session and retry the operation
        RETRY_SAME_SESSION: Retry the operation with the existing session
        NO_RETRY: Do not retry; surface the error to the caller
    """

    RETRY_WITH_NEW_SESSION = "retry_with_new_session"
    RETRY_SAME_SESSION = "retry_same_session"
    NO_RETRY = "no_retry"


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    """Decision about how to handle an MCP operation failure.
    
    Attributes:
        action: The recovery action to take
        reason: Human-readable reason for this decision (for logging)
        http_status: HTTP status code if applicable (for HTTP-based transports)
    """

    action: RecoveryAction
    reason: str
    http_status: Optional[int] = None

