"""
Synthesis controller for synthesizing parallel investigation results.

This controller provides a simple, tool-less synthesis strategy that works
with any LLM provider. It receives rich investigation history from parallel
agents and produces a unified analysis.
"""

from typing import TYPE_CHECKING

from tarsy.agents.iteration_controllers.base_controller import IterationController
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    from tarsy.agents.prompts.builders import PromptBuilder
    from tarsy.integrations.llm.manager import LLMManager
    from tarsy.models.processing_context import StageContext

logger = get_module_logger(__name__)


class SynthesisController(IterationController):
    """
    Simple synthesis controller for combining parallel investigation results.
    
    This controller performs tool-less synthesis using a single LLM call.
    Works with any LLM provider (provider-agnostic).
    """
    
    def __init__(self, llm_manager: 'LLMManager', prompt_builder: 'PromptBuilder'):
        """
        Initialize synthesis controller.
        
        Args:
            llm_manager: LLM manager for accessing LLM clients
            prompt_builder: Prompt builder for creating synthesis prompts
        """
        super().__init__()
        self.llm_manager = llm_manager
        self.prompt_builder = prompt_builder
    
    def needs_mcp_tools(self) -> bool:
        """Synthesis doesn't need MCP tools."""
        return False
    
    async def execute_analysis_loop(self, context: 'StageContext') -> str:
        """Execute synthesis with single LLM call (no tools)."""
        logger.info("Starting synthesis analysis (tool-less, single call)")
        
        # Get agent reference
        agent = context.agent
        if agent is None:
            raise ValueError("Agent reference is required in context")
        
        # Build synthesis prompt with previous stage results
        prompt = self.prompt_builder.build_synthesis_prompt(context)
        
        # Build system message with synthesis instructions
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
        
        # Create conversation
        conversation = LLMConversation(messages=messages)
        
        # Get stage execution ID for interaction tagging
        stage_execution_id = agent.get_current_stage_execution_id()
        
        # Extract native tools override from context (if specified)
        native_tools_override = self._get_native_tools_override(context)
        
        # Single LLM call for synthesis using llm_manager
        try:
            # Get parallel execution metadata for streaming
            parallel_metadata = agent.get_parallel_execution_metadata()
            
            conversation_result = await self.llm_manager.generate_response(
                conversation=conversation,
                session_id=context.session_id,
                stage_execution_id=stage_execution_id,
                provider=agent._llm_provider_name,
                native_tools_override=native_tools_override,
                parallel_metadata=parallel_metadata
            )
            
            # Extract assistant response
            assistant_message = conversation_result.get_latest_assistant_message()
            if not assistant_message:
                raise Exception("No assistant response received from LLM")
            
            response = assistant_message
            
            # Extract content from assistant message
            analysis = response.content if hasattr(response, 'content') else str(response)
            
            # Store conversation for investigation_history
            self._last_conversation = conversation_result
            
            logger.info("Synthesis analysis completed successfully")
            return analysis if analysis else "No synthesis result generated"
            
        except Exception as e:
            logger.error(f"Synthesis failed: {e}", exc_info=True)
            raise
    
    def build_synthesis_conversation(self, conversation: LLMConversation) -> str:
        """
        Build investigation history - not typically called for synthesis.
        
        Synthesis controllers don't produce investigation history themselves,
        they consume it from parallel agents.
        """
        # Simple implementation: return last assistant message
        if not hasattr(conversation, 'messages') or not conversation.messages:
            return ""
        
        for msg in reversed(conversation.messages):
            if msg.role == MessageRole.ASSISTANT:
                return msg.content
        
        return ""
    
    def create_result_summary(
        self,
        analysis_result: str,
        context: 'StageContext'
    ) -> str:
        """
        Create result summary for synthesis.
        
        Args:
            analysis_result: Raw synthesis analysis
            context: StageContext containing processing data
            
        Returns:
            Formatted summary string
        """
        if not analysis_result:
            return "No synthesis result generated"
        
        return f"## Synthesis Result\n\n{analysis_result}"

