"""
Tests for Stdio transport implementation using official MCP SDK.

This module tests the stdio transport functionality including:
- MCP SDK stdio_client integration
- Transport configuration and session management  
- Subprocess and stream management via AsyncExitStack
- Error handling scenarios
"""

from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp import ClientSession

from tarsy.integrations.mcp.transport.stdio_transport import StdioTransport
from tarsy.models.mcp_transport_config import TRANSPORT_STDIO, StdioTransportConfig


@pytest.mark.unit
class TestStdioTransport:
    """Test Stdio Transport implementation using MCP SDK."""

    @pytest.fixture
    def stdio_config(self):
        """Create Stdio transport configuration."""
        return StdioTransportConfig(
            type=TRANSPORT_STDIO,
            command="python",
            args=["-m", "test_server"],
            env={"TEST_VAR": "test_value"},
            timeout=30
        )

    @pytest.fixture
    def exit_stack(self):
        """Create mock AsyncExitStack."""
        return AsyncMock(spec=AsyncExitStack)

    @pytest.fixture
    def stdio_transport(self, stdio_config, exit_stack):
        """Create Stdio transport instance."""
        return StdioTransport("test-server", stdio_config, exit_stack)

    def test_init_creates_transport_correctly(self, stdio_transport, stdio_config, exit_stack):
        """Test Stdio transport initialization."""
        assert stdio_transport.server_id == "test-server"
        assert stdio_transport.config == stdio_config
        assert stdio_transport.exit_stack == exit_stack
        assert stdio_transport.session is None
        assert not stdio_transport.is_connected
        assert not stdio_transport._connected

    async def test_create_session_returns_existing_session(self, stdio_transport):
        """Test that create_session returns existing session if available."""
        existing_session = Mock(spec=ClientSession)
        stdio_transport.session = existing_session
        
        result = await stdio_transport.create_session()
        
        assert result == existing_session

    @patch('tarsy.integrations.mcp.transport.stdio_transport.stdio_client')
    @patch('tarsy.integrations.mcp.transport.stdio_transport.ClientSession')
    @patch('tarsy.integrations.mcp.transport.stdio_transport.StdioServerParameters')
    async def test_create_session_creates_new_session(
        self, mock_stdio_params, mock_client_session, mock_stdio_client, stdio_transport
    ):
        """Test creating new stdio session with proper MCP SDK integration."""
        # Setup mocks
        mock_stdio_context = AsyncMock()
        mock_stdio_client.return_value = mock_stdio_context
        
        mock_read_stream = Mock()
        mock_write_stream = Mock()
        mock_streams = (mock_read_stream, mock_write_stream)
        stdio_transport.exit_stack.enter_async_context.side_effect = [mock_streams, Mock()]
        
        mock_session = AsyncMock(spec=ClientSession)
        mock_session_context = AsyncMock()
        mock_session_context.__aenter__.return_value = mock_session
        mock_client_session.return_value = mock_session_context
        
        # Return session from second enter_async_context call
        stdio_transport.exit_stack.enter_async_context.side_effect = [mock_streams, mock_session]
        
        # Execute
        result = await stdio_transport.create_session()
        
        # Verify StdioServerParameters creation
        mock_stdio_params.assert_called_once_with(
            command="python",
            args=["-m", "test_server"],
            env={"TEST_VAR": "test_value"}
        )
        
        # Verify stdio_client call
        mock_stdio_client.assert_called_once_with(mock_stdio_params.return_value)
        
        # Verify exit_stack usage
        assert stdio_transport.exit_stack.enter_async_context.call_count == 2
        
        # Verify ClientSession creation  
        mock_client_session.assert_called_once_with(mock_read_stream, mock_write_stream)
        
        # Verify session initialization
        mock_session.initialize.assert_called_once()
        
        # Verify state updates
        assert stdio_transport.session == mock_session
        assert stdio_transport._connected is True
        assert result == mock_session

    @patch('tarsy.integrations.mcp.transport.stdio_transport.stdio_client')
    @patch('tarsy.integrations.mcp.transport.stdio_transport.ClientSession') 
    @patch('tarsy.integrations.mcp.transport.stdio_transport.StdioServerParameters')
    async def test_create_session_handles_config_without_optional_fields(
        self, mock_stdio_params, mock_client_session, mock_stdio_client, exit_stack
    ):
        """Test session creation with minimal configuration."""
        # Create config without args and env
        config = StdioTransportConfig(
            type=TRANSPORT_STDIO,
            command="test-command"
        )
        transport = StdioTransport("test-server", config, exit_stack)
        
        # Setup mocks
        mock_stdio_context = AsyncMock()
        mock_stdio_client.return_value = mock_stdio_context
        
        mock_streams = (Mock(), Mock())
        mock_session = AsyncMock(spec=ClientSession)
        exit_stack.enter_async_context.side_effect = [mock_streams, mock_session]
        
        # Execute
        await transport.create_session()
        
        # Verify StdioServerParameters called with empty defaults
        mock_stdio_params.assert_called_once_with(
            command="test-command",
            args=[],
            env={}
        )

    @patch('tarsy.integrations.mcp.transport.stdio_transport.stdio_client')
    async def test_create_session_handles_initialization_error(
        self, mock_stdio_client, stdio_transport
    ):
        """Test error handling during session initialization."""
        # Setup mocks to fail during session initialization
        mock_streams = (Mock(), Mock())
        mock_session = AsyncMock(spec=ClientSession)
        mock_session.initialize.side_effect = Exception("Initialization failed")
        
        stdio_transport.exit_stack.enter_async_context.side_effect = [mock_streams, mock_session]
        
        # Should propagate the exception
        with pytest.raises(Exception, match="Initialization failed"):
            await stdio_transport.create_session()

    async def test_close_transport_when_connected(self, stdio_transport):
        """Test transport closure when connected."""
        stdio_transport._connected = True
        stdio_transport.session = Mock()
        
        await stdio_transport.close()
        
        stdio_transport.exit_stack.aclose.assert_called_once()
        assert not stdio_transport._connected
        assert stdio_transport.session is None

    async def test_close_transport_when_not_connected(self, stdio_transport):
        """Test transport closure when not connected."""
        stdio_transport._connected = False
        stdio_transport.session = None
        
        await stdio_transport.close()
        
        # Should not call aclose when not connected
        stdio_transport.exit_stack.aclose.assert_not_called()

    async def test_close_transport_handles_errors(self, stdio_transport):
        """Test transport closure error handling."""
        stdio_transport._connected = True
        stdio_transport.session = Mock()
        stdio_transport.exit_stack.aclose.side_effect = Exception("Close error")
        
        # Should not raise exception
        await stdio_transport.close()
        
        assert not stdio_transport._connected
        assert stdio_transport.session is None

    def test_is_connected_property_various_states(self, stdio_transport):
        """Test is_connected property in various states."""
        # Initially not connected
        assert not stdio_transport.is_connected
        
        # After setting connected and session
        stdio_transport._connected = True
        stdio_transport.session = Mock()
        assert stdio_transport.is_connected
        
        # Only connected flag true
        stdio_transport.session = None
        assert not stdio_transport.is_connected
        
        # Only session set
        stdio_transport._connected = False
        stdio_transport.session = Mock()
        assert not stdio_transport.is_connected

    def test_config_with_comprehensive_settings(self):
        """Test configuration with all possible settings."""
        config = StdioTransportConfig(
            type=TRANSPORT_STDIO,
            command="/usr/bin/python3",
            args=["--version", "--verbose"],
            env={"PATH": "/custom/path", "DEBUG": "1"},
            timeout=60
        )
        exit_stack = AsyncMock(spec=AsyncExitStack)
        transport = StdioTransport("comprehensive-server", config, exit_stack)
        
        assert transport.config.command == "/usr/bin/python3"
        assert transport.config.args == ["--version", "--verbose"]
        assert transport.config.env == {"PATH": "/custom/path", "DEBUG": "1"}
        assert transport.config.timeout == 60


