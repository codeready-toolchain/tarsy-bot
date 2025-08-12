"""
ReAct Final Analysis iteration controller for comprehensive analysis stages.

This controller implements final analysis without tool calling, using all
accumulated data from previous stages to provide comprehensive conclusions.
"""

from typing import TYPE_CHECKING

from tarsy.utils.logger import get_module_logger
from tarsy.models.llm import LLMMessage
from .base_iteration_controller import IterationController, IterationContext

if TYPE_CHECKING:
    pass

logger = get_module_logger(__name__)


class ReactFinalAnalysisController(IterationController):
    """
    Final analysis controller - no tool calling, pure analysis.
    
    Provides comprehensive final analysis using all accumulated data from
    previous chain stages without additional data collection.
    """
    
    def __init__(self, llm_client, prompt_builder):
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder
    
    async def execute_analysis_loop(self, context: IterationContext) -> str:
        """Execute final analysis using all accumulated data."""
        logger.info("Starting final analysis (no tools)")
        
        # Build comprehensive prompt with all stage data
        prompt_context = context.agent.create_prompt_context(
            alert_data=context.alert_data,
            runbook_content=context.runbook_content,
            mcp_data=context.initial_mcp_data,  # All data from previous stages
            available_tools=None  # No tools available
        )
        
        prompt = self.prompt_builder.build_final_analysis_prompt(prompt_context)
        
        # Single comprehensive analysis call
        messages = [
            LLMMessage(
                role="system", 
                content="You are an expert SRE. Provide comprehensive final analysis based on all available data."
            ),
            LLMMessage(role="user", content=prompt)
        ]
        
        return await self.llm_client.generate_response(messages, context.session_id)