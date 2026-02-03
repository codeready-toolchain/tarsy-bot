"""
API Models for Request/Response Serialization

Defines Pydantic models for API request/response structures.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, computed_field

from tarsy.models.constants import ChainStatus, ScoringStatus
from tarsy.agents.prompts.judges import CURRENT_PROMPT_HASH

# Non-history related response models


class HealthCheckResponse(BaseModel):
    """Response for health check endpoints."""

    service: str = Field(description="Service name")
    status: str = Field(
        description="Service status ('healthy', 'unhealthy', 'disabled')"
    )
    timestamp_us: int = Field(
        description="Health check timestamp (microseconds since epoch UTC)"
    )
    details: Dict[str, Any] = Field(description="Additional health check details")


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: str = Field(description="Error type or category")
    message: str = Field(description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(description="Additional error details")
    timestamp_us: int = Field(
        description="When the error occurred (microseconds since epoch UTC)"
    )


class ChainExecutionResult(BaseModel):
    """
    Result from chain execution.

    This model represents the result of executing a chain of agent stages,
    containing both success and failure information.
    """

    # Core execution metadata - always present
    status: ChainStatus = Field(description="Overall execution status")
    timestamp_us: int = Field(
        description="Execution completion timestamp (microseconds since epoch UTC)"
    )

    # Success case fields - present when status is completed or partial
    final_analysis: Optional[str] = Field(
        None, description="Final analysis result from the chain"
    )

    # Error case fields - present when status is failed
    error: Optional[str] = Field(None, description="Error message when execution fails")


# ===== Chat API Models =====


class ChatResponse(BaseModel):
    """Response for chat creation endpoint."""

    chat_id: str = Field(description="Unique chat identifier")
    session_id: str = Field(description="Original session ID")
    created_at_us: int = Field(
        description="Chat creation timestamp (microseconds since epoch UTC)"
    )
    created_by: str = Field(description="User who initiated the chat")
    message_count: int = Field(default=0, description="Number of messages in chat")


class ChatAvailabilityResponse(BaseModel):
    """Response for chat availability check endpoint."""

    available: bool = Field(description="Whether chat is available for this session")
    reason: Optional[str] = Field(default=None, description="Reason if unavailable")
    chat_id: Optional[str] = Field(
        default=None, description="Existing chat ID if already created"
    )


class ChatMessageRequest(BaseModel):
    """Request body for sending chat message."""

    content: str = Field(
        ...,
        min_length=1,
        max_length=100000,
        description="User's question or follow-up message",
    )

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Ensure content is not just whitespace."""
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty or whitespace only")
        return v.strip()


class ChatMessageResponse(BaseModel):
    """Response for message creation endpoint."""

    message_id: str = Field(description="Unique message identifier")
    chat_id: str = Field(description="Parent chat ID")
    content: str = Field(description="Message content")
    author: str = Field(description="Message author")
    created_at_us: int = Field(
        description="Message timestamp (microseconds since epoch UTC)"
    )
    stage_execution_id: Optional[str] = Field(
        default=None,
        description="Stage execution ID for AI response (streams via WebSocket)",
    )


class ChatUserMessageListResponse(BaseModel):
    """Response for chat message history endpoint."""

    messages: List[ChatMessageResponse] = Field(description="List of user messages")
    total_count: int = Field(description="Total message count")
    chat_id: str = Field(description="Chat identifier")


# ===== Scoring API Models =====


class SessionScoreResponse(BaseModel):
    """
    Session scoring result for API responses.

    Includes computed field to indicate if score uses current prompt template.
    """

    score_id: str = Field(description="Unique scoring attempt identifier")
    session_id: str = Field(description="Alert session that was scored")
    prompt_hash: str = Field(description="Hash of prompt template used for scoring")
    total_score: Optional[int] = Field(
        None, ge=0, le=100, description="Total score (0-100), None if not yet completed"
    )
    score_analysis: Optional[str] = Field(None, description="Detailed scoring analysis")
    missing_tools_analysis: Optional[str] = Field(
        None, description="Missing tools analysis"
    )
    score_triggered_by: str = Field(description="Who/what triggered the scoring")
    scored_at_us: int = Field(
        description="When scoring was initiated (microseconds since epoch)"
    )

    # Async status fields
    status: ScoringStatus = Field(
        description="Scoring status (pending|in_progress|completed|failed|timed_out)"
    )
    started_at_us: int = Field(
        description="Processing start time (microseconds since epoch)"
    )
    completed_at_us: Optional[int] = Field(
        None, description="Processing end time (microseconds since epoch)"
    )
    error_message: Optional[str] = Field(None, description="Error details if failed")

    @computed_field  # type: ignore[misc]
    @property
    def current_prompt_used(self) -> bool:
        """
        Whether this score uses the current prompt template.

        Compares the stored prompt_hash with the current hash computed from
        the judge prompts in judges.py. If they match, the score is current.
        If they differ, the score was produced with obsolete criteria.

        Returns:
            True if prompt_hash matches current hash, False otherwise
        """
        return self.prompt_hash == CURRENT_PROMPT_HASH


class SessionScoreRequest(BaseModel):
    """
    Request body for session scoring endpoint.

    Controls whether to force re-scoring even if a score already exists.
    """

    force_rescore: bool = Field(
        default=False,
        description="If true, re-score even if score already exists. Returns 409 if scoring is in progress.",
    )


# ===== Session Control API Models =====


class CancelAgentResponse(BaseModel):
    """Response for individual parallel agent cancellation endpoint."""

    success: bool = Field(description="Whether the cancellation was successful")
    session_status: str = Field(description="Updated session status after cancellation")
    stage_status: str = Field(
        description="Updated parent stage status after re-evaluation"
    )
