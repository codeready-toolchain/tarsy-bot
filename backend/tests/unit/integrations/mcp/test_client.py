"""
Comprehensive unit tests for MCP Client integration.

Tests MCPClient's server management, tool operations, hook integration,
logging, and error handling with proper mocking of MCP SDK components.
"""

import json
from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, Mock, call, patch

import pytest

from tarsy.config.settings import Settings
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.mcp_config import MCPServerConfig
from tarsy.services.mcp_server_registry import MCPServerRegistry


@pytest.mark.unit
class TestMCPClientInitialization:
    """Test MCP client initialization and configuration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_settings = Mock(spec=Settings)
        self.sample_server_config = MCPServerConfig(
            server_id="test-server",
            server_type="test",
            enabled=True,
            connection_params={
                "command": "test-command",
                "args": ["arg1", "arg2"],
                "env": {"TEST_VAR": "value"}
            },
            instructions="Test instructions"
        )
    
    def test_initialization_with_settings_only(self):
        """Test MCPClient initialization with settings only."""
        client = MCPClient(self.mock_settings)
        
        assert client.settings is self.mock_settings
        assert isinstance(client.mcp_registry, MCPServerRegistry)
        assert client.sessions == {}
        assert isinstance(client.exit_stack, AsyncExitStack)
        assert client._initialized is False
    
    def test_initialization_with_custom_registry(self):
        """Test MCPClient initialization with custom registry."""
        mock_registry = Mock(spec=MCPServerRegistry)
        client = MCPClient(self.mock_settings, mcp_registry=mock_registry)
        
        assert client.settings is self.mock_settings
        assert client.mcp_registry is mock_registry
        assert client.sessions == {}
        assert client._initialized is False
    
    def test_initialization_creates_separate_instances(self):
        """Test that separate MCPClient instances are independent."""
        client1 = MCPClient(self.mock_settings)
        client2 = MCPClient(self.mock_settings)
        
        assert client1 is not client2
        assert client1.mcp_registry is not client2.mcp_registry
        assert client1.sessions is not client2.sessions
        assert client1.exit_stack is not client2.exit_stack


@pytest.mark.unit
class TestMCPClientServerInitialization:
    """Test MCP server initialization and connection management."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_settings = Mock(spec=Settings)
        self.mock_registry = Mock(spec=MCPServerRegistry)
        self.client = MCPClient(self.mock_settings, mcp_registry=self.mock_registry)
        
        self.enabled_server_config = MCPServerConfig(
            server_id="enabled-server",
            server_type="test",
            enabled=True,
            connection_params={
                "command": "test-command",
                "args": ["arg1"]
            }
        )
        
        self.disabled_server_config = MCPServerConfig(
            server_id="disabled-server", 
            server_type="test",
            enabled=False,
            connection_params={"command": "disabled-command"}
        )
    
    @patch('tarsy.integrations.mcp.client.stdio_client')
    @patch('tarsy.integrations.mcp.client.StdioServerParameters')
    @patch('tarsy.integrations.mcp.client.ClientSession')
    async def test_initialize_single_enabled_server(self, mock_client_session, mock_server_params, mock_stdio_client):
        """Test initializing with single enabled server."""
        # Setup mocks
        self.mock_registry.get_all_server_ids.return_value = ["enabled-server"]
        self.mock_registry.get_server_config_safe.return_value = self.enabled_server_config
        
        mock_read_stream = Mock()
        mock_write_stream = Mock()
        mock_stdio_client.return_value.__aenter__.return_value = (mock_read_stream, mock_write_stream)
        
        mock_session = AsyncMock()
        mock_client_session.return_value.__aenter__.return_value = mock_session
        
        # Initialize client
        await self.client.initialize()
        
        # Verify initialization
        assert self.client._initialized is True
        assert "enabled-server" in self.client.sessions
        assert self.client.sessions["enabled-server"] is mock_session
        
        # Verify MCP SDK calls
        mock_server_params.assert_called_once_with(
            command="test-command",
            args=["arg1"],
            env=None
        )
        mock_session.initialize.assert_called_once()
    
    @patch('tarsy.integrations.mcp.client.stdio_client')
    @patch('tarsy.integrations.mcp.client.StdioServerParameters')
    async def test_initialize_skips_disabled_servers(self, mock_server_params, mock_stdio_client):
        """Test initialization skips disabled servers."""
        self.mock_registry.get_all_server_ids.return_value = ["disabled-server"]
        self.mock_registry.get_server_config_safe.return_value = self.disabled_server_config
        
        await self.client.initialize()
        
        assert self.client._initialized is True
        assert self.client.sessions == {}
        mock_server_params.assert_not_called()
        mock_stdio_client.assert_not_called()
    
    @patch('tarsy.integrations.mcp.client.stdio_client')
    @patch('tarsy.integrations.mcp.client.StdioServerParameters')
    async def test_initialize_skips_none_configs(self, mock_server_params, mock_stdio_client):
        """Test initialization skips servers with None config."""
        self.mock_registry.get_all_server_ids.return_value = ["missing-server"]
        self.mock_registry.get_server_config_safe.return_value = None
        
        await self.client.initialize()
        
        assert self.client._initialized is True
        assert self.client.sessions == {}
        mock_server_params.assert_not_called()
        mock_stdio_client.assert_not_called()
    
    @patch('tarsy.integrations.mcp.client.stdio_client')
    @patch('tarsy.integrations.mcp.client.StdioServerParameters')
    @patch('tarsy.integrations.mcp.client.logger')
    async def test_initialize_handles_server_connection_error(self, mock_logger, mock_server_params, mock_stdio_client):
        """Test initialization handles server connection errors gracefully."""
        self.mock_registry.get_all_server_ids.return_value = ["failing-server"]
        self.mock_registry.get_server_config.return_value = self.enabled_server_config
        
        # Make stdio_client raise an exception
        mock_stdio_client.side_effect = Exception("Connection failed")
        
        await self.client.initialize()
        
        assert self.client._initialized is True
        assert self.client.sessions == {}
        mock_logger.error.assert_called_once()
        assert "Failed to initialize MCP server" in mock_logger.error.call_args[0][0]
    
    @patch('tarsy.integrations.mcp.client.stdio_client')
    @patch('tarsy.integrations.mcp.client.StdioServerParameters')
    @patch('tarsy.integrations.mcp.client.ClientSession')
    async def test_initialize_multiple_servers(self, mock_client_session, mock_server_params, mock_stdio_client):
        """Test initializing multiple servers."""
        # Setup multiple server configs
        server1_config = MCPServerConfig(
            server_id="server1",
            server_type="test",
            enabled=True,
            connection_params={"command": "cmd1"}
        )
        server2_config = MCPServerConfig(
            server_id="server2",
            server_type="test", 
            enabled=True,
            connection_params={"command": "cmd2"}
        )
        
        self.mock_registry.get_all_server_ids.return_value = ["server1", "server2"]
        self.mock_registry.get_server_config.side_effect = [server1_config, server2_config]
        
        # Setup mocks for both servers
        mock_stdio_client.return_value.__aenter__.return_value = (Mock(), Mock())
        mock_session1 = AsyncMock()
        mock_session2 = AsyncMock()
        mock_client_session.return_value.__aenter__.side_effect = [mock_session1, mock_session2]
        
        await self.client.initialize()
        
        assert self.client._initialized is True
        assert len(self.client.sessions) == 2
        assert self.client.sessions["server1"] is mock_session1
        assert self.client.sessions["server2"] is mock_session2
    
    async def test_initialize_idempotent(self):
        """Test that initialize() is idempotent."""
        self.mock_registry.get_all_server_ids.return_value = []
        
        # First call
        await self.client.initialize()
        assert self.client._initialized is True
        
        # Second call should not reinitialize
        with patch.object(self.mock_registry, 'get_all_server_ids') as mock_get_ids:
            await self.client.initialize()
            mock_get_ids.assert_not_called()


