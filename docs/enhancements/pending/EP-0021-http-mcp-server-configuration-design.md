# EP-0021: HTTP MCP Server Configuration Support

## Implementation Status 🚧

**🔄 PENDING: Phase 1** - Configuration Model Extensions  
**🔄 PENDING: Phase 2** - MCP Client Transport Layer  
**🔄 PENDING: Phase 3** - HTTP Client Integration  
**🔄 PENDING: Phase 4** - Registry and Validation  
**🔄 PENDING: Phase 5** - Testing and Documentation  

## Problem Statement

**Note**: This design follows the official [MCP Streamable HTTP Transport specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) which uses a single endpoint with JSON-RPC messages, not REST-style multiple endpoints.

The current MCP server implementation only supports **stdio transport**, limiting integration with modern MCP servers that provide HTTP endpoints:

1. **Transport Limitation**: Only stdio-based MCP servers can be configured via `StdioServerParameters`
2. **Modern MCP Servers**: Many production MCP servers expose HTTP endpoints for better scalability and deployment flexibility
3. **Network Integration**: HTTP transports enable containerized, remote, and cloud-based MCP server deployments
4. **Limited Ecosystem**: Restricted to command-line MCP servers, missing web-based and service-oriented implementations

**Current Flow**:
```
MCP Client → StdioServerParameters → subprocess.Popen → stdin/stdout communication
```

**Missing Capabilities**:
```
MCP Client → HTTP Transport → JSON-RPC over HTTP
```

## Solution Overview

Extend the MCP server configuration system to support **HTTP transports** with a clean, unified configuration approach:

1. **Multi-Transport Architecture**: Support stdio and HTTP transports with unified configuration
2. **Transport-Specific Parameters**: Dedicated configuration models for each transport type
3. **Connection Management**: Abstract transport layer with consistent session interface
4. **Service Discovery**: Support for URL-based MCP server endpoints
5. **Security Integration**: Authentication and TLS support for HTTP transports
6. **Unified Configuration**: All transport types use the same structured configuration format

**Target Architecture**:
```
MCP Client → Transport Factory → [Stdio|HTTP] Transport → Unified Session Interface
```

## Key MCP Specification Clarifications

Based on the [official MCP Transport specification](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports):

### **Single Endpoint Pattern**
- MCP servers provide **one HTTP endpoint** (e.g., `/mcp`) for all operations
- POST requests are used for sending JSON-RPC messages

### **JSON-RPC Message Format**
- All communications use **JSON-RPC 2.0** format
- Tool listing: `{"jsonrpc": "2.0", "method": "tools/list", "params": {}}`  
- Tool calling: `{"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "...", "arguments": {...}}}`

### **Session Management**
- Optional `Mcp-Session-Id` header for stateful sessions
- `MCP-Protocol-Version: 2025-06-18` header required
- Session lifecycle managed through JSON-RPC initialize/terminate

## Key Implementation Points

### **1. Transport Configuration Strategy**
- **Unified Interface**: All transports implement common `MCPTransport` interface
- **Transport-Specific Config**: Dedicated parameter models for HTTP configuration
- **Explicit Transport Types**: Transport type must be explicitly specified in configuration
- **Connection Pooling**: Reuse HTTP connections for performance

### **2. Configuration Structure Design**
```yaml
# Stdio Transport - explicit type required for discriminated unions
kubernetes-server:
  transport:
    type: "stdio"  # Required discriminator field
    command: "npx"
    args: ["-y", "kubernetes-mcp-server@latest"]
    env:
      KUBECONFIG: "${KUBECONFIG}"

# HTTP Transport (production) - with bearer token authentication over HTTPS
azure-mcp-http:
  transport:
    type: "http"  # Required discriminator field
    url: "https://azure-mcp.example.com/mcp"  # Single MCP endpoint (HTTPS for production)
    bearer_token: "${AZURE_MCP_ACCESS_TOKEN}"  # Pre-configured bearer token
    timeout: 30
    headers:
      User-Agent: "tarsy/1.0"
    verify_ssl: true

# HTTP Transport (development) - HTTP allowed for local testing
local-dev-mcp:
  transport:
    type: "http"  # Required discriminator field
    url: "http://localhost:3000/mcp"  # HTTP OK for development/testing
    bearer_token: "${DEV_MCP_TOKEN}"  # Development token
    timeout: 10
```

