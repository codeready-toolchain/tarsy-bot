"""
Base iteration controller interface and shared types.

This module provides the minimal interface and types needed by 
all iteration controller implementations.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ...models.unified_interactions import MessageRole
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

    def _extract_react_final_analysis(
        self, 
        analysis_result: str, 
        completion_patterns: list[str], 
        incomplete_patterns: list[str],
        fallback_message: str,
        context: 'StageContext'
    ) -> str:
        """
        Shared utility for extracting final analysis from ReAct conversations.
        
        Uses ReActParser to properly handle all edge cases.
        
        Args:
            analysis_result: Full ReAct conversation history
            completion_patterns: List of patterns to look for completion messages
            incomplete_patterns: List of patterns for incomplete messages
            fallback_message: Default message if no analysis found
            context: StageContext containing all stage processing data
            
        Returns:
            Extracted final analysis
        """
        if not analysis_result:
            return fallback_message
        
        # Use ReActParser to extract sections
        sections = ReActParser._extract_sections(analysis_result)
        
        # Check if Final Answer was found by the parser
        if sections.get('final_answer'):
            final_answer = sections['final_answer'].strip()
            if final_answer:
                return final_answer
        
        # Fallback: Look for stage-specific completion patterns
        lines = analysis_result.split('\n')
        for line in lines:
            for pattern in completion_patterns:
                if pattern in line and ":" in line:
                    summary_start = line.find(':') + 1
                    return line[summary_start:].strip()
        
        # Fallback: Look for incomplete patterns
        for line in lines:
            for pattern in incomplete_patterns:
                if line.startswith(pattern):
                    return f"{pattern.rstrip(':')} due to iteration limits"
        
        return fallback_message


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
        from tarsy.agents.parsers.react_parser import ReActParser
        self.logger = get_module_logger(__name__)
        self.parser = ReActParser
        
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
        
        # 1. Build initial conversation (controller-specific)
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
            # This timeout is longer than MCP's full retry cycle (2 × 60s = 120s) to allow retries to complete
            try:
                async def run_iteration():
                    nonlocal conversation, last_interaction_failed, consecutive_timeout_failures
                    
                    # 3. Call LLM with current conversation
                    conversation_result = await self.llm_client.generate_response(
                        conversation=conversation,
                        session_id=context.session_id,
                        stage_execution_id=context.agent.get_current_stage_execution_id()
                    )
                    
                    # 4. Extract and parse assistant response
                    assistant_message = conversation_result.get_latest_assistant_message()
                    if not assistant_message:
                        raise Exception("No assistant response received from LLM")
                    
                    response = assistant_message.content
                    self.logger.debug(f"LLM Response (first 500 chars): {response[:500]}")
                    
                    parsed_response = self.parser.parse_response(response)
                    
                    # Mark this interaction as successful
                    last_interaction_failed = False
                    consecutive_timeout_failures = 0  # Reset on successful LLM call
                    
                    # 5. Handle final answer (completion)
                    if parsed_response.is_final_answer:
                        self.logger.info("ReAct analysis completed with final answer")
                        return self._build_final_result(conversation_result, parsed_response.final_answer)
                        
                    # 6. Handle tool action
                    elif parsed_response.has_action:
                        try:
                            self.logger.debug(f"ReAct Action: {parsed_response.action} with input: {parsed_response.action_input[:100] if parsed_response.action_input else 'None'}...")
                            
                            # Execute tool using parsed tool call, passing conversation context for summarization
                            mcp_data = await agent.execute_mcp_tools([parsed_response.tool_call.model_dump()], context.session_id, conversation_result)
                            
                            # Format observation
                            observation = self.parser.format_observation(mcp_data)
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
                            
                    # 7. Handle malformed response
                    else:
                        self.logger.warning("ReAct response is malformed - removing it and sending format correction")
                        
                        # Remove the malformed assistant message from conversation
                        # This prevents the LLM from seeing its own malformed output
                        if conversation_result.messages and conversation_result.messages[-1].role == MessageRole.ASSISTANT:
                            conversation_result.messages.pop()
                            self.logger.debug("Removed malformed assistant message from conversation")
                        
                        # Add brief format correction reminder as user message
                        format_reminder = self.parser.get_format_correction_reminder()
                        conversation_result.append_observation(format_reminder)
                    
                    return conversation_result
                
                # Run iteration with 180s timeout (allows full MCP retry cycle: 2 × 60s + overhead)
                # If tools consistently timeout, consecutive_timeout_failures check will break the loop
                result = await asyncio.wait_for(run_iteration(), timeout=180)
                
                # Check if we got a final answer (string) or a conversation object
                if isinstance(result, str):
                    # Final answer - return it immediately
                    return result
                else:
                    # Update conversation for next iteration
                    conversation = result
                    
            except asyncio.TimeoutError:
                error_msg = f"Iteration {iteration + 1} exceeded 180s timeout - LLM or tool call stuck"
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
                format_reminder = self.parser.get_format_correction_reminder()
                conversation.append_observation(format_reminder)
                continue
                
        # 8. Timeout handling - check if stage should be marked as failed
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
            # Max iterations reached but last interaction was successful - return incomplete result
            self.logger.warning("ReAct analysis reached maximum iterations without final answer")
            return f"Analysis incomplete: reached maximum iterations ({max_iterations}) without final answer"

    @abstractmethod
    def build_initial_conversation(self, context: 'StageContext') -> 'LLMConversation':
        """Build controller-specific initial conversation."""
        pass
        
    def _build_final_result(self, conversation, final_answer: str) -> str:
        """
        Build complete ReAct conversation history for progressive conversation format.
        
        This returns the complete conversation history with all Thought/Action/Observation
        sequences plus the final answer, which is what subsequent stages need to see
        according to progressive conversation format.
        """
        if not hasattr(conversation, 'messages') or not conversation.messages:
            return final_answer
        
        # Extract the complete conversation history from the LLMConversation
        conversation_parts = []
        
        # Skip the system message and initial user message, focus on the ReAct interactions
        for message in conversation.messages[2:]:  # Skip system and initial user message
            if message.role == MessageRole.ASSISTANT:
                # Assistant messages contain Thought/Action sequences
                conversation_parts.append(message.content)
            elif message.role == MessageRole.USER and message.content.startswith("Observation:"):
                # User messages with observations.
                # Skip user messages that are not observations (e.g. error-continuation messages)
                conversation_parts.append(message.content)
        
        # Join all the conversation parts
        complete_conversation = "\n".join(conversation_parts)
        
        # If we only have a single "Final Answer:" response with no ReAct interactions,
        # return just the final answer content for cleaner API consumption
        if (len(conversation_parts) == 1 and 
            conversation_parts[0].startswith("Final Answer:") and 
            "Thought:" not in conversation_parts[0] and 
            "Action:" not in conversation_parts[0]):
            return conversation_parts[0].replace("Final Answer:", "").strip()
        
        return complete_conversation
    