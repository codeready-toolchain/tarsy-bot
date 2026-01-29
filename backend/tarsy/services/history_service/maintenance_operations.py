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
    
    def __init__(self, infra: BaseHistoryInfra):
        self._infra = infra
    
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
        """Find and mark orphaned sessions as failed based on inactivity timeout."""
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
                
                return len(orphaned_sessions)
        
        count = self._infra._retry_database_operation("cleanup_orphaned_sessions", _cleanup_operation)
        
        if count and count > 0:
            logger.info(f"Cleaned up {count} orphaned sessions during startup")
        
        return count or 0
    
    async def mark_pod_sessions_interrupted(self, pod_id: str) -> int:
        """Mark sessions being processed by a pod as failed during graceful shutdown."""
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
        
        count = self._infra._retry_database_operation("mark_interrupted_sessions", _interrupt_operation)
        
        if count and count > 0:
            logger.info(f"Marked {count} sessions as failed (interrupted) for pod {pod_id}")
        
        return count or 0
    
    async def start_session_processing(self, session_id: str, pod_id: str) -> bool:
        """Mark session as being processed by a specific pod."""
        def _start_operation():
            with self._infra.get_repository() as repo:
                if not repo:
                    return False
                return repo.update_session_pod_tracking(
                    session_id, 
                    pod_id, 
                    AlertSessionStatus.IN_PROGRESS.value
                )
        
        return self._infra._retry_database_operation("start_session_processing", _start_operation) or False
    
    def record_session_interaction(self, session_id: str) -> bool:
        """Update session last_interaction_at timestamp."""
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
