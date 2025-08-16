"""
ReAct Final Analysis iteration controller for comprehensive analysis stages.

This controller implements final analysis without tool calling, using all
accumulated data from previous stages to provide comprehensive conclusions.
"""

from typing import TYPE_CHECKING

from tarsy.utils.logger import get_module_logger
from tarsy.models.unified_interactions import LLMMessage
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
    
    def needs_mcp_tools(self) -> bool:
        """Final analysis doesn't need MCP tool discovery."""
        return False
    
    async def execute_analysis_loop(self, context: IterationContext) -> str:
        """Execute final analysis using all accumulated data."""
        logger.info("Starting final analysis (no tools)")
        
        # Enhanced stage-aware logging
        if context.initial_mcp_data:
            logger.info("Enhanced logging: Final analysis stage with accumulated data from previous stages")
            data_sources = list(context.initial_mcp_data.keys())
            logger.info(f"Enhanced logging: Data available from sources: {data_sources}")
        else:
            logger.info("Enhanced logging: Final analysis stage running independently (no previous stage data)")
        
        # Build comprehensive prompt with all stage data
        prompt_context = context.agent.create_prompt_context(
            alert_data=context.alert_data,
            runbook_content=context.runbook_content,
            mcp_data=context.initial_mcp_data,  # All data from previous stages (merged)
            available_tools=None,  # No tools available
            stage_name="final-analysis",
            is_final_stage=True,
            previous_stages=list(context.stage_attributed_data.keys()) if context.stage_attributed_data else None,
            stage_attributed_data=context.stage_attributed_data  # Stage-attributed format for better clarity
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
        
        return await self.llm_client.generate_response(messages, context.session_id, context.agent.get_current_stage_execution_id())