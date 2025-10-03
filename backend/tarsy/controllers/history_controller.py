"""
History Controller

FastAPI controller for alert processing history endpoints.
Provides REST API for querying historical data with filtering, pagination,
and chronological timeline reconstruction.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from tarsy.utils.logger import get_logger
from tarsy.models.history_models import (
    DetailedSession,
    PaginatedSessions,
    SessionStats,
    FilterOptions,
)
from tarsy.models.api_models import (
    ErrorResponse,
    HealthCheckResponse,
)
from tarsy.utils.timestamp import now_us
from tarsy.services.history_service import HistoryService, get_history_service

migration_logger = logging.getLogger(__name__)

# Initialize logger
logger = get_logger(__name__)

# Valid event types expected from the repository
VALID_EVENT_TYPES = {'llm', 'mcp', 'system'}

router = APIRouter(prefix="/api/v1/history", tags=["history"])

@router.get(
    "/sessions", 
    response_model=PaginatedSessions,
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
) -> PaginatedSessions:
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
        
        paginated_sessions = history_service.get_sessions_list(
            filters=filters,
            page=page,
            page_size=page_size
        )
        
        if not paginated_sessions:
            # Return empty response if no data available  
            from tarsy.models.history_models import PaginationInfo
            return PaginatedSessions(
                sessions=[],
                pagination=PaginationInfo(
                    page=page,
                    page_size=page_size,
                    total_pages=0,
                    total_items=0
                ),
                filters_applied=filters
            )
        
        return paginated_sessions
        
    except HTTPException:
        raise
    except RuntimeError as e:
        # Database unavailable - return 503
        raise HTTPException(
            status_code=503,
            detail=f"History service unavailable: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve sessions: {str(e)}"
        )

@router.get(
    "/sessions/{session_id}",
    response_model=DetailedSession,
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
) -> DetailedSession:
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
        detailed_session = history_service.get_session_details(session_id)
        
        if not detailed_session:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )
        return detailed_session
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve session details: {str(e)}"
        )

@router.get(
    "/sessions/{session_id}/summary",
    response_model=SessionStats,
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
) -> SessionStats:
    """Get summary statistics for a specific session (lightweight)."""
    try:
        logger.info(f"Fetching summary statistics for session {session_id}")
        session_stats = await history_service.get_session_summary(session_id)
        
        if session_stats is None:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )
        
        logger.info(f"Summary statistics calculated for session {session_id}")
        return session_stats
        
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
        if not history_service.is_enabled:
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
        
        # Get migration status (import here to avoid circular imports)
        from tarsy.database.migrations import get_current_version, get_pending_migrations
        
        migration_status = {}
        try:
            if history_service.settings.database_url:
                current_version = get_current_version(history_service.settings.database_url)
                pending = get_pending_migrations(history_service.settings.database_url)
                migration_status = {
                    "schema_version": current_version,
                    "pending_migrations": pending
                }
        except Exception as e:
            migration_logger.warning(f"Failed to retrieve migration status in health check: {e}")
            migration_status = {
                "schema_version": None,
                "pending_migrations": [],
                "migration_status_error": str(e)
            }
        
        if test_result:
            return HealthCheckResponse(
                service="alert_processing_history",
                status="healthy",
                timestamp_us=now_us(),
                details={
                    "database_connection": "ok",
                    "history_enabled": True,
                    "database_url": history_service.settings.database_url.split('/')[-1],  # Just the DB name for security
                    **migration_status
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
                    "error": "Database connection test failed",
                    **migration_status
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
    except RuntimeError as e:
        # Database unavailable - return 503
        raise HTTPException(
            status_code=503, 
            detail=f"History service unavailable: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get active sessions: {str(e)}")

@router.get(
    "/filter-options",
    response_model=FilterOptions,
    summary="Filter Options",
    description="Get available filter options for dashboard filtering"
)
async def get_filter_options(
    history_service: HistoryService = Depends(get_history_service)
):
    """Get available filter options for the dashboard."""
    try:
        filter_options = history_service.get_filter_options()
        return filter_options
        
    except RuntimeError as e:
        # Database unavailable - return 503
        raise HTTPException(
            status_code=503, 
            detail=f"History service unavailable: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get filter options: {str(e)}")

# Note: Exception handlers should be registered at the app level in main.py 