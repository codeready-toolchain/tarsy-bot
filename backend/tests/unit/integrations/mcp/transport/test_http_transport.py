"""
Tests for HTTP transport implementation using official MCP SDK.

This module tests the HTTP transport functionality including:
- MCP SDK streamablehttp_client integration
- Transport configuration and session management  
- Error handling scenarios
"""

from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from mcp import ClientSession
from unittest.mock import patch

from tarsy.integrations.mcp.transport.http_transport import HTTPTransport
from tarsy.models.mcp_transport_config import TRANSPORT_HTTP, HTTPTransportConfig


@pytest.mark.unit
class TestHTTPTransport:
    """Test HTTP Transport implementation using MCP SDK."""

    @pytest.fixture
    def http_config(self):
        """Create HTTP transport configuration."""
        return HTTPTransportConfig(
            type=TRANSPORT_HTTP,
            url="http://localhost:8081/mcp",
            bearer_token="test-token-123",
            timeout=30.0,
            verify_ssl=False
        )

    @pytest.fixture
    def http_transport(self, http_config):
        """Create HTTP transport instance."""
        return HTTPTransport("test-server", http_config)

    def test_init_creates_transport_correctly(self, http_transport, http_config):
        """Test HTTP transport initialization."""
        assert http_transport.server_id == "test-server"
        assert http_transport.config == http_config
        assert http_transport.session is None
        assert not http_transport.is_connected

    async def test_create_session_returns_existing_session(self, http_transport):
        """Test that create_session returns existing session if available."""
        existing_session = Mock(spec=ClientSession)
        http_transport.session = existing_session
        
        result = await http_transport.create_session()
        
        assert result == existing_session

    async def test_close_transport(self, http_transport):
        """Test transport closure."""
        http_transport._connected = True
        http_transport.session = Mock()
        http_transport.exit_stack = AsyncMock()
        
        await http_transport.close()
        
        http_transport.exit_stack.aclose.assert_called_once()
        assert not http_transport._connected
        assert http_transport.session is None

    async def test_close_transport_handles_errors(self, http_transport):
        """Test transport closure error handling.

        Only known-safe teardown errors should be suppressed; unexpected errors should surface.
        """
        http_transport._connected = True
        http_transport.session = Mock()
        http_transport.exit_stack = AsyncMock()
        http_transport.exit_stack.aclose.side_effect = Exception("Close error")
        
        with pytest.raises(Exception, match="Close error"):
            await http_transport.close()
        
        assert not http_transport._connected
        assert http_transport.session is None

    async def test_close_transport_suppresses_cancel_scope_mismatch(self, http_transport):
        """Test that the known AnyIO cancel-scope mismatch error is suppressed on close."""
        http_transport._connected = True
        http_transport.session = Mock()
        http_transport.exit_stack = AsyncMock()
        http_transport.exit_stack.aclose.side_effect = RuntimeError(
            "Attempted to exit cancel scope in a different task than it was entered in"
        )

        await http_transport.close()

        assert not http_transport._connected
        assert http_transport.session is None

    async def test_close_transport_suppresses_safe_exception_group(self, http_transport):
        """Test that safe exception groups produced by MCP SDK teardown are suppressed."""
        http_transport._connected = True
        http_transport.session = Mock()
        http_transport.exit_stack = AsyncMock()

        req = httpx.Request("POST", "http://example.com/mcp")
        eg = BaseExceptionGroup(
            "teardown",
            [
                httpx.ConnectError("All connection attempts failed", request=req),
                RuntimeError("Attempted to exit cancel scope in a different task than it was entered in"),
            ],
        )
        http_transport.exit_stack.aclose.side_effect = eg

        await http_transport.close()

        assert not http_transport._connected
        assert http_transport.session is None

    async def test_create_session_failed_aenter_calls_aexit_to_avoid_asyncgen_finalizer(
        self, http_transport
    ) -> None:
        """If streamablehttp_client.__aenter__ fails, we should still call __aexit__ best-effort."""
        http_transport.exit_stack = AsyncMock()

        cm = AsyncMock()
        cm.__aenter__.side_effect = httpx.ConnectError(
            "All connection attempts failed",
            request=httpx.Request("POST", "http://localhost:8081/mcp"),
        )

        with patch(
            "tarsy.integrations.mcp.transport.http_transport.streamablehttp_client",
            return_value=cm,
        ):
            with pytest.raises(Exception, match="Failed to create HTTP session"):
                await http_transport.create_session()

        cm.__aexit__.assert_called_once()

    def test_is_connected_property(self, http_transport):
        """Test is_connected property."""
        # Initially not connected
        assert not http_transport.is_connected
        
        # After setting connected and session
        http_transport._connected = True
        http_transport.session = Mock()
        assert http_transport.is_connected
        
        # Only connected flag true
        http_transport.session = None
        assert not http_transport.is_connected
        
        # Only session set
        http_transport._connected = False
        http_transport.session = Mock()
        assert not http_transport.is_connected

    def test_config_with_custom_headers(self):
        """Test configuration with custom headers."""
        config = HTTPTransportConfig(
            type=TRANSPORT_HTTP,
            url="http://localhost:8081/mcp",
            bearer_token="test-token",
            headers={"Custom-Header": "value", "User-Agent": "TestAgent"}
        )
        transport = HTTPTransport("test-server", config)
        
        assert transport.config.headers == {"Custom-Header": "value", "User-Agent": "TestAgent"}


