"""
MCP client using the official MCP SDK for integration with MCP servers.
"""

import json
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tarsy.config.settings import Settings
from tarsy.hooks.typed_context import mcp_interaction_context, mcp_list_context
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.services.data_masking_service import DataMaskingService
from tarsy.utils.logger import get_module_logger
from tarsy.utils.token_counter import TokenCounter

if TYPE_CHECKING:
    from tarsy.integrations.mcp.summarizer import MCPResultSummarizer
    from tarsy.models.unified_interactions import LLMConversation

# Setup logger for this module
logger = get_module_logger(__name__)

# Setup separate logger for MCP communications
mcp_comm_logger = get_module_logger("mcp.communications")


class MCPClient:
    """MCP client using the official MCP SDK."""
    
    def __init__(self, settings: Settings, mcp_registry: Optional[MCPServerRegistry] = None, 
                 summarizer: Optional['MCPResultSummarizer'] = None):
        self.settings = settings
        self.mcp_registry = mcp_registry or MCPServerRegistry()
        self.data_masking_service = DataMaskingService(self.mcp_registry)
        self.summarizer = summarizer  # Optional agent-provided summarizer
        self.token_counter = TokenCounter()  # For size threshold detection
        self.sessions: Dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()
        self._initialized = False
    
    async def initialize(self):
        """Initialize MCP servers based on registry configuration."""
        if self._initialized:
            return
            
        # Get all server configurations from the registry
        all_server_ids = self.mcp_registry.get_all_server_ids()
        
        for server_id in all_server_ids:
            server_config = self.mcp_registry.get_server_config_safe(server_id)
            if not server_config or not server_config.enabled:
                continue
                
            try:
                logger.debug("Initializing MCP server '%s' with configuration:", server_id)
                logger.debug("  Server type: %s", server_config.server_type)
                logger.debug("  Enabled: %s", server_config.enabled)
                logger.debug("  Command: %s", server_config.connection_params.get('command'))
                logger.debug("  Args: %s", server_config.connection_params.get('args', []))
                # Log env keys only to avoid exposing sensitive values
                env_keys = sorted(server_config.connection_params.get('env', {}).keys())
                logger.debug("  Env keys: %s", env_keys)
                
                # Create server parameters for stdio connection
                server_params = StdioServerParameters(
                    command=server_config.connection_params.get("command"),
                    args=server_config.connection_params.get("args", []),
                    env=server_config.connection_params.get("env", None)
                )
                
                # Log server parameters without exposing sensitive env values
                logger.debug("Created StdioServerParameters for '%s':", server_id)
                logger.debug("  Command: %s", server_params.command)
                logger.debug("  Args: %s", server_params.args)
                env_keys = sorted(server_params.env.keys()) if server_params.env else []
                logger.debug("  Env keys: %s", env_keys)
                
                # Connect to the server
                read_stream, write_stream = await self.exit_stack.enter_async_context(
                    stdio_client(server_params)
                )
                
                # Create session
                session = await self.exit_stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                
                # Initialize the session
                await session.initialize()
                
                self.sessions[server_id] = session
                logger.info(f"Successfully initialized MCP server: {server_id}")
                
            except Exception as e:
                logger.error(f"Failed to initialize MCP server {server_id}: {str(e)}")
        
        self._initialized = True
    
    async def list_tools(self, session_id: str, server_name: Optional[str] = None, stage_execution_id: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """List available tools from MCP servers."""
        if not self._initialized:
            await self.initialize()
        
        if not session_id:
            raise ValueError("session_id is required for MCP tool listing")
        
        # Use typed hook context for clean data flow
        async with mcp_list_context(session_id, server_name, stage_execution_id) as ctx:
            
            # Get request ID for logging
            request_id = ctx.get_request_id()
            
            # Log the tools listing request
            self._log_mcp_list_tools_request(server_name, request_id)
            
            all_tools = {}
            
            if server_name:
                # List tools from specific server
                if server_name in self.sessions:
                    try:
                        session = self.sessions[server_name]
                        tools_result = await session.list_tools()
                        tools = []
                        for tool in tools_result.tools:
                            tool_dict = {
                                "name": tool.name,
                                "description": tool.description or "",
                                "inputSchema": tool.inputSchema
                            }
                            tools.append(tool_dict)
                        all_tools[server_name] = tools
                        
                        # Log the successful response
                        self._log_mcp_list_tools_response(server_name, tools, request_id)
                        
                    except Exception as e:
                        logger.error(f"Error listing tools from {server_name}: {str(e)}")
                        self._log_mcp_list_tools_error(server_name, str(e), request_id)
                        all_tools[server_name] = []
            else:
                # List tools from all servers
                for name, session in self.sessions.items():
                    try:
                        tools_result = await session.list_tools()
                        tools = []
                        for tool in tools_result.tools:
                            tool_dict = {
                                "name": tool.name,
                                "description": tool.description or "",
                                "inputSchema": tool.inputSchema
                            }
                            tools.append(tool_dict)
                        all_tools[name] = tools
                        
                        # Log the successful response for this server
                        self._log_mcp_list_tools_response(name, tools, request_id)
                        
                    except Exception as e:
                        logger.error(f"Error listing tools from {name}: {str(e)}")
                        self._log_mcp_list_tools_error(name, str(e), request_id)
                        all_tools[name] = []
            
            # Update the interaction with result data
            ctx.interaction.available_tools = all_tools
            
            # Complete the typed context with success
            await ctx.complete_success({})
            
            return all_tools
    
    async def _maybe_summarize_result(
        self, 
        server_name: str, 
        tool_name: str, 
        result: Dict[str, Any], 
        investigation_conversation: 'LLMConversation',
        session_id: str,
        stage_execution_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Apply summarization if result exceeds size threshold.
        
        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool that produced the result
            result: The original tool result dictionary
            investigation_conversation: The ongoing ReAct conversation for context
            session_id: Session ID for tracking
            stage_execution_id: Optional stage execution ID
            
        Returns:
            Either the original result or a summarized version if threshold exceeded
        """
        
        if not self.summarizer:
            return result
        
        # Get server-specific configuration
        server_config = self.mcp_registry.get_server_config_safe(server_name)
        if not server_config or not hasattr(server_config, 'summarization'):
            return result
        
        summarization_config = getattr(server_config, 'summarization', None)
        if not summarization_config or not getattr(summarization_config, 'enabled', True):
            return result
        
        # Check size threshold
        size_threshold = getattr(summarization_config, 'size_threshold_tokens', 2000)
        estimated_tokens = self.token_counter.estimate_observation_tokens(server_name, tool_name, result)
        
        if estimated_tokens <= size_threshold:
            logger.debug(f"Result size {estimated_tokens} tokens below threshold {size_threshold} for {server_name}.{tool_name}")
            return result
        
        try:
            # Get max summary tokens from server configuration
            max_summary_tokens = getattr(summarization_config, 'summary_max_token_limit', 1000)
            
            logger.info(f"Summarizing large MCP result: {server_name}.{tool_name} ({estimated_tokens} tokens)")
            summarized = await self.summarizer.summarize_result(
                server_name, tool_name, result, investigation_conversation, 
                session_id, stage_execution_id, max_summary_tokens
            )
            
            logger.info(f"Successfully summarized {server_name}.{tool_name} from {estimated_tokens} to ~{max_summary_tokens} tokens")
            return summarized
            
        except Exception as e:
            logger.error(f"Failed to summarize MCP result {server_name}.{tool_name}: {e}")
            # Return error message as result for graceful degradation
            return {
                "result": f"Error: Failed to summarize large result ({estimated_tokens} tokens). Summarization error: {str(e)}"
            }

    async def call_tool(self, server_name: str, tool_name: str, parameters: Dict[str, Any], session_id: str, stage_execution_id: Optional[str] = None, investigation_conversation: Optional['LLMConversation'] = None) -> Dict[str, Any]:
        """Call a specific tool on an MCP server with optional investigation context for summarization.
        
        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool to call
            parameters: Parameters to pass to the tool
            session_id: Required session ID for timeline logging and tracking
            stage_execution_id: Optional stage execution ID
            investigation_conversation: Optional ReAct conversation for context-aware summarization
        """
        if not self._initialized:
            await self.initialize()
        
        if server_name not in self.sessions:
            raise Exception(f"MCP server not found: {server_name}")
        
        # Use typed hook context for clean data flow
        async with mcp_interaction_context(session_id, server_name, tool_name, parameters, stage_execution_id) as ctx:
            
            # Get request ID for logging
            request_id = ctx.get_request_id()
            
            # Log the outgoing tool call
            self._log_mcp_request(server_name, tool_name, parameters, request_id)
            
            session = self.sessions[server_name]
            
            try:
                result = await session.call_tool(tool_name, parameters)
                
                # Convert result to dictionary
                if hasattr(result, 'content'):
                    # Handle different content types
                    content = result.content
                    if isinstance(content, list):
                        # Extract text content from the list
                        text_parts = []
                        for item in content:
                            if hasattr(item, 'text'):
                                text_parts.append(item.text)
                            elif hasattr(item, 'type') and item.type == 'text':
                                text_parts.append(str(item))
                        response_dict = {"result": "\n".join(text_parts)}
                    else:
                        response_dict = {"result": str(content)}
                else:
                    response_dict = {"result": str(result)}
                
                # Apply data masking if service is available
                if self.data_masking_service:
                    try:
                        logger.debug("Applying data masking for server: %s", server_name)
                        response_dict = self.data_masking_service.mask_response(response_dict, server_name)
                        logger.debug("Data masking completed for server: %s", server_name)
                    except Exception as e:
                        logger.error("Error during data masking for server '%s': %s", server_name, e)
                        # Continue with unmasked response rather than failing the entire call
                        logger.warning("Continuing with unmasked response for server: %s", server_name)
                
                # Apply summarization AFTER data masking (if investigation context available)
                if investigation_conversation:
                    response_dict = await self._maybe_summarize_result(
                        server_name, tool_name, response_dict, investigation_conversation, 
                        session_id, stage_execution_id
                    )
                
                # Log the successful response (after masking and optional summarization)
                self._log_mcp_response(server_name, tool_name, response_dict, request_id)
                
                # Update the interaction with result data
                ctx.interaction.tool_result = response_dict
                
                # Complete the typed context with success
                await ctx.complete_success({})
                
                return response_dict
                    
            except Exception as e:
                # Log the error (hooks will be triggered automatically by context manager)
                error_msg = f"Failed to call tool {tool_name} on {server_name}: {str(e)}"
                self._log_mcp_error(server_name, tool_name, str(e), request_id)
                raise Exception(error_msg)
    
    def _log_mcp_request(self, server_name: str, tool_name: str, parameters: Dict[str, Any], request_id: str):
        """Log the outgoing MCP tool call request."""
        mcp_comm_logger.info(f"=== MCP REQUEST [{server_name}] [ID: {request_id}] ===")
        mcp_comm_logger.info(f"Request ID: {request_id}")
        mcp_comm_logger.info(f"Server: {server_name}")
        mcp_comm_logger.info(f"Tool: {tool_name}")
        mcp_comm_logger.info(f"Parameters: {json.dumps(parameters, indent=2, default=str)}")
        mcp_comm_logger.info(f"=== END REQUEST [ID: {request_id}] ===")
    
    def _log_mcp_response(self, server_name: str, tool_name: str, response: Dict[str, Any], request_id: str):
        """Log the MCP tool call response."""
        response_content = response.get("result", str(response))
        mcp_comm_logger.info(f"=== MCP RESPONSE [{server_name}] [ID: {request_id}] ===")
        mcp_comm_logger.info(f"Request ID: {request_id}")
        mcp_comm_logger.info(f"Server: {server_name}")
        mcp_comm_logger.info(f"Tool: {tool_name}")
        mcp_comm_logger.info(f"Response length: {len(response_content)} characters")
        mcp_comm_logger.info("--- RESPONSE CONTENT ---")
        mcp_comm_logger.info(response_content)
        mcp_comm_logger.info(f"=== END RESPONSE [ID: {request_id}] ===")
    
    def _log_mcp_error(self, server_name: str, tool_name: str, error_message: str, request_id: str):
        """Log MCP tool call errors."""
        mcp_comm_logger.error(f"=== MCP ERROR [{server_name}] [ID: {request_id}] ===")
        mcp_comm_logger.error(f"Request ID: {request_id}")
        mcp_comm_logger.error(f"Server: {server_name}")
        mcp_comm_logger.error(f"Tool: {tool_name}")
        mcp_comm_logger.error(f"Error: {error_message}")
        mcp_comm_logger.error(f"=== END ERROR [ID: {request_id}] ===")
    
    def _log_mcp_list_tools_request(self, server_name: Optional[str], request_id: str):
        """Log the MCP list tools request."""
        target = server_name if server_name else "ALL_SERVERS"
        mcp_comm_logger.info(f"=== MCP LIST TOOLS REQUEST [{target}] [ID: {request_id}] ===")
        mcp_comm_logger.info(f"Request ID: {request_id}")
        mcp_comm_logger.info(f"Target: {target}")
        mcp_comm_logger.info(f"=== END LIST TOOLS REQUEST [ID: {request_id}] ===")
    
    def _log_mcp_list_tools_response(self, server_name: str, tools: List[Dict[str, Any]], request_id: str):
        """Log the MCP list tools response."""
        mcp_comm_logger.info(f"=== MCP LIST TOOLS RESPONSE [{server_name}] [ID: {request_id}] ===")
        mcp_comm_logger.info(f"Request ID: {request_id}")
        mcp_comm_logger.info(f"Server: {server_name}")
        mcp_comm_logger.info(f"Tools count: {len(tools)}")
        mcp_comm_logger.info("--- TOOLS ---")
        for i, tool in enumerate(tools):
            mcp_comm_logger.info(f"Tool {i+1}: {tool['name']}")
            mcp_comm_logger.info(f"  Description: {tool['description']}")
            mcp_comm_logger.info(f"  Schema: {json.dumps(tool['inputSchema'], indent=2, default=str)}")
        mcp_comm_logger.info(f"=== END LIST TOOLS RESPONSE [ID: {request_id}] ===")
    
    def _log_mcp_list_tools_error(self, server_name: str, error_message: str, request_id: str):
        """Log MCP list tools errors."""
        mcp_comm_logger.error(f"=== MCP LIST TOOLS ERROR [{server_name}] [ID: {request_id}] ===")
        mcp_comm_logger.error(f"Request ID: {request_id}")
        mcp_comm_logger.error(f"Server: {server_name}")
        mcp_comm_logger.error(f"Error: {error_message}")
        mcp_comm_logger.error(f"=== END LIST TOOLS ERROR [ID: {request_id}] ===")

    async def close(self):
        """Close all MCP client connections."""
        try:
            await self.exit_stack.aclose()
        finally:
            # Always clean up state even if exit stack fails
            self.sessions.clear()
            self._initialized = False 