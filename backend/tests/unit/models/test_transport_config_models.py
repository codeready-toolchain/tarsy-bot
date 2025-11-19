"""Unit tests for transport configuration Pydantic models."""

import pytest
from pydantic import ValidationError

from tarsy.models.mcp_transport_config import (
    TRANSPORT_STDIO,
    TRANSPORT_HTTP,
    BaseTransportConfig,
    StdioTransportConfig,
    HTTPTransportConfig
)


@pytest.mark.unit
class TestTransportConstants:
    """Test cases for transport type constants."""

    def test_constant_values(self):
        """Test that constants have correct values."""
        assert TRANSPORT_STDIO == "stdio"
        assert TRANSPORT_HTTP == "http"

    def test_constants_are_strings(self):
        """Test that constants are strings."""
        assert isinstance(TRANSPORT_STDIO, str)
        assert isinstance(TRANSPORT_HTTP, str)


@pytest.mark.unit  
class TestBaseTransportConfig:
    """Test cases for BaseTransportConfig validation."""

    def test_valid_base_config(self):
        """Test valid base transport configuration."""
        config_data = {
            "type": "stdio",
            "timeout": 30
        }
        
        config = BaseTransportConfig(**config_data)
        
        assert config.type == "stdio"
        assert config.timeout == 30

    def test_default_timeout(self):
        """Test default timeout value."""
        config_data = {
            "type": "http"
        }
        
        config = BaseTransportConfig(**config_data)
        
        assert config.timeout == 30

    def test_timeout_validation(self):
        """Test timeout validation boundaries."""
        # Valid timeout values
        valid_timeouts = [1, 30, 300]
        for timeout in valid_timeouts:
            config = BaseTransportConfig(type="stdio", timeout=timeout)
            assert config.timeout == timeout

        # Invalid timeout values  
        invalid_timeouts = [0, -1, 301]
        for timeout in invalid_timeouts:
            with pytest.raises(ValidationError):
                BaseTransportConfig(type="stdio", timeout=timeout)


@pytest.mark.unit
class TestStdioTransportConfig:
    """Test cases for StdioTransportConfig validation."""

    def test_valid_stdio_config(self):
        """Test valid stdio transport configuration."""
        config_data = {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "kubernetes-mcp-server@latest"],
            "env": {"MCP_KUBECONFIG": "/path/to/kubeconfig"},
            "timeout": 45
        }
        
        config = StdioTransportConfig(**config_data)
        
        assert config.type == "stdio"
        assert config.command == "npx"
        assert config.args == ["-y", "kubernetes-mcp-server@latest"]
        assert config.env == {"MCP_KUBECONFIG": "/path/to/kubeconfig"}
        assert config.timeout == 45

    def test_minimal_stdio_config(self):
        """Test minimal valid stdio configuration."""
        config_data = {
            "command": "kubectl"
        }
        
        config = StdioTransportConfig(**config_data)
        
        assert config.type == "stdio"  # Default value
        assert config.command == "kubectl"
        assert config.args == []  # Default empty list
        assert config.env == {}  # Default empty dict
        assert config.timeout == 30  # Default timeout

    def test_command_validation(self):
        """Test command field validation."""
        # Valid commands
        valid_commands = ["npx", "kubectl", "/usr/bin/python3"]
        for command in valid_commands:
            config = StdioTransportConfig(command=command)
            assert config.command == command

        # Invalid commands
        invalid_commands = ["", "   "]
        expected_errors = ["String should have at least 1 character", "Command cannot be empty"]
        for i, command in enumerate(invalid_commands):
            with pytest.raises(ValidationError, match=expected_errors[i]):
                StdioTransportConfig(command=command)

    def test_command_whitespace_stripping(self):
        """Test that command whitespace is stripped."""
        config = StdioTransportConfig(command="  npx  ")
        assert config.command == "npx"

    def test_serialization_roundtrip(self, model_test_helpers):
        """Test that stdio config can be serialized and deserialized correctly."""
        valid_data = {
            "command": "npx",
            "args": ["-y", "kubernetes-mcp-server@latest"],
            "env": {"MCP_KUBECONFIG": "/path/to/kubeconfig"}
        }
        
        model_test_helpers.test_serialization_roundtrip(StdioTransportConfig, valid_data)

    def test_json_serialization(self, model_test_helpers):
        """Test JSON serialization for stdio config."""
        valid_data = {
            "command": "kubectl",
            "args": ["get", "pods"],
            "env": {"NAMESPACE": "default"}
        }
        
        model_test_helpers.test_json_serialization(StdioTransportConfig, valid_data)


