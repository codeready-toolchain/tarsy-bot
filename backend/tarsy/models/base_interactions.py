"""
Unified base models for LLM and MCP interactions.

This module provides the core interaction models that are shared between
runtime processing and database storage, eliminating the need for manual
conversions and ensuring consistency across the system.
"""

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from tarsy.utils.timestamp import now_us


class BaseInteraction(BaseModel):
    """Base model for all interactions with common fields."""
    request_id: str = Field(default_factory=lambda: f"req_{uuid.uuid4().hex[:8]}")
    session_id: str = Field(..., description="Session identifier")
    timestamp_us: int = Field(default_factory=now_us, description="Completion timestamp in microseconds")
    duration_ms: int = Field(0, description="Interaction duration in milliseconds")
    success: bool = Field(True, description="Whether interaction succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class LLMMessage(BaseModel):
    """Individual message in LLM conversation."""
    role: str = Field(..., description="Message role (system, user, assistant)")
    content: str = Field(..., description="Message content")


class BaseLLMInteraction(BaseInteraction):
    """Base model for LLM interactions with core fields."""
    model_name: str = Field(..., description="LLM model identifier")
    request_json: Dict[str, Any] = Field(..., description="Full JSON request sent to LLM API")
    response_json: Optional[Dict[str, Any]] = Field(None, description="Full JSON response from LLM API")
    token_usage: Optional[Dict[str, Any]] = Field(None, description="Token usage statistics")
    tool_calls: Optional[Dict[str, Any]] = Field(None, description="Tool calls made during interaction")
    tool_results: Optional[Dict[str, Any]] = Field(None, description="Results from tool calls")
    
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
        messages = self.request_json.get("messages", [])
        for msg in messages:
            if msg.get("role") == "system":
                return msg.get("content", "")
        return ""

    def get_user_prompt(self) -> str:
        """Extract user prompt from request."""
        messages = self.request_json.get("messages", [])
        for msg in messages:
            if msg.get("role") == "user":
                return msg.get("content", "")
        return ""


class BaseMCPInteraction(BaseInteraction):
    """Base model for MCP interactions with core fields."""
    server_name: str = Field(..., description="MCP server identifier")
    communication_type: str = Field(..., description="Type of communication (tool_list, tool_call)")
    tool_name: Optional[str] = Field(None, description="Tool name (for tool_call type)")
    tool_arguments: Optional[Dict[str, Any]] = Field(None, description="Tool arguments (for tool_call type)")
    tool_result: Optional[Dict[str, Any]] = Field(None, description="Tool result (for tool_call type)")
    available_tools: Optional[Dict[str, Any]] = Field(None, description="Available tools (for tool_list type)")
    
    def get_step_description(self) -> str:
        """Generate human-readable step description."""
        if self.communication_type == "tool_list":
            target = self.server_name if self.server_name != "all_servers" else "all servers"
            return f"Discover available tools from {target}"
        elif self.tool_name:
            return f"Execute {self.tool_name} via {self.server_name}"
        else:
            return f"MCP communication with {self.server_name}"