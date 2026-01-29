"""Pod tracking operations for sessions and chats."""

import logging

from tarsy.services.history_service.base_infrastructure import BaseHistoryInfra
from tarsy.utils.timestamp import now_us

logger = logging.getLogger(__name__)


class TrackingOperations:
    """Pod tracking for sessions and chats."""
    
    def __init__(self, infra: BaseHistoryInfra):
        self._infra = infra
    
    async def start_chat_message_processing(self, chat_id: str, pod_id: str) -> bool:
        """Mark chat as processing a message on a specific pod."""
        def _start_operation():
            with self._infra.get_repository() as repo:
                if not repo:
                    return False
                return repo.update_chat_pod_tracking(chat_id, pod_id)
        
        result = await self._infra._retry_database_operation_async(
            "start_chat_message_processing",
            _start_operation
        )
        return result or False
    
    def record_chat_interaction(self, chat_id: str) -> bool:
        """Update chat last_interaction_at timestamp."""
        def _record_operation():
            with self._infra.get_repository() as repo:
                if not repo:
                    return False
                chat = repo.get_chat_by_id(chat_id)
                if not chat:
                    return False
                chat.last_interaction_at = now_us()
                return repo.update_chat(chat)
        
        return self._infra._retry_database_operation(
            "record_chat_interaction",
            _record_operation
        ) or False
    
    def cleanup_orphaned_chats(self, timeout_minutes: int = 30) -> int:
        """Find and clear stale processing markers from orphaned chats."""
        def _cleanup_operation():
            with self._infra.get_repository() as repo:
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
        
        count = self._infra._retry_database_operation(
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
        def _interrupt_operation():
            with self._infra.get_repository() as repo:
                if not repo:
                    return 0
                
                active_chats = repo.find_chats_by_pod(pod_id)
                
                for chat in active_chats:
                    chat.pod_id = None
                    chat.last_interaction_at = None
                    repo.session.add(chat)
                repo.session.commit()
                
                return len(active_chats)
        
        count = await self._infra._retry_database_operation_async(
            "mark_interrupted_chats",
            _interrupt_operation
        )
        
        if count and count > 0:
            logger.info(f"Marked {count} chat(s) as interrupted for pod {pod_id}")
        
        return count or 0
