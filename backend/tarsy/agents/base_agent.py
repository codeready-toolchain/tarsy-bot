"""
Base agent abstract class for the multi-layer agent architecture.

This module provides the abstract base class that all specialized agents must inherit from.
It implements common processing logic and defines abstract methods for agent-specific behavior.
"""

import asyncio
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Dict, List, Optional, assert_never

from tarsy.config.settings import get_settings
from tarsy.integrations.llm.manager import LLMManager
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.constants import StageStatus
from tarsy.models.mcp_selection_models import MCPSelectionConfig
from tarsy.models.processing_context import (
    AvailableTools,
    ChainContext,
    StageContext,
    ToolWithServer,
)

if TYPE_CHECKING:
    from tarsy.models.unified_interactions import LLMConversation
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.utils.logger import get_module_logger
from tarsy.utils.timestamp import now_us

from ..models.constants import IterationStrategy
from .exceptions import (
    AgentError,
    ConfigurationError,
    ErrorRecoveryHandler,
    SessionPaused,
    ToolExecutionError,
    ToolSelectionError,
)
from .iteration_controllers import (
    IterationController,
    ReactStageController,
    SimpleReActController,
)
from .prompts import get_prompt_builder

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
        llm_manager: LLMManager,
        mcp_client: MCPClient,
        mcp_registry: MCPServerRegistry,
        iteration_strategy: IterationStrategy = IterationStrategy.REACT
    ):
        """
        Initialize the base agent with required dependencies.
        
        Args:
            llm_manager: LLM manager for accessing LLM clients (both LangChain and native thinking)
            mcp_client: Client for MCP server interactions
            mcp_registry: Registry of MCP server configurations (REQUIRED)
            iteration_strategy: Which iteration strategy to use (configured per agent)
        """
        self.llm_manager = llm_manager
        self.mcp_client = mcp_client
        self.mcp_registry = mcp_registry
        self._max_iterations = get_settings().max_llm_mcp_iterations
        self._configured_servers: Optional[List[str]] = None
        self._prompt_builder = get_prompt_builder()
        
        # Stage execution tracking for chain processing
        self._current_stage_execution_id: Optional[str] = None
        
        # Chat tracking for interaction recording
        self._current_chat_id: Optional[str] = None
        
        # LLM provider override for this agent instance (per-stage or per-chain)
        # When None, uses the global default provider from settings
        self._llm_provider_name: Optional[str] = None
        
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
            return SimpleReActController(self.llm_manager, self._prompt_builder)
        elif strategy == IterationStrategy.REACT_STAGE:
            return ReactStageController(self.llm_manager, self._prompt_builder)
        elif strategy == IterationStrategy.REACT_FINAL_ANALYSIS:
            from .iteration_controllers.react_final_analysis_controller import (
                ReactFinalAnalysisController,
            )
            return ReactFinalAnalysisController(self.llm_manager, self._prompt_builder)
        elif strategy == IterationStrategy.NATIVE_THINKING:
            from .iteration_controllers.native_thinking_controller import (
                NativeThinkingController,
            )
            print(f"[DEBUG-CONTROLLER] Creating NativeThinkingController")
            return NativeThinkingController(self.llm_manager, self._prompt_builder)
        else:
            assert_never(strategy)
    
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

    @classmethod
    @abstractmethod
    def mcp_servers(cls) -> List[str]:
        """
        Return the list of MCP server IDs this agent requires.
        
        This method must be implemented by each specialized agent to specify
        which MCP servers it needs for its operations.
        
        This is a class method because the server list is typically static
        and doesn't depend on instance state. This allows safe querying
        of required servers without instantiating the agent.
        
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

    async def process_alert(self, context: ChainContext) -> AgentExecutionResult:
        """
        Process alert.
        
        Args:
            context: ChainContext containing all processing data
        
        Returns:
            Structured AgentExecutionResult with rich investigation summary
        """
        try:
            # Configure MCP client with agent-specific servers
            await self._configure_mcp_client()
            
            # Get available tools only if the iteration strategy needs them
            if self._iteration_controller.needs_mcp_tools():
                logger.info(f"Enhanced logging: Strategy {self.iteration_strategy.value} requires MCP tool discovery")
                available_tools = await self._get_available_tools(context.session_id, context.mcp)
                logger.info(f"Enhanced logging: Retrieved {len(available_tools.tools)} tools for {self.iteration_strategy.value}")
            else:
                logger.info(f"Enhanced logging: Strategy {self.iteration_strategy.value} skips MCP tool discovery - Final analysis stage")
                available_tools = AvailableTools()
            
            # Create new StageContext
            stage_context = StageContext(
                chain_context=context,
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
                complete_conversation_history=analysis_result,
                final_analysis=final_analysis,
                iteration_strategy=self._iteration_strategy.value,
                llm_provider=self._llm_provider_name
            )
            
        except AgentError as e:
            # Special handling for SessionPaused - let it propagate up
            if isinstance(e, SessionPaused):
                logger.info(f"Agent processing failed with structured error: {e.to_dict()}")
                raise  # Re-raise SessionPaused to be handled by alert_service
            
            # Handle other structured agent errors with recovery information
            logger.error(f"Agent processing failed with structured error: {e.to_dict()}", exc_info=True)
            
            return AgentExecutionResult(
                status=StageStatus.FAILED,
                agent_name=self.__class__.__name__,
                timestamp_us=now_us(),
                result_summary=f"Agent execution failed: {str(e)}",
                error_message=str(e),
                iteration_strategy=self._iteration_strategy.value,
                llm_provider=self._llm_provider_name
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
                error_message=error_msg,
                iteration_strategy=self._iteration_strategy.value,
                llm_provider=self._llm_provider_name
            )

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
    
    def set_current_chat_id(self, chat_id: Optional[str]):
        """Set the current chat ID for interaction recording."""
        self._current_chat_id = chat_id
    
    def get_current_chat_id(self) -> Optional[str]:
        """Get the current chat ID."""
        return self._current_chat_id
    
    def set_llm_provider(self, provider_name: Optional[str]):
        """
        Set the LLM provider override for this agent instance.
        
        When set, this provider will be used for all LLM calls instead of the global default.
        Used by AgentFactory to configure per-stage or per-chain providers.
        
        Args:
            provider_name: Name of the LLM provider to use, or None to use global default
        """
        self._llm_provider_name = provider_name
        # Update the iteration controller with the provider
        self._iteration_controller.set_llm_provider(provider_name)
        if provider_name:
            logger.info(f"Agent {self.__class__.__name__} configured with LLM provider: {provider_name}")
    
    def get_llm_provider(self) -> Optional[str]:
        """
        Get the LLM provider override for this agent instance.
        
        Returns:
            Provider name if set, or None if using global default
        """
        return self._llm_provider_name
    
    async def _configure_mcp_client(self):
        """Configure MCP client with agent-specific server subset and summarizer."""
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
        
        # Create and inject summarizer if LLM manager is available
        if hasattr(self, 'llm_manager') and self.llm_manager:
            from tarsy.integrations.mcp.summarizer import MCPResultSummarizer
            summarizer = MCPResultSummarizer(self.llm_manager, self._prompt_builder)
            # Update MCP client with summarizer
            self.mcp_client.summarizer = summarizer
        
        # Configure agent to use only the assigned servers
        self._configured_servers = mcp_server_ids
        logger.info(f"Configured agent {self.__class__.__name__} with MCP servers: {mcp_server_ids}")
    
    async def _get_available_tools(self, session_id: str, mcp_selection: Optional['MCPSelectionConfig'] = None) -> AvailableTools:
        """
        Get available tools from MCP servers with optional user selection override.
        
        Supports three execution paths:
        1. No selection: Use agent's default configured servers (current behavior)
        2. Server selection: Use user-selected servers, fetch all tools from them
        3. Tool selection: Use user-selected servers, filter to only specified tools
        
        Args:
            session_id: Session ID for tracking
            mcp_selection: Optional MCP selection config from user (overrides defaults)
            
        Returns:
            AvailableTools with tools from appropriate servers
            
        Raises:
            MCPServerSelectionError: When selected servers don't exist
            MCPToolSelectionError: When selected tools don't exist on specified server
            ToolSelectionError: For other tool retrieval failures
        """
        from tarsy.agents.exceptions import (
            MCPServerSelectionError,
            MCPToolSelectionError,
        )
        
        try:
            tools_with_server = []
            
            # Determine which servers to use
            if mcp_selection is not None:
                # User provided MCP selection - use their servers instead of defaults
                logger.info(f"Agent {self.__class__.__name__} using user-provided MCP selection with {len(mcp_selection.servers)} servers")

                # Validate all selected servers exist in registry
                requested_server_names = [s.name for s in mcp_selection.servers]
                available_server_ids = self.mcp_registry.get_all_server_ids()
                missing_servers = set(requested_server_names) - set(available_server_ids)

                if missing_servers:
                    missing_list = sorted(missing_servers)
                    available_list = sorted(available_server_ids)
                    error_msg = f"Requested MCP servers not found: {missing_list}. Available servers: {available_list}"
                    logger.error(error_msg)
                    raise MCPServerSelectionError(
                        message=error_msg,
                        requested_servers=requested_server_names,
                        available_servers=available_list,
                        context={
                            "agent_class": self.__class__.__name__,
                            "session_id": session_id,
                            "missing_servers": missing_list
                        }
                    )
                
                # Process each selected server
                for server_selection in mcp_selection.servers:
                    server_name = server_selection.name
                    requested_tool_names = server_selection.tools
                    
                    # Fetch tools from the server
                    server_tools = await self.mcp_client.list_tools(
                        session_id=session_id, 
                        server_name=server_name, 
                        stage_execution_id=self._current_stage_execution_id
                    )
                    
                    if server_name not in server_tools:
                        logger.warning(f"Server {server_name} returned no tools")
                        continue
                    
                    available_tools = server_tools[server_name]
                    
                    # Filter to specific tools if requested
                    if requested_tool_names is not None and len(requested_tool_names) > 0:
                        # User specified specific tools - validate they exist
                        available_tool_names = {tool.name for tool in available_tools}
                        missing_tools = set(requested_tool_names) - available_tool_names
                        
                        if missing_tools:
                            missing_list = sorted(missing_tools)
                            available_list = sorted(available_tool_names)
                            error_msg = f"Requested tools not found on server '{server_name}': {missing_list}. Available tools: {available_list}"
                            logger.error(error_msg)
                            raise MCPToolSelectionError(
                                message=error_msg,
                                server_name=server_name,
                                requested_tools=requested_tool_names,
                                available_tools=available_list,
                                context={
                                    "agent_class": self.__class__.__name__,
                                    "session_id": session_id,
                                    "missing_tools": missing_list
                                }
                            )
                        
                        # Filter to only requested tools
                        for tool in available_tools:
                            if tool.name in requested_tool_names:
                                tools_with_server.append(ToolWithServer(
                                    server=server_name,
                                    tool=tool
                                ))
                        logger.info(f"Agent {self.__class__.__name__} using {len(requested_tool_names)} specific tools from server '{server_name}'")
                    else:
                        # No tool filtering - use all tools from server
                        for tool in available_tools:
                            tools_with_server.append(ToolWithServer(
                                server=server_name,
                                tool=tool
                            ))
                        logger.info(f"Agent {self.__class__.__name__} using all {len(available_tools)} tools from server '{server_name}'")
                
                logger.info(f"Agent {self.__class__.__name__} retrieved {len(tools_with_server)} tools total from user-selected servers")
            
            else:
                # No user selection - use agent's default configured servers
                if self._configured_servers is None:
                    error_msg = f"Agent {self.__class__.__name__} has not been properly configured with MCP servers"
                    logger.error(error_msg)
                    raise ValueError(error_msg)
                
                for server_name in self._configured_servers:
                    server_tools = await self.mcp_client.list_tools(
                        session_id=session_id, 
                        server_name=server_name, 
                        stage_execution_id=self._current_stage_execution_id
                    )
                    if server_name in server_tools:
                        for tool in server_tools[server_name]:
                            tools_with_server.append(ToolWithServer(
                                server=server_name,
                                tool=tool
                            ))
                
                logger.info(f"Agent {self.__class__.__name__} retrieved {len(tools_with_server)} tools from default servers: {self._configured_servers}")
            
            return AvailableTools(tools=tools_with_server)
            
        except (MCPServerSelectionError, MCPToolSelectionError):
            # Re-raise selection errors as-is (they have detailed context)
            raise
        except Exception as e:
            error_msg = f"Failed to retrieve tools for agent {self.__class__.__name__}: {str(e)}"
            logger.error(error_msg)
            raise ToolSelectionError(
                message=error_msg,
                context={
                    "agent_class": self.__class__.__name__,
                    "configured_servers": self._configured_servers,
                    "session_id": session_id,
                    "original_error": str(e)
                }
            ) from e

    async def execute_mcp_tools(
        self, 
        tools_to_call: List[Dict], 
        session_id: str, 
        investigation_conversation: Optional['LLMConversation'] = None,
        mcp_selection: Optional[MCPSelectionConfig] = None
    ) -> Dict[str, List[Dict]]:
        """
        Execute a list of MCP tool calls and return organized results.
        
        This method provides the public interface for executing MCP tools,
        handling proper validation, error recovery, and result organization.
        
        Args:
            tools_to_call: List of tool call dictionaries with server, tool, parameters
            session_id: Session ID for tracking and logging
            investigation_conversation: Optional investigation context for summarization
            mcp_selection: Optional MCP selection config to validate tool calls against
            
        Returns:
            Dictionary organized by server containing tool execution results
            
        Raises:
            ValueError: If tool call is not allowed by agent configuration or MCP selection
        """
        results = {}
        settings = get_settings()
        mcp_timeout = settings.mcp_tool_call_timeout
        
        for tool_call in tools_to_call:
            try:
                server_name = tool_call.get("server")
                tool_name = tool_call.get("tool")
                tool_params = tool_call.get("parameters", {})
                
                # Pass investigation conversation for context-aware summarization
                # MCP client now handles validation internally and records failures
                # Wrap with timeout to catch cases where MCP client's internal timeout fails
                # MCP client uses a single 60s timeout with no retries, so allow ~10s overhead
                try:
                    result = await asyncio.wait_for(
                        self.mcp_client.call_tool(
                            server_name, tool_name, tool_params, session_id, 
                            self._current_stage_execution_id, investigation_conversation,
                            mcp_selection, self._configured_servers
                        ),
                        timeout=mcp_timeout  # Wraps MCP call (no retries) with ~10s overhead
                    )
                except asyncio.TimeoutError:
                    raise TimeoutError(f"MCP tool call {tool_name} on {server_name} exceeded {mcp_timeout}s timeout") from None
                
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
 