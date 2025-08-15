"""
Domain models for type-safe data flow between Repository, Service, and Controller layers.

These models provide strong typing and clear data contracts, replacing the Dict[str, Any]
usage throughout the history system with proper Pydantic models.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from tarsy.models.history import AlertSession, StageExecution
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.models.api_models import InteractionSummary


class InteractionData(BaseModel):
    """Unified interaction data for timeline events."""
    interaction_id: str = Field(description="Unique interaction identifier")
    interaction_type: str = Field(description="Type: 'llm' or 'mcp'")
    timestamp_us: int = Field(description="Interaction timestamp")
    duration_ms: Optional[int] = Field(description="Duration in milliseconds")
    step_description: str = Field(description="Human-readable description")
    success: bool = Field(description="Whether interaction succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    stage_execution_id: Optional[str] = Field(None, description="Associated stage execution ID")
    
    # Type-specific details
    details: Dict[str, Any] = Field(description="Interaction-specific details")
    
    @classmethod
    def from_llm_interaction(cls, llm: LLMInteraction) -> "InteractionData":
        """Create InteractionData from LLMInteraction."""
        return cls(
            interaction_id=llm.interaction_id,
            interaction_type="llm",
            timestamp_us=llm.timestamp_us,
            duration_ms=llm.duration_ms,
            step_description=llm.step_description,
            success=llm.success,
            error_message=llm.error_message,
            stage_execution_id=llm.stage_execution_id,
            details={
                "model_name": llm.model_name,
                "request_json": llm.request_json,
                "response_json": llm.response_json,
                "token_usage": llm.token_usage,
                "tool_calls": llm.tool_calls,
                "tool_results": llm.tool_results
            }
        )
    
    @classmethod
    def from_mcp_interaction(cls, mcp: MCPInteraction) -> "InteractionData":
        """Create InteractionData from MCPInteraction."""
        return cls(
            interaction_id=mcp.communication_id,
            interaction_type="mcp",
            timestamp_us=mcp.timestamp_us,
            duration_ms=mcp.duration_ms,
            step_description=mcp.step_description,
            success=mcp.success,
            error_message=mcp.error_message,
            stage_execution_id=mcp.stage_execution_id,
            details={
                "server_name": mcp.server_name,
                "communication_type": mcp.communication_type,
                "tool_name": mcp.tool_name,
                "tool_arguments": mcp.tool_arguments,
                "tool_result": mcp.tool_result,
                "available_tools": mcp.available_tools
            }
        )


class StageData(BaseModel):
    """Complete stage execution data with interactions."""
    stage_execution: StageExecution = Field(description="Stage execution metadata")
    interactions: List[InteractionData] = Field(description="All interactions for this stage")
    interaction_summary: InteractionSummary = Field(description="Summary statistics")
    
    @property
    def execution_id(self) -> str:
        """Convenience property for stage execution ID."""
        return self.stage_execution.execution_id
    
    @property
    def stage_name(self) -> str:
        """Convenience property for stage name."""
        return self.stage_execution.stage_name


class SessionData(BaseModel):
    """Complete session data with metadata and computed statistics."""
    session: AlertSession = Field(description="Session metadata")
    llm_interaction_count: int = Field(description="Count of LLM interactions")
    mcp_communication_count: int = Field(description="Count of MCP communications")
    total_interaction_count: int = Field(description="Total interactions")
    
    # Stage-related data for chain executions
    stages: List[StageData] = Field(default_factory=list, description="Stage executions (if chain)")
    
    @property
    def session_id(self) -> str:
        """Convenience property for session ID."""
        return self.session.session_id
    
    @property
    def is_chain_execution(self) -> bool:
        """Check if this is a chain execution."""
        return self.session.chain_id is not None
    
    @property
    def duration_ms(self) -> Optional[int]:
        """Calculate session duration if completed."""
        if self.session.completed_at_us and self.session.started_at_us:
            return int((self.session.completed_at_us - self.session.started_at_us) / 1000)
        return None


class SessionTimelineData(BaseModel):
    """Complete session timeline with chronological ordering."""
    session_data: SessionData = Field(description="Complete session data")
    chronological_timeline: List[InteractionData] = Field(description="All interactions in chronological order")
    
    @property
    def session(self) -> AlertSession:
        """Convenience property for session."""
        return self.session_data.session
    
    @property
    def stages(self) -> List[StageData]:
        """Convenience property for stages."""
        return self.session_data.stages


class SessionSummaryData(BaseModel):
    """Summary statistics for a session."""
    total_interactions: int = Field(description="Total number of interactions")
    llm_interactions: int = Field(description="Number of LLM interactions")
    mcp_communications: int = Field(description="Number of MCP communications")
    system_events: int = Field(description="Number of system events")
    errors_count: int = Field(description="Number of failed interactions")
    total_duration_ms: int = Field(description="Total duration of all interactions")
    
    # Chain-specific statistics (optional)
    chain_statistics: Optional[Dict[str, Any]] = Field(None, description="Chain execution statistics")


class PaginatedSessionsData(BaseModel):
    """Paginated list of sessions with interaction counts."""
    sessions: List[AlertSession] = Field(description="List of alert sessions")
    interaction_counts: Dict[str, Dict[str, int]] = Field(description="Interaction counts per session")
    total_items: int = Field(description="Total number of sessions matching filters")
    
    def get_session_with_counts(self, session: AlertSession) -> AlertSession:
        """Get session with interaction counts attached as dynamic attributes."""
        counts = self.interaction_counts.get(session.session_id, {})
        # Use object.__setattr__ to bypass SQLModel validation
        object.__setattr__(session, 'llm_interaction_count', counts.get('llm_interactions', 0))
        object.__setattr__(session, 'mcp_communication_count', counts.get('mcp_communications', 0))
        return session


class StageInteractionCounts(BaseModel):
    """Interaction counts for stage executions."""
    execution_id: str = Field(description="Stage execution ID")
    llm_interactions: int = Field(description="Number of LLM interactions")
    mcp_communications: int = Field(description="Number of MCP communications")
    
    @property
    def total_interactions(self) -> int:
        """Total interaction count."""
        return self.llm_interactions + self.mcp_communications
