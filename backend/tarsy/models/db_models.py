"""
Database models for alert processing audit trail.

Defines SQLModel table classes for storing alert processing sessions
and stage executions with Unix timestamp precision for optimal 
performance and consistency.
"""

import uuid
from typing import Optional

from sqlmodel import Column, Field, SQLModel, Index
from sqlalchemy import JSON

from tarsy.models.constants import AlertSessionStatus
from tarsy.utils.timestamp import now_us

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
    
    alert_id: str = Field(
        unique=True,
        index=True,
        description="External alert identifier from the alert system"
    )
    
    alert_data: dict = Field(
        default_factory=dict,
        sa_column=Column(JSON),
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
        description="Session start timestamp (microseconds since epoch UTC)",
        index=True
    )
    
    completed_at_us: Optional[int] = Field(
        default=None,
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
        sa_column=Column(JSON),
        description="Additional context and metadata for the session"
    )
    
    # NEW: Chain execution tracking
    chain_id: str = Field(description="Chain identifier for this execution")
    chain_definition: Optional[dict] = Field(default=None, sa_column=Column(JSON), description="Complete chain definition snapshot")
    current_stage_index: Optional[int] = Field(default=None, description="Current stage position (0-based)")
    current_stage_id: Optional[str] = Field(default=None, description="Current stage identifier")
    
    # Note: Relationships removed to avoid circular import issues with unified models
    # Use queries with session_id foreign key for data access instead


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
        foreign_key="alert_sessions.session_id",
        index=True,
        description="Reference to the parent alert session"
    )
    
    # Stage identification
    stage_id: str = Field(description="Stage identifier (e.g., 'initial-analysis')")
    stage_index: int = Field(description="Stage position in chain (0-based)", index=True)
    stage_name: str = Field(description="Human-readable stage name from configuration")
    agent: str = Field(description="Agent used for this stage")
    
    # Execution tracking
    status: str = Field(description="Stage execution status (pending|active|completed|failed)")
    started_at_us: Optional[int] = Field(default=None, description="Stage start timestamp")
    completed_at_us: Optional[int] = Field(default=None, description="Stage completion timestamp")
    duration_ms: Optional[int] = Field(default=None, description="Stage execution duration")
    stage_output: Optional[dict] = Field(
        default=None, 
        sa_column=Column(JSON), 
        description="Data produced by stage (only for successful completion)"
    )
    error_message: Optional[str] = Field(
        default=None, 
        description="Error message if stage failed (mutually exclusive with stage_output)"
    )
    
    # Note: Relationship to AlertSession would be: session: AlertSession = Relationship(back_populates="stage_executions")
    # Omitted to avoid circular imports - use session_id for queries instead
    

# Import unified models that replace the old separate DB models
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction 