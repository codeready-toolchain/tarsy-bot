"""Integration tests for agent configuration models with transport support."""

import pytest
from pydantic import ValidationError

from tarsy.models.agent_config import CombinedConfigModel, MCPServerConfigModel
from tarsy.models.mcp_transport_config import HTTPTransportConfig, StdioTransportConfig


@pytest.mark.unit
class TestTransportConfigDiscrimination:
    """Test cases for discriminated union transport configuration."""

    def test_stdio_transport_discrimination(self):
        """Test that stdio transport is correctly identified by discriminator."""
        server_config_data = {
            "server_id": "kubernetes-server",
            "server_type": "kubernetes", 
            "enabled": True,
            "transport": {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "kubernetes-mcp-server@latest"],
                "env": {"KUBECONFIG": "/path/to/kubeconfig"}
            }
        }
        
        server_config = MCPServerConfigModel(**server_config_data)
        
        # Check that transport is correctly typed
        assert isinstance(server_config.transport, StdioTransportConfig)
        assert server_config.transport.type == "stdio"
        assert server_config.transport.command == "npx"
        assert server_config.transport.args == ["-y", "kubernetes-mcp-server@latest"]

    def test_http_transport_discrimination(self):
        """Test that HTTP transport is correctly identified by discriminator."""
        server_config_data = {
            "server_id": "azure-mcp-server",
            "server_type": "azure",
            "enabled": True,
            "transport": {
                "type": "http",
                "url": "https://azure-mcp.example.com/mcp",
                "bearer_token": "secret-token",
                "verify_ssl": True
            }
        }
        
        server_config = MCPServerConfigModel(**server_config_data)
        
        # Check that transport is correctly typed
        assert isinstance(server_config.transport, HTTPTransportConfig)
        assert server_config.transport.type == "http"
        assert str(server_config.transport.url) == "https://azure-mcp.example.com/mcp"
        assert server_config.transport.bearer_token == "secret-token"

    def test_explicit_stdio_transport_required(self):
        """Test that stdio transport requires explicit type field."""
        server_config_data = {
            "server_id": "kubernetes-server",
            "server_type": "kubernetes",
            "enabled": True,
            "transport": {
                "command": "kubectl",  # Missing type field - should fail
                "args": ["proxy", "--port=8001"]
            }
        }
        
        with pytest.raises(ValidationError, match="Unable to extract tag using discriminator"):
            MCPServerConfigModel(**server_config_data)

    def test_explicit_http_transport_required(self):
        """Test that HTTP transport requires explicit type field."""
        server_config_data = {
            "server_id": "local-dev-server",
            "server_type": "development", 
            "enabled": True,
            "transport": {
                "url": "http://localhost:3000/mcp"  # Missing type field - should fail
            }
        }
        
        with pytest.raises(ValidationError, match="Unable to extract tag using discriminator"):
            MCPServerConfigModel(**server_config_data)

    def test_invalid_transport_type_discrimination(self):
        """Test that invalid transport types are rejected."""
        server_config_data = {
            "server_id": "invalid-server",
            "server_type": "invalid",
            "enabled": True,
            "transport": {
                "type": "invalid-transport-type",
                "some_field": "some_value"
            }
        }
        
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfigModel(**server_config_data)
        
        # Should contain transport type validation error
        assert "type" in str(exc_info.value)

    def test_conflicting_transport_fields(self):
        """Test that conflicting transport fields are handled correctly."""
        # With discriminated union, stdio type ignores HTTP-specific fields
        conflicting_config_data = {
            "server_id": "conflicted-server",
            "server_type": "test",
            "enabled": True,
            "transport": {
                "type": "stdio",
                "command": "kubectl",
                "url": "https://example.com/mcp"  # HTTP field ignored in stdio config
            }
        }
        
        # Should succeed - extra fields are ignored by Pydantic discriminated union
        server_config = MCPServerConfigModel(**conflicting_config_data)
        assert isinstance(server_config.transport, StdioTransportConfig)
        assert server_config.transport.type == "stdio"
        assert server_config.transport.command == "kubectl"


