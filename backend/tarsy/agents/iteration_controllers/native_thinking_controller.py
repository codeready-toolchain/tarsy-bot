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
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.utils.logger import get_module_logger

from .base_controller import IterationController

if TYPE_CHECKING:
    from ...agents.prompts import PromptBuilder
    from ...integrations.llm.manager import LLMManager
    from ...models.processing_context import StageContext

logger = get_module_logger(__name__)


# Helper functions for consecutive timeout detection
def _create_consecutive_timeout_error(count: int, failure_type: str = "tool") -> str:
    """
    Create standardized error message for consecutive timeout failures.
    
    Args:
        count: Number of consecutive timeouts
        failure_type: Type of timeout ("tool" or "iteration")
        
    Returns:
        Standardized error message string
    """
    return f"Stopping after {count} consecutive {failure_type} timeout failures"


def _is_consecutive_timeout_error(exception: Exception) -> bool:
    """
    Check if an exception is our own consecutive timeout failure exception.
    
    This allows us to detect and re-raise our intentional timeout exceptions
    without processing them again.
    
    Args:
        exception: Exception to check
        
    Returns:
        True if this is our consecutive timeout exception, False otherwise
    """
    error_msg = str(exception).lower()
    # Check for our specific error message pattern
    return "consecutive" in error_msg and "timeout failures" in error_msg


