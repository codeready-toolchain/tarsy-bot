"""HTTP transport implementation for MCP servers."""

import json
from typing import Dict, Any, Optional
import aiohttp
from mcp import ClientSession
from mcp.types import Tool

from .factory import MCPTransport
from tarsy.models.mcp_transport_config import HTTPTransportConfig
from tarsy.utils.logger import get_module_logger
from tarsy.utils.error_details import extract_error_details

logger = get_module_logger(__name__)


class HTTPMCPSession(ClientSession):
    """HTTP-based MCP session implementation per MCP Streamable HTTP specification."""
    
    def __init__(self, server_id: str, config: HTTPTransportConfig, session: aiohttp.ClientSession):
        self.server_id = server_id
        self.config = config
        self.http_session = session
        self._initialized = False
        self._session_id: Optional[str] = None
        self._request_id = 0
    
    async def initialize(self):
        """Initialize the HTTP MCP session using JSON-RPC initialize request."""
        if self._initialized:
            return
        
        try:
            # Send JSON-RPC initialize request
            initialize_request = {
                "jsonrpc": "2.0",
                "id": self._get_next_request_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "tarsy",
                        "version": "1.0"
                    }
                }
            }
            
            response_data = await self._send_jsonrpc_request(initialize_request)
            
            # Extract session ID if provided
            if "Mcp-Session-Id" in response_data.get("headers", {}):
                self._session_id = response_data["headers"]["Mcp-Session-Id"]
            
            self._initialized = True
            logger.info(f"HTTP MCP session initialized for server: {self.server_id}")
            
        except Exception as e:
            error_details = extract_error_details(e)
            logger.error(f"Failed to initialize HTTP MCP session for {self.server_id}: {error_details}")
            raise
    
    async def list_tools(self):
        """List tools using JSON-RPC tools/list request."""
        if not self._initialized:
            await self.initialize()
        
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_request_id(),
            "method": "tools/list",
            "params": {}
        }
        
        response_data = await self._send_jsonrpc_request(request)
        tools_data = response_data.get("result", {})
        tools = [Tool(**tool) for tool in tools_data.get("tools", [])]
        return type('ToolsResult', (), {'tools': tools})()
    
    async def call_tool(self, tool_name: str, parameters: Dict[str, Any]):
        """Call tool using JSON-RPC tools/call request."""
        if not self._initialized:
            await self.initialize()
        
        request = {
            "jsonrpc": "2.0",
            "id": self._get_next_request_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": parameters
            }
        }
        
        response_data = await self._send_jsonrpc_request(request)
        result = response_data.get("result", {})
        
        # Convert to MCP-compatible result format
        return type('ToolResult', (), {
            'content': [type('Content', (), {'text': json.dumps(result)})()]
        })()
    
    async def _send_jsonrpc_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send JSON-RPC request to MCP endpoint."""
        headers = self._build_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        
        # Add protocol version header
        headers["MCP-Protocol-Version"] = "2025-06-18"
        
        # Add session ID if available
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        
        async with self.http_session.post(
            str(self.config.url),
            json=request,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        ) as response:
            response.raise_for_status()
            
            # Check if server provided session ID in response headers
            if "Mcp-Session-Id" in response.headers and not self._session_id:
                self._session_id = response.headers["Mcp-Session-Id"]
            
            # Handle JSON response
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                response_json = await response.json()
                
                # Check for JSON-RPC error
                if "error" in response_json:
                    error_info = response_json["error"]
                    raise Exception(f"JSON-RPC error {error_info.get('code', 'unknown')}: {error_info.get('message', 'Unknown error')}")
                
                return response_json
            else:
                raise Exception(f"Unexpected content type: {content_type}")
    
    def _build_headers(self) -> Dict[str, str]:
        """Build HTTP headers with bearer token authentication per MCP Authorization specification."""
        headers = dict(self.config.headers or {})

        # Add Authorization header with Bearer token if configured
        if self.config.bearer_token:
            # Per MCP spec: Must use Authorization header with Bearer token format
            headers["Authorization"] = f"Bearer {self.config.bearer_token}"
        
        return headers
    
    def _get_next_request_id(self) -> int:
        """Get next JSON-RPC request ID."""
        self._request_id += 1
        return self._request_id


class HTTPTransport(MCPTransport):
    """HTTP transport for MCP servers."""
    
    def __init__(self, server_id: str, config: HTTPTransportConfig):
        self.server_id = server_id
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.mcp_session: Optional[HTTPMCPSession] = None
    
    async def create_session(self) -> ClientSession:
        """Create HTTP MCP session."""
        if self.mcp_session:
            return self.mcp_session
        
        # Create SSL context
        ssl_context = None
        if not self.config.verify_ssl:
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        
        # Create HTTP session with timeout
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector
        )
        
        # Create MCP session
        self.mcp_session = HTTPMCPSession(self.server_id, self.config, self.session)
        await self.mcp_session.initialize()
        
        return self.mcp_session
    
    async def close(self):
        """Close HTTP transport."""
        if self.session:
            await self.session.close()
            self.session = None
        self.mcp_session = None
    
    @property
    def is_connected(self) -> bool:
        """Check if HTTP transport is connected."""
        return self.session is not None and not self.session.closed