@pytest.mark.unit 
class TestStdioTransportIntegration:
    """Integration tests for Stdio transport with configuration validation."""
    
    def test_transport_with_valid_stdio_config(self):
        """Test transport creation with valid stdio configuration."""
        config = StdioTransportConfig(
            type=TRANSPORT_STDIO,
            command="node",
            args=["server.js"],
            env={"NODE_ENV": "development"},
            timeout=45
        )
        exit_stack = AsyncMock(spec=AsyncExitStack)
        transport = StdioTransport("node-server", config, exit_stack)
        
        assert transport.server_id == "node-server"
        assert transport.config.type == TRANSPORT_STDIO
        assert transport.config.command == "node"
        assert transport.config.args == ["server.js"]
        assert transport.config.env == {"NODE_ENV": "development"}
        assert transport.config.timeout == 45

    def test_transport_inherits_from_mcp_transport(self):
        """Test that StdioTransport implements MCPTransport interface."""
        from tarsy.integrations.mcp.transport.factory import MCPTransport
        
        config = StdioTransportConfig(
            type=TRANSPORT_STDIO,
            command="test-command"
        )
        exit_stack = AsyncMock(spec=AsyncExitStack)
        transport = StdioTransport("test-server", config, exit_stack)
        
        assert isinstance(transport, MCPTransport)
        assert hasattr(transport, 'create_session')
        assert hasattr(transport, 'close')
        assert hasattr(transport, 'is_connected')

    async def test_session_lifecycle_complete_flow(self):
        """Test complete session lifecycle from creation to closure."""
        config = StdioTransportConfig(
            type=TRANSPORT_STDIO,
            command="echo",
            args=["hello"]
        )
        exit_stack = AsyncMock(spec=AsyncExitStack)
        transport = StdioTransport("lifecycle-test", config, exit_stack)
        
        # Initial state
        assert not transport.is_connected
        assert transport.session is None
        
        # Mock the session creation
        with patch('tarsy.integrations.mcp.transport.stdio_transport.stdio_client'), \
             patch('tarsy.integrations.mcp.transport.stdio_transport.ClientSession'):
            
            mock_streams = (Mock(), Mock())
            mock_session = AsyncMock(spec=ClientSession)
            exit_stack.enter_async_context.side_effect = [mock_streams, mock_session]
            
            # Create session
            session = await transport.create_session()
            assert transport.is_connected
            assert session == mock_session
            
            # Close transport
            await transport.close()
            assert not transport.is_connected
            assert transport.session is None
            exit_stack.aclose.assert_called_once()
