"""
Type-safe data models for the history system.

This module provides Pydantic models that replace dict-based data structures
throughout the history service. These models ensure type safety and validation
for session timelines, interaction details, and API responses.
"""

from __future__ import annotations  # Deferred evaluation for forward references

from typing import List, Dict, Optional, Union, Literal, Any
from pydantic import BaseModel, Field, model_validator, computed_field

# Import existing enums and models
from tarsy.models.constants import AlertSessionStatus, StageStatus
from tarsy.models.unified_interactions import LLMInteraction
from tarsy.models.mcp_selection_models import MCPSelectionConfig


# =============================================================================
# CORE SHARED MODELS
# =============================================================================

class PaginationInfo(BaseModel):
    """Pagination information for paginated responses."""
    page: int
    page_size: int
    total_pages: int
    total_items: int


class TimeRangeOption(BaseModel):
    """Filter time range option"""
    label: str
    value: str


class FilterOptions(BaseModel):
    """Available filter options"""
    agent_types: List[str]
    alert_types: List[str] 
    status_options: List[str]  # String values for API consistency
    time_ranges: List[TimeRangeOption]


# =============================================================================
# EVENT DETAILS MODELS
# =============================================================================

class MCPEventDetails(BaseModel):
    """MCP-specific event details with structured objects"""
    
    tool_name: Optional[str] = None # Only required for tool_call interactions
    server_name: str
    communication_type: Literal["tool_list", "tool_call"]
    tool_arguments: Optional[Dict[str, Any]] = Field(default_factory=dict)
    tool_result: Optional[Dict[str, Any]] = Field(default_factory=dict)
    available_tools: Dict[str, Any] = Field(default_factory=dict)  # structured tools data, not serialized JSON
    success: bool
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None


# =============================================================================
# INTERACTION MODELS
# =============================================================================

class BaseInteraction(BaseModel):
    """Base interaction model with common fields"""
    id: str                    # Same as event_id (legacy field)
    event_id: str
    timestamp_us: int
    step_description: str
    duration_ms: Optional[int] = None
    stage_execution_id: str


class LLMTimelineEvent(BaseInteraction):
    """LLM timeline event using complete interaction details directly."""
    type: Literal["llm"] = "llm"
    details: LLMInteraction
    
    @model_validator(mode='after')
    def validate_llm_details(self):
        """Validate LLM-specific details"""
        if not self.details.model_name:
            raise ValueError("LLM interactions require model_name in details")
        return self


class MCPTimelineEvent(BaseInteraction):
    """MCP timeline event with type-specific details"""
    type: Literal["mcp"] = "mcp"
    details: MCPEventDetails
    
    @model_validator(mode='after') 
    def validate_mcp_details(self):
        """Validate MCP-specific details"""
        if not self.details.server_name:
            raise ValueError("MCP interactions require server_name in details")
        # tool_name is only required for tool_call interactions, not tool_list
        if self.details.communication_type == "tool_call" and not self.details.tool_name:
            raise ValueError("MCP tool_call interactions require tool_name in details")
        return self


# Union type for timeline events
TimelineEvent = Union[LLMTimelineEvent, MCPTimelineEvent]


# =============================================================================
# SUMMARY MODELS
# =============================================================================

class LLMInteractionSummary(BaseModel):
    """Simplified LLM interaction for summary lists"""
    interaction_id: str
    timestamp_us: int
    step_description: str
    model_name: str
    duration_ms: Optional[int] = None


class MCPCommunicationSummary(BaseModel):
    """Simplified MCP communication for summary lists"""
    communication_id: str
    timestamp_us: int
    step_description: str
    server_name: str
    tool_name: str
    success: bool
    duration_ms: Optional[int] = None


# =============================================================================
# CHAIN STATISTICS MODEL
# =============================================================================

class ChainStatistics(BaseModel):
    """Chain execution statistics"""
    total_stages: int
    completed_stages: int
    failed_stages: int
    stages_by_agent: Dict[str, int]


# =============================================================================
# CHAT MESSAGE MODELS
# =============================================================================

class ChatUserMessageData(BaseModel):
    """User message data embedded in stage execution responses"""
    message_id: str
    content: str
    author: str
    created_at_us: int


# =============================================================================
# MAIN RESPONSE MODELS
# =============================================================================

class SessionOverview(BaseModel):
    """Session overview for lists, filtering, and pagination - dashboard use"""
    # Core identification
    session_id: str
    alert_type: Optional[str] = None
    agent_type: str
    status: AlertSessionStatus
    author: Optional[str] = None
    
    # Timing info
    started_at_us: int
    completed_at_us: Optional[int] = None
    
    # Basic status info
    error_message: Optional[str] = None
    
    # Summary counts (for dashboard display)
    llm_interaction_count: int = 0
    mcp_communication_count: int = 0
    total_interactions: int = 0
    
    # Token usage aggregations
    session_input_tokens: Optional[int] = None
    session_output_tokens: Optional[int] = None  
    session_total_tokens: Optional[int] = None
    
    # Chain progress info (for dashboard filtering/display)
    chain_id: str
    total_stages: Optional[int] = None
    completed_stages: Optional[int] = None
    failed_stages: int = 0
    current_stage_index: Optional[int] = None  # Matches AlertSession field type
    
    # MCP configuration override
    mcp_selection: Optional[MCPSelectionConfig] = None
    
    chat_message_count: Optional[int] = None  # Number of user messages in follow-up chat (if chat exists)
    
    # Calculated properties
    @computed_field
    @property
    def duration_ms(self) -> Optional[int]:
        """Calculate session duration from start and completion times"""
        if self.started_at_us and self.completed_at_us:
            return (self.completed_at_us - self.started_at_us) // 1000
        return None


