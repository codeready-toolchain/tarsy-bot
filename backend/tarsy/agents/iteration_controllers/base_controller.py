"""
Base iteration controller interface and shared types.

This module provides the minimal interface and types needed by 
all iteration controller implementations.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

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
        
        lines = analysis_result.split('\n')
        
        # Look for final answer first (universal across all ReAct controllers)
        final_answer_content = []
        collecting_final_answer = False
        
        for i, line in enumerate(lines):
            if line.startswith("Final Answer:"):
                collecting_final_answer = True
                # Add content from the same line if any
                content = line.replace("Final Answer:", "").strip()
                if content:
                    final_answer_content.append(content)
                continue
            
            if collecting_final_answer:
                # Stop collecting if we hit another ReAct section
                if (line.startswith("Thought:") or 
                    line.startswith("Action:") or 
                    line.startswith("Observation:")):
                    break
                
                # Add all content lines (including empty ones within the final answer)
                final_answer_content.append(line)
        
        if final_answer_content:
            # Clean up trailing empty lines but preserve internal structure
            while final_answer_content and final_answer_content[-1].strip() == "":
                final_answer_content.pop()
            return '\n'.join(final_answer_content)
        
        # Look for stage-specific completion patterns
        for line in lines:
            for pattern in completion_patterns:
                if pattern in line and ":" in line:
                    summary_start = line.find(':') + 1
                    return line[summary_start:].strip()
        
        # Look for incomplete patterns
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
        
        # 2. ReAct iteration loop with timeout protection  
        for iteration in range(max_iterations):
            self.logger.info(f"ReAct iteration {iteration + 1}/{max_iterations}")
            
            try:
                # 3. Call LLM with current conversation
                conversation = await self.llm_client.generate_response(
                    conversation=conversation,
                    session_id=context.session_id,
                    stage_execution_id=context.agent.get_current_stage_execution_id()
                )
                
                # 4. Extract and parse assistant response
                assistant_message = conversation.get_latest_assistant_message()
                if not assistant_message:
                    raise Exception("No assistant response received from LLM")
                
                response = assistant_message.content
                self.logger.debug(f"LLM Response (first 500 chars): {response[:500]}")
                
                parsed_response = self.parser.parse_response(response)
                
                # 5. Handle final answer (completion)
                if parsed_response.is_final_answer:
                    self.logger.info("ReAct analysis completed with final answer")
                    return self._build_final_result(conversation, parsed_response.final_answer)
                    
                # 6. Handle tool action
                elif parsed_response.has_action:
                    try:
                        self.logger.debug(f"ReAct Action: {parsed_response.action} with input: {parsed_response.action_input[:100] if parsed_response.action_input else 'None'}...")
                        
                        # Execute tool using parsed tool call
                        mcp_data = await agent.execute_mcp_tools([parsed_response.tool_call.model_dump()], context.session_id)
                        
                        # Format observation
                        observation = self.parser.format_observation(mcp_data)
                        conversation.append_observation(f"Observation: {observation}")
                        
                        self.logger.debug(f"ReAct Observation: {observation[:150]}...")
                        
                    except Exception as e:
                        self.logger.error(f"Failed to execute ReAct action: {str(e)}")
                        error_observation = f"Error executing action: {str(e)}"
                        conversation.append_observation(f"Observation: {error_observation}")
                        
                # 7. Handle malformed response
                else:
                    self.logger.warning("ReAct response missing action, adding continuation prompt")
                    continuation_prompt = self.parser.get_continuation_prompt()
                    conversation.append_observation(continuation_prompt)
                    
            except Exception as e:
                self.logger.error(f"ReAct iteration {iteration + 1} failed: {str(e)}")
                # Add error continuation and continue with next iteration
                error_continuation = self.parser.get_error_continuation(str(e))
                conversation.append_observation(error_continuation)
                continue
                
        # 8. Timeout handling
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
            if message.role == "assistant":
                # Assistant messages contain Thought/Action sequences
                conversation_parts.append(message.content)
            elif message.role == "user" and message.content.startswith("Observation:"):
                # User messages with observations.
                # Skip user messages that are not observations (e.g. error-continuation messages)
                conversation_parts.append(message.content)
        
        # Join all the conversation parts
        complete_conversation = "\n".join(conversation_parts)
        return complete_conversation
    