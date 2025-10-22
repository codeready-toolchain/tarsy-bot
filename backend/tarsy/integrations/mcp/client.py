"""
MCP client using the official MCP SDK for integration with MCP servers.
"""

import asyncio
import json
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from mcp import ClientSession
from mcp.types import Tool

from tarsy.config.settings import Settings
from tarsy.hooks.hook_context import mcp_interaction_context, mcp_list_context
from tarsy.models.agent_config import MCPServerConfigModel
from tarsy.integrations.mcp.transport.factory import MCPTransportFactory, MCPTransport
from tarsy.models.mcp_transport_config import TRANSPORT_STDIO
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.services.data_masking_service import DataMaskingService
from tarsy.utils.logger import get_module_logger
from tarsy.utils.token_counter import TokenCounter
from tarsy.utils.error_details import extract_error_details

if TYPE_CHECKING:
    from tarsy.integrations.mcp.summarizer import MCPResultSummarizer
    from tarsy.models.unified_interactions import LLMConversation

# Setup logger for this module
logger = get_module_logger(__name__)

# Setup separate logger for MCP communications
mcp_comm_logger = get_module_logger("mcp.communications")

# MCP operation timeout constant (in seconds)
MCP_OPERATION_TIMEOUT_SECONDS = 60  # Timeout for MCP list_tools and call_tool operations


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
        self.transports: Dict[str, MCPTransport] = {}  # Transport instances
        self.exit_stack = AsyncExitStack()
        self._initialized = False
        self.failed_servers: Dict[str, str] = {}  # server_id -> error_message
    
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
                logger.debug("  Transport type: %s", server_config.transport.type)
                logger.debug("  Command: %s", getattr(server_config.transport, 'command', 'N/A'))
                logger.debug("  Args: %s", getattr(server_config.transport, 'args', []))
                # Log env keys only to avoid exposing sensitive values  
                env = getattr(server_config.transport, 'env', {})
                env_keys = sorted(env.keys()) if env else []
                logger.debug("  Env keys: %s", env_keys)

                # Create and initialize session using shared helper
                session = await self._create_session(server_id, server_config)
                self.sessions[server_id] = session
                logger.info(f"Successfully initialized MCP server: {server_id}")

            except Exception as e:
                error_details = extract_error_details(e)
                logger.error(f"Failed to initialize MCP server {server_id}: {error_details}", exc_info=True)
                # Track failed server for warning generation
                self.failed_servers[server_id] = error_details
                # Ensure we don't leave partial state in sessions dict
                if server_id in self.sessions:
                    del self.sessions[server_id]
        
        self._initialized = True
    
    def get_failed_servers(self) -> Dict[str, str]:
        """
        Get dictionary of failed MCP servers.
        
        Returns:
            Dict[server_id, error_message] for servers that failed to initialize
        """
        return self.failed_servers.copy()
    
    async def _create_session(self, server_id: str, server_config: MCPServerConfigModel) -> ClientSession:
        """Create and initialize a new MCP session for a server.
        
        Args:
            server_id: ID of the server
            server_config: Server configuration object
            
        Returns:
            Initialized ClientSession
            
        Raises:
            Exception: If session creation fails
        """
        try:
            # Get already-parsed transport configuration
            transport_config = server_config.transport
            
            # Create transport instance
            transport = MCPTransportFactory.create_transport(
                server_id, 
                transport_config, 
                self.exit_stack if transport_config.type == TRANSPORT_STDIO else None
            )
            
            # Store transport for lifecycle management
            self.transports[server_id] = transport
            
            # Create session via transport
            session = await transport.create_session()
            
            logger.info(f"Created {transport_config.type} session for server: {server_id}")
            return session
            
        except Exception as e:
            error_details = extract_error_details(e)
            logger.error(f"Failed to create session for {server_id}: {error_details}", exc_info=True)
            raise
    
    async def list_tools(
        self,
        session_id: str,
        server_name: Optional[str] = None,
        stage_execution_id: Optional[str] = None,
    ) -> Dict[str, List[Tool]]:
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
                    max_retries = 2
                    timeout_seconds = MCP_OPERATION_TIMEOUT_SECONDS
                    for attempt in range(max_retries):
                        try:
                            session = self.sessions[server_name]
                            # Wrap list_tools call with timeout
                            tools_result = await asyncio.wait_for(
                                session.list_tools(),
                                timeout=timeout_seconds
                            )
                            # Keep the official Tool objects with full schema information
                            all_tools[server_name] = tools_result.tools
                            
                            # Log the successful response
                            self._log_mcp_list_tools_response(server_name, tools_result.tools, request_id)
                            break  # Success, exit retry loop
                        
                        except asyncio.TimeoutError:
                            error_msg = f"List tools timed out after {timeout_seconds}s (attempt {attempt + 1}/{max_retries})"
                            logger.error(f"{error_msg} for {server_name}")
                            
                            if attempt < max_retries - 1:
                                logger.warning("Retrying list_tools after timeout...")
                                try:
                                    await self._recover_session(server_name)
                                    logger.info(f"Successfully recovered session for server: {server_name}")
                                    continue
                                except Exception as recovery_error:
                                    logger.error(f"Failed to recover session for {server_name}: {extract_error_details(recovery_error)}")
                            
                            # Final attempt or recovery failed
                            logger.error(f"List tools timed out for {server_name} after {max_retries} attempts")
                            self._log_mcp_list_tools_error(server_name, error_msg, request_id)
                            all_tools[server_name] = []
                            break
                            
                        except Exception as e:
                            error_details = extract_error_details(e)
                            
                            if attempt < max_retries - 1:
                                logger.warning(f"List tools failed on attempt {attempt + 1}/{max_retries} for {server_name}: {error_details}")
                                logger.info(f"Attempting to recover session for server: {server_name}")
                                
                                try:
                                    await self._recover_session(server_name)
                                    logger.info(f"Successfully recovered session for server: {server_name}")
                                    continue  # Retry with the new session
                                except Exception as recovery_error:
                                    logger.error(f"Failed to recover session for {server_name}: {extract_error_details(recovery_error)}")
                                    # Continue to final attempt logic below
                            
                            # Final attempt or recovery failed
                            logger.error(f"Error listing tools from {server_name}: {error_details}")
                            self._log_mcp_list_tools_error(server_name, error_details, request_id)
                            all_tools[server_name] = []
                            break  # Exit retry loop
            else:
                # List tools from all servers
                for name in list(self.sessions.keys()):  # Use list() to avoid dict changed during iteration
                    max_retries = 2
                    timeout_seconds = MCP_OPERATION_TIMEOUT_SECONDS
                    for attempt in range(max_retries):
                        try:
                            session = self.sessions.get(name)
                            if not session:
                                all_tools[name] = []
                                break
                            
                            # Wrap list_tools call with timeout
                            tools_result = await asyncio.wait_for(
                                session.list_tools(),
                                timeout=timeout_seconds
                            )
                            # Keep the official Tool objects with full schema information
                            all_tools[name] = tools_result.tools
                            
                            # Log the successful response for this server
                            self._log_mcp_list_tools_response(name, tools_result.tools, request_id)
                            break  # Success, exit retry loop
                        
                        except asyncio.TimeoutError:
                            error_msg = f"List tools timed out after {timeout_seconds}s (attempt {attempt + 1}/{max_retries})"
                            logger.error(f"{error_msg} for {name}")
                            
                            if attempt < max_retries - 1:
                                logger.warning("Retrying list_tools after timeout...")
                                try:
                                    await self._recover_session(name)
                                    logger.info(f"Successfully recovered session for server: {name}")
                                    continue
                                except Exception as recovery_error:
                                    logger.error(f"Failed to recover session for {name}: {extract_error_details(recovery_error)}")
                            
                            # Final attempt or recovery failed
                            logger.error(f"List tools timed out for {name} after {max_retries} attempts")
                            self._log_mcp_list_tools_error(name, error_msg, request_id)
                            all_tools[name] = []
                            break
                            
                        except Exception as e:
                            error_details = extract_error_details(e)
                            
                            if attempt < max_retries - 1:
                                logger.warning(f"List tools failed on attempt {attempt + 1}/{max_retries} for {name}: {error_details}")
                                logger.info(f"Attempting to recover session for server: {name}")
                                
                                try:
                                    await self._recover_session(name)
                                    logger.info(f"Successfully recovered session for server: {name}")
                                    continue  # Retry with the new session
                                except Exception as recovery_error:
                                    logger.error(f"Failed to recover session for {name}: {extract_error_details(recovery_error)}")
                                    # Continue to final attempt logic below
                            
                            # Final attempt or recovery failed
                            logger.error(f"Error listing tools from {name}: {error_details}")
                            self._log_mcp_list_tools_error(name, error_details, request_id)
                            all_tools[name] = []
                            break  # Exit retry loop
            
            # Convert Tool objects to dictionaries for JSON serialization in hook context
            serializable_tools: Dict[str, List[Dict[str, Any]]] = {}
            for srv_name, tools in all_tools.items():
                if tools:
                    serializable_tools[srv_name] = [
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                            "inputSchema": tool.inputSchema or {}
                        }
                        for tool in tools
                    ]
                else:
                    serializable_tools[srv_name] = []
            
            # Update the interaction with result data
            ctx.interaction.available_tools = serializable_tools
            
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
        stage_execution_id: Optional[str] = None,
        mcp_event_id: Optional[str] = None
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
        size_threshold = getattr(summarization_config, 'size_threshold_tokens', 5000)
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
                session_id, stage_execution_id, max_summary_tokens, mcp_event_id
            )
            
            logger.info(f"Successfully summarized {server_name}.{tool_name} from {estimated_tokens} to ~{max_summary_tokens} tokens")
            return summarized
            
        except Exception as e:
            error_details = extract_error_details(e)
            logger.error(f"Failed to summarize MCP result {server_name}.{tool_name}: {error_details}")
            # Return error message as result for graceful degradation
            return {
                "result": f"Error: Failed to summarize large result ({estimated_tokens} tokens). Summarization error: {str(e)}"
            }

    async def call_tool(self, server_name: str, tool_name: str, parameters: Dict[str, Any], session_id: str, stage_execution_id: Optional[str] = None, investigation_conversation: Optional['LLMConversation'] = None) -> Dict[str, Any]:
        """Call a specific tool on an MCP server with optional investigation context for summarization.
        
        Timeline: This method ensures correct interaction ordering in history:
        1. MCP interaction stored with actual tool result
        2. Summarization LLM interaction (if triggered)
        3. Summary returned to agent for conversation
        
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
        
        # Variable to store the actual result for later summarization (if needed)
        actual_result: Optional[Dict[str, Any]] = None
        mcp_event_id: Optional[str] = None  # Captured after MCP interaction is stored
        
        # Use typed hook context for clean data flow
        async with mcp_interaction_context(session_id, server_name, tool_name, parameters, stage_execution_id) as ctx:
            
            # Get request ID for logging
            request_id = ctx.get_request_id()
            
            # Emit started event before execution (for real-time UI feedback)
            from tarsy.services.events.event_helpers import publish_mcp_tool_call_started
            await publish_mcp_tool_call_started(
                session_id=session_id,
                communication_id=ctx.interaction.communication_id,
                server_name=server_name,
                tool_name=tool_name,
                tool_arguments=parameters,
                stage_id=stage_execution_id
            )
            
            # Log the outgoing tool call
            self._log_mcp_request(server_name, tool_name, parameters, request_id)
            
            # Try the tool call with automatic session recovery on failure
            max_retries = 2
            timeout_seconds = MCP_OPERATION_TIMEOUT_SECONDS
            
            for attempt in range(max_retries):
                session = self.sessions.get(server_name)
                if not session:
                    raise Exception(f"MCP server not found: {server_name}")
                
                try:
                    # Wrap MCP call with timeout to prevent indefinite hanging
                    result = await asyncio.wait_for(
                        session.call_tool(tool_name, parameters),
                        timeout=timeout_seconds
                    )
                    
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
                            # Never return unmasked data - redact on masking failure
                            response_dict = {"result": "[REDACTED: masking failure]"}
                            raise Exception(f"Data masking failed for server '{server_name}': {str(e)}") from e
                    
                    # Log the successful response with ACTUAL result (before optional summarization)
                    self._log_mcp_response(server_name, tool_name, response_dict, request_id)
                    
                    # Store ACTUAL result in interaction (this is what goes to DB)
                    ctx.interaction.tool_result = response_dict
                    
                    # Capture MCP event ID before completion (for linking summarization)
                    mcp_event_id = ctx.interaction.communication_id
                    
                    # Complete the typed context with success
                    # This triggers MCP hooks and stores the interaction to DB with actual result
                    await ctx.complete_success({})
                    
                    # Store actual result and event ID for potential summarization outside the context
                    actual_result = response_dict
                    break  # Success, exit retry loop
                
                except asyncio.TimeoutError:
                    # Handle timeout specifically
                    error_msg = f"MCP tool call timed out after {timeout_seconds}s (attempt {attempt + 1}/{max_retries})"
                    logger.error(f"{error_msg} for {server_name}.{tool_name}")
                    
                    if attempt < max_retries - 1:
                        logger.warning("Retrying after timeout...")
                        try:
                            # Attempt to recover the session after timeout
                            await self._recover_session(server_name)
                            logger.info(f"Successfully recovered session for server: {server_name}")
                            continue  # Retry with the new session
                        except Exception as recovery_error:
                            logger.error(f"Failed to recover session for {server_name}: {extract_error_details(recovery_error)}")
                            # Continue to final attempt logic below
                    
                    # Final attempt or recovery failed - raise timeout error
                    final_error_msg = f"MCP tool call {tool_name} on {server_name} timed out after {max_retries} attempts ({timeout_seconds}s each)"
                    self._log_mcp_error(server_name, tool_name, final_error_msg, request_id)
                    raise TimeoutError(final_error_msg) from None
                        
                except Exception as e:
                    error_details = extract_error_details(e)
                    
                    if attempt < max_retries - 1:
                        # Always attempt recovery on first failure - simpler and more robust
                        logger.warning(f"Tool call failed on attempt {attempt + 1}/{max_retries} for {server_name}.{tool_name}: {error_details}")
                        logger.info(f"Attempting to recover session for server: {server_name}")
                        
                        try:
                            # Attempt to recover the session
                            await self._recover_session(server_name)
                            logger.info(f"Successfully recovered session for server: {server_name}")
                            continue  # Retry with the new session
                        except Exception as recovery_error:
                            logger.error(f"Failed to recover session for {server_name}: {extract_error_details(recovery_error)}")
                            # Continue to final attempt logic below
                    
                    # Final attempt or recovery failed - raise the original error
                    error_msg = f"Failed to call tool {tool_name} on {server_name} after {max_retries} attempts: {error_details}"
                    self._log_mcp_error(server_name, tool_name, error_details, request_id)
                    raise Exception(error_msg) from e
        
        # MCP interaction is now stored in DB with actual result
        # Now perform summarization if needed (creates separate LLM interaction with later timestamp)
        if actual_result and investigation_conversation:
            summarized_result = await self._maybe_summarize_result(
                server_name, tool_name, actual_result, investigation_conversation, 
                session_id, stage_execution_id, mcp_event_id
            )
            # Return summary for agent conversation
            return summarized_result
        
        # Return actual result if no summarization needed
        return actual_result
    
    async def _recover_session(self, server_name: str) -> None:
        """Recover a failed MCP session by recreating it.

        Args:
            server_name: Name of the server whose session needs recovery

        Raises:
            Exception: If session recovery fails
        """
        logger.info(f"Recovering session for MCP server: {server_name}")

        # Remove from sessions dict - the exit stack will handle cleanup
        if server_name in self.sessions:
            del self.sessions[server_name]

        # Get server configuration
        server_config = self.mcp_registry.get_server_config_safe(server_name)
        if not server_config:
            raise Exception(f"Server configuration not found for: {server_name}")

        # Recreate the session using shared helper
        try:
            session = await self._create_session(server_name, server_config)
            self.sessions[server_name] = session
            logger.info(f"Successfully recovered MCP server session: {server_name}")

        except Exception as e:
            logger.error(f"Failed to recover session for {server_name}: {extract_error_details(e)}")
            raise Exception(f"Session recovery failed for {server_name}: {str(e)}") from e
    
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
    
    def _log_mcp_list_tools_response(self, server_name: str, tools: List[Tool], request_id: str):
        """Log the MCP list tools response."""
        mcp_comm_logger.info(f"=== MCP LIST TOOLS RESPONSE [{server_name}] [ID: {request_id}] ===")
        mcp_comm_logger.info(f"Request ID: {request_id}")
        mcp_comm_logger.info(f"Server: {server_name}")
        mcp_comm_logger.info(f"Tools count: {len(tools)}")
        mcp_comm_logger.info("--- TOOLS ---")
        for i, tool in enumerate(tools):
            mcp_comm_logger.info(f"Tool {i+1}: {tool.name}")
            mcp_comm_logger.info(f"  Description: {tool.description or 'No description'}")
            mcp_comm_logger.info(f"  Schema: {json.dumps(tool.inputSchema or {}, indent=2, default=str)}")
        mcp_comm_logger.info(f"=== END LIST TOOLS RESPONSE [ID: {request_id}] ===")
    
    def _log_mcp_list_tools_error(self, server_name: str, error_message: str, request_id: str):
        """Log MCP list tools errors."""
        mcp_comm_logger.error(f"=== MCP LIST TOOLS ERROR [{server_name}] [ID: {request_id}] ===")
        mcp_comm_logger.error(f"Request ID: {request_id}")
        mcp_comm_logger.error(f"Server: {server_name}")
        mcp_comm_logger.error(f"Error: {error_message}")
        mcp_comm_logger.error(f"=== END LIST TOOLS ERROR [ID: {request_id}] ===")

    async def close(self):
        """Close all MCP client connections and transports."""
        # Close all transports
        for server_id, transport in self.transports.items():
            try:
                await transport.close()
            except Exception as e:
                logger.error(f"Error closing transport for {server_id}: {extract_error_details(e)}")
        
        # Close exit stack (for stdio transports)
        try:
            await self.exit_stack.aclose()
        except Exception as e:
            logger.error(f"Error during MCP client cleanup: {extract_error_details(e)}")
        finally:
            # Always clean up state even if cleanup fails
            self.sessions.clear()
            self.transports.clear()
            self._initialized = False 