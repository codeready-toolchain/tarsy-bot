"""
Runtime interaction models for type-safe LLM and MCP data handling.

This module provides runtime-specific extensions of the base interaction models
with additional processing-specific fields and methods.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from tarsy.models.base_interactions import BaseLLMInteraction, BaseMCPInteraction, LLMMessage

# Re-export LLMMessage for backward compatibility
__all__ = ['LLMMessage', 'LLMRequest', 'LLMChoice', 'LLMUsage', 'LLMResponse', 'LLMInteractionData', 'MCPInteractionData', 'MCPToolListData']


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


class LLMInteractionData(BaseLLMInteraction):
    """Runtime LLM interaction with processing-specific fields."""
    provider: str = Field(..., description="LLM provider (openai, google, etc.)")
    start_time_us: int = Field(..., description="Start time in microseconds")
    end_time_us: int = Field(..., description="End time in microseconds")


class MCPInteractionData(BaseMCPInteraction):
    """Runtime MCP interaction for tool calls."""
    start_time_us: int = Field(..., description="Start time in microseconds")
    end_time_us: int = Field(..., description="End time in microseconds")


class MCPToolListData(BaseMCPInteraction):
    """Runtime MCP interaction for tool listing."""
    start_time_us: int = Field(..., description="Start time in microseconds")
    end_time_us: int = Field(..., description="End time in microseconds")
    
    def __init__(self, **data):
        # Ensure communication_type is always tool_list
        data['communication_type'] = 'tool_list'
        super().__init__(**data)