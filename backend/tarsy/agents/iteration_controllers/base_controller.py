"""
Base iteration controller interface and shared types.

This module provides the minimal interface and types needed by 
all iteration controller implementations.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ...models.unified_interactions import MessageRole
from ...config.settings import get_settings
from ..parsers.react_parser import ReActParser

if TYPE_CHECKING:
    from ...models.processing_context import StageContext
    from ...integrations.llm.client import LLMClient
    from ...agents.prompts import PromptBuilder
    from ...models.unified_interactions import LLMConversation

class IterationController(ABC):
    """
    Abstract controller for different iteration processing strategies.
    
    This allows clean separation between ReAct and regular processing flows
    without conditional logic scattered throughout the BaseAgent.
    """
    
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
    
    def __init__(self, llm_client: 'LLMClient', prompt_builder: 'PromptBuilder'):
        """Initialize with LLM client and prompt builder."""
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder
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
        conversation = None
        if context.stage_name in context.chain_context.stage_outputs:
            stage_result = context.chain_context.stage_outputs[context.stage_name]
            if hasattr(stage_result, 'status') and hasattr(stage_result, 'paused_conversation_state'):
                # Type-safe status comparison (handle both enum and string values)
                from tarsy.models.constants import StageStatus
                status_value = stage_result.status.value if isinstance(stage_result.status, StageStatus) else stage_result.status
                
                if status_value == StageStatus.PAUSED.value and stage_result.paused_conversation_state:
                    # Restore conversation from paused state
                    from tarsy.models.unified_interactions import LLMConversation
                    try:
                        conversation = LLMConversation.model_validate(stage_result.paused_conversation_state)
                        self.logger.info(f"Resuming from paused state with {len(conversation.messages)} messages")
                    except Exception as e:
                        self.logger.warning(f"Failed to restore conversation history: {e}, starting fresh")
                        conversation = None
        
        # Build initial conversation if not resuming
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
                    nonlocal conversation, last_interaction_failed, consecutive_timeout_failures
                    
                    # 3. Call LLM with current conversation
                    # Extract native tools override from context (if specified)
                    native_tools_override = self._get_native_tools_override(context)
                    
                    conversation_result = await self.llm_client.generate_response(
                        conversation=conversation,
                        session_id=context.session_id,
                        stage_execution_id=context.agent.get_current_stage_execution_id(),
                        native_tools_override=native_tools_override
                    )
                    
                    # 4. Extract and parse assistant response
                    assistant_message = conversation_result.get_latest_assistant_message()
                    if not assistant_message:
                        raise Exception("No assistant response received from LLM")
                    
                    response = assistant_message.content
                    self.logger.debug(f"LLM Response (first 500 chars): {response[:500]}")
                    
                    parsed_response = ReActParser.parse_response(response)
                    
                    # Mark this interaction as successful
                    last_interaction_failed = False
                    consecutive_timeout_failures = 0  # Reset on successful LLM call
                    
                    # 5. Handle final answer (completion)
                    if parsed_response.is_final_answer:
                        self.logger.info("ReAct analysis completed with final answer")
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
                        self.logger.warning("ReAct response is malformed - removing it and sending format correction")
                        
                        # Remove the malformed assistant message from conversation
                        # This prevents the LLM from seeing its own malformed output
                        if conversation_result.messages and conversation_result.messages[-1].role == MessageRole.ASSISTANT:
                            conversation_result.messages.pop()
                            self.logger.debug("Removed malformed assistant message from conversation")
                        
                        # Add brief format correction reminder as user message
                        format_reminder = ReActParser.get_format_correction_reminder()
                        conversation_result.append_observation(format_reminder)
                    
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
                self.logger.error(f"ReAct iteration {iteration + 1} failed: {str(e)}")
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
        if last_interaction_failed:
            # Stage failure: reached max iterations with failed last interaction
            from ..exceptions import MaxIterationsFailureError
            self.logger.error(f"Stage failed: reached maximum iterations ({max_iterations}) with failed last interaction")
            raise MaxIterationsFailureError(
                f"Stage failed: reached maximum iterations ({max_iterations}) and last LLM interaction failed",
                max_iterations=max_iterations,
                context={
                    "session_id": context.session_id,
                    "stage_execution_id": context.agent.get_current_stage_execution_id(),
                    "stage_name": context.stage_name
                }
            )
        else:
            # Max iterations reached but last interaction was successful - pause session
            from tarsy.agents.exceptions import SessionPaused
            self.logger.warning(f"Session paused: reached maximum iterations ({max_iterations}) without final answer")
            raise SessionPaused(
                f"Session paused at maximum iterations ({max_iterations})",
                iteration=max_iterations,
                conversation=conversation,  # Pass conversation history for resume
                context={
                    "session_id": context.session_id,
                    "stage_execution_id": context.agent.get_current_stage_execution_id(),
                    "stage_name": context.stage_name
                }
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
    