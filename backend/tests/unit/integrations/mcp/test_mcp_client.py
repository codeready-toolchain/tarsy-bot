"""
Unit tests for MCP client.

Tests the MCP client that handles communication with MCP servers
using the official MCP SDK and the new typed hook system.
"""

from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import Tool

from tarsy.config.settings import Settings
from tarsy.integrations.mcp.client import MCPClient
from tarsy.integrations.mcp.summarizer import MCPResultSummarizer
from tarsy.models.constants import StreamingEventType
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.services.data_masking_service import DataMaskingService
from tarsy.services.mcp_server_registry import MCPServerRegistry


@pytest.mark.unit
class TestMCPClientInitialization:
    """Test MCP client initialization."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings."""
        settings = Mock(spec=Settings)
        settings.agent_config_path = None  # No agent config for unit tests
        return settings
    
    @pytest.fixture
    def mock_registry(self):
        """Mock MCP server registry."""
        from tarsy.models.mcp_transport_config import TRANSPORT_STDIO
        
        registry = Mock(spec=MCPServerRegistry)
        registry.get_all_server_ids.return_value = ["test-server"]
        
        # Create mock transport config with proper type
        mock_transport = Mock()
        mock_transport.type = TRANSPORT_STDIO
        mock_transport.command = "test"
        mock_transport.args = []
        mock_transport.env = {}
        
        registry.get_server_config_safe.return_value = Mock(
            enabled=True,
            transport=mock_transport
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
        assert isinstance(client.data_masking_service, DataMaskingService)
    
    @pytest.mark.asyncio
    async def test_initialize_servers_success(self, mock_settings, mock_registry):
        """Test successful server initialization."""
        client = MCPClient(mock_settings, mock_registry)
        
        with patch('tarsy.integrations.mcp.client.MCPTransportFactory') as mock_factory:
            # Mock transport and session
            mock_transport = AsyncMock()
            mock_session = AsyncMock()
            mock_transport.create_session.return_value = mock_session
            mock_factory.create_transport.return_value = mock_transport
            
            await client.initialize()
            
            assert client._initialized == True
            assert "test-server" in client.sessions
            assert "test-server" in client.transports
            mock_registry.get_all_server_ids.assert_called_once()
            mock_factory.create_transport.assert_called_once()
            mock_transport.create_session.assert_called_once()
    
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
        
        with patch('tarsy.integrations.mcp.client.MCPTransportFactory') as mock_factory:
            mock_factory.create_transport.side_effect = Exception("Server connection failed")
            
            # Should not raise exception, just log error
            await client.initialize()
            
            assert client._initialized == True
            assert len(client.sessions) == 0
            assert len(client.transports) == 0


@pytest.mark.unit
class TestMCPClientToolListing:
    """Test MCP client tool listing functionality."""
    
    @pytest.fixture
    def mock_session(self):
        """Mock MCP session."""
        session = AsyncMock()
        mock_tool = Tool(
            name="test_tool",
            description="Test tool description",
            inputSchema={"type": "object", "properties": {}}
        )
        
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
        # Ensure list_tools(server_name=...) treats only 'test-server' as configured
        client.mcp_registry.get_server_config_safe.side_effect = (
            lambda server_id: Mock(enabled=True) if server_id == "test-server" else None
        )
        return client
    
    @pytest.mark.asyncio
    async def test_list_tools_specific_server_success(self, client_with_session, mock_session):
        """Test successful tool listing for specific server."""
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id = Mock(return_value="list-req-123")
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client_with_session.list_tools("test-session", "test-server")
            
            assert "test-server" in result
            assert len(result["test-server"]) == 1
            
            tool = result["test-server"][0]
            assert tool.name == "test_tool"
            assert tool.description == "Test tool description"
            assert tool.inputSchema == {"type": "object", "properties": {}}
            
            mock_session.list_tools.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_tools_all_servers_success(self, client_with_session, mock_session):
        """Test successful tool listing for all servers."""
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id = Mock(return_value="list-all-req-456")
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
            mock_ctx.get_request_id = Mock(return_value="list-nonexistent-req")
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client_with_session.list_tools("test-session", "nonexistent-server")
            
            assert result == {}
    
    @pytest.mark.asyncio
    async def test_list_tools_server_error(self, client_with_session, mock_session):
        """Test tool listing handles server errors."""
        mock_session.list_tools.side_effect = Exception("Server error")
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id = Mock(return_value="list-error-req")
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
            mock_ctx.get_request_id = Mock(return_value="list-auto-init-req")
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            await client.list_tools("test-session")
            
            mock_init.assert_called_once()


@pytest.mark.unit
class TestMCPClientToolListingSimple:
    """Test MCP client simple tool listing functionality (without database storage)."""
    
    @pytest.fixture
    def mock_session(self):
        """Mock MCP session."""
        session = AsyncMock()
        mock_tool = Tool(
            name="test_tool",
            description="Test tool description",
            inputSchema={"type": "object", "properties": {}}
        )
        
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
    async def test_list_tools_simple_specific_server_success(self, client_with_session, mock_session):
        """Test successful simple tool listing for specific server."""
        result = await client_with_session.list_tools_simple("test-server")
        
        assert "test-server" in result
        assert len(result["test-server"]) == 1
        
        tool = result["test-server"][0]
        assert tool.name == "test_tool"
        assert tool.description == "Test tool description"
        assert tool.inputSchema == {"type": "object", "properties": {}}
        
        mock_session.list_tools.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_tools_simple_all_servers_success(self, client_with_session, mock_session):
        """Test successful simple tool listing for all servers."""
        result = await client_with_session.list_tools_simple()
        
        assert "test-server" in result
        assert len(result["test-server"]) == 1
        mock_session.list_tools.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_tools_simple_nonexistent_server(self, client_with_session):
        """Test simple tool listing for nonexistent server returns empty."""
        result = await client_with_session.list_tools_simple("nonexistent-server")
        
        assert result == {}
    
    @pytest.mark.asyncio
    async def test_list_tools_simple_server_error_returns_empty(self, client_with_session, mock_session):
        """Test simple tool listing handles server errors gracefully."""
        mock_session.list_tools.side_effect = Exception("Server error")
        
        result = await client_with_session.list_tools_simple("test-server")
        
        assert "test-server" in result
        assert result["test-server"] == []
    
    @pytest.mark.asyncio
    async def test_list_tools_simple_auto_initialize(self):
        """Test simple tool listing auto-initializes if needed."""
        client = MCPClient(Mock(), Mock())
        client._initialized = False
        
        with patch.object(client, 'initialize') as mock_init:
            await client.list_tools_simple()
            mock_init.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_tools_simple_multiple_servers(self):
        """Test simple tool listing with multiple servers."""
        client = MCPClient(Mock(), Mock())
        
        # Create multiple mock sessions with different tools
        mock_session1 = AsyncMock()
        mock_tool1 = Tool(name="tool1", description="Tool 1", inputSchema={})
        mock_result1 = Mock()
        mock_result1.tools = [mock_tool1]
        mock_session1.list_tools.return_value = mock_result1
        
        mock_session2 = AsyncMock()
        mock_tool2 = Tool(name="tool2", description="Tool 2", inputSchema={})
        mock_result2 = Mock()
        mock_result2.tools = [mock_tool2]
        mock_session2.list_tools.return_value = mock_result2
        
        client.sessions = {
            "server1": mock_session1,
            "server2": mock_session2
        }
        client._initialized = True
        
        result = await client.list_tools_simple()
        
        assert len(result) == 2
        assert "server1" in result
        assert "server2" in result
        assert result["server1"][0].name == "tool1"
        assert result["server2"][0].name == "tool2"
    
    @pytest.mark.asyncio
    async def test_list_tools_simple_no_database_interaction(self, client_with_session):
        """Test that simple tool listing doesn't interact with database."""
        # This test verifies that list_tools_simple doesn't use hook contexts
        # by checking that it can run without any database session or hook mocking
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            # Should NOT call mcp_list_context
            result = await client_with_session.list_tools_simple("test-server")
            
            assert "test-server" in result
            assert len(result["test-server"]) == 1
            
            # Verify no hook context was used
            mock_context.assert_not_called()


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
        registry.get_server_config_safe.side_effect = (
            lambda server_id: Mock(enabled=True, data_masking=Mock(enabled=False))
            if server_id == "test-server"
            else None
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
            mock_ctx.get_request_id = Mock(return_value="call-req-789")
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
        mock_result.content = [Mock(type="text", text="Result with api_key: not-a-real-api-key-0000000000000000")]
        mock_session.call_tool.return_value = mock_result
        
        client = MCPClient(Mock(), registry)
        client.sessions = {"test-server": mock_session}
        client._initialized = True
        
        # Mock data masking service
        mock_masking = Mock()
        mock_masking.mask_response.return_value = {"result": "Result with api_key: __MASKED_API_KEY__"}
        client.data_masking_service = mock_masking
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id = Mock(return_value="call-mask-req")
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client.call_tool(
                "test-server",
                "test_tool", 
                {"param": "value"},
                "test-session"
            )
            
            assert "__MASKED_API_KEY__" in str(result)
            # mask_response is now called twice: once for request parameters (logging), once for response
            assert mock_masking.mask_response.call_count == 2
            # Verify masking was called for both request parameters and response
            calls = mock_masking.mask_response.call_args_list
            assert calls[0][0] == ({'param': 'value'}, 'test-server')  # Request parameters
            assert 'api_key' in str(calls[1][0][0])  # Response
    
    @pytest.mark.asyncio
    async def test_call_tool_server_not_found(self, client_with_session):
        """Test tool calling with nonexistent server."""
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id = Mock(return_value="call-nonexistent-req")
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
            mock_ctx.get_request_id = Mock(return_value="call-error-req")
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
            mock_ctx.get_request_id = Mock(return_value="call-auto-init-req")
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
        from tarsy.models.mcp_transport_config import TRANSPORT_STDIO
        
        # Create mock transport config
        mock_transport = Mock()
        mock_transport.type = TRANSPORT_STDIO
        mock_transport.command = "test"
        mock_transport.args = []
        mock_transport.env = {}
        
        mock_registry.get_server_config_safe.return_value = Mock(
            enabled=True,
            transport=mock_transport,
            data_masking=Mock(enabled=False)
        )
        
        client = MCPClient(Mock(), mock_registry)
        
        with patch('tarsy.integrations.mcp.client.MCPTransportFactory') as mock_factory, \
             patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_list_context, \
             patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_call_context:
            
            # Setup transport and session mocks
            mock_transport_instance = AsyncMock()
            mock_session = AsyncMock()
            mock_transport_instance.create_session.return_value = mock_session
            mock_factory.create_transport.return_value = mock_transport_instance
            
            # Setup tool listing
            mock_tool = Tool(
                name="integration_tool",
                description="Integration test tool",
                inputSchema={"type": "object"}
            )
            
            mock_list_result = Mock()
            mock_list_result.tools = [mock_tool]
            mock_session.list_tools.return_value = mock_list_result
            
            # Setup tool calling
            mock_call_result = Mock()
            mock_call_result.content = [Mock(type="text", text="Integration result")]
            mock_session.call_tool.return_value = mock_call_result
            
            # Setup contexts
            mock_list_ctx = AsyncMock()
            mock_list_ctx.get_request_id = Mock(return_value="integration-list-req")
            mock_list_context.return_value.__aenter__.return_value = mock_list_ctx
            
            mock_call_ctx = AsyncMock()
            mock_call_ctx.get_request_id = Mock(return_value="integration-call-req")
            mock_call_context.return_value.__aenter__.return_value = mock_call_ctx
            
            # Execute complete workflow
            await client.initialize()
            assert client._initialized
            
            tools = await client.list_tools("integration-session", "integration-server")
            assert "integration-server" in tools
            assert len(tools["integration-server"]) == 1
            assert tools["integration-server"][0].name == "integration_tool"
            
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


@pytest.mark.unit
class TestMCPClientSummarization:
    """Test MCP client summarization functionality."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings."""
        settings = Mock(spec=Settings)
        settings.llm_iteration_timeout = 210  # Default timeout for summarization
        return settings
    
    @pytest.fixture
    def mock_registry_with_summarization(self):
        """Mock MCP server registry with summarization config."""
        from tarsy.models.mcp_transport_config import TRANSPORT_STDIO
        
        registry = Mock(spec=MCPServerRegistry)
        registry.get_all_server_ids.return_value = ["test-server"]
        
        # Mock server config with summarization enabled
        server_config = Mock()
        server_config.enabled = True
        
        # Create mock transport config
        mock_transport = Mock()
        mock_transport.type = TRANSPORT_STDIO
        mock_transport.command = "test"
        mock_transport.args = []
        mock_transport.env = {}
        server_config.transport = mock_transport
        
        # Mock summarization config
        summarization_config = Mock()
        summarization_config.enabled = True
        summarization_config.size_threshold_tokens = 100  # Low threshold for testing
        summarization_config.summary_max_token_limit = 50
        server_config.summarization = summarization_config
        
        registry.get_server_config_safe.return_value = server_config
        return registry
    
    @pytest.fixture
    def mock_summarizer(self):
        """Mock summarizer."""
        summarizer = Mock(spec=MCPResultSummarizer)
        # Mock summarizer to return shortened result
        async def mock_summarize(*args, **kwargs):
            return {"result": "Summarized: Large data truncated"}
        
        summarizer.summarize_result = AsyncMock(side_effect=mock_summarize)
        return summarizer
    
    @pytest.fixture
    def sample_conversation(self):
        """Create a sample investigation conversation."""
        return LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are an SRE investigating alerts"),
            LLMMessage(role=MessageRole.USER, content="Investigate the pod failures"),
            LLMMessage(role=MessageRole.ASSISTANT, content="I need to check the pod status")
        ])

    @pytest.mark.asyncio
    async def test_call_tool_with_summarization_large_result(self, mock_settings, mock_registry_with_summarization, mock_summarizer, sample_conversation):
        """Test call_tool applies summarization for large results."""
        client = MCPClient(mock_settings, mock_registry_with_summarization, mock_summarizer)
        
        # Mock data masking service to avoid mocking issues
        mock_masking = Mock()
        mock_masking.mask_response.return_value = {"result": "x" * 1000}  # Return large unmasked result
        client.data_masking_service = mock_masking
        
        # Create large result that exceeds the low threshold
        large_result = {"result": "x" * 1000}  # Large result to trigger summarization
        
        with patch('tarsy.integrations.mcp.client.MCPTransportFactory') as mock_factory, \
             patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_interaction_context:
            
            # Setup transport and session mocks
            mock_transport = AsyncMock()
            mock_session = AsyncMock()
            mock_session.call_tool.return_value = Mock(content=large_result["result"])
            mock_transport.create_session.return_value = mock_session
            mock_factory.create_transport.return_value = mock_transport
            
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id = Mock(return_value="test-req-123")
            mock_interaction_context.return_value.__aenter__.return_value = mock_ctx
            
            await client.initialize()
            
            # Call tool with investigation conversation
            result = await client.call_tool(
                "test-server", 
                "test-tool", 
                {"param": "value"}, 
                "test-session",
                "test-stage",
                sample_conversation
            )
            
            # Verify summarization was called
            mock_summarizer.summarize_result.assert_called_once()
            
            # Verify result structure includes summarization metadata
            assert "result" in result
            assert result["result"] == "Summarized: Large data truncated"

    @pytest.mark.asyncio
    async def test_call_tool_without_summarization_small_result(self, mock_settings, mock_registry_with_summarization, mock_summarizer, sample_conversation):
        """Test call_tool skips summarization for small results."""
        client = MCPClient(mock_settings, mock_registry_with_summarization, mock_summarizer)
        
        # Mock data masking service to return small result unchanged
        mock_masking = Mock()
        mock_masking.mask_response.return_value = {"result": "small"}
        client.data_masking_service = mock_masking
        
        # Create small result that doesn't exceed threshold
        small_result = {"result": "small"}
        
        with patch('tarsy.integrations.mcp.client.MCPTransportFactory') as mock_factory, \
             patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_interaction_context:
            
            # Setup transport and session mocks
            mock_transport = AsyncMock()
            mock_session = AsyncMock()
            mock_session.call_tool.return_value = Mock(content=small_result["result"])
            mock_transport.create_session.return_value = mock_session
            mock_factory.create_transport.return_value = mock_transport
            
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id = Mock(return_value="test-req-456")
            mock_interaction_context.return_value.__aenter__.return_value = mock_ctx
            
            await client.initialize()
            
            # Call tool with investigation conversation
            result = await client.call_tool(
                "test-server", 
                "test-tool", 
                {"param": "value"}, 
                "test-session",
                "test-stage",
                sample_conversation
            )
            
            # Verify summarization was NOT called
            mock_summarizer.summarize_result.assert_not_called()
            
            # Verify original result is returned
            assert result["result"] == "small"
            assert "_summarized" not in result

    @pytest.mark.asyncio
    async def test_call_tool_without_investigation_conversation(self, mock_settings, mock_registry_with_summarization, mock_summarizer):
        """Test call_tool skips summarization without investigation conversation."""
        client = MCPClient(mock_settings, mock_registry_with_summarization, mock_summarizer)
        
        # Mock data masking service to return large result unchanged
        mock_masking = Mock()
        mock_masking.mask_response.return_value = {"result": "x" * 1000}
        client.data_masking_service = mock_masking
        
        large_result = {"result": "x" * 1000}  # Large result
        
        with patch('tarsy.integrations.mcp.client.MCPTransportFactory') as mock_factory, \
             patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_interaction_context:
            
            # Setup transport and session mocks
            mock_transport = AsyncMock()
            mock_session = AsyncMock()
            mock_session.call_tool.return_value = Mock(content=large_result["result"])
            mock_transport.create_session.return_value = mock_session
            mock_factory.create_transport.return_value = mock_transport
            
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id = Mock(return_value="test-req-789")
            mock_interaction_context.return_value.__aenter__.return_value = mock_ctx
            
            await client.initialize()
            
            # Call tool WITHOUT investigation conversation
            result = await client.call_tool(
                "test-server", 
                "test-tool", 
                {"param": "value"}, 
                "test-session"
            )
            
            # Verify summarization was NOT called
            mock_summarizer.summarize_result.assert_not_called()
            
            # Verify original large result is returned
            assert result["result"] == "x" * 1000
            assert "_summarized" not in result

    @pytest.mark.asyncio
    async def test_call_tool_summarization_disabled_by_config(self, mock_settings, mock_summarizer, sample_conversation):
        """Test call_tool respects disabled summarization configuration."""
        from tarsy.models.mcp_transport_config import TRANSPORT_STDIO
        
        # Arrange - Registry with summarization disabled
        registry = Mock(spec=MCPServerRegistry)
        registry.get_all_server_ids.return_value = ["test-server"]
        
        server_config = Mock()
        server_config.enabled = True
        
        # Create mock transport config
        mock_transport = Mock()
        mock_transport.type = TRANSPORT_STDIO
        mock_transport.command = "test"
        mock_transport.args = []
        mock_transport.env = {}
        server_config.transport = mock_transport
        
        # Disabled summarization config
        summarization_config = Mock()
        summarization_config.enabled = False  # Explicitly disabled
        server_config.summarization = summarization_config
        
        registry.get_server_config_safe.return_value = server_config
        
        client = MCPClient(mock_settings, registry, mock_summarizer)
        
        # Mock data masking service
        mock_masking = Mock()
        mock_masking.mask_response.return_value = {"result": "x" * 1000}  # Large result
        client.data_masking_service = mock_masking
        
        large_result = {"result": "x" * 1000}
        
        with patch('tarsy.integrations.mcp.client.MCPTransportFactory') as mock_factory, \
             patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_interaction_context:
            
            # Setup transport and session mocks
            mock_transport = AsyncMock()
            mock_session = AsyncMock()
            mock_session.call_tool.return_value = Mock(content=large_result["result"])
            mock_transport.create_session.return_value = mock_session
            mock_factory.create_transport.return_value = mock_transport
            
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id = Mock(return_value="test-req-disabled")
            mock_interaction_context.return_value.__aenter__.return_value = mock_ctx
            
            await client.initialize()
            
            # Call tool with investigation conversation and large result
            result = await client.call_tool(
                "test-server",
                "test-tool",
                {"param": "value"},
                "test-session",
                "test-stage", 
                sample_conversation
            )
            
            # Verify summarization was NOT called despite large result and conversation
            mock_summarizer.summarize_result.assert_not_called()
            
            # Verify original large result is returned unchanged
            assert result["result"] == "x" * 1000
            assert "_summarized" not in result

    @pytest.mark.asyncio
    async def test_call_tool_summarization_error_graceful_degradation(self, mock_settings, mock_registry_with_summarization, sample_conversation):
        """Test graceful degradation when summarization fails."""
        # Arrange - Summarizer that always fails
        failing_summarizer = Mock(spec=MCPResultSummarizer)
        failing_summarizer.summarize_result = AsyncMock(side_effect=Exception("Summarization failed"))
        
        client = MCPClient(mock_settings, mock_registry_with_summarization, failing_summarizer)
        
        # Mock data masking service
        mock_masking = Mock()
        mock_masking.mask_response.return_value = {"result": "x" * 1000}  # Large result
        client.data_masking_service = mock_masking
        
        large_result = {"result": "x" * 1000}
        
        with patch('tarsy.integrations.mcp.client.MCPTransportFactory') as mock_factory, \
             patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_interaction_context:
            
            # Setup transport and session mocks
            mock_transport = AsyncMock()
            mock_session = AsyncMock()
            mock_session.call_tool.return_value = Mock(content=large_result["result"])
            mock_transport.create_session.return_value = mock_session
            mock_factory.create_transport.return_value = mock_transport
            
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id = Mock(return_value="test-req-error")
            mock_interaction_context.return_value.__aenter__.return_value = mock_ctx
            
            await client.initialize()
            
            # Act
            result = await client.call_tool(
                "test-server",
                "test-tool", 
                {"param": "value"},
                "test-session",
                "test-stage",
                sample_conversation
            )
            
            # Assert - Should return error message as result (graceful degradation)
            assert "result" in result
            result_text = str(result["result"])
            assert "Error: Failed to summarize large result" in result_text
            assert "Summarization failed" in result_text
            assert "tokens)" in result_text  # Should include original token count from token counter

    @pytest.mark.asyncio
    async def test_call_tool_no_server_config_skips_summarization(self, mock_settings, mock_summarizer, sample_conversation):
        """Test that missing server config skips summarization safely."""
        # Arrange - Registry that returns None for server config but has valid server session
        registry = Mock(spec=MCPServerRegistry)
        registry.get_all_server_ids.return_value = ["test-server"]
        registry.get_server_config_safe.return_value = None  # Missing config
        
        client = MCPClient(mock_settings, registry, mock_summarizer)
        
        large_result = {"result": "x" * 1000}
        
        with patch('tarsy.integrations.mcp.client.MCPTransportFactory') as mock_factory, \
             patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_interaction_context:
            
            # Setup transport and session mocks
            mock_transport = AsyncMock()
            mock_session = AsyncMock()
            mock_session.call_tool.return_value = Mock(content=large_result["result"])
            mock_transport.create_session.return_value = mock_session
            mock_factory.create_transport.return_value = mock_transport
            
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id = Mock(return_value="test-req-no-config")
            mock_interaction_context.return_value.__aenter__.return_value = mock_ctx
            
            await client.initialize()
            
            # Mock the server session to exist (even though config is None)
            client.sessions["test-server"] = mock_session
            
            # Act
            result = await client.call_tool(
                "test-server",
                "test-tool",
                {"param": "value"},
                "test-session", 
                "test-stage",
                sample_conversation
            )
            
            # Assert - Should not call summarization and return original result
            mock_summarizer.summarize_result.assert_not_called()
            assert result["result"] == "x" * 1000
            assert "_summarized" not in result

    @pytest.mark.asyncio
    async def test_call_tool_custom_summarization_thresholds(self, mock_settings, mock_summarizer, sample_conversation):
        """Test call_tool respects custom summarization thresholds."""
        from tarsy.models.mcp_transport_config import TRANSPORT_STDIO
        
        # Arrange - Registry with custom threshold
        registry = Mock(spec=MCPServerRegistry)
        registry.get_all_server_ids.return_value = ["test-server"]
        
        server_config = Mock()
        server_config.enabled = True
        
        # Create mock transport config
        mock_transport = Mock()
        mock_transport.type = TRANSPORT_STDIO
        mock_transport.command = "test"
        mock_transport.args = []
        mock_transport.env = {}
        server_config.transport = mock_transport
        
        # Custom summarization config with higher threshold
        summarization_config = Mock()
        summarization_config.enabled = True
        summarization_config.size_threshold_tokens = 500  # Higher threshold
        summarization_config.summary_max_token_limit = 200  # Custom limit
        server_config.summarization = summarization_config
        
        registry.get_server_config_safe.return_value = server_config
        
        client = MCPClient(mock_settings, registry, mock_summarizer)
        
        # Mock data masking service
        mock_masking = Mock()
        mock_masking.mask_response.return_value = {"result": "x" * 300}  # Medium result (below 500 threshold)
        client.data_masking_service = mock_masking
        
        medium_result = {"result": "x" * 300}
        
        with patch('tarsy.integrations.mcp.client.MCPTransportFactory') as mock_factory, \
             patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_interaction_context:
            
            # Setup transport and session mocks
            mock_transport = AsyncMock()
            mock_session = AsyncMock()
            mock_session.call_tool.return_value = Mock(content=medium_result["result"])
            mock_transport.create_session.return_value = mock_session
            mock_factory.create_transport.return_value = mock_transport
            
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id = Mock(return_value="test-req-threshold")
            mock_interaction_context.return_value.__aenter__.return_value = mock_ctx
            
            await client.initialize()
            
            # Act
            result = await client.call_tool(
                "test-server",
                "test-tool",
                {"param": "value"}, 
                "test-session",
                "test-stage",
                sample_conversation
            )
            
            # Assert - Should not trigger summarization (below custom threshold)
            mock_summarizer.summarize_result.assert_not_called()
            assert result["result"] == "x" * 300
            assert "_summarized" not in result

    @pytest.mark.asyncio
    async def test_call_tool_summarization_timeout_returns_error(self, mock_registry_with_summarization, sample_conversation):
        """Test that summarization timeout is handled gracefully with error message."""
        import asyncio
        
        # Arrange - Summarizer that takes too long
        slow_summarizer = Mock(spec=MCPResultSummarizer)
        
        async def slow_summarize(*args, **kwargs):
            await asyncio.sleep(2)  # Takes 2 seconds (exceeds 500ms timeout)
            return {"result": "Should never reach this"}
        
        slow_summarizer.summarize_result = AsyncMock(side_effect=slow_summarize)
        
        # Mock settings with short timeout for testing
        mock_settings = Mock(spec=Settings)
        mock_settings.llm_iteration_timeout = 0.5  # 500ms timeout for testing
        client = MCPClient(mock_settings, mock_registry_with_summarization, slow_summarizer)
        
        # Mock data masking service to return large result
        mock_masking = Mock()
        mock_masking.mask_response.return_value = {"result": "x" * 1000}  # Large result
        client.data_masking_service = mock_masking
        
        large_result = {"result": "x" * 1000}
        
        with patch('tarsy.integrations.mcp.client.MCPTransportFactory') as mock_factory, \
             patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_interaction_context:
            
            # Setup transport and session mocks
            mock_transport = AsyncMock()
            mock_session = AsyncMock()
            mock_session.call_tool.return_value = Mock(content=large_result["result"])
            mock_transport.create_session.return_value = mock_session
            mock_factory.create_transport.return_value = mock_transport
            
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id = Mock(return_value="test-req-timeout")
            mock_interaction_context.return_value.__aenter__.return_value = mock_ctx
            
            await client.initialize()
            
            # Act - Call tool with investigation conversation (should trigger summarization)
            result = await client.call_tool(
                "test-server",
                "test-tool",
                {"param": "value"},
                "test-session",
                "test-stage",
                sample_conversation
            )
            
            # Assert - Should return error message about timeout
            assert "result" in result
            result_text = str(result["result"])
            assert "Error: Summarization timed out" in result_text
            assert "tokens)" in result_text  # Should include original token count


