"""
ReAct iteration controller for chat conversations.

This controller follows the ReAct format specifically for follow-up chat conversations,
building initial conversation with historical context from completed investigations.
"""

from typing import TYPE_CHECKING

from tarsy.models.unified_interactions import LLMMessage, LLMConversation, MessageRole
from tarsy.utils.logger import get_module_logger
from .base_controller import ReactController

if TYPE_CHECKING:
    from tarsy.models.processing_context import StageContext

logger = get_module_logger(__name__)


class ChatReActController(ReactController):
    """
    ReAct controller for chat with conversation history context.
    
    Differs from standard ReAct by building initial conversation with
    complete investigation history from the session, enabling the LLM
    to answer follow-up questions with full context.
    """
    
    def __init__(self, llm_client, prompt_builder):
        """Initialize with LLM client and prompt builder."""
        super().__init__(llm_client, prompt_builder)
        logger.info("Initialized ChatReActController for follow-up conversations")
    
    def build_initial_conversation(self, context: 'StageContext') -> LLMConversation:
        """
        Build initial conversation for chat with history context.
        
        Gets conversation history and user question from StageContext.chat_context
        and formats them appropriately for the ReAct loop.
        
        Args:
            context: StageContext with chat_context populated
            
        Returns:
            LLMConversation with system message and user message containing history
            
        Raises:
            ValueError: If chat context is missing from chain context
        """
        # Get chat context from StageContext (type-safe!)
        if not context.chain_context.chat_context:
            raise ValueError("Chat context missing from chain context")
        
        chat_context = context.chain_context.chat_context
        
        # System message with chat instructions
        system_content = self.prompt_builder.get_enhanced_react_system_message(
            context.agent._compose_instructions(),
            "answering follow-up questions about a completed investigation"
        )
        
        # User message with history + question (delegated to prompt builder)
        # conversation_history already contains formatted investigation + optional chat history
        user_content = self.prompt_builder.build_chat_user_message(
            investigation_context=chat_context.conversation_history,
            user_question=chat_context.user_question
        )
        
        return LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content=system_content),
            LLMMessage(role=MessageRole.USER, content=user_content)
        ])
    
    def extract_final_analysis(self, analysis_result: str, context) -> str:
        """
        Extract final answer from ReAct conversation.
        
        Uses the parent class's ReAct parser to extract the Final Answer
        section from the last assistant message.
        
        Args:
            analysis_result: Last assistant message containing the Final Answer
            context: StageContext (unused but kept for interface compatibility)
            
        Returns:
            Extracted final analysis for the chat response
        """
        return self._extract_react_final_analysis(analysis_result)

