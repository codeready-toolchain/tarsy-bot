"""
History Service for Alert Processing Audit Trail.

Provides centralized management of alert processing history including session
lifecycle, LLM interaction tracking, MCP communication logging, and timeline
reconstruction with graceful degradation when database is unavailable.
"""

import asyncio
import logging
import random
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from tarsy.config.settings import get_settings

from tarsy.models.history_models import (
    PaginatedSessions, DetailedSession, FilterOptions, SessionStats
)
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession, StageExecution
from tarsy.utils.timestamp import now_us
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.models.processing_context import ChainContext
from tarsy.models.agent_config import ChainConfigModel
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
    
    def _retry_database_operation(
        self,
        operation_name: str,
        operation_func,
        *,
        treat_none_as_success: bool = False,
    ):
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
                if treat_none_as_success:
                    # None is an acceptable outcome (e.g., entity not found)
                    return None
                # If result is None, log and continue to retry
                logger.warning(
                    f"Database operation '{operation_name}' returned None on attempt {attempt + 1}"
                )
                
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
    
    async def _retry_database_operation_async(
        self,
        operation_name: str,
        operation_func,
        *,
        treat_none_as_success: bool = False,
    ):
        """
        Async version of retry database operations with exponential backoff for transient failures.
        
        Args:
            operation_name: Name of the operation for logging
            operation_func: Function to retry
            treat_none_as_success: Whether None result is acceptable
        
        Returns:
            Result of the operation, or None if all retries failed
        """
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                result = operation_func()
                if result is not None:
                    return result
                if treat_none_as_success:
                    return None
                logger.warning(f"Database operation '{operation_name}' returned None on attempt {attempt + 1}")
            except Exception as e:
                last_exception = e
                error_msg = str(e).lower()
                is_retryable = any(k in error_msg for k in [
                    'database is locked', 'database disk image is malformed', 'sqlite3.operationalerror',
                    'connection timeout', 'database table is locked', 'connection pool', 'connection closed'
                ])
                if operation_name == "create_session" and attempt > 0:
                    logger.warning("Not retrying session creation after database error to prevent duplicates: %s", str(e))
                    return None
                if not is_retryable or attempt == self.max_retries:
                    logger.error("Database operation '%s' failed after %d attempts: %s", operation_name, attempt + 1, str(e))
                    return None
                delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                jitter = random.uniform(0, delay * 0.1)
                await asyncio.sleep(delay + jitter)
        logger.error("Database operation '%s' failed after all retries. Last error: %s", operation_name, str(last_exception))
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
        repository = None
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
            # Don't yield here - the repository was already yielded above
            
        finally:
            if session:
                try:
                    session.close()
                except Exception as e:
                    logger.error(f"Error closing database session: {str(e)}")
    
    # Session Lifecycle Operations
    def create_session(
        self,
        chain_context: ChainContext,
        chain_definition: ChainConfigModel,
        alert_id: str
    ) -> bool:
        """
        Create a new alert processing session with retry logic.
        
        Args:
            chain_context: Chain processing context containing session data
            chain_definition: Chain configuration model with chain details
            alert_id: External alert identifier
            
        Returns:
            True if created successfully, False if failed
        """
        if not self.is_enabled:
            logger.debug("History capture disabled - skipping session creation")
            return False
        
        def _create_session_operation():
            with self.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot create session")
                
                # Extract data from ChainContext and ChainConfigModel
                agent_type = f"chain:{chain_definition.chain_id}"  # Construct agent_type internally
                
                session = AlertSession(
                    session_id=chain_context.session_id,
                    alert_id=alert_id,
                    alert_data=chain_context.alert_data,
                    agent_type=agent_type,
                    alert_type=chain_context.alert_type,
                    status=AlertSessionStatus.PENDING.value,
                    chain_id=chain_definition.chain_id,
                    chain_definition=chain_definition.model_dump()  # Store as JSON-serializable dict
                )
                
                created_session = repo.create_alert_session(session)
                if created_session:
                    logger.info(f"Created history session {created_session.session_id} for alert {alert_id}")
                    return True
                return False
        
        result = self._retry_database_operation("create_session", _create_session_operation)
        return result if result is not None else False
    
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
                    raise RuntimeError("History repository unavailable - cannot update session status")
                
                session = repo.get_alert_session(session_id)
                if not session:
                    logger.warning(f"Session {session_id} not found for status update")
                    return False
                
                session.status = status
                if error_message:
                    session.error_message = error_message
                if final_analysis:
                    session.final_analysis = final_analysis
                if status in AlertSessionStatus.terminal_values():
                    session.completed_at_us = now_us()
                
                success = repo.update_alert_session(session)
                if success:
                    logger.debug(f"Updated session {session_id} status to {status}")
                    
                    # Notify dashboard update service of session status change
                    # 
                    # NOTE: We call dashboard_manager directly instead of using the hook mechanism because:
                    # 1. No session status hook exists - current hooks handle interaction-level events
                    #    (LLM calls, MCP tools, stage executions), not session lifecycle events
                    # 2. Circular import prevention - importing dashboard_manager at module level would
                    #    create dependency cycles (HistoryService -> DashboardManager -> hooks -> HistoryService)
                    # 3. DashboardUpdateService has a dedicated process_session_status_change() method
                    #    designed specifically for session lifecycle events (vs. interaction events)
                    # 4. Async context handling - this sync method needs to trigger async dashboard updates
                    #
                    # To use hooks instead, we'd need: a SessionStatusEvent model, a SessionStatusHook,
                    # dependency injection refactoring, and hook registry updates for session-level events.
                    try:
                        # Import here to avoid circular imports
                        from tarsy.main import dashboard_manager
                        if dashboard_manager and dashboard_manager.update_service:
                            # Prepare details for dashboard update
                            details = {}
                            if error_message:
                                details['error_message'] = error_message
                            if final_analysis:
                                details['final_analysis'] = final_analysis
                                
                            # Process session status change for dashboard updates
                            import asyncio
                            try:
                                loop = asyncio.get_running_loop()
                                # In async context: schedule task on current loop
                                loop.create_task(
                                    dashboard_manager.update_service.process_session_status_change(
                                        session_id, status, details
                                    )
                                )
                            except RuntimeError:
                                # No running loop: run synchronously
                                asyncio.run(
                                    dashboard_manager.update_service.process_session_status_change(
                                        session_id, status, details
                                    )
                                )
                    except Exception as e:
                        logger.warning(f"Failed to notify dashboard update service: {e}")
                        
                return success
        
        result = self._retry_database_operation("update_session_status", _update_status_operation)
        return result if result is not None else False

    # Stage Execution Methods for Chain Processing
    async def create_stage_execution(self, stage_execution: StageExecution) -> str:
        """Create a new stage execution record."""
        def _create_stage_operation():
            with self.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot create stage execution record")
                return repo.create_stage_execution(stage_execution)
        
        result = await self._retry_database_operation_async("create_stage_execution", _create_stage_operation)
        if result is None:
            raise RuntimeError(f"Failed to create stage execution record for stage '{stage_execution.stage_name}'. Chain processing cannot continue without proper stage tracking.")
        return result
    
    async def update_stage_execution(self, stage_execution: StageExecution):
        """Update an existing stage execution record."""
        def _update_stage_operation():
            with self.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot update stage execution")
                return repo.update_stage_execution(stage_execution)
        
        result = await self._retry_database_operation_async("update_stage_execution", _update_stage_operation)
        return result if result is not None else False
    
    async def update_session_current_stage(
        self, 
        session_id: str, 
        current_stage_index: int, 
        current_stage_id: str
    ):
        """Update the current stage information for a session."""
        def _update_current_stage_operation():
            with self.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot update session current stage")
                return repo.update_session_current_stage(session_id, current_stage_index, current_stage_id)
        
        result = await self._retry_database_operation_async("update_session_current_stage", _update_current_stage_operation)
        return result if result is not None else False

    async def get_session_summary(self, session_id: str) -> Optional[SessionStats]:
        """
        Get just the summary statistics for a session - returns SessionStats model for controllers.
        
        Args:
            session_id: Session identifier
            
        Returns:
            SessionStats model or None if session not found
        """
        try:
            def _get_session_summary_operation():
                with self.get_repository() as repo:
                    if not repo:
                        raise RuntimeError("History repository unavailable - cannot retrieve session summary")
                    
                    session_overview = repo.get_session_overview(session_id)
                    if not session_overview:
                        # This is a legitimate case - session doesn't exist, not a system failure
                        return None
                    
                    # Calculate statistics from SessionOverview and return as SessionStats
                    from tarsy.models.history_models import SessionStats, ChainStatistics
                    
                    # Calculate basic counts from the SessionOverview model
                    total_interactions = session_overview.total_interactions
                    llm_interactions = session_overview.llm_interaction_count
                    mcp_communications = session_overview.mcp_communication_count
                    
                    # Calculate duration from session timing
                    total_duration_ms = 0
                    if session_overview.started_at_us and session_overview.completed_at_us:
                        total_duration_ms = (session_overview.completed_at_us - session_overview.started_at_us) // 1000
                    
                    # Create chain statistics from SessionOverview
                    chain_stats = ChainStatistics(
                        total_stages=session_overview.total_stages or 0,
                        completed_stages=session_overview.completed_stages or 0,
                        failed_stages=session_overview.failed_stages,
                        stages_by_agent={}  # Not calculated in overview for performance
                    )
                    
                    session_stats = SessionStats(
                        total_interactions=total_interactions,
                        llm_interactions=llm_interactions,
                        mcp_communications=mcp_communications,
                        system_events=0,  # Not tracked in SessionOverview
                        errors_count=1 if session_overview.error_message else 0,
                        total_duration_ms=total_duration_ms,
                        chain_statistics=chain_stats
                    )
                    return session_stats
            
            result = await self._retry_database_operation_async(
                "get_session_summary",
                _get_session_summary_operation,
                treat_none_as_success=True,
            )
            return result
                
        except Exception as e:
            logger.error(f"Failed to get session summary for {session_id}: {str(e)}")
            return None
    
    async def get_stage_execution(self, execution_id: str) -> Optional[StageExecution]:
        """Get a single stage execution by ID."""
        def _get_stage_execution_operation():
            with self.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot retrieve stage execution")
                return repo.get_stage_execution(execution_id)
        
        result = await self._retry_database_operation_async(
            "get_stage_execution",
            _get_stage_execution_operation,
            treat_none_as_success=True,
        )
        return result
    
    # LLM Interaction Logging
    def store_llm_interaction(self, interaction: LLMInteraction) -> bool:
        """
        Store an LLM interaction to the database using unified model.
        
        Args:
            interaction: LLMInteraction instance with all interaction details
            
        Returns:
            True if logged successfully, False otherwise
        """
        if not self.is_enabled or not interaction.session_id:
            return False
            
        def _store_llm_operation():
            with self.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot store LLM interaction")
                # Step description is handled at the timeline event level, not interaction level
                repo.create_llm_interaction(interaction)
                logger.debug(f"Stored LLM interaction for session {interaction.session_id}")
                return True

        result = self._retry_database_operation("store_llm_interaction", _store_llm_operation)
        return bool(result)
    
    # MCP Communication Logging
    def store_mcp_interaction(self, interaction: MCPInteraction) -> bool:
        """
        Store an MCP interaction to the database using unified model.
        
        Args:
            interaction: MCPInteraction instance with all interaction details
            
        Returns:
            True if logged successfully, False otherwise
        """
        if not self.is_enabled or not interaction.session_id:
            return False
            
        def _store_mcp_operation():
            with self.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot store MCP interaction")
                # Set step description if not already set
                if not interaction.step_description:
                    interaction.step_description = interaction.get_step_description()
                repo.create_mcp_communication(interaction)
                logger.debug(f"Stored MCP interaction for session {interaction.session_id}")
                return True

        result = self._retry_database_operation("store_mcp_interaction", _store_mcp_operation)
        return bool(result)
    
    # Properties
    @property
    def enabled(self) -> bool:
        """Check if history service is enabled."""
        return self.is_enabled

    def get_sessions_list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Optional[PaginatedSessions]:
        """
        Retrieve alert sessions with filtering and pagination - returns PaginatedSessions model directly for controllers.
        
        Args:
            filters: Dictionary of filters (status, agent_type, alert_type, start_date_us, end_date_us)
            page: Page number for pagination
            page_size: Number of results per page
            
        Returns:
            PaginatedSessions model or None if unavailable
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot retrieve sessions list")
                
                # Extract filters or use defaults
                filters = filters or {}
                
                # Use regular method that returns PaginatedSessions model directly
                paginated_sessions = repo.get_alert_sessions(
                    status=filters.get('status'),
                    agent_type=filters.get('agent_type'),
                    alert_type=filters.get('alert_type'),
                    search=filters.get('search'),
                    start_date_us=filters.get('start_date_us'),
                    end_date_us=filters.get('end_date_us'),
                    page=page,
                    page_size=page_size
                )
                
                # Add the applied filters to the model
                if paginated_sessions and filters:
                    paginated_sessions.filters_applied = filters
                
                return paginated_sessions
                
        except Exception as e:
            logger.error(f"Failed to get sessions list: {str(e)}")
            return None

    def test_database_connection(self) -> bool:
        """
        Test database connectivity.
        
        Returns:
            True if database connection is working, False otherwise
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot check health")
                
                # Try to perform a simple database operation
                # This will test both connection and basic functionality
                repo.get_alert_sessions(page=1, page_size=1)
                # Result is now PaginatedSessions model or None
                return True
                
        except Exception as e:
            logger.error(f"Database connection test failed: {str(e)}")
            return False

    def get_session_details(self, session_id: str) -> Optional[DetailedSession]:
        """
        Get complete session details including timeline, stages, and all interactions.
        
        Args:
            session_id: The session identifier
            
        Returns:
            DetailedSession model with complete session data or None if not found
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot retrieve session details")
                
                detailed_session = repo.get_session_details(session_id)
                return detailed_session
                
        except Exception as e:
            logger.error(f"Failed to get session details for {session_id}: {str(e)}")
            return None
    
    def get_active_sessions(self) -> List[AlertSession]:
        """
        Get all currently active sessions.
        
        Returns:
            List of active AlertSession instances
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot retrieve active sessions")
                
                return repo.get_active_sessions()
                
        except Exception as e:
            logger.error(f"Failed to get active sessions: {str(e)}")
            return []

    def get_filter_options(self) -> FilterOptions:
        """
        Get available filter options for the dashboard - returns FilterOptions model for controllers.
        
        Returns:
            FilterOptions model
            
        Raises:
            RuntimeError: If repository is unavailable
        """
        with self.get_repository() as repo:
            if not repo:
                raise RuntimeError("History repository unavailable - cannot retrieve filter options")
            
            return repo.get_filter_options()

    # Maintenance Operations
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
                    raise RuntimeError("History repository unavailable - cannot cleanup orphaned sessions")
                
                # Find all sessions in active states (pending or in_progress)
                active_sessions_result = repo.get_alert_sessions(
                    status=AlertSessionStatus.active_values(),
                    page_size=1000  # Get a large batch to handle all orphaned sessions
                )
                
                if not active_sessions_result or not active_sessions_result.sessions:
                    logger.info("No orphaned sessions found during startup cleanup")
                    return 0
                
                session_overviews = active_sessions_result.sessions
                cleanup_count = 0
                
                for session_overview in session_overviews:
                    try:
                        # Get the existing session from database instead of creating new object
                        session = repo.get_alert_session(session_overview.session_id)
                        if not session:
                            logger.warning(f"Could not find session {session_overview.session_id} for cleanup")
                            continue
                        
                        # Update the existing session object's fields
                        session.status = AlertSessionStatus.FAILED.value
                        session.error_message = "Backend was restarted - session terminated unexpectedly"
                        session.completed_at_us = now_us()
                        
                        success = repo.update_alert_session(session)
                        if success:
                            cleanup_count += 1
                            logger.debug(f"Marked orphaned session {session.session_id} as failed")
                        else:
                            logger.warning(f"Failed to update orphaned session {session.session_id}")
                            
                    except Exception as session_error:
                        session_id = session_overview.session_id if hasattr(session_overview, 'session_id') else 'unknown'
                        logger.error(f"Error cleaning up session {session_id}: {str(session_error)}")
                        continue
                
                if cleanup_count > 0:
                    logger.info(f"Cleaned up {cleanup_count} orphaned sessions during startup")
                else:
                    logger.info("No orphaned sessions required cleanup during startup")
                    
                return cleanup_count
                
        except Exception as e:
            logger.error(f"Failed to cleanup orphaned sessions: {str(e)}")
            return 0


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