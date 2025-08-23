"""
ReAct iteration controller for standard investigation and analysis.

This controller follows the ReAct format:
- Question: The alert analysis question
- Thought: Agent reasons about what to do next
- Action: Agent specifies which tool to use
- Action Input: Parameters for the tool
- Observation: Results from the tool execution
- (repeat until) Final Answer: Complete analysis

This is a true ReAct implementation that follows the established pattern
that LLMs are specifically trained to handle.
"""

from typing import TYPE_CHECKING

from tarsy.models.unified_interactions import LLMMessage, LLMConversation, MessageRole
from tarsy.utils.logger import get_module_logger
from .base_controller import ReactController

if TYPE_CHECKING:
    from ...models.processing_context import StageContext

logger = get_module_logger(__name__)


class SimpleReActController(ReactController):
    """
    Standard ReAct controller for systematic investigation - only differs in prompt building.
    
    Extends ReactController and customizes only the initial conversation building.
    All ReAct loop logic is handled by the parent class.
    """
    
    def __init__(self, llm_client, prompt_builder):
        """Initialize with LLM client and prompt builder."""
        super().__init__(llm_client, prompt_builder)
        logger.info("Initialized SimpleReActController for systematic investigation")
    
    def build_initial_conversation(self, context: 'StageContext') -> LLMConversation:
        """Build initial conversation for standard ReAct investigation."""
        system_content = self.prompt_builder.get_enhanced_react_system_message(
            context.agent._compose_instructions(), 
            "investigation and providing recommendations"
        )
        user_content = self.prompt_builder.build_standard_react_prompt(context, [])
        
        return LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content=system_content),
            LLMMessage(role=MessageRole.USER, content=user_content) 
        ])

    def extract_final_analysis(self, analysis_result: str, context) -> str:
        """
        Extract final analysis from ReAct conversation for API consumption.
        
        Looks for the Final Answer in the ReAct history.
        """
        return self._extract_react_final_analysis(
            analysis_result=analysis_result,
            completion_patterns=["Analysis completed"],
            incomplete_patterns=["Analysis incomplete:"],
            fallback_message="Analysis completed but no clear final answer was provided",
            context=context
        )