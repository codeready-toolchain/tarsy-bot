"""
Database models for alert processing audit trail.

Defines SQLModel table classes for storing alert processing sessions
and stage executions with Unix timestamp precision for optimal 
performance and consistency.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from sqlmodel import Column, Field, SQLModel, Index
from sqlalchemy import JSON, Integer, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import BIGINT

from tarsy.models.constants import AlertSessionStatus
from tarsy.utils.timestamp import now_us

if TYPE_CHECKING:
    from tarsy.models.agent_config import ChainConfigModel

class AlertSession(SQLModel, table=True):
    """
    Represents an alert processing session with complete lifecycle tracking.
    
    Captures the full context of alert processing from initiation to completion,
    including session metadata, processing status, and timing information.
    Uses Unix timestamps (microseconds since epoch) for optimal performance and precision.
    """
    
    __tablename__ = "alert_sessions"
    
    # Database-agnostic indexes for common query patterns
    __table_args__ = (
        # Individual column indexes for filtering
        Index('ix_alert_sessions_status', 'status'),
        Index('ix_alert_sessions_agent_type', 'agent_type'), 
        Index('ix_alert_sessions_alert_type', 'alert_type'),
        
        # Composite index for most common query pattern: filter by status + order by timestamp
        Index('ix_alert_sessions_status_started_at', 'status', 'started_at_us'),
        
        # Composite index for efficient orphan detection
        Index('ix_alert_sessions_status_last_interaction', 'status', 'last_interaction_at'),
        
        # Note: PostgreSQL-specific JSON indexes removed for database compatibility
        # In production with PostgreSQL, consider adding:
        # - GIN index on alert_data: Index('ix_alert_data_gin', 'alert_data', postgresql_using='gin')
        # - JSON field indexes: Index('ix_alert_data_severity', text("((alert_data->>'severity'))"))
    )
    
    session_id: str = Field(
        ...,  # Required field - must be set from ChainContext.session_id
        primary_key=True,
        description="Unique identifier for the alert processing session"
    )
    
    alert_data: dict = Field(
        default_factory=dict,
        sa_column=Column[Any](JSON),
        description="Original alert payload and context data"
    )
    
    agent_type: str = Field(
        description="Type of processing agent (e.g., 'kubernetes', 'base')"
    )
    
    alert_type: Optional[str] = Field(
        default=None,
        description="Alert type for efficient filtering (e.g., 'NamespaceTerminating', 'UnidledPods', 'OutOfSyncApplication')"
    )
    
    status: str = Field(
        description=f"Current processing status ({', '.join(AlertSessionStatus.values())})"
    )
    
    started_at_us: int = Field(
        default_factory=now_us,
        sa_column=Column[Any](BIGINT, index=True),
        description="Session start timestamp (microseconds since epoch UTC)"
    )
    
    completed_at_us: Optional[int] = Field(
        default=None,
        sa_column=Column(BIGINT),
        description="Session completion timestamp (microseconds since epoch UTC)"
    )
    
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if processing failed"
    )
    
    final_analysis: Optional[str] = Field(
        default=None,
        description="Final formatted analysis result if processing completed successfully"
    )
    
    session_metadata: Optional[dict] = Field(
        default=None,
        sa_column=Column[Any](JSON),
        description="Additional context and metadata for the session"
    )
    
    author: Optional[str] = Field(
        default=None,
        max_length=255,
        description="User or API Client who submitted the alert (from oauth2-proxy X-Forwarded-User header)"
    )
    
    runbook_url: Optional[str] = Field(
        default=None,
        description="Runbook URL used for processing this alert (if provided)"
    )
    
    mcp_selection: Optional[dict] = Field(
        default=None,
        sa_column=Column[Any](JSON),
        description="MCP server/tool selection override (if provided)"
    )
    
    # Chain execution tracking
    chain_id: str = Field(description="Chain identifier for this execution")
    chain_definition: Optional[dict] = Field(default=None, sa_column=Column(JSON), description="Complete chain definition snapshot")
    current_stage_index: Optional[int] = Field(default=None, description="Current stage position (0-based)")
    current_stage_id: Optional[str] = Field(default=None, description="Current stage identifier")
    
    # Pod tracking for multi-replica support
    pod_id: Optional[str] = Field(
        default=None,
        description="Kubernetes pod identifier for multi-replica session tracking"
    )
    
    last_interaction_at: Optional[int] = Field(
        default=None,
        sa_column=Column[Any](BIGINT),
        description="Last interaction timestamp (microseconds) for orphan detection"
    )
    
    # Note: Relationships removed to avoid circular import issues with unified models
    # Use queries with session_id foreign key for data access instead
    
    @property
    def chain_config(self) -> Optional['ChainConfigModel']:
        """
        Parse chain_definition dict to typed ChainConfigModel.
        
        Provides type-safe access to chain configuration with IDE autocomplete
        and Pydantic validation. Returns None if chain_definition is not set.
        
        Returns:
            ChainConfigModel instance or None
        """
        if not self.chain_definition:
            return None
        from tarsy.models.agent_config import ChainConfigModel
        return ChainConfigModel(**self.chain_definition)


class StageExecution(SQLModel, table=True):
    """
    Represents the execution of a single stage within a chain processing session.
    
    Tracks detailed execution information for each chain stage including timing,
    status, outputs, and error information with Unix timestamp precision.
    """
    
    __tablename__ = "stage_executions"
    
    execution_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Unique identifier for this stage execution"
    )
    
    session_id: str = Field(
        sa_column=Column[Any](String, ForeignKey("alert_sessions.session_id", ondelete="CASCADE"), index=True),
        description="Reference to the parent alert session"
    )
    
    # Stage identification
    stage_id: str = Field(description="Stage identifier (e.g., 'initial-analysis')")
    stage_index: int = Field(description="Stage position in chain (0-based)", index=True)
    stage_name: str = Field(description="Human-readable stage name from configuration")
    agent: str = Field(description="Agent used for this stage")
    
    # Execution tracking
    status: str = Field(description="Stage execution status (pending|active|completed|failed)")
    started_at_us: Optional[int] = Field(default=None, sa_column=Column(BIGINT), description="Stage start timestamp")
    completed_at_us: Optional[int] = Field(default=None, sa_column=Column(BIGINT), description="Stage completion timestamp")
    duration_ms: Optional[int] = Field(default=None, description="Stage execution duration")
    stage_output: Optional[dict] = Field(
        default=None, 
        sa_column=Column[Any](JSON), 
        description="Data produced by stage (only for successful completion)"
    )
    error_message: Optional[str] = Field(
        default=None, 
        description="Error message if stage failed (mutually exclusive with stage_output)"
    )
    current_iteration: Optional[int] = Field(
        default=None,
        description="Current iteration number when paused (for pause/resume)"
    )
    
    # Chat context tracking
    chat_id: Optional[str] = Field(
        default=None,
        description="Chat ID if this execution is a chat response"
    )
    chat_user_message_id: Optional[str] = Field(
        default=None,
        description="User message ID this execution is responding to"
    )
    
    # Note: Relationship to AlertSession would be: session: AlertSession = Relationship(back_populates="stage_executions")
    # Omitted to avoid circular imports - use session_id for queries instead


class Event(SQLModel, table=True):
    """
    Event persistence for cross-pod event distribution and catchup.

    Stores events for PostgreSQL LISTEN/NOTIFY system with SQLite polling fallback.
    Enables reliable event delivery across multiple backend pods and client reconnection
    with catchup support.
    """

    __tablename__ = "events"

    __table_args__ = (
        # Index for cleanup performance (time-based queries)
        Index("idx_events_created_at", "created_at"),
        # Composite index for polling queries (SQLite dev mode)
        Index("idx_events_channel_id", "channel", "id"),
    )

    id: Optional[int] = Field(
        default=None,
        sa_column=Column[Any](Integer, primary_key=True, autoincrement=True),
        description="Auto-incrementing event ID for ordering and catchup",
    )

    channel: str = Field(
        max_length=100,
        index=True,
        description="Event channel (e.g., 'sessions', 'session:abc-123')",
    )

    payload: dict = Field(
        sa_column=Column[Any](JSON),
        description="Event data as JSON (type, data, timestamp, id)",
    )

    created_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column[Any](DateTime, nullable=False, server_default=func.now()),
        description="Event creation timestamp (for cleanup and ordering)",
    )


class Chat(SQLModel, table=True):
    """Chat metadata and context snapshot from terminated session."""
    
    __tablename__ = "chats"
    
    __table_args__ = (
        Index('ix_chats_session_id', 'session_id'),
        Index('ix_chats_created_at', 'created_at_us'),
        Index('ix_chats_pod_last_interaction', 'pod_id', 'last_interaction_at'),
    )
    
    chat_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Unique chat identifier"
    )
    
    session_id: str = Field(
        sa_column=Column[Any](String, ForeignKey("alert_sessions.session_id")),
        description="Original session this chat extends"
    )
    
    created_at_us: int = Field(
        default_factory=now_us,
        sa_column=Column[Any](BIGINT),
        description="Chat creation timestamp"
    )
    
    created_by: Optional[str] = Field(
        default=None,
        description="User who initiated the chat"
    )
    
    conversation_history: str = Field(
        description="Formatted session investigation text"
    )
    
    chain_id: str = Field(
        description="Chain ID from original session"
    )
    
    mcp_selection: Optional[dict] = Field(
        default=None,
        sa_column=Column[Any](JSON),
        description="MCP server/tool selection used in original session"
    )
    
    context_captured_at_us: int = Field(
        sa_column=Column[Any](BIGINT),
        description="Timestamp when context was captured from session"
    )
    
    pod_id: Optional[str] = Field(
        default=None,
        description="Kubernetes pod identifier for multi-replica chat message tracking"
    )
    
    last_interaction_at: Optional[int] = Field(
        default=None,
        sa_column=Column[Any](BIGINT),
        description="Last interaction timestamp for orphan detection during chat message processing"
    )


class ChatUserMessage(SQLModel, table=True):
    """User questions in a chat conversation."""
    
    __tablename__ = "chat_user_messages"
    
    __table_args__ = (
        Index('ix_chat_user_messages_chat_id', 'chat_id'),
        Index('ix_chat_user_messages_created_at', 'created_at_us'),
    )
    
    message_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Unique message identifier"
    )
    
    chat_id: str = Field(
        sa_column=Column[Any](String, ForeignKey("chats.chat_id", ondelete="CASCADE")),
        description="Parent chat"
    )
    
    content: str = Field(
        description="User's question text"
    )
    
    author: str = Field(
        description="User email/ID who sent the message"
    )
    
    created_at_us: int = Field(
        default_factory=now_us,
        sa_column=Column[Any](BIGINT),
        description="Message creation timestamp"
    )


# Import unified models that replace the old separate DB models
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction 