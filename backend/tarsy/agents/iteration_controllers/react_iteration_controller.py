"""
Simple ReAct iteration controller implementing the standard ReAct pattern.

This controller follows the ReAct format:
- Question: The alert analysis question
- Thought: Agent reasons about what to do next
- Action: Agent specifies which tool to use
- Action Input: Parameters for the tool
- Observation: Results from the tool execution
- (repeat until) Final Answer: Complete analysis

This is a true ReAct implementation that follows the established pattern
that LLMs are specifically trained to handle.
"""

from typing import TYPE_CHECKING

from tarsy.utils.logger import get_module_logger
from tarsy.models.unified_interactions import LLMMessage
from .base_iteration_controller import IterationController, IterationContext

if TYPE_CHECKING:
    pass
logger = get_module_logger(__name__)


class SimpleReActController(IterationController):
    """
    Simple ReAct controller following the standard Thought-Action-Observation pattern.
    
    This controller implements the true ReAct pattern where the LLM follows
    a structured format to reason about the problem, take actions, observe
    results, and continue until reaching a final answer.
    
    Key features:
    - Uses standard ReAct prompting format that LLMs are trained on
    - Structured parsing of ReAct responses  
    - Simple iterative loop with clear error handling
    - Clean separation between reasoning and tool execution
    """
    
    def __init__(self, llm_client, prompt_builder):
        """
        Initialize the simple ReAct controller.
        
        Args:
            llm_client: LLM client for generating responses
            prompt_builder: Prompt builder with ReAct methods
        """
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder
    
    def needs_mcp_tools(self) -> bool:
        """ReAct iteration requires MCP tool discovery."""
        return True
        
    async def execute_analysis_loop(self, context: IterationContext) -> str:
        """Execute simple ReAct loop following the standard pattern."""
        logger.info("Starting Standard ReAct analysis loop")
        
        agent = context.agent
        if not agent:
            raise ValueError("Agent reference is required in context")
        
        max_iterations = agent.max_iterations
        react_history = []
        
        # Create initial prompt context
        prompt_context = agent.create_prompt_context(
            alert_data=context.alert_data,
            runbook_content=context.runbook_content,
            mcp_data={},
            available_tools={"tools": context.available_tools}
        )
        
        for iteration in range(max_iterations):
            logger.info(f"ReAct iteration {iteration + 1}/{max_iterations}")
            
            try:
                # Build ReAct prompt with history
                prompt = self.prompt_builder.build_standard_react_prompt(prompt_context, react_history)
                
                # Get LLM response in ReAct format
                messages = [
                    LLMMessage(
                        role="system", 
                        content=self.prompt_builder.get_standard_react_system_message("investigation and providing recommendations")
                    ),
                    LLMMessage(role="user", content=prompt)
                ]
                
                response = await self.llm_client.generate_response(messages, context.session_id, agent.get_current_stage_execution_id())
                logger.info(f"LLM Response (first 500 chars): {response[:500]}")
                
                # Parse ReAct response
                parsed = self.prompt_builder.parse_react_response(response)
                logger.info(f"Parsed ReAct response: {parsed}")
                
                # Add thought to history
                if parsed['thought']:
                    react_history.append(f"Thought: {parsed['thought']}")
                    logger.info(f"ReAct Thought: {parsed['thought'][:150]}...")
                
                # Check if complete
                if parsed['is_complete'] and parsed['final_answer']:
                    logger.info("ReAct analysis completed with final answer")
                    return parsed['final_answer']
                
                # Execute action if present
                if parsed['action'] and parsed['action_input']:
                    try:
                        logger.info(f"ReAct Action: {parsed['action']} with input: {parsed['action_input'][:100]}...")
                        
                        # Convert to tool call format
                        tool_call = self.prompt_builder.convert_action_to_tool_call(
                            parsed['action'], parsed['action_input']
                        )
                        
                        # Execute tool
                        mcp_data = await agent.execute_mcp_tools([tool_call], context.session_id)
                        
                        # Format observation
                        observation = self.prompt_builder.format_observation(mcp_data)
                        
                        # Add to history
                        react_history.extend([
                            f"Action: {parsed['action']}",
                            f"Action Input: {parsed['action_input']}",
                            f"Observation: {observation}"
                        ])
                        
                        logger.info(f"ReAct Observation: {observation[:150]}...")
                        
                    except Exception as e:
                        logger.error(f"Failed to execute ReAct action: {str(e)}")
                        error_obs = f"Error executing action: {str(e)}"
                        react_history.extend([
                            f"Action: {parsed['action']}",
                            f"Action Input: {parsed['action_input']}",
                            f"Observation: {error_obs}"
                        ])
                
                elif not parsed['is_complete']:
                    # LLM didn't provide action but also didn't complete - prompt for action
                    logger.warning("ReAct response missing action, adding prompt to continue")
                    react_history.extend(self.prompt_builder.get_react_continuation_prompt("general"))
                    
                    # Prevent context overflow by truncating history if needed
                    if len(react_history) > 30:
                        react_history = self.prompt_builder.truncate_conversation_history(react_history, max_entries=25)
                
            except Exception as e:
                logger.error(f"ReAct iteration {iteration + 1} failed: {str(e)}")
                # Add error to history and try to continue
                react_history.extend(self.prompt_builder.get_react_error_continuation(str(e)))
                continue
        
        # If we reach max iterations without completion
        logger.warning("ReAct analysis reached maximum iterations without final answer")
        
        # Use utility method to flatten react history
        flattened_history = self.prompt_builder._flatten_react_history(react_history)
        
        # Try to get a final analysis with available information
        final_prompt = f"""Based on the investigation so far, provide your best analysis of the alert.

Investigation History:
{chr(10).join(flattened_history)}

Please provide a final answer based on what you've discovered, even if the investigation isn't complete."""
        
        try:
            messages = [
                LLMMessage(
                    role="system", 
                    content="Provide a final analysis based on the available information."
                ),
                LLMMessage(role="user", content=final_prompt)
            ]
            
            fallback_response = await self.llm_client.generate_response(messages, context.session_id, agent.get_current_stage_execution_id())
            return f"Analysis completed (reached max iterations):\n\n{fallback_response}"
            
        except Exception as e:
            logger.error(f"Failed to generate fallback analysis: {str(e)}")
            return f"Analysis incomplete: reached maximum iterations ({max_iterations}) without final answer. Last investigation steps:\n\n{chr(10).join(react_history[-5:])}"