class NativeThinkingController(IterationController):
    """
    Gemini-specific controller using native thinking and function calling.
    
    Eliminates text-based ReAct parsing by leveraging:
    - thinkingLevel parameter for reasoning depth control
    - Native function calling for tool execution
    - Thought signatures for multi-turn reasoning continuity
    
    This controller is specifically designed for Gemini
    models that support native thinking capabilities.
    
    Per-stage LLM provider switching IS supported, but only between Google/Gemini
    providers (e.g., google-default, gemini-flash). Non-Google providers will
    raise an error since native thinking uses Google SDK features.
    """
    
    def __init__(self, llm_manager: 'LLMManager', prompt_builder: 'PromptBuilder'):
        """
        Initialize the native thinking controller.
        
        Args:
            llm_manager: LLM manager for accessing native thinking clients
            prompt_builder: Prompt builder for creating system/user prompts
            
        Raises:
            ValueError: If default LLM provider is not Google/Gemini
        """
        self.llm_manager = llm_manager
        self.prompt_builder = prompt_builder
        self.logger = logger
        self._llm_provider_name: Optional[str] = None
        
        # Validate that default provider supports native thinking (is Google/Gemini)
        # Use get_native_thinking_client() to check - it returns None for non-Google providers
        native_client = llm_manager.get_native_thinking_client()
        if native_client is None:
            # Get default client to provide better error message
            default_client = llm_manager.get_client()
            provider_type = default_client.config.type.value if default_client else "unknown"
            raise ValueError(
                f"NativeThinkingController requires Google/Gemini provider as default, "
                f"got {provider_type}"
            )
        
        logger.info("Initialized NativeThinkingController for Gemini native thinking")
    
    def set_llm_provider(self, provider_name: Optional[str]):
        """
        Set the LLM provider for this controller.
        
        Native thinking supports switching between Google/Gemini providers only.
        Non-Google providers will raise an error when execute_analysis_loop is called.
        
        Args:
            provider_name: Name of the LLM provider (must be Google/Gemini type)
        """
        self._llm_provider_name = provider_name
        if provider_name:
            logger.info(f"NativeThinkingController configured with provider: {provider_name}")
    
    def _get_native_client(self) -> GeminiNativeThinkingClient:
        """
        Get the native thinking client for the current provider.
        
        Uses LLMManager.get_native_thinking_client() which handles lazy creation
        and caching of native thinking clients.
        
        Returns:
            GeminiNativeThinkingClient for the current provider
            
        Raises:
            ValueError: If requested provider is not Google/Gemini type
        """
        # Use LLM manager to get native thinking client (handles caching internally)
        client = self.llm_manager.get_native_thinking_client(self._llm_provider_name)
        
        if client is None:
            provider_name = self._llm_provider_name or "default"
            raise ValueError(
                f"NativeThinkingController requires Google/Gemini provider, "
                f"but '{provider_name}' is not a Google provider. "
                f"Use a different iteration strategy for non-Google providers."
            )
        
        return client
    
    def needs_mcp_tools(self) -> bool:
        """Native thinking controller uses tools via native function calling."""
        return True
    
    async def execute_analysis_loop(self, context: 'StageContext') -> str:
        """
        Execute analysis using Gemini's native thinking and function calling.
        
        This loop:
        1. Checks for paused session and resumes if found
        2. Builds initial conversation with simplified prompt (no ReAct format)
        3. Converts MCP tools to Gemini function declarations
        4. Calls LLM with thinking_level + bound functions + thought_signature
        5. Extracts thinking_content for audit
        6. If tool_calls in response: execute MCP tools, append results
        7. If no tool_calls: final answer reached
        8. Preserves thought_signature for next iteration
        9. Handles max iterations with pause/failure distinction
        
        Args:
            context: StageContext containing all stage processing data
            
        Returns:
            Final analysis result string
            
        Raises:
            SessionPaused: When max iterations reached with successful last interaction
            MaxIterationsFailureError: When max iterations reached with failed last interaction
        """
        self.logger.info("Starting native thinking analysis loop")
        
        agent = context.agent
        if agent is None:
            raise ValueError("Agent reference is required in context")
        
        max_iterations = agent.max_iterations
        settings = get_settings()
        iteration_timeout = settings.llm_iteration_timeout
        
        # Get the native client for the current provider (supports per-stage switching)
        native_client = self._get_native_client()
        
        # 1. Check if resuming from a paused session with conversation history
        conversation = self._restore_paused_conversation(context, self.logger)
        if conversation is None:
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
        
        # 2. Track last interaction success for failure detection
        last_interaction_failed = False
        consecutive_timeout_failures = 0  # Track consecutive timeout failures
        
        # Main iteration loop
        for iteration in range(max_iterations):
            self.logger.info(f"Native thinking iteration {iteration + 1}/{max_iterations}")
            
            # Check for consecutive timeout failures (prevent infinite retry loops)
            if consecutive_timeout_failures >= 2:
                error_msg = _create_consecutive_timeout_error(consecutive_timeout_failures, "iteration")
                self.logger.error(error_msg)
                raise Exception(error_msg)
            
            try:
                # Call LLM with native thinking
                response = await asyncio.wait_for(
                    native_client.generate(
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
                
                # Mark this interaction as successful
                last_interaction_failed = False
                # Note: consecutive_timeout_failures NOT reset here - only reset on successful
                # tool execution or non-timeout errors, so timeouts accumulate across iterations
                
                # Check if we have a final answer (no tool calls)
                if response.is_final:
                    self.logger.info("Native thinking completed with final answer")
                    self._last_conversation = conversation  # Store for investigation_history
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
                            
                            # Tool succeeded - reset timeout failure counter
                            consecutive_timeout_failures = 0
                            
                            # Format observation and append to conversation
                            observation = self._format_tool_result(mcp_data)
                            conversation.append_observation(f"Tool Result: {observation}")
                            
                            self.logger.debug("Tool result added to conversation")
                            
                        except Exception as e:
                            error_msg = f"Error executing {tool_call.server}.{tool_call.tool}: {str(e)}"
                            self.logger.error(error_msg)
                            conversation.append_observation(f"Tool Error: {error_msg}")
                            
                            # Track timeout failures specifically using exception type checking
                            # Check for standard timeout exceptions from asyncio and built-in TimeoutError
                            is_timeout = isinstance(e, (TimeoutError, asyncio.TimeoutError))
                            
                            # Note: We only check exception types, not messages, for reliability.
                            # If other libraries raise custom timeout exceptions, they should either:
                            # 1. Inherit from TimeoutError (proper design)
                            # 2. Be caught and re-raised as TimeoutError by the calling code
                            
                            if is_timeout:
                                consecutive_timeout_failures += 1
                                self.logger.warning(f"Tool timeout detected ({consecutive_timeout_failures} consecutive)")
                                
                                # Check if we should stop immediately (don't wait for next iteration)
                                if consecutive_timeout_failures >= 2:
                                    error_msg = _create_consecutive_timeout_error(consecutive_timeout_failures, "tool")
                                    raise Exception(error_msg) from None
                            else:
                                consecutive_timeout_failures = 0  # Reset on non-timeout errors
                else:
                    # No tool calls and not marked as final - unusual state
                    self.logger.warning("Response has no tool calls but is not marked as final")
                    self._last_conversation = conversation  # Store for investigation_history
                    return self._build_final_result(response.content, all_thinking_content)
                    
            except asyncio.TimeoutError:
                error_msg = f"Iteration {iteration + 1} exceeded {iteration_timeout}s timeout"
                self.logger.error(error_msg)
                consecutive_timeout_failures += 1
                self.logger.warning(f"Iteration timeout ({consecutive_timeout_failures} consecutive)")
                
                # Check if we should stop
                if consecutive_timeout_failures >= 2:
                    error_msg = _create_consecutive_timeout_error(consecutive_timeout_failures, "iteration")
                    raise Exception(error_msg) from None
                
                # Otherwise, append error and continue
                conversation.append_observation(f"Error: {error_msg}")
                
            except Exception as e:
                import traceback
                
                # Check if this is already our consecutive timeout exception
                # If so, re-raise it immediately without further processing to avoid double-counting
                if _is_consecutive_timeout_error(e):
                    raise
                
                error_msg = f"Native thinking iteration {iteration + 1} failed: {str(e)}"
                self.logger.error(error_msg)
                self.logger.error(f"Full traceback:\n{traceback.format_exc()}")
                
                # Mark this interaction as failed
                last_interaction_failed = True
                
                # Check if it's a timeout-related failure using exception type only
                is_timeout = isinstance(e, (TimeoutError, asyncio.TimeoutError))
                
                if is_timeout:
                    consecutive_timeout_failures += 1
                    self.logger.warning(f"Exception is timeout type ({consecutive_timeout_failures} consecutive)")
                    if consecutive_timeout_failures >= 2:
                        error_msg = _create_consecutive_timeout_error(consecutive_timeout_failures, "general")
                        raise Exception(error_msg) from e
                else:
                    consecutive_timeout_failures = 0  # Reset on non-timeout errors
                
                conversation.append_observation(f"Error: {error_msg}")
        
        # 3. Max iterations reached - pause for user action or fail
        self._raise_max_iterations_exception(
            max_iterations=max_iterations,
            last_interaction_failed=last_interaction_failed,
            conversation=conversation,
            context=context,
            logger=self.logger
        )
    
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

