"""Maintenance and cleanup operations."""

import logging

from sqlmodel import select

from tarsy.models.constants import AlertSessionStatus, StageStatus
from tarsy.models.db_models import StageExecution
from tarsy.repositories.history_repository import HistoryRepository
from tarsy.services.history_service.base_infrastructure import BaseHistoryInfra
from tarsy.utils.timestamp import now_us

logger = logging.getLogger(__name__)


class MaintenanceOperations:
    """Cleanup and maintenance operations."""
    
    def __init__(self, infra: BaseHistoryInfra) -> None:
        self._infra: BaseHistoryInfra = infra
    
    def _cleanup_orphaned_stages_for_session(self, repo: HistoryRepository, session_id: str) -> int:
        """Mark all non-terminal stages in a session as failed."""
        try:
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
                    stage.status = StageStatus.FAILED.value
                    stage.error_message = "Session terminated due to backend restart"
                    stage.completed_at_us = current_time
                    
                    if stage.started_at_us and stage.completed_at_us:
                        stage.duration_ms = int((stage.completed_at_us - stage.started_at_us) / 1000)
                    
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
        """Find and mark orphaned sessions as failed based on inactivity timeout.
        
        Sessions that have been inactive longer than the timeout are marked as failed
        with an appropriate error message. Their active stages are also cleaned up.
        
        Args:
            timeout_minutes: Minutes of inactivity before a session is considered
                orphaned. Defaults to 30.
        
        Returns:
            Number of orphaned sessions that were cleaned up.
        """
        def _cleanup_operation():
            with self._infra.get_repository() as repo:
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
                    
                    # Also mark orphaned stages as failed for this session
                    self._cleanup_orphaned_stages_for_session(repo, session_record.session_id)
                
                return len(orphaned_sessions)
        
        count = self._infra._retry_database_operation("cleanup_orphaned_sessions", _cleanup_operation)
        
        if count and count > 0:
            logger.info(f"Cleaned up {count} orphaned sessions during startup")
        
        return count or 0
    
    async def mark_pod_sessions_interrupted(self, pod_id: str) -> int:
        """Mark sessions being processed by a pod as failed during graceful shutdown.
        
        Called during pod shutdown to mark all in-progress sessions as failed
        so they can be picked up by another pod or retried.
        
        Args:
            pod_id: Identifier of the pod that is shutting down.
        
        Returns:
            Number of sessions that were marked as interrupted.
        """
        def _interrupt_operation():
            with self._infra.get_repository() as repo:
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
        
        count = await self._infra._retry_database_operation_async(
            "mark_interrupted_sessions", _interrupt_operation
        )
        
        if count and count > 0:
            logger.info(f"Marked {count} sessions as failed (interrupted) for pod {pod_id}")
        
        return count or 0
    
    async def start_session_processing(self, session_id: str, pod_id: str) -> bool:
        """Mark session as being processed by a specific pod.
        
        Updates the session's pod tracking information and sets status to IN_PROGRESS.
        
        Args:
            session_id: Unique identifier of the session to start processing.
            pod_id: Identifier of the pod that will process this session.
        
        Returns:
            True if the session was successfully marked as processing, False otherwise.
        """
        def _start_operation():
            with self._infra.get_repository() as repo:
                if not repo:
                    return False
                return repo.update_session_pod_tracking(
                    session_id, 
                    pod_id, 
                    AlertSessionStatus.IN_PROGRESS.value
                )
        
        result = await self._infra._retry_database_operation_async(
            "start_session_processing", _start_operation
        )
        return result or False
    
    def record_session_interaction(self, session_id: str) -> bool:
        """Update session last_interaction_at timestamp.
        
        Called to record activity on a session, preventing it from being
        marked as orphaned during cleanup.
        
        Args:
            session_id: Unique identifier of the session to update.
        
        Returns:
            True if the timestamp was successfully updated, False otherwise.
        """
        def _interaction_operation():
            with self._infra.get_repository() as repo:
                if not repo:
                    return False
                
                session = repo.get_alert_session(session_id)
                if not session:
                    return False
                
                session.last_interaction_at = now_us()
                return repo.update_alert_session(session)
        
        return self._infra._retry_database_operation("record_interaction", _interaction_operation) or False
