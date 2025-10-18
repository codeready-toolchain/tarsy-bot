"""
Unit tests for MCP client timeout functionality.

Tests the 60-second timeout implementation for MCP tool calls
and list_tools operations to prevent indefinite hanging.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import Tool

from tarsy.integrations.mcp.client import MCPClient


@pytest.mark.unit
class TestMCPClientCallToolTimeout:
    """Test MCP client call_tool timeout functionality."""
    
    @pytest.fixture
    def mock_session(self):
        """Mock MCP session."""
        return AsyncMock()
    
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
    async def test_call_tool_timeout_after_60_seconds(self, client_with_session, mock_session):
        """Test that tool call times out after 60 seconds."""
        # Mock call_tool to raise TimeoutError
        mock_session.call_tool.side_effect = asyncio.TimeoutError()
        
        # Mock failing recovery
        async def failing_recovery(server_name):
            raise Exception("Recovery failed")
        
        client_with_session._recover_session = failing_recovery
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "timeout-test-123"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):  # Speed up retry delays
                # Should raise TimeoutError after timeout and recovery failure
                with pytest.raises(asyncio.TimeoutError, match="timed out after 2 attempts"):
                    await client_with_session.call_tool(
                        "test-server",
                        "test_tool",
                        {"param": "value"},
                        "test-session"
                    )
                
                # With failed recovery, only attempts once before raising
                assert mock_session.call_tool.call_count == 1
    
    @pytest.mark.asyncio
    async def test_call_tool_timeout_triggers_recovery(self, client_with_session, mock_session):
        """Test that timeout triggers session recovery."""
        # First call times out, second succeeds
        success_result = Mock()
        success_result.content = [Mock(type="text", text="Success after recovery")]
        
        mock_session.call_tool.side_effect = [
            asyncio.TimeoutError(),  # First call times out
            success_result  # After recovery, call succeeds
        ]
        
        # Mock successful recovery
        recovery_called = False
        async def mock_recover(server_name):
            nonlocal recovery_called
            recovery_called = True
        
        client_with_session._recover_session = mock_recover
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "recovery-test-456"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):  # Speed up retries
                result = await client_with_session.call_tool(
                    "test-server",
                    "test_tool",
                    {},
                    "test-session"
                )
                
                assert "Success after recovery" in str(result)
                assert recovery_called, "Recovery should have been attempted"
                assert mock_session.call_tool.call_count == 2
    
    @pytest.mark.asyncio
    async def test_call_tool_timeout_final_failure(self, client_with_session, mock_session):
        """Test final failure after max retries exhausted."""
        # All calls time out
        mock_session.call_tool.side_effect = asyncio.TimeoutError()
        
        # Mock recovery that also fails
        async def failing_recovery(server_name):
            raise Exception("Recovery failed")
        
        client_with_session._recover_session = failing_recovery
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):
                with pytest.raises(asyncio.TimeoutError, match="timed out after 2 attempts"):
                    await client_with_session.call_tool(
                        "test-server",
                        "test_tool",
                        {},
                        "test-session"
                    )
                
                # With failed recovery, only attempts once before raising
                assert mock_session.call_tool.call_count == 1
    
    @pytest.mark.asyncio
    async def test_call_tool_completes_within_timeout(self, client_with_session, mock_session):
        """Test that normal calls complete successfully within timeout."""
        mock_result = Mock()
        mock_result.content = [Mock(type="text", text="Quick response")]
        mock_session.call_tool.return_value = mock_result
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "normal-test-789"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client_with_session.call_tool(
                "test-server",
                "test_tool",
                {},
                "test-session"
            )
            
            assert "Quick response" in str(result)
            assert mock_session.call_tool.call_count == 1


@pytest.mark.unit
class TestMCPClientListToolsTimeout:
    """Test MCP client list_tools timeout functionality."""
    
    @pytest.fixture
    def mock_session(self):
        """Mock MCP session."""
        return AsyncMock()
    
    @pytest.fixture
    def client_with_session(self, mock_session):
        """Create client with mocked session."""
        client = MCPClient(Mock(), Mock())
        client.sessions = {"test-server": mock_session}
        client._initialized = True
        return client
    
    @pytest.mark.asyncio
    async def test_list_tools_timeout_specific_server(self, client_with_session, mock_session):
        """Test that list_tools times out for specific server."""
        # Mock list_tools to raise TimeoutError
        mock_session.list_tools.side_effect = asyncio.TimeoutError()
        
        # Mock failing recovery
        async def failing_recovery(server_name):
            raise Exception("Recovery failed")
        
        client_with_session._recover_session = failing_recovery
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "list-timeout-123"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):  # Speed up retry delays
                result = await client_with_session.list_tools("test-session", "test-server")
                
                # Should return empty list after timeout
                assert result["test-server"] == []
                # With failed recovery, only attempts once before returning empty
                assert mock_session.list_tools.call_count == 1
    
    @pytest.mark.asyncio
    async def test_list_tools_timeout_all_servers(self, client_with_session, mock_session):
        """Test that list_tools times out when listing all servers."""
        # Mock list_tools to raise TimeoutError
        mock_session.list_tools.side_effect = asyncio.TimeoutError()
        
        # Mock failing recovery
        async def failing_recovery(server_name):
            raise Exception("Recovery failed")
        
        client_with_session._recover_session = failing_recovery
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "list-all-timeout-456"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):
                result = await client_with_session.list_tools("test-session")
                
                # Should return empty list after timeout
                assert result["test-server"] == []
                # With failed recovery, only attempts once before returning empty
                assert mock_session.list_tools.call_count == 1
    
    @pytest.mark.asyncio
    async def test_list_tools_timeout_triggers_recovery(self, client_with_session, mock_session):
        """Test that list_tools timeout triggers session recovery."""
        # First call times out, second succeeds
        mock_tool = Tool(
            name="recovered_tool",
            description="Tool after recovery",
            inputSchema={"type": "object"}
        )
        
        success_result = Mock()
        success_result.tools = [mock_tool]
        
        mock_session.list_tools.side_effect = [
            asyncio.TimeoutError(),  # First call times out
            success_result  # After recovery, call succeeds
        ]
        
        # Mock successful recovery
        recovery_called = False
        async def mock_recover(server_name):
            nonlocal recovery_called
            recovery_called = True
        
        client_with_session._recover_session = mock_recover
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "list-recovery-789"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):
                result = await client_with_session.list_tools("test-session", "test-server")
                
                assert len(result["test-server"]) == 1
                assert result["test-server"][0].name == "recovered_tool"
                assert recovery_called, "Recovery should have been attempted"
                assert mock_session.list_tools.call_count == 2
    
    @pytest.mark.asyncio
    async def test_list_tools_completes_within_timeout(self, client_with_session, mock_session):
        """Test that normal list_tools completes successfully within timeout."""
        mock_tool = Tool(
            name="quick_tool",
            description="Quick response tool",
            inputSchema={"type": "object"}
        )
        
        mock_result = Mock()
        mock_result.tools = [mock_tool]
        mock_session.list_tools.return_value = mock_result
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "list-normal-101"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client_with_session.list_tools("test-session", "test-server")
            
            assert len(result["test-server"]) == 1
            assert result["test-server"][0].name == "quick_tool"
            assert mock_session.list_tools.call_count == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "operation,server_name,should_recover,expected_calls",
    [
        ("call_tool", "test-server", True, 2),
        ("call_tool", "test-server", False, 2),
        ("list_tools", "test-server", True, 2),
        ("list_tools", None, True, 2),  # All servers
    ],
)
class TestMCPClientTimeoutMatrix:
    """Test timeout behavior across different MCP operations."""
    
    @pytest.mark.asyncio
    async def test_timeout_scenarios(self, operation, server_name, should_recover, expected_calls):
        """Test various timeout scenarios across operations."""
        mock_session = AsyncMock()
        
        # Build side effects
        if should_recover:
            if operation == "call_tool":
                success_result = Mock()
                success_result.content = [Mock(type="text", text="Success")]
                side_effects = [asyncio.TimeoutError(), success_result]
            else:  # list_tools
                success_result = Mock()
                success_result.tools = [Tool(name="tool", description="desc", inputSchema={})]
                side_effects = [asyncio.TimeoutError(), success_result]
        else:
            side_effects = [asyncio.TimeoutError()] * expected_calls
        
        if operation == "call_tool":
            mock_session.call_tool.side_effect = side_effects
        else:
            mock_session.list_tools.side_effect = side_effects
        
        registry = Mock()
        registry.get_server_config_safe.return_value = Mock(
            data_masking=Mock(enabled=False)
        )
        
        client = MCPClient(Mock(), registry)
        client.sessions = {"test-server": mock_session}
        client._initialized = True
        
        # Mock recovery
        async def mock_recover(srv_name):
            if not should_recover:
                raise Exception("Recovery failed")
        
        client._recover_session = mock_recover
        
        if operation == "call_tool":
            context_patch = 'tarsy.integrations.mcp.client.mcp_interaction_context'
        else:
            context_patch = 'tarsy.integrations.mcp.client.mcp_list_context'
        
        with patch(context_patch) as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = f"matrix-{operation}"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):
                if operation == "call_tool":
                    if should_recover:
                        result = await client.call_tool(
                            "test-server", "tool", {}, "session"
                        )
                        assert "Success" in str(result)
                        # With successful recovery, makes 2 calls
                        assert mock_session.call_tool.call_count == 2
                    else:
                        with pytest.raises(asyncio.TimeoutError):
                            await client.call_tool(
                                "test-server", "tool", {}, "session"
                            )
                        # With failed recovery, only attempts once
                        assert mock_session.call_tool.call_count == 1
                else:  # list_tools
                    result = await client.list_tools("session", server_name)
                    if should_recover:
                        assert len(result["test-server"]) == 1
                        # With successful recovery, makes 2 calls
                        assert mock_session.list_tools.call_count == 2
                    else:
                        assert result["test-server"] == []
                        # With failed recovery, only attempts once
                        assert mock_session.list_tools.call_count == 1


@pytest.mark.unit
class TestMCPClientTimeoutLogging:
    """Test that timeout events are properly logged."""
    
    @pytest.mark.asyncio
    async def test_call_tool_timeout_logs_error(self, caplog):
        """Test that call_tool timeout errors are logged."""
        mock_session = AsyncMock()
        mock_session.call_tool.side_effect = asyncio.TimeoutError()
        
        registry = Mock()
        registry.get_server_config_safe.return_value = Mock(
            data_masking=Mock(enabled=False)
        )
        
        client = MCPClient(Mock(), registry)
        client.sessions = {"test-server": mock_session}
        client._initialized = True
        
        # Mock failing recovery
        async def failing_recovery(server_name):
            raise Exception("Recovery failed")
        
        client._recover_session = failing_recovery
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):
                with pytest.raises(asyncio.TimeoutError):
                    await client.call_tool("test-server", "tool", {}, "session")
        
        # Verify timeout was logged
        assert any("timed out after 60s" in record.message for record in caplog.records)
    
    @pytest.mark.asyncio
    async def test_list_tools_timeout_logs_error(self, caplog):
        """Test that list_tools timeout errors are logged."""
        mock_session = AsyncMock()
        mock_session.list_tools.side_effect = asyncio.TimeoutError()
        
        client = MCPClient(Mock(), Mock())
        client.sessions = {"test-server": mock_session}
        client._initialized = True
        
        # Mock failing recovery
        async def failing_recovery(server_name):
            raise Exception("Recovery failed")
        
        client._recover_session = failing_recovery
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            with patch('asyncio.sleep'):
                await client.list_tools("session", "test-server")
        
        # Verify timeout was logged
        assert any("List tools timed out" in record.message or "timed out after 60s" in record.message for record in caplog.records)
