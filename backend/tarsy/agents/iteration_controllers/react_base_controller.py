"""
Base ReAct controller with consolidated loop logic.

This module provides the ReactController base class that implements the complete
ReAct iteration loop. Specific controllers extend this class and only need to
override build_initial_conversation() to customize their behavior.
"""

import asyncio
from abc import abstractmethod
from typing import TYPE_CHECKING, Optional

from ...config.settings import get_settings
from ...models.constants import LLMInteractionType
from ...models.unified_interactions import LLMConversation, MessageRole
from ..parsers.react_parser import ReActParser
from .base_controller import IterationController

if TYPE_CHECKING:
    from ...agents.prompts import PromptBuilder
    from ...integrations.llm.manager import LLMManager
    from ...models.processing_context import StageContext


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
                async def run_iteration():
                    nonlocal last_interaction_failed, consecutive_timeout_failures, conversation
                    
                    # 3. Call LLM with current conversation
                    # Extract native tools override from context (if specified)
                    native_tools_override = self._get_native_tools_override(context)
                    
                    # Get parallel execution metadata for streaming
                    parallel_metadata = context.agent.get_parallel_execution_metadata()
                    
                    conversation_result = await self.llm_manager.generate_response(
                        conversation=conversation,
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
                
        # 8. Max iterations reached - check if we should pause or force conclusion
        from ..exceptions import ForceConclusion
        
        try:
            self._raise_max_iterations_exception(
                max_iterations=max_iterations,
                last_interaction_failed=last_interaction_failed,
                conversation=conversation,
                context=context,
                logger=self.logger
            )
        except ForceConclusion as e:
            # Force conclusion was requested
            return await self._force_conclusion(
                conversation=e.conversation,
                context=context,
                iteration=e.iteration
            )
        # If SessionPaused is raised, it will propagate up (existing behavior)

    def _get_forced_conclusion_prompt(self, iteration: int) -> str:
        """
        Get ReAct-specific forced conclusion prompt with Final Answer requirement.
        
        Args:
            iteration: Iteration count when limit reached
            
        Returns:
            ReAct-formatted prompt requesting Final Answer
        """
        return self.prompt_builder.build_react_forced_conclusion_prompt(iteration)
    
    async def _call_llm_for_forced_conclusion(
        self,
        conversation: LLMConversation,
        context: 'StageContext',
        timeout: int
    ) -> str:
        """
        ReAct-specific LLM call using LangChain generate_response().
        
        Args:
            conversation: Current conversation with forced conclusion prompt already added
            context: Stage context
            timeout: Timeout in seconds
            
        Returns:
            Conclusion text from LLM
            
        Raises:
            asyncio.TimeoutError: If LLM call times out
            Exception: On LLM communication failures
        """
        agent = context.agent
        stage_execution_id = agent.get_current_stage_execution_id()
        
        response = await asyncio.wait_for(
            self.llm_manager.generate_response(
                conversation=conversation,
                session_id=context.session_id,
                stage_execution_id=stage_execution_id,
                interaction_type=LLMInteractionType.FORCED_CONCLUSION.value,
                # NO mcp_event_id or tools - pure LLM call
            ),
            timeout=timeout
        )
        
        # Extract final message
        final_message = response.get_latest_assistant_message()
        if final_message:
            return final_message.content
        else:
            return "Unable to generate conclusion (no response from LLM)"

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
