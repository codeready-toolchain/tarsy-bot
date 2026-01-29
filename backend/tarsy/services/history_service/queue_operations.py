"""Queue management operations."""

from typing import Optional

from tarsy.models.db_models import AlertSession
from tarsy.services.history_service.base_infrastructure import BaseHistoryInfra


class QueueOperations:
    """Session queue management operations."""
    
    def __init__(self, infra: BaseHistoryInfra):
        self._infra = infra
    
    def count_sessions_by_status(self, status: str) -> int:
        """Count sessions with given status across all pods."""
        with self._infra.get_repository() as repo:
            if not repo:
                return 0
            return repo.count_sessions_by_status(status)
    
    def count_pending_sessions(self) -> int:
        """Count sessions in PENDING state."""
        with self._infra.get_repository() as repo:
            if not repo:
                return 0
            return repo.count_pending_sessions()
    
    def claim_next_pending_session(self, pod_id: str) -> Optional[AlertSession]:
        """Atomically claim next PENDING session for this pod."""
        with self._infra.get_repository() as repo:
            if not repo:
                return None
            return repo.claim_next_pending_session(pod_id)
