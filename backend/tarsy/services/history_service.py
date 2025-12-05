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
from typing import Any, Dict, List, Optional, Tuple

from tarsy.config.settings import get_settings
from tarsy.models.agent_config import ChainConfigModel
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession, Chat, ChatUserMessage, StageExecution
from tarsy.models.history_models import (
    ConversationMessage,
    DetailedSession,
    FilterOptions,
    LLMConversationHistory,
    PaginatedSessions,
    SessionStats,
)
from tarsy.models.processing_context import ChainContext
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.repositories.base_repository import DatabaseManager
from tarsy.repositories.history_repository import HistoryRepository
from tarsy.utils.timestamp import now_us

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
        
        Runs synchronous database operations in a thread pool to avoid blocking the event loop.
        
        Args:
            operation_name: Name of the operation for logging
            operation_func: Function to retry (executed in thread pool)
            treat_none_as_success: Whether None result is acceptable
        
        Returns:
            Result of the operation, or None if all retries failed
        """
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await asyncio.to_thread(operation_func)
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
            self.db_manager = DatabaseManager(self.settings.database_url)
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
        chain_definition: ChainConfigModel
    ) -> bool:
        """
        Create a new alert processing session with retry logic.
        
        Args:
            chain_context: Chain processing context containing session data
            chain_definition: Chain configuration model with chain details
            
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
                    alert_data=chain_context.processing_alert.alert_data,
                    agent_type=agent_type,
                    alert_type=chain_context.processing_alert.alert_type,
                    status=AlertSessionStatus.PENDING.value,
                    chain_id=chain_definition.chain_id,
                    chain_definition=chain_definition.model_dump(),  # Store as JSON-serializable dict
                    author=chain_context.author,  # User who submitted the alert (from oauth2-proxy headers)
                    runbook_url=chain_context.processing_alert.runbook_url,  # Runbook URL for re-submission
                    mcp_selection=chain_context.mcp.model_dump() if chain_context.mcp else None  # MCP selection for re-submission
                )
                
                created_session = repo.create_alert_session(session)
                if created_session:
                    logger.info(f"Created history session {created_session.session_id}")
                    return True
                return False
        
        result = self._retry_database_operation("create_session", _create_session_operation)
        return result if result is not None else False
    
    def update_session_status(
        self,
        session_id: str,
        status: str,
        error_message: Optional[str] = None,
        final_analysis: Optional[str] = None,
        final_analysis_summary: Optional[str] = None,
        pause_metadata: Optional[dict] = None
    ) -> bool:
        """
        Update session processing status with retry logic.
        
        Args:
            session_id: The session identifier
            status: New status (pending, in_progress, completed, failed, paused)
            error_message: Error message if status is failed
            final_analysis: Final formatted analysis if status is completed
            pause_metadata: Pause metadata if status is paused
            
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
                if final_analysis_summary:
                    session.final_analysis_summary = final_analysis_summary
                # Set pause_metadata when transitioning to PAUSED, clear it otherwise
                if status == AlertSessionStatus.PAUSED.value:
                    session.pause_metadata = pause_metadata
                else:
                    # Clear pause_metadata when not paused (keep it clean)
                    session.pause_metadata = None
                if status in AlertSessionStatus.terminal_values():
                    session.completed_at_us = now_us()
                
                success = repo.update_alert_session(session)
                if success:
                    logger.debug(f"Updated session {session_id} status to {status}")
                        
                return success
        
        result = self._retry_database_operation("update_session_status", _update_status_operation)
        return result if result is not None else False
    
    def get_session(self, session_id: str) -> Optional['AlertSession']:
        """
        Get session by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            AlertSession if found, None otherwise
        """
        if not self.is_enabled or not session_id:
            return None
        
        def _get_operation():
            with self.get_repository() as repo:
                if not repo:
                    return None
                return repo.get_alert_session(session_id)
        
        return self._retry_database_operation(
            "get_session",
            _get_operation,
            treat_none_as_success=True
        )
    
    def update_session_to_canceling(self, session_id: str) -> tuple[bool, str]:
        """
        Atomically update session to CANCELING if not already terminal.
        
        This is used for session cancellation to ensure we don't cancel
        sessions that have already completed or failed.
        
        Args:
            session_id: Session identifier
            
        Returns:
            (success, current_status): True if updated to CANCELING, False if already terminal.
                                        Also returns the current status.
        """
        if not self.is_enabled or not session_id:
            return (False, "unknown")
        
        def _update_operation():
            with self.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable")
                
                session = repo.get_alert_session(session_id)
                if not session:
                    return (False, "not_found")
                
                # Check if already terminal - don't update if so
                if session.status in AlertSessionStatus.terminal_values():
                    logger.info(f"Session {session_id} already terminal: {session.status}")
                    return (False, session.status)
                
                # Check if already canceling - idempotent
                if session.status == AlertSessionStatus.CANCELING.value:
                    logger.info(f"Session {session_id} already canceling")
                    return (True, session.status)
                
                # Update to CANCELING
                session.status = AlertSessionStatus.CANCELING.value
                success = repo.update_alert_session(session)
                
                if success:
                    logger.info(f"Updated session {session_id} to CANCELING")
                    return (True, AlertSessionStatus.CANCELING.value)
                
                return (False, session.status)
        
        result = self._retry_database_operation("update_to_canceling", _update_operation)
        return result if result else (False, "error")

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
                    from tarsy.models.history_models import (
                        ChainStatistics,
                        SessionStats,
                    )
                    
                    # Calculate basic counts from the SessionOverview model
                    total_interactions = session_overview.total_interactions
                    llm_interactions = session_overview.llm_interaction_count
                    mcp_communications = session_overview.mcp_communication_count
                    
                    # Calculate duration from session timing
                    total_duration_ms = 0
                    if session_overview.started_at_us and session_overview.completed_at_us:
                        total_duration_ms = (session_overview.completed_at_us - session_overview.started_at_us) // 1000
                    
                    # Calculate token usage aggregations - prefer repository-provided session totals
                    session_input_tokens = 0
                    session_output_tokens = 0
                    session_total_tokens = 0

                    # Check if aggregated token totals are already available in session overview
                    if (session_overview.session_input_tokens is not None and 
                        session_overview.session_output_tokens is not None and 
                        session_overview.session_total_tokens is not None):
                        # Use the already-available aggregated session totals from overview
                        session_input_tokens = session_overview.session_input_tokens
                        session_output_tokens = session_overview.session_output_tokens
                        session_total_tokens = session_overview.session_total_tokens
                    else:
                        # Aggregates not available in overview, get detailed session for fallback calculation
                        detailed_session = repo.get_session_details(session_id)
                        if detailed_session:
                            # Check if aggregated session totals are available in detailed session
                            if (detailed_session.session_input_tokens is not None and 
                                detailed_session.session_output_tokens is not None and 
                                detailed_session.session_total_tokens is not None):
                                # Use the repository-provided aggregated session totals
                                session_input_tokens = detailed_session.session_input_tokens
                                session_output_tokens = detailed_session.session_output_tokens
                                session_total_tokens = detailed_session.session_total_tokens
                            else:
                                # Fall back to manual per-stage summation if aggregates are missing
                                for stage in detailed_session.stages:
                                    if stage.stage_input_tokens:
                                        session_input_tokens += stage.stage_input_tokens
                                    if stage.stage_output_tokens: 
                                        session_output_tokens += stage.stage_output_tokens
                                    if stage.stage_total_tokens:
                                        session_total_tokens += stage.stage_total_tokens
                    
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
                        session_input_tokens=session_input_tokens,
                        session_output_tokens=session_output_tokens,
                        session_total_tokens=session_total_tokens,
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
    
    async def get_stage_executions(self, session_id: str) -> List[StageExecution]:
        """Get all stage executions for a session."""
        def _get_stage_executions_operation():
            with self.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot retrieve stage executions")
                return repo.get_stage_executions_for_session(session_id)
        
        result = await self._retry_database_operation_async(
            "get_stage_executions",
            _get_stage_executions_operation,
            treat_none_as_success=True,
        )
        return result or []
    
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
        page_size: int = 20,
        sort_by: Optional[str] = None,
        sort_order: Optional[str] = None
    ) -> Optional[PaginatedSessions]:
        """
        Retrieve alert sessions with filtering and pagination - returns PaginatedSessions model directly for controllers.
        
        Args:
            filters: Dictionary of filters (status, agent_type, alert_type, start_date_us, end_date_us)
            page: Page number for pagination
            page_size: Number of results per page
            sort_by: Optional field to sort by
            sort_order: Optional sort order ('asc' or 'desc')
            
        Returns:
            PaginatedSessions model or None if unavailable
            
        Raises:
            RuntimeError: If repository is unavailable
        """
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
                page_size=page_size,
                sort_by=sort_by,
                sort_order=sort_order
            )
            
            # Add the applied filters to the model
            if paginated_sessions and filters:
                paginated_sessions.filters_applied = filters
            
            return paginated_sessions

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
            
        Raises:
            RuntimeError: If repository is unavailable
        """
        with self.get_repository() as repo:
            if not repo:
                raise RuntimeError("History repository unavailable - cannot retrieve active sessions")
            
            return repo.get_active_sessions()

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
    def _cleanup_orphaned_stages_for_session(self, repo: 'HistoryRepository', session_id: str) -> int:
        """
        Mark all non-terminal stages in a session as failed.
        
        This is a helper method called when cleaning up orphaned sessions to ensure
        that all stages that were in progress or pending are also marked as failed.
        
        Args:
            repo: History repository instance 
            session_id: Session ID to cleanup stages for
            
        Returns:
            Number of stages marked as failed
        """
        from sqlmodel import select

        from tarsy.models.constants import StageStatus
        from tarsy.models.db_models import StageExecution
        
        try:
            # Get all stages for this session that are not already in terminal states
            stages_stmt = (
                select(StageExecution)
                .where(StageExecution.session_id == session_id)
                .where(StageExecution.status.in_([
                    StageStatus.PENDING.value, 
                    StageStatus.ACTIVE.value
                ]))
            )
            active_stages = repo.session.exec(stages_stmt).all()
            
            if not active_stages:
                logger.debug(f"No active stages found for session {session_id}")
                return 0
            
            stage_cleanup_count = 0
            current_time = now_us()
            
            for stage in active_stages:
                try:
                    # Update stage to failed status
                    stage.status = StageStatus.FAILED.value
                    stage.error_message = "Session terminated due to backend restart"
                    stage.completed_at_us = current_time
                    
                    # Calculate duration if stage was started
                    if stage.started_at_us and stage.completed_at_us:
                        stage.duration_ms = int((stage.completed_at_us - stage.started_at_us) / 1000)
                    
                    # Update the stage execution
                    success = repo.update_stage_execution(stage)
                    if success:
                        stage_cleanup_count += 1
                        logger.debug(f"Marked orphaned stage {stage.stage_id} (index {stage.stage_index}) as failed for session {session_id}")
                    else:
                        logger.warning(f"Failed to update orphaned stage {stage.stage_id} for session {session_id}")
                        
                except Exception as stage_update_error:
                    logger.error(f"Error updating stage {stage.stage_id} for session {session_id}: {str(stage_update_error)}")
                    continue
            
            if stage_cleanup_count > 0:
                logger.debug(f"Cleaned up {stage_cleanup_count} orphaned stages for session {session_id}")
            
            return stage_cleanup_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup stages for session {session_id}: {str(e)}")
            return 0

    def cleanup_orphaned_sessions(self, timeout_minutes: int = 30) -> int:
        """
        Find and mark orphaned sessions as failed based on inactivity timeout (EP-0024).
        
        Replaces the existing simple cleanup_orphaned_sessions() method with
        timeout-based detection. An orphaned session is one that:
        - Is in 'in_progress' status
        - Has not had any interaction for longer than timeout_minutes
        
        This handles cases where:
        - Pod crashed without graceful shutdown
        - Session is stuck/hung without activity
        
        Args:
            timeout_minutes: Mark sessions inactive for this long as failed (default: 30)
        
        Returns:
            Number of sessions marked as failed
        """
        if not self.is_enabled:
            return 0
        
        def _cleanup_operation():
            with self.get_repository() as repo:
                if not repo:
                    return 0
                
                timeout_threshold_us = now_us() - (timeout_minutes * 60 * 1_000_000)
                orphaned_sessions = repo.find_orphaned_sessions(timeout_threshold_us)
                
                for session_record in orphaned_sessions:
                    session_record.status = AlertSessionStatus.FAILED.value
                    session_record.error_message = (
                        'Processing failed - session became unresponsive. '
                        'This may be due to pod crash, restart, or timeout during processing.'
                    )
                    session_record.completed_at_us = now_us()
                    repo.update_alert_session(session_record)
                
                return len(orphaned_sessions)
        
        count = self._retry_database_operation("cleanup_orphaned_sessions", _cleanup_operation)
        
        if count and count > 0:
            logger.info(f"Cleaned up {count} orphaned sessions during startup")
        
        return count or 0
    
    async def mark_pod_sessions_interrupted(self, pod_id: str) -> int:
        """
        Mark sessions being processed by a pod as failed during graceful shutdown
        Sets descriptive error_message to distinguish from other failure types.
        
        Args:
            pod_id: Kubernetes pod identifier
        
        Returns:
            Number of sessions marked as failed
        """
        if not self.is_enabled:
            return 0
        
        def _interrupt_operation():
            with self.get_repository() as repo:
                if not repo:
                    return 0
                
                in_progress_sessions = repo.find_sessions_by_pod(
                    pod_id, 
                    AlertSessionStatus.IN_PROGRESS.value
                )
                
                for session_record in in_progress_sessions:
                    session_record.status = AlertSessionStatus.FAILED.value
                    session_record.error_message = f"Session interrupted during pod '{pod_id}' graceful shutdown"
                    session_record.completed_at_us = now_us()
                    repo.update_alert_session(session_record)
                
                return len(in_progress_sessions)
        
        count = self._retry_database_operation("mark_interrupted_sessions", _interrupt_operation)
        
        if count and count > 0:
            logger.info(f"Marked {count} sessions as failed (interrupted) for pod {pod_id}")
        
        return count or 0
    
    async def start_session_processing(self, session_id: str, pod_id: str) -> bool:
        """
        Mark session as being processed by a specific pod (EP-0024).
        Updates status, pod_id, and last_interaction_at.
        
        Args:
            session_id: Session identifier
            pod_id: Kubernetes pod identifier
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_enabled:
            return False
        
        def _start_operation():
            with self.get_repository() as repo:
                if not repo:
                    return False
                return repo.update_session_pod_tracking(
                    session_id, 
                    pod_id, 
                    AlertSessionStatus.IN_PROGRESS.value
                )
        
        return self._retry_database_operation("start_session_processing", _start_operation) or False
    
    def record_session_interaction(self, session_id: str) -> bool:
        """
        Update session last_interaction_at timestamp (EP-0024).
        
        Called during LLM interactions, MCP tool calls, and stage transitions
        to keep the session marked as active for orphan detection.
        
        Note: This is a synchronous function. When calling from async code,
        use asyncio.to_thread() to avoid blocking the event loop.
        
        Args:
            session_id: Session identifier
        
        Returns:
            True if successful, False otherwise
        """
        if not self.is_enabled:
            return False
        
        def _interaction_operation():
            with self.get_repository() as repo:
                if not repo:
                    return False
                
                session = repo.get_alert_session(session_id)
                if not session:
                    return False
                
                session.last_interaction_at = now_us()
                return repo.update_alert_session(session)
        
        return self._retry_database_operation("record_interaction", _interaction_operation) or False
    
    # ===== CHAT OPERATIONS =====
    
    async def create_chat(self, chat: Chat) -> Chat:
        """Create a new chat record."""
        if not self.is_enabled:
            raise ValueError("History service is disabled")
        
        def _create_operation():
            with self.get_repository() as repo:
                if not repo:
                    raise ValueError("Repository unavailable")
                return repo.create_chat(chat)
        
        return self._retry_database_operation("create_chat", _create_operation)
    
    async def get_chat_by_id(self, chat_id: str) -> Optional[Chat]:
        """Get chat by ID."""
        if not self.is_enabled:
            return None
        
        def _get_operation():
            with self.get_repository() as repo:
                if not repo:
                    return None
                return repo.get_chat_by_id(chat_id)
        
        return self._retry_database_operation(
            "get_chat_by_id",
            _get_operation,
            treat_none_as_success=True
        )
    
    async def get_chat_by_session(self, session_id: str) -> Optional[Chat]:
        """Get chat for a session (if exists)."""
        if not self.is_enabled:
            return None
        
        def _get_operation():
            with self.get_repository() as repo:
                if not repo:
                    return None
                return repo.get_chat_by_session(session_id)
        
        return self._retry_database_operation(
            "get_chat_by_session",
            _get_operation,
            treat_none_as_success=True
        )
    
    async def create_chat_user_message(self, message: ChatUserMessage) -> ChatUserMessage:
        """Create a new chat user message."""
        if not self.is_enabled:
            raise ValueError("History service is disabled")
        
        def _create_operation():
            with self.get_repository() as repo:
                if not repo:
                    raise ValueError("Repository unavailable")
                return repo.create_chat_user_message(message)
        
        return self._retry_database_operation("create_chat_user_message", _create_operation)
    
    async def get_stage_executions_for_chat(self, chat_id: str) -> List[StageExecution]:
        """Get all stage executions for a chat."""
        if not self.is_enabled:
            return []
        
        def _get_operation():
            with self.get_repository() as repo:
                if not repo:
                    return []
                return repo.get_stage_executions_for_chat(chat_id)
        
        return self._retry_database_operation(
            "get_stage_executions_for_chat",
            _get_operation
        ) or []
    
    async def get_llm_interactions_for_session(self, session_id: str) -> List['LLMInteraction']:
        """Get all LLM interactions for a session."""
        if not self.is_enabled:
            return []
        
        def _get_operation():
            with self.get_repository() as repo:
                if not repo:
                    return []
                return repo.get_llm_interactions_for_session(session_id)
        
        return self._retry_database_operation(
            "get_llm_interactions_for_session",
            _get_operation
        ) or []
    
    async def get_llm_interactions_for_stage(self, stage_execution_id: str) -> List['LLMInteraction']:
        """Get all LLM interactions for a stage execution."""
        if not self.is_enabled:
            return []
        
        def _get_operation():
            with self.get_repository() as repo:
                if not repo:
                    return []
                return repo.get_llm_interactions_for_stage(stage_execution_id)
        
        return self._retry_database_operation(
            "get_llm_interactions_for_stage",
            _get_operation
        ) or []
    
    async def get_chat_user_message_count(self, chat_id: str) -> int:
        """Get total user message count for a chat."""
        if not self.is_enabled:
            return 0
        
        def _count_operation():
            with self.get_repository() as repo:
                if not repo:
                    return 0
                return repo.get_chat_user_message_count(chat_id)
        
        return self._retry_database_operation(
            "get_chat_user_message_count",
            _count_operation
        ) or 0
    
    async def get_chat_user_messages(
        self,
        chat_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[ChatUserMessage]:
        """Get user messages for a chat with pagination."""
        if not self.is_enabled:
            return []
        
        def _get_operation():
            with self.get_repository() as repo:
                if not repo:
                    return []
                return repo.get_chat_user_messages(chat_id, limit, offset)
        
        return self._retry_database_operation(
            "get_chat_user_messages",
            _get_operation
        ) or []
    
    # ===== CONVERSATION HISTORY =====
    
    def get_session_conversation_history(
        self,
        session_id: str,
        include_chat: bool = False
    ) -> Tuple[Optional[LLMConversationHistory], Optional[LLMConversationHistory]]:
        """
        Get LLM conversation history for a session and optionally its chat.
        
        Strategy:
        1. For main session: Get the last final_analysis type interaction (or fallback to last by timestamp)
        2. For chat (if include_chat=True): Get the last chat stage's final_analysis interaction
        
        The conversation includes all accumulated messages up to that point,
        providing the full context for analysis/evaluation.
        
        Args:
            session_id: Session identifier
            include_chat: If True, also get chat conversation history
            
        Returns:
            Tuple of (session_conversation, chat_conversation), either can be None
        """
        if not self.is_enabled:
            return None, None
        
        def _get_conversation_history():
            with self.get_repository() as repo:
                if not repo:
                    return None, None
                
                # Get main session conversation
                session_interaction = repo.get_last_llm_interaction_with_conversation(
                    session_id=session_id,
                    prefer_final_analysis=True,
                    chat_id=None  # Main session, exclude chat stages
                )
                session_conversation = self._build_conversation_history(session_interaction)
                
                # Get chat conversation if requested
                chat_conversation = None
                if include_chat:
                    chat = repo.get_chat_by_session(session_id)
                    if chat:
                        chat_interaction = repo.get_last_llm_interaction_with_conversation(
                            session_id=session_id,
                            prefer_final_analysis=True,
                            chat_id=chat.chat_id
                        )
                        chat_conversation = self._build_conversation_history(chat_interaction)
                
                return session_conversation, chat_conversation
        
        result = self._retry_database_operation(
            "get_session_conversation_history",
            _get_conversation_history
        )
        return result if result else (None, None)
    
    def _build_conversation_history(
        self,
        interaction: Optional[LLMInteraction]
    ) -> Optional[LLMConversationHistory]:
        """
        Build LLMConversationHistory from an LLMInteraction.
        
        Args:
            interaction: LLMInteraction with conversation data
            
        Returns:
            LLMConversationHistory model or None if no valid conversation
        """
        if not interaction or not interaction.conversation:
            return None
        
        try:
            # Convert conversation messages to simple format
            messages = [
                ConversationMessage(
                    role=msg.role.value if hasattr(msg.role, 'value') else str(msg.role),
                    content=msg.content
                )
                for msg in interaction.conversation.messages
            ]
            
            return LLMConversationHistory(
                model_name=interaction.model_name,
                provider=interaction.provider,
                timestamp_us=interaction.timestamp_us,
                input_tokens=interaction.input_tokens,
                output_tokens=interaction.output_tokens,
                total_tokens=interaction.total_tokens,
                messages=messages
            )
        except Exception as e:
            logger.error(f"Failed to build conversation history: {str(e)}")
            return None
    
    # Pod Tracking & Orphan Detection
    
    async def start_chat_message_processing(self, chat_id: str, pod_id: str) -> bool:
        """Mark chat as processing a message on a specific pod."""
        if not self.is_enabled:
            return False
        
        def _start_operation():
            with self.get_repository() as repo:
                if not repo:
                    return False
                return repo.update_chat_pod_tracking(chat_id, pod_id)
        
        return self._retry_database_operation(
            "start_chat_message_processing",
            _start_operation
        ) or False
    
    def record_chat_interaction(self, chat_id: str) -> bool:
        """Update chat last_interaction_at timestamp (synchronous)."""
        if not self.is_enabled:
            return False
        
        def _record_operation():
            with self.get_repository() as repo:
                if not repo:
                    return False
                chat = repo.get_chat_by_id(chat_id)
                if not chat:
                    return False
                chat.last_interaction_at = now_us()
                return repo.update_chat(chat)
        
        return self._retry_database_operation(
            "record_chat_interaction",
            _record_operation
        ) or False
    
    def cleanup_orphaned_chats(self, timeout_minutes: int = 30) -> int:
        """Find and clear stale processing markers from orphaned chats."""
        if not self.is_enabled:
            return 0
        
        def _cleanup_operation():
            with self.get_repository() as repo:
                if not repo:
                    return 0
                
                timeout_us = timeout_minutes * 60 * 1_000_000
                threshold = now_us() - timeout_us
                
                orphaned_chats = repo.find_orphaned_chats(threshold)
                
                for chat in orphaned_chats:
                    chat.pod_id = None
                    chat.last_interaction_at = None
                    repo.session.add(chat)
                repo.session.commit()
                
                return len(orphaned_chats)
        
        count = self._retry_database_operation(
            "cleanup_orphaned_chats",
            _cleanup_operation
        )
        
        if count and count > 0:
            logger.info(
                f"Cleaned up {count} orphaned chat message processing markers"
            )
        
        return count or 0
    
    async def mark_pod_chats_interrupted(self, pod_id: str) -> int:
        """Clear processing markers for chats on a shutting-down pod."""
        if not self.is_enabled:
            return 0
        
        def _interrupt_operation():
            with self.get_repository() as repo:
                if not repo:
                    return 0
                
                active_chats = repo.find_chats_by_pod(pod_id)
                
                for chat in active_chats:
                    chat.pod_id = None
                    chat.last_interaction_at = None
                    repo.session.add(chat)
                repo.session.commit()
                
                return len(active_chats)
        
        count = self._retry_database_operation(
            "mark_interrupted_chats",
            _interrupt_operation
        )
        
        if count and count > 0:
            logger.info(f"Marked {count} chat(s) as interrupted for pod {pod_id}")
        
        return count or 0


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