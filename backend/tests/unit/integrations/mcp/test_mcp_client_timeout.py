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


class _DummyCtx:
    """Minimal async hook context stub used by MCPClient for unit tests."""

    def __init__(self, request_id: str):
        self._request_id = request_id
        # MCPClient expects ctx.interaction.* to be writable.
        self.interaction = Mock(communication_id=f"comm-{request_id}")

    def get_request_id(self) -> str:
        return self._request_id

    async def complete_success(self, _payload):  # noqa: ANN001
        return None

    async def _trigger_appropriate_hooks(self):  # noqa: D401
        return None


class _DummyAsyncCM:
    """Async context manager that returns the provided context object."""

    def __init__(self, ctx: _DummyCtx):
        self._ctx = ctx

    async def __aenter__(self) -> _DummyCtx:
        return self._ctx

    async def __aexit__(self, _exc_type, _exc, _tb):  # noqa: ANN001
        return False


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
        """Test that tool call times out after 60 seconds without automatic retry."""
        # Mock call_tool to raise TimeoutError
        mock_session.call_tool.side_effect = asyncio.TimeoutError()
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_context.return_value = _DummyAsyncCM(_DummyCtx("timeout-test-123"))
            
            with pytest.raises(TimeoutError, match="MCP tool call timed out after 60s"):
                await client_with_session.call_tool(
                    "test-server",
                    "test_tool",
                    {"param": "value"},
                    "test-session"
                )
            
            # Should only attempt once (no retry on operation timeout)
            assert mock_session.call_tool.call_count == 1
    
    @pytest.mark.asyncio
    async def test_call_tool_timeout_triggers_recovery(self, client_with_session, mock_session):
        """Test that timeout does not trigger recovery."""
        mock_session.call_tool.side_effect = asyncio.TimeoutError()

        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_context.return_value = _DummyAsyncCM(_DummyCtx("recovery-test-456"))
            
            with pytest.raises(TimeoutError, match="MCP tool call timed out after 60s"):
                await client_with_session.call_tool(
                    "test-server",
                    "test_tool",
                    {},
                    "test-session",
                )

            assert mock_session.call_tool.call_count == 1
    
    @pytest.mark.asyncio
    async def test_call_tool_timeout_final_failure(self, client_with_session, mock_session):
        """Test that timeout failures raise without retry."""
        mock_session.call_tool.side_effect = asyncio.TimeoutError()
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_context.return_value = _DummyAsyncCM(_DummyCtx("final-failure"))
            
            with pytest.raises(TimeoutError, match="MCP tool call timed out after 60s"):
                await client_with_session.call_tool(
                    "test-server",
                    "test_tool",
                    {},
                    "test-session"
                )
            
            assert mock_session.call_tool.call_count == 1
    
    @pytest.mark.asyncio
    async def test_call_tool_completes_within_timeout(self, client_with_session, mock_session):
        """Test that normal calls complete successfully within timeout."""
        mock_result = Mock()
        mock_result.content = [Mock(type="text", text="Quick response")]
        mock_session.call_tool.return_value = mock_result
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_context.return_value = _DummyAsyncCM(_DummyCtx("normal-test-789"))
            
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
        """Test that list_tools returns empty list without retry on operation timeout."""
        mock_session.list_tools.side_effect = asyncio.TimeoutError()
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_context.return_value = _DummyAsyncCM(_DummyCtx("list-timeout-123"))
            
            result = await client_with_session.list_tools("test-session", "test-server")
            
            # Should return empty list after retrying once
            assert result["test-server"] == []
            assert mock_session.list_tools.call_count == 1
    
    @pytest.mark.asyncio
    async def test_list_tools_timeout_all_servers(self, client_with_session, mock_session):
        """Test that list_tools returns empty list without retry on operation timeout."""
        mock_session.list_tools.side_effect = asyncio.TimeoutError()
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_context.return_value = _DummyAsyncCM(_DummyCtx("list-all-timeout-456"))
            
            result = await client_with_session.list_tools("test-session")
            
            # Should return empty list after retrying once
            assert result["test-server"] == []
            assert mock_session.list_tools.call_count == 1
    
    @pytest.mark.asyncio
    async def test_list_tools_timeout_triggers_recovery(self, client_with_session, mock_session):
        """Test that list_tools timeout does not trigger recovery."""
        mock_session.list_tools.side_effect = asyncio.TimeoutError()
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_context.return_value = _DummyAsyncCM(_DummyCtx("list-recovery-789"))
            
            result = await client_with_session.list_tools("test-session", "test-server")
            
            assert result["test-server"] == []
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
            mock_context.return_value = _DummyAsyncCM(_DummyCtx("list-normal-101"))
            
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
    """Test timeout behavior across different MCP operations - no retry on operation timeout."""
    
    @pytest.mark.asyncio
    async def test_timeout_scenarios(self, operation, server_name):
        """Test timeout scenarios - all should fail/empty without retry."""
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
            mock_context.return_value = _DummyAsyncCM(_DummyCtx(f"matrix-{operation}"))
            
            if operation == "call_tool":
                with pytest.raises(TimeoutError, match="MCP tool call timed out after 60s"):
                    await client.call_tool(
                        "test-server", "tool", {}, "session"
                    )
                assert mock_session.call_tool.call_count == 1
            else:  # list_tools
                result = await client.list_tools("session", server_name)
                assert result["test-server"] == []
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
        
        with patch('tarsy.integrations.mcp.client.mcp_interaction_context') as mock_context:
            mock_context.return_value = _DummyAsyncCM(_DummyCtx("log-timeout-call-tool"))
            
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
        # Ensure list_tools(server_name=...) treats server as configured/enabled
        client.mcp_registry.get_server_config_safe.return_value = Mock(enabled=True)
        
        with patch('tarsy.integrations.mcp.client.mcp_list_context') as mock_context:
            mock_context.return_value = _DummyAsyncCM(_DummyCtx("log-timeout-list-tools"))
            
            await client.list_tools("session", "test-server")
        
        # Verify timeout was logged
        assert any("List tools timed out" in record.message or "timed out after 60s" in record.message for record in caplog.records)
