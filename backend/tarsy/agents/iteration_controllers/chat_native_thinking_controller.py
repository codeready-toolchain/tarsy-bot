"""
Native thinking iteration controller for chat conversations.

This controller uses Gemini's native thinking capabilities for follow-up chat
conversations, building initial conversation with historical context from
completed investigations.
"""

from typing import TYPE_CHECKING

from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.utils.logger import get_module_logger

from .native_thinking_controller import NativeThinkingController

if TYPE_CHECKING:
    from tarsy.models.processing_context import StageContext

logger = get_module_logger(__name__)


class ChatNativeThinkingController(NativeThinkingController):
    """
    Native thinking controller for chat with conversation history context.
    
    Differs from standard NativeThinkingController by building initial 
    conversation with complete investigation history from the session, 
    enabling the LLM to answer follow-up questions with full context.
    
    Uses Gemini's native thinking and function calling (no ReAct parsing).
    """
    
    def __init__(self, llm_manager, prompt_builder):
        """
        Initialize with LLM manager and prompt builder.
        
        Args:
            llm_manager: LLM manager (default client must be Google/Gemini)
            prompt_builder: Prompt builder for creating prompts
        """
        super().__init__(llm_manager, prompt_builder)
        logger.info("Initialized ChatNativeThinkingController for follow-up conversations")
    
    def _build_initial_conversation(self, context: 'StageContext') -> LLMConversation:
        """
        Build initial conversation for chat with history context.
        
        Gets conversation history and user question from StageContext.chat_context
        and formats them appropriately for native thinking.
        
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
        
        # System message with native thinking chat instructions
        system_content = self.prompt_builder.get_native_thinking_system_message(
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
    
    def extract_final_analysis(self, analysis_result: str, context: 'StageContext') -> str:
        """
        Extract final answer from native thinking conversation.
        
        For native thinking, the result is already clean (no ReAct markers).
        
        Args:
            analysis_result: Analysis result from native thinking loop
            context: StageContext (unused but kept for interface compatibility)
            
        Returns:
            Extracted final analysis for the chat response
        """
        if not analysis_result:
            return "No response generated"
        
        return analysis_result