@pytest.mark.unit
class TestMCPClientListTools:
    """Test MCP client list_tools functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_settings = Mock(spec=Settings)
        self.mock_registry = Mock(spec=MCPServerRegistry)
        self.client = MCPClient(self.mock_settings, mcp_registry=self.mock_registry)
        self.client._initialized = True
        
        # Setup mock sessions
        self.mock_session1 = AsyncMock()
        self.mock_session2 = AsyncMock()
        self.client.sessions = {
            "server1": self.mock_session1,
            "server2": self.mock_session2
        }
        
        # Mock tool data
        self.mock_tool1 = Mock()
        self.mock_tool1.name = "tool1"
        self.mock_tool1.description = "Tool 1 description"
        self.mock_tool1.inputSchema = {"type": "object", "properties": {}}
        
        self.mock_tool2 = Mock()
        self.mock_tool2.name = "tool2"
        self.mock_tool2.description = None  # Test None description
        self.mock_tool2.inputSchema = {"type": "string"}
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_list_tools_all_servers_success(self, mock_hook_context):
        """Test listing tools from all servers successfully."""
        # Setup hook context mock
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="req-123")  # Use Mock instead of AsyncMock for sync method
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup tools response
        mock_tools_result1 = Mock()
        mock_tools_result1.tools = [self.mock_tool1]
        self.mock_session1.list_tools.return_value = mock_tools_result1
        
        mock_tools_result2 = Mock()
        mock_tools_result2.tools = [self.mock_tool2]
        self.mock_session2.list_tools.return_value = mock_tools_result2
        
        with patch.object(self.client, '_log_mcp_list_tools_request') as mock_log_req, \
             patch.object(self.client, '_log_mcp_list_tools_response') as mock_log_resp:
            
            result = await self.client.list_tools()
        
        # Verify result structure
        assert "server1" in result
        assert "server2" in result
        assert len(result["server1"]) == 1
        assert len(result["server2"]) == 1
        
        # Verify tool1 conversion
        tool1_dict = result["server1"][0]
        assert tool1_dict["name"] == "tool1"
        assert tool1_dict["description"] == "Tool 1 description"
        assert tool1_dict["inputSchema"] == {"type": "object", "properties": {}}
        
        # Verify tool2 conversion (None description becomes empty string)
        tool2_dict = result["server2"][0]
        assert tool2_dict["name"] == "tool2"
        assert tool2_dict["description"] == ""
        assert tool2_dict["inputSchema"] == {"type": "string"}
        
        # Verify logging
        mock_log_req.assert_called_once_with(None, "req-123")
        assert mock_log_resp.call_count == 2
        
        # Verify hook context completion
        mock_ctx.complete_success.assert_called_once_with(result)
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_list_tools_specific_server_success(self, mock_hook_context):
        """Test listing tools from specific server."""
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="req-456")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup tools response for server1 only
        mock_tools_result = Mock()
        mock_tools_result.tools = [self.mock_tool1, self.mock_tool2]
        self.mock_session1.list_tools.return_value = mock_tools_result
        
        with patch.object(self.client, '_log_mcp_list_tools_request') as mock_log_req, \
             patch.object(self.client, '_log_mcp_list_tools_response') as mock_log_resp:
            
            result = await self.client.list_tools(server_name="server1")
        
        # Verify only server1 is in result
        assert "server1" in result
        assert "server2" not in result
        assert len(result["server1"]) == 2
        
        # Verify session calls
        self.mock_session1.list_tools.assert_called_once()
        self.mock_session2.list_tools.assert_not_called()
        
        # Verify logging
        mock_log_req.assert_called_once_with("server1", "req-456")
        mock_log_resp.assert_called_once()
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_list_tools_nonexistent_server(self, mock_hook_context):
        """Test listing tools from nonexistent server."""
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="req-789")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        with patch.object(self.client, '_log_mcp_list_tools_request') as mock_log_req:
            result = await self.client.list_tools(server_name="nonexistent")
        
        # Should return empty result for nonexistent server
        assert result == {}
        
        # No sessions should be called
        self.mock_session1.list_tools.assert_not_called()
        self.mock_session2.list_tools.assert_not_called()
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    @patch('tarsy.integrations.mcp.client.logger')
    async def test_list_tools_server_error(self, mock_logger, mock_hook_context):
        """Test handling server errors during tool listing."""
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="req-error")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Make server1 raise an exception
        self.mock_session1.list_tools.side_effect = Exception("Server error")
        
        # Server2 works normally
        mock_tools_result = Mock()
        mock_tools_result.tools = [self.mock_tool2]
        self.mock_session2.list_tools.return_value = mock_tools_result
        
        with patch.object(self.client, '_log_mcp_list_tools_error') as mock_log_error:
            result = await self.client.list_tools()
        
        # Should return empty list for failed server, normal results for working server
        assert result["server1"] == []
        assert len(result["server2"]) == 1
        
        # Verify error logging
        mock_logger.error.assert_called_once()
        mock_log_error.assert_called_once_with("server1", "Server error", "req-error")
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_list_tools_with_kwargs(self, mock_hook_context):
        """Test list_tools passes kwargs to HookContext."""
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="req-kwargs")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Mock empty sessions for quick test
        self.client.sessions = {}
        
        await self.client.list_tools(
            server_name="test-server", 
            session_id="session-123",
            custom_param="custom_value"
        )
        
        # Verify HookContext was called with correct parameters
        mock_hook_context.assert_called_once_with(
            service_type="mcp",
            method_name="list_tools",
            session_id="session-123",
            server_name="test-server",
            custom_param="custom_value"
        )
    
    @patch.object(MCPClient, 'initialize')
    async def test_list_tools_auto_initialize(self, mock_initialize):
        """Test list_tools auto-initializes if not initialized."""
        self.client._initialized = False
        self.client.sessions = {}  # Empty to avoid actual tool listing
        
        with patch('tarsy.integrations.mcp.client.HookContext'):
            await self.client.list_tools()
        
        mock_initialize.assert_called_once()


@pytest.mark.unit
class TestMCPClientCallTool:
    """Test MCP client call_tool functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_settings = Mock(spec=Settings)
        self.mock_registry = Mock(spec=MCPServerRegistry)
        
        # Mock the registry's get_server_config_safe method to return None
        # This disables data masking for these tests
        self.mock_registry.get_server_config_safe.return_value = None
        
        self.client = MCPClient(self.mock_settings, mcp_registry=self.mock_registry)
        self.client._initialized = True
        
        # Setup mock session
        self.mock_session = AsyncMock()
        self.client.sessions = {"test-server": self.mock_session}
        
        self.test_params = {"param1": "value1", "param2": 42}
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_call_tool_success_with_text_content(self, mock_hook_context):
        """Test successful tool call with text content result."""
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="req-call-123")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup mock result with content.text
        mock_result = Mock()
        mock_content_item = Mock()
        mock_content_item.text = "Tool execution result"
        mock_result.content = [mock_content_item]
        self.mock_session.call_tool.return_value = mock_result
        
        with patch.object(self.client, '_log_mcp_request') as mock_log_req, \
             patch.object(self.client, '_log_mcp_response') as mock_log_resp:
            
            result = await self.client.call_tool("test-server", "test-tool", self.test_params, "test-session-123")
        
        # Verify result
        assert result == {"result": "Tool execution result"}
        
        # Verify session call
        self.mock_session.call_tool.assert_called_once_with("test-tool", self.test_params)
        
        # Verify logging
        mock_log_req.assert_called_once_with("test-server", "test-tool", self.test_params, "req-call-123")
        mock_log_resp.assert_called_once_with("test-server", "test-tool", result, "req-call-123")
        
        # Verify hook context completion
        mock_ctx.complete_success.assert_called_once_with(result)
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_call_tool_success_with_multiple_text_items(self, mock_hook_context):
        """Test tool call with multiple text content items."""
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="req-multi")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup mock result with multiple text items
        mock_result = Mock()
        mock_item1 = Mock()
        mock_item1.text = "First part"
        mock_item2 = Mock()
        mock_item2.text = "Second part"
        mock_result.content = [mock_item1, mock_item2]
        self.mock_session.call_tool.return_value = mock_result
        
        result = await self.client.call_tool("test-server", "test-tool", self.test_params, "test-session-123")
        
        assert result == {"result": "First part\nSecond part"}
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_call_tool_success_with_type_text_items(self, mock_hook_context):
        """Test tool call with content items having type='text'."""
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="req-type")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup mock result with type='text' items
        mock_result = Mock()
        
        # Create a simple object that behaves like a text item
        class MockTextItem:
            def __init__(self):
                self.type = 'text'
            def __str__(self):
                return "Text content from str"
        
        mock_item = MockTextItem()
        mock_result.content = [mock_item]
        self.mock_session.call_tool.return_value = mock_result
        
        result = await self.client.call_tool("test-server", "test-tool", self.test_params, "test-session-123")
        
        assert result == {"result": "Text content from str"}
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_call_tool_success_with_string_content(self, mock_hook_context):
        """Test tool call with string content (not a list)."""
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="req-string")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup mock result with string content
        mock_result = Mock()
        mock_result.content = "Simple string result"
        self.mock_session.call_tool.return_value = mock_result
        
        result = await self.client.call_tool("test-server", "test-tool", self.test_params, "test-session-123")
        
        assert result == {"result": "Simple string result"}
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_call_tool_success_without_content_attribute(self, mock_hook_context):
        """Test tool call with result that has no content attribute."""
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="req-no-content")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup mock result without content attribute
        class MockResultWithoutContent:
            def __str__(self):
                return "String representation"
        
        mock_result = MockResultWithoutContent()
        self.mock_session.call_tool.return_value = mock_result
        
        result = await self.client.call_tool("test-server", "test-tool", self.test_params, "test-session-123")
        
        assert result == {"result": "String representation"}
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_call_tool_server_not_found(self, mock_hook_context):
        """Test call_tool raises exception for nonexistent server."""
        mock_ctx = AsyncMock()
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        with pytest.raises(Exception) as exc_info:
            await self.client.call_tool("nonexistent-server", "test-tool", self.test_params, "test-session-error")
        
        assert "MCP server not found: nonexistent-server" in str(exc_info.value)
        
        # Test tool execution failure
        self.mock_session.call_tool.side_effect = Exception("Tool execution failed")
        mock_ctx.get_request_id = Mock(return_value="req-error")
        with patch.object(self.client, '_log_mcp_error') as mock_log_error:
            with pytest.raises(Exception) as exc_info:
                await self.client.call_tool("test-server", "test-tool", self.test_params, "test-session-123")
        
        # Verify error message format
        assert "Failed to call tool test-tool on test-server: Tool execution failed" in str(exc_info.value)
        
        # Verify error logging
        mock_log_error.assert_called_once_with("test-server", "test-tool", "Tool execution failed", "req-error")
        
        # Hook context should not be completed with success
        mock_ctx.complete_success.assert_not_called()
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_call_tool_with_kwargs(self, mock_hook_context):
        """Test call_tool passes kwargs to HookContext."""
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="req-kwargs")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup simple successful response
        mock_result = Mock()
        mock_result.content = "Success"
        self.mock_session.call_tool.return_value = mock_result
        
        await self.client.call_tool(
            "test-server", 
            "test-tool", 
            self.test_params,
            session_id="session-456",
            custom_data="test_data"
        )
        
        # Verify HookContext received all parameters
        mock_hook_context.assert_called_once_with(
            service_type="mcp",
            method_name="call_tool",
            session_id="session-456",
            server_name="test-server",
            tool_name="test-tool",
            tool_arguments=self.test_params,
            custom_data="test_data"
        )
    
    @patch.object(MCPClient, 'initialize')
    async def test_call_tool_auto_initialize(self, mock_initialize):
        """Test call_tool auto-initializes if not initialized."""
        self.client._initialized = False
        # Clear sessions so server won't be found
        self.client.sessions = {}
        
        # Setup for quick failure after initialization
        with patch('tarsy.integrations.mcp.client.HookContext'):
            with pytest.raises(Exception, match="MCP server not found"):
                await self.client.call_tool("test-server", "test-tool", self.test_params, "test-session-123")
        
        mock_initialize.assert_called_once()


