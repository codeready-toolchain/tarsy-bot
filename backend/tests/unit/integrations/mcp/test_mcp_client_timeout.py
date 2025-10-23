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
        """Test that tool call times out after 60 seconds and fails immediately."""
        # Mock call_tool to raise TimeoutError
        mock_session.call_tool.side_effect = asyncio.TimeoutError()
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "timeout-test-123"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            # Per plan: timeouts fail immediately without retry
            with pytest.raises(TimeoutError, match="MCP tool call timed out after 60s"):
                await client_with_session.call_tool(
                    "test-server",
                    "test_tool",
                    {"param": "value"},
                    "test-session"
                )
            
            # Should only attempt once (no retry on timeout)
            assert mock_session.call_tool.call_count == 1
    
    @pytest.mark.asyncio
    async def test_call_tool_timeout_triggers_recovery(self, client_with_session, mock_session):
        """Test that timeout does NOT trigger recovery - fails immediately per plan."""
        # Mock call_tool to raise TimeoutError
        mock_session.call_tool.side_effect = asyncio.TimeoutError()
        
        # Mock recovery to track if it's called (it should NOT be)
        recovery_called = False
        async def mock_recover(server_name):
            nonlocal recovery_called
            recovery_called = True
        
        client_with_session._recover_session = mock_recover
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "recovery-test-456"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            # Timeout should fail immediately without recovery
            with pytest.raises(TimeoutError, match="MCP tool call timed out after 60s"):
                await client_with_session.call_tool(
                    "test-server",
                    "test_tool",
                    {},
                    "test-session"
                )
            
            assert not recovery_called, "Recovery should NOT be attempted on timeout"
            assert mock_session.call_tool.call_count == 1
    
    @pytest.mark.asyncio
    async def test_call_tool_timeout_final_failure(self, client_with_session, mock_session):
        """Test that timeout failures are immediate without retry."""
        # Call times out
        mock_session.call_tool.side_effect = asyncio.TimeoutError()
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            # Timeout should fail immediately
            with pytest.raises(TimeoutError, match="MCP tool call timed out after 60s"):
                await client_with_session.call_tool(
                    "test-server",
                    "test_tool",
                    {},
                    "test-session"
                )
            
            # Should only attempt once (no retry on timeout)
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
        """Test that list_tools returns empty list immediately on timeout."""
        # Mock list_tools to raise TimeoutError
        mock_session.list_tools.side_effect = asyncio.TimeoutError()
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "list-timeout-123"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client_with_session.list_tools("test-session", "test-server")
            
            # Should return empty list immediately on timeout (no retry)
            assert result["test-server"] == []
            # Should only attempt once
            assert mock_session.list_tools.call_count == 1
    
    @pytest.mark.asyncio
    async def test_list_tools_timeout_all_servers(self, client_with_session, mock_session):
        """Test that list_tools returns empty list immediately on timeout."""
        # Mock list_tools to raise TimeoutError
        mock_session.list_tools.side_effect = asyncio.TimeoutError()
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "list-all-timeout-456"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client_with_session.list_tools("test-session")
            
            # Should return empty list immediately on timeout (no retry)
            assert result["test-server"] == []
            # Should only attempt once
            assert mock_session.list_tools.call_count == 1
    
    @pytest.mark.asyncio
    async def test_list_tools_timeout_triggers_recovery(self, client_with_session, mock_session):
        """Test that list_tools timeout does NOT trigger recovery - returns empty immediately."""
        # Mock list_tools to raise TimeoutError
        mock_session.list_tools.side_effect = asyncio.TimeoutError()
        
        # Mock recovery to track if it's called (it should NOT be)
        recovery_called = False
        async def mock_recover(server_name):
            nonlocal recovery_called
            recovery_called = True
        
        client_with_session._recover_session = mock_recover
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = "list-recovery-789"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            result = await client_with_session.list_tools("test-session", "test-server")
            
            # Should return empty list immediately without recovery
            assert result["test-server"] == []
            assert not recovery_called, "Recovery should NOT be attempted on timeout"
            assert mock_session.list_tools.call_count == 1
    
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
    "operation,server_name",
    [
        ("call_tool", "test-server"),
        ("list_tools", "test-server"),
        ("list_tools", None),  # All servers
    ],
)
class TestMCPClientTimeoutMatrix:
    """Test timeout behavior across different MCP operations - immediate failure per plan."""
    
    @pytest.mark.asyncio
    async def test_timeout_scenarios(self, operation, server_name):
        """Test timeout scenarios - all should fail immediately without retry."""
        mock_session = AsyncMock()
        
        # All operations timeout on first attempt
        if operation == "call_tool":
            mock_session.call_tool.side_effect = asyncio.TimeoutError()
        else:
            mock_session.list_tools.side_effect = asyncio.TimeoutError()
        
        registry = Mock()
        registry.get_server_config_safe.return_value = Mock(
            data_masking=Mock(enabled=False)
        )
        
        client = MCPClient(Mock(), registry)
        client.sessions = {"test-server": mock_session}
        client._initialized = True
        
        if operation == "call_tool":
            context_patch = 'tarsy.integrations.mcp.client.mcp_interaction_context'
        else:
            context_patch = 'tarsy.integrations.mcp.client.mcp_list_context'
        
        with patch(context_patch) as mock_context:
            mock_ctx = AsyncMock()
            mock_ctx.get_request_id.return_value = f"matrix-{operation}"
            mock_context.return_value.__aenter__.return_value = mock_ctx
            
            if operation == "call_tool":
                # call_tool should raise TimeoutError immediately
                with pytest.raises(TimeoutError, match="MCP tool call timed out after 60s"):
                    await client.call_tool(
                        "test-server", "tool", {}, "session"
                    )
                # Should only attempt once (no retry)
                assert mock_session.call_tool.call_count == 1
            else:  # list_tools
                # list_tools should return empty list immediately
                result = await client.list_tools("session", server_name)
                assert result["test-server"] == []
                # Should only attempt once (no retry)
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
                with pytest.raises(TimeoutError):
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
