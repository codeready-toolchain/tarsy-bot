"""
Tests for HTTP transport implementation.

This module tests the HTTP transport functionality including:
- JSON-RPC 2.0 protocol over HTTP
- Bearer token authentication 
- SSL verification configuration
- Session management and lifecycle
- Error handling scenarios
"""

import ssl
from unittest.mock import Mock, AsyncMock, patch

import pytest
import aiohttp

from tarsy.integrations.mcp.transport.http_transport import HTTPTransport, HTTPMCPSession
from tarsy.models.mcp_transport_config import HTTPTransportConfig


@pytest.mark.unit
class TestHTTPMCPSession:
    """Test HTTP MCP Session implementation."""

    @pytest.fixture
    def mock_http_session(self):
        """Create mock aiohttp ClientSession."""
        return AsyncMock(spec=aiohttp.ClientSession)

    @pytest.fixture
    def http_config(self):
        """Create HTTP transport configuration."""
        return HTTPTransportConfig(
            url="https://api.example.com/mcp",
            bearer_token="test-token-123",
            verify_ssl=True,
            timeout=30,
            headers={"User-Agent": "tarsy/1.0"}
        )

    @pytest.fixture
    def http_session(self, http_config, mock_http_session):
        """Create HTTP MCP session."""
        return HTTPMCPSession("test-server", http_config, mock_http_session)

    def test_http_session_initialization(self, http_session, http_config):
        """Test HTTP MCP session initialization."""
        assert http_session.server_id == "test-server"
        assert http_session.config == http_config
        assert not http_session._initialized
        assert http_session._session_id is None
        assert http_session._request_id == 0

    def test_get_next_request_id(self, http_session):
        """Test request ID generation."""
        assert http_session._get_next_request_id() == 1
        assert http_session._get_next_request_id() == 2
        assert http_session._get_next_request_id() == 3

    def test_build_headers_with_bearer_token(self, http_session):
        """Test header building with bearer token."""
        headers = http_session._build_headers()
        
        assert headers["Authorization"] == "Bearer test-token-123"
        assert headers["User-Agent"] == "tarsy/1.0"

    def test_build_headers_without_bearer_token(self, mock_http_session):
        """Test header building without bearer token."""
        config = HTTPTransportConfig(
            url="https://api.example.com/mcp",
            verify_ssl=True,
            headers={"Custom-Header": "value"}
        )
        session = HTTPMCPSession("test-server", config, mock_http_session)
        
        headers = session._build_headers()
        
        assert "Authorization" not in headers
        assert headers["Custom-Header"] == "value"

    @pytest.mark.asyncio
    async def test_successful_initialize_request(self, http_session):
        """Test successful MCP initialization."""
        # Mock HTTP response with proper async json() method
        mock_response = AsyncMock()
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "test-server", "version": "1.0"}
            }
        })
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        http_session.http_session.post.return_value = mock_context
        
        await http_session.initialize()
        
        assert http_session._initialized
        http_session.http_session.post.assert_called_once()
        
        # Verify request was properly formatted
        call_args = http_session.http_session.post.call_args
        assert call_args[0][0] == "https://api.example.com/mcp"
        
        # Check JSON-RPC request structure
        request_data = call_args[1]["json"]
        assert request_data["jsonrpc"] == "2.0"
        assert request_data["method"] == "initialize"
        assert request_data["params"]["protocolVersion"] == "2025-06-18"
        assert request_data["params"]["clientInfo"]["name"] == "tarsy"

    @pytest.mark.asyncio 
    async def test_initialize_with_session_id_in_headers(self, http_session):
        """Test initialization with session ID provided in response headers."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = Mock()
        mock_response.headers = {
            "Content-Type": "application/json",
            "Mcp-Session-Id": "session-123"
        }
        mock_response.json = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {}
        })
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        http_session.http_session.post.return_value = mock_context
        
        await http_session.initialize()
        
        assert http_session._session_id == "session-123"
        assert http_session._initialized

    @pytest.mark.asyncio
    async def test_initialize_error_handling(self, http_session):
        """Test initialization error handling."""
        http_session.http_session.post.side_effect = aiohttp.ClientError("Connection failed")
        
        with pytest.raises(aiohttp.ClientError):
            await http_session.initialize()
        
        assert not http_session._initialized

    @pytest.mark.asyncio
    async def test_list_tools_request(self, http_session):
        """Test tools/list JSON-RPC request."""
        # Mock initialize response
        http_session._initialized = True
        
        # Mock tools/list response
        mock_response = AsyncMock()
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {
                        "name": "test_tool",
                        "description": "A test tool",
                        "inputSchema": {"type": "object", "properties": {}}
                    }
                ]
            }
        })
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        http_session.http_session.post.return_value = mock_context
        
        result = await http_session.list_tools()
        
        assert len(result.tools) == 1
        assert result.tools[0].name == "test_tool"
        
        # Verify request format
        call_args = http_session.http_session.post.call_args
        request_data = call_args[1]["json"]
        assert request_data["method"] == "tools/list"
        assert request_data["params"] == {}

    @pytest.mark.asyncio
    async def test_call_tool_request(self, http_session):
        """Test tools/call JSON-RPC request."""
        # Mock initialize response
        http_session._initialized = True
        
        # Mock tools/call response
        mock_response = Mock()
        mock_response.raise_for_status = Mock() 
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [{"type": "text", "text": "Tool executed successfully"}]
            }
        }
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_context
        mock_context.raise_for_status = Mock()
        mock_context.headers = {"Content-Type": "application/json"}
        mock_context.json.return_value = mock_response.json.return_value
        http_session.http_session.post.return_value = mock_context
        
        result = await http_session.call_tool("test_tool", {"param": "value"})
        
        assert hasattr(result, 'content')
        assert len(result.content) == 1
        
        # Verify request format
        call_args = http_session.http_session.post.call_args
        request_data = call_args[1]["json"]
        assert request_data["method"] == "tools/call"
        assert request_data["params"]["name"] == "test_tool"
        assert request_data["params"]["arguments"] == {"param": "value"}

    @pytest.mark.asyncio
    async def test_json_rpc_error_handling(self, http_session):
        """Test JSON-RPC error response handling."""
        # Mock error response
        mock_response = AsyncMock()
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json = AsyncMock(return_value={
            "jsonrpc": "2.0",
            "id": 1,
            "error": {
                "code": -32601,
                "message": "Method not found",
                "data": {"method": "invalid/method"}
            }
        })
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        http_session.http_session.post.return_value = mock_context
        
        with pytest.raises(Exception, match="JSON-RPC error -32601: Method not found"):
            await http_session._send_jsonrpc_request({"method": "invalid/method"})

    @pytest.mark.asyncio
    async def test_session_id_persistence(self, http_session):
        """Test session ID persistence across requests."""
        http_session._session_id = "persistent-session-123"
        
        mock_response = AsyncMock()
        mock_response.raise_for_status = Mock()
        mock_response.headers = {"Content-Type": "application/json"}
        mock_response.json = AsyncMock(return_value={"jsonrpc": "2.0", "id": 1, "result": {}})
        
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        http_session.http_session.post.return_value = mock_context
        
        await http_session._send_jsonrpc_request({"method": "test"})
        
        # Verify session ID was included in headers
        call_args = http_session.http_session.post.call_args
        headers = call_args[1]["headers"]
        assert headers["Mcp-Session-Id"] == "persistent-session-123"


@pytest.mark.unit
class TestHTTPTransport:
    """Test HTTP Transport implementation."""

    @pytest.fixture
    def http_config(self):
        """Create HTTP transport configuration."""
        return HTTPTransportConfig(
            url="https://secure.example.com/mcp",
            bearer_token="secure-token-456", 
            verify_ssl=True,
            timeout=45
        )

    @pytest.fixture
    def http_transport(self, http_config):
        """Create HTTP transport."""
        return HTTPTransport("secure-server", http_config)

    def test_http_transport_initialization(self, http_transport, http_config):
        """Test HTTP transport initialization."""
        assert http_transport.server_id == "secure-server"
        assert http_transport.config == http_config
        assert http_transport.session is None
        assert http_transport.mcp_session is None

    @pytest.mark.asyncio
    async def test_create_session_with_ssl_verification(self, http_transport):
        """Test session creation with SSL verification enabled."""
        with patch('aiohttp.ClientSession') as mock_client_session_class, \
             patch('aiohttp.TCPConnector') as mock_connector_class:
            
            mock_session = AsyncMock()
            mock_client_session_class.return_value = mock_session
            
            mock_mcp_session = AsyncMock()
            with patch('tarsy.integrations.mcp.transport.http_transport.HTTPMCPSession') as mock_mcp_session_class:
                mock_mcp_session_class.return_value = mock_mcp_session
                
                session = await http_transport.create_session()
                
                assert session == mock_mcp_session
                assert http_transport.session == mock_session
                assert http_transport.mcp_session == mock_mcp_session
                
                # Verify SSL connector was created without disabling verification
                mock_connector_class.assert_called_once_with(ssl=None)
                mock_mcp_session.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_session_with_ssl_disabled(self, http_config):
        """Test session creation with SSL verification disabled."""
        http_config.verify_ssl = False
        http_transport = HTTPTransport("insecure-server", http_config)
        
        with patch('aiohttp.ClientSession') as mock_client_session_class, \
             patch('aiohttp.TCPConnector') as mock_connector_class, \
             patch('ssl.create_default_context') as mock_ssl_context:
            
            mock_session = AsyncMock()
            mock_client_session_class.return_value = mock_session
            
            mock_ssl_ctx = Mock()
            mock_ssl_context.return_value = mock_ssl_ctx
            
            mock_mcp_session = AsyncMock()
            with patch('tarsy.integrations.mcp.transport.http_transport.HTTPMCPSession') as mock_mcp_session_class:
                mock_mcp_session_class.return_value = mock_mcp_session
                
                await http_transport.create_session()
                
                # Verify SSL context was configured to disable verification
                assert mock_ssl_ctx.check_hostname == False
                assert mock_ssl_ctx.verify_mode == ssl.CERT_NONE
                mock_connector_class.assert_called_once_with(ssl=mock_ssl_ctx)

    @pytest.mark.asyncio
    async def test_session_reuse(self, http_transport):
        """Test that existing session is reused."""
        mock_existing_session = AsyncMock()
        http_transport.mcp_session = mock_existing_session
        
        session = await http_transport.create_session()
        
        assert session == mock_existing_session

    @pytest.mark.asyncio
    async def test_close_transport(self, http_transport):
        """Test transport closure."""
        mock_session = AsyncMock()
        http_transport.session = mock_session
        http_transport.mcp_session = AsyncMock()
        
        await http_transport.close()
        
        mock_session.close.assert_called_once()
        assert http_transport.session is None
        assert http_transport.mcp_session is None

    def test_is_connected_property(self, http_transport):
        """Test connection status property."""
        # Initially not connected
        assert not http_transport.is_connected
        
        # Mock connected session
        mock_session = Mock()
        mock_session.closed = False
        http_transport.session = mock_session
        assert http_transport.is_connected
        
        # Mock closed session
        mock_session.closed = True
        assert not http_transport.is_connected
        
        # No session
        http_transport.session = None
        assert not http_transport.is_connected
