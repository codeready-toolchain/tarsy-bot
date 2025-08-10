"""
Structured interaction models for type-safe LLM and MCP data handling.

This module provides Pydantic models for LLM and MCP interactions that ensure
type safety and prevent data contamination between hook contexts and actual results.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid



class LLMMessage(BaseModel):
    """Individual message in LLM conversation."""
    role: str = Field(..., description="Message role (system, user, assistant)")
    content: str = Field(..., description="Message content")


class LLMRequest(BaseModel):
    """LLM request structure with essential parameters."""
    model: str = Field(..., description="Model name")
    messages: List[LLMMessage] = Field(..., description="Conversation messages")
    temperature: Optional[float] = Field(None, description="Sampling temperature")


class LLMChoice(BaseModel):
    """Individual choice in LLM response."""
    message: LLMMessage = Field(..., description="Response message")
    finish_reason: str = Field(..., description="Why generation stopped")


class LLMUsage(BaseModel):
    """Token usage information."""
    prompt_tokens: Optional[int] = Field(None, description="Tokens in prompt")
    completion_tokens: Optional[int] = Field(None, description="Tokens in completion")
    total_tokens: Optional[int] = Field(None, description="Total tokens used")


class LLMResponse(BaseModel):
    """LLM response structure matching API format."""
    choices: List[LLMChoice] = Field(..., description="Response choices")
    model: Optional[str] = Field(None, description="Model used")
    usage: Optional[LLMUsage] = Field(None, description="Token usage")


class LLMInteractionData(BaseModel):
    """Complete LLM interaction with metadata."""
    request_id: str = Field(default_factory=lambda: f"llm_{uuid.uuid4().hex[:8]}")
    session_id: str = Field(..., description="Session identifier")
    request: LLMRequest = Field(..., description="Request data")
    response: Optional[LLMResponse] = Field(None, description="Response data")
    provider: str = Field(..., description="LLM provider (openai, google, etc.)")
    model_name: str = Field(..., description="Model name used")
    success: bool = Field(True, description="Whether interaction succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    duration_ms: int = Field(0, description="Interaction duration in milliseconds")
    start_time_us: int = Field(..., description="Start time in microseconds")
    end_time_us: int = Field(..., description="End time in microseconds")
    timestamp_us: int = Field(..., description="Completion timestamp in microseconds")
    
    def get_response_text(self) -> str:
        """Extract response text from structured response."""
        if not self.response or not self.response.choices:
            return ""
        return self.response.choices[0].message.content

    def get_system_prompt(self) -> str:
        """Extract system prompt from request."""
        for msg in self.request.messages:
            if msg.role == "system":
                return msg.content
        return ""

    def get_user_prompt(self) -> str:
        """Extract user prompt from request."""
        for msg in self.request.messages:
            if msg.role == "user":
                return msg.content
        return ""


class MCPToolCall(BaseModel):
    """MCP tool call details."""
    server_name: str = Field(..., description="MCP server name")
    tool_name: str = Field(..., description="Tool name")
    arguments: Dict[str, Any] = Field(..., description="Tool arguments")


class MCPToolResult(BaseModel):
    """MCP tool execution result."""
    result: Any = Field(..., description="Tool execution result")
    success: bool = Field(True, description="Whether tool call succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class MCPInteractionData(BaseModel):
    """Complete MCP interaction with metadata."""
    request_id: str = Field(default_factory=lambda: f"mcp_{uuid.uuid4().hex[:8]}")
    session_id: str = Field(..., description="Session identifier")
    tool_call: MCPToolCall = Field(..., description="Tool call details")
    tool_result: Optional[MCPToolResult] = Field(None, description="Tool result")
    communication_type: str = Field("tool_call", description="Type of MCP communication")
    success: bool = Field(True, description="Whether interaction succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    duration_ms: int = Field(0, description="Interaction duration in milliseconds")
    start_time_us: int = Field(..., description="Start time in microseconds")
    end_time_us: int = Field(..., description="End time in microseconds")
    timestamp_us: int = Field(..., description="Completion timestamp in microseconds")

    def get_step_description(self) -> str:
        """Generate human-readable step description."""
        if self.communication_type == "tool_list":
            return f"Discover available tools from {self.tool_call.server_name}"
        else:
            return f"Execute {self.tool_call.tool_name} via {self.tool_call.server_name}"


class MCPToolListResult(BaseModel):
    """Result from MCP tool listing operation."""
    tools: Dict[str, List[Dict[str, Any]]] = Field(..., description="Available tools by server")


class MCPToolListData(BaseModel):
    """MCP tool listing interaction."""
    request_id: str = Field(default_factory=lambda: f"mcp_{uuid.uuid4().hex[:8]}")
    session_id: str = Field(..., description="Session identifier")
    server_name: Optional[str] = Field(None, description="Target server (None for all)")
    result: Optional[MCPToolListResult] = Field(None, description="Tool list result")
    communication_type: str = Field("tool_list", description="Communication type")
    success: bool = Field(True, description="Whether operation succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    duration_ms: int = Field(0, description="Operation duration in milliseconds")
    start_time_us: int = Field(..., description="Start time in microseconds")
    end_time_us: int = Field(..., description="End time in microseconds")
    timestamp_us: int = Field(..., description="Completion timestamp in microseconds")

    def get_step_description(self) -> str:
        """Generate human-readable step description."""
        target = self.server_name if self.server_name else "all servers"
        return f"Discover available tools from {target}"