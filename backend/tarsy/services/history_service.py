"""
History Service for Alert Processing Audit Trail.

Provides centralized management of alert processing history including session
lifecycle, LLM interaction tracking, MCP communication logging, and timeline
reconstruction with graceful degradation when database is unavailable.
"""

import logging
import random
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from tarsy.config.settings import get_settings
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.history import AlertSession, LLMInteraction, MCPCommunication, now_us
from tarsy.repositories.base_repository import DatabaseManager
from tarsy.repositories.history_repository import HistoryRepository

logger = logging.getLogger(__name__)


class HistoryService:
    """
    Core service for managing alert processing history.
    
    Provides high-level operations for session management, interaction logging,
    and timeline reconstruction with integrated error handling and graceful
    degradation when database operations fail.
    """
    
    def __init__(self):
        """Initialize history service with configuration."""
        self.settings = get_settings()
        self.db_manager: Optional[DatabaseManager] = None
        self.is_enabled = self.settings.history_enabled
        self._initialization_attempted = False
        self._is_healthy = False
        
        # Retry configuration for database operations
        self.max_retries = 3
        self.base_delay = 0.1  # 100ms base delay
        self.max_delay = 2.0   # 2 second max delay
    
    def _retry_database_operation(self, operation_name: str, operation_func):
        """
        Retry database operations with exponential backoff for transient failures.
        
        Args:
            operation_name: Name of the operation for logging
            operation_func: Function to retry
        
        Returns:
            Result of the operation, or None if all retries failed
        """
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                result = operation_func()
                if result is not None:
                    return result
                # If result is None, log and continue to retry
                logger.warning(f"Database operation '{operation_name}' returned None on attempt {attempt + 1}")
                
            except Exception as e:
                last_exception = e
                error_msg = str(e).lower()
                
                # Check if this is a retryable database error
                is_retryable = any(keyword in error_msg for keyword in [
                    'database is locked',
                    'database disk image is malformed', 
                    'sqlite3.operationalerror',
                    'connection timeout',
                    'database table is locked',
                    'connection pool',
                    'connection closed'
                ])
                
                # For session creation, check if it might have succeeded despite the error
                if operation_name == "create_session" and attempt > 0:
                    # Don't retry if we might have created a duplicate
                    logger.warning(f"Not retrying session creation after database error to prevent duplicates: {str(e)}")
                    return None
                
                if not is_retryable or attempt == self.max_retries:
                    logger.error(f"Database operation '{operation_name}' failed after {attempt + 1} attempts: {str(e)}")
                    return None
                
                # Exponential backoff with jitter
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                jitter = random.uniform(0, delay * 0.1)  # Add up to 10% jitter
                total_delay = delay + jitter
                
                logger.warning(f"Database operation '{operation_name}' failed on attempt {attempt + 1}, retrying in {total_delay:.2f}s: {str(e)}")
                time.sleep(total_delay)
        
        logger.error(f"Database operation '{operation_name}' failed after all retries. Last error: {str(last_exception)}")
        return None
    
    def initialize(self) -> bool:
        """
        Initialize database connection and schema.
        
        Returns:
            True if initialization successful, False otherwise
        """
        if not self.is_enabled:
            logger.info("History service disabled via configuration")
            return False
        
        if self._initialization_attempted:
            return self._is_healthy
            
        self._initialization_attempted = True
        
        try:
            self.db_manager = DatabaseManager(self.settings.history_database_url)
            self.db_manager.initialize()
            self.db_manager.create_tables()
            self._is_healthy = True
            logger.info("History service initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize history service: {str(e)}")
            logger.info("History service will operate in degraded mode (logging only)")
            self._is_healthy = False
            return False
    
    @contextmanager
    def get_repository(self):
        """
        Context manager for getting repository with error handling.
        
        Yields:
            HistoryRepository instance or None if unavailable
        """
        if not self.is_enabled or not self._is_healthy:
            yield None
            return
            
        session = None
        try:
            if not self.db_manager:
                yield None
                return
                
            session = self.db_manager.get_session()
            repository = HistoryRepository(session)
            yield repository
            
        except Exception as e:
            logger.error(f"History repository error: {str(e)}")
            if session:
                try:
                    session.rollback()
                except Exception:
                    pass
            yield None
            
        finally:
            if session:
                try:
                    session.close()
                except Exception as e:
                    logger.error(f"Error closing database session: {str(e)}")
    
    # Session Lifecycle Operations
    def create_session(
        self,
        alert_id: str,
        alert_data: Dict[str, Any],
        agent_type: str,
        alert_type: Optional[str] = None
    ) -> Optional[str]:
        """
        Create a new alert processing session with retry logic.
        
        Args:
            alert_id: External alert identifier
            alert_data: Original alert payload
            agent_type: Processing agent type (e.g., 'kubernetes', 'base')
            alert_type: Alert type for filtering (e.g., 'pod_crash', 'high_cpu')
            
        Returns:
            Session ID if created successfully, None if failed
        """
        if not self.is_enabled:
            logger.debug("History capture disabled - skipping session creation")
            return None
        
        def _create_session_operation():
            with self.get_repository() as repo:
                if not repo:
                    logger.warning("History repository unavailable - session not persisted")
                    return None
                
                session = AlertSession(
                    alert_id=alert_id,
                    alert_data=alert_data,
                    agent_type=agent_type,
                    alert_type=alert_type,
                    status=AlertSessionStatus.PENDING
                )
                
                created_session = repo.create_alert_session(session)
                if created_session:
                    logger.info(f"Created history session {created_session.session_id} for alert {alert_id}")
                    return created_session.session_id
                return None
        
        return self._retry_database_operation("create_session", _create_session_operation)
    
    def update_session_status(
        self,
        session_id: str,
        status: str,
        error_message: Optional[str] = None,
        final_analysis: Optional[str] = None
    ) -> bool:
        """
        Update session processing status with retry logic.
        
        Args:
            session_id: The session identifier
            status: New status (pending, in_progress, completed, failed)
            error_message: Error message if status is failed
            final_analysis: Final formatted analysis if status is completed
            
        Returns:
            True if updated successfully, False otherwise
        """
        if not self.is_enabled or not session_id:
            return False
        
        def _update_status_operation():
            with self.get_repository() as repo:
                if not repo:
                    logger.warning("History repository unavailable - status not updated")
                    return False
                
                session = repo.get_alert_session(session_id)
                if not session:
                    logger.warning(f"Session {session_id} not found for status update")
                    return False
                
                session.status = status
                if error_message:
                    session.error_message = error_message
                if final_analysis:
                    session.final_analysis = final_analysis
                if status in AlertSessionStatus.TERMINAL_STATUSES:
                    session.completed_at_us = now_us()
                
                success = repo.update_alert_session(session)
                if success:
                    logger.debug(f"Updated session {session_id} status to {status}")
                    
                    # Notify dashboard update service of session status change
                    try:
                        # Import here to avoid circular imports
                        from tarsy.main import websocket_manager
                        if websocket_manager and websocket_manager.dashboard_manager and websocket_manager.dashboard_manager.update_service:
                            # Prepare details for dashboard update
                            details = {}
                            if error_message:
                                details['error_message'] = error_message
                            if final_analysis:
                                details['final_analysis'] = final_analysis
                                
                            # Process session status change for dashboard updates
                            import asyncio
                            if asyncio.get_event_loop().is_running():
                                # If we're in an async context, create a task
                                asyncio.create_task(
                                    websocket_manager.dashboard_manager.update_service.process_session_status_change(
                                        session_id, status, details
                                    )
                                )
                            else:
                                # If not in async context, run directly
                                asyncio.run(
                                    websocket_manager.dashboard_manager.update_service.process_session_status_change(
                                        session_id, status, details
                                    )
                                )
                    except Exception as e:
                        logger.warning(f"Failed to notify dashboard update service: {e}")
                        
                return success
        
        result = self._retry_database_operation("update_session_status", _update_status_operation)
        return result if result is not None else False
    
    # LLM Interaction Logging
    def log_llm_interaction(
        self,
        session_id: str,
        prompt_text: str,
        response_text: str,
        model_used: str,
        step_description: str,
        tool_calls: Optional[Dict] = None,
        tool_results: Optional[Dict] = None,
        token_usage: Optional[Dict] = None,
        duration_ms: int = 0
    ) -> bool:
        """
        Log an LLM interaction with comprehensive details.
        
        Args:
            session_id: The session identifier
            prompt_text: Full prompt sent to LLM
            response_text: Complete response from LLM
            model_used: LLM model identifier
            step_description: Human-readable description of this step
            tool_calls: Tool calls made during interaction
            tool_results: Results from tool calls
            token_usage: Token usage statistics
            duration_ms: Interaction duration in milliseconds
            
        Returns:
            True if logged successfully, False otherwise
        """
        if not self.is_enabled or not session_id:
            return False
            
        try:
            with self.get_repository() as repo:
                if not repo:
                    logger.warning("History repository unavailable - LLM interaction not logged")
                    return False
                
                interaction = LLMInteraction(
                    session_id=session_id,
                    prompt_text=prompt_text,
                    response_text=response_text,
                    model_used=model_used,
                    step_description=step_description,
                    tool_calls=tool_calls,
                    tool_results=tool_results,
                    token_usage=token_usage,
                    duration_ms=duration_ms
                )
                
                repo.create_llm_interaction(interaction)
                logger.debug(f"Logged LLM interaction for session {session_id}: {step_description}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to log LLM interaction for session {session_id}: {str(e)}")
            return False
    
    # MCP Communication Logging
    def log_mcp_communication(
        self,
        session_id: str,
        server_name: str,
        communication_type: str,
        step_description: str,
        success: bool,
        duration_ms: int = 0,
        tool_name: Optional[str] = None,
        tool_arguments: Optional[Dict] = None,
        tool_result: Optional[Dict] = None,
        available_tools: Optional[Dict] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Log an MCP communication with comprehensive details.
        
        Args:
            session_id: The session identifier
            server_name: MCP server identifier
            communication_type: Type of communication (tool_list, tool_call, result)
            step_description: Human-readable description of this step
            success: Whether the communication was successful
            duration_ms: Communication duration in milliseconds
            tool_name: Name of the tool (for tool_call type)
            tool_arguments: Arguments passed to tool call
            tool_result: Result from tool call
            available_tools: List of available tools (for tool_list type)
            error_message: Error message if communication failed
            
        Returns:
            True if logged successfully, False otherwise
        """
        if not self.is_enabled or not session_id:
            return False
            
        try:
            with self.get_repository() as repo:
                if not repo:
                    logger.warning("History repository unavailable - MCP communication not logged")
                    return False
                
                communication = MCPCommunication(
                    session_id=session_id,
                    server_name=server_name,
                    communication_type=communication_type,
                    step_description=step_description,
                    success=success,
                    duration_ms=duration_ms,
                    tool_name=tool_name,
                    tool_arguments=tool_arguments,
                    tool_result=tool_result,
                    available_tools=available_tools,
                    error_message=error_message
                )
                
                repo.create_mcp_communication(communication)
                logger.debug(f"Logged MCP communication for session {session_id}: {step_description}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to log MCP communication for session {session_id}: {str(e)}")
            return False
    
    # Properties
    @property
    def enabled(self) -> bool:
        """Check if history service is enabled."""
        return self.is_enabled

    # Query Operations
    def get_sessions(
        self,
        status: Optional[str] = None,
        agent_type: Optional[str] = None,
        alert_type: Optional[str] = None,
        start_date_us: Optional[int] = None,
        end_date_us: Optional[int] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """
        Retrieve alert sessions with filtering and pagination.
        
        Args:
            status: Filter by processing status
            agent_type: Filter by agent type
            alert_type: Filter by alert type
            start_date_us: Filter sessions started after this Unix timestamp (microseconds)
            end_date_us: Filter sessions started before this Unix timestamp (microseconds)
            page: Page number for pagination
            page_size: Number of results per page
            
        Returns:
            Dictionary containing sessions and pagination info, empty if unavailable
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    return {"sessions": [], "pagination": {"page": 1, "page_size": 0, "total_pages": 0, "total_items": 0}}
                
                return repo.get_alert_sessions(
                    status=status,
                    agent_type=agent_type,
                    alert_type=alert_type,
                    start_date_us=start_date_us,
                    end_date_us=end_date_us,
                    page=page,
                    page_size=page_size
                )
                
        except Exception as e:
            logger.error(f"Failed to get sessions: {str(e)}")
            return {"sessions": [], "pagination": {"page": 1, "page_size": 0, "total_pages": 0, "total_items": 0}}

    def get_sessions_list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[List[AlertSession], int]:
        """
        Retrieve alert sessions with filtering and pagination (returns tuple for API).
        
        Args:
            filters: Dictionary of filters (status, agent_type, alert_type, start_date_us, end_date_us)
            page: Page number for pagination
            page_size: Number of results per page
            
        Returns:
            Tuple of (sessions_list, total_count), empty list if unavailable
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    return [], 0
                
                # Extract filters or use defaults
                filters = filters or {}
                
                result = repo.get_alert_sessions(
                    status=filters.get('status'),
                    agent_type=filters.get('agent_type'),
                    alert_type=filters.get('alert_type'),
                    search=filters.get('search'),
                    start_date_us=filters.get('start_date_us'),
                    end_date_us=filters.get('end_date_us'),
                    page=page,
                    page_size=page_size
                )
                
                sessions = result.get('sessions', [])
                interaction_counts = result.get('interaction_counts', {})
                total_items = result.get('pagination', {}).get('total_items', 0)
                
                # Add interaction counts as dynamic attributes to session objects
                for session in sessions:
                    counts = interaction_counts.get(session.session_id, {})
                    # Use object.__setattr__ to bypass SQLModel validation
                    object.__setattr__(session, 'llm_interaction_count', counts.get('llm_interactions', 0))
                    object.__setattr__(session, 'mcp_communication_count', counts.get('mcp_communications', 0))
                
                return sessions, total_items
                
        except Exception as e:
            logger.error(f"Failed to get sessions list: {str(e)}")
            return [], 0

    def test_database_connection(self) -> bool:
        """
        Test database connectivity.
        
        Returns:
            True if database connection is working, False otherwise
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    return False
                
                # Try to perform a simple database operation
                # This will test both connection and basic functionality
                repo.get_alert_sessions(page=1, page_size=1)
                return True
                
        except Exception as e:
            logger.error(f"Database connection test failed: {str(e)}")
            return False
    
    def get_session_timeline(self, session_id: str) -> Dict[str, Any]:
        """
        Get complete session timeline with chronological ordering.
        
        Args:
            session_id: The session identifier
            
        Returns:
            Dictionary containing session details and chronological timeline
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    return {}
                
                return repo.get_session_timeline(session_id)
                
        except Exception as e:
            logger.error(f"Failed to get session timeline for {session_id}: {str(e)}")
            return {}
    
    def get_active_sessions(self) -> List[AlertSession]:
        """
        Get all currently active sessions.
        
        Returns:
            List of active AlertSession instances
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    return []
                
                return repo.get_active_sessions()
                
        except Exception as e:
            logger.error(f"Failed to get active sessions: {str(e)}")
            return []
    
    def get_dashboard_metrics(self) -> Dict[str, Any]:
        """
        Get dashboard metrics including session counts and statistics.
        
        Returns:
            Dictionary containing dashboard metrics
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    return {
                        "active_sessions": 0,
                        "completed_sessions": 0,
                        "failed_sessions": 0,
                        "total_interactions": 0,
                        "avg_session_duration": 0.0,
                        "error_rate": 0.0,
                        "last_24h_sessions": 0
                    }
                
                return repo.get_dashboard_metrics()
                
        except Exception as e:
            logger.error(f"Failed to get dashboard metrics: {str(e)}")
            return {
                "active_sessions": 0,
                "completed_sessions": 0,
                "failed_sessions": 0,
                "total_interactions": 0,
                "avg_session_duration": 0.0,
                "error_rate": 0.0,
                "last_24h_sessions": 0
            }
    
    def get_filter_options(self) -> Dict[str, Any]:
        """
        Get available filter options for the dashboard.
        
        Returns:
            Dictionary containing filter options
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    return {
                        "agent_types": [],
                        "alert_types": [],
                        "status_options": AlertSessionStatus.ALL_STATUSES,
                        "time_ranges": [
                            {"label": "Last Hour", "value": "1h"},
                            {"label": "Last 4 Hours", "value": "4h"},
                            {"label": "Today", "value": "today"},
                            {"label": "This Week", "value": "week"}
                        ]
                    }
                
                return repo.get_filter_options()
                
        except Exception as e:
            logger.error(f"Failed to get filter options: {str(e)}")
            return {
                "agent_types": [],
                "alert_types": [],
                "status_options": AlertSessionStatus.ALL_STATUSES,
                "time_ranges": [
                    {"label": "Last Hour", "value": "1h"},
                    {"label": "Last 4 Hours", "value": "4h"},
                    {"label": "Today", "value": "today"},
                    {"label": "This Week", "value": "week"}
                ]
            }
    
    def export_session_data(self, session_id: str, format: str = 'json') -> Dict[str, Any]:
        """
        Export session data in the specified format.
        
        Args:
            session_id: The session ID to export
            format: Export format ('json' or 'csv')
            
        Returns:
            Dictionary containing export data and metadata
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    return {
                        "error": "Repository unavailable",
                        "session_id": session_id,
                        "format": format,
                        "data": None
                    }
                
                return repo.export_session_data(session_id, format)
                
        except Exception as e:
            logger.error(f"Failed to export session data for {session_id}: {str(e)}")
            return {
                "error": str(e),
                "session_id": session_id,
                "format": format,
                "data": None
            }
    
    def search_sessions(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Search sessions by alert content, error messages, or metadata.
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
            
        Returns:
            List of matching session summaries
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    return []
                
                return repo.search_sessions(query, limit)
                
        except Exception as e:
            logger.error(f"Failed to search sessions with query '{query}': {str(e)}")
            return []
    
    # Maintenance Operations
    def cleanup_old_sessions(self) -> int:
        """
        Clean up sessions older than retention period.
        
        Returns:
            Number of sessions cleaned up
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    return 0
                
                return repo.cleanup_old_sessions(self.settings.history_retention_days)
                
        except Exception as e:
            logger.error(f"Failed to cleanup old sessions: {str(e)}")
            return 0
    
    def cleanup_orphaned_sessions(self) -> int:
        """
        Clean up sessions that were left in active states due to unexpected backend shutdown.
        
        This method finds all sessions in "pending" or "in_progress" status and marks them
        as "failed" since they were clearly interrupted and cannot continue processing.
        
        Should be called during backend startup to handle crash recovery.
        
        Returns:
            Number of orphaned sessions cleaned up
        """
        if not self.is_enabled:
            logger.debug("History service disabled - skipping orphaned session cleanup")
            return 0
            
        try:
            with self.get_repository() as repo:
                if not repo:
                    logger.warning("History repository unavailable - cannot cleanup orphaned sessions")
                    return 0
                
                # Find all sessions in active states (pending or in_progress)
                active_sessions_result = repo.get_alert_sessions(
                    status=AlertSessionStatus.ACTIVE_STATUSES,
                    page_size=1000  # Get a large batch to handle all orphaned sessions
                )
                
                if not active_sessions_result or not active_sessions_result.get("sessions"):
                    logger.info("No orphaned sessions found during startup cleanup")
                    return 0
                
                active_sessions = active_sessions_result["sessions"]
                cleanup_count = 0
                
                for session in active_sessions:
                    try:
                        # Mark session as failed with appropriate error message
                        session.status = AlertSessionStatus.FAILED
                        session.error_message = "Backend was restarted - session terminated unexpectedly"
                        session.completed_at_us = now_us()
                        
                        success = repo.update_alert_session(session)
                        if success:
                            cleanup_count += 1
                            logger.debug(f"Marked orphaned session {session.session_id} as failed")
                        else:
                            logger.warning(f"Failed to update orphaned session {session.session_id}")
                            
                    except Exception as session_error:
                        logger.error(f"Error cleaning up session {session.session_id}: {str(session_error)}")
                        continue
                
                if cleanup_count > 0:
                    logger.info(f"Cleaned up {cleanup_count} orphaned sessions during startup")
                else:
                    logger.info("No orphaned sessions required cleanup during startup")
                    
                return cleanup_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup orphaned sessions: {str(e)}")
            return 0
    
    def health_check(self) -> Dict[str, Any]:
        """
        Get health status of history service.
        
        Returns:
            Dictionary containing health status information
        """
        return {
            "enabled": self.is_enabled,
            "healthy": self._is_healthy,
            "database_url": self.settings.history_database_url if self.is_enabled else None,
            "retention_days": self.settings.history_retention_days if self.is_enabled else None
        }
    
    def shutdown(self) -> None:
        """Gracefully shutdown history service."""
        try:
            if self.db_manager:
                self.db_manager.close()
                logger.info("History service shutdown complete")
        except Exception as e:
            logger.error(f"Error during history service shutdown: {str(e)}")


# Global history service instance
_history_service: Optional[HistoryService] = None


def get_history_service() -> HistoryService:
    """
    Get the global history service instance.
    
    Returns:
        HistoryService instance (initialized on first access)
    """
    global _history_service
    if _history_service is None:
        _history_service = HistoryService()
        _history_service.initialize()
    return _history_service 