"""
Base agent abstract class for the multi-layer agent architecture.

This module provides the abstract base class that all specialized agents must inherit from.
It implements common processing logic and defines abstract methods for agent-specific behavior.
"""

import asyncio
import json
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Callable, Dict, List, Optional

from tarsy.config.settings import get_settings
from tarsy.integrations.llm.client import LLMClient
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.llm import LLMMessage
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.utils.logger import get_module_logger
from tarsy.utils.timestamp import now_us

from .prompt_builder import PromptContext, get_prompt_builder

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
    
    Agents also control their own prompt building to leverage domain-specific context.
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        mcp_client: MCPClient,
        mcp_registry: MCPServerRegistry,
        progress_callback: Optional[Callable] = None
    ):
        """
        Initialize the base agent with required dependencies.
        
        Args:
            llm_client: Client for LLM interactions
            mcp_client: Client for MCP server interactions
            mcp_registry: Registry of MCP server configurations (REQUIRED)
            progress_callback: Optional callback for progress updates
        """
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.mcp_registry = mcp_registry
        self.progress_callback = progress_callback
        self._iteration_count = 0
        self._max_iterations = get_settings().max_llm_mcp_iterations
        self._configured_servers: Optional[List[str]] = None
        self._prompt_builder = get_prompt_builder()
        
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

    def build_analysis_prompt(self, alert_data: Dict, runbook_content: str, mcp_data: Dict) -> str:
        """
        Build analysis prompt leveraging agent-specific context.
        
        Agents can override this method to customize prompt building based on their domain.
        The default implementation provides a comprehensive SRE analysis prompt.
        """
        context = self._create_prompt_context(
            alert_data=alert_data,
            runbook_content=runbook_content,
            mcp_data=mcp_data
        )
        return self._prompt_builder.build_analysis_prompt(context)

    def build_mcp_tool_selection_prompt(self, alert_data: Dict, runbook_content: str, available_tools: Dict) -> str:
        """
        Build MCP tool selection prompt with agent-specific context.
        
        Agents can override this method to customize tool selection logic.
        """
        context = self._create_prompt_context(
            alert_data=alert_data,
            runbook_content=runbook_content,
            mcp_data={},
            available_tools=available_tools
        )
        return self._prompt_builder.build_mcp_tool_selection_prompt(context)

    def build_iterative_mcp_tool_selection_prompt(self, alert_data: Dict, runbook_content: str, 
                                                available_tools: Dict, iteration_history: List[Dict], 
                                                current_iteration: int) -> str:
        """
        Build iterative MCP tool selection prompt with agent-specific context.
        
        Agents can override this method to customize iterative tool selection logic.
        """
        context = self._create_prompt_context(
            alert_data=alert_data,
            runbook_content=runbook_content,
            mcp_data={},
            available_tools=available_tools,
            iteration_history=iteration_history,
            current_iteration=current_iteration,
            max_iterations=self._max_iterations
        )
        return self._prompt_builder.build_iterative_mcp_tool_selection_prompt(context)

    def build_partial_analysis_prompt(self, alert_data: Dict, runbook_content: str, 
                                    iteration_history: List[Dict], current_iteration: int) -> str:
        """
        Build partial analysis prompt with agent-specific context.
        
        Agents can override this method to customize partial analysis logic.
        """
        context = self._create_prompt_context(
            alert_data=alert_data,
            runbook_content=runbook_content,
            mcp_data={},
            iteration_history=iteration_history,
            current_iteration=current_iteration
        )
        return self._prompt_builder.build_partial_analysis_prompt(context)

    def _create_prompt_context(self, 
                             alert_data: Dict, 
                             runbook_content: str, 
                             mcp_data: Dict,
                             available_tools: Optional[Dict] = None,
                             iteration_history: Optional[List[Dict]] = None,
                             current_iteration: Optional[int] = None,
                             max_iterations: Optional[int] = None) -> PromptContext:
        """Create a PromptContext object with all necessary data for prompt building."""
        return PromptContext(
            agent_name=self.__class__.__name__,
            alert_data=alert_data,
            runbook_content=runbook_content,
            mcp_data=mcp_data,
            mcp_servers=self.mcp_servers(),
            server_guidance=self._get_server_specific_tool_guidance(),
            agent_specific_guidance=self.custom_instructions(),
            available_tools=available_tools,
            iteration_history=iteration_history,
            current_iteration=current_iteration,
            max_iterations=max_iterations or self._max_iterations
        )

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

    async def analyze_alert(self, 
                          alert_data: Dict, 
                          runbook_content: str, 
                          mcp_data: Dict,
                          session_id: str,
                          **kwargs) -> str:
        """Analyze an alert using the agent's LLM capabilities."""
        logger.info(f"Starting alert analysis with {self.__class__.__name__} - Alert: {alert_data.get('alert_type', alert_data.get('alert', 'unknown'))}")
        
        # Build comprehensive prompt using agent-specific prompt building
        prompt = self.build_analysis_prompt(alert_data, runbook_content, mcp_data)
        
        # Create structured messages for LLM
        messages = [
            LLMMessage(
                role="system",
                content=self._compose_instructions()
            ),
            LLMMessage(
                role="user",
                content=prompt
            )
        ]
        
        try:
            result = await self.llm_client.generate_response(messages, session_id, **kwargs)
            logger.info(f"Alert analysis completed with {self.__class__.__name__}")
            return result
        except Exception as e:
            logger.error(f"Alert analysis failed with {self.__class__.__name__}: {str(e)}")
            raise Exception(f"Analysis error: {str(e)}")

    async def determine_mcp_tools(self,
                                alert_data: Dict,
                                runbook_content: str,
                                available_tools: Dict,
                                session_id: str,
                                **kwargs) -> List[Dict]:
        """Determine which MCP tools to call based on alert and runbook."""
        logger.info(f"Starting MCP tool selection with {self.__class__.__name__} - Alert: {alert_data.get('alert_type', alert_data.get('alert', 'unknown'))}")
        
        # Build prompt using agent-specific prompt building
        prompt = self.build_mcp_tool_selection_prompt(alert_data, runbook_content, available_tools)
        
        # Create messages
        messages = [
            LLMMessage(
                role="system",
                content=self._prompt_builder.get_mcp_tool_selection_system_message()
            ),
            LLMMessage(
                role="user",
                content=prompt
            )
        ]
        
        try:
            response = await self.llm_client.generate_response(messages, session_id, **kwargs)
            
            # Parse the JSON response
            tools_to_call = self._parse_json_response(response, expected_type=list)
            
            # Validate each tool call
            for tool_call in tools_to_call:
                if not isinstance(tool_call, dict):
                    raise ValueError("Each tool call must be a JSON object")
                
                required_fields = ["server", "tool", "parameters", "reason"]
                for field in required_fields:
                    if field not in tool_call:
                        raise ValueError(f"Missing required field: {field}")
            
            logger.info(f"MCP tool selection completed with {self.__class__.__name__} - Selected {len(tools_to_call)} tools")
            return tools_to_call
            
        except Exception as e:
            logger.error(f"MCP tool selection failed with {self.__class__.__name__}: {str(e)}")
            raise Exception(f"Tool selection error: {str(e)}")

    async def determine_next_mcp_tools(self,
                                     alert_data: Dict,
                                     runbook_content: str,
                                     available_tools: Dict,
                                     iteration_history: List[Dict],
                                     current_iteration: int,
                                     session_id: str,
                                     **kwargs) -> Dict:
        """Determine next MCP tools to call based on current context and previous iterations."""
        logger.info(f"Starting iterative MCP tool selection with {self.__class__.__name__} - Iteration {current_iteration}")
        
        # Build prompt using agent-specific prompt building
        prompt = self.build_iterative_mcp_tool_selection_prompt(
            alert_data, runbook_content, available_tools, iteration_history, current_iteration
        )
        
        # Create messages
        messages = [
            LLMMessage(
                role="system",
                content=self._prompt_builder.get_iterative_mcp_tool_selection_system_message()
            ),
            LLMMessage(
                role="user",
                content=prompt
            )
        ]
        
        try:
            response = await self.llm_client.generate_response(messages, session_id, **kwargs)
            
            # Parse the JSON response
            next_action = self._parse_json_response(response, expected_type=dict)
            
            # Validate the response format
            if "continue" not in next_action:
                raise ValueError("Missing required field: continue")
            
            if next_action.get("continue", False):
                if "tools" not in next_action or not isinstance(next_action["tools"], list):
                    raise ValueError("When continue=true, 'tools' field must be a list")
                
                # Validate each tool call
                for tool_call in next_action["tools"]:
                    if not isinstance(tool_call, dict):
                        raise ValueError("Each tool call must be a JSON object")
                    
                    required_fields = ["server", "tool", "parameters", "reason"]
                    for field in required_fields:
                        if field not in tool_call:
                            raise ValueError(f"Missing required field: {field}")
            
            logger.info(f"Iterative MCP tool selection completed with {self.__class__.__name__} - Continue: {next_action.get('continue', False)}")
            return next_action
            
        except Exception as e:
            logger.error(f"Iterative MCP tool selection failed with {self.__class__.__name__}: {str(e)}")
            raise Exception(f"Iterative tool selection error: {str(e)}")

    async def analyze_partial_results(self,
                                    alert_data: Dict,
                                    runbook_content: str,
                                    iteration_history: List[Dict],
                                    current_iteration: int,
                                    **kwargs) -> str:
        """Analyze partial results from current iteration to guide next steps."""
        logger.info(f"Starting partial analysis with {self.__class__.__name__} - Iteration {current_iteration}")
        
        # Build prompt using agent-specific prompt building
        prompt = self.build_partial_analysis_prompt(
            alert_data, runbook_content, iteration_history, current_iteration
        )
        
        # Create messages
        messages = [
            LLMMessage(
                role="system",
                content=self._prompt_builder.get_partial_analysis_system_message()
            ),
            LLMMessage(
                role="user",
                content=prompt
            )
        ]
        
        try:
            result = await self.llm_client.generate_response(messages, **kwargs)
            logger.info(f"Partial analysis completed with {self.__class__.__name__}")
            return result
        except Exception as e:
            logger.error(f"Partial analysis failed with {self.__class__.__name__}: {str(e)}")
            raise Exception(f"Partial analysis error: {str(e)}")

    def _parse_json_response(self, response: str, expected_type: type) -> any:
        """Parse JSON response from LLM, handling markdown code blocks."""
        response = response.strip()
        
        # Find JSON in the response (handle markdown code blocks)
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            response = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            response = response[start:end].strip()
        
        # Parse the JSON
        try:
            parsed = json.loads(response)
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse LLM response as JSON: {str(e)}")
        
        # Validate type
        if not isinstance(parsed, expected_type):
            raise ValueError(f"Response must be a JSON {expected_type.__name__}")
        
        return parsed
    
    async def process_alert(
        self,
        alert_data: Dict[str, Any],
        runbook_content: str,
        session_id: str,
        callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Process an alert using the LLM-first approach.
        
        Args:
            alert_data: Complete alert data as flexible dictionary
            runbook_content: The downloaded runbook content  
            session_id: Session ID for timeline logging
            callback: Optional callback for progress updates
            
        Returns:
            Dictionary containing the analysis result and metadata
        """
        # Basic validation - data validation should happen at API layer
        if not session_id:
            raise ValueError("session_id is required for alert processing")
                       
        try:
            # Use provided callback or fall back to constructor callback
            progress_callback = callback or self.progress_callback
            
            # Start processing
            await self._update_progress(
                progress_callback,
                status="processing",
                message=f"Starting analysis with {self.__class__.__name__}"
            )
            
            # Configure MCP client with agent-specific servers
            await self._configure_mcp_client()
            
            # Get available tools from assigned MCP servers
            available_tools = await self._get_available_tools()
            
            # Iterative analysis loop with flexible data
            analysis_result = await self._iterative_analysis(
                alert_data, 
                runbook_content, 
                available_tools,
                progress_callback,
                session_id=session_id
            )
            
            # Final result
            await self._update_progress(
                progress_callback,
                status=AlertSessionStatus.COMPLETED,
                message="Analysis completed successfully"
            )
            
            return {
                "status": "success",
                "agent": self.__class__.__name__,
                "analysis": analysis_result,
                "iterations": self._iteration_count,
                "timestamp_us": now_us()
            }
            
        except Exception as e:
            # Simple error handling: log and fail
            error_msg = f"Agent processing failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            await self._update_progress(
                progress_callback,
                status="error",
                message=error_msg
            )
            
            return {
                "status": "error",
                "agent": self.__class__.__name__,
                "error": error_msg,
                "timestamp_us": now_us()
            }

    async def _iterative_analysis(
        self,
        alert_data: Dict[str, Any],
        runbook_content: str,
        available_tools: List[Dict[str, Any]],
        progress_callback: Optional[Callable],
        session_id: str
    ) -> str:
        """
        Perform iterative analysis using flexible alert data (LLM-First Processing).
        
        Args:
            alert_data: Complete flexible alert data dictionary
            runbook_content: The runbook content
            available_tools: List of available MCP tools
            progress_callback: Optional progress callback
            session_id: Session ID for timeline logging
            
        Returns:
            Final analysis result
        """
        iteration_history = []
        self._iteration_count = 0
        
        # Initial tool selection with flexible data
        try:
            initial_tools = await self.determine_mcp_tools(
                alert_data, runbook_content, {"tools": available_tools}, session_id=session_id
            )
        except Exception as e:
            logger.info(f"Initial tool selection failed, providing error as tool result: {str(e)}")
            # Instead of falling back to empty tools, provide the error as an MCP tool result
            # This lets the LLM see what went wrong and work with it naturally
            mcp_data = {
                "tool_selection_error": {
                    "error": str(e),
                    "message": "MCP tool selection failed - the LLM response did not match the required format",
                    "required_format": {
                        "description": "Each tool call must be a JSON object with these required fields:",
                        "fields": ["server", "tool", "parameters", "reason"],
                        "format": "JSON array of objects, each containing the four required fields above"
                    }
                }
            }
            return await self.analyze_alert(alert_data, runbook_content, mcp_data, session_id=session_id)
        
        # Execute initial tools if any
        mcp_data = {}
        if initial_tools:
            mcp_data = await self._execute_mcp_tools(initial_tools, session_id=session_id)
            iteration_history.append({
                "tools_called": initial_tools,
                "mcp_data": mcp_data
            })
        
        while self._iteration_count < self._max_iterations:
            self._iteration_count += 1
            
            await self._update_progress(
                progress_callback,
                status="processing",
                message=f"Analysis iteration {self._iteration_count}/{self._max_iterations}"
            )
            
            # Determine if we need more tools
            try:
                next_action = await self.determine_next_mcp_tools(
                    alert_data, runbook_content, {"tools": available_tools},
                    iteration_history, self._iteration_count, session_id=session_id
                )
            except Exception as e:
                logger.error(f"Next tool determination failed in iteration {self._iteration_count}: {str(e)}")
                break
            
            # Check if we should continue
            if not next_action.get("continue", False):
                logger.info(f"Analysis complete after {self._iteration_count} iterations")
                break
            
            # Execute additional tools
            additional_tools = next_action.get("tools", [])
            if additional_tools:
                additional_mcp_data = await self._execute_mcp_tools(additional_tools, session_id=session_id)
                # Merge with existing data
                for server_name, server_data in additional_mcp_data.items():
                    if server_name in mcp_data:
                        if isinstance(mcp_data[server_name], list) and isinstance(server_data, list):
                            mcp_data[server_name].extend(server_data)
                        else:
                            # Convert to list format if needed
                            if not isinstance(mcp_data[server_name], list):
                                mcp_data[server_name] = [mcp_data[server_name]]
                            if isinstance(server_data, list):
                                mcp_data[server_name].extend(server_data)
                            else:
                                mcp_data[server_name].append(server_data)
                    else:
                        mcp_data[server_name] = server_data
                
                iteration_history.append({
                    "tools_called": additional_tools,
                    "mcp_data": additional_mcp_data
                })
        
        # Final analysis with all collected data
        try:
            return await self.analyze_alert(alert_data, runbook_content, mcp_data, session_id=session_id)
        except Exception as e:
            logger.error(f"Final analysis failed: {str(e)}")
            return f"Analysis incomplete due to error: {str(e)}"

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
    
    async def _configure_mcp_client(self):
        """Configure MCP client with agent-specific server subset."""
        mcp_server_ids = self.mcp_servers()
        
        # Get configurations for this agent's servers
        server_configs = self.mcp_registry.get_server_configs(mcp_server_ids)
        
        # Validate that all required servers are available
        available_server_ids = [config.server_id for config in server_configs]
        missing_servers = set(mcp_server_ids) - set(available_server_ids)
        if missing_servers:
            logger.error(f"Missing MCP server configurations for: {missing_servers}")
            raise ValueError(f"Required MCP servers not configured: {missing_servers}")
        
        # Configure agent to use only the assigned servers
        self._configured_servers = mcp_server_ids
        logger.info(f"Configured agent {self.__class__.__name__} with MCP servers: {mcp_server_ids}")
    
    async def _get_available_tools(self) -> List[Dict[str, Any]]:
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
                server_tools = await self.mcp_client.list_tools(server_name=server_name)
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

    async def _execute_mcp_tools(self, tools_to_call: List[Dict], session_id: str) -> Dict[str, List[Dict]]:
        """Execute a list of MCP tool calls and return organized results."""
        results = {}
        
        for tool_call in tools_to_call:
            try:
                server_name = tool_call.get("server")
                tool_name = tool_call.get("tool")
                tool_params = tool_call.get("parameters", {})
                
                # Verify this server is allowed for this agent
                if self._configured_servers and server_name not in self._configured_servers:
                    raise ValueError(f"Tool '{tool_name}' from server '{server_name}' not allowed for agent {self.__class__.__name__}")
                
                result = await self.mcp_client.call_tool(server_name, tool_name, tool_params, session_id)
                
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
                logger.error(f"Tool execution failed for {tool_name}: {str(e)}")
                if server_name not in results:
                    results[server_name] = []
                
                results[server_name].append({
                    "tool": tool_name,
                    "parameters": tool_params,
                    "error": str(e),
                    "timestamp": datetime.now(UTC).isoformat()
                })
        
        return results
    
    async def _update_progress(
        self,
        callback: Optional[Callable],
        status: str,
        message: str
    ):
        """Update progress through callback if available."""
        if callback:
            try:
                progress_data = {
                    "status": status,
                    "message": message,
                    "agent": self.__class__.__name__,
                    "iteration": self._iteration_count,
                    "timestamp": datetime.now(UTC).isoformat()
                }
                
                # Handle both sync and async callbacks
                if asyncio.iscoroutinefunction(callback):
                    await callback(progress_data)
                else:
                    callback(progress_data)
                    
            except Exception as e:
                logger.error(f"Progress callback failed: {str(e)}") 