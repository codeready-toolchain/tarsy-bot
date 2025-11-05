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
    from tarsy.models.mcp_selection_models import MCPSelectionConfig

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
    
    async def initialize(self) -> None:
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

                # Create and initialize session using shared helper with timeout
                # Use a reasonable timeout to prevent hanging during startup
                try:
                    session = await asyncio.wait_for(
                        self._create_session(server_id, server_config),
                        timeout=30.0  # 30 second timeout for initialization
                    )
                    self.sessions[server_id] = session
                    logger.info(f"Successfully initialized MCP server: {server_id}")
                except asyncio.TimeoutError:
                    raise Exception("Server initialization timed out after 30 seconds") from None

            except asyncio.CancelledError:
                # Handle cancellation during initialization (e.g., timeout or shutdown)
                error_msg = "Server initialization was cancelled (timeout or connection failure)"
                logger.warning(f"MCP server {server_id} initialization cancelled: {error_msg}")
                self.failed_servers[server_id] = error_msg
                # Ensure we don't leave partial state in sessions dict
                if server_id in self.sessions:
                    del self.sessions[server_id]
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
        transport = None
        try:
            # Get already-parsed transport configuration
            transport_config = server_config.transport
            
            # Create transport instance
            transport = MCPTransportFactory.create_transport(
                server_id, 
                transport_config, 
                self.exit_stack if transport_config.type == TRANSPORT_STDIO else None
            )
            
            # Create session via transport
            session = await transport.create_session()
            
            # Remove old transport reference before replacement
            # DO NOT attempt to close - MCP SDK cancel scopes cause CancelledError propagation
            # Abandoning the old transport is acceptable to avoid killing parent tasks
            if server_id in self.transports:
                old_transport = self.transports[server_id]
                if transport_config.type != TRANSPORT_STDIO:
                    # Just log that we're abandoning it - cleanup causes more harm than good
                    logger.debug(f"Abandoning old {transport_config.type} transport for {server_id} (cleanup causes cancel scope issues)")
            
            # Store transport for lifecycle management ONLY after successful session creation
            self.transports[server_id] = transport
            
            logger.info(f"Created {transport_config.type} session for server: {server_id}")
            return session
            
        except Exception as e:
            error_details = extract_error_details(e)
            logger.error(f"Failed to create session for {server_id}: {error_details}", exc_info=True)
            
            # Clean up transport resources on failure, but only for non-stdio transports
            # Stdio transports use a shared exit_stack that must not be closed prematurely
            if transport is not None:
                transport_config = server_config.transport
                if transport_config.type != TRANSPORT_STDIO:
                    # HTTP/SSE transports have their own exit_stack - clean it up to prevent leaks
                    # We can't use transport.close() because _connected=False, so close exit_stack directly
                    try:
                        if hasattr(transport, 'exit_stack'):
                            await transport.exit_stack.aclose()
                            logger.debug(f"Cleaned up {transport_config.type} transport resources for {server_id}")
                    except BaseException as cleanup_error:
                        # Catch ALL exceptions including CancelledError to prevent propagation
                        # Log but don't re-raise - original error is more important
                        logger.warning(f"Error cleaning up transport for {server_id}: {type(cleanup_error).__name__}")
            
            raise
    
    async def list_tools_simple(
        self,
        server_name: Optional[str] = None,
    ) -> Dict[str, List[Tool]]:
        """
        List available tools from MCP servers without database storage.
        
        This is a lightweight version for API discovery that doesn't use hook contexts
        or store interactions in the database. Use this for non-alert scenarios like
        the MCP servers discovery endpoint.
        
        Args:
            server_name: Optional server name to list tools from. If None, lists from all servers.
            
        Returns:
            Dictionary mapping server names to lists of Tool objects
        """
        if not self._initialized:
            await self.initialize()
        
        all_tools = {}
        
        if server_name:
            # List tools from specific server
            if server_name in self.sessions:
                try:
                    session = self.sessions[server_name]
                    tools_result = await asyncio.wait_for(
                        session.list_tools(),
                        timeout=MCP_OPERATION_TIMEOUT_SECONDS
                    )
                    all_tools[server_name] = tools_result.tools
                    logger.debug(f"Listed {len(tools_result.tools)} tools from {server_name}")
                except Exception as e:
                    logger.warning(f"Failed to list tools from {server_name}: {e}")
                    all_tools[server_name] = []
        else:
            # List tools from all servers
            for name in list(self.sessions.keys()):
                try:
                    session = self.sessions.get(name)
                    if not session:
                        all_tools[name] = []
                        continue
                    
                    tools_result = await asyncio.wait_for(
                        session.list_tools(),
                        timeout=MCP_OPERATION_TIMEOUT_SECONDS
                    )
                    all_tools[name] = tools_result.tools
                    logger.debug(f"Listed {len(tools_result.tools)} tools from {name}")
                except Exception as e:
                    logger.warning(f"Failed to list tools from {name}: {e}")
                    all_tools[name] = []
        
        return all_tools
    
    async def list_tools(
        self,
        session_id: str,
        server_name: Optional[str] = None,
        stage_execution_id: Optional[str] = None,
    ) -> Dict[str, List[Tool]]:
        """List available tools from MCP servers with database storage."""
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
                    timeout_seconds = MCP_OPERATION_TIMEOUT_SECONDS
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
                    
                    except asyncio.TimeoutError:
                        # No retry - let LLM handle it
                        error_msg = f"List tools timed out after {timeout_seconds}s"
                        logger.error(f"{error_msg} for {server_name}")
                        self._log_mcp_list_tools_error(server_name, error_msg, request_id)
                        # Return empty list so processing can continue
                        all_tools[server_name] = []
                        
                    except Exception as e:
                        # No retry - fail fast
                        error_details = extract_error_details(e)
                        logger.error(f"List tools failed for {server_name}: {error_details}")
                        self._log_mcp_list_tools_error(server_name, error_details, request_id)
                        # Return empty list so processing can continue
                        all_tools[server_name] = []
            else:
                # List tools from all servers
                for name in list(self.sessions.keys()):  # Use list() to avoid dict changed during iteration
                    timeout_seconds = MCP_OPERATION_TIMEOUT_SECONDS
                    try:
                        session = self.sessions.get(name)
                        if not session:
                            all_tools[name] = []
                            continue
                        
                        # Wrap list_tools call with timeout
                        tools_result = await asyncio.wait_for(
                            session.list_tools(),
                            timeout=timeout_seconds
                        )
                        # Keep the official Tool objects with full schema information
                        all_tools[name] = tools_result.tools
                        
                        # Log the successful response for this server
                        self._log_mcp_list_tools_response(name, tools_result.tools, request_id)
                    
                    except asyncio.TimeoutError:
                        # No retry - let LLM handle it
                        error_msg = f"List tools timed out after {timeout_seconds}s"
                        logger.error(f"{error_msg} for {name}")
                        self._log_mcp_list_tools_error(name, error_msg, request_id)
                        # Return empty list so processing can continue
                        all_tools[name] = []
                        
                    except Exception as e:
                        # No retry - fail fast
                        error_details = extract_error_details(e)
                        logger.error(f"List tools failed for {name}: {error_details}")
                        self._log_mcp_list_tools_error(name, error_details, request_id)
                        # Return empty list so processing can continue
                        all_tools[name] = []
            
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
    
    async def try_initialize_server(self, server_id: str) -> bool:
        """
        Attempt to initialize a server that failed during startup.
        
        Used by health monitor to recover misconfigured servers that
        become available after startup. Also replaces dead sessions if
        a session exists but is unresponsive.
        
        Args:
            server_id: ID of the server to initialize
            
        Returns:
            True if initialization succeeded, False otherwise
        """
        try:
            server_config = self.mcp_registry.get_server_config_safe(server_id)
            if not server_config or not server_config.enabled:
                logger.debug(f"Cannot initialize {server_id}: no config or disabled")
                return False
            
            # Create session with timeout (health monitor shouldn't wait forever)
            # Note: MCP library may log asyncio errors for connection failures - these are harmless
            try:
                session = await asyncio.wait_for(
                    self._create_session(server_id, server_config),
                    timeout=10.0  # Quick timeout for health monitor
                )
                self.sessions[server_id] = session
                
                # Remove from failed servers tracking
                if server_id in self.failed_servers:
                    del self.failed_servers[server_id]
                
                logger.debug(f"✓ Successfully initialized previously failed server: {server_id}")
                return True
                
            except asyncio.TimeoutError:
                logger.debug(f"✗ Timeout initializing {server_id} (10s)")
                return False
            except asyncio.CancelledError:
                logger.debug(f"✗ Initialization cancelled for {server_id}")
                return False
            
        except Exception as e:
            logger.debug(f"✗ Failed to initialize {server_id}: {extract_error_details(e)}")
            return False
    
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

    async def call_tool(
        self, 
        server_name: str, 
        tool_name: str, 
        parameters: Dict[str, Any], 
        session_id: str, 
        stage_execution_id: Optional[str] = None, 
        investigation_conversation: Optional['LLMConversation'] = None,
        mcp_selection: Optional['MCPSelectionConfig'] = None,
        configured_servers: Optional[List[str]] = None
    ) -> Dict[str, Any]:
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
            mcp_selection: Optional MCP selection config to validate tool calls against (user override)
            configured_servers: Optional list of agent's configured servers (fallback if no mcp_selection)
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
            
            # Validate tool call is allowed (raises ValueError if not)
            # This validation happens INSIDE the context so failures are automatically recorded
            try:
                self._validate_tool_call(server_name, tool_name, mcp_selection, configured_servers)
            except ValueError as e:
                # Mark interaction as failed and let the context record it
                from tarsy.utils.timestamp import now_us
                ctx.interaction.success = False
                ctx.interaction.error_message = f"Validation failed: {str(e)}"
                ctx.interaction.tool_result = {
                    "error": str(e),
                    "error_type": "validation_error"
                }
                ctx.interaction.end_time_us = now_us()
                ctx.interaction.duration_ms = (ctx.interaction.end_time_us - ctx.interaction.start_time_us) / 1000
                
                # Trigger hooks to record validation failure in database
                await ctx._trigger_appropriate_hooks()
                
                # Re-raise so the agent receives the error
                raise
            
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
            
            # Execute tool call with timeout - fail fast on any error
            timeout_seconds = MCP_OPERATION_TIMEOUT_SECONDS
            
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
            
            except asyncio.TimeoutError:
                # No retry - let LLM handle it
                error_msg = f"MCP tool call timed out after {timeout_seconds}s"
                logger.error(f"{error_msg} for {server_name}.{tool_name}")
                self._log_mcp_error(server_name, tool_name, error_msg, request_id)
                raise TimeoutError(error_msg) from None
                    
            except Exception as e:
                # No retry - fail fast
                error_details = extract_error_details(e)
                error_msg = f"Failed to call tool {tool_name} on {server_name}: {error_details}"
                logger.error(error_msg)
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
    
    def _log_mcp_request(self, server_name: str, tool_name: str, parameters: Dict[str, Any], request_id: str) -> None:
        """Log the outgoing MCP tool call request with sensitive data masked."""
        # Log event at INFO level (without content)
        mcp_comm_logger.info(f"MCP Request: {server_name}.{tool_name} [ID: {request_id}]")
        
        # Log detailed content at DEBUG level
        # Apply data masking to parameters before logging to prevent credential/PII exposure
        try:
            masked_parameters = self.data_masking_service.mask_response(parameters, server_name)
        except Exception as e:
            logger.warning(f"Failed to mask request parameters for logging: {e}. Using parameter keys only.")
            # Fallback: log only parameter keys, not values
            masked_parameters = {k: "__MASKED__" for k in parameters.keys()}
        
        mcp_comm_logger.debug(f"=== MCP REQUEST [{server_name}] [ID: {request_id}] ===")
        mcp_comm_logger.debug(f"Request ID: {request_id}")
        mcp_comm_logger.debug(f"Server: {server_name}")
        mcp_comm_logger.debug(f"Tool: {tool_name}")
        mcp_comm_logger.debug(f"Parameters: {json.dumps(masked_parameters, indent=2, default=str)}")
        mcp_comm_logger.debug(f"=== END REQUEST [ID: {request_id}] ===")
    
    def _log_mcp_response(self, server_name: str, tool_name: str, response: Dict[str, Any], request_id: str) -> None:
        """Log the MCP tool call response."""
        response_content = response.get("result", str(response))
        
        # Log event at INFO level (without content)
        mcp_comm_logger.info(f"MCP Response: {server_name}.{tool_name} ({len(response_content)} chars) [ID: {request_id}]")
        
        # Log detailed content at DEBUG level
        mcp_comm_logger.debug(f"=== MCP RESPONSE [{server_name}] [ID: {request_id}] ===")
        mcp_comm_logger.debug(f"Request ID: {request_id}")
        mcp_comm_logger.debug(f"Server: {server_name}")
        mcp_comm_logger.debug(f"Tool: {tool_name}")
        mcp_comm_logger.debug(f"Response length: {len(response_content)} characters")
        mcp_comm_logger.debug("--- RESPONSE CONTENT ---")
        mcp_comm_logger.debug(response_content)
        mcp_comm_logger.debug(f"=== END RESPONSE [ID: {request_id}] ===")
    
    def _log_mcp_error(self, server_name: str, tool_name: str, error_message: str, request_id: str) -> None:
        """Log MCP tool call errors."""
        mcp_comm_logger.error(f"=== MCP ERROR [{server_name}] [ID: {request_id}] ===")
        mcp_comm_logger.error(f"Request ID: {request_id}")
        mcp_comm_logger.error(f"Server: {server_name}")
        mcp_comm_logger.error(f"Tool: {tool_name}")
        mcp_comm_logger.error(f"Error: {error_message}")
        mcp_comm_logger.error(f"=== END ERROR [ID: {request_id}] ===")
    
    def _log_mcp_list_tools_request(self, server_name: Optional[str], request_id: str) -> None:
        """Log the MCP list tools request."""
        target = server_name if server_name else "ALL_SERVERS"
        # Log event at INFO level
        mcp_comm_logger.info(f"MCP List Tools Request: {target} [ID: {request_id}]")
        
        # Log detailed info at DEBUG level
        mcp_comm_logger.debug(f"=== MCP LIST TOOLS REQUEST [{target}] [ID: {request_id}] ===")
        mcp_comm_logger.debug(f"Request ID: {request_id}")
        mcp_comm_logger.debug(f"Target: {target}")
        mcp_comm_logger.debug(f"=== END LIST TOOLS REQUEST [ID: {request_id}] ===")
    
    def _log_mcp_list_tools_response(self, server_name: str, tools: List[Tool], request_id: str) -> None:
        """Log the MCP list tools response."""
        # Log event at INFO level (without detailed tool content)
        mcp_comm_logger.info(f"MCP List Tools Response: {server_name} ({len(tools)} tools) [ID: {request_id}]")
        
        # Log detailed content at DEBUG level
        mcp_comm_logger.debug(f"=== MCP LIST TOOLS RESPONSE [{server_name}] [ID: {request_id}] ===")
        mcp_comm_logger.debug(f"Request ID: {request_id}")
        mcp_comm_logger.debug(f"Server: {server_name}")
        mcp_comm_logger.debug(f"Tools count: {len(tools)}")
        mcp_comm_logger.debug("--- TOOLS ---")
        for i, tool in enumerate(tools):
            mcp_comm_logger.debug(f"Tool {i+1}: {tool.name}")
            mcp_comm_logger.debug(f"  Description: {tool.description or 'No description'}")
            mcp_comm_logger.debug(f"  Schema: {json.dumps(tool.inputSchema or {}, indent=2, default=str)}")
        mcp_comm_logger.debug(f"=== END LIST TOOLS RESPONSE [ID: {request_id}] ===")
    
    def _log_mcp_list_tools_error(self, server_name: str, error_message: str, request_id: str) -> None:
        """Log MCP list tools errors."""
        mcp_comm_logger.error(f"=== MCP LIST TOOLS ERROR [{server_name}] [ID: {request_id}] ===")
        mcp_comm_logger.error(f"Request ID: {request_id}")
        mcp_comm_logger.error(f"Server: {server_name}")
        mcp_comm_logger.error(f"Error: {error_message}")
        mcp_comm_logger.error(f"=== END LIST TOOLS ERROR [ID: {request_id}] ===")
    
    def _validate_tool_call(
        self, 
        server_name: str, 
        tool_name: str, 
        mcp_selection: Optional['MCPSelectionConfig'],
        configured_servers: Optional[List[str]]
    ) -> None:
        """
        Validate that a tool call is allowed based on MCP selection or agent configuration.
        
        This validation acts as a security filter to ensure that:
        1. User-provided MCP selections are enforced at execution time
        2. Agent-configured server restrictions are respected
        3. Unauthorized tool calls are blocked and recorded as failed interactions
        
        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool being called
            mcp_selection: Optional MCP selection config (user override, takes precedence)
            configured_servers: Optional list of agent's configured servers (fallback)
            
        Raises:
            ValueError: If the tool call is not allowed by either MCP selection or agent config
        """
        # If MCP selection is provided, validate against it (user override)
        if mcp_selection is not None:
            # Check if server is in the selection
            selected_server = next(
                (s for s in mcp_selection.servers if s.name == server_name), 
                None
            )
            
            if selected_server is None:
                # Server not in selection - not allowed
                allowed_servers = [s.name for s in mcp_selection.servers]
                raise ValueError(
                    f"Tool '{tool_name}' from server '{server_name}' not allowed by MCP selection. "
                    f"Allowed servers: {allowed_servers}"
                )
            
            # If specific tools are selected for this server, check tool is in the list
            if selected_server.tools is not None and len(selected_server.tools) > 0:
                if tool_name not in selected_server.tools:
                    raise ValueError(
                        f"Tool '{tool_name}' not allowed by MCP selection. "
                        f"Allowed tools from '{server_name}': {selected_server.tools}"
                    )
            # If tools is None or empty, all tools from this server are allowed
            logger.debug(f"Tool call validated against MCP selection: {server_name}.{tool_name}")
        
        # Otherwise, validate against agent's default configured servers (if provided)
        elif configured_servers and server_name not in configured_servers:
            raise ValueError(
                f"Tool '{tool_name}' from server '{server_name}' not allowed by agent configuration. "
                f"Configured servers: {configured_servers}"
            )

    async def close(self) -> None:
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