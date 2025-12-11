"""
ReAct Final Analysis iteration controller for comprehensive analysis stages.

This controller implements final analysis without tool calling, using all
accumulated data from previous stages to provide comprehensive conclusions.
"""

from typing import TYPE_CHECKING, Optional

from tarsy.models.constants import LLMInteractionType
from tarsy.models.unified_interactions import LLMConversation, LLMMessage
from tarsy.utils.logger import get_module_logger

from .base_controller import IterationController

if TYPE_CHECKING:
    from tarsy.agents.prompts import PromptBuilder
    from tarsy.integrations.llm.manager import LLMManager

    from ...models.processing_context import StageContext

logger = get_module_logger(__name__)


class ReactFinalAnalysisController(IterationController):
    """
    Final analysis controller - no tool calling, pure analysis.
    
    Provides comprehensive final analysis using all accumulated data from
    previous chain stages without additional data collection.
    """
    
    def __init__(self, llm_manager: 'LLMManager', prompt_builder: 'PromptBuilder'):
        """Initialize with proper type annotations."""
        self.llm_manager = llm_manager
        self.prompt_builder = prompt_builder
        self._llm_provider_name: Optional[str] = None
    
    def needs_mcp_tools(self) -> bool:
        """Final analysis doesn't need MCP tool discovery."""
        return False
    
    async def execute_analysis_loop(self, context: 'StageContext') -> str:
        """Execute final analysis with StageContext."""
        logger.info("Starting final analysis with StageContext")
        
        # Import exception class at method start to avoid scoping issues
        from ..exceptions import MaxIterationsFailureError
        
        # Pass StageContext directly to prompt builder
        prompt = self.prompt_builder.build_final_analysis_prompt(context)
        
        # Single comprehensive analysis call with simplified system message
        # No ReAct or MCP instructions needed for final analysis
        general_instructions = context.agent.get_general_instructions()
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
        
        # Capture stage execution ID once for reuse
        stage_execution_id = context.agent.get_current_stage_execution_id()
        
        # Extract native tools override from context (if specified)
        native_tools_override = self._get_native_tools_override(context)
        
        # Generate response and get the latest assistant message content
        try:
            # Get parallel execution metadata for streaming
            parallel_metadata = context.agent.get_parallel_execution_metadata()
            
            updated_conversation = await self.llm_manager.generate_response(
                conversation, 
                context.session_id, 
                stage_execution_id,
                provider=self._llm_provider_name,
                interaction_type=LLMInteractionType.FINAL_ANALYSIS.value,
                parallel_metadata=parallel_metadata,
                native_tools_override=native_tools_override
            )
            latest_message = updated_conversation.get_latest_assistant_message()
            
            if latest_message:
                self._last_conversation = updated_conversation  # Store for investigation_history
                return latest_message.content
            else:
                # No response from LLM - this is a failure condition for final analysis
                error_msg = "Final analysis stage failed: no response generated from LLM"
                failure_msg = "Final analysis stage failed: LLM returned no response"
                logger.error(error_msg)
                raise MaxIterationsFailureError(
                    failure_msg,
                    max_iterations=1,
                    context={
                        "session_id": context.session_id,
                        "stage_execution_id": stage_execution_id,
                        "stage_type": "final_analysis"
                    }
                )
        except MaxIterationsFailureError:
            # Re-raise our own exceptions
            raise
        except Exception as e:
            # Any LLM exception in final analysis stage = stage failure
            original_error = str(e)
            error_msg = f"Final analysis stage failed: {original_error}"
            logger.exception(error_msg)
            raise MaxIterationsFailureError(
                error_msg,
                max_iterations=1,
                context={
                    "session_id": context.session_id,
                    "stage_execution_id": stage_execution_id,
                    "stage_type": "final_analysis",
                    "original_error": original_error
                }
            ) from e