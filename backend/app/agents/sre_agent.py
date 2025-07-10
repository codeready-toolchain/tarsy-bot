"""
SRE Agent using LangChain and LangGraph for incident response workflow.
Replaces the custom iterative loop with proper LangChain agent abstractions.
"""

import json
from typing import Dict, List, Optional, Any, Annotated, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import BaseTool
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from app.models.alert import Alert
from app.integrations.llm.langchain_client import LangChainLLMClient
from app.integrations.mcp.mcp_tools import MCPToolkit
from app.services.runbook_service import RunbookService
from app.config.settings import Settings
from app.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class SREAgentState(TypedDict):
    """State for the SRE agent workflow."""
    messages: Annotated[List[BaseMessage], add_messages]
    alert: Alert
    runbook_data: Dict[str, Any]
    investigation_history: List[Dict[str, Any]]
    iteration_count: int
    max_iterations: int
    gathered_data: Dict[str, Any]
    analysis_complete: bool
    final_analysis: Optional[str]


class SREAgent:
    """SRE Agent using LangChain and LangGraph for incident response."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.llm_client = LangChainLLMClient(settings)
        self.runbook_service = RunbookService(settings)
        self.mcp_toolkit: Optional[MCPToolkit] = None
        self.tools: List[BaseTool] = []
        self.graph = None
        self.memory = MemorySaver()
        
    async def initialize(self, mcp_toolkit: MCPToolkit):
        """Initialize the agent with MCP tools."""
        self.mcp_toolkit = mcp_toolkit
        self.tools = await mcp_toolkit.get_tools()
        logger.info(f"Initialized SRE agent with {len(self.tools)} tools")
        
        # Build the workflow graph
        self._build_workflow_graph()
    
    def _build_workflow_graph(self):
        """Build the LangGraph workflow for SRE incident response."""
        # Create the workflow graph
        workflow = StateGraph(SREAgentState)
        
        # Add nodes
        workflow.add_node("initialize", self._initialize_investigation)
        workflow.add_node("plan_next_steps", self._plan_next_steps)
        workflow.add_node("execute_tools", ToolNode(self.tools))
        workflow.add_node("analyze_results", self._analyze_results)
        workflow.add_node("final_analysis", self._perform_final_analysis)
        workflow.add_node("complete", self._complete_investigation)
        
        # Set entry point
        workflow.set_entry_point("initialize")
        
        # Add edges
        workflow.add_edge("initialize", "plan_next_steps")
        workflow.add_conditional_edges(
            "plan_next_steps",
            self._should_continue_investigation,
            {
                "continue": "execute_tools",
                "finish": "final_analysis"
            }
        )
        workflow.add_edge("execute_tools", "analyze_results")
        workflow.add_conditional_edges(
            "analyze_results",
            self._check_iteration_limit,
            {
                "continue": "plan_next_steps",
                "finish": "final_analysis"
            }
        )
        workflow.add_edge("final_analysis", "complete")
        workflow.add_edge("complete", END)
        
        # Compile the graph
        self.graph = workflow.compile(checkpointer=self.memory)
    
    async def process_alert(self, alert: Alert, progress_callback: Optional[callable] = None) -> str:
        """Process an alert using the LangGraph workflow."""
        try:
            # Download runbook
            if progress_callback:
                await progress_callback(10, "Downloading runbook")
            
            runbook_content = await self.runbook_service.download_runbook(alert.runbook)
            runbook_data = self.runbook_service.parse_runbook(runbook_content)
            
            # Initialize state
            initial_state = SREAgentState(
                messages=[
                    SystemMessage(content="""You are an expert SRE agent investigating a system alert. 
                    Your goal is to gather necessary information and provide a comprehensive analysis."""),
                    HumanMessage(content=f"""Alert: {alert.alert}
                    Severity: {alert.severity}
                    Environment: {alert.environment}
                    Cluster: {alert.cluster}
                    Namespace: {alert.namespace}
                    Pod: {alert.pod}
                    Message: {alert.message}
                    
                    Please investigate this alert and provide a detailed analysis.""")
                ],
                alert=alert,
                runbook_data=runbook_data,
                investigation_history=[],
                iteration_count=0,
                max_iterations=self.settings.max_llm_mcp_iterations,
                gathered_data={},
                analysis_complete=False,
                final_analysis=None
            )
            
            # Run the workflow
            config = RunnableConfig(
                configurable={"thread_id": f"alert_{alert.alert}"}
            )
            
            final_state = None
            async for state in self.graph.astream(initial_state, config=config):
                final_state = state
                
                # Update progress based on iteration
                if progress_callback and "iteration_count" in state:
                    progress = min(20 + (state["iteration_count"] * 60 // state["max_iterations"]), 90)
                    await progress_callback(progress, f"Investigation iteration {state['iteration_count']}")
            
            # Complete
            if progress_callback:
                await progress_callback(100, "Analysis complete")
            
            # Debug logging to understand the final state
            logger.info(f"Final state keys: {list(final_state.keys()) if final_state else 'None'}")
            if final_state and "final_analysis" in final_state:
                logger.info(f"Final analysis found: {final_state['final_analysis'][:200]}..." if len(final_state['final_analysis']) > 200 else final_state['final_analysis'])
            else:
                logger.error("No final_analysis in final state!")
                logger.error(f"Final state content: {final_state}")
            
            # Return final analysis
            return final_state.get("final_analysis", "Analysis could not be completed")
            
        except Exception as e:
            error_msg = f"Alert processing failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            if progress_callback:
                await progress_callback(0, error_msg)
            raise
    
    async def _initialize_investigation(self, state: SREAgentState, config: RunnableConfig) -> SREAgentState:
        """Initialize the investigation."""
        logger.info("Starting SRE investigation")
        
        # Add initial system message
        new_message = AIMessage(content="Investigation initialized. Starting analysis...")
        
        return {
            **state,
            "messages": [*state["messages"], new_message],
            "iteration_count": 0
        }
    
    async def _plan_next_steps(self, state: SREAgentState, config: RunnableConfig) -> SREAgentState:
        """Plan the next steps in the investigation."""
        logger.info(f"Planning next steps for iteration {state['iteration_count'] + 1}")
        
        # Get available tools info
        available_tools = {}
        for tool in self.tools:
            server_name = tool.name.split('_')[0]
            tool_name_without_prefix = '_'.join(tool.name.split('_')[1:])  # Remove server prefix
            if server_name not in available_tools:
                available_tools[server_name] = []
            available_tools[server_name].append({
                'name': tool_name_without_prefix,
                'full_name': tool.name,
                'description': tool.description
            })
        
        # Determine next steps using LLM
        next_action = await self.llm_client.determine_next_steps(
            state["alert"],
            available_tools,
            state["investigation_history"]
        )
        
        # Update state with the decision
        decision_message = AIMessage(
            content=f"Decision: {next_action['reasoning']}"
        )
        
        # Convert tools to tool calls if we should continue
        if next_action.get("continue", False):
            tools_to_call = []
            for tool_spec in next_action.get("tools", []):
                server = tool_spec['server']
                tool = tool_spec['tool']
                
                # Handle tool names that already include server prefix
                if tool.startswith(f"{server}_"):
                    tool_name = tool
                else:
                    tool_name = f"{server}_{tool}"
                
                tools_to_call.append({
                    "name": tool_name,
                    "args": tool_spec.get("parameters", {}),
                    "id": f"call_{len(tools_to_call)}",
                    "type": "tool_call"
                })
            
            # Create message with tool calls
            tool_call_message = AIMessage(
                content="Executing tools to gather more information...",
                tool_calls=tools_to_call
            )
            
            return {
                **state,
                "messages": [*state["messages"], decision_message, tool_call_message],
                "iteration_count": state["iteration_count"] + 1
            }
        else:
            return {
                **state,
                "messages": [*state["messages"], decision_message],
                "analysis_complete": True
            }
    
    async def _analyze_results(self, state: SREAgentState, config: RunnableConfig) -> SREAgentState:
        """Analyze the results from tool execution."""
        logger.info(f"Analyzing results for iteration {state['iteration_count']}")
        
        # Get the last few messages to find tool results
        recent_messages = state["messages"][-5:]
        tool_results = {}
        
        for msg in recent_messages:
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                # This is a tool call message
                pass
            elif hasattr(msg, 'name') and msg.name:
                # This is a tool result message
                tool_results[msg.name] = msg.content
        
        # Perform partial analysis
        partial_analysis = await self.llm_client.analyze_partial_results(
            state["alert"],
            tool_results
        )
        
        # Record this iteration in history
        iteration_record = {
            "iteration": state["iteration_count"],
            "tools_called": list(tool_results.keys()),
            "mcp_data": tool_results,
            "partial_analysis": partial_analysis
        }
        
        # Update gathered data
        new_gathered_data = {**state["gathered_data"]}
        for tool_name, result in tool_results.items():
            server_name = tool_name.split('_')[0]
            if server_name not in new_gathered_data:
                new_gathered_data[server_name] = []
            new_gathered_data[server_name].append(result)
        
        # Add analysis message
        analysis_message = AIMessage(content=f"Iteration {state['iteration_count']} analysis: {partial_analysis}")
        
        return {
            **state,
            "messages": [*state["messages"], analysis_message],
            "investigation_history": [*state["investigation_history"], iteration_record],
            "gathered_data": new_gathered_data
        }
    
    async def _perform_final_analysis(self, state: SREAgentState, config: RunnableConfig) -> SREAgentState:
        """Perform final comprehensive analysis."""
        logger.info("=== PERFORMING FINAL ANALYSIS ===")
        logger.info(f"Alert: {state['alert'].alert}")
        logger.info(f"Gathered data keys: {list(state['gathered_data'].keys())}")
        
        try:
            # Perform comprehensive analysis
            final_analysis = await self.llm_client.analyze_alert(
                state["alert"],
                state["runbook_data"],
                state["gathered_data"]
            )
            
            logger.info(f"Final analysis completed successfully: {len(final_analysis)} characters")
            logger.info(f"Final analysis preview: {final_analysis[:200]}...")
            
            final_message = AIMessage(content=f"Final Analysis:\n{final_analysis}")
            
            result = {
                **state,
                "messages": [*state["messages"], final_message],
                "final_analysis": final_analysis,
                "analysis_complete": True
            }
            
            logger.info("Final analysis state update completed")
            return result
            
        except Exception as e:
            logger.error(f"Final analysis failed: {str(e)}")
            # Return state with error message as final analysis
            error_analysis = f"Final analysis failed: {str(e)}"
            return {
                **state,
                "messages": [*state["messages"], AIMessage(content=f"Error in final analysis: {str(e)}")],
                "final_analysis": error_analysis,
                "analysis_complete": True
            }
    
    async def _complete_investigation(self, state: SREAgentState, config: RunnableConfig) -> SREAgentState:
        """Complete the investigation."""
        logger.info("Investigation completed")
        logger.info(f"Preserving final_analysis: {bool(state.get('final_analysis'))}")
        
        completion_message = AIMessage(content="Investigation completed successfully.")
        
        return {
            **state,
            "messages": [*state["messages"], completion_message],
            # Explicitly preserve the final_analysis from the previous state
            "final_analysis": state.get("final_analysis"),
            "analysis_complete": True
        }
    
    def _should_continue_investigation(self, state: SREAgentState) -> str:
        """Determine if investigation should continue."""
        logger.info(f"Checking if investigation should continue: analysis_complete={state.get('analysis_complete', False)}, iteration_count={state['iteration_count']}, max_iterations={state['max_iterations']}")
        
        if state.get("analysis_complete", False):
            logger.info("Investigation stopping: analysis marked as complete")
            return "finish"
        
        # Check iteration limit
        if state["iteration_count"] >= state["max_iterations"]:
            logger.info("Investigation stopping: reached maximum iterations")
            return "finish"
        
        logger.info("Investigation continuing")
        return "continue"
    
    def _check_iteration_limit(self, state: SREAgentState) -> str:
        """Check if we've reached the iteration limit."""
        total_data_points = sum(len(data) if isinstance(data, list) else 1 
                               for data in state["gathered_data"].values())
        
        logger.info(f"Checking iteration limit: iteration_count={state['iteration_count']}, max_iterations={state['max_iterations']}, total_data_points={total_data_points}")
        
        if state["iteration_count"] >= state["max_iterations"]:
            logger.info("Iteration limit reached: maximum iterations")
            return "finish"
        
        # Check if we have enough data (simple heuristic)
        if total_data_points >= 5 and state["iteration_count"] >= 3:
            logger.info("Iteration limit reached: sufficient data collected")
            return "finish"
        
        logger.info("Iteration continuing")
        return "continue" 