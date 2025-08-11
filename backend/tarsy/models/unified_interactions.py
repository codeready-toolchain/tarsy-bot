"""
Unified interaction models using SQLModel for both runtime and database operations.

This module provides SQLModel classes that serve as both Pydantic models for runtime
processing AND SQLAlchemy models for database storage, eliminating the need for
separate runtime/database model hierarchies and manual conversions.
"""

import uuid
from typing import Any, Dict, List, Optional
from sqlmodel import JSON, Column, Field, Relationship, SQLModel, Index
from sqlalchemy import text

from tarsy.utils.timestamp import now_us


class LLMMessage(SQLModel):
    """Individual message in LLM conversation."""
    role: str = Field(..., description="Message role (system, user, assistant)")
    content: str = Field(..., description="Message content")


class LLMRequest(SQLModel):
    """LLM request structure with essential parameters."""
    model: str = Field(..., description="Model name")
    messages: List[LLMMessage] = Field(..., description="Conversation messages")
    temperature: Optional[float] = Field(None, description="Sampling temperature")


class LLMChoice(SQLModel):
    """Individual choice in LLM response."""
    message: LLMMessage = Field(..., description="Response message")
    finish_reason: str = Field(..., description="Why generation stopped")


class LLMUsage(SQLModel):
    """Token usage information."""
    prompt_tokens: Optional[int] = Field(None, description="Tokens in prompt")
    completion_tokens: Optional[int] = Field(None, description="Tokens in completion")
    total_tokens: Optional[int] = Field(None, description="Total tokens used")


class LLMResponse(SQLModel):
    """LLM response structure matching API format."""
    choices: List[LLMChoice] = Field(..., description="Response choices")
    model: Optional[str] = Field(None, description="Model used")
    usage: Optional[LLMUsage] = Field(None, description="Token usage")


class LLMInteraction(SQLModel, table=True):
    """
    Unified LLM interaction model for both runtime processing and database storage.
    
    This model serves as both a Pydantic model for type-safe runtime operations
    and a SQLAlchemy model for database persistence, eliminating the need for
    separate model hierarchies and manual conversions.
    """
    
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
    request_id: str = Field(
        default_factory=lambda: f"req_{uuid.uuid4().hex[:8]}",
        description="Request identifier"
    )
    session_id: str = Field(
        foreign_key="alert_sessions.session_id",
        description="Session identifier and foreign key reference to parent alert session"
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
    
    # Runtime-specific fields (not persisted to DB when None)
    provider: Optional[str] = Field(None, description="LLM provider (openai, google, etc.)")
    start_time_us: Optional[int] = Field(None, description="Start time in microseconds")
    end_time_us: Optional[int] = Field(None, description="End time in microseconds")
    
    # Relationship back to session
    session: Optional["AlertSession"] = Relationship(back_populates="llm_interactions")
    
    # Runtime helper methods
    def get_response_text(self) -> str:
        """Extract response text from structured response."""
        if not self.response_json or not self.response_json.get("choices"):
            return ""
        choice = self.response_json["choices"][0]
        if choice and choice.get("message") and choice["message"].get("content"):
            return choice["message"]["content"]
        return ""

    def get_system_prompt(self) -> str:
        """Extract system prompt from request."""
        if not self.request_json:
            return ""
        messages = self.request_json.get("messages", [])
        for msg in messages:
            if msg.get("role") == "system":
                return msg.get("content", "")
        return ""

    def get_user_prompt(self) -> str:
        """Extract user prompt from request."""
        if not self.request_json:
            return ""
        messages = self.request_json.get("messages", [])
        for msg in messages:
            if msg.get("role") == "user":
                return msg.get("content", "")
        return ""


class MCPInteraction(SQLModel, table=True):
    """
    Unified MCP interaction model for both runtime processing and database storage.
    
    This model serves as both a Pydantic model for type-safe runtime operations
    and a SQLAlchemy model for database persistence, eliminating the need for
    separate model hierarchies and manual conversions.
    """
    
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
    request_id: str = Field(
        default_factory=lambda: f"req_{uuid.uuid4().hex[:8]}",
        description="Request identifier"
    )
    session_id: str = Field(
        foreign_key="alert_sessions.session_id",
        description="Session identifier and foreign key reference to parent alert session"
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
    
    # Runtime-specific fields (not persisted to DB when None)
    start_time_us: Optional[int] = Field(None, description="Start time in microseconds")
    end_time_us: Optional[int] = Field(None, description="End time in microseconds")
    
    # Relationship back to session
    session: Optional["AlertSession"] = Relationship(back_populates="mcp_communications")
    
    # Runtime helper methods
    def get_step_description(self) -> str:
        """Generate human-readable step description."""
        if self.communication_type == "tool_list":
            target = self.server_name if self.server_name != "all_servers" else "all servers"
            return f"Discover available tools from {target}"
        elif self.tool_name:
            return f"Execute {self.tool_name} via {self.server_name}"
        else:
            return f"MCP communication with {self.server_name}"


# Type aliases for backward compatibility and clarity
LLMInteractionData = LLMInteraction  # Runtime usage
MCPInteractionData = MCPInteraction  # Runtime usage for tool calls
MCPToolListData = MCPInteraction     # Runtime usage for tool lists