"""
Models for pause metadata.

Provides type-safe structures for tracking why and when a session paused.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class PauseReason(Enum):
    """Reason why a session was paused."""
    
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    # Future extensibility:
    # MANUAL_PAUSE = "manual_pause"
    # TIMEOUT = "timeout"
    
    @classmethod
    def values(cls) -> list[str]:
        """All pause reason values as strings."""
        return [reason.value for reason in cls]


class PauseMetadata(BaseModel):
    """
    Metadata about why and when a session paused.
    
    Used to communicate pause context to users and for audit trail.
    """
    
    reason: PauseReason = Field(
        description="Why the session paused"
    )
    
    current_iteration: Optional[int] = Field(
        default=None,
        description="Iteration count when paused (for MAX_ITERATIONS_REACHED)"
    )
    
    message: str = Field(
        description="User-friendly message explaining the pause"
    )
    
    paused_at_us: int = Field(
        description="Timestamp when session paused (microseconds since epoch)"
    )

