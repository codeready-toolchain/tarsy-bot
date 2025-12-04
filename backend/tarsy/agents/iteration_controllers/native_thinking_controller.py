"""
Native Thinking iteration controller for Gemini-specific reasoning.

This controller uses Gemini's native thinking capabilities and structured
function calling instead of text-based ReAct parsing. This eliminates
format compliance issues while providing full observability of reasoning.

Key features:
- Uses thinkingLevel parameter for reasoning depth control
- Native function calling for tool execution (no text parsing)
- Thought signatures for multi-turn reasoning continuity
- Stores thinking_content for audit/observability
"""

import asyncio
from typing import TYPE_CHECKING, Optional

from tarsy.config.settings import get_settings
from tarsy.integrations.llm.gemini_client import GeminiNativeThinkingClient
from tarsy.models.llm_models import LLMProviderType
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.utils.logger import get_module_logger

from .base_controller import IterationController

if TYPE_CHECKING:
    from ...agents.prompts import PromptBuilder
    from ...integrations.llm.manager import LLMManager
    from ...models.processing_context import StageContext

logger = get_module_logger(__name__)


class NativeThinkingController(IterationController):
    """
    Gemini-specific controller using native thinking and function calling.
    
    Eliminates text-based ReAct parsing by leveraging:
    - thinkingLevel parameter for reasoning depth control
    - Native function calling for tool execution
    - Thought signatures for multi-turn reasoning continuity
    
    This controller is specifically designed for Gemini 3.0 Pro and later
    models that support native thinking capabilities.
    """
    
    def __init__(self, llm_manager: 'LLMManager', prompt_builder: 'PromptBuilder'):
        """
        Initialize the native thinking controller.
        
        Args:
            llm_manager: LLM manager (the default client must be Google/Gemini provider)
            prompt_builder: Prompt builder for creating system/user prompts
            
        Raises:
            ValueError: If default LLM client is not Google/Gemini provider
        """
        self.llm_manager = llm_manager
        self.prompt_builder = prompt_builder
        self.logger = logger
        
        # Get the actual LLM client from the manager and validate it's Google/Gemini
        actual_client = llm_manager.get_client()
        if actual_client is None:
            raise ValueError("No default LLM client available in manager")
        
        if actual_client.config.type != LLMProviderType.GOOGLE:
            raise ValueError(
                f"NativeThinkingController requires Google/Gemini provider, "
                f"got {actual_client.config.type.value}"
            )
        
        # Create dedicated native thinking client from the config
        self._native_client = GeminiNativeThinkingClient(
            actual_client.config,
            provider_name=actual_client.provider_name
        )
        
        logger.info("Initialized NativeThinkingController for Gemini native thinking")
    
    def needs_mcp_tools(self) -> bool:
        """Native thinking controller uses tools via native function calling."""
        return True
    
    async def execute_analysis_loop(self, context: 'StageContext') -> str:
        """
        Execute analysis using Gemini's native thinking and function calling.
        
        This loop:
        1. Builds initial conversation with simplified prompt (no ReAct format)
        2. Converts MCP tools to Gemini function declarations
        3. Calls LLM with thinking_level + bound functions + thought_signature
        4. Extracts thinking_content for audit
        5. If tool_calls in response: execute MCP tools, append results
        6. If no tool_calls: final answer reached
        7. Preserves thought_signature for next iteration
        
        Args:
            context: StageContext containing all stage processing data
            
        Returns:
            Final analysis result string
        """
        self.logger.info("Starting native thinking analysis loop")
        
        agent = context.agent
        if agent is None:
            raise ValueError("Agent reference is required in context")
        
        max_iterations = agent.max_iterations
        settings = get_settings()
        iteration_timeout = settings.llm_iteration_timeout
        
        # Build initial conversation (simplified, no ReAct format instructions)
        conversation = self._build_initial_conversation(context)
        
        # Get MCP tools for native function binding
        mcp_tools = context.available_tools.tools
        self.logger.info(f"Starting with {len(mcp_tools)} MCP tools bound as native functions")
        
        # Track thought signature across iterations for reasoning continuity
        thought_signature: Optional[bytes] = None
        
        # Track thinking content for observability
        all_thinking_content: list[str] = []
        
        # Extract native tools override from context
        native_tools_override = self._get_native_tools_override(context)
        
        # Main iteration loop
        for iteration in range(max_iterations):
            self.logger.info(f"Native thinking iteration {iteration + 1}/{max_iterations}")
            
            try:
                # Call LLM with native thinking
                response = await asyncio.wait_for(
                    self._native_client.generate(
                        conversation=conversation,
                        session_id=context.session_id,
                        mcp_tools=mcp_tools,
                        stage_execution_id=agent.get_current_stage_execution_id(),
                        thinking_level="high",  # Use high thinking for complex SRE analysis
                        thought_signature=thought_signature,
                        native_tools_override=native_tools_override
                    ),
                    timeout=iteration_timeout
                )
                
                # Store thinking content for audit
                if response.thinking_content:
                    all_thinking_content.append(response.thinking_content)
                    self.logger.debug(f"Captured thinking content ({len(response.thinking_content)} chars)")
                
                # Update thought signature for next iteration
                thought_signature = response.thought_signature
                
                # Update conversation from response
                conversation = response.conversation
                
                # Check if we have a final answer (no tool calls)
                if response.is_final:
                    self.logger.info("Native thinking completed with final answer")
                    return self._build_final_result(response.content, all_thinking_content)
                
                # Execute tool calls
                if response.has_tool_calls:
                    self.logger.info(f"Executing {len(response.tool_calls)} tool calls")
                    
                    for tool_call in response.tool_calls:
                        try:
                            self.logger.debug(
                                f"Executing tool: {tool_call.server}.{tool_call.tool} "
                                f"with params: {list(tool_call.parameters.keys())}"
                            )
                            
                            # Convert to format expected by execute_mcp_tools
                            tool_request = {
                                "server": tool_call.server,
                                "tool": tool_call.tool,
                                "parameters": tool_call.parameters
                            }
                            
                            # Execute tool
                            mcp_data = await agent.execute_mcp_tools(
                                [tool_request],
                                context.session_id,
                                conversation,
                                context.chain_context.mcp
                            )
                            
                            # Format observation and append to conversation
                            observation = self._format_tool_result(mcp_data)
                            conversation.append_observation(f"Tool Result: {observation}")
                            
                            self.logger.debug("Tool result added to conversation")
                            
                        except Exception as e:
                            error_msg = f"Error executing {tool_call.server}.{tool_call.tool}: {str(e)}"
                            self.logger.error(error_msg)
                            conversation.append_observation(f"Tool Error: {error_msg}")
                else:
                    # No tool calls and not marked as final - unusual state
                    self.logger.warning("Response has no tool calls but is not marked as final")
                    return self._build_final_result(response.content, all_thinking_content)
                    
            except asyncio.TimeoutError:
                error_msg = f"Iteration {iteration + 1} exceeded {iteration_timeout}s timeout"
                self.logger.error(error_msg)
                conversation.append_observation(f"Error: {error_msg}")
                
            except Exception as e:
                import traceback
                error_msg = f"Native thinking iteration {iteration + 1} failed: {str(e)}"
                self.logger.error(error_msg)
                self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
                conversation.append_observation(f"Error: {error_msg}")
        
        # Max iterations reached
        self.logger.warning(f"Max iterations ({max_iterations}) reached without final answer")
        
        # Return best available result
        last_content = self._get_last_assistant_content(conversation)
        return self._build_final_result(last_content, all_thinking_content)
    
    def _build_initial_conversation(self, context: 'StageContext') -> LLMConversation:
        """
        Build initial conversation with simplified prompt (no ReAct format).
        
        Native thinking doesn't need ReAct format instructions since the model
        uses native function calling for tools and internal reasoning.
        
        Args:
            context: StageContext containing processing data
            
        Returns:
            LLMConversation with system and user messages
        """
        # Get system message using native thinking template
        system_content = self.prompt_builder.get_native_thinking_system_message(
            context.agent._compose_instructions(),
            "investigation and providing recommendations"
        )
        
        # Build user content (analysis question without ReAct format)
        user_content = self.prompt_builder.build_native_thinking_prompt(context)
        
        return LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content=system_content),
            LLMMessage(role=MessageRole.USER, content=user_content)
        ])
    
    def _format_tool_result(self, mcp_data: dict) -> str:
        """
        Format MCP tool result for conversation.
        
        Args:
            mcp_data: Result from execute_mcp_tools
            
        Returns:
            Formatted string representation
        """
        import json
        
        results = []
        for server_name, tool_results in mcp_data.items():
            for result in tool_results:
                tool_name = result.get("tool", "unknown")
                tool_result = result.get("result", {})
                
                # Convert to string representation
                if isinstance(tool_result, str):
                    results.append(f"{server_name}.{tool_name}: {tool_result}")
                else:
                    try:
                        result_str = json.dumps(tool_result, indent=2, default=str)
                        results.append(f"{server_name}.{tool_name}:\n{result_str}")
                    except Exception:
                        results.append(f"{server_name}.{tool_name}: {str(tool_result)}")
        
        return "\n\n".join(results) if results else "No results"
    
    def _build_final_result(
        self, 
        content: str, 
        thinking_content: list[str]
    ) -> str:
        """
        Build final result string, optionally including thinking content.
        
        Args:
            content: Main response content
            thinking_content: List of thinking content from iterations
            
        Returns:
            Final result string
        """
        # For now, return just the content
        # Thinking content is stored separately in interactions
        return content if content else "No analysis result generated"
    
    def _get_last_assistant_content(self, conversation: LLMConversation) -> str:
        """
        Get content from the last assistant message.
        
        Args:
            conversation: Conversation to extract from
            
        Returns:
            Last assistant message content, or empty string
        """
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
        Create result summary for native thinking analysis.
        
        Args:
            analysis_result: Raw analysis text
            context: StageContext containing processing data
            
        Returns:
            Formatted summary string
        """
        if not analysis_result:
            return "No analysis result generated"
        
        return f"## Analysis Result\n\n{analysis_result}"
    
    def extract_final_analysis(
        self, 
        analysis_result: str, 
        context: 'StageContext'
    ) -> str:
        """
        Extract final analysis for API consumption.
        
        For native thinking, the result is already clean (no ReAct markers).
        
        Args:
            analysis_result: Raw analysis text
            context: StageContext containing processing data
            
        Returns:
            Clean final analysis string
        """
        if not analysis_result:
            return "No analysis generated"
        
        return analysis_result

