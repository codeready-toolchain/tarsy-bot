"""Chat CRUD operations."""

import logging
from typing import List, Optional

from tarsy.models.db_models import Chat, ChatUserMessage, StageExecution
from tarsy.models.unified_interactions import LLMInteraction
from tarsy.services.history_service.base_infrastructure import BaseHistoryInfra

logger = logging.getLogger(__name__)


class ChatOperations:
    """Chat CRUD operations."""
    
    def __init__(self, infra: BaseHistoryInfra):
        self._infra = infra
    
    async def create_chat(self, chat: Chat) -> Chat:
        """Create a new chat record."""
        def _create_operation() -> Chat:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise ValueError("Repository unavailable")
                return repo.create_chat(chat)
        
        result = self._infra._retry_database_operation("create_chat", _create_operation)
        if result is None:
            raise ValueError("Failed to create chat")
        return result
    
    async def get_chat_by_id(self, chat_id: str) -> Optional[Chat]:
        """Get chat by ID."""
        def _get_operation() -> Optional[Chat]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return None
                return repo.get_chat_by_id(chat_id)
        
        return self._infra._retry_database_operation(
            "get_chat_by_id",
            _get_operation,
            treat_none_as_success=True
        )
    
    async def get_chat_by_session(self, session_id: str) -> Optional[Chat]:
        """Get chat for a session (if exists)."""
        def _get_operation() -> Optional[Chat]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return None
                return repo.get_chat_by_session(session_id)
        
        return self._infra._retry_database_operation(
            "get_chat_by_session",
            _get_operation,
            treat_none_as_success=True
        )
    
    async def create_chat_user_message(self, message: ChatUserMessage) -> ChatUserMessage:
        """Create a new chat user message."""
        def _create_operation() -> ChatUserMessage:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise ValueError("Repository unavailable")
                return repo.create_chat_user_message(message)
        
        result = self._infra._retry_database_operation("create_chat_user_message", _create_operation)
        if result is None:
            raise ValueError("Failed to create chat user message")
        return result
    
    async def get_stage_executions_for_chat(self, chat_id: str) -> List[StageExecution]:
        """Get all stage executions for a chat."""
        def _get_operation() -> List[StageExecution]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return []
                return repo.get_stage_executions_for_chat(chat_id)
        
        return self._infra._retry_database_operation(
            "get_stage_executions_for_chat",
            _get_operation
        ) or []
    
    async def has_llm_interactions(self, session_id: str) -> bool:
        """Check if session has any LLM interactions."""
        def _has_operation() -> bool:
            with self._infra.get_repository() as repo:
                if not repo:
                    return False
                return repo.has_llm_interactions(session_id)
        
        return await self._infra._retry_database_operation_async(
            "has_llm_interactions",
            _has_operation
        ) or False
    
    async def get_llm_interactions_for_session(self, session_id: str) -> List[LLMInteraction]:
        """Get all LLM interactions for a session."""
        def _get_operation() -> List[LLMInteraction]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return []
                return repo.get_llm_interactions_for_session(session_id)
        
        return self._infra._retry_database_operation(
            "get_llm_interactions_for_session",
            _get_operation
        ) or []
    
    async def get_llm_interactions_for_stage(self, stage_execution_id: str) -> List[LLMInteraction]:
        """Get all LLM interactions for a stage execution."""
        def _get_operation() -> List[LLMInteraction]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return []
                return repo.get_llm_interactions_for_stage(stage_execution_id)
        
        return self._infra._retry_database_operation(
            "get_llm_interactions_for_stage",
            _get_operation
        ) or []
    
    async def get_chat_user_message_count(self, chat_id: str) -> int:
        """Get total user message count for a chat."""
        def _count_operation() -> int:
            with self._infra.get_repository() as repo:
                if not repo:
                    return 0
                return repo.get_chat_user_message_count(chat_id)
        
        return self._infra._retry_database_operation(
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
        def _get_operation() -> List[ChatUserMessage]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return []
                return repo.get_chat_user_messages(chat_id, limit, offset)
        
        return self._infra._retry_database_operation(
            "get_chat_user_messages",
            _get_operation
        ) or []
