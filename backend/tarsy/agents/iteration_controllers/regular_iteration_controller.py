"""
Regular iteration controller for simple processing flow.

This controller implements straightforward analysis without ReAct reasoning complexity,
focusing on tool selection and execution for faster processing.
"""

from typing import TYPE_CHECKING

from tarsy.utils.logger import get_module_logger
from .base_iteration_controller import IterationController, IterationContext

if TYPE_CHECKING:
    from ..base_agent import BaseAgent

logger = get_module_logger(__name__)


class RegularIterationController(IterationController):
    """
    Clean regular iteration flow without ReAct reasoning complexity.
    
    This controller implements the straightforward analysis loop without
    explicit reasoning steps, focusing on tool selection and execution.
    """
    
    async def execute_analysis_loop(self, context: IterationContext) -> str:
        """Execute regular analysis loop with simple tool iteration."""
        logger.info("Starting regular analysis loop")
        
        agent = context.agent
        if not agent:
            raise ValueError("Agent reference is required in context")
            
        # Setup initial analysis
        initial_tools, mcp_data, iteration_history = await agent._setup_initial_analysis(
            context.alert_data, context.runbook_content, 
            context.available_tools, context.session_id
        )
        
        # Early return if initial setup returned error data
        if not initial_tools and "tool_selection_error" in mcp_data:
            return await agent.analyze_alert(
                context.alert_data, context.runbook_content, 
                mcp_data, context.session_id
            )
        
        # Simple iteration loop - no ReAct conditionals
        iteration_count = 0
        max_iterations = agent._max_iterations
        
        while iteration_count < max_iterations:
            iteration_count += 1
            
            # Regular tool selection decision
            next_action = await agent.determine_next_mcp_tools(
                context.alert_data, context.runbook_content, 
                {"tools": context.available_tools}, iteration_history, 
                iteration_count, context.session_id
            )
            
            # Check if we should continue
            if not next_action.get("continue", False):
                logger.info(f"Analysis complete after {iteration_count} iterations")
                break
                
            # Execute tools if any
            additional_tools = next_action.get("tools", [])
            if additional_tools:
                additional_mcp_data = await agent._execute_mcp_tools(
                    additional_tools, context.session_id
                )
                
                # Merge with existing data
                mcp_data = agent._merge_mcp_data(mcp_data, additional_mcp_data)
                
                # Add to iteration history
                iteration_history.append({
                    "tools_called": additional_tools,
                    "mcp_data": additional_mcp_data
                })
        
        # Final analysis with all collected data
        logger.info(f"Regular analysis completed after {iteration_count} iterations")
        return await agent.analyze_alert(
            context.alert_data, context.runbook_content, 
            mcp_data, context.session_id
        )
