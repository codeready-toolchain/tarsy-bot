"""
History Controller

FastAPI controller for alert processing history endpoints.
Provides REST API for querying historical data with filtering, pagination,
and chronological timeline reconstruction.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

import asyncio
import logging
from typing import Annotated, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query

from tarsy.utils.logger import get_logger
from tarsy.models.history_models import (
    DetailedSession,
    PaginatedSessions,
    SessionStats,
    FilterOptions,
    FinalAnalysisResponse,
)
from tarsy.models.api_models import ErrorResponse
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
    *,
    status: Optional[List[str]] = Query(None, description="Filter by session status(es) - supports multiple values"),
    agent_type: Optional[str] = Query(None, description="Filter by agent type"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    search: Optional[str] = Query(None, description="Text search across alert messages, error messages, and analysis results", min_length=3),
    start_date_us: Optional[int] = Query(None, description="Filter sessions started after this timestamp (microseconds since epoch UTC)"),
    end_date_us: Optional[int] = Query(None, description="Filter sessions started before this timestamp (microseconds since epoch UTC)"),
    page: int = Query(1, ge=1, description="Page number for pagination"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (1-100)"),
    sort_by: Optional[str] = Query(None, description="Field to sort by. Supported: 'started_at_us', 'status', 'alert_type', 'agent_type', 'author', 'duration_ms'. Unsupported values fall back to default ordering."),
    sort_order: Optional[str] = Query(None, description="Sort order: 'asc' or 'desc'"),
    history_service: Annotated[HistoryService, Depends(get_history_service)]
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
        sort_by: Field to sort by. Supported: 'started_at_us', 'status', 'alert_type', 
            'agent_type', 'author', 'duration_ms'. Unsupported values fall back to default 
            ordering by 'started_at_us' descending.
        sort_order: Sort order 'asc' or 'desc' (defaults to 'desc')
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
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order
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
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve sessions: {str(e)}"
        ) from e

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
    *,
    session_id: str = Path(..., description="Unique session identifier"),
    history_service: Annotated[HistoryService, Depends(get_history_service)]
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
        ) from e

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
    *,
    session_id: str = Path(..., description="Unique session identifier"),
    history_service: Annotated[HistoryService, Depends(get_history_service)]
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
        ) from e

@router.get(
    "/sessions/{session_id}/final-analysis",
    response_model=FinalAnalysisResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Session not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    },
    summary="Get Session Final Analysis",
    description="""
    Retrieve the final analysis content for an alert processing session.
    
    **Response behavior:**
    - Returns session status and final_analysis field (null if not available)
    - Completed sessions with analysis: final_analysis contains markdown content
    - Completed sessions without analysis: final_analysis is null
    - Non-completed sessions (pending, in_progress, etc.): final_analysis is null
    - Failed/cancelled sessions: final_analysis is null
    
    **Response includes:**
    - Final analysis content in markdown format (or null)
    - Current session status
    - Timestamp of the response
    """
)
async def get_session_final_analysis(
    *,
    session_id: str = Path(..., description="Unique session identifier"),
    history_service: Annotated[HistoryService, Depends(get_history_service)]
) -> FinalAnalysisResponse:
    """
    Get final analysis content for any session.
    
    Args:
        session_id: Unique session identifier
        history_service: Injected history service
        
    Returns:
        FinalAnalysisResponse containing the analysis content (or null) and session status
        
    Raises:
        HTTPException: 404 if session not found, 500 for internal errors
    """
    try:
        from tarsy.models.constants import AlertSessionStatus
        
        # Get the session
        session = history_service.get_session(session_id)
        
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Session {session_id} not found"
            )
        
        # Always return response with current status and final_analysis (or null)
        return FinalAnalysisResponse(
            final_analysis=session.final_analysis,  # Will be None if not available
            session_id=session_id,
            status=AlertSessionStatus(session.status)
        )
        
    except HTTPException:
        raise
    except RuntimeError as e:
        # Database unavailable - return 503
        raise HTTPException(
            status_code=503,
            detail=f"History service unavailable: {str(e)}"
        ) from e
    except Exception as e:
        logger.error(f"Failed to get final analysis for session {session_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve final analysis: {str(e)}"
        ) from e


# Dashboard-specific endpoints for EP-0004 implementation

@router.get(
    "/active-sessions",
    summary="Active Sessions", 
    description="Get currently active/processing sessions"
)
async def get_active_sessions(
    history_service: Annotated[HistoryService, Depends(get_history_service)]
):
    """Get list of currently active sessions."""
    try:
        active_sessions = history_service.get_active_sessions()
        # Convert to the format expected by the frontend
        return [
            {
                "session_id": session.session_id,
                "agent_type": session.agent_type,
                "alert_type": session.alert_type,
                "status": session.status,
                "started_at_us": session.started_at_us,
                "completed_at_us": session.completed_at_us,
                "error_message": session.error_message,
                "pause_metadata": session.pause_metadata,
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
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get active sessions: {str(e)}") from e

@router.get(
    "/filter-options",
    response_model=FilterOptions,
    summary="Filter Options",
    description="Get available filter options for dashboard filtering"
)
async def get_filter_options(
    history_service: Annotated[HistoryService, Depends(get_history_service)]
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
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get filter options: {str(e)}") from e


async def check_cancellation_completion(
    session_id: str,
    history_service: HistoryService,
    timeout_seconds: int = 300
) -> None:
    """
    Periodically check if cancellation completed, mark as orphaned if timeout reached.
    
    This runs as a background task after cancel_session returns.
    It checks every 10 seconds to see if the owning pod cancelled the task.
    If status is still CANCELING after timeout, marks as orphaned.
    
    Args:
        session_id: Session to check
        history_service: History service for database access
        timeout_seconds: How long to wait before declaring orphaned
    """
    from tarsy.models.constants import AlertSessionStatus
    from tarsy.services.events.event_helpers import publish_session_cancelled
    
    logger.info(f"Starting orphan detection for session {session_id} (timeout: {timeout_seconds}s)")
    
    check_interval = 10  # Check every 10 seconds
    elapsed = 0
    
    while elapsed < timeout_seconds:
        # Wait for check interval
        await asyncio.sleep(check_interval)
        elapsed += check_interval
        
        # Check current session status
        session = history_service.get_session(session_id)
        
        if not session:
            logger.warning(f"Session {session_id} not found during orphan detection")
            return
        
        # If no longer CANCELING, cancellation completed (or failed naturally)
        if session.status != AlertSessionStatus.CANCELING.value:
            logger.info(
                f"Session {session_id} cancellation completed after {elapsed}s: {session.status}"
            )
            return  # Exit background task early
        
        # Still CANCELING, continue waiting
        logger.debug(f"Session {session_id} still CANCELING after {elapsed}s, checking again...")
    
    # Timeout reached and still CANCELING - mark as orphaned
    session = history_service.get_session(session_id)
    
    if not session:
        logger.warning(f"Session {session_id} not found after timeout")
        return
    
    # Double-check still CANCELING (could have changed in final interval)
    if session.status == AlertSessionStatus.CANCELING.value:
        logger.warning(
            f"Session {session_id} still CANCELING after {timeout_seconds}s - "
            f"marking as orphaned and cancelled"
        )
        
        # Update to CANCELLED with orphan message
        history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.CANCELLED.value,
            error_message="Session cancelled (no response from processing pod - likely orphaned)"
        )
        
        # Publish cancellation event for UI
        await publish_session_cancelled(session_id)
        logger.info(f"Orphaned session {session_id} marked as cancelled")
    else:
        # Status changed in the final interval
        logger.info(
            f"Session {session_id} status changed to {session.status} just before timeout"
        )


@router.post(
    "/sessions/{session_id}/cancel",
    summary="Cancel Session",
    description="Cancel an active alert processing session"
)
async def cancel_session(
    *,
    session_id: str = Path(..., description="Session ID to cancel"),
    background_tasks: BackgroundTasks,
    history_service: Annotated[HistoryService, Depends(get_history_service)]
) -> dict:
    """
    Cancel an active session.
    
    For active sessions (with recent activity), this publishes a cancellation request
    to all backend pods. The pod owning the task will cancel it.
    
    For orphaned sessions (no recent activity), a background task monitors the
    cancellation and marks the session as cancelled if no pod responds.
    
    Args:
        session_id: Session identifier
        background_tasks: FastAPI background tasks
        history_service: Injected history service
        
    Returns:
        Success response with cancellation status
        
    Raises:
        HTTPException: 404 if session not found, 400 if already terminal
    """
    from tarsy.config.settings import get_settings
    from tarsy.models.constants import AlertSessionStatus
    from tarsy.services.events.event_helpers import publish_cancel_request
    
    # Step 1: Validate session exists
    session = history_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    # Step 2: Atomically update status to CANCELING
    success, current_status = history_service.update_session_to_canceling(session_id)
    
    if not success:
        if current_status in AlertSessionStatus.terminal_values():
            raise HTTPException(
                status_code=400,
                detail=f"Session already {current_status}, cannot cancel"
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to update session status")
    
    # If already CANCELING, this is idempotent - continue normally
    
    # Step 3: Publish cancellation request
    await publish_cancel_request(session_id)
    logger.info(f"Published cancellation request for session {session_id}")
    
    # Step 4: Start orphan detection background task
    settings = get_settings()
    # Use LLM iteration timeout + buffer for orphan detection
    # This is the maximum time a single iteration can take, which is what
    # we need to wait for during cancellation (not the full session timeout)
    orphan_timeout = settings.llm_iteration_timeout + 60  # Add 60s buffer
    
    background_tasks.add_task(
        check_cancellation_completion,
        session_id,
        history_service,
        timeout_seconds=orphan_timeout
    )
    
    # Step 5: Return success immediately
    return {
        "success": True,
        "message": "Cancellation request sent",
        "status": "canceling"
    }


@router.post(
    "/sessions/{session_id}/resume",
    summary="Resume Paused Session",
    description="Resume a paused alert processing session"
)
async def resume_session(
    *,
    session_id: str = Path(..., description="Session ID to resume"),
    background_tasks: BackgroundTasks,
    history_service: Annotated[HistoryService, Depends(get_history_service)]
) -> dict:
    """
    Resume a paused session.
    
    Validates the session is paused and triggers resume processing in background.
    
    Args:
        session_id: Session identifier
        background_tasks: FastAPI background tasks
        history_service: Injected history service
        
    Returns:
        Success response with resume status
        
    Raises:
        HTTPException: 404 if session not found, 400 if not paused
    """
    from tarsy.models.constants import AlertSessionStatus
    from tarsy.services.alert_service import get_alert_service
    
    # Step 1: Validate session exists
    session = history_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    
    # Step 2: Validate session is paused
    if session.status != AlertSessionStatus.PAUSED.value:
        raise HTTPException(
            status_code=400,
            detail=f"Session is not paused (status: {session.status})"
        )
    
    # Step 3: Trigger resume in background
    alert_service = get_alert_service()
    if not alert_service:
        raise HTTPException(status_code=500, detail="Alert service not available")
    
    async def resume_session_background():
        """Background task to resume session processing."""
        try:
            logger.info(f"Starting background resume for session {session_id}")
            await alert_service.resume_paused_session(session_id)
            logger.info(f"Successfully resumed session {session_id}")
        except Exception as e:
            logger.error(f"Failed to resume session {session_id}: {str(e)}", exc_info=True)
    
    background_tasks.add_task(resume_session_background)
    
    # Step 4: Return success immediately
    return {
        "success": True,
        "message": "Session resume initiated",
        "status": "resuming"
    }


# Note: Exception handlers should be registered at the app level in main.py 