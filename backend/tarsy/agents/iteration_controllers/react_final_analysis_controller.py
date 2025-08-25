"""
ReAct Final Analysis iteration controller for comprehensive analysis stages.

This controller implements final analysis without tool calling, using all
accumulated data from previous stages to provide comprehensive conclusions.
"""

from typing import TYPE_CHECKING

from tarsy.utils.logger import get_module_logger
from tarsy.models.unified_interactions import LLMMessage, LLMConversation
from .base_controller import IterationController

if TYPE_CHECKING:
    from ...models.processing_context import StageContext
    from tarsy.integrations.llm.client import LLMClient
    from tarsy.agents.prompts import PromptBuilder

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
    
    async def execute_analysis_loop(self, context: 'StageContext') -> str:
        """Execute final analysis with StageContext."""
        logger.info("Starting final analysis with StageContext")
        
        # Pass StageContext directly to prompt builder
        prompt = self.prompt_builder.build_final_analysis_prompt(context)
        
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
        
        # Create LLMConversation object for EP-0014 compatibility
        conversation = LLMConversation(messages=messages)
        
        # Generate response and get the latest assistant message content
        updated_conversation = await self.llm_client.generate_response(conversation, context.session_id, context.agent.get_current_stage_execution_id())
        latest_message = updated_conversation.get_latest_assistant_message()
        
        if latest_message:
            return latest_message.content
        else:
            return "No response generated from LLM"