### **3. Security and Authentication (Machine-to-Machine)**
- **Bearer Token Format**: `Authorization: Bearer <access-token>` header format per MCP Authorization spec
- **Pre-configured Tokens**: Support for pre-obtained access tokens (no OAuth flow in Tarsy)
- **HTTPS Recommended**: HTTPS strongly recommended for production; HTTP allowed for development/testing
- **Token Validation**: MCP servers validate bearer tokens as per OAuth 2.1 resource server requirements
- **Machine-to-Machine**: No browser/user-agent flows - suitable for server-to-server communication
- **Environment Variables**: Secure token storage via environment variable expansion
- **Development Flexibility**: HTTP support for local development and testing scenarios

### **4. Connection Management**
- **Connection Pooling**: Reuse HTTP connections for efficiency
- **Retry Logic**: Automatic retry with exponential backoff
- **Health Checks**: Connection validation and auto-recovery
- **Timeout Handling**: Configurable request and connection timeouts

## Detailed Implementation

### **1. Transport Parameter Models**

**Location**: `backend/tarsy/models/mcp_transport_config.py` (new file)

```python
"""MCP transport configuration models."""

from enum import Enum
from typing import Dict, Any, Optional, List, Literal
from pydantic import BaseModel, Field, HttpUrl, field_validator

class TransportType(str, Enum):
    """Supported MCP transport types."""
    
    STDIO = "stdio"
    HTTP = "http"

class BaseTransportConfig(BaseModel):
    """Base configuration for MCP transports."""
    
    type: str = Field(..., description="Transport type identifier")
    timeout: Optional[int] = Field(
        default=30, 
        description="Connection timeout in seconds",
        ge=1,
        le=300
    )

class StdioTransportConfig(BaseTransportConfig):
    """Configuration for stdio transport (existing functionality)."""
    
    type: Literal["stdio"] = Field(
        default="stdio", 
        description="Transport type - automatically set to 'stdio'"
    )
    command: str = Field(
        ..., 
        description="Command to execute for the MCP server",
        min_length=1
    )
    args: Optional[List[str]] = Field(
        default_factory=list, 
        description="Command line arguments for the MCP server"
    )
    env: Optional[Dict[str, str]] = Field(
        default_factory=dict, 
        description="Environment variables for the MCP server process"
    )

    @field_validator('command')
    def validate_command_not_empty(cls, v: str) -> str:
        """Validate that command is not empty or only whitespace."""
        if not v or not v.strip():
            raise ValueError("Command cannot be empty")
        return v.strip()

class HTTPTransportConfig(BaseTransportConfig):
    """Configuration for HTTP transport per MCP Streamable HTTP specification."""
    
    type: Literal["http"] = Field(
        default="http", 
        description="Transport type - automatically set to 'http'"
    )
    url: HttpUrl = Field(
        ..., 
        description="Single MCP endpoint URL (e.g., 'https://api.example.com/mcp')"
    )
    bearer_token: Optional[str] = Field(
        default=None,
        description="Bearer access token for machine-to-machine authentication",
        min_length=1
    )
    headers: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Additional HTTP headers (Authorization header managed by bearer_token)"
    )
    verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificates (strongly recommended for production)"
    )

    # Note: HttpUrl automatically validates that scheme is http or https

    @field_validator('bearer_token')
    def validate_bearer_token_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate bearer token format if provided."""
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Bearer token cannot be empty if provided")
            if any(char in v for char in ['\n', '\r', '\t']):
                raise ValueError("Bearer token cannot contain newlines, carriage returns, or tabs")
        return v

    @field_validator('headers')
    def validate_headers_no_auth(cls, v: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """Validate that Authorization header is not manually set (use bearer_token instead)."""
        if v:
            auth_headers = [key.lower() for key in v.keys() if key.lower() == 'authorization']
            if auth_headers:
                raise ValueError(
                    "Do not set 'Authorization' header manually - use 'bearer_token' field instead"
                )
        return v

```

### **2. Transport Factory and Interface**

**Location**: `backend/tarsy/integrations/mcp/transport/factory.py` (new file)

```python
"""MCP transport factory for creating transport instances."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from mcp import ClientSession

from tarsy.models.agent_config import TransportConfig
from tarsy.models.mcp_transport_config import (
    TransportType,
    StdioTransportConfig,
    HTTPTransportConfig
)
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)

class MCPTransport(ABC):
    """Abstract base class for MCP transports."""
    
    @abstractmethod
    async def create_session(self) -> ClientSession:
        """Create and initialize an MCP session."""
        pass
    
    @abstractmethod
    async def close(self):
        """Close the transport connection."""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if transport is connected."""
        pass

class MCPTransportFactory:
    """Factory for creating MCP transport instances."""
    
    @staticmethod
    def create_transport(
        server_id: str,
        transport: TransportConfig,
        exit_stack: Optional[Any] = None
    ) -> MCPTransport:
        """
        Create appropriate transport instance based on configuration.
        
        Args:
            server_id: Unique identifier for the server
            transport: Transport-specific configuration
            exit_stack: Optional AsyncExitStack for resource management
            
        Returns:
            MCPTransport instance
            
        Raises:
            ValueError: If transport type is not supported
        """
        transport_type = transport.type
        
        if transport_type == TransportType.STDIO:
            from .stdio_transport import StdioTransport
            return StdioTransport(server_id, transport, exit_stack)
        elif transport_type == TransportType.HTTP:
            from .http_transport import HTTPTransport
            return HTTPTransport(server_id, transport)
        else:
            raise ValueError(f"Unsupported transport type: {transport_type}")
    
```

