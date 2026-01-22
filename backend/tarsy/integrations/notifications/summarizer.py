"""
Executive Summary Agent for generating concise final analysis summaries.

This lightweight agent creates AI-powered summaries after chain completion,
displayed in the dashboard reasoning view and used in external notifications (Slack, etc.).
"""

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from tarsy.agents.prompts.builders import PromptBuilder
from tarsy.models.constants import LLMInteractionType
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    from tarsy.config.settings import Settings
    from tarsy.integrations.llm.manager import LLMManager

logger = get_module_logger(__name__)


@dataclass
class ExecutiveSummaryResult:
    """Result of executive summary generation with success/error tracking."""
    
    summary: Optional[str]
    """The generated executive summary, or None if generation failed."""
    
    error: Optional[str]
    """Error message if generation failed, None if successful."""


class ExecutiveSummaryAgent:
    """
    Lightweight agent for generating concise executive summaries of completed alert investigations.
    
    This agent uses LLM to create executive summaries displayed in the dashboard
    and used in external notifications (Slack, etc.).
    """
    
    def __init__(self, llm_manager: 'LLMManager', settings: 'Settings'):
        """
        Initialize summarizer with LLM manager, settings, and prompt builder.
        
        Args:
            llm_manager: The LLM manager to use for summarization
            settings: Settings containing timeout configuration
        """
        self.llm_manager = llm_manager
        self.settings = settings
        self.prompt_builder = PromptBuilder()
    
    async def generate_executive_summary(
        self,
        content: str,
        session_id: str,
        stage_execution_id: Optional[str] = None,
        max_tokens: int = 150,
        provider: Optional[str] = None
    ) -> ExecutiveSummaryResult:
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
            ExecutiveSummaryResult with summary string or error message
            
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
            
            # Generate summary using LLM manager with timeout protection
            # Use llm_iteration_timeout as executive summary generation is an LLM call
            try:
                response_conversation = await asyncio.wait_for(
                    self.llm_manager.generate_response(
                        conversation=conversation,
                        session_id=session_id,
                        stage_execution_id=stage_execution_id,
                        provider=provider,
                        max_tokens=max_tokens,
                        interaction_type=LLMInteractionType.FINAL_ANALYSIS_SUMMARY.value
                    ),
                    timeout=self.settings.llm_iteration_timeout
                )
            except asyncio.TimeoutError:
                error_msg = f"Executive summary generation timed out after {self.settings.llm_iteration_timeout}s"
                logger.warning(f"{error_msg} for session {session_id}")
                return ExecutiveSummaryResult(summary=None, error=error_msg)
            except asyncio.CancelledError as e:
                # Task was cancelled (timeout or user request) - return error gracefully
                from tarsy.utils.agent_execution_utils import extract_cancellation_reason
                reason = extract_cancellation_reason(e)
                error_msg = f"Cancelled ({reason})"
                logger.warning(
                    f"Executive summary generation cancelled ({reason}) for session {session_id}"
                )
                return ExecutiveSummaryResult(summary=None, error=error_msg)
            
            # Extract summary from response
            assistant_message = response_conversation.get_latest_assistant_message()
            if not assistant_message:
                error_msg = "No assistant response received"
                logger.error(f"{error_msg} for executive summary generation")
                return ExecutiveSummaryResult(summary=None, error=error_msg)
            
            executive_summary = assistant_message.content.strip()

            logger.info(f"Generated executive summary for session {session_id}: {executive_summary[:100]}...")
            return ExecutiveSummaryResult(summary=executive_summary, error=None)
            
        except Exception as e:
            error_msg = str(e) or type(e).__name__
            logger.error(f"Failed to generate executive summary for session {session_id}: {e}")
            return ExecutiveSummaryResult(summary=None, error=error_msg)