class DetailedStage(BaseModel):
    """Complete stage execution with all interactions - for detailed view"""
    # Stage identification
    execution_id: str
    session_id: str
    stage_id: str
    stage_index: int
    stage_name: str
    agent: str
    
    # Stage execution info
    status: StageStatus
    started_at_us: Optional[int] = None
    completed_at_us: Optional[int] = None
    duration_ms: Optional[int] = None
    stage_output: Optional[dict] = None  # Structured results produced by this stage (e.g. analysis findings, collected data) - used by subsequent stages in chain. None if stage failed/incomplete.
    error_message: Optional[str] = None
    
    # Chat context (if this stage is a chat response)
    chat_id: Optional[str] = None
    chat_user_message_id: Optional[str] = None
    chat_user_message: Optional[ChatUserMessageData] = None  # Full user message data (populated when chat_user_message_id exists)
    
    # ALL interactions that happened during this stage (FULL objects with complete details)
    llm_interactions: List[LLMTimelineEvent] = Field(default_factory=list)  # Complete LLM interactions with full details
    mcp_communications: List[MCPTimelineEvent] = Field(default_factory=list)  # Complete MCP interactions with full details
    
    # Summary counts for this stage
    llm_interaction_count: int = 0
    mcp_communication_count: int = 0
    total_interactions: int = 0
    
    # Calculated properties
    @computed_field
    @property
    def stage_interactions_duration_ms(self) -> Optional[int]:
        """Calculate total duration from all interactions in this stage"""
        total = 0
        for interaction in self.llm_interactions + self.mcp_communications:
            if interaction.duration_ms:
                total += interaction.duration_ms
        return total if total > 0 else None
    
    @computed_field
    @property  
    def stage_input_tokens(self) -> Optional[int]:
        """Sum of input tokens from all LLM interactions in this stage"""
        total = sum(
            interaction.details.input_tokens or 0 
            for interaction in self.llm_interactions
        )
        return total if total > 0 else None

    @computed_field
    @property
    def stage_output_tokens(self) -> Optional[int]:
        """Sum of output tokens from all LLM interactions in this stage"""
        total = sum(
            interaction.details.output_tokens or 0 
            for interaction in self.llm_interactions
        )
        return total if total > 0 else None

    @computed_field
    @property
    def stage_total_tokens(self) -> Optional[int]:
        """Sum of total tokens from all LLM interactions in this stage"""
        total = sum(
            interaction.details.total_tokens or 0 
            for interaction in self.llm_interactions
        )
        return total if total > 0 else None
    
    @computed_field
    @property
    def chronological_interactions(self) -> List[TimelineEvent]:
        """
        Get all interactions in chronological order by timestamp.
        
        Returns a sorted list combining LLM and MCP interactions, ordered by timestamp_us.
        This provides the actual timeline of what happened during stage execution,
        which is essential for debugging, dashboards, and understanding agent reasoning flow.
        
        Returns:
            List[TimelineEvent]: All interactions sorted chronologically
        """
        # Combine all interactions and sort by timestamp
        all_interactions: List[TimelineEvent] = [
            *self.llm_interactions,
            *self.mcp_communications
        ]
        
        # Sort chronologically by timestamp_us
        return sorted(all_interactions, key=lambda x: x.timestamp_us)


class DetailedSession(BaseModel):
    """Complete session with EVERYTHING - for detailed session page"""
    # Core session data (everything from SessionOverview)
    session_id: str
    alert_type: Optional[str] = None
    agent_type: str
    status: AlertSessionStatus
    author: Optional[str] = None
    runbook_url: Optional[str] = None
    started_at_us: int
    completed_at_us: Optional[int] = None
    error_message: Optional[str] = None
    
    # Full session details
    alert_data: dict  # Complete alert information
    final_analysis: Optional[str] = None
    session_metadata: Optional[dict] = None
    pause_metadata: Optional[Dict[str, Any]] = None
    
    # Chain execution details
    chain_id: str
    chain_definition: dict
    current_stage_index: Optional[int] = None  # Matches AlertSession field type
    current_stage_id: Optional[str] = None  # Matches AlertSession field type
    
    # MCP configuration override
    mcp_selection: Optional[MCPSelectionConfig] = None
    
    # Complete interaction data
    total_interactions: int = 0
    llm_interaction_count: int = 0
    mcp_communication_count: int = 0
    
    # Token usage aggregations
    session_input_tokens: Optional[int] = None
    session_output_tokens: Optional[int] = None  
    session_total_tokens: Optional[int] = None
    
    # Complete stage executions with all their interactions
    stages: List[DetailedStage] = Field(default_factory=list)  # Each stage contains its full interaction timeline
    
    # Calculated properties
    @computed_field
    @property
    def duration_ms(self) -> Optional[int]:
        """Calculate session duration from start and completion times"""
        if self.started_at_us and self.completed_at_us:
            return (self.completed_at_us - self.started_at_us) // 1000
        return None


class SessionStats(BaseModel):
    """Lightweight statistics and metrics - for headers and quick stats"""
    # Basic counts
    total_interactions: int
    llm_interactions: int
    mcp_communications: int
    system_events: int = 0
    errors_count: int
    total_duration_ms: int
    
    # Token usage aggregations
    session_input_tokens: int = 0
    session_output_tokens: int = 0  
    session_total_tokens: int = 0
    
    # Chain progress (always present since all sessions are chains)
    chain_statistics: ChainStatistics


class PaginatedSessions(BaseModel):
    """Paginated session results for dashboard list view"""
    sessions: List[SessionOverview]  # Session overviews for list display
    pagination: PaginationInfo
    filters_applied: Dict[str, Any] = Field(default_factory=dict)  # Applied filters for this query
