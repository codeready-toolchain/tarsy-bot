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
    
    # Relationships for chronological timeline reconstruction
    llm_interactions: list["LLMInteraction"] = Relationship(
        back_populates="session",
        sa_relationship_kwargs={"lazy": "select", "cascade": "all, delete-orphan"}
    )
    
    mcp_communications: list["MCPCommunication"] = Relationship(
        back_populates="session", 
        sa_relationship_kwargs={"lazy": "select", "cascade": "all, delete-orphan"}
    )
    
class LLMInteraction(SQLModel, table=True):
    """Database model for LLM interactions."""
    
    __tablename__ = "llm_interactions"
    
    # Database-specific fields
    interaction_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Unique identifier for the LLM interaction"
    )
    
    step_description: str = Field(
        description="Human-readable description of this processing step"
    )
    
    # Base interaction fields
    request_id: str = Field(description="Request identifier")
    session_id: str = Field(
        foreign_key="alert_sessions.session_id",
        description="Foreign key reference to the parent alert session"
    )
    timestamp_us: int = Field(
        default_factory=now_us,
        description="Interaction timestamp (microseconds since epoch UTC)",
        index=True
    )
    duration_ms: int = Field(default=0, description="Interaction duration in milliseconds")
    success: bool = Field(default=True, description="Whether interaction succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    # LLM-specific fields
    model_name: str = Field(description="LLM model identifier")
    request_json: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Full JSON request sent to LLM API"
    )
    response_json: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Full JSON response received from LLM API"
    )
    token_usage: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Token usage statistics"
    )
    tool_calls: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Tool calls made during interaction"
    )
    tool_results: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Results from tool calls"
    )
    
    # Relationship back to session
    session: AlertSession = Relationship(back_populates="llm_interactions")


class MCPCommunication(SQLModel, table=True):
    """Database model for MCP communications."""
    
    __tablename__ = "mcp_communications"
    
    # Database-specific fields
    communication_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Unique identifier for the MCP communication"
    )
    
    step_description: str = Field(
        description="Human-readable description of this step"
    )
    
    # Base interaction fields
    request_id: str = Field(description="Request identifier")
    session_id: str = Field(
        foreign_key="alert_sessions.session_id",
        description="Foreign key reference to the parent alert session"
    )
    timestamp_us: int = Field(
        default_factory=now_us,
        description="Communication timestamp (microseconds since epoch UTC)",
        index=True
    )
    duration_ms: int = Field(default=0, description="Communication duration in milliseconds")
    success: bool = Field(default=True, description="Whether communication succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    
    # MCP-specific fields
    server_name: str = Field(description="MCP server identifier")
    communication_type: str = Field(description="Type of communication (tool_list, tool_call)")
    tool_name: Optional[str] = Field(None, description="Tool name (for tool_call type)")
    tool_arguments: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Tool arguments (for tool_call type)"
    )
    tool_result: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Tool result (for tool_call type)"
    )
    available_tools: Optional[dict] = Field(
        default=None,
        sa_column=Column(JSON),
        description="Available tools (for tool_list type)"
    )
    
    # Relationship back to session
    session: AlertSession = Relationship(back_populates="mcp_communications") 