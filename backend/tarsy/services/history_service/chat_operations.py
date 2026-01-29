"""Chat CRUD operations."""

import logging
from typing import List, Optional

from tarsy.models.db_models import Chat, ChatUserMessage, StageExecution
from tarsy.models.unified_interactions import LLMInteraction
from tarsy.services.history_service.base_infrastructure import BaseHistoryInfra

logger = logging.getLogger(__name__)


class ChatOperations:
    """Chat CRUD operations."""
    
    def __init__(self, infra: BaseHistoryInfra) -> None:
        self._infra: BaseHistoryInfra = infra
    
    async def create_chat(self, chat: Chat) -> Chat:
        """Create a new chat record.
        
        Args:
            chat: Chat model instance to persist.
        
        Returns:
            The created Chat record with database-assigned fields populated.
        
        Raises:
            ValueError: If the chat could not be created.
        """
        def _create_operation() -> Chat:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise ValueError("Repository unavailable")
                return repo.create_chat(chat)
        
        result = await self._infra._retry_database_operation_async("create_chat", _create_operation)
        if result is None:
            raise ValueError("Failed to create chat")
        return result
    
    async def get_chat_by_id(self, chat_id: str) -> Optional[Chat]:
        """Get chat by ID.
        
        Args:
            chat_id: Unique identifier of the chat to retrieve.
        
        Returns:
            The Chat record if found, None otherwise.
        """
        def _get_operation() -> Optional[Chat]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return None
                return repo.get_chat_by_id(chat_id)
        
        return await self._infra._retry_database_operation_async(
            "get_chat_by_id",
            _get_operation,
            treat_none_as_success=True,
        )
    
    async def get_chat_by_session(self, session_id: str) -> Optional[Chat]:
        """Get chat for a session (if exists).
        
        Args:
            session_id: Unique identifier of the session.
        
        Returns:
            The Chat record associated with the session, or None if no chat exists.
        """
        def _get_operation() -> Optional[Chat]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return None
                return repo.get_chat_by_session(session_id)
        
        return await self._infra._retry_database_operation_async(
            "get_chat_by_session",
            _get_operation,
            treat_none_as_success=True,
        )
    
    async def create_chat_user_message(self, message: ChatUserMessage) -> ChatUserMessage:
        """Create a new chat user message.
        
        Args:
            message: ChatUserMessage model instance to persist.
        
        Returns:
            The created ChatUserMessage record.
        
        Raises:
            ValueError: If the message could not be created.
        """
        def _create_operation() -> ChatUserMessage:
            with self._infra.get_repository() as repo:
                if not repo:
                    raise ValueError("Repository unavailable")
                return repo.create_chat_user_message(message)
        
        result = await self._infra._retry_database_operation_async("create_chat_user_message", _create_operation)
        if result is None:
            raise ValueError("Failed to create chat user message")
        return result
    
    async def get_stage_executions_for_chat(self, chat_id: str) -> List[StageExecution]:
        """Get all stage executions for a chat.
        
        Args:
            chat_id: Unique identifier of the chat.
        
        Returns:
            List of StageExecution records for the chat, empty list if none found.
        """
        def _get_operation() -> List[StageExecution]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return []
                return repo.get_stage_executions_for_chat(chat_id)
        
        return await self._infra._retry_database_operation_async(
            "get_stage_executions_for_chat",
            _get_operation,
        ) or []
    
    async def has_llm_interactions(self, session_id: str) -> bool:
        """Check if session has any LLM interactions.
        
        Args:
            session_id: Unique identifier of the session.
        
        Returns:
            True if the session has at least one LLM interaction, False otherwise.
        """
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
        """Get all LLM interactions for a session.
        
        Args:
            session_id: Unique identifier of the session.
        
        Returns:
            List of LLMInteraction records for the session, empty list if none found.
        """
        def _get_operation() -> List[LLMInteraction]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return []
                return repo.get_llm_interactions_for_session(session_id)
        
        return await self._infra._retry_database_operation_async(
            "get_llm_interactions_for_session",
            _get_operation,
        ) or []
    
    async def get_llm_interactions_for_stage(self, stage_execution_id: str) -> List[LLMInteraction]:
        """Get all LLM interactions for a stage execution.
        
        Args:
            stage_execution_id: Unique identifier of the stage execution.
        
        Returns:
            List of LLMInteraction records for the stage, empty list if none found.
        """
        def _get_operation() -> List[LLMInteraction]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return []
                return repo.get_llm_interactions_for_stage(stage_execution_id)
        
        return await self._infra._retry_database_operation_async(
            "get_llm_interactions_for_stage",
            _get_operation,
        ) or []
    
    async def get_chat_user_message_count(self, chat_id: str) -> int:
        """Get total user message count for a chat.
        
        Args:
            chat_id: Unique identifier of the chat.
        
        Returns:
            Total number of user messages in the chat.
        """
        def _count_operation() -> int:
            with self._infra.get_repository() as repo:
                if not repo:
                    return 0
                return repo.get_chat_user_message_count(chat_id)
        
        return await self._infra._retry_database_operation_async(
            "get_chat_user_message_count",
            _count_operation,
        ) or 0
    
    async def get_chat_user_messages(
        self,
        chat_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ChatUserMessage]:
        """Get user messages for a chat with pagination.
        
        Args:
            chat_id: Unique identifier of the chat.
            limit: Maximum number of messages to return. Defaults to 50.
            offset: Number of messages to skip for pagination. Defaults to 0.
        
        Returns:
            List of ChatUserMessage records, empty list if none found.
        """
        def _get_operation() -> List[ChatUserMessage]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return []
                return repo.get_chat_user_messages(chat_id, limit, offset)
        
        return await self._infra._retry_database_operation_async(
            "get_chat_user_messages",
            _get_operation,
        ) or []
