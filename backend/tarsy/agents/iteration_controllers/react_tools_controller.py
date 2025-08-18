"""
ReAct Tools-Only iteration controller for data collection stages.

This controller implements the ReAct pattern focused purely on data collection
via MCP tools without providing analysis - passing accumulated data to next stage.
"""

from typing import TYPE_CHECKING

from tarsy.utils.logger import get_module_logger
from tarsy.models.unified_interactions import LLMMessage
from .base_iteration_controller import IterationController, IterationContext

if TYPE_CHECKING:
    pass

logger = get_module_logger(__name__)


class ReactToolsController(IterationController):
    """
    Data collection focused ReAct controller - reuses existing ReAct infrastructure.
    
    Implements ReAct pattern for tool-based data collection without analysis,
    accumulating data for subsequent stages in chain processing.
    """
    
    def __init__(self, llm_client, prompt_builder):
        """Initialize with existing infrastructure."""
        self.llm_client = llm_client
        self.prompt_builder = prompt_builder
    
    def needs_mcp_tools(self) -> bool:
        """ReAct tools controller requires MCP tool discovery."""
        return True
    
    async def execute_analysis_loop(self, context: IterationContext) -> str:
        """Execute ReAct loop focused purely on data collection using existing ReAct format."""
        logger.info("Starting ReAct Tools-Only analysis loop")
        
        agent = context.agent
        if not agent:
            raise ValueError("Agent reference is required in context")
        
        max_iterations = agent.max_iterations
        react_history = []
        
        # Create prompt context with chain-specific data
        prompt_context = agent.create_prompt_context(
            alert_data=context.alert_data,
            runbook_content=context.runbook_content,
            mcp_data={},  # Previous stage data handled at chain level
            available_tools={"tools": context.available_tools},
            stage_name="data-collection",
            previous_stages=None,  # Handled by chain context
            stage_attributed_data=None  # Handled by chain context
        )
        
        # Execute ReAct loop using EXISTING ReAct format and parsing
        for iteration in range(max_iterations):
            logger.info(f"Data collection iteration {iteration + 1}/{max_iterations}")
            
            try:
                # Use chain-specific data collection prompt but SAME ReAct format
                prompt = self.prompt_builder.build_data_collection_react_prompt(prompt_context, react_history)
                
                # Use enhanced ReAct system message with MCP server instructions
                composed_instructions = agent._compose_instructions()
                messages = [
                    LLMMessage(
                        role="system", 
                        content=self.prompt_builder.get_enhanced_react_system_message(composed_instructions, "comprehensive data collection for this stage")
                    ),
                    LLMMessage(role="user", content=prompt)
                ]
                
                response = await self.llm_client.generate_response(messages, context.session_id, agent.get_current_stage_execution_id())
                logger.debug(f"LLM Response (first 500 chars): {response[:500]}")
                
                # REUSE EXISTING ReAct parsing - critical for consistent format handling
                parsed = self.prompt_builder.parse_react_response(response)
                logger.debug(f"Parsed ReAct response: {parsed}")
                
                # Add thought to history
                if parsed['thought']:
                    react_history.append(f"Thought: {parsed['thought']}")
                    logger.debug(f"ReAct Thought: {parsed['thought'][:150]}...")
                
                # Check if complete (data collection final answer)
                if parsed['is_complete'] and parsed['final_answer']:
                    logger.debug("Data collection completed with final answer")
                    react_history.append(f"Final Answer: {parsed['final_answer']}")
                    return "\n".join(react_history)
                
                # Execute action if present - REUSE existing tool execution logic
                if parsed['action'] and parsed['action_input']:
                    try:
                        logger.debug(f"ReAct Action: {parsed['action']} with input: {parsed['action_input'][:100]}...")
                        
                        # REUSE existing action-to-tool conversion
                        tool_call = self.prompt_builder.convert_action_to_tool_call(
                            parsed['action'], parsed['action_input']
                        )
                        
                        # Execute tool using agent's existing method
                        mcp_data = await agent.execute_mcp_tools([tool_call], context.session_id)
                        
                        # REUSE existing observation formatting
                        observation = self.prompt_builder.format_observation(mcp_data)
                        
                        # Add to history using EXACT format from SimpleReActController
                        react_history.extend([
                            f"Action: {parsed['action']}",
                            f"Action Input: {parsed['action_input']}",
                            f"Observation: {observation}"
                        ])
                        
                        logger.debug(f"ReAct Observation: {observation[:150]}...")
                        
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
                    react_history.extend(self.prompt_builder.get_react_continuation_prompt("data_collection"))
                
            except Exception as e:
                logger.error(f"ReAct iteration {iteration + 1} failed: {str(e)}")
                react_history.extend(self.prompt_builder.get_react_error_continuation(str(e)))
                continue
        
        # REUSE fallback logic from SimpleReActController
        logger.warning("Data collection reached maximum iterations without final answer")
        
        # Use utility method to flatten react history
        flattened_history = self.prompt_builder._flatten_react_history(react_history)
        
        final_prompt = f"""Based on the data collection so far, provide a summary of what information was gathered.

Collection History:
{chr(10).join(flattened_history)}

Please provide a final summary of the data collected, even if the collection isn't complete."""
        
        try:
            messages = [
                LLMMessage(
                    role="system", 
                    content="Provide a summary of data collected based on the investigation."
                ),
                LLMMessage(role="user", content=final_prompt)
            ]
            
            fallback_response = await self.llm_client.generate_response(messages, context.session_id, agent.get_current_stage_execution_id())
            # Include history plus fallback data collection summary
            react_history.append(f"Data collection completed (reached max iterations):\n{fallback_response}")
            return "\n".join(react_history)
            
        except Exception as e:
            logger.error(f"Failed to generate fallback summary: {str(e)}")
            # Return complete history even when incomplete
            react_history.append(f"Data collection incomplete: reached maximum iterations ({max_iterations}) without final summary")
            return "\n".join(react_history)

    def extract_final_analysis(self, analysis_result: str, context) -> str:
        """
        Extract data collection summary from ReAct history for API consumption.
        
        For data collection stages, we want to summarize what data was collected
        rather than showing the full conversation history.
        """
        def extract_observations(lines):
            """Extract meaningful observations as fallback."""
            observations = []
            for line in lines:
                if line.startswith("Observation:"):
                    obs = line.replace("Observation:", "").strip()
                    if obs and not obs.startswith("Error"):
                        observations.append(obs)
            
            if observations:
                return f"Collected data from {len(observations)} successful operations. Latest: {observations[-1][:200]}..."
            return None
        
        return self._extract_react_final_analysis(
            analysis_result=analysis_result,
            completion_patterns=["Data collection completed"],
            incomplete_patterns=["Data collection incomplete:"],
            fallback_extractor=extract_observations,
            fallback_message="Data collection stage completed with limited results"
        )