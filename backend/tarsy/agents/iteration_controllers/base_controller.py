"""
Base iteration controller interface and shared types.

This module provides the minimal interface and types needed by 
all iteration controller implementations.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from ...config.settings import get_settings
from ...models.unified_interactions import LLMConversation, MessageRole
from ..parsers.react_parser import ReActParser

if TYPE_CHECKING:
    from ...agents.prompts import PromptBuilder
    from ...integrations.llm.manager import LLMManager
    from ...models.processing_context import StageContext

class IterationController(ABC):
    """
    Abstract controller for different iteration processing strategies.
    
    This allows clean separation between ReAct and regular processing flows
    without conditional logic scattered throughout the BaseAgent.
    """
    
    # LLM provider override (set by agent for per-stage/per-chain providers)
    _llm_provider_name: Optional[str] = None
    
    # Last conversation (stored for investigation_history generation)
    _last_conversation: Optional['LLMConversation'] = None
    
    def set_llm_provider(self, provider_name: Optional[str]):
        """
        Set the LLM provider override for this controller.
        
        Args:
            provider_name: Name of the LLM provider to use, or None for global default
        """
        self._llm_provider_name = provider_name
    
    def get_llm_provider(self) -> Optional[str]:
        """
        Get the LLM provider override for this controller.
        
        Returns:
            Provider name if set, or None for global default
        """
        return self._llm_provider_name
    
    def get_last_conversation(self) -> Optional['LLMConversation']:
        """
        Get the last conversation from execute_analysis_loop.
        
        Returns:
            LLMConversation if available, None otherwise
        """
        return self._last_conversation
    
    def _get_native_tools_override(self, context: 'StageContext'):
        """
        Extract native tools override from processing context.
        
        Args:
            context: StageContext containing processing alert with optional native tools config
            
        Returns:
            NativeToolsConfig if specified in alert, None otherwise
        """
        alert = getattr(context.chain_context, "processing_alert", None)
        if not alert:
            return None
        
        mcp = getattr(alert, "mcp", None)
        if not mcp:
            return None
        
        return getattr(mcp, "native_tools", None)
    
    def _restore_paused_conversation(
        self, 
        context: 'StageContext',
        logger=None
    ) -> Optional[LLMConversation]:
        """
        Check for paused session state and restore conversation if found.
        
        Uses stage execution_id as the lookup key, which is ALWAYS set before
        agent execution (in both parallel and non-parallel stages). This design
        eliminates naming conflicts and works consistently across all scenarios.
        
        Args:
            context: StageContext containing stage processing data
            logger: Optional logger for debug messages
            
        Returns:
            Restored LLMConversation if resuming from paused state, None otherwise
        """
        # Get execution_id (always set before agent.process_alert() is called)
        stage_execution_id = context.agent.get_current_stage_execution_id()
        if not stage_execution_id:
            # This should never happen in production (execution_id always set before execution)
            if logger:
                logger.error("Agent execution_id not set - cannot restore paused conversation")
            return None
        
        if logger:
            logger.debug(f"Looking up paused state with execution_id: {stage_execution_id}")
        
        # Lookup the stage result by execution_id
        if stage_execution_id not in context.chain_context.stage_outputs:
            return None
        
        stage_result = context.chain_context.stage_outputs[stage_execution_id]
        
        # Validate it's a paused AgentExecutionResult with conversation state
        if not hasattr(stage_result, 'status') or not hasattr(stage_result, 'paused_conversation_state'):
            if logger:
                logger.debug("Stage result missing required fields for restoration")
            return None
        
        # Type-safe status comparison (handle both enum and string values)
        from tarsy.models.constants import StageStatus
        status_value = stage_result.status.value if isinstance(stage_result.status, StageStatus) else stage_result.status
        
        if status_value != StageStatus.PAUSED.value or not stage_result.paused_conversation_state:
            return None
        
        # Restore conversation from paused state
        try:
            conversation = LLMConversation.model_validate(stage_result.paused_conversation_state)
            if logger:
                logger.info(f"Resuming from paused state with {len(conversation.messages)} messages")
            return conversation
        except Exception as e:
            if logger:
                logger.warning(f"Failed to restore conversation history: {e}, starting fresh")
            return None
    
    def _raise_max_iterations_exception(
        self,
        max_iterations: int,
        last_interaction_failed: bool,
        conversation: LLMConversation,
        context: 'StageContext',
        logger=None
    ) -> None:
        """
        Raise appropriate exception when max iterations reached.
        
        Args:
            max_iterations: The maximum iteration count that was reached
            last_interaction_failed: Whether the last LLM interaction failed
            conversation: Current conversation state (for resume)
            context: StageContext containing stage processing data
            logger: Optional logger for messages
            
        Raises:
            MaxIterationsFailureError: If last interaction failed
            SessionPaused: If last interaction succeeded (allows resume)
        """
        from ..exceptions import MaxIterationsFailureError, SessionPaused
        
        if last_interaction_failed:
            if logger:
                logger.error(f"Stage failed: reached maximum iterations ({max_iterations}) with failed last interaction")
            raise MaxIterationsFailureError(
                f"Stage failed: reached maximum iterations ({max_iterations}) and last LLM interaction failed",
                max_iterations=max_iterations,
                context={
                    "session_id": context.session_id,
                    "stage_execution_id": context.agent.get_current_stage_execution_id() if context.agent else None,
                    "stage_name": context.stage_name
                }
            )
        else:
            if logger:
                logger.warning(f"Session paused: reached maximum iterations ({max_iterations}) without final answer")
            raise SessionPaused(
                f"Session paused at maximum iterations ({max_iterations})",
                iteration=max_iterations,
                conversation=conversation,
                context={
                    "session_id": context.session_id,
                    "stage_execution_id": context.agent.get_current_stage_execution_id() if context.agent else None,
                    "stage_name": context.stage_name
                }
            )
    
    @abstractmethod
    def needs_mcp_tools(self) -> bool:
        """
        Determine if this iteration strategy requires MCP tool discovery.
        
        Returns:
            True if MCP tools should be discovered, False otherwise
        """
        pass
    
    @abstractmethod
    async def execute_analysis_loop(self, context: 'StageContext') -> str:
        """
        Execute analysis loop with clean StageContext.
        
        Args:
            context: StageContext containing all stage processing data
            
        Returns:
            Final analysis result string
        """
        pass
    
    def build_synthesis_conversation(self, conversation: 'LLMConversation') -> str:
        """
        Build investigation history for synthesis strategies.
        
        Default implementation filters conversation to include thoughts and observations
        while excluding system messages and initial alert data.
        
        Excludes:
        - System messages (internal instructions)
        - First user message (alert data - already in context)
        
        Includes:
        - All assistant messages (thoughts, reasoning)
        - All tool observations (user messages with tool results)
        - Final answers
        
        Args:
            conversation: LLM conversation from execute_analysis_loop
            
        Returns:
            Formatted investigation history string for synthesis
        """
        if not hasattr(conversation, 'messages') or not conversation.messages:
            return ""
        
        sections = []
        first_user_seen = False
        
        for message in conversation.messages:
            # Skip system messages
            if message.role == MessageRole.SYSTEM:
                continue
            
            # Skip first user message (alert data)
            if message.role == MessageRole.USER and not first_user_seen:
                first_user_seen = True
                continue
            
            # Include all other messages
            sections.append(f"{message.role.value.upper()}: {message.content}")
        
        return "\n\n".join(sections)

    def create_result_summary(
        self, 
        analysis_result: str, 
        context: 'StageContext'
    ) -> str:
        """
        Create result summary with clean StageContext.
        
        Default implementation provides simple formatting. Individual strategies
        can override this method to provide specialized formatting.
        
        Args:
            analysis_result: Raw analysis text from execute_analysis_loop
            context: StageContext containing all stage processing data
            
        Returns:
            Formatted summary string for this iteration strategy
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
        Extract final analysis with clean StageContext.
        
        This method should extract a concise, user-friendly final analysis
        from the full analysis result for API consumption.
        
        Default implementation returns the analysis result as-is. Individual strategies
        should override this method to extract relevant final analysis.
        
        Args:
            analysis_result: Raw analysis text from execute_analysis_loop
            context: StageContext containing all stage processing data
            
        Returns:
            Clean final analysis string for API/dashboard consumption
        """
        if not analysis_result:
            return "No analysis result generated"
        
        return analysis_result

    def _extract_react_final_analysis(self, analysis_result: str) -> str:
        """
        Extract final analysis from the last assistant message.
        
        Args:
            analysis_result: Last assistant message containing the Final Answer
            
        Returns:
            Extracted final analysis, or the entire message if parsing fails
        """
        if not analysis_result:
            return "No analysis generated"
        
        # Use ReActParser to extract the Final Answer section
        sections = ReActParser._extract_sections(analysis_result)
        
        # If Final Answer was found, return it
        if sections.get('final_answer'):
            final_answer = sections['final_answer'].strip()
            if final_answer:
                return final_answer
        
        # Fallback: Return the entire last assistant message
        # This ensures we always show something even if parsing fails
        return analysis_result


class ReactController(IterationController):
    """
    Base class for all ReAct-based controllers with consolidated loop logic.
    
    Eliminates code duplication by implementing the complete ReAct loop once.
    Specific controllers only need to override build_initial_conversation().
    """
    
    def __init__(self, llm_manager: 'LLMManager', prompt_builder: 'PromptBuilder'):
        """Initialize with LLM manager and prompt builder."""
        self.llm_manager = llm_manager
        self.prompt_builder = prompt_builder
        self._llm_provider_name: Optional[str] = None
        # Import here to avoid circular imports during class definition
        from tarsy.utils.logger import get_module_logger
        self.logger = get_module_logger(__name__)
        
    def needs_mcp_tools(self) -> bool:
        """All ReAct controllers use tools."""
        return True
    
    async def execute_analysis_loop(self, context: 'StageContext') -> str:
        """Consolidated ReAct loop - same for all ReAct controllers."""
        self.logger.info("Starting ReAct analysis loop")
        agent = context.agent
        if agent is None:
            raise ValueError("Agent reference is required in context")
        
        max_iterations = agent.max_iterations
        settings = get_settings()
        iteration_timeout = settings.llm_iteration_timeout
        
        # 1. Check if resuming from a paused session with conversation history
        conversation = self._restore_paused_conversation(context, self.logger)
        if conversation is None:
            conversation = self.build_initial_conversation(context)
        
        # 2. Track last interaction success for failure detection
        last_interaction_failed = False
        consecutive_timeout_failures = 0  # Track consecutive timeout failures specifically
        
        # 3. ReAct iteration loop with timeout protection  
        for iteration in range(max_iterations):
            self.logger.info(f"ReAct iteration {iteration + 1}/{max_iterations}")
            
            # Check for consecutive timeout failures (prevent infinite retry loops)
            if consecutive_timeout_failures >= 2:
                error_msg = f"Stopping after {consecutive_timeout_failures} consecutive tool timeout failures"
                self.logger.error(error_msg)
                raise Exception(error_msg)
            
            # Wrap ENTIRE iteration (LLM + tool execution) with timeout
            # This timeout is configurable and should allow MCP.s full retry cycle to complete
            try:
                # Snapshot loop variable before creating coroutine to avoid capturing changing reference
                # This silences Ruff B023 and makes behavior explicit
                convo_snapshot = conversation
                
                async def run_iteration():
                    nonlocal last_interaction_failed, consecutive_timeout_failures
                    
                    # 3. Call LLM with current conversation
                    # Extract native tools override from context (if specified)
                    native_tools_override = self._get_native_tools_override(context)
                    
                    # Get parallel execution metadata for streaming
                    parallel_metadata = context.agent.get_parallel_execution_metadata()
                    
                    conversation_result = await self.llm_manager.generate_response(
                        conversation=convo_snapshot,
                        session_id=context.session_id,
                        stage_execution_id=context.agent.get_current_stage_execution_id(),
                        provider=self._llm_provider_name,
                        native_tools_override=native_tools_override,
                        parallel_metadata=parallel_metadata
                    )
                    
                    # 4. Extract and parse assistant response
                    assistant_message = conversation_result.get_latest_assistant_message()
                    if not assistant_message:
                        stage_execution_id = context.agent.get_current_stage_execution_id()
                        error_msg = (
                            f"No assistant response received from LLM - "
                            f"session_id={context.session_id}, stage_execution_id={stage_execution_id}"
                        )
                        self.logger.error(error_msg)
                        raise RuntimeError("No assistant response received from LLM")
                    
                    response = assistant_message.content
                    self.logger.debug(f"LLM Response (first 500 chars): {response[:500]}")
                    
                    parsed_response = ReActParser.parse_response(response)
                    
                    # Mark this interaction as successful
                    last_interaction_failed = False
                    consecutive_timeout_failures = 0  # Reset on successful LLM call
                    
                    # 5. Handle final answer (completion)
                    if parsed_response.is_final_answer:
                        self.logger.info("ReAct analysis completed with final answer")
                        self._last_conversation = conversation_result  # Store for investigation_history
                        return self._build_final_result(conversation_result, parsed_response.final_answer)
                    
                    # 6. Handle unknown tool (tool name doesn't match available tools)
                    elif parsed_response.is_unknown_tool:
                        self.logger.warning(f"Unknown tool attempted: {parsed_response.action}")
                        
                        # Format error observation using ReActParser (lists all available tools)
                        error_observation = ReActParser.format_unknown_tool_error(
                            parsed_response.error_message,
                            context.available_tools.tools
                        )
                        
                        conversation_result.append_observation(f"Observation: {error_observation}")
                        self.logger.debug("Unknown tool error observation added to conversation")
                        
                    # 7. Handle tool action
                    elif parsed_response.has_action:
                        try:
                            self.logger.debug(f"ReAct Action: {parsed_response.action} with input: {parsed_response.action_input[:100] if parsed_response.action_input else 'None'}...")
                            
                            # Execute tool using parsed tool call, passing conversation context for summarization
                            # Pass MCP selection from context to enforce tool restrictions
                            mcp_data = await agent.execute_mcp_tools(
                                [parsed_response.tool_call.model_dump()], 
                                context.session_id, 
                                conversation_result,
                                context.chain_context.mcp
                            )
                            
                            # Format observation
                            observation = ReActParser.format_observation(mcp_data)
                            conversation_result.append_observation(f"Observation: {observation}")
                            
                            self.logger.debug(f"ReAct Observation: {observation[:150]}...")
                            
                        except Exception as e:
                            self.logger.error(f"Failed to execute ReAct action: {str(e)}")
                            error_observation = f"Error executing action: {str(e)}"
                            conversation_result.append_observation(f"Observation: {error_observation}")
                            
                            # Track timeout failures specifically
                            error_str = str(e).lower()
                            if 'timeout' in error_str or 'timed out' in error_str:
                                consecutive_timeout_failures += 1
                                self.logger.warning(f"Tool timeout detected ({consecutive_timeout_failures} consecutive)")
                            else:
                                consecutive_timeout_failures = 0  # Reset on non-timeout errors
                            
                    # 8. Handle malformed response
                    else:
                        self.logger.warning("ReAct response is malformed - keeping it and sending specific error feedback")
                        
                        # Keep the malformed message in context so LLM can see what it produced
                        # Generate specific feedback about what was missing/wrong
                        error_feedback = ReActParser.get_format_error_feedback(parsed_response)
                        conversation_result.append_observation(error_feedback)
                    
                    return conversation_result
                
                # Run iteration with configurable timeout (allows full MCP retry cycle to complete)
                # If tools consistently timeout, consecutive_timeout_failures check will break the loop
                result = await asyncio.wait_for(run_iteration(), timeout=iteration_timeout)
                
                # Check if we got a final answer (string) or a conversation object
                if isinstance(result, str):
                    # Final answer - return it immediately
                    return result
                else:
                    # Update conversation for next iteration
                    conversation = result
                    
            except asyncio.TimeoutError:
                error_msg = f"Iteration {iteration + 1} exceeded {iteration_timeout}s timeout - LLM or tool call stuck"
                self.logger.error(error_msg)
                consecutive_timeout_failures += 1
                self.logger.warning(f"Iteration timeout ({consecutive_timeout_failures} consecutive)")
                
                # Check if we should stop
                if consecutive_timeout_failures >= 2:
                    raise Exception(f"Stopping after {consecutive_timeout_failures} consecutive iteration timeouts") from None
                
                # Otherwise, append error observation and continue
                error_observation = f"Error: {error_msg}"
                conversation.append_observation(f"Observation: {error_observation}")
                    
            except Exception as e:
                stage_execution_id = context.agent.get_current_stage_execution_id() if context.agent else None
                self.logger.error(
                    f"ReAct iteration {iteration + 1} failed: {str(e)} - "
                    f"session_id={context.session_id}, stage_execution_id={stage_execution_id}",
                    exc_info=True
                )
                # Mark this interaction as failed
                last_interaction_failed = True
                
                # Check if it's a timeout-related failure
                error_str = str(e).lower()
                if 'timeout' in error_str or 'timed out' in error_str:
                    consecutive_timeout_failures += 1
                    self.logger.warning(f"Exception contains timeout ({consecutive_timeout_failures} consecutive)")
                    if consecutive_timeout_failures >= 2:
                        raise Exception(f"Stopping after {consecutive_timeout_failures} consecutive timeout failures") from e
                else:
                    consecutive_timeout_failures = 0  # Reset on non-timeout errors
                
                # Remove malformed assistant message if present (LLM call succeeded but processing failed)
                if conversation.messages and conversation.messages[-1].role == MessageRole.ASSISTANT:
                    conversation.messages.pop()
                    self.logger.debug("Removed malformed assistant message after exception")
                
                # Add format correction instead of generic error message
                format_reminder = ReActParser.get_format_correction_reminder()
                conversation.append_observation(format_reminder)
                continue
                
        # 8. Max iterations reached - pause for user action or fail
        self._raise_max_iterations_exception(
            max_iterations=max_iterations,
            last_interaction_failed=last_interaction_failed,
            conversation=conversation,
            context=context,
            logger=self.logger
        )

    @abstractmethod
    def build_initial_conversation(self, context: 'StageContext') -> 'LLMConversation':
        """Build controller-specific initial conversation."""
        pass
        
    def _build_final_result(self, conversation, final_answer: str) -> str:
        """
        Return the last assistant message containing the final analysis.
        
        Subsequent stages only need the conclusion/final answer, not the detailed
        investigation steps (Thought/Action/Observation sequences).
        """
        if not hasattr(conversation, 'messages') or not conversation.messages:
            return final_answer
        
        # Get the last assistant message (which contains the Final Answer)
        for message in reversed(conversation.messages):
            if message.role == MessageRole.ASSISTANT:
                return message.content
        
        # Fallback if no assistant message found
        return final_answer
    