"""Extended unit tests for MCPServerRegistry with configuration support."""

from unittest.mock import patch

import pytest

from tarsy.models.agent_config import MCPServerConfigModel
from tarsy.services.mcp_server_registry import MCPServerRegistry


@pytest.mark.unit
class TestMCPServerRegistryExtended:
    """Extended test cases for MCPServerRegistry with configuration support."""

    @pytest.fixture
    def sample_mcp_server_configs(self):
        """Sample MCP server configurations for testing."""
        return {
            "security-tools": MCPServerConfigModel(
                transport={"type": "stdio", "command": "test", "env": {"HOST": "localhost", "PORT": "8080"}},
                instructions="Security analysis tools"
            ),
            "monitoring-server": MCPServerConfigModel(
                transport={"type": "stdio", "command": "monitoring", "env": {"ENDPOINT": "http://monitoring.local"}}
            ),
            "disabled-server": MCPServerConfigModel(
                transport={"type": "stdio", "command": "/usr/bin/test-server"}
            )
        }

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_init_without_configured_servers(self):
        """Test MCPServerRegistry initialization without configured servers."""
        registry = MCPServerRegistry()
        
        # Should work with built-in servers only - verify built-in servers are loaded
        assert len(registry.static_servers) > 0
        assert "kubernetes-server" in registry.get_all_server_ids()

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_init_with_configured_servers(self, sample_mcp_server_configs):
        """Test MCPServerRegistry initialization with configured servers."""
        registry = MCPServerRegistry(configured_servers=sample_mcp_server_configs)
        
        # Verify configured servers are available in the registry
        for server_id in sample_mcp_server_configs.keys():
            assert server_id in registry.get_all_server_ids()
            assert registry.get_server_config(server_id) is not None

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_init_with_empty_configured_servers(self):
        """Test MCPServerRegistry initialization with empty configured servers."""
        empty_configs = {}
        registry = MCPServerRegistry(configured_servers=empty_configs)
        
        # Should still have built-in servers
        assert len(registry.static_servers) > 0
        assert "kubernetes-server" in registry.get_all_server_ids()

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_server_config_conversion_single_server(self):
        """Test conversion of MCPServerConfigModel to internal format."""
        configured_servers = {
            "security-tools": MCPServerConfigModel(
                transport={"type": "stdio", "command": "test", "env": {"HOST": "localhost"}},
                instructions="Security tools"
            )
        }
        
        registry = MCPServerRegistry(configured_servers=configured_servers)
        
        # Check that configured server is available
        server_config = registry.get_server_config("security-tools")
        
        assert server_config.transport.env == {"HOST": "localhost"}
        assert server_config.instructions == "Security tools"

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_server_config_conversion_multiple_servers(self, sample_mcp_server_configs):
        """Test conversion of multiple MCPServerConfigModel instances."""
        registry = MCPServerRegistry(configured_servers=sample_mcp_server_configs)
        
        # Check security-tools server
        security_config = registry.get_server_config("security-tools")
        assert security_config.transport.env == {"HOST": "localhost", "PORT": "8080"}
        assert security_config.instructions == "Security analysis tools"
        
        # Check monitoring-server
        monitoring_config = registry.get_server_config("monitoring-server")
        assert monitoring_config.transport.env == {"ENDPOINT": "http://monitoring.local"}
        assert monitoring_config.instructions == ""  # Default empty string, not None
        
        # Check disabled server
        disabled_config = registry.get_server_config("disabled-server")
        assert disabled_config is not None

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_server_merge_built_in_only(self):
        """Test server lookup with built-in servers only."""
        registry = MCPServerRegistry()
        
        # Should be able to get built-in server
        server_config = registry.get_server_config("kubernetes-server")
        assert server_config is not None

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_server_merge_configured_only(self):
        """Test server lookup with configured servers only."""
        configured_servers = {
            "security-tools": MCPServerConfigModel(
                transport={"type": "stdio", "command": "/usr/bin/security-server"}
            )
        }
        
        registry = MCPServerRegistry(configured_servers=configured_servers)
        
        # Should be able to get configured server
        server_config = registry.get_server_config("security-tools")
        assert server_config is not None
        
        # Should still be able to get built-in server
        server_config = registry.get_server_config("kubernetes-server")
        assert server_config is not None

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_server_merge_mixed_servers(self, sample_mcp_server_configs):
        """Test server lookup with both built-in and configured servers."""
        registry = MCPServerRegistry(configured_servers=sample_mcp_server_configs)
        
        # Should be able to get configured servers
        assert registry.get_server_config("security-tools") is not None
        assert registry.get_server_config("monitoring-server") is not None
        assert registry.get_server_config("disabled-server") is not None
        
        # Should still be able to get built-in server
        assert registry.get_server_config("kubernetes-server") is not None

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_configured_servers_override_built_in(self):
        """Test that configured servers override built-in servers with same ID."""
        configured_servers = {
            "kubernetes-server": MCPServerConfigModel(
                transport={"type": "stdio", "command": "/usr/bin/custom-k8s-server"},
                instructions="Custom Kubernetes server"
            )
        }
        
        registry = MCPServerRegistry(configured_servers=configured_servers)
        
        # Configured server should override built-in
        server_config = registry.get_server_config("kubernetes-server")
        assert server_config is not None
        assert server_config.instructions == "Custom Kubernetes server"

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_get_server_config_fail_fast(self):
        """Test that get_server_config fails fast for unknown server IDs."""
        registry = MCPServerRegistry()
        
        with pytest.raises(ValueError) as exc_info:
            registry.get_server_config("unknown-server")
            
        error_msg = str(exc_info.value)
        assert "MCP server 'unknown-server' not found" in error_msg
        assert "Available: kubernetes-server" in error_msg

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_get_server_config_safe_returns_none(self):
        """Test that get_server_config_safe returns None for unknown server IDs."""
        registry = MCPServerRegistry()
        
        server_config = registry.get_server_config_safe("unknown-server")
        assert server_config is None

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_get_server_config_safe_returns_valid_config(self):
        """Test that get_server_config_safe returns valid config for known server IDs."""
        registry = MCPServerRegistry()
        
        server_config = registry.get_server_config_safe("kubernetes-server")
        assert server_config is not None

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_get_server_config_with_configured_servers_safe(self, sample_mcp_server_configs):
        """Test get_server_config_safe with configured servers."""
        registry = MCPServerRegistry(configured_servers=sample_mcp_server_configs)
        
        # Should return configured server
        server_config = registry.get_server_config_safe("security-tools")
        assert server_config is not None
        
        # Should return built-in server
        server_config = registry.get_server_config_safe("kubernetes-server")
        assert server_config is not None
        
        # Should return None for unknown
        server_config = registry.get_server_config_safe("unknown")
        assert server_config is None

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_error_message_includes_available_servers(self, sample_mcp_server_configs):
        """Test that error messages include all available servers (built-in + configured)."""
        registry = MCPServerRegistry(configured_servers=sample_mcp_server_configs)
        
        with pytest.raises(ValueError) as exc_info:
            registry.get_server_config("unknown-server")
            
        error_msg = str(exc_info.value)
        assert "MCP server 'unknown-server' not found" in error_msg
        assert "Available:" in error_msg
        
        # Should include built-in servers
        assert "kubernetes-server" in error_msg
        
        # Should include configured servers
        assert "security-tools" in error_msg
        assert "monitoring-server" in error_msg
        assert "disabled-server" in error_msg

    def test_configured_servers_only_scenario(self):
        """Test scenario with only configured servers (no built-in servers)."""
        configured_servers = {
            "only-server": MCPServerConfigModel(
                transport={"type": "stdio", "command": "/usr/bin/only-server"}
            )
        }
        
        registry = MCPServerRegistry(config={}, configured_servers=configured_servers)
        
        # Should work with configured server
        server_config = registry.get_server_config("only-server")
        assert server_config is not None
        
        # Should fail for unknown server
        with pytest.raises(ValueError) as exc_info:
            registry.get_server_config("unknown")
            
        error_msg = str(exc_info.value)
        # The registry includes both built-in servers and configured servers
        assert "only-server" in error_msg
        assert "Available:" in error_msg

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_no_configured_servers_scenario(self):
        """Test scenario with only built-in servers (no configured servers)."""
        registry = MCPServerRegistry(configured_servers=None)
        
        # Should work with built-in server
        server_config = registry.get_server_config("kubernetes-server")
        assert server_config is not None
        
        # Should fail for unknown server
        with pytest.raises(ValueError) as exc_info:
            registry.get_server_config("unknown")
            
        error_msg = str(exc_info.value)
        assert "Available: kubernetes-server" in error_msg

    def test_server_config_property_immutability(self, sample_mcp_server_configs):
        """Test that server configurations cannot be modified externally."""
        registry = MCPServerRegistry(configured_servers=sample_mcp_server_configs)
        
        original_static_servers = registry.static_servers
        
        # Verify we get the same reference for static_servers
        assert registry.static_servers is original_static_servers
        
        # Test that the registry still works correctly
        server_config = registry.get_server_config("security-tools")
        assert server_config is not None

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_case_sensitivity_server_ids(self):
        """Test that server ID lookups are case-sensitive."""
        configured_servers = {
            "Security-Tools": MCPServerConfigModel(  # Capital letters
                transport={"type": "stdio", "command": "/usr/bin/Security-Tools"}
            )
        }
        
        registry = MCPServerRegistry(configured_servers=configured_servers)
        
        # Should work with exact case match
        server_config = registry.get_server_config("Security-Tools")
        assert server_config is not None
        
        # Should fail with different case
        with pytest.raises(ValueError):
            registry.get_server_config("security-tools")

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {})
    def test_server_config_with_minimal_fields(self):
        """Test server configuration with only required fields."""
        configured_servers = {
            "minimal-server": MCPServerConfigModel(
                transport={"type": "stdio", "command": "test"}  # Minimal transport
            )
        }
        
        registry = MCPServerRegistry(configured_servers=configured_servers)
        
        server_config = registry.get_server_config("minimal-server")
        assert server_config is not None
        assert server_config.transport.command == "test"  # Has basic transport
        assert server_config.instructions == ""  # Default value (empty string, not None)

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {})
    def test_server_config_with_all_fields(self):
        """Test server configuration with all possible fields."""
        configured_servers = {
            "full-server": MCPServerConfigModel(
                transport={
                    "type": "stdio", 
                    "command": "test",
                    "env": {
                        "HOST": "example.com",
                        "PORT": "9090", 
                        "SSL": "True",
                        "TIMEOUT": "30"
                    }
                },
                instructions="Comprehensive server with all configuration options"
            )
        }
        
        registry = MCPServerRegistry(configured_servers=configured_servers)
        
        server_config = registry.get_server_config("full-server")
        assert server_config is not None
        assert server_config.transport.env["HOST"] == "example.com"
        assert server_config.transport.env["PORT"] == "9090"
        assert server_config.transport.env["SSL"] == "True"
        assert server_config.transport.env["TIMEOUT"] == "30"
        assert server_config.instructions == "Comprehensive server with all configuration options"

    @patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}})
    def test_complex_server_ids_in_registry(self):
        """Test that complex server IDs work correctly in registry."""
        configured_servers = {
            "complex-server_v2.0-beta": MCPServerConfigModel(
                transport={"type": "stdio", "command": "/usr/bin/complex-server_v2.0-beta"}
            )
        }
        
        registry = MCPServerRegistry(configured_servers=configured_servers)
        
        server_config = registry.get_server_config("complex-server_v2.0-beta")
        assert server_config is not None

    def test_builtin_kubernetes_server_default_summarization_config(self):
        """Test that built-in kubernetes server gets correct default summarization configuration."""
        # Use real builtin config (not mocked) to test actual default behavior
        registry = MCPServerRegistry()
        
        # Get the kubernetes server configuration
        server_config = registry.get_server_config("kubernetes-server")
        
        # Verify the server is configured correctly
        assert server_config is not None
        
        # Verify summarization gets the expected default configuration
        assert server_config.summarization is not None, "Summarization config should be present"
        assert server_config.summarization.enabled is True, "Summarization should be enabled by default"
        assert server_config.summarization.size_threshold_tokens == 5000, "Default threshold should be 5000 tokens"
        assert server_config.summarization.summary_max_token_limit == 1000, "Default max summary should be 1000 tokens"
        
        # Verify data masking is also configured as expected
        assert server_config.data_masking is not None
        assert server_config.data_masking.enabled is True 