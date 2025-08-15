"""
Session conversion utilities.

Provides converters for transforming AlertSession SQLModel objects and repository
responses into the new type-safe history models where format differences exist.
"""

from typing import Dict, List, Any, Optional

from tarsy.models.history import AlertSession
from tarsy.models.history_models import SessionOverview, PaginatedSessions, PaginationInfo
from tarsy.models.constants import AlertSessionStatus


def alert_session_to_session_overview(
    session: AlertSession,
    interaction_counts: Optional[Dict[str, int]] = None
) -> SessionOverview:
    """
    Convert AlertSession SQLModel to SessionOverview.
    
    Merges interaction counts from separate repository query results into 
    the session overview for dashboard display.
    
    Args:
        session: AlertSession SQLModel instance
        interaction_counts: Optional counts dict with 'llm_interactions', 'mcp_communications'
    
    Returns:
        SessionOverview instance with merged interaction counts
    """
    # Extract interaction counts with defaults
    counts = interaction_counts or {}
    llm_count = counts.get('llm_interactions', 0)
    mcp_count = counts.get('mcp_communications', 0)
    
    return SessionOverview(
        # Core identification
        session_id=session.session_id,
        alert_id=session.alert_id,
        alert_type=session.alert_type,
        agent_type=session.agent_type,
        status=AlertSessionStatus(session.status),  # Convert string to enum
        
        # Timing info
        started_at_us=session.started_at_us,
        completed_at_us=session.completed_at_us,
        
        # Basic status info
        error_message=session.error_message,
        
        # Summary counts (merged from interaction_counts)
        llm_interaction_count=llm_count,
        mcp_communication_count=mcp_count,
        total_interactions=llm_count + mcp_count,
        
        # Chain progress info
        chain_id=session.chain_id,
        current_stage_index=session.current_stage_index,
        
        # Optional fields that may need calculation elsewhere
        total_stages=None,  # Will be populated by service layer if needed
        completed_stages=None,  # Will be populated by service layer if needed
        failed_stages=0  # Default, will be populated by service layer if needed
    )


def sessions_list_to_paginated_sessions(
    repository_response: Dict[str, Any]
) -> PaginatedSessions:
    """
    Convert repository get_alert_sessions() response to PaginatedSessions.
    
    Transforms the repository dict response containing AlertSession objects
    and separate interaction counts into the unified PaginatedSessions model.
    
    Args:
        repository_response: Dict from repository get_alert_sessions() with:
            - sessions: List[AlertSession]
            - interaction_counts: Dict[session_id, Dict[str, int]]
            - pagination: Dict[str, int]
    
    Returns:
        PaginatedSessions instance with converted SessionOverview objects
    """
    # Extract components from repository response
    sessions = repository_response.get('sessions', [])
    interaction_counts = repository_response.get('interaction_counts', {})
    pagination_data = repository_response.get('pagination', {})
    
    # Convert sessions to SessionOverview objects
    session_overviews = []
    for session in sessions:
        # Get interaction counts for this specific session
        session_counts = interaction_counts.get(session.session_id, {})
        
        # Convert to SessionOverview
        overview = alert_session_to_session_overview(session, session_counts)
        session_overviews.append(overview)
    
    # Convert pagination data
    pagination = PaginationInfo(
        page=pagination_data.get('page', 1),
        page_size=pagination_data.get('page_size', 20),
        total_pages=pagination_data.get('total_pages', 0),
        total_items=pagination_data.get('total_items', 0)
    )
    
    return PaginatedSessions(
        sessions=session_overviews,
        pagination=pagination,
        filters_applied={}  # TODO: Extract from original request if needed
    )
