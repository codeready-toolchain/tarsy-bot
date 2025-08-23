"""
ReAct Stage iteration controller for stage-specific analysis within multi-stage chains.

This controller implements the ReAct pattern for stage-specific data collection and 
analysis, providing incremental insights during chain processing.
"""

from typing import TYPE_CHECKING

from tarsy.utils.logger import get_module_logger
from tarsy.models.unified_interactions import LLMMessage, LLMConversation, MessageRole
from .base_controller import ReactController

if TYPE_CHECKING:
    from ...models.processing_context import StageContext
    from tarsy.integrations.llm.client import LLMClient
    from tarsy.agents.prompts import PromptBuilder

logger = get_module_logger(__name__)


class ReactStageController(ReactController):
    """
    ReAct controller for stage-specific analysis - only differs in prompt building.
    
    Extends ReactController and customizes only the initial conversation building.
    All ReAct loop logic is handled by the parent class.
    """
    
    def __init__(self, llm_client: 'LLMClient', prompt_builder: 'PromptBuilder'):
        """Initialize with proper type annotations."""
        super().__init__(llm_client, prompt_builder)
        logger.info("Initialized ReactStageController for stage-specific analysis")
    
    def build_initial_conversation(self, context: 'StageContext') -> LLMConversation:
        """Build initial conversation for stage-specific ReAct analysis."""
        system_content = self.prompt_builder.get_enhanced_react_system_message(
            context.agent._compose_instructions(), 
            "collecting additional data and providing stage-specific analysis"
        )
        user_content = self.prompt_builder.build_stage_analysis_react_prompt(context, [])
        
        return LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content=system_content),
            LLMMessage(role=MessageRole.USER, content=user_content)
        ])

    def extract_final_analysis(self, analysis_result: str, context) -> str:
        """
        Extract partial analysis from ReAct conversation for API consumption.
        
        Similar to full analysis but focused on partial/intermediate findings.
        """
        return self._extract_react_final_analysis(
            analysis_result=analysis_result,
            completion_patterns=["Partial analysis completed"],
            incomplete_patterns=["Partial analysis incomplete:"],
            fallback_message="Partial analysis stage completed with limited findings",
            context=context
        )