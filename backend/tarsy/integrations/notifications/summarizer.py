"""
Executive Summary Agent for generating concise final analysis summaries.

This lightweight agent creates AI-powered summaries after chain completion,
displayed in the dashboard reasoning view and used in external notifications (Slack, etc.).
"""

from typing import TYPE_CHECKING, Optional

from tarsy.agents.prompts.builders import PromptBuilder
from tarsy.models.constants import LLMInteractionType
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    from tarsy.integrations.llm.manager import LLMManager

logger = get_module_logger(__name__)


class ExecutiveSummaryAgent:
    """
    Lightweight agent for generating concise executive summaries of completed alert investigations.
    
    This agent uses LLM to create executive summaries displayed in the dashboard
    and used in external notifications (Slack, etc.).
    """
    
    def __init__(self, llm_manager: 'LLMManager'):
        """
        Initialize summarizer with LLM manager and prompt builder.
        
        Args:
            llm_manager: The LLM manager to use for summarization
        """
        self.llm_manager = llm_manager
        self.prompt_builder = PromptBuilder()
    
    async def generate_executive_summary(
        self,
        content: str,
        session_id: str,
        stage_execution_id: Optional[str] = None,
        max_tokens: int = 150,
        provider: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate a concise executive summary of the content.
        
        This executive summary is displayed in the dashboard reasoning view
        and used in external notifications (Slack, etc.) where brevity is crucial.
        
        Args:
            content: The content to generate an executive summary
            session_id: Session ID for tracking
            stage_execution_id: Optional stage execution ID (typically None for post-chain)
            max_tokens: Maximum tokens for executive summary (default: 150)
            provider: Optional LLM provider name (uses chain's provider or global default)
            
        Returns:
            Concise executive summary string, or None if generation fails
            
        Raises:
            ValueError: If content is empty or None
        """
        if not content:
            raise ValueError("Cannot generate executive summary: content is required and cannot be empty")
        
        try:
            # Build summarization prompt using the existing builder
            summary_prompt = self.prompt_builder.build_final_analysis_summary_prompt(content)
            # Create user message with the prompt
            user_message = LLMMessage(
                role=MessageRole.USER,
                content=summary_prompt
            )
            
            # Create system message with the system prompt
            system_content = self.prompt_builder.build_final_analysis_summary_system_prompt()
            system_message = LLMMessage(
                role=MessageRole.SYSTEM,
                content=system_content
            )
            
            # Create conversation with both messages
            conversation = LLMConversation(messages=[system_message, user_message])
            
            # Generate summary using LLM manager with RESULT_SUMMARY interaction type
            # Pass provider to use chain-level or global default
            response_conversation = await self.llm_manager.generate_response(
                conversation=conversation,
                session_id=session_id,
                stage_execution_id=stage_execution_id,
                provider=provider,
                max_tokens=max_tokens,
                interaction_type=LLMInteractionType.FINAL_ANALYSIS_SUMMARY.value  # Type dedicated to Final Analysis Summaries only
            )
            
            # Extract summary from response
            assistant_message = response_conversation.get_latest_assistant_message()
            if not assistant_message:
                logger.error("No assistant response received for executive summary generation")
                return None
            
            executive_summary = assistant_message.content.strip()

            logger.info(f"Generated executive summary for session {session_id}: {executive_summary[:100]}...")
            return executive_summary
            
        except Exception as e:
            logger.error(f"Failed to generate executive summary for session {session_id}: {e}")
            return None
