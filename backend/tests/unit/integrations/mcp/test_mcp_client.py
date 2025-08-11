"""
Unit tests for MCP client.

Tests the MCP client that handles communication with MCP servers
using the official MCP SDK and the new typed hook system.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from contextlib import AsyncExitStack

from tarsy.integrations.mcp.client import MCPClient
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.services.data_masking_service import DataMaskingService
from tarsy.config.settings import Settings


@pytest.mark.unit
class TestMCPClientInitialization:
    """Test MCP client initialization."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings."""
        settings = Mock(spec=Settings)
        return settings
    
    @pytest.fixture
    def mock_registry(self):
        """Mock MCP server registry."""
        registry = Mock(spec=MCPServerRegistry)
        registry.get_all_server_ids.return_value = ["test-server"]
        registry.get_server_config_safe.return_value = Mock(
            enabled=True,
            connection_params={"command": "test", "args": []}
        )
        return registry
    
    def test_initialization_success(self, mock_settings, mock_registry):
        """Test successful client initialization."""
        client = MCPClient(mock_settings, mock_registry)
        
        assert client.settings == mock_settings
        assert client.mcp_registry == mock_registry
        assert isinstance(client.data_masking_service, DataMaskingService)
        assert client.sessions == {}
        assert isinstance(client.exit_stack, AsyncExitStack)
        assert client._initialized == False
    
    def test_initialization_without_registry(self, mock_settings):
        """Test initialization without registry creates default."""
        client = MCPClient(mock_settings)
        
        assert client.settings == mock_settings
        assert isinstance(client.mcp_registry, MCPServerRegistry)
        assert client.data_masking_service is None
    
    @pytest.mark.asyncio
    async def test_initialize_servers_success(self, mock_settings, mock_registry):
        """Test successful server initialization."""
        client = MCPClient(mock_settings, mock_registry)
        
        with patch('tarsy.integrations.mcp.client.stdio_client') as mock_stdio, \
             patch('tarsy.integrations.mcp.client.StdioServerParameters') as mock_params, \
             patch('tarsy.integrations.mcp.client.ClientSession') as mock_client_session:
            
            mock_session = AsyncMock()
            # stdio_client is expected to return a tuple of (read_stream, write_stream)
            mock_stdio.return_value.__aenter__.return_value = (AsyncMock(), AsyncMock())
            # ClientSession context manager returns the session
            mock_client_session.return_value.__aenter__.return_value = mock_session
            
            await client.initialize()
            
            assert client._initialized == True
            assert "test-server" in client.sessions
            mock_registry.get_all_server_ids.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_initialize_skips_disabled_servers(self, mock_settings, mock_registry):
        """Test initialization skips disabled servers."""
        mock_registry.get_server_config_safe.return_value = Mock(enabled=False)
        client = MCPClient(mock_settings, mock_registry)
        
        await client.initialize()
        
        assert client._initialized == True
        assert len(client.sessions) == 0
    
    @pytest.mark.asyncio
    async def test_initialize_handles_server_error(self, mock_settings, mock_registry):
        """Test initialization handles individual server errors."""
        client = MCPClient(mock_settings, mock_registry)
        
        with patch('tarsy.integrations.mcp.client.stdio_client') as mock_stdio:
            mock_stdio.side_effect = Exception("Server connection failed")
            
            # Should not raise exception, just log error
            await client.initialize()
            
            assert client._initialized == True
            assert len(client.sessions) == 0


