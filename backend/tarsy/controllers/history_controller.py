"""
History Controller

FastAPI controller for alert processing history endpoints.
Provides REST API for querying historical data with filtering, pagination,
and chronological timeline reconstruction.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from tarsy.utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

from tarsy.models.api_models import (
    ErrorResponse,
    HealthCheckResponse,
    InteractionSummary,
    PaginationInfo,
    SessionDetailResponse,
    SessionsListResponse,
    SessionSummary,
    ChainExecution,
    StageExecution,
)
# Import new type-safe models for Phase 4
from tarsy.models.history_models import (
    DetailedSession,
    PaginatedSessions,
    SessionOverview, 
    SessionStats,
    FilterOptions
)
from tarsy.models.history import now_us
from tarsy.services.history_service import HistoryService, get_history_service

# Valid event types expected from the repository
VALID_EVENT_TYPES = {'llm', 'mcp', 'system'}

router = APIRouter(prefix="/api/v1/history", tags=["history"])

@router.get(
    "/sessions", 
    response_model=SessionsListResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Bad request - invalid parameters"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="List Alert Processing Sessions",
    description="""
    Retrieve a paginated list of alert processing sessions with optional filtering.
    
    **Filtering Support:**
    - Multiple filters use AND logic (all conditions must be met)
    - Combine filters for precise queries (e.g., alert_type + status + time_range)
    
    **Common Use Cases:**
    1. Recent completed alerts: `status=completed&start_date_us=1734476400000000`
    2. Kubernetes alerts: `agent_type=kubernetes&status=completed`
    3. Specific alert types: `alert_type=NamespaceTerminating`
    4. Search error messages: `search=connection refused&status=failed`
    5. Search analysis content: `search=namespace terminating`
    6. Time range analysis: `start_date_us=1734476400000000&end_date_us=1734562799999999`
    
    **Timestamp Format:**
    - All timestamps are Unix timestamps in microseconds since epoch (UTC)
    """
)
async def list_sessions(
    status: Optional[List[str]] = Query(None, description="Filter by session status(es) - supports multiple values"),
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    search: Optional[str] = Query(None, description="Text search across alert messages, error messages, and analysis results", min_length=3),
    start_date_us: Optional[int] = Query(None, description="Filter sessions started after this timestamp (microseconds since epoch UTC)"),
    end_date_us: Optional[int] = Query(None, description="Filter sessions started before this timestamp (microseconds since epoch UTC)"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
    history_service: HistoryService = Depends(get_history_service)
) -> SessionsListResponse:
    """
    List alert processing sessions with filtering and pagination.
    
    Args:
        status: Optional status filter(s) (e.g., ['completed', 'failed'] or ['in_progress'])
        agent_type: Optional agent type filter (e.g., 'kubernetes')
        alert_type: Optional alert type filter (e.g., 'NamespaceTerminating')
        search: Optional text search across alert messages, errors, and analysis (minimum 3 characters)
        start_date_us: Optional start timestamp filter (microseconds since epoch UTC, inclusive)
        end_date_us: Optional end timestamp filter (microseconds since epoch UTC, inclusive)
        page: Page number (starting from 1)
        page_size: Number of items per page (1-100)
        history_service: Injected history service
        
    Returns:
        SessionsListResponse containing paginated session list with filters applied
        
    Raises:
        HTTPException: 400 for invalid parameters, 500 for internal errors
    """
    try:
        # Build filters dictionary
        filters = {}
        if status is not None:
            filters['status'] = status
        if agent_type is not None:
            filters['agent_type'] = agent_type
        if alert_type is not None:
            filters['alert_type'] = alert_type
        if search is not None and search.strip():
            filters['search'] = search.strip()
        if start_date_us is not None:
            filters['start_date_us'] = start_date_us
        if end_date_us is not None:
            filters['end_date_us'] = end_date_us
            
        # Validate timestamp range
        if start_date_us and end_date_us and start_date_us >= end_date_us:
            raise HTTPException(
                status_code=400,
                detail="start_date_us must be before end_date_us"
            )
        
        # Phase 4: Use internal service method that returns type-safe PaginatedSessions model
        paginated_sessions = history_service.get_sessions_list(
            filters=filters,
            page=page,
            page_size=page_size
        )
        
        if not paginated_sessions:
            # Return empty response if no data available
            return SessionsListResponse(
                sessions=[],
                pagination=PaginationInfo(
                    page=page,
                    page_size=page_size,
                    total_pages=0,
                    total_items=0
                ),
                filters_applied=filters
            )
        
        # Phase 4.2: Convert new models to API models for compatibility
        # Convert SessionOverview objects to SessionSummary for existing API contract
        session_summaries = []
        for session_overview in paginated_sessions.sessions:
            session_summary = SessionSummary(
                session_id=session_overview.session_id,
                alert_id=session_overview.alert_id,
                agent_type=session_overview.agent_type,
                alert_type=session_overview.alert_type,
                status=session_overview.status.value,  # Convert enum to string
                started_at_us=session_overview.started_at_us,
                completed_at_us=session_overview.completed_at_us,
                error_message=session_overview.error_message,
                duration_ms=session_overview.duration_ms,  # Use the property
                llm_interaction_count=session_overview.llm_interaction_count,
                mcp_communication_count=session_overview.mcp_communication_count,
                # Chain fields
                chain_id=session_overview.chain_id,
                total_stages=session_overview.total_stages,
                completed_stages=session_overview.completed_stages,
                failed_stages=session_overview.failed_stages,
                current_stage_index=session_overview.current_stage_index
            )
            session_summaries.append(session_summary)
        
        # Convert PaginationInfo from history_models to api_models format
        api_pagination = PaginationInfo(
            page=paginated_sessions.pagination.page,
            page_size=paginated_sessions.pagination.page_size,
            total_pages=paginated_sessions.pagination.total_pages,
            total_items=paginated_sessions.pagination.total_items
        )
        
        return SessionsListResponse(
            sessions=session_summaries,
            pagination=api_pagination,
            filters_applied=paginated_sessions.filters_applied
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve sessions: {str(e)}"
        )

@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetailResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Get Session Details with Timeline",
    description="""
    Retrieve detailed information for a specific alert processing session.
    
    **Response includes:**
    - Complete session metadata and processing details
    - Chronological timeline of all LLM interactions and MCP communications
    - Full audit trail with microsecond-precision timing
    
    **Timestamp Format:**
    - All timestamps are Unix timestamps in microseconds since epoch (UTC)
    """
)

async def get_session_detail(
    session_id: str = Path(..., description="Unique session identifier"),
    history_service: HistoryService = Depends(get_history_service)
) -> SessionDetailResponse:
    """
    Get detailed session information with chronological timeline.
    
    Args:
        session_id: Unique session identifier
        history_service: Injected history service
        
    Returns:
        SessionDetailResponse containing complete session details and timeline
        
    Raises:
        HTTPException: 404 if session not found, 500 for internal errors
    """
    try:
        # Phase 4: Use internal service method that returns type-safe DetailedSession model
        detailed_session = history_service.get_session_timeline(session_id)
        
        if not detailed_session:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )
        
        # Get session summary statistics using type-safe method
        session_stats = await history_service.get_session_summary(session_id)
        if not session_stats:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to calculate summary statistics for session {session_id}"
            )
        
        # Phase 4.2: Convert DetailedSession to API response model for compatibility
        # Convert stages to API StageExecution format
        stage_executions = []
        for detailed_stage in detailed_session.stages:
            # Build chronological timeline for this stage from its interactions
            stage_timeline = []
            all_stage_interactions = detailed_stage.llm_interactions + detailed_stage.mcp_communications
            # Sort by timestamp
            all_stage_interactions.sort(key=lambda x: x.timestamp_us)
            
            for interaction in all_stage_interactions:
                # Validate event_id is present - no fallbacks
                if not interaction.event_id:
                    raise ValueError(f"Missing required event_id for interaction: {interaction}")
                
                # Validate event type - fail fast on unknown types
                if interaction.type not in VALID_EVENT_TYPES:
                    raise ValueError(f"Unknown interaction type: {interaction.type}. Expected one of: {VALID_EVENT_TYPES}")
                
                stage_timeline.append({
                    'event_id': interaction.event_id,
                    'type': interaction.type,
                    'timestamp_us': interaction.timestamp_us,
                    'step_description': interaction.step_description,
                    'duration_ms': interaction.duration_ms,
                    'details': interaction.details.model_dump()
                })
            
            # Create interaction summary from stage data
            interaction_summary = InteractionSummary(
                llm_count=detailed_stage.llm_interaction_count,
                mcp_count=detailed_stage.mcp_communication_count,
                total_count=detailed_stage.total_interactions,
                duration_ms=detailed_stage.stage_interactions_duration_ms
            )
            
            stage_execution = StageExecution(
                execution_id=detailed_stage.execution_id,
                stage_id=detailed_stage.stage_id,
                stage_index=detailed_stage.stage_index,
                stage_name=detailed_stage.stage_name,
                agent=detailed_stage.agent,
                iteration_strategy=None,  # Not currently tracked in DetailedStage
                status=detailed_stage.status,
                started_at_us=detailed_stage.started_at_us,
                completed_at_us=detailed_stage.completed_at_us,
                duration_ms=detailed_stage.duration_ms,
                stage_output=detailed_stage.stage_output,
                error_message=detailed_stage.error_message,
                timeline=stage_timeline,
                interaction_summary=interaction_summary
            )
            stage_executions.append(stage_execution)
        
        # Create chain execution from detailed session
        chain_execution = ChainExecution(
            chain_id=detailed_session.chain_id,
            chain_definition=detailed_session.chain_definition,
            current_stage_index=detailed_session.current_stage_index,
            current_stage_id=detailed_session.current_stage_id,
            stages=stage_executions
        )
        
        return SessionDetailResponse(
            session_id=detailed_session.session_id,
            alert_id=detailed_session.alert_id,
            alert_data=detailed_session.alert_data,
            agent_type=detailed_session.agent_type,
            alert_type=detailed_session.alert_type,
            status=detailed_session.status.value,  # Convert enum to string
            started_at_us=detailed_session.started_at_us,
            completed_at_us=detailed_session.completed_at_us,
            error_message=detailed_session.error_message,
            final_analysis=detailed_session.final_analysis,
            duration_ms=detailed_session.duration_ms,  # Use the property
            session_metadata=detailed_session.session_metadata or {},
            chain_execution=chain_execution,
            summary=session_stats.model_dump()  # Convert SessionStats to dict
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve session details: {str(e)}"
        )

@router.get(
    "/sessions/{session_id}/summary",
    response_model=Dict[str, Any],
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Get Session Summary Statistics",
    description="""
    Retrieve just the summary statistics for a session (lightweight).
    
    Returns updated counts for LLM interactions, MCP communications, 
    total interactions, errors, and chain progress without fetching 
    the full session timeline.
    """
)
async def get_session_summary(
    session_id: str = Path(..., description="Unique session identifier"),
    history_service: HistoryService = Depends(get_history_service)
) -> Dict[str, Any]:
    """Get summary statistics for a specific session (lightweight)."""
    try:
        logger.info(f"Fetching summary statistics for session {session_id}")
        
        # Phase 4: Use internal service method that returns type-safe SessionStats model
        session_stats = await history_service.get_session_summary(session_id)
        
        if session_stats is None:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )
        
        # Phase 4.2: Convert SessionStats to dict for API response compatibility
        summary_dict = session_stats.model_dump()
        
        logger.info(f"Summary statistics calculated for session {session_id}: {summary_dict}")
        return summary_dict
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session summary for {session_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve session summary: {str(e)}"
        )

@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="History Service Health Check",
    description="""
    Check the health status of the history service.
    
    **Status Values:**
    - `healthy`: Service is operational and database is accessible
    - `unhealthy`: Service has issues (e.g., database connection failed)
    - `disabled`: Service is disabled via configuration (HISTORY_ENABLED=false)
    
    **Timestamp Format:**
    - All timestamps are Unix timestamps in microseconds since epoch (UTC)
    """
)

async def health_check(
    history_service: HistoryService = Depends(get_history_service)
) -> HealthCheckResponse:
    """
    Perform history service health check.
    
    Args:
        history_service: Injected history service
        
    Returns:
        HealthCheckResponse containing service health status and details
    """
    try:
        # Check if history service is enabled
        if not history_service.enabled:
            return HealthCheckResponse(
                service="alert_processing_history",
                status="disabled",
                timestamp_us=now_us(),
                details={
                    "message": "History service is disabled via configuration",
                    "history_enabled": False
                }
            )
        
        # Test database connectivity
        test_result = history_service.test_database_connection()
        
        if test_result:
            return HealthCheckResponse(
                service="alert_processing_history",
                status="healthy",
                timestamp_us=now_us(),
                details={
                    "database_connection": "ok",
                    "history_enabled": True,
                    "database_url": history_service.settings.history_database_url.split('/')[-1]  # Just the DB name for security
                }
            )
        else:
            return HealthCheckResponse(
                service="alert_processing_history",
                status="unhealthy",
                timestamp_us=now_us(),
                details={
                    "database_connection": "failed",
                    "history_enabled": True,
                    "error": "Database connection test failed"
                }
            )
            
    except Exception as e:
        return HealthCheckResponse(
            service="alert_processing_history",
            status="unhealthy",
            timestamp_us=now_us(),
            details={
                "error": str(e),
                "message": "Health check failed with exception"
            }
        )

# Dashboard-specific endpoints for EP-0004 implementation

@router.get(
    "/active-sessions",
    summary="Active Sessions", 
    description="Get currently active/processing sessions"
)
async def get_active_sessions(
    history_service: HistoryService = Depends(get_history_service)
):
    """Get list of currently active sessions."""
    try:
        active_sessions = history_service.get_active_sessions()
        # Convert to the format expected by the frontend
        return [
            {
                "session_id": session.session_id,
                "alert_id": session.alert_id,
                "agent_type": session.agent_type,
                "alert_type": session.alert_type,
                "status": session.status,
                "started_at_us": session.started_at_us,
                "completed_at_us": session.completed_at_us,
                "error_message": session.error_message,
                "duration_seconds": (
                    (session.completed_at_us - session.started_at_us) / 1000000
                    if session.completed_at_us else 
                    (now_us() - session.started_at_us) / 1000000
                )
            }
            for session in active_sessions
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get active sessions: {str(e)}")

@router.get(
    "/filter-options",
    summary="Filter Options",
    description="Get available filter options for dashboard filtering"
)
async def get_filter_options(
    history_service: HistoryService = Depends(get_history_service)
):
    """Get available filter options for the dashboard."""
    try:
        # Phase 4: Use internal service method that returns type-safe FilterOptions model
        filter_options = history_service.get_filter_options()
        
        # Phase 4.2: Convert FilterOptions to dict for API response compatibility  
        return filter_options.model_dump()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get filter options: {str(e)}")

# Note: Exception handlers should be registered at the app level in main.py 