"""
History data models for alert processing audit trail.

Defines SQLModel classes for storing alert processing sessions,
LLM interactions, and MCP communications with Unix timestamp
precision for optimal performance and consistency.
"""

import uuid
from typing import Optional

from sqlmodel import JSON, Column, Field, Relationship, SQLModel, Index
from sqlalchemy import text

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
    
    # JSON indexes for efficient querying of flexible alert data
    __table_args__ = (
        Index('ix_alert_data_gin', 'alert_data', postgresql_using='gin'),
        Index('ix_alert_data_severity', text("((alert_data->>'severity'))")),
        Index('ix_alert_data_environment', text("((alert_data->>'environment'))")),
        Index('ix_alert_data_cluster', text("((alert_data->>'cluster'))")),
    )
    
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
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
        description=f"Current processing status ({', '.join(AlertSessionStatus.ALL_STATUSES)})"
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
    
    # Note: Relationships removed to avoid circular import issues with unified models
    # Use queries with session_id foreign key for data access instead
    
# Import unified models that replace the old separate DB models
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction 