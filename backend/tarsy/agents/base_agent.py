"""
Base agent abstract class for the multi-layer agent architecture.

This module provides the abstract base class that all specialized agents must inherit from.
It implements common processing logic and defines abstract methods for agent-specific behavior.
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING

from tarsy.config.settings import get_settings
from tarsy.integrations.llm.client import LLMClient
from tarsy.integrations.mcp.client import MCPClient

from tarsy.models.agent_execution_result import (
    AgentExecutionResult
)
from tarsy.models.constants import StageStatus

from tarsy.models.processing_context import ChainContext, StageContext, AvailableTools, MCPTool
from .iteration_controllers import (
    IterationController, SimpleReActController, ReactStageController
)
from .exceptions import (
    AgentError, 
    ToolExecutionError, ConfigurationError,
    ErrorRecoveryHandler
)
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.utils.logger import get_module_logger
from tarsy.utils.timestamp import now_us

from ..models.constants import IterationStrategy

if TYPE_CHECKING:
    from .prompt_builder import PromptBuilder
    from ..models.processing_context import ChainContext, StageContext

from .prompt_builder import get_prompt_builder

logger = get_module_logger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all specialized agents.
    
    This class provides common processing logic for alert analysis and defines
    abstract methods that must be implemented by specialized agent classes.
    
    The agent follows a three-tier instruction composition pattern:
    1. General instructions (common to all agents)
    2. MCP server-specific instructions (from assigned servers)
    3. Custom instructions (agent-specific, optional)
    
    Uses configurable iteration strategies to provide different approaches
    to alert analysis, from simple processing to transparent reasoning cycles
    for enhanced observability and decision-making.
    
    Agents also control their own prompt building to leverage domain-specific context.
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        mcp_client: MCPClient,
        mcp_registry: MCPServerRegistry,
        iteration_strategy: IterationStrategy = IterationStrategy.REACT
    ):
        """
        Initialize the base agent with required dependencies.
        
        Args:
            llm_client: Client for LLM interactions
            mcp_client: Client for MCP server interactions
            mcp_registry: Registry of MCP server configurations (REQUIRED)
            iteration_strategy: Which iteration strategy to use (configured per agent)
        """
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.mcp_registry = mcp_registry
        self._iteration_count = 0
        self._max_iterations = get_settings().max_llm_mcp_iterations
        self._configured_servers: Optional[List[str]] = None
        self._prompt_builder = get_prompt_builder()
        
        # Stage execution tracking for chain processing
        self._current_stage_execution_id: Optional[str] = None
        
        # Create appropriate iteration controller based on configuration
        self._iteration_controller: IterationController = self._create_iteration_controller(iteration_strategy)
        # Cache the iteration strategy to avoid redundant imports in property getter
        self._iteration_strategy: IterationStrategy = iteration_strategy
    
    def _create_iteration_controller(self, strategy: IterationStrategy) -> IterationController:
        """
        Factory method to create appropriate iteration controller.
        
        Args:
            strategy: Which iteration strategy to use
            
        Returns:
            Appropriate IterationController instance
        """
        if strategy == IterationStrategy.REACT:
            return SimpleReActController(self.llm_client, self._prompt_builder)
        elif strategy == IterationStrategy.REACT_STAGE:
            return ReactStageController(self.llm_client, self._prompt_builder)
        elif strategy == IterationStrategy.REACT_FINAL_ANALYSIS:
            from .iteration_controllers.react_final_analysis_controller import ReactFinalAnalysisController
            return ReactFinalAnalysisController(self.llm_client, self._prompt_builder)
        else:
            raise ValueError(f"Unknown iteration strategy: {strategy}")
    
    @property
    def iteration_strategy(self) -> IterationStrategy:
        """Get the current iteration strategy for this agent."""
        return self._iteration_strategy

    # Strategy can be overridden per stage via AgentFactory
    def set_iteration_strategy(self, strategy: IterationStrategy):
        """Update iteration strategy (used by AgentFactory for stage-specific strategies)."""
        self._iteration_controller = self._create_iteration_controller(strategy)
        self._iteration_strategy = strategy

    @property
    def max_iterations(self) -> int:
        """Get the maximum number of iterations allowed for this agent."""
        return self._max_iterations


    @abstractmethod
    def mcp_servers(self) -> List[str]:
        """
        Return the list of MCP server IDs this agent requires.
        
        This method must be implemented by each specialized agent to specify
        which MCP servers it needs for its operations.
        
        Returns:
            List of MCP server IDs (e.g., ["kubernetes-server"])
        """
        pass
    
    @abstractmethod
    def custom_instructions(self) -> str:
        """
        Return agent-specific custom instructions.
        
        This method can be implemented by specialized agents to provide
        additional guidance beyond general and MCP server instructions.
        
        Returns:
            Custom instructions as a string (can be empty)
        """
        pass



    def _get_server_specific_tool_guidance(self) -> str:
        """Get guidance text specific to this agent's assigned MCP servers."""
        guidance_parts = []
        
        # Get server configs for this agent
        server_configs = self.mcp_registry.get_server_configs(self.mcp_servers())
        
        if server_configs:
            guidance_parts.append("## Server-Specific Tool Selection Guidance")
            
            for server_config in server_configs:
                if server_config.instructions:
                    guidance_parts.append(f"### {server_config.server_type.title()} Tools")
                    guidance_parts.append(server_config.instructions)
        
        return "\n\n".join(guidance_parts) if guidance_parts else ""

    async def process_alert(self, context: ChainContext) -> AgentExecutionResult:
        """
        Process alert using the new ChainContext model.
        
        Args:
            context: ChainContext containing all alert processing data
        
        Returns:
            Structured AgentExecutionResult with rich investigation summary
        """
        return await self._process_alert_new(context)

    async def _process_alert_new(self, chain_context: ChainContext) -> AgentExecutionResult:
        """
        New implementation using ChainContext and StageContext.
        
        This will become the main process_alert implementation in Phase 6.
        
        Args:
            chain_context: ChainContext containing all processing data
        
        Returns:
            Structured AgentExecutionResult with rich investigation summary
        """
        try:
            # Configure MCP client with agent-specific servers
            await self._configure_mcp_client()
            
            # Get available tools only if the iteration strategy needs them
            if self._iteration_controller.needs_mcp_tools():
                logger.info(f"Enhanced logging: Strategy {self.iteration_strategy.value} requires MCP tool discovery")
                available_tools_list = await self._get_available_tools(chain_context.session_id)
                logger.info(f"Enhanced logging: Retrieved {len(available_tools_list)} tools for {self.iteration_strategy.value}")
                
                # Convert legacy tools to MCPTool objects
                mcp_tools = []
                for tool in available_tools_list:
                    mcp_tools.append(MCPTool(
                        server=tool.get('server', 'unknown'),
                        name=tool.get('name', 'tool'),
                        description=tool.get('description', 'No description'),
                        parameters=tool.get('parameters', [])
                    ))
                available_tools = AvailableTools(tools=mcp_tools)
            else:
                logger.info(f"Enhanced logging: Strategy {self.iteration_strategy.value} skips MCP tool discovery - Final analysis stage")
                available_tools = AvailableTools()
            
            # Create new StageContext
            stage_context = StageContext(
                chain_context=chain_context,
                available_tools=available_tools,
                agent=self
            )
            
            # Delegate to appropriate iteration controller
            analysis_result = await self._iteration_controller.execute_analysis_loop(stage_context)
            
            # Create strategy-specific execution result summary
            result_summary = self._iteration_controller.create_result_summary(
                analysis_result=analysis_result,
                context=stage_context
            )
            
            # Extract clean final analysis for API consumption
            final_analysis = self._iteration_controller.extract_final_analysis(
                analysis_result=analysis_result,
                context=stage_context
            )
            
            return AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name=self.__class__.__name__,
                timestamp_us=now_us(),
                result_summary=result_summary,
                final_analysis=final_analysis
            )
            
        except AgentError as e:
            # Handle structured agent errors with recovery information
            logger.error(f"Agent processing failed with structured error: {e.to_dict()}", exc_info=True)
            
            return AgentExecutionResult(
                status=StageStatus.FAILED,
                agent_name=self.__class__.__name__,
                timestamp_us=now_us(),
                result_summary=f"Agent execution failed: {str(e)}",
                error_message=str(e)
            )
        except Exception as e:
            # Handle unexpected errors
            error_msg = f"Agent processing failed with unexpected error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            return AgentExecutionResult(
                status=StageStatus.FAILED,
                agent_name=self.__class__.__name__,
                timestamp_us=now_us(),
                result_summary=f"Agent execution failed with unexpected error: {str(e)}",
                error_message=error_msg
            )


    
    def merge_mcp_data(self, existing_data: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge new MCP data with existing data.
        
        Handles both list and non-list data formats gracefully.
        """
        merged_data = existing_data.copy()
        
        for server_name, server_data in new_data.items():
            if server_name in merged_data:
                if isinstance(merged_data[server_name], list) and isinstance(server_data, list):
                    merged_data[server_name].extend(server_data)
                else:
                    # Convert to list format if needed
                    if not isinstance(merged_data[server_name], list):
                        merged_data[server_name] = [merged_data[server_name]]
                    if isinstance(server_data, list):
                        merged_data[server_name].extend(server_data)
                    else:
                        merged_data[server_name].append(server_data)
            else:
                merged_data[server_name] = server_data
        
        return merged_data

    def _compose_instructions(self) -> str:
        """
        Compose final instructions from three tiers.
        
        Combines:
        1. General SRE instructions (from _get_general_instructions)
        2. MCP server-specific instructions (from registry)
        3. Custom agent instructions (from custom_instructions)
        
        Returns:
            Complete instruction set for the LLM
        """
        instructions = []
        
        # Tier 1: General instructions
        instructions.append(self._get_general_instructions())
        
        # Tier 2: MCP server instructions
        mcp_server_ids = self.mcp_servers()
        server_configs = self.mcp_registry.get_server_configs(mcp_server_ids)
        
        for server_config in server_configs:
            if hasattr(server_config, 'instructions') and server_config.instructions:
                instructions.append(f"## {server_config.server_type.title()} Server Instructions")
                instructions.append(server_config.instructions)
        
        # Tier 3: Custom instructions
        custom_instructions = self.custom_instructions()
        if custom_instructions:
            instructions.append("## Agent-Specific Instructions")
            instructions.append(custom_instructions)
        
        composed = "\n\n".join(instructions)
        logger.debug(f"Composed instructions for {self.__class__.__name__} with {len(instructions)} sections")
        
        return composed
    
    def _get_general_instructions(self) -> str:
        """
        Provide general SRE instructions common to all agents.
        
        Returns:
            General instruction text
        """
        return self._prompt_builder.get_general_instructions()
    
    def set_current_stage_execution_id(self, stage_execution_id: Optional[str]):
        """Set the current stage execution ID for chain processing context."""
        self._current_stage_execution_id = stage_execution_id
    
    def get_current_stage_execution_id(self) -> Optional[str]:
        """Get the current stage execution ID."""
        return self._current_stage_execution_id
    
    async def _configure_mcp_client(self):
        """Configure MCP client with agent-specific server subset."""
        mcp_server_ids = self.mcp_servers()
        
        # Get configurations for this agent's servers
        server_configs = self.mcp_registry.get_server_configs(mcp_server_ids)
        
        # Validate that all required servers are available
        available_server_ids = [config.server_id for config in server_configs]
        missing_servers = set(mcp_server_ids) - set(available_server_ids)
        if missing_servers:
            missing_list = list(missing_servers)
            config_error = ConfigurationError(
                message=f"Required MCP servers not configured: {missing_list}",
                missing_config="mcp_servers",
                context={
                    "required_servers": mcp_server_ids,
                    "available_servers": available_server_ids,
                    "missing_servers": missing_list,
                    "agent_class": self.__class__.__name__
                }
            )
            logger.error(f"Missing MCP server configurations: {config_error.to_dict()}")
            raise config_error
        
        # Configure agent to use only the assigned servers
        self._configured_servers = mcp_server_ids
        logger.info(f"Configured agent {self.__class__.__name__} with MCP servers: {mcp_server_ids}")
    
    async def _get_available_tools(self, session_id: str) -> List[Dict[str, Any]]:
        """Get available tools from assigned MCP servers."""
        try:
            all_tools = []
            
            if self._configured_servers is None:
                # This should never happen now - configuration is required
                error_msg = f"Agent {self.__class__.__name__} has not been properly configured with MCP servers"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Use only configured servers for this agent
            for server_name in self._configured_servers:
                server_tools = await self.mcp_client.list_tools(session_id=session_id, server_name=server_name, stage_execution_id=self._current_stage_execution_id)
                if server_name in server_tools:
                    for tool in server_tools[server_name]:
                        tool_with_server = tool.copy()
                        tool_with_server["server"] = server_name
                        all_tools.append(tool_with_server)
            
            logger.info(f"Agent {self.__class__.__name__} retrieved {len(all_tools)} tools from servers: {self._configured_servers}")
            return all_tools
            
        except Exception as e:
            logger.error(f"Failed to retrieve tools for agent {self.__class__.__name__}: {str(e)}")
            return []

    async def execute_mcp_tools(self, tools_to_call: List[Dict], session_id: str) -> Dict[str, List[Dict]]:
        """
        Execute a list of MCP tool calls and return organized results.
        
        This method provides the public interface for executing MCP tools,
        handling proper validation, error recovery, and result organization.
        
        Args:
            tools_to_call: List of tool call dictionaries with server, tool, parameters
            session_id: Session ID for tracking and logging
            
        Returns:
            Dictionary organized by server containing tool execution results
        """
        results = {}
        
        for tool_call in tools_to_call:
            try:
                server_name = tool_call.get("server")
                tool_name = tool_call.get("tool")
                tool_params = tool_call.get("parameters", {})
                
                # Verify this server is allowed for this agent
                if self._configured_servers and server_name not in self._configured_servers:
                    raise ValueError(f"Tool '{tool_name}' from server '{server_name}' not allowed for agent {self.__class__.__name__}")
                
                result = await self.mcp_client.call_tool(server_name, tool_name, tool_params, session_id, self._current_stage_execution_id)
                
                # Organize results by server
                if server_name not in results:
                    results[server_name] = []
                
                results[server_name].append({
                    "tool": tool_name,
                    "parameters": tool_params,
                    "result": result,
                    "timestamp": datetime.now(UTC).isoformat()
                })
                
            except Exception as e:
                # Create structured error with recovery strategy
                tool_exec_error = ToolExecutionError(
                    message=f"Tool execution failed: {str(e)}",
                    tool_name=tool_name,
                    server_name=server_name,
                    context={
                        "parameters": tool_params,
                        "agent_class": self.__class__.__name__
                    }
                )
                logger.error(f"Tool execution failed: {tool_exec_error.to_dict()}")
                
                # Use recovery handler to create error result
                if server_name not in results:
                    results[server_name] = []
                
                error_result = ErrorRecoveryHandler.handle_tool_execution_error(tool_exec_error)
                error_result.update({
                    "parameters": tool_params,
                    "timestamp": datetime.now(UTC).isoformat()
                })
                results[server_name].append(error_result)
        
        return results
 