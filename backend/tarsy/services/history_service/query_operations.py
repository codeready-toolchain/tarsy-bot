"""Session query operations."""

import logging
from typing import Any, Dict, List, Optional

from tarsy.models.db_models import AlertSession
from tarsy.models.history_models import DetailedSession, FilterOptions, PaginatedSessions
from tarsy.services.history_service.base_infrastructure import BaseHistoryInfra

logger = logging.getLogger(__name__)


class QueryOperations:
    """Session query and filtering operations."""
    
    def __init__(self, infra: BaseHistoryInfra):
        self._infra = infra
    
    def get_sessions_list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None
    ) -> Optional[PaginatedSessions]:
        """Retrieve alert sessions with filtering and pagination."""
        with self._infra.get_repository() as repo:
            if not repo:
                raise RuntimeError("History repository unavailable - cannot retrieve sessions list")
            
            filters = filters or {}
            
            paginated_sessions = repo.get_alert_sessions(
                status=filters.get('status'),
                agent_type=filters.get('agent_type'),
                alert_type=filters.get('alert_type'),
                search=filters.get('search'),
                start_date_us=filters.get('start_date_us'),
                end_date_us=filters.get('end_date_us'),
                page=page,
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order
            )
            
            if paginated_sessions and filters:
                paginated_sessions.filters_applied = filters
            
            return paginated_sessions

    def test_database_connection(self) -> bool:
        """Test database connectivity."""
        try:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot check health")
                repo.get_alert_sessions(page=1, page_size=1)
                return True
                
        except Exception as e:
            logger.error(f"Database connection test failed: {str(e)}")
            return False

    def get_session_details(self, session_id: str) -> Optional[DetailedSession]:
        """Get complete session details including timeline and interactions."""
        try:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot retrieve session details")
                
                detailed_session = repo.get_session_details(session_id)
                return detailed_session
                
        except Exception as e:
            logger.error(f"Failed to get session details for {session_id}: {str(e)}")
            return None
    
    def get_active_sessions(self) -> List[AlertSession]:
        """Get all currently active sessions."""
        with self._infra.get_repository() as repo:
            if not repo:
                raise RuntimeError("History repository unavailable - cannot retrieve active sessions")
            
            return repo.get_active_sessions()

    def get_filter_options(self) -> FilterOptions:
        """Get available filter options for the dashboard."""
        with self._infra.get_repository() as repo:
            if not repo:
                raise RuntimeError("History repository unavailable - cannot retrieve filter options")
            
            return repo.get_filter_options()
