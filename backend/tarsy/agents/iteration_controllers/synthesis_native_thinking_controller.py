"""
Native Thinking Synthesis controller for deep synthesis using Gemini.

This controller uses Gemini's native thinking capabilities to perform
deeper reasoning and analysis when synthesizing parallel investigation results.
"""

from typing import TYPE_CHECKING

from tarsy.agents.iteration_controllers.native_thinking_controller import NativeThinkingController
from tarsy.models.unified_interactions import LLMConversation, LLMMessage
from tarsy.utils.logger import get_module_logger

if TYPE_CHECKING:
    from tarsy.agents.prompts.builders import PromptBuilder
    from tarsy.integrations.llm.manager import LLMManager
    from tarsy.models.processing_context import StageContext

logger = get_module_logger(__name__)


class SynthesisNativeThinkingController(NativeThinkingController):
    """
    Synthesis controller using Gemini native thinking for deep reasoning.
    
    Extends NativeThinkingController but overrides to make it tool-less
    and synthesis-specific.
    """
    
    def __init__(self, llm_manager: 'LLMManager', prompt_builder: 'PromptBuilder'):
        """
        Initialize synthesis native thinking controller.
        
        Args:
            llm_manager: LLM manager for accessing native thinking clients
            prompt_builder: Prompt builder for creating synthesis prompts
        """
        super().__init__(llm_manager, prompt_builder)
    
    def needs_mcp_tools(self) -> bool:
        """Synthesis doesn't need MCP tools."""
        return False
    
    async def execute_analysis_loop(self, context: 'StageContext') -> str:
        """Execute synthesis using Gemini native thinking (single call, no tools)."""
        logger.info("Starting native thinking synthesis (tool-less)")
        
        # Get agent reference
        agent = context.agent
        if agent is None:
            raise ValueError("Agent reference is required in context")
        
        # Build synthesis prompt with previous stage results
        prompt = self.prompt_builder.build_synthesis_prompt(context)
        
        # Build system message with synthesis instructions
        general_instructions = agent.get_general_instructions()
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
        
        # Extract native tools override - synthesis never uses tools, but preserve context
        native_tools_override = self._get_native_tools_override(context)
        
        # Get Gemini native thinking client (from parent class method)
        client = self._get_native_thinking_client(agent.get_llm_provider())
        
        # Single LLM call with native thinking for synthesis
        try:
            # Get parallel execution metadata for streaming
            parallel_metadata = agent.get_parallel_execution_metadata()
            
            response = await client.generate(
                conversation=conversation,
                session_id=context.session_id,
                mcp_tools=[],  # Synthesis doesn't use tools
                stage_execution_id=stage_execution_id,
                thinking_level="high",  # Enable deep thinking for synthesis
                native_tools_override=native_tools_override,
                parallel_metadata=parallel_metadata
            )
            
            # Extract thinking content if available
            thinking_content = []
            if hasattr(response, 'thinking_content') and response.thinking_content:
                thinking_content.append(response.thinking_content)
                logger.debug(f"🧠 Synthesis Thinking: {response.thinking_content[:200]}...")
            
            # Extract main content
            if hasattr(response, 'content'):
                analysis = response.content
            else:
                analysis = str(response)
            
            # Store conversation for investigation_history
            self._last_conversation = conversation
            
            logger.info("Native thinking synthesis completed successfully")
            
            # Return final result (thinking is captured separately in interactions)
            return analysis if analysis else "No synthesis result generated"
            
        except Exception as e:
            logger.error(f"Native thinking synthesis failed: {e}", exc_info=True)
            raise
    
    def create_result_summary(
        self,
        analysis_result: str,
        context: 'StageContext'
    ) -> str:
        """
        Create result summary for native thinking synthesis.
        
        Args:
            analysis_result: Raw synthesis analysis
            context: StageContext containing processing data
            
        Returns:
            Formatted summary string
        """
        if not analysis_result:
            return "No synthesis result generated"
        
        return f"## Native Thinking Synthesis Result\n\n{analysis_result}"