@pytest.mark.unit
class TestMCPClientToolListing:
    """Test MCP client tool listing functionality."""
    
    @pytest.fixture
    def mock_session(self):
        """Mock MCP session."""
        session = AsyncMock()
        mock_tool = Mock()
        mock_tool.name = "test_tool"
        mock_tool.description = "Test tool description"
        mock_tool.inputSchema = {"type": "object", "properties": {}}
        
        mock_result = Mock()
        mock_result.tools = [mock_tool]
        session.list_tools.return_value = mock_result
        return session
    
    @pytest.fixture
    def client_with_session(self, mock_session):
        """Create client with mocked session."""
        client = MCPClient(Mock(), Mock())
        client.sessions = {"test-server": mock_session}
        client._initialized = True
        return client
    
    @pytest.mark.asyncio
    async def test_list_tools_specific_server_success(self, client_with_session, mock_session):
        """Test successful tool listing for specific server."""
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "list-req-123"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client_with_session.list_tools("test-session", "test-server")
            
            assert "test-server" in result
            assert len(result["test-server"]) == 1
            
            tool = result["test-server"][0]
            assert tool["name"] == "test_tool"
            assert tool["description"] == "Test tool description"
            assert "inputSchema" in tool
            
            mock_session.list_tools.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_tools_all_servers_success(self, client_with_session, mock_session):
        """Test successful tool listing for all servers."""
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "list-all-req-456"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client_with_session.list_tools("test-session")
            
            assert "test-server" in result
            assert len(result["test-server"]) == 1
            mock_session.list_tools.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_tools_nonexistent_server(self, client_with_session):
        """Test tool listing for nonexistent server."""
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client_with_session.list_tools("test-session", "nonexistent-server")
            
            assert result == {}
    
    @pytest.mark.asyncio
    async def test_list_tools_server_error(self, client_with_session, mock_session):
        """Test tool listing handles server errors."""
        mock_session.list_tools.side_effect = Exception("Server error")
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client_with_session.list_tools("test-session", "test-server")
            
            assert "test-server" in result
            assert result["test-server"] == []
    
    @pytest.mark.asyncio
    async def test_list_tools_auto_initialize(self):
        """Test tool listing auto-initializes if needed."""
        client = MCPClient(Mock(), Mock())
        client._initialized = False
        
        with patch.object(client, 'initialize') as mock_init, \
             patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            await client.list_tools("test-session")
            
            mock_init.assert_called_once()


@pytest.mark.unit
class TestMCPClientToolCalling:
    """Test MCP client tool calling functionality."""
    
    @pytest.fixture
    def mock_session(self):
        """Mock MCP session."""
        session = AsyncMock()
        mock_result = Mock()
        mock_result.content = [Mock(type="text", text="Tool execution result")]
        session.call_tool.return_value = mock_result
        return session
    
    @pytest.fixture
    def client_with_session(self, mock_session):
        """Create client with mocked session."""
        registry = Mock()
        registry.get_server_config_safe.return_value = Mock(
            data_masking=Mock(enabled=False)
        )
        
        client = MCPClient(Mock(), registry)
        client.sessions = {"test-server": mock_session}
        client._initialized = True
        return client
    
    @pytest.mark.asyncio
    async def test_call_tool_success(self, client_with_session, mock_session):
        """Test successful tool calling."""
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "call-req-789"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client_with_session.call_tool(
                "test-server", 
                "test_tool", 
                {"param": "value"}, 
                "test-session"
            )
            
            assert "Tool execution result" in str(result)
            mock_session.call_tool.assert_called_once_with("test_tool", {"param": "value"})
    
    @pytest.mark.asyncio
    async def test_call_tool_with_masking(self):
        """Test tool calling with data masking enabled."""
        registry = Mock()
        registry.get_server_config_safe.return_value = Mock(
            data_masking=Mock(enabled=True)
        )
        
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.content = [Mock(type="text", text="Result with api_key: sk_123456789")]
        mock_session.call_tool.return_value = mock_result
        
        client = MCPClient(Mock(), registry)
        client.sessions = {"test-server": mock_session}
        client._initialized = True
        
        # Mock data masking service
        mock_masking = Mock()
        mock_masking.mask_response.return_value = {"result": "Result with api_key: ***MASKED_API_KEY***"}
        client.data_masking_service = mock_masking
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client.call_tool(
                "test-server",
                "test_tool", 
                {"param": "value"},
                "test-session"
            )
            
            assert "***MASKED_API_KEY***" in str(result)
            mock_masking.mask_response.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_call_tool_server_not_found(self, client_with_session):
        """Test tool calling with nonexistent server."""
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with pytest.raises(Exception, match="MCP server not found: nonexistent-server"):
                await client_with_session.call_tool(
                    "nonexistent-server",
                    "test_tool",
                    {},
                    "test-session"
                )
    
    @pytest.mark.asyncio
    async def test_call_tool_handles_server_error(self, client_with_session, mock_session):
        """Test tool calling handles server errors."""
        mock_session.call_tool.side_effect = Exception("Tool execution failed")
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with pytest.raises(Exception, match="Tool execution failed"):
                await client_with_session.call_tool(
                    "test-server",
                    "test_tool",
                    {},
                    "test-session"
                )
    
    @pytest.mark.asyncio
    async def test_call_tool_auto_initialize(self):
        """Test tool calling auto-initializes if needed."""
        client = MCPClient(Mock(), Mock())
        client._initialized = False
        
        with patch.object(client, 'initialize') as mock_init, \
             patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with pytest.raises(Exception):  # Will fail after init due to no sessions
                await client.call_tool("test-server", "tool", {}, "session")
            
            mock_init.assert_called_once()