@pytest.mark.unit
class TestMCPClientLogging:
    """Test MCP client logging functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_settings = Mock(spec=Settings)
        self.client = MCPClient(self.mock_settings)
        self.test_params = {"key": "value", "nested": {"data": 123}}
        self.test_response = {"result": "Success response"}
        self.test_tools = [
            {"name": "tool1", "description": "First tool", "inputSchema": {"type": "object"}},
            {"name": "tool2", "description": "Second tool", "inputSchema": {"type": "string"}}
        ]
    
    @patch('tarsy.integrations.mcp.client.mcp_comm_logger')
    def test_log_mcp_request(self, mock_logger):
        """Test _log_mcp_request logs correctly."""
        self.client._log_mcp_request("test-server", "test-tool", self.test_params, "req-123")
        
        # Verify logging calls
        expected_calls = [
            call("=== MCP REQUEST [test-server] [ID: req-123] ==="),
            call("Request ID: req-123"),
            call("Server: test-server"),
            call("Tool: test-tool"),
            call(f"Parameters: {json.dumps(self.test_params, indent=2, default=str)}"),
            call("=== END REQUEST [ID: req-123] ===")
        ]
        
        mock_logger.info.assert_has_calls(expected_calls)
        assert mock_logger.info.call_count == 6
    
    @patch('tarsy.integrations.mcp.client.mcp_comm_logger')
    def test_log_mcp_response(self, mock_logger):
        """Test _log_mcp_response logs correctly."""
        self.client._log_mcp_response("test-server", "test-tool", self.test_response, "req-456")
        
        # Verify logging calls
        expected_calls = [
            call("=== MCP RESPONSE [test-server] [ID: req-456] ==="),
            call("Request ID: req-456"),
            call("Server: test-server"),
            call("Tool: test-tool"),
            call("Response length: 16 characters"),  # len("Success response") = 16
            call("--- RESPONSE CONTENT ---"),
            call("Success response"),
            call("=== END RESPONSE [ID: req-456] ===")
        ]
        
        mock_logger.info.assert_has_calls(expected_calls)
        assert mock_logger.info.call_count == 8
    
    @patch('tarsy.integrations.mcp.client.mcp_comm_logger')
    def test_log_mcp_error(self, mock_logger):
        """Test _log_mcp_error logs correctly."""
        self.client._log_mcp_error("test-server", "test-tool", "Connection timeout", "req-error")
        
        # Verify logging calls
        expected_calls = [
            call("=== MCP ERROR [test-server] [ID: req-error] ==="),
            call("Request ID: req-error"),
            call("Server: test-server"),
            call("Tool: test-tool"),
            call("Error: Connection timeout"),
            call("=== END ERROR [ID: req-error] ===")
        ]
        
        mock_logger.error.assert_has_calls(expected_calls)
        assert mock_logger.error.call_count == 6
    
    @patch('tarsy.integrations.mcp.client.mcp_comm_logger')
    def test_log_mcp_list_tools_request_specific_server(self, mock_logger):
        """Test _log_mcp_list_tools_request for specific server."""
        self.client._log_mcp_list_tools_request("specific-server", "req-list")
        
        expected_calls = [
            call("=== MCP LIST TOOLS REQUEST [specific-server] [ID: req-list] ==="),
            call("Request ID: req-list"),
            call("Target: specific-server"),
            call("=== END LIST TOOLS REQUEST [ID: req-list] ===")
        ]
        
        mock_logger.info.assert_has_calls(expected_calls)
        assert mock_logger.info.call_count == 4
    
    @patch('tarsy.integrations.mcp.client.mcp_comm_logger')
    def test_log_mcp_list_tools_request_all_servers(self, mock_logger):
        """Test _log_mcp_list_tools_request for all servers."""
        self.client._log_mcp_list_tools_request(None, "req-all")
        
        expected_calls = [
            call("=== MCP LIST TOOLS REQUEST [ALL_SERVERS] [ID: req-all] ==="),
            call("Request ID: req-all"),
            call("Target: ALL_SERVERS"),
            call("=== END LIST TOOLS REQUEST [ID: req-all] ===")
        ]
        
        mock_logger.info.assert_has_calls(expected_calls)
    
    @patch('tarsy.integrations.mcp.client.mcp_comm_logger')
    def test_log_mcp_list_tools_response(self, mock_logger):
        """Test _log_mcp_list_tools_response logs tools correctly."""
        self.client._log_mcp_list_tools_response("tools-server", self.test_tools, "req-tools")
        
        # Verify header and footer calls
        mock_logger.info.assert_any_call("=== MCP LIST TOOLS RESPONSE [tools-server] [ID: req-tools] ===")
        mock_logger.info.assert_any_call("Request ID: req-tools")
        mock_logger.info.assert_any_call("Server: tools-server")
        mock_logger.info.assert_any_call("Tools count: 2")
        mock_logger.info.assert_any_call("--- TOOLS ---")
        
        # Verify tool details
        mock_logger.info.assert_any_call("Tool 1: tool1")
        mock_logger.info.assert_any_call("  Description: First tool")
        mock_logger.info.assert_any_call("Tool 2: tool2")
        mock_logger.info.assert_any_call("  Description: Second tool")
        
        mock_logger.info.assert_any_call("=== END LIST TOOLS RESPONSE [ID: req-tools] ===")
    
    @patch('tarsy.integrations.mcp.client.mcp_comm_logger')
    def test_log_mcp_list_tools_error(self, mock_logger):
        """Test _log_mcp_list_tools_error logs correctly."""
        self.client._log_mcp_list_tools_error("error-server", "Network unreachable", "req-error")
        
        expected_calls = [
            call("=== MCP LIST TOOLS ERROR [error-server] [ID: req-error] ==="),
            call("Request ID: req-error"),
            call("Server: error-server"),
            call("Error: Network unreachable"),
            call("=== END LIST TOOLS ERROR [ID: req-error] ===")
        ]
        
        mock_logger.error.assert_has_calls(expected_calls)
        assert mock_logger.error.call_count == 5


@pytest.mark.unit
class TestMCPClientResourceManagement:
    """Test MCP client resource management and cleanup."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_settings = Mock(spec=Settings)
        self.client = MCPClient(self.mock_settings)
    
    async def test_close_cleans_up_resources(self):
        """Test close() properly cleans up all resources."""
        # Setup some mock sessions
        mock_session1 = AsyncMock()
        mock_session2 = AsyncMock()
        self.client.sessions = {
            "server1": mock_session1,
            "server2": mock_session2
        }
        self.client._initialized = True
        
        # Mock the exit stack
        mock_exit_stack = AsyncMock()
        self.client.exit_stack = mock_exit_stack
        
        await self.client.close()
        
        # Verify cleanup
        mock_exit_stack.aclose.assert_called_once()
        assert self.client.sessions == {}
        assert self.client._initialized is False
    
    async def test_close_handles_exit_stack_error(self):
        """Test close() handles exit stack errors gracefully."""
        # Setup state
        self.client.sessions = {"server1": AsyncMock()}
        self.client._initialized = True
        
        # Make exit stack raise an exception
        mock_exit_stack = AsyncMock()
        mock_exit_stack.aclose.side_effect = Exception("Cleanup failed")
        self.client.exit_stack = mock_exit_stack
        
        # close() should still raise the exception but ensure cleanup happens
        with pytest.raises(Exception, match="Cleanup failed"):
            await self.client.close()
        
        # Sessions should still be cleared
        assert self.client.sessions == {}
        assert self.client._initialized is False
    
    async def test_close_idempotent(self):
        """Test close() can be called multiple times safely."""
        mock_exit_stack = AsyncMock()
        self.client.exit_stack = mock_exit_stack
        
        # First close
        await self.client.close()
        
        # Second close should not cause issues
        await self.client.close()
        
        # Exit stack should be called twice
        assert mock_exit_stack.aclose.call_count == 2


