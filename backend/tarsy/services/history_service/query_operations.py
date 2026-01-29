"""Session query operations."""

import logging
from typing import Any, Dict, List, Optional

from tarsy.models.db_models import AlertSession
from tarsy.models.history_models import DetailedSession, FilterOptions, PaginatedSessions
from tarsy.services.history_service.base_infrastructure import BaseHistoryInfra

logger = logging.getLogger(__name__)


class QueryOperations:
    """Session query and filtering operations."""
    
    def __init__(self, infra: BaseHistoryInfra) -> None:
        self._infra: BaseHistoryInfra = infra
    
    def get_sessions_list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None
    ) -> Optional[PaginatedSessions]:
        """Retrieve alert sessions with filtering and pagination.
        
        Args:
            filters: Optional dictionary of filter criteria. Supported keys:
                status, agent_type, alert_type, search, start_date_us, end_date_us.
            page: Page number for pagination (1-indexed). Defaults to 1.
            page_size: Number of results per page. Defaults to 20.
            sort_by: Field name to sort by.
            sort_order: Sort direction, either 'asc' or 'desc'.
        
        Returns:
            PaginatedSessions containing the results and pagination metadata,
            or None if the operation fails.
        """
        def _get_sessions_operation() -> Optional[PaginatedSessions]:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot retrieve sessions list")
                
                filters_local = filters or {}
                
                paginated_sessions = repo.get_alert_sessions(
                    status=filters_local.get('status'),
                    agent_type=filters_local.get('agent_type'),
                    alert_type=filters_local.get('alert_type'),
                    search=filters_local.get('search'),
                    start_date_us=filters_local.get('start_date_us'),
                    end_date_us=filters_local.get('end_date_us'),
                    page=page,
                    page_size=page_size,
                    sort_by=sort_by,
                    sort_order=sort_order
                )
                
                if paginated_sessions and filters_local:
                    paginated_sessions.filters_applied = filters_local
                
                return paginated_sessions
        
        return self._infra._retry_database_operation(
            "get_sessions_list",
            _get_sessions_operation,
            treat_none_as_success=True
        )

    def test_database_connection(self) -> bool:
        """Test database connectivity.
        
        Performs a simple query to verify the database connection is working.
        
        Returns:
            True if the database connection is healthy, False otherwise.
        """
        def _test_connection_operation() -> bool:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot check health")
                result = repo.get_alert_sessions(page=1, page_size=1)
                if result is None:
                    raise RuntimeError("Database query failed - health check unsuccessful")
                return True
        
        result = self._infra._retry_database_operation(
            "test_database_connection",
            _test_connection_operation
        )
        return result or False

    def get_session_details(self, session_id: str) -> Optional[DetailedSession]:
        """Get complete session details including timeline and interactions.
        
        Args:
            session_id: Unique identifier of the session.
        
        Returns:
            DetailedSession with full timeline and interaction data,
            or None if the session is not found.
        """
        def _get_session_details_operation() -> Optional[DetailedSession]:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot retrieve session details")
                
                return repo.get_session_details(session_id)
        
        return self._infra._retry_database_operation(
            "get_session_details",
            _get_session_details_operation,
            treat_none_as_success=True
        )
    
    def get_active_sessions(self) -> List[AlertSession]:
        """Get all currently active sessions.
        
        Returns:
            List of AlertSession records that are currently in progress,
            empty list if none are active.
        """
        def _get_active_sessions_operation() -> List[AlertSession]:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot retrieve active sessions")
                
                return repo.get_active_sessions()
        
        return self._infra._retry_database_operation(
            "get_active_sessions",
            _get_active_sessions_operation
        ) or []

    def get_filter_options(self) -> Optional[FilterOptions]:
        """Get available filter options for the dashboard.
        
        Retrieves distinct values for filterable fields to populate
        filter dropdowns in the UI.
        
        Returns:
            FilterOptions containing available filter values,
            or None if the operation fails.
        """
        def _get_filter_options_operation() -> FilterOptions:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot retrieve filter options")
                
                return repo.get_filter_options()
        
        return self._infra._retry_database_operation(
            "get_filter_options",
            _get_filter_options_operation
        )
