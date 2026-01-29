"""Session lifecycle operations."""

import logging
from typing import Optional

from tarsy.models.agent_config import ChainConfigModel
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession
from tarsy.models.processing_context import ChainContext
from tarsy.services.history_service.base_infrastructure import BaseHistoryInfra
from tarsy.utils.timestamp import now_us

logger = logging.getLogger(__name__)


class SessionOperations:
    """Session lifecycle operations."""
    
    def __init__(self, infra: BaseHistoryInfra) -> None:
        self._infra: BaseHistoryInfra = infra
    
    def create_session(
        self,
        chain_context: ChainContext,
        chain_definition: ChainConfigModel
    ) -> bool:
        """Create a new alert processing session."""
        def _create_session_operation() -> bool:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot create session")
                
                agent_type = f"chain:{chain_definition.chain_id}"
                
                session = AlertSession(
                    session_id=chain_context.session_id,
                    alert_data=chain_context.processing_alert.alert_data,
                    agent_type=agent_type,
                    alert_type=chain_context.processing_alert.alert_type,
                    status=AlertSessionStatus.PENDING.value,
                    chain_id=chain_definition.chain_id,
                    chain_definition=chain_definition.model_dump(),
                    author=chain_context.author,
                    runbook_url=chain_context.processing_alert.runbook_url,
                    mcp_selection=chain_context.mcp.model_dump() if chain_context.mcp else None
                )
                
                created_session = repo.create_alert_session(session)
                if created_session:
                    logger.info(f"Created history session {created_session.session_id}")
                    return True
                return False
        
        result = self._infra._retry_database_operation("create_session", _create_session_operation)
        return result if result is not None else False
    
    def update_session_status(
        self,
        session_id: str,
        status: str,
        error_message: Optional[str] = None,
        final_analysis: Optional[str] = None,
        final_analysis_summary: Optional[str] = None,
        executive_summary_error: Optional[str] = None,
        pause_metadata: Optional[dict] = None
    ) -> bool:
        """Update session processing status."""
        if not session_id:
            return False
        
        def _update_status_operation() -> bool:
            with self._infra.get_repository() as repo:
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
                if executive_summary_error:
                    session.executive_summary_error = executive_summary_error
                if status == AlertSessionStatus.PAUSED.value:
                    session.pause_metadata = pause_metadata
                else:
                    session.pause_metadata = None
                if status in AlertSessionStatus.terminal_values():
                    session.completed_at_us = now_us()
                
                success = repo.update_alert_session(session)
                if success:
                    logger.debug(f"Updated session {session_id} status to {status}")
                        
                return success
        
        result = self._infra._retry_database_operation("update_session_status", _update_status_operation)
        return result if result is not None else False
    
    def get_session(self, session_id: str) -> Optional[AlertSession]:
        """Get session by ID."""
        if not session_id:
            return None
        
        def _get_operation() -> Optional[AlertSession]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return None
                return repo.get_alert_session(session_id)
        
        return self._infra._retry_database_operation(
            "get_session",
            _get_operation,
            treat_none_as_success=True
        )
    
    def update_session_to_canceling(self, session_id: str) -> tuple[bool, str]:
        """Atomically update session to CANCELING if not already terminal."""
        if not session_id:
            return (False, "unknown")
        
        def _update_operation() -> tuple[bool, str]:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable")
                
                session = repo.get_alert_session(session_id)
                if not session:
                    return (False, "not_found")
                
                if session.status in AlertSessionStatus.terminal_values():
                    logger.info(f"Session {session_id} already terminal: {session.status}")
                    return (False, session.status)
                
                if session.status == AlertSessionStatus.CANCELING.value:
                    logger.info(f"Session {session_id} already canceling")
                    return (True, session.status)
                
                session.status = AlertSessionStatus.CANCELING.value
                success = repo.update_alert_session(session)
                
                if success:
                    logger.info(f"Updated session {session_id} to CANCELING")
                    return (True, AlertSessionStatus.CANCELING.value)
                
                return (False, session.status)
        
        result = self._infra._retry_database_operation("update_to_canceling", _update_operation)
        return result if result else (False, "error")
