"""
Models for structured agent execution results.

This module defines a simple format for agent execution results,
allowing agents to provide their own summary format as a string.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any, Optional
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
    timestamp_us: int = Field(..., description="Execution timestamp in microseconds")
    
    # The key field - agent decides the format (could be ReAct JSON, markdown, plain text, etc.)
    result_summary: str = Field(..., description="Agent-provided summary in whatever format the agent chooses")
    
    # Optional clean final analysis for end-user consumption
    final_analysis: Optional[str] = Field(None, description="Clean final analysis for end-user, extracted from result_summary")
    
    # Error handling
    error_message: Optional[str] = Field(None, description="Error message if execution failed")
    
    # Optional metadata
    duration_ms: Optional[int] = Field(None, description="Execution duration in milliseconds")


class ChainExecutionContext(BaseModel):
    """
    Simple accumulated context from all previous stages in a chain.
    
    Just collects the agent-provided summaries and passes them through.
    """
    model_config = ConfigDict(extra="forbid")
    
    stage_results: Dict[str, AgentExecutionResult] = Field(
        default_factory=dict,
        description="Results from completed stages, keyed by stage name"
    )
    
    def get_formatted_context(self) -> str:
        """Get all previous stage summaries formatted for next stage."""
        if not self.stage_results:
            return "No previous stage context available."
        
        sections = []
        for stage_name, result in self.stage_results.items():
            stage_title = result.stage_description or stage_name
            sections.append(f"## Results from '{stage_title}' stage:")
            sections.append(result.result_summary)
            sections.append("")
        
        return "\n".join(sections)