@pytest.mark.unit
class TestMCPClientCleanup:
    """Test MCP client cleanup functionality."""
    
    @pytest.mark.asyncio
    async def test_close_cleanup(self):
        """Test client cleanup on close."""
        client = MCPClient(Mock(), Mock())
        client.exit_stack = AsyncMock()
        
        await client.close()
        
        client.exit_stack.aclose.assert_called_once()


@pytest.mark.integration
class TestMCPClientIntegration:
    """Integration tests for MCP client."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self):
        """Test complete MCP client workflow."""
        # Setup mocks for complete workflow
        mock_registry = Mock()
        mock_registry.get_all_server_ids.return_value = ["integration-server"]
        mock_registry.get_server_config_safe.return_value = Mock(
            enabled=True,
            connection_params={"command": "test", "args": []},
            data_masking=Mock(enabled=False)
        )
        
        client = MCPClient(Mock(), mock_registry)
        
        with patch('tarsy.integrations.mcp.client.stdio_client') as mock_stdio, \
             patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_list_context, \
             patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_call_context, \
             patch('tarsy.integrations.mcp.client.ClientSession') as mock_client_session:
            
            # Setup session mock
            mock_session = AsyncMock()
            # stdio_client returns (read_stream, write_stream)
            mock_stdio.return_value.__aenter__.return_value = (AsyncMock(), AsyncMock())
            # ClientSession context manager returns the session
            mock_client_session.return_value.__aenter__.return_value = mock_session
            
            # Setup tool listing
            mock_tool = Mock()
            mock_tool.name = "integration_tool"
            mock_tool.description = "Integration test tool"
            mock_tool.inputSchema = {"type": "object"}
            
            mock_list_result = Mock()
            mock_list_result.tools = [mock_tool]
            mock_session.list_tools.return_value = mock_list_result
            
            # Setup tool calling
            mock_call_result = Mock()
            mock_call_result.content = [Mock(type="text", text="Integration result")]
            mock_session.call_tool.return_value = mock_call_result
            
            # Setup contexts
            mock_list_ctx = AsyncMock()
            mock_list_ctx.get_request_id.return_value = "integration-list-req"
            mock_list_context.return_value.__aenter__.return_value = mock_list_ctx
            
            mock_call_ctx = AsyncMock()
            mock_call_ctx.get_request_id.return_value = "integration-call-req"
            mock_call_context.return_value.__aenter__.return_value = mock_call_ctx
            
            # Execute complete workflow
            await client.initialize()
            assert client._initialized
            
            tools = await client.list_tools("integration-session", "integration-server")
            assert "integration-server" in tools
            assert len(tools["integration-server"]) == 1
            assert tools["integration-server"][0]["name"] == "integration_tool"
            
            result = await client.call_tool(
                "integration-server",
                "integration_tool",
                {"test": "param"},
                "integration-session"
            )
            assert "Integration result" in str(result)
            
            await client.close()
            
            # Verify all components were used
            mock_registry.get_all_server_ids.assert_called()
            mock_session.list_tools.assert_called_once()
            mock_session.call_tool.assert_called_once_with("integration_tool", {"test": "param"})