@pytest.mark.unit
class TestMCPServerConfigModelTransport:
    """Test cases for MCPServerConfigModel with transport configurations."""

    def test_complete_stdio_server_config(self):
        """Test complete server configuration with stdio transport."""
        config_data = {
            "server_id": "kubernetes-server",
            "server_type": "kubernetes",
            "enabled": True,
            "transport": {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "kubernetes-mcp-server@latest"],
                "env": {"KUBECONFIG": "/path/to/kubeconfig"},
                "timeout": 45
            },
            "instructions": "Kubernetes MCP server for cluster management.",
            "data_masking": {
                "enabled": True,
                "pattern_groups": ["security"],
                "patterns": ["api_keys"]
            }
        }
        
        server_config = MCPServerConfigModel(**config_data)
        
        assert server_config.server_id == "kubernetes-server"
        assert server_config.server_type == "kubernetes"
        assert server_config.enabled is True
        assert isinstance(server_config.transport, StdioTransportConfig)
        assert server_config.transport.command == "npx"
        assert server_config.instructions == "Kubernetes MCP server for cluster management."

    def test_complete_http_server_config(self):
        """Test complete server configuration with HTTP transport."""
        config_data = {
            "server_id": "azure-mcp-server", 
            "server_type": "azure",
            "enabled": True,
            "transport": {
                "type": "http",
                "url": "https://azure-mcp.example.com/mcp",
                "bearer_token": "prod-bearer-token-12345",
                "timeout": 30,
                "headers": {"User-Agent": "tarsy/1.0"},
                "verify_ssl": True
            },
            "instructions": "Azure MCP server with bearer token authentication."
        }
        
        server_config = MCPServerConfigModel(**config_data)
        
        assert server_config.server_id == "azure-mcp-server"
        assert server_config.server_type == "azure"
        assert isinstance(server_config.transport, HTTPTransportConfig)
        assert str(server_config.transport.url) == "https://azure-mcp.example.com/mcp"
        assert server_config.transport.bearer_token == "prod-bearer-token-12345"

    def test_server_config_serialization(self, model_test_helpers):
        """Test server configuration serialization with transport."""
        config_data = {
            "server_id": "test-server",
            "server_type": "test",
            "transport": {
                "type": "http",
                "url": "https://test.example.com/mcp",
                "bearer_token": "test-token"
            }
        }
        
        model_test_helpers.test_serialization_roundtrip(MCPServerConfigModel, config_data)

    def test_server_config_json_serialization(self, model_test_helpers):
        """Test server configuration JSON serialization with transport."""
        config_data = {
            "server_id": "test-server",
            "server_type": "test", 
            "transport": {
                "type": "stdio",  # Add missing type field
                "command": "kubectl",
                "args": ["proxy"]
            }
        }
        
        model_test_helpers.test_json_serialization(MCPServerConfigModel, config_data)