### **3. Stdio Transport Implementation**

**Location**: `backend/tarsy/integrations/mcp/transport/stdio_transport.py` (new file)

```python
"""Stdio transport implementation - wrapper around existing MCP SDK functionality."""

from contextlib import AsyncExitStack
from typing import Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tarsy.integrations.mcp.transport.factory import MCPTransport
from tarsy.models.mcp_transport_config import StdioTransportConfig
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)

class StdioTransport(MCPTransport):
    """Stdio transport wrapper to integrate existing functionality into unified transport architecture."""
    
    def __init__(self, server_id: str, config: StdioTransportConfig, exit_stack: AsyncExitStack):
        """
        Initialize stdio transport.
        
        Args:
            server_id: Unique identifier for the server
            config: Stdio transport configuration
            exit_stack: AsyncExitStack for resource management
        """
        self.server_id = server_id
        self.config = config
        self.exit_stack = exit_stack
        self.session: Optional[ClientSession] = None
        self._connected = False
    
    async def create_session(self) -> ClientSession:
        """Create stdio session using existing MCP SDK."""
        if self.session:
            return self.session
        
        logger.info(f"Creating stdio session for server: {self.server_id}")
        
        # Create stdio parameters from config
        stdio_params = StdioServerParameters(
            command=self.config.command,
            args=self.config.args or [],
            env=self.config.env or {}
        )
        
        # Use existing MCP SDK stdio client with exit_stack management
        stdio_context = stdio_client(stdio_params)
        self.session = await self.exit_stack.enter_async_context(stdio_context)
        self._connected = True
        
        logger.info(f"Stdio session created for server: {self.server_id}")
        return self.session
    
    async def close(self):
        """Close stdio transport (handled automatically by exit_stack)."""
        if self._connected:
            logger.info(f"Closing stdio transport for server: {self.server_id}")
            self._connected = False
            self.session = None
    
    @property
    def is_connected(self) -> bool:
        """Check if stdio transport is connected."""
        return self._connected and self.session is not None
```

### **4. HTTP Transport Implementation**

**Location**: `backend/tarsy/integrations/mcp/transport/http_transport.py` (new file)

```python
"""HTTP transport implementation for MCP servers."""

import json
import asyncio
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
                return await response.json()
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
```

### **5. Enhanced MCP Client**

**Location**: `backend/tarsy/integrations/mcp/client.py` (enhanced existing file)

```python
# Import new transport components
from tarsy.integrations.mcp.transport.factory import MCPTransportFactory, MCPTransport
from tarsy.models.agent_config import TransportConfig
from tarsy.models.mcp_transport_config import TransportType

class MCPClient:
    """Enhanced MCP client with multi-transport support."""
    
    def __init__(self, settings: Settings, mcp_registry: Optional[MCPServerRegistry] = None, 
                 summarizer: Optional['MCPResultSummarizer'] = None):
        self.settings = settings
        self.mcp_registry = mcp_registry or MCPServerRegistry()
        self.data_masking_service = DataMaskingService(self.mcp_registry)
        self.summarizer = summarizer
        self.token_counter = TokenCounter()
        
        # Enhanced session management
        self.sessions: Dict[str, ClientSession] = {}
        self.transports: Dict[str, MCPTransport] = {}  # NEW: Transport instances
        self.exit_stack = AsyncExitStack()
        self._initialized = False
    
    async def _create_session(self, server_id: str, server_config: MCPServerConfigModel) -> ClientSession:
        """Create session using appropriate transport."""
        try:
            # Get already-parsed transport configuration (no manual parsing needed!)
            transport_config = server_config.transport
            
            # Create transport instance
            transport = MCPTransportFactory.create_transport(
                server_id, 
                transport_config, 
                self.exit_stack if transport_config.type == TransportType.STDIO else None
            )
            
            # Store transport for lifecycle management
            self.transports[server_id] = transport
            
            # Create session via transport
            session = await transport.create_session()
            
            logger.info(f"Created {transport_config.type.value} session for server: {server_id}")
            return session
            
        except Exception as e:
            error_details = extract_error_details(e)
            logger.error(f"Failed to create session for {server_id}: {error_details}")
            raise
    
    async def close(self):
        """Enhanced close with transport cleanup."""
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
            self.sessions.clear()
            self.transports.clear()
            self._initialized = False
```

