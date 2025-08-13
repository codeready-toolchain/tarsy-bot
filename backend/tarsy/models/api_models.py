"""
API Models for Request/Response Serialization

Defines Pydantic models for API request/response structures.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from tarsy.models.constants import StageStatus


# Response Models
class PaginationInfo(BaseModel):
    """Pagination information for paginated responses."""
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Items per page")
    total_pages: int = Field(description="Total number of pages")
    total_items: int = Field(description="Total number of items")

class SessionSummary(BaseModel):
    """Summary information for a session in list responses."""
    session_id: str = Field(description="Unique session identifier")
    alert_id: str = Field(description="Alert identifier that triggered this session")
    agent_type: str = Field(description="Type of agent that processed the alert")
    alert_type: Optional[str] = Field(description="Type/category of the alert")
    status: str = Field(description="Current status of the session")
    started_at_us: int = Field(description="When the session started (microseconds since epoch UTC)")
    completed_at_us: Optional[int] = Field(description="When the session completed (microseconds since epoch UTC, null if not finished)")
    error_message: Optional[str] = Field(description="Error message if session failed")
    duration_ms: Optional[int] = Field(description="Session duration in milliseconds (if completed)")
    llm_interaction_count: int = Field(description="Number of LLM interactions in this session")
    mcp_communication_count: int = Field(description="Number of MCP communications in this session")
    
    # Chain execution information
    chain_id: Optional[str] = Field(None, description="Chain identifier if this is a chain execution")
    total_stages: Optional[int] = Field(None, description="Total number of stages in the chain")
    completed_stages: Optional[int] = Field(None, description="Number of successfully completed stages")
    failed_stages: Optional[int] = Field(None, description="Number of failed stages")
    current_stage_index: Optional[int] = Field(None, description="Current stage index (if still processing)")

class SessionsListResponse(BaseModel):
    """Response for the sessions list endpoint."""
    sessions: List[SessionSummary] = Field(description="List of session summaries")
    pagination: PaginationInfo = Field(description="Pagination information")
    filters_applied: Dict[str, Any] = Field(description="Applied filters for this query")

class StageExecution(BaseModel):
    """Information about a single stage execution within a chain."""
    execution_id: str = Field(description="Unique stage execution identifier")
    stage_id: str = Field(description="Stage identifier")
    stage_index: int = Field(description="Stage position in chain (0-based)")
    stage_name: str = Field(description="Human-readable stage name")
    agent: str = Field(description="Agent used for this stage")
    iteration_strategy: Optional[str] = Field(None, description="Iteration strategy used for this stage")
    status: StageStatus = Field(description="Stage execution status")
    started_at_us: Optional[int] = Field(None, description="Stage start timestamp")
    completed_at_us: Optional[int] = Field(None, description="Stage completion timestamp")
    duration_ms: Optional[int] = Field(None, description="Stage execution duration")
    stage_output: Optional[Dict[str, Any]] = Field(None, description="Stage output data (if successful)")
    error_message: Optional[str] = Field(None, description="Error message (if failed)")

class ChainExecution(BaseModel):
    """Information about chain execution within a session."""
    chain_id: str = Field(description="Chain identifier")
    chain_definition: Dict[str, Any] = Field(description="Complete chain definition snapshot")
    current_stage_index: Optional[int] = Field(None, description="Current stage position (0-based)")
    current_stage_id: Optional[str] = Field(None, description="Current stage identifier")
    stages: List[StageExecution] = Field(description="List of stage executions in order")

class TimelineEvent(BaseModel):
    """Single event in a session timeline."""
    event_id: str = Field(description="Unique event identifier")
    type: str = Field(description="Event type ('llm_interaction', 'mcp_communication', 'stage_execution')")
    timestamp_us: int = Field(description="When the event occurred (microseconds since epoch UTC)")
    step_description: str = Field(description="Human-readable description of this step")
    details: Dict[str, Any] = Field(description="Event-specific details")
    duration_ms: Optional[int] = Field(description="Event duration in milliseconds (if available)")
    
    # Chain context information
    stage_execution_id: Optional[str] = Field(None, description="Associated stage execution ID (if part of a chain)")

class SessionDetailResponse(BaseModel):
    """Response for the individual session detail endpoint."""
    session_id: str = Field(description="Unique session identifier")
    alert_id: str = Field(description="Alert identifier that triggered this session")
    alert_data: Dict[str, Any] = Field(description="Original alert data")
    agent_type: str = Field(description="Type of agent that processed the alert")
    alert_type: Optional[str] = Field(description="Type/category of the alert")
    status: str = Field(description="Current status of the session")
    started_at_us: int = Field(description="When the session started (microseconds since epoch UTC)")
    completed_at_us: Optional[int] = Field(description="When the session completed (microseconds since epoch UTC, null if not finished)")
    error_message: Optional[str] = Field(description="Error message if session failed")
    final_analysis: Optional[str] = Field(description="Final formatted analysis result if session completed successfully")
    duration_ms: Optional[int] = Field(description="Total session duration in milliseconds (if completed)")
    session_metadata: Optional[Dict[str, Any]] = Field(description="Additional session metadata")
    
    # Chain execution information (if this is a chain session)
    chain_execution: Optional[ChainExecution] = Field(None, description="Chain execution details (if this is a chain session)")
    
    # Timeline
    chronological_timeline: List[TimelineEvent] = Field(description="Chronologically ordered list of all events")
    summary: Dict[str, Any] = Field(description="Session summary statistics")

class HealthCheckResponse(BaseModel):
    """Response for health check endpoints."""
    service: str = Field(description="Service name")
    status: str = Field(description="Service status ('healthy', 'unhealthy', 'disabled')")
    timestamp_us: int = Field(description="Health check timestamp (microseconds since epoch UTC)")
    details: Dict[str, Any] = Field(description="Additional health check details")

class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str = Field(description="Error type or category")
    message: str = Field(description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(description="Additional error details")
    timestamp_us: int = Field(description="When the error occurred (microseconds since epoch UTC)") 