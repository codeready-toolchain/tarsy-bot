"""
Models for structured agent execution results.

This module defines a simple format for agent execution results,
allowing agents to provide their own summary format as a string.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from tarsy.models.constants import StageStatus


class AgentExecutionResult(BaseModel):
    """
    Simple result from agent execution.
    
    This model allows agents to provide their own summary in whatever format they choose.
    The alert service just passes this through to subsequent stages.
    """
    model_config = ConfigDict(extra="forbid")
    
    # Basic execution metadata
    status: StageStatus = Field(..., description="Execution status")
    agent_name: str = Field(..., description="Name of the agent that produced this result")
    stage_name: Optional[str] = Field(None, description="Name of the stage (e.g., 'data-collection')")
    stage_description: Optional[str] = Field(None, description="Human-readable description of what this stage did")
    timestamp_us: int = Field(..., description="Completion timestamp in microseconds")
    
    # The key field - agent decides the format (could be ReAct JSON, markdown, plain text, etc.)
    result_summary: str = Field(..., description="Agent-provided summary in whatever format the agent chooses")
    
    # Complete conversation history for stage context passing (string format for inter-stage context)
    complete_conversation_history: Optional[str] = Field(
        None, 
        description="Formatted ReAct conversation for passing context to subsequent stages (string format)"
    )
    
    # Conversation state for pause/resume (dict format for exact state restoration)
    paused_conversation_state: Optional[Dict[str, Any]] = Field(
        None,
        description="LLMConversation state for resuming paused stages (only populated when status=PAUSED)"
    )
    
    # Optional clean final analysis for end-user consumption
    final_analysis: Optional[str] = Field(None, description="Clean final analysis for end-user, extracted from result_summary")
    
    # Error handling
    error_message: Optional[str] = Field(None, description="Error message if execution failed")
    
    # Optional metadata
    duration_ms: Optional[int] = Field(None, description="Execution duration in milliseconds")
    
    @field_validator('paused_conversation_state')
    @classmethod
    def validate_paused_state(cls, v: Optional[Dict[str, Any]], info: ValidationInfo) -> Optional[Dict[str, Any]]:
        """Ensure paused_conversation_state is only set when status is PAUSED."""
        if v is not None:
            status = info.data.get('status')
            # Handle both enum and string values
            if isinstance(status, StageStatus):
                status_value = status.value
            else:
                status_value = status
            
            if status_value != StageStatus.PAUSED.value:
                raise ValueError(f"paused_conversation_state can only be set when status is PAUSED, got status={status_value}")
        return v