### **6. Configuration Model Updates**

**Location**: `backend/tarsy/models/agent_config.py` (enhanced existing file)

```python
from typing import Union
from pydantic import Field, discriminator

from tarsy.models.mcp_transport_config import StdioTransportConfig, HTTPTransportConfig

# Transport configuration union with discriminator
TransportConfig = Union[StdioTransportConfig, HTTPTransportConfig]

class MCPServerConfigModel(BaseModel):
    """Enhanced MCP server configuration with multi-transport support."""
    
    # ... existing fields ...
    
    transport: TransportConfig = Field(
        ...,
        description="Transport-specific configuration (stdio or HTTP)",
        discriminator='type'
    )
```

### **7. Registry Enhancement**

**Location**: `backend/tarsy/services/mcp_server_registry.py` (enhanced existing file)

```python
class MCPServerRegistry:
    """Enhanced registry with automatic transport validation."""
    
    def _validate_server_config(self, server_id: str, config_dict: Dict[str, Any]) -> None:
        """Validate server configuration - Pydantic handles transport validation automatically."""
        try:
            # Pydantic model validation handles all transport validation automatically
            server_config = MCPServerConfigModel(**config_dict)
            
            # Log the validated transport type
            transport_type = server_config.transport.type
            logger.debug(f"Validated {transport_type.value} transport for server: {server_id}")
            
        except Exception as e:
            logger.error(f"Invalid server configuration for {server_id}: {e}")
            raise
```

### **8. Dependencies and Requirements**

**Location**: `backend/pyproject.toml` (add new dependencies)

```toml
[tool.poetry.dependencies]
# Existing dependencies...

# HTTP transport support
aiohttp = "^3.9.0"
```

## Implementation Phases

### **Phase 1: Configuration Model Extensions**

**Deliverables:**
- Transport configuration models with validation
- Updated MCPServerConfigModel with discriminated union support
- Pydantic-based configuration parsing with automatic transport detection

**Tasks:**
1. **Create Transport Config Models** (`backend/tarsy/models/mcp_transport_config.py`)
   - Implement `TransportType` enum for type safety
   - Create `BaseTransportConfig` and specific transport configurations
   - Add bearer token authentication with field validation
   - Include SSL verification options (verify_ssl boolean)

2. **Update Agent Config Models** (`backend/tarsy/models/agent_config.py`)
   - Define `TransportConfig` union type with discriminated unions
   - Update `MCPServerConfigModel.transport` field with `discriminator='type'`
   - Remove manual parsing methods - Pydantic handles transport type resolution automatically

3. **Configuration Testing**
   - Unit tests for all transport configuration models
   - Discriminated union validation testing
   - Bearer token and SSL configuration validation

**Verification:** All configuration models validate correctly and enforce proper transport configurations.

### **Phase 2: MCP Client Transport Layer**

**Deliverables:**
- Transport factory and abstract interface
- Enhanced MCP client with transport support
- Connection management and lifecycle handling

**Tasks:**
1. **Create Transport Factory** (`backend/tarsy/integrations/mcp/transport/factory.py`)
   - Implement `MCPTransport` abstract interface
   - Create transport factory using explicit transport types
   - Add transport lifecycle management and connection handling

2. **Create Stdio Transport Wrapper** (`backend/tarsy/integrations/mcp/transport/stdio_transport.py`)
   - Implement `StdioTransport` class wrapping existing `stdio_client`
   - Bridge existing functionality to new `MCPTransport` interface
   - Maintain compatibility with `AsyncExitStack` resource management

3. **Enhance MCP Client** (`backend/tarsy/integrations/mcp/client.py`)
   - Update session creation to use transport factory
   - Add transport instance management and cleanup
   - Remove manual transport parsing (use discriminated unions directly)

4. **Transport Testing**
   - Mock transport implementations for testing
   - Connection management and lifecycle tests
   - Error handling and recovery tests

**Verification:** MCP client can create sessions using transport factory, existing stdio functionality is preserved.

### **Phase 3: HTTP Client Integration**

**Deliverables:**
- HTTP transport implementation
- Authentication and SSL/TLS support
- Connection pooling and timeout handling

