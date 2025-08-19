"""
ReAct Final Analysis iteration controller for comprehensive analysis stages.

This controller implements final analysis without tool calling, using all
accumulated data from previous stages to provide comprehensive conclusions.
"""

from typing import TYPE_CHECKING, Union

from tarsy.utils.logger import get_module_logger
from tarsy.models.unified_interactions import LLMMessage
from .base_iteration_controller import IterationController, IterationContext

if TYPE_CHECKING:
    # TEMPORARY PHASE 3: Import new context for overloaded methods
    from ...models.processing_context import StageContext
    from tarsy.integrations.llm.client import LLMClient
    from tarsy.agents.prompt_builder import PromptBuilder

logger = get_module_logger(__name__)


class ReactFinalAnalysisController(IterationController):
    """
    Final analysis controller - no tool calling, pure analysis.
    
    Provides comprehensive final analysis using all accumulated data from
    previous chain stages without additional data collection.
    """
    
    def __init__(self, llm_client: 'LLMClient', prompt_builder: 'PromptBuilder'):
        """Initialize with proper type annotations."""
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder
    
    def needs_mcp_tools(self) -> bool:
        """Final analysis doesn't need MCP tool discovery."""
        return False
    
    async def execute_analysis_loop(self, context: Union[IterationContext, 'StageContext']) -> str:
        """
        TEMPORARY OVERLOAD: Execute final analysis supporting both old and new contexts during migration.
        """
        from ...models.processing_context import StageContext
        
        if isinstance(context, StageContext):
            logger.info("PHASE 3: Starting final analysis with new StageContext")
            return await self._execute_with_stage_context(context)
        else:
            logger.info("PHASE 3: Starting final analysis with legacy IterationContext")
            return await self._execute_with_iteration_context(context)
    
    async def _execute_with_stage_context(self, context: 'StageContext') -> str:
        """Execute final analysis with new StageContext."""
        logger.info("Starting final analysis (single LLM call, no tools) (StageContext)")
        
        # PHASE 4: Pass StageContext directly to prompt builder (no PromptContext conversion)
        return await self._execute_final_analysis_with_stage_context(context.agent, context)
    
    async def _execute_final_analysis_with_stage_context(self, agent, stage_context: 'StageContext') -> str:
        """Execute final analysis using StageContext directly - PHASE 4 enhancement."""
        
        # PHASE 4: Pass StageContext directly to prompt builder
        prompt = self.prompt_builder.build_final_analysis_prompt(stage_context)
        
        # Single comprehensive analysis call with simplified system message
        # No ReAct or MCP instructions needed for final analysis
        general_instructions = agent._get_general_instructions()
        custom_instructions = agent.custom_instructions()
        
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
        
        return await self.llm_client.generate_response(messages, stage_context.session_id, agent.get_current_stage_execution_id())
    
    async def _execute_with_iteration_context(self, context: IterationContext) -> str:
        """Execute final analysis with legacy IterationContext."""
        logger.info("Starting final analysis (single LLM call, no tools) (IterationContext)")
        
        # Get actual stage name from AlertProcessingData (or None for non-chain execution)
        stage_name = getattr(context.alert_data, 'current_stage_name', None)
        
        # Build final analysis prompt (chain context will be handled in prompt builder)
        prompt_context = context.agent.create_prompt_context(
            alert_data=context.alert_data,
            runbook_content=context.runbook_content,
            available_tools=None,  # No tools available
            stage_name=stage_name,
            is_final_stage=True,
            previous_stages=None  # Will be handled by chain context
        )
        
        return await self._execute_final_analysis(context.agent, prompt_context, context.session_id)
    
    async def _execute_final_analysis(self, agent, prompt_context, session_id) -> str:
        """Common final analysis logic for both context types."""
        
        prompt = self.prompt_builder.build_final_analysis_prompt(prompt_context)
        
        # Single comprehensive analysis call with simplified system message
        # No ReAct or MCP instructions needed for final analysis
        general_instructions = agent._get_general_instructions()
        custom_instructions = agent.custom_instructions()
        
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
        
        return await self.llm_client.generate_response(messages, session_id, agent.get_current_stage_execution_id())

    def extract_final_analysis(self, analysis_result: str, context) -> str:
        """
        Final analysis controller already generates clean analysis - return as-is.
        """
        if not analysis_result:
            return "No final analysis generated"
        
        return analysis_result.strip()