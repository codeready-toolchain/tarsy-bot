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
from typing import Any, Dict, List, Optional

from tarsy.config.settings import get_settings

from tarsy.models.history_models import (
    PaginatedSessions, DetailedSession, FilterOptions, SessionStats
)
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession, StageExecution
from tarsy.utils.timestamp import now_us
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
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
        alert_type: Optional[str] = None,
        chain_id: Optional[str] = None,
        chain_definition: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Create a new alert processing session with retry logic.
        
        Args:
            alert_id: External alert identifier
            alert_data: Original alert payload
            agent_type: Processing agent type (e.g., 'kubernetes', 'base')
            alert_type: Alert type for filtering (e.g., 'pod_crash', 'high_cpu')
            chain_id: Chain identifier for chain processing (optional)
            chain_definition: Complete chain definition for chain processing (optional)
            
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
                    status=AlertSessionStatus.PENDING.value,
                    chain_id=chain_id,
                    chain_definition=chain_definition
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
                if status in AlertSessionStatus.terminal_values():
                    session.completed_at_us = now_us()
                
                success = repo.update_alert_session(session)
                if success:
                    logger.debug(f"Updated session {session_id} status to {status}")
                    
                    # Notify dashboard update service of session status change
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
                            if asyncio.get_event_loop().is_running():
                                # If we're in an async context, create a task
                                asyncio.create_task(
                                    dashboard_manager.update_service.process_session_status_change(
                                        session_id, status, details
                                    )
                                )
                            else:
                                # If not in async context, run directly
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
        
        result = self._retry_database_operation("create_stage_execution", _create_stage_operation)
        if result is None:
            raise RuntimeError(f"Failed to create stage execution record for stage '{stage_execution.stage_name}'. Chain processing cannot continue without proper stage tracking.")
        return result
    
    async def update_stage_execution(self, stage_execution: StageExecution):
        """Update an existing stage execution record."""
        def _update_stage_operation():
            with self.get_repository() as repo:
                if not repo:
                    logger.warning("History repository unavailable - stage execution not updated")
                    return False
                return repo.update_stage_execution(stage_execution)
        
        result = self._retry_database_operation("update_stage_execution", _update_stage_operation)
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
                    logger.warning("History repository unavailable - current stage not updated")
                    return False
                return repo.update_session_current_stage(session_id, current_stage_index, current_stage_id)
        
        result = self._retry_database_operation("update_session_current_stage", _update_current_stage_operation)
        return result if result is not None else False

    def get_stage_interaction_counts(self, execution_ids: List[str]) -> Dict[str, Dict[str, int]]:
        """
        Get interaction counts for stages using SQL aggregation.
        
        Args:
            execution_ids: List of stage execution IDs to get counts for
            
        Returns:
            Dictionary mapping execution_id to {'llm_interactions': count, 'mcp_communications': count}
        """
        def _get_stage_interaction_counts_operation():
            with self.get_repository() as repo:
                if not repo:
                    logger.warning("History repository unavailable - stage interaction counts not retrieved")
                    return {}
                return repo.get_stage_interaction_counts(execution_ids)
        
        result = self._retry_database_operation("get_stage_interaction_counts", _get_stage_interaction_counts_operation)
        return result if result is not None else {}
    
    def calculate_session_summary(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate summary statistics from session data.
        
        Extracts and calculates:
        - Total interactions, LLM calls, MCP communications, system events
        - Error counts and total duration
        - Chain-specific statistics if applicable
        
        Args:
            session_data: Raw session data from get_session_with_stages
            
        Returns:
            Dictionary with calculated summary statistics
        """
        if not session_data:
            return {}
            
        # Extract timeline and session info for calculations
        timeline = session_data.get('chronological_timeline', [])
        session_info = session_data.get('session', {})
        
        # Use pre-calculated counts from repository when available (more efficient)
        # Fall back to timeline-based calculation for backward compatibility
        llm_count = session_info.get('llm_interaction_count')
        if llm_count is None:
            llm_count = len([event for event in timeline if event.get('type') == 'llm'])
            
        mcp_count = session_info.get('mcp_communication_count') 
        if mcp_count is None:
            mcp_count = len([event for event in timeline if event.get('type') == 'mcp'])
        
        # Calculate basic interaction statistics
        summary = {
            'total_interactions': len(timeline),
            'llm_interactions': llm_count,
            'mcp_communications': mcp_count,
            'system_events': len([event for event in timeline if event.get('type') == 'system']),
            'errors_count': len([event for event in timeline if event.get('status') == 'failed']),
            'total_duration_ms': sum(event.get('duration_ms') or 0 for event in timeline)
        }
        
        # Add chain-specific statistics if it's a chain execution
        session_info = session_data.get('session', {})
        if session_info.get('chain_id'):
            stage_executions = session_data.get('stages', [])
            if stage_executions:
                from tarsy.models.constants import StageStatus
                # Note: stage_executions are dictionaries here, not model objects
                completed_stages = [stage for stage in stage_executions if stage.get('status') == StageStatus.COMPLETED.value]
                failed_stages = [stage for stage in stage_executions if stage.get('status') == StageStatus.FAILED.value]
                
                # Calculate stages by agent
                stages_by_agent = {}
                for stage in stage_executions:
                    agent = stage.get('agent')
                    if agent:
                        stages_by_agent[agent] = stages_by_agent.get(agent, 0) + 1
                
                summary.update({
                    'chain_statistics': {
                        'total_stages': len(stage_executions),
                        'completed_stages': len(completed_stages),
                        'failed_stages': len(failed_stages),
                        'stages_by_agent': stages_by_agent
                    }
                })
        
        return summary
    
    def calculate_session_summary_from_model(self, detailed_session: DetailedSession) -> Dict[str, Any]:
        """
        Calculate summary statistics from DetailedSession model.
        
        This replaces the dict-based calculate_session_summary method for better type safety.
        
        Args:
            detailed_session: DetailedSession model with all session data
            
        Returns:
            Dictionary with calculated summary statistics
        """
        # Calculate basic counts from the model
        total_interactions = detailed_session.total_interactions
        llm_interactions = detailed_session.llm_interaction_count
        mcp_communications = detailed_session.mcp_communication_count
        
        # Count errors across all stages
        errors_count = 0
        system_events = 0  # Currently not tracked in our system
        
        # Calculate duration by summing from all interactions across all stages
        total_duration_ms = 0
        for stage in detailed_session.stages:
            for interaction in stage.llm_interactions:
                total_duration_ms += interaction.duration_ms or 0
            for interaction in stage.mcp_communications:
                total_duration_ms += interaction.duration_ms or 0
        
        # Calculate chain statistics
        total_stages = len(detailed_session.stages)
        completed_stages = len([s for s in detailed_session.stages if s.status.value == 'completed'])
        failed_stages = len([s for s in detailed_session.stages if s.status.value == 'failed'])
        
        # Count errors and calculate stages by agent
        stages_by_agent = {}
        for stage in detailed_session.stages:
            if stage.error_message:
                errors_count += 1
            
            # Count stages by agent
            agent_name = stage.agent
            stages_by_agent[agent_name] = stages_by_agent.get(agent_name, 0) + 1
        
        return {
            "total_interactions": total_interactions,
            "llm_interactions": llm_interactions,
            "mcp_communications": mcp_communications,
            "system_events": system_events,
            "errors_count": errors_count,
            "total_duration_ms": total_duration_ms,
            "chain_statistics": {
                "total_stages": total_stages,
                "completed_stages": completed_stages,
                "failed_stages": failed_stages,
                "stages_by_agent": stages_by_agent
            }
        }
    

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
            
            result = self._retry_database_operation(
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
                    logger.warning("History repository unavailable - stage execution not retrieved")
                    return None
                return repo.get_stage_execution(execution_id)
        
        result = self._retry_database_operation(
            "get_stage_execution",
            _get_stage_execution_operation,
            treat_none_as_success=True,
        )
        return result
    
    # LLM Interaction Logging
    def log_llm_interaction(self, interaction: LLMInteraction) -> bool:
        """
        Log an LLM interaction using unified model.
        
        Args:
            interaction: LLMInteraction instance with all interaction details
            
        Returns:
            True if logged successfully, False otherwise
        """
        if not self.is_enabled or not interaction.session_id:
            return False
            
        try:
            with self.get_repository() as repo:
                if not repo:
                    logger.warning("History repository unavailable - LLM interaction not logged")
                    return False
                
                # Set step description if not already set
                if not interaction.step_description:
                    model_name = (
                        getattr(interaction, "model_name", None) or
                        getattr(getattr(interaction, "details", None), "model_name", None) or
                        "LLM"
                    )
                    interaction.step_description = f"LLM analysis using {model_name}"
                
                repo.create_llm_interaction(interaction)
                logger.debug(f"Logged LLM interaction for session {interaction.session_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to log LLM interaction for session {interaction.session_id}: {str(e)}")
            return False

    
    # MCP Communication Logging
    def log_mcp_interaction(self, interaction: MCPInteraction) -> bool:
        """
        Log an MCP interaction using unified model.
        
        Args:
            interaction: MCPInteraction instance with all interaction details
            
        Returns:
            True if logged successfully, False otherwise
        """
        if not self.is_enabled or not interaction.session_id:
            return False
            
        try:
            with self.get_repository() as repo:
                if not repo:
                    logger.warning("History repository unavailable - MCP communication not logged")
                    return False
                
                # Set step description if not already set
                if not interaction.step_description:
                    interaction.step_description = interaction.get_step_description()
                
                repo.create_mcp_communication(interaction)
                logger.debug(f"Logged MCP communication for session {interaction.session_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to log MCP communication for session {interaction.session_id}: {str(e)}")
            return False

    
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
                    return None
                
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
                    return False
                
                # Try to perform a simple database operation
                # This will test both connection and basic functionality
                repo.get_alert_sessions(page=1, page_size=1)
                # Result is now PaginatedSessions model or None
                return True
                
        except Exception as e:
            logger.error(f"Database connection test failed: {str(e)}")
            return False

    def get_session_timeline(self, session_id: str) -> Optional[DetailedSession]:
        """
        Get complete session timeline - returns DetailedSession model directly for controllers.
        
        Args:
            session_id: The session identifier
            
        Returns:
            DetailedSession model or None if not found
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    return None
                
                detailed_session = repo.get_session_timeline(session_id)
                return detailed_session
                
        except Exception as e:
            logger.error(f"Failed to get session timeline for {session_id}: {str(e)}")
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
                    return []
                
                return repo.get_active_sessions()
                
        except Exception as e:
            logger.error(f"Failed to get active sessions: {str(e)}")
            return []

    def get_filter_options(self) -> FilterOptions:
        """
        Get available filter options for the dashboard - returns FilterOptions model for controllers.
        
        Returns:
            FilterOptions model
        """
        try:
            with self.get_repository() as repo:
                if not repo:
                    # Create default FilterOptions model
                    from tarsy.models.history_models import FilterOptions, TimeRangeOption
                    default_options = FilterOptions(
                        agent_types=[],
                        alert_types=[],
                        status_options=AlertSessionStatus.values(),
                        time_ranges=[
                            TimeRangeOption(label="Last Hour", value="1h"),
                            TimeRangeOption(label="Last 4 Hours", value="4h"),
                            TimeRangeOption(label="Today", value="today"),
                            TimeRangeOption(label="This Week", value="week")
                        ]
                    )
                    return default_options
                
                filter_options = repo.get_filter_options()
                return filter_options
                
        except Exception as e:
            logger.error(f"Failed to get filter options: {str(e)}")
            # Return default options on error
            from tarsy.models.history_models import FilterOptions, TimeRangeOption
            default_options = FilterOptions(
                agent_types=[],
                alert_types=[],
                status_options=AlertSessionStatus.values(),
                time_ranges=[
                    TimeRangeOption(label="Last Hour", value="1h"),
                    TimeRangeOption(label="Last 4 Hours", value="4h"),
                    TimeRangeOption(label="Today", value="today"),
                    TimeRangeOption(label="This Week", value="week")
                ]
            )
            return default_options

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
                    logger.warning("History repository unavailable - cannot cleanup orphaned sessions")
                    return 0
                
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