"""Queue management operations."""

from typing import Optional

from tarsy.models.db_models import AlertSession
from tarsy.services.history_service.base_infrastructure import BaseHistoryInfra


class QueueOperations:
    """Session queue management operations."""
    
    def __init__(self, infra: BaseHistoryInfra) -> None:
        self._infra: BaseHistoryInfra = infra
    
    def count_sessions_by_status(self, status: str) -> int:
        """Count sessions with given status across all pods.
        
        Args:
            status: Session status value to count (e.g., 'PENDING', 'IN_PROGRESS').
        
        Returns:
            Total count of sessions with the specified status.
        """
        with self._infra.get_repository() as repo:
            if not repo:
                return 0
            return repo.count_sessions_by_status(status)
    
    def count_pending_sessions(self) -> int:
        """Count sessions in PENDING state.
        
        Returns:
            Total count of sessions waiting to be processed.
        """
        with self._infra.get_repository() as repo:
            if not repo:
                return 0
            return repo.count_pending_sessions()
    
    def claim_next_pending_session(self, pod_id: str) -> Optional[AlertSession]:
        """Atomically claim next PENDING session for this pod.
        
        Uses database-level locking to ensure only one pod can claim
        each session, preventing duplicate processing.
        
        Args:
            pod_id: Identifier of the pod attempting to claim work.
        
        Returns:
            The claimed AlertSession if one was available, None otherwise.
        """
        with self._infra.get_repository() as repo:
            if not repo:
                return None
            return repo.claim_next_pending_session(pod_id)