@pytest.mark.unit 
class TestHTTPTransportConfig:
    """Test HTTP transport configuration validation."""
    
    def test_valid_http_config(self):
        """Test valid HTTP transport configuration."""
        config = HTTPTransportConfig(
            type=TRANSPORT_HTTP,
            url="https://api.example.com/mcp",
            bearer_token="valid-token",
            timeout=45.0,
            verify_ssl=True
        )
        
        assert config.type == TRANSPORT_HTTP
        assert str(config.url) == "https://api.example.com/mcp"
        assert config.bearer_token == "valid-token"
        assert config.timeout == 45.0
        assert config.verify_ssl is True

    def test_config_inherits_from_http_based(self):
        """Test that HTTPTransportConfig inherits from HTTPBasedTransportConfig."""
        from tarsy.models.mcp_transport_config import HTTPBasedTransportConfig
        
        config = HTTPTransportConfig(
            type=TRANSPORT_HTTP,
            url="http://localhost:8081/mcp"
        )
        
        assert isinstance(config, HTTPBasedTransportConfig)
        assert hasattr(config, 'url')
        assert hasattr(config, 'bearer_token')
        assert hasattr(config, 'headers')
        assert hasattr(config, 'verify_ssl')
        assert hasattr(config, 'timeout')

    def test_default_values(self):
        """Test default configuration values."""
        config = HTTPTransportConfig(
            type=TRANSPORT_HTTP,
            url="http://localhost:8081/mcp"
        )
        
        assert config.bearer_token is None
        assert config.headers == {}
        assert config.verify_ssl is True
        assert config.timeout == 30.0

    def test_bearer_token_validation(self):
        """Test bearer token validation."""
        # Valid token
        config = HTTPTransportConfig(
            type=TRANSPORT_HTTP,
            url="http://localhost:8081/mcp",
            bearer_token="valid-token-123"
        )
        assert config.bearer_token == "valid-token-123"
        
        # Empty token should fail
        with pytest.raises(ValueError, match="Bearer token cannot be empty"):
            HTTPTransportConfig(
                type=TRANSPORT_HTTP,
                url="http://localhost:8081/mcp",
                bearer_token="   "
            )

    def test_headers_validation(self):
        """Test headers validation."""
        # Valid headers
        config = HTTPTransportConfig(
            type=TRANSPORT_HTTP,
            url="http://localhost:8081/mcp",
            headers={"Custom-Header": "value"}
        )
        assert config.headers == {"Custom-Header": "value"}
        
        # Should reject Authorization header
        with pytest.raises(ValueError, match="Use 'bearer_token' field instead"):
            HTTPTransportConfig(
                type=TRANSPORT_HTTP,
                url="http://localhost:8081/mcp",
                headers={"Authorization": "Bearer manual-token"}
            )