**Tasks:**
1. **HTTP Transport Implementation** (`backend/tarsy/integrations/mcp/transport/http_transport.py`)
   - Implement HTTP-based MCP session with JSON-RPC 2.0 protocol
   - Add bearer token authentication per MCP Authorization specification
   - Support SSL verification (verify_ssl boolean flag)
   - Implement MCP session management with proper headers

2. **HTTP Session Management**
   - Connection pooling with aiohttp for efficiency
   - Configurable request timeout handling
   - JSON-RPC request/response correlation
   - Session lifecycle management (initialize/terminate)

3. **HTTP Testing**
   - Mock HTTP MCP server for testing JSON-RPC endpoints
   - Bearer token authentication testing
   - SSL verification configuration testing

**Verification:** HTTP MCP servers can be configured and communicate successfully with proper authentication.

### **Phase 4: Registry and Validation**

**Deliverables:**
- Simplified registry using automatic Pydantic validation
- Updated configuration examples with new transport structure
- Security best practices documentation

**Tasks:**
1. **Registry Enhancement** (`backend/tarsy/services/mcp_server_registry.py`)
   - Remove manual transport validation (Pydantic handles it automatically)
   - Simplify server configuration instantiation using discriminated unions
   - Add logging for validated transport types

2. **Configuration Examples**
   - Update `config/agents.yaml.example` with new transport examples
   - Add authentication configuration examples
   - Document security best practices

**Verification:** Registry validates all transport configurations, examples work correctly.

### **Phase 5: Testing and Documentation**

**Deliverables:**
- Comprehensive test suite
- Integration tests with real MCP servers

**Tasks:**
1. **Integration Testing**
   - End-to-end tests with HTTP MCP servers
   - Authentication flow testing
   - Error recovery scenario testing

2. **Documentation Updates**
   - API documentation for new transport features
   - Configuration reference documentation
   - Security considerations and best practices

**Verification:** Full test suite passes, documentation is complete and accurate.

## Specification Compliance

### **📋 Specification References**

- **Transport Overview**: [MCP Transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- **Authorization Specification**: [MCP Authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization)
- **Streamable HTTP**: Single endpoint with POST/GET methods
- **JSON-RPC Format**: Tools operations as `tools/list` and `tools/call` methods
- **Bearer Token Requirements**: `Authorization: Bearer <token>` header format
- **Security Requirements**: HTTPS recommended for production, token validation

## Configuration Examples

### **Complete Agent Configuration**

```yaml
# config/agents.yaml
mcp_servers:
  # Stdio server
  kubernetes-server:
    server_id: "kubernetes-server"
    server_type: "kubernetes"
    enabled: true
    transport:
      type: "stdio"  # Required discriminator field
      command: "npx"
      args: ["-y", "kubernetes-mcp-server@latest", "--read-only"]
      env:
        KUBECONFIG: "${KUBECONFIG}"
    
  # Production HTTP server (HTTPS recommended)
  azure-mcp-server:
    server_id: "azure-mcp-server"
    server_type: "azure"
    enabled: true
    transport:
      type: "http"
      url: "https://azure-mcp.example.com/mcp"  # HTTPS for production
      bearer_token: "${AZURE_MCP_ACCESS_TOKEN}"  # Pre-configured bearer token
      timeout: 30
      verify_ssl: true
    instructions: |
      Azure MCP server with bearer token authentication per MCP Authorization specification.
      Uses Authorization: Bearer <token> header for machine-to-machine authentication.
    
  # Development HTTP server (HTTP allowed for local testing)
  local-dev-server:
    server_id: "local-dev-server"
    server_type: "development"
    enabled: true
    transport:
      type: "http"
      url: "http://localhost:3000/mcp"  # HTTP OK for development
      bearer_token: "${DEV_MCP_TOKEN}"  # Development token
      timeout: 10
      verify_ssl: false  # Not needed for HTTP
    instructions: |
      Local development MCP server for testing.
      HTTP is acceptable for localhost development scenarios.
    
```

### **Environment Variables**

```bash
# .env - Bearer tokens for machine-to-machine MCP authentication

# Production tokens (use with HTTPS endpoints)
AZURE_MCP_ACCESS_TOKEN="your-bearer-access-token-for-azure-mcp"

# Development tokens (can use with HTTP localhost endpoints)
DEV_MCP_TOKEN="dev-token-for-local-testing"

# Other configuration
KUBECONFIG="/path/to/kubeconfig"

# Security Notes:
# - Use HTTPS endpoints in production for secure token transmission
# - HTTP endpoints are acceptable for local development and testing
# - Bearer tokens should be obtained through your organization's token management system
# - These are pre-configured tokens for server-to-server communication (no OAuth flows)
```
