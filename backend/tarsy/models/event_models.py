"""
Event models for type-safe event publishing.

Events are lightweight notification triggers that inform clients about changes.
Clients use these events to determine when to refresh data via REST API.
"""

import time
from typing import Any, Dict, Literal, Optional

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


class SessionPausedEvent(BaseEvent):
    """Session paused at max iterations."""

    type: Literal["session.paused"] = "session.paused"
    session_id: str = Field(description="Session identifier")
    status: Literal["paused"] = "paused"  # For instant client update
    pause_metadata: Optional[Dict[str, Any]] = Field(default=None, description="Metadata about why session paused")


class SessionResumedEvent(BaseEvent):
    """Session resumed from paused state."""

    type: Literal["session.resumed"] = "session.resumed"
    session_id: str = Field(description="Session identifier")
    status: Literal["in_progress"] = "in_progress"  # For instant client update


class SessionCancelRequestedEvent(BaseEvent):
    """Session cancellation requested (backend-to-backend communication)."""

    type: Literal["session.cancel_requested"] = "session.cancel_requested"
    session_id: str = Field(description="Session identifier")


class ChatCancelRequestedEvent(BaseEvent):
    """Chat execution cancellation requested (backend-to-backend communication)."""

    type: Literal["chat.cancel_requested"] = "chat.cancel_requested"
    stage_execution_id: str = Field(description="Stage execution identifier for the chat response")


class SessionCancelledEvent(BaseEvent):
    """Session cancelled successfully."""

    type: Literal["session.cancelled"] = "session.cancelled"
    session_id: str = Field(description="Session identifier")
    status: Literal["cancelled"] = "cancelled"  # For instant client update


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
    chat_id: Optional[str] = Field(default=None, description="Chat ID if this is a chat response stage")
    # User message data (for chat stages)
    chat_user_message_id: Optional[str] = Field(default=None, description="User message ID if this is a chat response")
    chat_user_message_content: Optional[str] = Field(default=None, description="User message content")
    chat_user_message_author: Optional[str] = Field(default=None, description="User message author")
    # Parallel execution metadata (for parent parallel stages)
    parallel_type: Optional[str] = Field(default=None, description="Parallel execution type: 'multi_agent' or 'replica'")
    expected_parallel_count: Optional[int] = Field(default=None, description="Expected number of parallel children")


class StageCompletedEvent(BaseEvent):
    """Chain stage completed execution."""

    type: Literal["stage.completed"] = "stage.completed"
    session_id: str = Field(description="Session identifier")
    stage_id: str = Field(description="Stage execution identifier")
    stage_name: str = Field(description="Human-readable stage name")
    status: str = Field(description="Stage status (completed/failed)")
    chat_id: Optional[str] = Field(default=None, description="Chat ID if this is a chat response stage")


# ===== Transient Streaming Events (not persisted to DB) =====


class LLMStreamChunkEvent(BaseEvent):
    """LLM content streamed in real-time as chunks (transient, not persisted)."""
    
    type: Literal["llm.stream.chunk"] = "llm.stream.chunk"
    session_id: str = Field(description="Session identifier")
    stage_execution_id: Optional[str] = Field(
        default=None, description="Stage execution identifier (child execution ID for parallel stages)"
    )
    chunk: str = Field(description="Content chunk (accumulated tokens)")
    stream_type: str = Field(description="Type of content being streamed: 'thought', 'final_answer', 'summarization', or 'native_thinking'")
    is_complete: bool = Field(default=False, description="True if this is the final chunk")
    mcp_event_id: Optional[str] = Field(
        default=None, description="MCP event ID if summarizing a tool result"
    )
    llm_interaction_id: Optional[str] = Field(
        default=None, description="LLM interaction ID for deduplication of thought/final_answer/native_thinking streams"
    )
    # Parallel execution metadata
    parent_stage_execution_id: Optional[str] = Field(
        default=None, description="Parent stage execution ID for parallel child stages"
    )
    parallel_index: Optional[int] = Field(
        default=None, description="Position in parallel group (1-N for parallel children, None for single stages)"
    )
    agent_name: Optional[str] = Field(
        default=None, description="Agent name for this execution"
    )


# ===== Chat Events (channel: 'session:{session_id}') =====


class ChatCreatedEvent(BaseEvent):
    """Chat created for a session."""
    
    type: Literal["chat.created"] = "chat.created"
    session_id: str = Field(description="Session identifier")
    chat_id: str = Field(description="Chat identifier")
    created_by: str = Field(description="User who created the chat")


class ChatUserMessageEvent(BaseEvent):
    """User sent a message to the chat."""
    
    type: Literal["chat.user_message"] = "chat.user_message"
    session_id: str = Field(description="Session identifier")
    chat_id: str = Field(description="Chat identifier")
    message_id: str = Field(description="Message identifier")
    content: str = Field(description="Message content")
    author: str = Field(description="Message author")