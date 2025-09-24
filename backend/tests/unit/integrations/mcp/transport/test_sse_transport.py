"""
Tests for SSE transport implementation using official MCP SDK.

This module tests the SSE transport functionality including:
- MCP SDK sse_client integration
- Transport configuration and session management
- SSE-specific features (endpoint discovery, long timeouts)
"""

from unittest.mock import Mock, AsyncMock
import pytest
from mcp import ClientSession

from tarsy.integrations.mcp.transport.sse_transport import SSETransport
from tarsy.models.mcp_transport_config import SSETransportConfig, TRANSPORT_SSE


@pytest.mark.unit
class TestSSETransport:
    """Test SSE Transport implementation using MCP SDK."""

    @pytest.fixture
    def sse_config(self):
        """Create SSE transport configuration."""
        return SSETransportConfig(
            type=TRANSPORT_SSE,
            url="https://api.example.com/sse",
            bearer_token="sse-token-456",
            timeout=30.0,
            sse_read_timeout=600.0  # 10 minutes
        )

    @pytest.fixture
    def sse_transport(self, sse_config):
        """Create SSE transport instance."""
        return SSETransport("sse-server", sse_config)

    def test_init_creates_transport_correctly(self, sse_transport, sse_config):
        """Test SSE transport initialization."""
        assert sse_transport.server_id == "sse-server"
        assert sse_transport.config == sse_config
        assert sse_transport.session is None
        assert not sse_transport.is_connected
        
    async def test_create_session_returns_existing_session(self, sse_transport):
        """Test that create_session returns existing session if available."""
        existing_session = Mock(spec=ClientSession)
        sse_transport.session = existing_session
        
        result = await sse_transport.create_session()
        
        assert result == existing_session

    async def test_close_transport(self, sse_transport):
        """Test transport closure."""
        sse_transport._connected = True
        sse_transport.session = Mock()
        sse_transport.exit_stack = AsyncMock()
        
        await sse_transport.close()
        
        sse_transport.exit_stack.aclose.assert_called_once()
        assert not sse_transport._connected
        assert sse_transport.session is None

    async def test_close_transport_handles_errors(self, sse_transport):
        """Test transport closure error handling."""
        sse_transport._connected = True
        sse_transport.session = Mock()
        sse_transport.exit_stack = AsyncMock()
        sse_transport.exit_stack.aclose.side_effect = Exception("Close error")
        
        # Should not raise exception
        await sse_transport.close()
        
        assert not sse_transport._connected
        assert sse_transport.session is None

    def test_is_connected_property(self, sse_transport):
        """Test is_connected property."""
        # Initially not connected
        assert not sse_transport.is_connected
        
        # After setting connected and session
        sse_transport._connected = True
        sse_transport.session = Mock()
        assert sse_transport.is_connected
        
        # Only connected flag true
        sse_transport.session = None
        assert not sse_transport.is_connected
        
        # Only session set
        sse_transport._connected = False
        sse_transport.session = Mock()
        assert not sse_transport.is_connected

    def test_config_with_custom_headers(self):
        """Test configuration with custom headers."""
        config = SSETransportConfig(
            type=TRANSPORT_SSE,
            url="https://streaming.example.com/sse",
            bearer_token="sse-token",
            headers={"X-Client": "Tarsy", "User-Agent": "TarsyBot/1.0"},
            sse_read_timeout=300.0
        )
        transport = SSETransport("streaming-server", config)
        
        assert transport.config.headers == {"X-Client": "Tarsy", "User-Agent": "TarsyBot/1.0"}
        assert transport.config.sse_read_timeout == 300.0


@pytest.mark.unit 
class TestSSETransportConfig:
    """Test SSE transport configuration validation."""
    
    def test_valid_sse_config(self):
        """Test valid SSE transport configuration."""
        config = SSETransportConfig(
            type=TRANSPORT_SSE,
            url="https://streaming.example.com/sse",
            bearer_token="sse-token",
            timeout=45.0,
            sse_read_timeout=900.0,  # 15 minutes
            verify_ssl=True
        )
        
        assert config.type == TRANSPORT_SSE
        assert str(config.url) == "https://streaming.example.com/sse"
        assert config.bearer_token == "sse-token"
        assert config.timeout == 45.0
        assert config.sse_read_timeout == 900.0
        assert config.verify_ssl is True

    def test_config_inherits_from_http_based(self):
        """Test that SSETransportConfig inherits from HTTPBasedTransportConfig."""
        from tarsy.models.mcp_transport_config import HTTPBasedTransportConfig
        
        config = SSETransportConfig(
            type=TRANSPORT_SSE,
            url="https://streaming.example.com/sse"
        )
        
        assert isinstance(config, HTTPBasedTransportConfig)
        # Inherited fields
        assert hasattr(config, 'url')
        assert hasattr(config, 'bearer_token')
        assert hasattr(config, 'headers')
        assert hasattr(config, 'verify_ssl')
        assert hasattr(config, 'timeout')
        # SSE-specific field
        assert hasattr(config, 'sse_read_timeout')

    def test_default_values(self):
        """Test default configuration values."""
        config = SSETransportConfig(
            type=TRANSPORT_SSE,
            url="https://streaming.example.com/sse"
        )
        
        assert config.bearer_token is None
        assert config.headers == {}
        assert config.verify_ssl is True
        assert config.timeout == 30.0  # Inherited default
        assert config.sse_read_timeout == 300.0  # SSE-specific default (5 minutes)

    def test_sse_timeout_validation(self):
        """Test SSE read timeout validation."""
        # Valid timeout
        config = SSETransportConfig(
            type=TRANSPORT_SSE,
            url="https://streaming.example.com/sse",
            sse_read_timeout=600.0
        )
        assert config.sse_read_timeout == 600.0
        
        # Should fail if too small (minimum 10 seconds)
        with pytest.raises(ValueError):
            SSETransportConfig(
                type=TRANSPORT_SSE,
                url="https://streaming.example.com/sse",
                sse_read_timeout=5.0
            )

    def test_bearer_token_validation_inherited(self):
        """Test that bearer token validation is inherited from HTTPBasedTransportConfig."""
        # Valid token
        config = SSETransportConfig(
            type=TRANSPORT_SSE,
            url="https://streaming.example.com/sse",
            bearer_token="valid-sse-token-123"
        )
        assert config.bearer_token == "valid-sse-token-123"
        
        # Empty token should fail (inherited validation)
        with pytest.raises(ValueError, match="Bearer token cannot be empty"):
            SSETransportConfig(
                type=TRANSPORT_SSE,
                url="https://streaming.example.com/sse",
                bearer_token="   "
            )

    def test_headers_validation_inherited(self):
        """Test that headers validation is inherited from HTTPBasedTransportConfig."""
        # Valid headers
        config = SSETransportConfig(
            type=TRANSPORT_SSE,
            url="https://streaming.example.com/sse",
            headers={"X-Stream-Type": "events"}
        )
        assert config.headers == {"X-Stream-Type": "events"}
        
        # Should reject Authorization header (inherited validation)
        with pytest.raises(ValueError, match="Use 'bearer_token' field instead"):
            SSETransportConfig(
                type=TRANSPORT_SSE,
                url="https://streaming.example.com/sse",
                headers={"Authorization": "Bearer manual-token"}
            )