@pytest.mark.unit
class TestCombinedConfigModelTransport:
    """Test cases for CombinedConfigModel with new transport configurations."""

    def test_mixed_transport_types_config(self):
        """Test combined configuration with mixed transport types."""
        config_data = {
            "mcp_servers": {
                "kubernetes-stdio": {
                    "server_id": "kubernetes-stdio",
                    "server_type": "kubernetes",
                    "enabled": True,
                    "transport": {
                        "type": "stdio",
                        "command": "npx",
                        "args": ["-y", "kubernetes-mcp-server@latest"]
                    }
                },
                "azure-http": {
                    "server_id": "azure-http",
                    "server_type": "azure", 
                    "enabled": True,
                    "transport": {
                        "type": "http",
                        "url": "https://azure-mcp.example.com/mcp",
                        "bearer_token": "secret-token"
                    }
                },
                "local-http": {
                    "server_id": "local-http",
                    "server_type": "development",
                    "enabled": True,
                    "transport": {
                        "type": "http",
                        "url": "http://localhost:3000/mcp",
                        "verify_ssl": False
                    }
                }
            },
            "agents": {
                "mixed-agent": {
                    "mcp_servers": ["kubernetes-stdio", "azure-http", "local-http"],
                    "custom_instructions": "Agent using mixed transport types."
                }
            },
            "agent_chains": {
                "mixed-chain": {
                    "chain_id": "mixed-chain",
                    "alert_types": ["mixed"],
                    "stages": [{
                        "name": "analysis",
                        "agent": "mixed-agent"
                    }]
                }
            }
        }
        
        combined_config = CombinedConfigModel(**config_data)
        
        # Verify transport types are preserved
        k8s_server = combined_config.mcp_servers["kubernetes-stdio"]
        azure_server = combined_config.mcp_servers["azure-http"]
        local_server = combined_config.mcp_servers["local-http"]
        
        assert isinstance(k8s_server.transport, StdioTransportConfig)
        assert isinstance(azure_server.transport, HTTPTransportConfig)
        assert isinstance(local_server.transport, HTTPTransportConfig)
        
        # Verify specific transport configurations
        assert k8s_server.transport.command == "npx"
        assert str(azure_server.transport.url) == "https://azure-mcp.example.com/mcp"
        assert str(local_server.transport.url) == "http://localhost:3000/mcp"
        assert local_server.transport.verify_ssl is False

    def test_combined_config_validation_with_transport(self):
        """Test combined configuration validation still works with new transport model."""
        config_data = {
            "mcp_servers": {
                "test-server": {
                    "server_id": "wrong-id",  # Should cause validation error
                    "server_type": "test",
                    "transport": {
                        "type": "stdio",  # Add missing type field
                        "command": "test-command"
                    }
                }
            }
        }
        
        with pytest.raises(ValidationError, match="does not match server_id"):
            CombinedConfigModel(**config_data)


@pytest.mark.unit
class TestTransportConfigBoundaryConditions:
    """Test boundary conditions and edge cases for transport configurations."""

    def test_empty_environment_variables(self):
        """Test stdio transport with empty environment variables."""
        config_data = {
            "server_id": "test-server",
            "server_type": "test",
            "transport": {
                "type": "stdio",  # Add missing type field
                "command": "test-command",
                "env": {}  # Explicitly empty
            }
        }
        
        server_config = MCPServerConfigModel(**config_data)
        assert server_config.transport.env == {}

    def test_empty_headers(self):
        """Test HTTP transport with empty headers."""
        config_data = {
            "server_id": "test-server", 
            "server_type": "test",
            "transport": {
                "type": "http",  # Add missing type field
                "url": "https://example.com/mcp",
                "headers": {}  # Explicitly empty
            }
        }
        
        server_config = MCPServerConfigModel(**config_data)
        assert server_config.transport.headers == {}

    def test_maximum_timeout_values(self):
        """Test transport configurations with maximum timeout values."""
        stdio_config_data = {
            "server_id": "stdio-server",
            "server_type": "test", 
            "transport": {
                "type": "stdio",  # Add missing type field
                "command": "test",
                "timeout": 300  # Maximum allowed
            }
        }
        
        http_config_data = {
            "server_id": "http-server",
            "server_type": "test",
            "transport": {
                "type": "http",  # Add missing type field
                "url": "https://example.com/mcp",
                "timeout": 300  # Maximum allowed
            }
        }
        
        stdio_config = MCPServerConfigModel(**stdio_config_data)
        http_config = MCPServerConfigModel(**http_config_data)
        
        assert stdio_config.transport.timeout == 300
        assert http_config.transport.timeout == 300

    def test_minimum_timeout_values(self):
        """Test transport configurations with minimum timeout values."""
        config_data = {
            "server_id": "test-server",
            "server_type": "test",
            "transport": {
                "type": "stdio",  # Add missing type field
                "command": "test",
                "timeout": 1  # Minimum allowed
            }
        }
        
        server_config = MCPServerConfigModel(**config_data)
        assert server_config.transport.timeout == 1
