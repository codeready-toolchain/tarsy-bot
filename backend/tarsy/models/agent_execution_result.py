"""
Models for structured agent execution results.

This module defines a simple format for agent execution results,
allowing agents to provide their own summary format as a string.
"""

from typing import Any, Dict, List, Literal, Optional

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


class AgentExecutionMetadata(BaseModel):
    """Metadata for a single agent execution within a parallel stage."""
    
    model_config = ConfigDict(extra="forbid")
    
    agent_name: str = Field(..., description="Agent name (e.g., 'KubernetesAgent' or 'KubernetesAgent-1')")
    llm_provider: str = Field(..., description="LLM provider used for this execution")
    iteration_strategy: str = Field(..., description="Iteration strategy used (e.g., 'react', 'native-thinking')")
    started_at_us: int = Field(..., description="Execution start timestamp in microseconds")
    completed_at_us: int = Field(..., description="Execution completion timestamp in microseconds")
    status: StageStatus = Field(..., description="Execution status")
    error_message: Optional[str] = Field(None, description="Error message if execution failed")
    token_usage: Optional[Dict[str, int]] = Field(
        None,
        description="Token usage statistics: {'input_tokens': X, 'output_tokens': Y, 'total_tokens': Z}"
    )
    
    @property
    def duration_ms(self) -> int:
        """Calculate execution duration in milliseconds."""
        return (self.completed_at_us - self.started_at_us) // 1000


class ParallelStageMetadata(BaseModel):
    """Metadata for parallel stage orchestration."""
    
    model_config = ConfigDict(extra="forbid")
    
    # Configuration
    parallel_type: Literal["multi_agent", "replica"] = Field(
        ...,
        description="Type of parallelism (ParallelType.MULTI_AGENT or ParallelType.REPLICA)"
    )
    failure_policy: Literal["all", "any"] = Field(
        ...,
        description="Failure policy: 'all' requires all to succeed, 'any' requires at least one"
    )
    
    # Timing
    started_at_us: int = Field(..., description="Stage start timestamp in microseconds")
    completed_at_us: int = Field(..., description="Stage completion timestamp in microseconds")
    
    # Individual executions
    agent_metadatas: List[AgentExecutionMetadata] = Field(
        ...,
        description="Metadata for each parallel agent execution"
    )
    
    @property
    def duration_ms(self) -> int:
        """Calculate stage duration in milliseconds."""
        return (self.completed_at_us - self.started_at_us) // 1000
    
    @property
    def successful_count(self) -> int:
        """Count of successful agent executions."""
        return sum(1 for meta in self.agent_metadatas if meta.status == StageStatus.COMPLETED)
    
    @property
    def failed_count(self) -> int:
        """Count of failed agent executions."""
        return sum(1 for meta in self.agent_metadatas if meta.status == StageStatus.FAILED)
    
    @property
    def total_count(self) -> int:
        """Total number of agent executions."""
        return len(self.agent_metadatas)


class ParallelStageResult(BaseModel):
    """
    Container for parallel execution results - raw data only, no synthesis.
    
    This is a pure data container that packages multiple agent execution results
    along with metadata. Synthesis of results is handled by subsequent stages
    (e.g., CommanderAgent) or automatically when parallel stage is final.
    """
    
    model_config = ConfigDict(extra="forbid")
    
    results: List[AgentExecutionResult] = Field(
        ...,
        description="Full investigation results from each parallel agent execution"
    )
    metadata: ParallelStageMetadata = Field(
        ...,
        description="Structured execution metadata (configuration and agent details)"
    )
    status: StageStatus = Field(
        ...,
        description="Aggregated stage status based on failure policy and individual results"
    )