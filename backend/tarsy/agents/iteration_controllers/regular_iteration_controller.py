"""
Regular iteration controller for simple processing flow.

This controller implements straightforward analysis without ReAct reasoning complexity,
focusing on tool selection and execution for faster processing.
"""

from typing import TYPE_CHECKING

from tarsy.utils.logger import get_module_logger
from .base_iteration_controller import IterationController, IterationContext

logger = get_module_logger(__name__)


class RegularIterationController(IterationController):
    """
    Clean regular iteration flow without ReAct reasoning complexity.
    
    This controller implements the straightforward analysis loop without
    explicit reasoning steps, focusing on tool selection and execution.
    """
    
    def needs_mcp_tools(self) -> bool:
        """Regular iteration requires MCP tool discovery."""
        return True
    
    async def execute_analysis_loop(self, context: IterationContext) -> str:
        """Execute regular analysis loop with iterative tool selection."""
        logger.info("Starting regular analysis loop")
        
        agent = context.agent
        if not agent:
            raise ValueError("Agent reference is required in context")
        
        # Step 1: Determine initial MCP tools to call based on alert and runbook
        try:
            initial_tools = await agent.determine_mcp_tools(
                context.alert_data,
                context.runbook_content, 
                {"tools": context.available_tools},
                context.session_id
            )
            logger.info(f"Selected {len(initial_tools)} initial tools for investigation")
        except Exception as e:
            logger.error(f"Tool selection failed: {str(e)}")
            # If tool selection fails, analyze with empty data
            return await agent.analyze_alert(
                context.alert_data, context.runbook_content,
                {"tool_selection_error": str(e)}, context.session_id
            )
        
        # Step 2: Execute initial MCP tools to gather investigation data
        mcp_data = {}
        iteration_history = []
        
        if initial_tools:
            try:
                mcp_data = await agent.execute_mcp_tools(initial_tools, context.session_id)
                iteration_history.append({
                    "tools_called": initial_tools,
                    "mcp_data": mcp_data
                })
                logger.info(f"Gathered initial data from {len(mcp_data)} MCP servers")
            except Exception as e:
                logger.error(f"MCP tool execution failed: {str(e)}")
                mcp_data = {"tool_execution_error": str(e)}
                # Early return if initial execution fails
                return await agent.analyze_alert(
                    context.alert_data, context.runbook_content, 
                    mcp_data, context.session_id
                )
        
        # Step 3: Iterative tool selection and execution until ready for analysis
        iteration_count = 0
        max_iterations = agent.max_iterations
        
        while iteration_count < max_iterations:
            try:
                # Ask agent if it needs more tools based on what we've learned
                next_action = await agent.determine_next_mcp_tools(
                    context.alert_data, context.runbook_content,
                    {"tools": context.available_tools}, iteration_history,
                    iteration_count, context.session_id
                )
                
                # Ensure next_action is a dict to avoid attribute errors
                if not isinstance(next_action, dict):
                    logger.error(f"Expected dict from determine_next_mcp_tools, got {type(next_action)}")
                    next_action = {}
                
                # Check if we should continue
                if not next_action.get("continue", False):
                    logger.info(f"Analysis ready after {iteration_count} iterations")
                    break
                    
                # Execute additional tools if any
                additional_tools = next_action.get("tools", [])
                if additional_tools:
                    logger.info(
                        f"Iteration {iteration_count + 1}: Executing "
                        f"{len(additional_tools)} additional tools"
                    )
                    
                    additional_mcp_data = await agent.execute_mcp_tools(
                        additional_tools, context.session_id
                    )
                    
                    # Merge with existing data
                    mcp_data = agent.merge_mcp_data(mcp_data, additional_mcp_data)
                    
                    # Add to iteration history
                    iteration_history.append({
                        "tools_called": additional_tools,
                        "mcp_data": additional_mcp_data
                    })
                    
                    iteration_count += 1
                else:
                    # No tools to execute, break out of loop
                    logger.info("No additional tools needed, proceeding to analysis")
                    break
                    
            except Exception as e:
                logger.error(f"Iteration {iteration_count + 1} failed: {str(e)}")
                # Continue with what we have so far
                break
        
        # Step 4: Final analysis with all collected data
        logger.info(f"Regular analysis completed after {iteration_count} iterations")
        return await agent.analyze_alert(
            context.alert_data, context.runbook_content,
            mcp_data, context.session_id
        )