@pytest.mark.unit
class TestMCPClientIntegrationScenarios:
    """Test MCP client integration scenarios and edge cases."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_settings = Mock(spec=Settings)
        self.mock_registry = Mock(spec=MCPServerRegistry)
        
        # Mock the registry's get_server_config_safe method to return None by default
        # This disables data masking for these tests (individual tests can override)
        self.mock_registry.get_server_config_safe.return_value = None
        
        self.client = MCPClient(self.mock_settings, mcp_registry=self.mock_registry)
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_workflow_initialize_list_call_close(self, mock_hook_context):
        """Test complete workflow from initialization to cleanup."""
        # Setup hook context
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="workflow-123")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup server config
        server_config = MCPServerConfig(
            server_id="workflow-server",
            server_type="test",
            enabled=True,
            connection_params={"command": "test-cmd"}
        )
        self.mock_registry.get_all_server_ids.return_value = ["workflow-server"]
        self.mock_registry.get_server_config_safe.return_value = server_config
        
        # Mock MCP SDK components
        with patch('tarsy.integrations.mcp.client.stdio_client') as mock_stdio, \
             patch('tarsy.integrations.mcp.client.ClientSession') as mock_session_cls:
            
            # Setup stdio client
            mock_stdio.return_value.__aenter__.return_value = (Mock(), Mock())
            
            # Setup session
            mock_session = AsyncMock()
            mock_session_cls.return_value.__aenter__.return_value = mock_session
            
            # Setup tool listing
            mock_tool = Mock()
            mock_tool.name = "test-tool"
            mock_tool.description = "Test tool"
            mock_tool.inputSchema = {"type": "object"}
            mock_tools_result = Mock()
            mock_tools_result.tools = [mock_tool]
            mock_session.list_tools.return_value = mock_tools_result
            
            # Setup tool calling
            mock_call_result = Mock()
            mock_call_result.content = "Tool result"
            mock_session.call_tool.return_value = mock_call_result
            
            # Execute workflow
            # 1. Initialize
            await self.client.initialize()
            assert self.client._initialized is True
            assert "workflow-server" in self.client.sessions
            
            # 2. List tools
            tools = await self.client.list_tools()
            assert "workflow-server" in tools
            assert len(tools["workflow-server"]) == 1
            assert tools["workflow-server"][0]["name"] == "test-tool"
            
            # 3. Call tool
            result = await self.client.call_tool("workflow-server", "test-tool", {"param": "value"}, "test-session-workflow")
            assert result == {"result": "Tool result"}
            
            # 4. Close
            await self.client.close()
            assert self.client.sessions == {}
            assert self.client._initialized is False
    
    async def test_multiple_clients_independence(self):
        """Test that multiple MCPClient instances are independent."""
        client1 = MCPClient(self.mock_settings)
        client2 = MCPClient(self.mock_settings)
        
        # Setup different states
        client1._initialized = True
        client1.sessions = {"server1": AsyncMock()}
        
        client2._initialized = False
        client2.sessions = {}
        
        # Verify independence
        assert client1._initialized != client2._initialized
        assert client1.sessions != client2.sessions
        assert client1.exit_stack is not client2.exit_stack
        
        # Operations on one shouldn't affect the other
        await client1.close()
        assert client1.sessions == {}
        assert client2.sessions == {}  # Was already empty
        assert client1._initialized is False
        assert client2._initialized is False  # Was already False
    
    @patch('tarsy.integrations.mcp.client.HookContext')
    async def test_concurrent_operations(self, mock_hook_context):
        """Test concurrent list_tools and call_tool operations."""
        # Setup initialized client
        self.client._initialized = True
        mock_session = AsyncMock()
        self.client.sessions = {"concurrent-server": mock_session}
        
        # Setup hook context
        mock_ctx = AsyncMock()
        mock_ctx.get_request_id = Mock(return_value="concurrent-123")
        mock_hook_context.return_value.__aenter__.return_value = mock_ctx
        
        # Setup responses
        mock_tools_result = Mock()
        mock_tools_result.tools = []
        mock_session.list_tools.return_value = mock_tools_result
        
        mock_call_result = Mock()
        mock_call_result.content = "Concurrent result"
        mock_session.call_tool.return_value = mock_call_result
        
        # Execute concurrent operations
        import asyncio
        
        tools_task = asyncio.create_task(self.client.list_tools("concurrent-server"))
        call_task = asyncio.create_task(
            self.client.call_tool("concurrent-server", "test-tool", {"param": "value"}, "test-session-concurrent")
        )
        
        tools_result, call_result = await asyncio.gather(tools_task, call_task)
        
        # Verify both operations completed successfully
        assert "concurrent-server" in tools_result
        assert call_result == {"result": "Concurrent result"}
        
        # Verify session was called for both operations
        mock_session.list_tools.assert_called_once()
        mock_session.call_tool.assert_called_once() 