@pytest.mark.unit
class TestHTTPTransportConfig:
    """Test cases for HTTPTransportConfig validation."""

    def test_valid_http_config(self):
        """Test valid HTTP transport configuration."""
        config_data = {
            "type": "http",
            "url": "https://api.example.com/mcp",
            "bearer_token": "secret-token-12345",
            "headers": {"User-Agent": "tarsy/1.0"},
            "verify_ssl": True,
            "timeout": 60
        }
        
        config = HTTPTransportConfig(**config_data)
        
        assert config.type == "http"
        assert str(config.url) == "https://api.example.com/mcp"
        assert config.bearer_token == "secret-token-12345"
        assert config.headers == {"User-Agent": "tarsy/1.0"}
        assert config.verify_ssl is True
        assert config.timeout == 60

    def test_minimal_http_config(self):
        """Test minimal valid HTTP configuration."""
        config_data = {
            "url": "http://localhost:3000/mcp"
        }
        
        config = HTTPTransportConfig(**config_data)
        
        assert config.type == "http"  # Default value
        assert str(config.url) == "http://localhost:3000/mcp"
        assert config.bearer_token is None  # Default None
        assert config.headers == {}  # Default empty dict
        assert config.verify_ssl is True  # Default True
        assert config.timeout == 30  # Default timeout

    def test_url_validation(self):
        """Test URL field validation."""
        # Valid URLs
        valid_urls = [
            "http://localhost:3000/mcp",
            "https://api.example.com/mcp",
            "https://mcp-server.internal.company.com:8443/api/mcp"
        ]
        for url in valid_urls:
            config = HTTPTransportConfig(url=url)
            assert str(config.url) == url

        # Invalid URL schemes
        invalid_schemes = [
            "ftp://example.com/mcp",
            "file:///tmp/mcp",
            "ws://example.com/mcp"
        ]
        for url in invalid_schemes:
            with pytest.raises(ValidationError, match="URL scheme should be 'http' or 'https'"):
                HTTPTransportConfig(url=url)

        # Malformed URLs
        invalid_urls = ["not-a-url", "http://", ""]
        for url in invalid_urls:
            with pytest.raises(ValidationError):
                HTTPTransportConfig(url=url)

    def test_bearer_token_validation(self):
        """Test bearer token validation."""
        base_config = {"url": "https://api.example.com/mcp"}

        # Valid bearer tokens
        valid_tokens = [
            "simple-token",
            "token-with-dashes-123",
            "VeryLongTokenWith_underscores_and_NUMBERS_12345"
        ]
        for token in valid_tokens:
            config = HTTPTransportConfig(**base_config, bearer_token=token)
            assert config.bearer_token == token

        # Empty token should raise error
        with pytest.raises(ValidationError, match="String should have at least 1 character"):
            HTTPTransportConfig(**base_config, bearer_token="")

        # Whitespace-only token should raise error
        with pytest.raises(ValidationError, match="Bearer token cannot be empty"):
            HTTPTransportConfig(**base_config, bearer_token="   ")

        # Tokens with problematic characters
        invalid_tokens = [
            "token\nwith\nnewlines",
            "token\rwith\rcarriage\rreturns",
            "token\twith\ttabs"
        ]
        for token in invalid_tokens:
            with pytest.raises(ValidationError, match="cannot contain newlines, carriage returns, or tabs"):
                HTTPTransportConfig(**base_config, bearer_token=token)

        # Token stripping
        config = HTTPTransportConfig(**base_config, bearer_token="  token-with-spaces  ")
        assert config.bearer_token == "token-with-spaces"

        # None should be allowed
        config = HTTPTransportConfig(**base_config, bearer_token=None)
        assert config.bearer_token is None

    def test_headers_validation(self):
        """Test headers validation."""
        base_config = {"url": "https://api.example.com/mcp"}

        # Valid headers
        valid_headers = {
            "User-Agent": "tarsy/1.0",
            "Accept": "application/json",
            "Custom-Header": "custom-value"
        }
        config = HTTPTransportConfig(**base_config, headers=valid_headers)
        assert config.headers == valid_headers

        # Should reject manual Authorization header
        with pytest.raises(ValidationError, match="Use 'bearer_token' field instead"):
            HTTPTransportConfig(**base_config, headers={"Authorization": "Bearer token"})

        # Case-insensitive check for Authorization header
        with pytest.raises(ValidationError, match="Use 'bearer_token' field instead"):
            HTTPTransportConfig(**base_config, headers={"authorization": "Bearer token"})

        with pytest.raises(ValidationError, match="Use 'bearer_token' field instead"):
            HTTPTransportConfig(**base_config, headers={"AUTHORIZATION": "Bearer token"})

    def test_verify_ssl_validation(self):
        """Test verify_ssl field validation."""
        base_config = {"url": "https://api.example.com/mcp"}

        # Test explicit SSL verification settings
        config_ssl_true = HTTPTransportConfig(**base_config, verify_ssl=True)
        assert config_ssl_true.verify_ssl is True

        config_ssl_false = HTTPTransportConfig(**base_config, verify_ssl=False)
        assert config_ssl_false.verify_ssl is False

    def test_serialization_roundtrip(self, model_test_helpers):
        """Test that HTTP config can be serialized and deserialized correctly."""
        valid_data = {
            "url": "https://api.example.com/mcp",
            "bearer_token": "secret-token",
            "headers": {"User-Agent": "tarsy/1.0"},
            "verify_ssl": True,
            "timeout": 45
        }
        
        model_test_helpers.test_serialization_roundtrip(HTTPTransportConfig, valid_data)

    def test_json_serialization(self, model_test_helpers):
        """Test JSON serialization for HTTP config."""
        valid_data = {
            "url": "http://localhost:3000/mcp",
            "bearer_token": "dev-token",
            "verify_ssl": False
        }
        
        model_test_helpers.test_json_serialization(HTTPTransportConfig, valid_data)

    def test_production_https_config(self):
        """Test production-like HTTPS configuration."""
        config_data = {
            "url": "https://azure-mcp.example.com/mcp",
            "bearer_token": "prod-bearer-token-12345",
            "timeout": 30,
            "headers": {"User-Agent": "tarsy/1.0"},
            "verify_ssl": True
        }
        
        config = HTTPTransportConfig(**config_data)
        
        assert str(config.url) == "https://azure-mcp.example.com/mcp"
        assert config.bearer_token == "prod-bearer-token-12345"
        assert config.verify_ssl is True
        assert config.timeout == 30

    def test_development_http_config(self):
        """Test development-like HTTP configuration."""
        config_data = {
            "url": "http://localhost:3000/mcp",
            "bearer_token": "dev-token",
            "timeout": 10,
            "verify_ssl": False
        }
        
        config = HTTPTransportConfig(**config_data)
        
        assert str(config.url) == "http://localhost:3000/mcp"
        assert config.bearer_token == "dev-token"
        assert config.verify_ssl is False
        assert config.timeout == 10


