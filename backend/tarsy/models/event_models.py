"""
Event models for type-safe event publishing.

Events are lightweight notification triggers that inform clients about changes.
Clients use these events to determine when to refresh data via REST API.
"""

import time
from typing import Literal, Optional

from pydantic import BaseModel, Field


class BaseEvent(BaseModel):
    """Base class for all events with common fields."""

    type: str = Field(description="Event type identifier")
    timestamp_us: int = Field(
        default_factory=lambda: int(time.time() * 1_000_000),
        description="Event timestamp (microseconds since epoch UTC)",
    )


# ===== Global Session Lifecycle Events (channel: 'sessions') =====


class SessionCreatedEvent(BaseEvent):
    """Session created - new alert processing session initiated."""

    type: Literal["session.created"] = "session.created"
    session_id: str = Field(description="Session identifier")
    alert_type: str = Field(description="Type of alert being processed")


class SessionStartedEvent(BaseEvent):
    """Session started - processing began."""

    type: Literal["session.started"] = "session.started"
    session_id: str = Field(description="Session identifier")
    alert_type: str = Field(description="Type of alert being processed")


class SessionCompletedEvent(BaseEvent):
    """Session completed successfully."""

    type: Literal["session.completed"] = "session.completed"
    session_id: str = Field(description="Session identifier")
    status: Literal["completed"] = "completed"  # For instant client update


class SessionFailedEvent(BaseEvent):
    """Session failed with error."""

    type: Literal["session.failed"] = "session.failed"
    session_id: str = Field(description="Session identifier")
    status: Literal["failed"] = "failed"  # For instant client update


# ===== Per-Session Detail Events (channel: 'session:{session_id}') =====


class LLMInteractionEvent(BaseEvent):
    """LLM interaction occurred during processing."""

    type: Literal["llm.interaction"] = "llm.interaction"
    session_id: str = Field(description="Session identifier")
    interaction_id: str = Field(description="Interaction identifier for deduplication")
    stage_id: Optional[str] = Field(
        default=None, description="Stage execution identifier"
    )


class MCPToolCallStartedEvent(BaseEvent):
    """MCP tool call started - before execution."""

    type: Literal["mcp.tool_call.started"] = "mcp.tool_call.started"
    session_id: str = Field(description="Session identifier")
    communication_id: str = Field(
        description="Communication ID (primary key) for deduplication with DB"
    )
    stage_id: Optional[str] = Field(
        default=None, description="Stage execution identifier"
    )
    server_name: str = Field(description="MCP server name")
    tool_name: str = Field(description="Tool name")
    tool_arguments: dict = Field(description="Tool arguments")


class MCPToolCallEvent(BaseEvent):
    """MCP tool was called during processing."""

    type: Literal["mcp.tool_call"] = "mcp.tool_call"
    session_id: str = Field(description="Session identifier")
    interaction_id: str = Field(description="Interaction identifier for deduplication")
    stage_id: Optional[str] = Field(
        default=None, description="Stage execution identifier"
    )
    tool_name: str = Field(description="Name of MCP tool called")


class MCPToolListEvent(BaseEvent):
    """MCP tool list operation occurred (listing available tools)."""

    type: Literal["mcp.tool_list"] = "mcp.tool_list"
    session_id: str = Field(description="Session identifier")
    request_id: str = Field(description="Request identifier for deduplication")
    stage_id: Optional[str] = Field(
        default=None, description="Stage execution identifier"
    )
    server_name: Optional[str] = Field(
        default=None, description="MCP server name queried"
    )


class StageStartedEvent(BaseEvent):
    """Chain stage started execution."""

    type: Literal["stage.started"] = "stage.started"
    session_id: str = Field(description="Session identifier")
    stage_id: str = Field(description="Stage execution identifier")
    stage_name: str = Field(description="Human-readable stage name")


class StageCompletedEvent(BaseEvent):
    """Chain stage completed execution."""

    type: Literal["stage.completed"] = "stage.completed"
    session_id: str = Field(description="Session identifier")
    stage_id: str = Field(description="Stage execution identifier")
    stage_name: str = Field(description="Human-readable stage name")
    status: str = Field(description="Stage status (completed/failed)")


# ===== Transient Streaming Events (not persisted to DB) =====


class LLMStreamChunkEvent(BaseEvent):
    """LLM content streamed in real-time as chunks (transient, not persisted)."""
    
    type: Literal["llm.stream.chunk"] = "llm.stream.chunk"
    session_id: str = Field(description="Session identifier")
    stage_execution_id: Optional[str] = Field(
        default=None, description="Stage execution identifier"
    )
    chunk: str = Field(description="Content chunk (accumulated tokens)")
    stream_type: str = Field(description="Type of content being streamed: 'thought', 'final_answer', or 'summarization'")
    is_complete: bool = Field(default=False, description="True if this is the final chunk")
    mcp_event_id: Optional[str] = Field(
        default=None, description="MCP event ID if summarizing a tool result"
    )