@pytest.mark.unit
class TestMCPClientSummarizationPlaceholder:
    """Test MCP client summarization placeholder functionality."""
    
    @pytest.mark.asyncio
    async def test_publish_summarization_placeholder_success(self):
        """Test successful publishing of summarization placeholder event."""
        client = MCPClient(Mock(), Mock())
        
        with patch('tarsy.database.init_db.get_async_session_factory') as mock_factory, \
             patch('tarsy.services.events.publisher.publish_transient_event') as mock_publish:
            
            # Setup mock session
            mock_session = AsyncMock()
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__.return_value = mock_session
            mock_factory.return_value.return_value = mock_session_context
            
            # Act
            await client._publish_summarization_placeholder(
                session_id="test-session",
                stage_execution_id="stage-123",
                mcp_event_id="mcp-event-456"
            )
            
            # Assert - Verify event was published
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            
            # Verify channel and session
            assert call_args[0][0] == mock_session
            assert call_args[0][1] == "session:test-session"
            
            # Verify event structure
            event = call_args[0][2]
            assert event.session_id == "test-session"
            assert event.stage_execution_id == "stage-123"
            assert event.mcp_event_id == "mcp-event-456"
            assert event.chunk == "Summarizing tool results..."
            assert event.stream_type == StreamingEventType.SUMMARIZATION.value
            assert event.is_complete is False
    
    @pytest.mark.asyncio
    async def test_publish_summarization_placeholder_without_stage_id(self):
        """Test publishing placeholder without stage execution ID."""
        client = MCPClient(Mock(), Mock())
        
        with patch('tarsy.database.init_db.get_async_session_factory') as mock_factory, \
             patch('tarsy.services.events.publisher.publish_transient_event') as mock_publish:
            
            mock_session = AsyncMock()
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__.return_value = mock_session
            mock_factory.return_value.return_value = mock_session_context
            
            # Act
            await client._publish_summarization_placeholder(
                session_id="test-session",
                stage_execution_id=None,
                mcp_event_id=None
            )
            
            # Assert
            mock_publish.assert_called_once()
            event = mock_publish.call_args[0][2]
            assert event.stage_execution_id is None
            assert event.mcp_event_id is None
            assert event.session_id == "test-session"
    
    @pytest.mark.asyncio
    async def test_publish_summarization_placeholder_handles_errors_gracefully(self):
        """Test placeholder publishing handles errors without failing."""
        client = MCPClient(Mock(), Mock())
        
        with patch('tarsy.database.init_db.get_async_session_factory') as mock_factory:
            mock_factory.side_effect = Exception("Event system error")
            
            # Should not raise exception (non-critical operation)
            await client._publish_summarization_placeholder(
                session_id="test-session",
                stage_execution_id="stage-123",
                mcp_event_id="mcp-event-456"
            )
    
    @pytest.mark.asyncio
    async def test_summarization_triggers_placeholder_before_summarizing(self, ):
        """Test that placeholder is published before actual summarization."""
        from tarsy.models.mcp_transport_config import TRANSPORT_STDIO
        
        # Setup registry with summarization enabled
        registry = Mock(spec=MCPServerRegistry)
        registry.get_all_server_ids.return_value = ["test-server"]
        
        server_config = Mock()
        server_config.enabled = True
        
        mock_transport = Mock()
        mock_transport.type = TRANSPORT_STDIO
        mock_transport.command = "test"
        mock_transport.args = []
        mock_transport.env = {}
        server_config.transport = mock_transport
        
        summarization_config = Mock()
        summarization_config.enabled = True
        summarization_config.size_threshold_tokens = 100
        summarization_config.summary_max_token_limit = 50
        server_config.summarization = summarization_config
        
        registry.get_server_config_safe.return_value = server_config
        
        # Setup summarizer
        mock_summarizer = Mock(spec=MCPResultSummarizer)
        mock_summarizer.summarize_result = AsyncMock(return_value={"result": "Summarized"})
        
        client = MCPClient(Mock(), registry, mock_summarizer)
        
        # Mock data masking
        mock_masking = Mock()
        mock_masking.mask_response.return_value = {"result": "x" * 1000}
        client.data_masking_service = mock_masking
        
        large_result = {"result": "x" * 1000}
        
        # Create sample conversation
        from tarsy.models.unified_interactions import (
            LLMConversation,
            LLMMessage,
            MessageRole,
        )
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are an SRE investigating alerts"),
            LLMMessage(role=MessageRole.USER, content="Test")
        ])
        
        with patch('tarsy.integrations.mcp.client.MCPTransportFactory') as mock_factory, \
             patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_interaction_context, \
             patch.object(client, '_publish_summarization_placeholder') as mock_placeholder:
            
            # Setup transport and session
            mock_transport_instance = AsyncMock()
            mock_session = AsyncMock()
            mock_session.call_tool.return_value = Mock(content=large_result["result"])
            mock_transport_instance.create_session.return_value = mock_session
            mock_factory.create_transport.return_value = mock_transport_instance
            
            mock_ctx = AsyncMock()
            mock_ctx.interaction.communication_id = "mcp-event-123"
            mock_interaction_context.return_value.__aenter__.return_value = mock_ctx
            
            await client.initialize()
            
            # Act - Call tool with large result
            await client.call_tool(
                "test-server",
                "test-tool",
                {"param": "value"},
                "test-session",
                "stage-123",
                conversation,
                mcp_selection=None,
                configured_servers=None
            )
            
            # Assert - Placeholder was published before summarization
            mock_placeholder.assert_called_once_with(
                "test-session",
                "stage-123",
                "mcp-event-123"
            )
            mock_summarizer.summarize_result.assert_called_once()