@pytest.mark.unit
class TestTransportConfigIntegration:
    """Integration tests for transport configuration models."""

    def test_transport_type_consistency(self):
        """Test that transport types are consistent across configs."""
        stdio_config = StdioTransportConfig(command="kubectl")
        http_config = HTTPTransportConfig(url="https://api.example.com/mcp")
        
        assert stdio_config.type == "stdio"
        assert http_config.type == "http"
        assert stdio_config.type != http_config.type

    def test_discriminator_field_access(self):
        """Test that discriminator field is accessible for union resolution."""
        stdio_config = StdioTransportConfig(command="kubectl")
        http_config = HTTPTransportConfig(url="https://api.example.com/mcp")
        
        # Both configs should have 'type' field for discriminator
        assert hasattr(stdio_config, 'type')
        assert hasattr(http_config, 'type')
        
        # Type should be the correct string value
        assert isinstance(stdio_config.type, str)
        assert isinstance(http_config.type, str)

    def test_config_uniqueness(self):
        """Test that different transport configs have different structures."""
        stdio_config = StdioTransportConfig(command="kubectl")
        http_config = HTTPTransportConfig(url="https://api.example.com/mcp")
        
        # Stdio-specific fields
        assert hasattr(stdio_config, 'command')
        assert hasattr(stdio_config, 'args')
        assert hasattr(stdio_config, 'env')
        
        # HTTP-specific fields  
        assert hasattr(http_config, 'url')
        assert hasattr(http_config, 'bearer_token')
        assert hasattr(http_config, 'headers')
        assert hasattr(http_config, 'verify_ssl')
        
        # Cross-field checks
        assert not hasattr(stdio_config, 'url')
        assert not hasattr(http_config, 'command')
