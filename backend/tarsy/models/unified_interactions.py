"""
Unified interaction models using SQLModel for both runtime and database operations.

This module provides SQLModel classes that serve as both Pydantic models for runtime
processing AND SQLAlchemy models for database storage, eliminating the need for
separate runtime/database model hierarchies and manual conversions.
"""

import uuid
from typing import List, Optional
from enum import Enum
from sqlmodel import Column, Field, SQLModel, Index
from sqlalchemy import JSON, String, TypeDecorator, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, BIGINT
from pydantic import field_validator, model_validator
from tarsy.utils.timestamp import now_us
from tarsy.models.constants import LLMInteractionType


class MessageRole(str, Enum):
    """Supported LLM message roles."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class LLMMessage(SQLModel):
    """Enhanced individual message in LLM conversation with role validation."""
    role: MessageRole = Field(..., description="Message role (system, user, assistant)")
    content: str = Field(..., min_length=1, description="Message content")
    
    @field_validator('content')
    def validate_content_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        return v.strip()


class LLMConversation(SQLModel):
    """Complete conversation thread with structured messages."""
    messages: List[LLMMessage] = Field(..., min_items=1, description="Ordered conversation messages")
    
    @field_validator('messages')
    def validate_message_order(cls, v):
        if not v:
            raise ValueError("Conversation must have at least one message")
        if v[0].role != MessageRole.SYSTEM:
            raise ValueError("Conversation must start with system message")
        return v
    
    def add_message(self, message: LLMMessage) -> None:
        """Add message to conversation with validation."""
        self.messages.append(message)
    
    def append_assistant_message(self, content: str) -> None:
        """Add assistant message to conversation."""
        message = LLMMessage(role=MessageRole.ASSISTANT, content=content)
        self.add_message(message)
    
    def append_observation(self, observation: str) -> None:
        """Add user observation message to conversation."""
        message = LLMMessage(role=MessageRole.USER, content=observation)
        self.add_message(message)
    
    def get_latest_assistant_message(self) -> Optional[LLMMessage]:
        """Get the most recent assistant message."""
        for msg in reversed(self.messages):
            if msg.role == MessageRole.ASSISTANT:
                return msg
        return None


class PydanticJSONType(TypeDecorator):
    """Custom SQLAlchemy type for Pydantic model JSON serialization."""
    impl = JSON
    
    def load_dialect_impl(self, dialect):
        # Use JSONB for PostgreSQL for better performance and GIN index support
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(JSONB())
        else:
            return dialect.type_descriptor(JSON())
    
    def process_bind_param(self, value, dialect):
        if value is not None:
            # Convert Pydantic model to dict for JSON serialization
            return value.model_dump()
        return value
    
    def process_result_value(self, value, dialect):
        if value is not None:
            # Convert dict back to Pydantic model
            return LLMConversation(**value)
        return value


class LLMInteraction(SQLModel, table=True):
    """Enhanced LLM interaction model with structured conversation storage."""
    
    __tablename__ = "llm_interactions"
    
    # Enhanced table configuration with specialized indexes
    __table_args__ = (
        # PostgreSQL-specific GIN index for efficient JSONB conversation queries
        Index('ix_llm_interactions_conversation', 'conversation', 
              postgresql_using='gin', postgresql_ops={'conversation': 'jsonb_path_ops'}),
    )
    
    interaction_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        primary_key=True,
        description="Interaction (request) identifier"
    )
    session_id: str = Field(
        sa_column=Column(String, ForeignKey("alert_sessions.session_id", ondelete="CASCADE"), index=True),
        description="Session identifier and foreign key reference to parent alert session"
    )
    stage_execution_id: Optional[str] = Field(
        None,
        sa_column=Column(String, ForeignKey("stage_executions.execution_id", ondelete="CASCADE"), index=True, nullable=True),
        description="Link to stage execution for chain context in hooks"
    )
    timestamp_us: int = Field(
        default_factory=now_us,
        sa_column=Column(BIGINT, index=True),
        description="Interaction timestamp (microseconds since epoch UTC)"
    )
    duration_ms: int = Field(default=0, description="Interaction duration in milliseconds")
    success: bool = Field(default=True, description="Whether interaction succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    # LLM-specific fields
    model_name: str = Field(description="LLM model identifier")
    provider: Optional[str] = Field(None, description="LLM provider (openai, google, etc.)")
    temperature: Optional[float] = Field(None, description="Sampling temperature")
    
    # Structured conversation storage
    conversation: Optional[LLMConversation] = Field(
        default=None,
        sa_column=Column(PydanticJSONType),
        description="Complete conversation object with messages and metadata"
    )
    
    # Token usage tracking fields
    input_tokens: Optional[int] = Field(None, ge=0, description="Input/prompt tokens")
    output_tokens: Optional[int] = Field(None, ge=0, description="Output/completion tokens")  
    total_tokens: Optional[int] = Field(None, ge=0, description="Total tokens used")
    
    # Response metadata from aggregated streaming chunks
    response_metadata: Optional[dict] = Field(
        None,
        sa_column=Column(JSON),
        description="Complete response metadata including grounding sources, tool usage, etc."
    )
    
    # Interaction type for categorization and UI rendering
    interaction_type: str = Field(
        default=LLMInteractionType.INVESTIGATION.value,
        sa_column=Column(
            String(50), 
            nullable=False, 
            server_default=LLMInteractionType.INVESTIGATION.value
        ),
        description="Type of LLM interaction (investigation, summarization, final_analysis)"
    )
    
    # Link to MCP event for summarization interactions
    mcp_event_id: Optional[str] = Field(
        None,
        description="MCP event ID if this LLM interaction is summarizing a tool result"
    )
    
    @model_validator(mode="after")
    def validate_token_consistency(self) -> "LLMInteraction":
        """Validate and ensure consistency of token fields."""
        if self.input_tokens is not None and self.output_tokens is not None:
            computed_total = self.input_tokens + self.output_tokens
            
            if self.total_tokens is None:
                # Set total_tokens if not provided
                self.total_tokens = computed_total
            elif self.total_tokens != computed_total:
                # Normalize to computed value if inconsistent
                self.total_tokens = computed_total
        
        return self

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
        sa_column=Column(String, ForeignKey("alert_sessions.session_id", ondelete="CASCADE"), index=True),
        description="Session identifier and foreign key reference to parent alert session"
    )
    stage_execution_id: Optional[str] = Field(
        None,
        sa_column=Column(String, ForeignKey("stage_executions.execution_id", ondelete="CASCADE"), index=True, nullable=True),
        description="Link to stage execution for chain context in hooks"
    )
    timestamp_us: int = Field(
        default_factory=now_us,
        sa_column=Column(BIGINT, index=True),
        description="Communication timestamp (microseconds since epoch UTC)"
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
    start_time_us: Optional[int] = Field(None, sa_column=Column(BIGINT), description="Start time in microseconds")
    end_time_us: Optional[int] = Field(None, sa_column=Column(BIGINT), description="End time in microseconds")
    
    # Note: Relationship to AlertSession removed to avoid circular import issues
    # The session_id foreign key provides the necessary database linkage
    
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