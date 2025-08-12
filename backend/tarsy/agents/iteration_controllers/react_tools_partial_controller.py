"""
ReAct Tools + Partial Analysis iteration controller for incremental analysis stages.

This controller implements the ReAct pattern for both data collection and 
stage-specific analysis, providing incremental insights during chain processing.
"""

from typing import TYPE_CHECKING

from tarsy.utils.logger import get_module_logger
from tarsy.models.llm import LLMMessage
from .base_iteration_controller import IterationController, IterationContext

if TYPE_CHECKING:
    pass

logger = get_module_logger(__name__)


class ReactToolsPartialController(IterationController):
    """
    ReAct controller for data collection + stage-specific analysis - reuses existing ReAct infrastructure.
    
    Implements ReAct pattern that combines tool-based data collection with preliminary
    analysis, providing incremental insights while accumulating data for next stages.
    """
    
    def __init__(self, llm_client, prompt_builder):
        self.llm_client = llm_client  
        self.prompt_builder = prompt_builder
    
    def needs_mcp_tools(self) -> bool:
        """ReAct tools partial controller requires MCP tool discovery."""
        return True
    
    async def execute_analysis_loop(self, context: IterationContext) -> str:
        """Execute ReAct loop with data collection AND partial analysis using existing ReAct format."""
        logger.info("Starting ReAct Tools + Partial Analysis loop")
        
        agent = context.agent
        if not agent:
            raise ValueError("Agent reference is required in context")
        
        max_iterations = agent.max_iterations
        react_history = []
        
        # Create prompt context with chain-specific data
        prompt_context = agent.create_prompt_context(
            alert_data=context.alert_data,
            runbook_content=context.runbook_content,
            mcp_data=context.initial_mcp_data,  # Include data from previous stages
            available_tools={"tools": context.available_tools},
            stage_name="partial-analysis",
            previous_stages=list(context.stage_attributed_data.keys()) if context.stage_attributed_data else None,
            stage_attributed_data=context.stage_attributed_data
        )
        
        # Execute ReAct loop using EXISTING ReAct format and parsing (same as SimpleReActController)
        for iteration in range(max_iterations):
            logger.info(f"Partial analysis iteration {iteration + 1}/{max_iterations}")
            
            try:
                # Use partial analysis prompt but SAME ReAct format
                prompt = self.prompt_builder.build_partial_analysis_react_prompt(prompt_context, react_history)
                
                # REUSE centralized ReAct system message
                messages = [
                    LLMMessage(
                        role="system", 
                        content=self.prompt_builder.get_standard_react_system_message("collecting additional data and providing stage-specific analysis")
                    ),
                    LLMMessage(role="user", content=prompt)
                ]
                
                response = await self.llm_client.generate_response(messages, context.session_id, context.agent.get_current_stage_execution_id())
                logger.info(f"LLM Response (first 500 chars): {response[:500]}")
                
                # REUSE EXISTING ReAct parsing - same parsing logic as SimpleReActController
                parsed = self.prompt_builder.parse_react_response(response)
                logger.info(f"Parsed ReAct response: {parsed}")
                
                # Add thought to history (same as SimpleReActController)
                if parsed['thought']:
                    react_history.append(f"Thought: {parsed['thought']}")
                    logger.info(f"ReAct Thought: {parsed['thought'][:150]}...")
                
                # Check if complete (partial analysis final answer)
                if parsed['is_complete'] and parsed['final_answer']:
                    logger.info("Partial analysis completed with final answer")
                    return parsed['final_answer']
                
                # Execute action if present (same tool execution as SimpleReActController)
                if parsed['action'] and parsed['action_input']:
                    try:
                        logger.info(f"ReAct Action: {parsed['action']} with input: {parsed['action_input'][:100]}...")
                        
                        # REUSE existing action-to-tool conversion
                        tool_call = self.prompt_builder.convert_action_to_tool_call(
                            parsed['action'], parsed['action_input']
                        )
                        
                        # Execute tool using agent's existing method
                        mcp_data = await agent.execute_mcp_tools([tool_call], context.session_id)
                        
                        # Store accumulated data for next stage
                        context.final_mcp_data = agent.merge_mcp_data(context.final_mcp_data, mcp_data)
                        
                        # REUSE existing observation formatting
                        observation = self.prompt_builder.format_observation(mcp_data)
                        
                        # Add to history using EXACT format from SimpleReActController
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
                    # Same prompting logic as SimpleReActController
                    logger.warning("ReAct response missing action, adding prompt to continue")
                    react_history.extend(self.prompt_builder.get_react_continuation_prompt("analysis"))
                    
                    # Prevent context overflow by truncating history if needed
                    if len(react_history) > 30:
                        react_history = self.prompt_builder.truncate_conversation_history(react_history, max_entries=25)
                
            except Exception as e:
                logger.error(f"ReAct iteration {iteration + 1} failed: {str(e)}")
                react_history.extend(self.prompt_builder.get_react_error_continuation(str(e)))
                continue
        
        # REUSE fallback logic from SimpleReActController  
        logger.warning("Partial analysis reached maximum iterations without final answer")
        
        final_prompt = f"""Based on the investigation so far, provide your stage-specific analysis.

Investigation History:
{chr(10).join(react_history)}

Please provide a final analysis based on what you've discovered, even if the investigation isn't complete."""
        
        try:
            messages = [
                LLMMessage(
                    role="system", 
                    content="Provide stage-specific analysis based on the available information."
                ),
                LLMMessage(role="user", content=final_prompt)
            ]
            
            fallback_response = await self.llm_client.generate_response(messages, context.session_id, context.agent.get_current_stage_execution_id())
            return f"Partial analysis completed (reached max iterations):\\n\\n{fallback_response}"
            
        except Exception as e:
            logger.error(f"Failed to generate fallback analysis: {str(e)}")
            return f"Partial analysis incomplete: reached maximum iterations ({max_iterations}) without final answer. Last investigation steps:\\n\\n{chr(10).join(react_history[-5:])}"