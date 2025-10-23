"""
Unit tests for MCP client.

Tests the MCP client that handles communication with MCP servers
using the official MCP SDK and the new typed hook system.
"""

from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, Mock, patch
from mcp.types import Tool

import pytest

from tarsy.config.settings import Settings
from tarsy.integrations.mcp.client import MCPClient
from tarsy.integrations.mcp.summarizer import MCPResultSummarizer
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
            assert tool.name == "test_tool"
            assert tool.description == "Test tool description"
            assert tool.inputSchema == {"type": "object", "properties": {}}
            
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
        mock_result.content = [Mock(type="text", text="Result with api_key: not-a-real-api-key-0000000000000000")]
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
class TestMCPClientRecovery:
    """Test MCP client recovery functionality."""
    
    @pytest.fixture
    def mock_registry(self):
        """Mock MCP server registry with recovery-friendly config."""
        registry = Mock(spec=MCPServerRegistry)
        mock_config = Mock()
        mock_config.command = "test-command"
        mock_config.args = ["--test"]
        mock_config.env = {"TEST_VAR": "test_value"}
        # Disable data masking to avoid interference
        mock_config.data_masking = Mock(enabled=False)
        registry.get_server_config_safe.return_value = mock_config
        return registry
    
    @pytest.fixture
    def client_with_recovery_setup(self, mock_registry):
        """Create client configured for recovery testing."""
        client = MCPClient(Mock(), mock_registry)
        client._initialized = True
        # Disable data masking service to avoid test interference
        client.data_masking_service = None
        return client
    
    @pytest.mark.asyncio
    async def test_recovery_attempted_on_tool_call_failure(self, client_with_recovery_setup):
        """Test that recovery is attempted when a tool call fails."""
        client = client_with_recovery_setup
        
        # Create a failing session
        failing_session = AsyncMock()
        failing_session.call_tool.side_effect = Exception("Connection closed")
        client.sessions = {"test-server": failing_session}
        
        # Mock the recovery method to track if it's called
        recovery_called = False
        
        async def mock_recover_session(server_name):
            nonlocal recovery_called
            recovery_called = True
            # Create a new working session
            new_session = AsyncMock()
            mock_result = Mock()
            mock_result.content = [Mock(type="text", text="Recovery successful")]
            new_session.call_tool.return_value = mock_result
            client.sessions[server_name] = new_session
        
        client._recover_session = mock_recover_session
        
        # Attempt tool call - should trigger recovery
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "recovery-test-123"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client.call_tool(
                "test-server", 
                "test_tool", 
                {"param": "value"}, 
                "test-session"
            )
            
            # Verify recovery was attempted and call succeeded
            assert recovery_called, "Recovery should have been attempted"
            assert "Recovery successful" in str(result), "Tool call should succeed after recovery"
    
    @pytest.mark.asyncio
    async def test_retry_logic_and_error_message_format(self, client_with_recovery_setup):
        """Test retry behavior and proper error message formatting."""
        client = client_with_recovery_setup
        
        # Track call attempts
        call_count = 0
        def failing_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise Exception("Always fails")
        
        failing_session = AsyncMock()
        failing_session.call_tool.side_effect = failing_side_effect
        client.sessions = {"test-server": failing_session}
        
        # Mock recovery that fails
        async def mock_recover_session(server_name):
            raise Exception("Recovery failed")
        
        client._recover_session = mock_recover_session
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "retry-test-456"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            # Should fail with proper error message including attempt count
            with pytest.raises(Exception) as exc_info:
                await client.call_tool("test-server", "test_tool", {"param": "value"}, "test-session")
            
            # Verify error message format includes attempt count
            error_msg = str(exc_info.value)
            assert "after 2 attempts" in error_msg, f"Error should mention attempts: {error_msg}"
            assert "Always fails" in error_msg, f"Error should include original error: {error_msg}"
    
    @pytest.mark.asyncio 
    async def test_successful_recovery_flow(self, client_with_recovery_setup):
        """Test the complete successful recovery flow."""
        client = client_with_recovery_setup
        
        # Track session lifecycle
        sessions_created = []
        recovery_called = False
        
        # Create initial failing session
        failing_session = AsyncMock()
        failing_session.call_tool.side_effect = Exception("Connection lost")
        client.sessions = {"test-server": failing_session}
        
        # Mock successful recovery
        async def mock_recover_session(server_name):
            nonlocal recovery_called
            recovery_called = True
            
            # Create recovered session that works
            recovered_session = AsyncMock()
            mock_result = Mock()
            mock_result.content = [Mock(type="text", text="Recovered and working")]
            recovered_session.call_tool.return_value = mock_result
            client.sessions[server_name] = recovered_session
            sessions_created.append("recovered_session")
        
        client._recover_session = mock_recover_session
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "success-recovery-test"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            # This should succeed after recovery
            result = await client.call_tool("test-server", "test_tool", {}, "test-session")
            
            # Verify recovery occurred and result is correct
            assert recovery_called, "Recovery should have been called"
            assert len(sessions_created) == 1, "One recovered session should be created"
            assert "Recovered and working" in str(result), "Should get result from recovered session"
    
    @pytest.mark.asyncio
    async def test_recovery_isolation(self, client_with_recovery_setup):
        """Test that recovery only affects the failing server."""
        client = client_with_recovery_setup
        
        # Set up two sessions: one failing, one working
        failing_session = AsyncMock()
        failing_session.call_tool.side_effect = Exception("Server A failed")
        
        working_session = AsyncMock()
        working_result = Mock()
        working_result.content = [Mock(type="text", text="Server B is fine")]
        working_session.call_tool.return_value = working_result
        
        client.sessions = {
            "server-a": failing_session,
            "server-b": working_session
        }
        
        # Mock recovery for server-a only
        recovery_calls = []
        async def mock_recover_session(server_name):
            recovery_calls.append(server_name)
            if server_name == "server-a":
                # Create recovered session
                recovered_session = AsyncMock()
                recovered_result = Mock()
                recovered_result.content = [Mock(type="text", text="Server A recovered")]
                recovered_session.call_tool.return_value = recovered_result
                client.sessions[server_name] = recovered_session
        
        client._recover_session = mock_recover_session
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "isolation-test"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            # Test failing server recovers
            result_a = await client.call_tool("server-a", "test_tool", {}, "test-session")
            assert "Server A recovered" in str(result_a)
            assert len(recovery_calls) == 1, "Recovery should be called once"
            assert recovery_calls[0] == "server-a", "Recovery should be called for server-a"
            
            # Test working server is unaffected
            result_b = await client.call_tool("server-b", "test_tool", {}, "test-session")
            assert "Server B is fine" in str(result_b)
            # Working session should still be the original one
            assert client.sessions["server-b"] == working_session, "Working session unchanged"
    


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
        return Mock(spec=Settings)
    
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
            mock_ctx.get_request_id.return_value = "test-req-123"
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
            mock_ctx.get_request_id.return_value = "test-req-456"
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
            mock_ctx.get_request_id.return_value = "test-req-789"
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
            mock_ctx.get_request_id.return_value = "test-req-disabled"
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
            mock_ctx.get_request_id.return_value = "test-req-error"
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
            mock_ctx.get_request_id.return_value = "test-req-no-config"
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
            mock_ctx.get_request_id.return_value = "test-req-threshold"
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