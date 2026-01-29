"""Conversation history and formatting operations."""

import json
import logging
from typing import Optional, Tuple, Union

from tarsy.models.db_models import AlertSession
from tarsy.models.history_models import ConversationMessage, LLMConversationHistory
from tarsy.models.unified_interactions import LLMInteraction
from tarsy.services.history_service.base_infrastructure import (
    BaseHistoryInfra,
    NO_INTERACTIONS,
    _NoInteractionsSentinel,
)

logger = logging.getLogger(__name__)


class ConversationOperations:
    """Conversation history formatting operations."""
    
    def __init__(self, infra: BaseHistoryInfra) -> None:
        self._infra: BaseHistoryInfra = infra
    
    def get_session_conversation_history(
        self,
        session_id: str,
        include_chat: bool = False
    ) -> Tuple[Optional[LLMConversationHistory], Optional[LLMConversationHistory]]:
        """Get LLM conversation history for a session and optionally its chat.
        
        Retrieves the conversation history from the most recent LLM interaction
        that includes conversation data. Optionally retrieves chat conversation
        history as well.
        
        Args:
            session_id: Unique identifier of the session.
            include_chat: If True, also retrieves conversation history for the
                session's associated chat (if one exists).
        
        Returns:
            A tuple of (session_conversation, chat_conversation). Either or both
            may be None if no conversation history is found.
        """
        def _get_conversation_history() -> Tuple[Optional[LLMConversationHistory], Optional[LLMConversationHistory]]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return None, None
                
                session_interaction = repo.get_last_llm_interaction_with_conversation(
                    session_id=session_id,
                    prefer_final_analysis=True,
                    chat_id=None
                )
                session_conversation = self._build_conversation_history(session_interaction)
                
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
        
        result = self._infra._retry_database_operation(
            "get_session_conversation_history",
            _get_conversation_history
        )
        return result if result else (None, None)
    
    def _build_conversation_history(
        self,
        interaction: Optional[LLMInteraction]
    ) -> Optional[LLMConversationHistory]:
        """Build LLMConversationHistory from an LLMInteraction."""
        if not interaction or not interaction.conversation:
            return None
        
        try:
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
    
    def get_formatted_session_conversation(
        self,
        session_id: str,
        exclude_chat_stages: bool = True,
        include_thinking: bool = False
    ) -> str:
        """Get formatted conversation text for any session.
        
        Retrieves and formats the conversation history as human-readable text,
        suitable for display or use as context in subsequent interactions.
        
        Args:
            session_id: Unique identifier of the session.
            exclude_chat_stages: If True, excludes interactions from chat stages
                from the formatted output.
            include_thinking: If True, includes model thinking/reasoning content
                in the formatted output.
        
        Returns:
            Formatted conversation text.
        
        Raises:
            ValueError: If no LLM interactions are found for the session or if
                the operation fails.
        """
        def _get_formatted_conversation() -> Union[str, _NoInteractionsSentinel, None]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return None
                
                all_interactions = repo.get_llm_interactions_for_session(
                    session_id=session_id,
                    exclude_chat_stages=exclude_chat_stages
                )
                
                if not all_interactions:
                    return NO_INTERACTIONS
                
                from tarsy.models.constants import CHAT_CONTEXT_INTERACTION_TYPES
                
                valid_interactions = [
                    interaction for interaction in all_interactions
                    if (interaction.conversation is not None and 
                        interaction.interaction_type in CHAT_CONTEXT_INTERACTION_TYPES)
                ]
                
                if not valid_interactions:
                    from tarsy.agents.prompts.builders import PromptBuilder
                    builder = PromptBuilder()
                    return builder.format_investigation_context(None)
                
                last_interaction = valid_interactions[-1]
                
                from tarsy.agents.prompts.builders import PromptBuilder
                builder = PromptBuilder()
                return builder.format_investigation_context(
                    conversation=last_interaction.conversation,
                    interactions=valid_interactions if include_thinking else None,
                    include_thinking=include_thinking
                )
        
        result = self._infra._retry_database_operation(
            "get_formatted_session_conversation",
            _get_formatted_conversation
        )
        
        if result is NO_INTERACTIONS:
            raise ValueError(f"No LLM interactions found for session {session_id}")
        
        if result is None:
            raise ValueError(f"Failed to get formatted conversation for session {session_id}")
        
        return result
    
    def build_comprehensive_session_history(
        self,
        session_id: str,
        include_separate_alert_section: bool = True,
        include_thinking: bool = False
    ) -> str:
        """Build comprehensive session history for external analysis.
        
        Creates a complete session history document including alert information
        and full conversation history, formatted for external analysis or
        documentation purposes.
        
        Args:
            session_id: Unique identifier of the session.
            include_separate_alert_section: If True, includes a dedicated section
                with alert metadata and data at the beginning of the output.
            include_thinking: If True, includes model thinking/reasoning content
                in the conversation output.
        
        Returns:
            Complete formatted session history as a string.
        
        Raises:
            ValueError: If the session is not found or if conversation retrieval
                fails.
        """
        # Verify session exists first for clearer error messages
        def _get_session() -> Optional[AlertSession]:
            with self._infra.get_repository() as repo:
                if not repo:
                    return None
                return repo.get_alert_session(session_id)
        
        session = self._infra._retry_database_operation(
            "get_session_for_history",
            _get_session,
            treat_none_as_success=True
        )
        
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        conversation_text = self.get_formatted_session_conversation(
            session_id,
            include_thinking=include_thinking
        )
        
        if not include_separate_alert_section:
            return conversation_text
        
        sections = []
        sections.append("=" * 79)
        sections.append("ALERT INFORMATION")
        sections.append("=" * 79)
        sections.append("")
        sections.append(f"**Alert Type:** {session.alert_type}")
        sections.append(f"**Session ID:** {session.session_id}")
        status_value = session.status.value if hasattr(session.status, 'value') else session.status
        sections.append(f"**Status:** {status_value}")
        sections.append("")
        sections.append("**Alert Data:**")
        sections.append("```json")
        sections.append(json.dumps(session.alert_data, indent=2))
        sections.append("```")
        sections.append("")
        sections.append(conversation_text)
        
        return "\n".join(sections)
