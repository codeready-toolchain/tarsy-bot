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
        """Execute final analysis - single LLM call, no iterations."""
        logger.info("Starting final analysis (single LLM call, no tools)")
        
        # Build final analysis prompt (chain context will be handled in prompt builder)
        prompt_context = context.agent.create_prompt_context(
            alert_data=context.alert_data,
            runbook_content=context.runbook_content,
            mcp_data={},  # Final analysis gets previous stage data via chain context in prompt
            available_tools=None,  # No tools available
            stage_name="final-analysis",
            is_final_stage=True,
            previous_stages=None,  # Will be handled by chain context
            stage_attributed_data=None  # Will be handled by chain context
        )
        
        prompt = self.prompt_builder.build_final_analysis_prompt(prompt_context)
        
        # Single comprehensive analysis call with simplified system message
        # No ReAct or MCP instructions needed for final analysis
        general_instructions = context.agent._get_general_instructions()
        custom_instructions = context.agent.custom_instructions()
        
        system_content_parts = [general_instructions]
        if custom_instructions:
            system_content_parts.append(f"\n## Agent-Specific Instructions\n{custom_instructions}")
        
        messages = [
            LLMMessage(
                role="system", 
                content="\n".join(system_content_parts)
            ),
            LLMMessage(role="user", content=prompt)
        ]
        
        return await self.llm_client.generate_response(messages, context.session_id, context.agent.get_current_stage_execution_id())

    def extract_final_analysis(self, analysis_result: str, context) -> str:
        """
        Final analysis controller already generates clean analysis - return as-is.
        """
        if not analysis_result:
            return "No final analysis generated"
        
        return analysis_result.strip()