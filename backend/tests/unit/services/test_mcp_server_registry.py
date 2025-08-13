"""
Unit tests for MCPServerRegistry - Manages MCP server configurations.

Tests server configuration management, registry initialization, lookups,
default configurations, and edge case handling.
"""

from unittest.mock import Mock, patch

import pytest

from tarsy.models.mcp_config import MCPServerConfig
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tests.utils import MCPServerFactory


@pytest.mark.unit
class TestMCPServerRegistryInitialization:
    """Test MCPServerRegistry initialization with different configurations."""
    
    def test_initialization_with_default_configurations(self):
        """Test initialization using default server configurations."""
        registry = MCPServerRegistry()
        
        # Should have default configurations
        assert isinstance(registry.static_servers, dict)
        assert len(registry.static_servers) >= 1
        assert "kubernetes-server" in registry.static_servers
        
        # Check kubernetes-server configuration
        k8s_config = registry.static_servers["kubernetes-server"]
        assert isinstance(k8s_config, MCPServerConfig)
        assert k8s_config.server_id == "kubernetes-server"
        assert k8s_config.server_type == "kubernetes"
        assert k8s_config.enabled is True
    
    def test_initialization_with_custom_config(self):
        """Test initialization with custom server configurations."""
        custom_config = {
            "test-server": MCPServerFactory.create_test_server(),
            "another-server": MCPServerFactory.create_disabled_server(
                server_id="another-server",
                server_type="another"
            )
        }
        
        registry = MCPServerRegistry(config=custom_config)
        
        # Should use custom configuration instead of defaults
        assert len(registry.static_servers) == 2
        assert "test-server" in registry.static_servers
        assert "another-server" in registry.static_servers
        assert "kubernetes-server" not in registry.static_servers
        
        # Verify server configs are properly converted
        test_config = registry.static_servers["test-server"]
        assert isinstance(test_config, MCPServerConfig)
        assert test_config.server_id == "test-server"
        assert test_config.enabled is True
    
    def test_initialization_with_empty_config(self):
        """Test initialization with empty configuration falls back to defaults."""
        registry = MCPServerRegistry(config={})
        
        # Empty dict is falsy, so should fall back to default configurations
        assert len(registry.static_servers) >= 1
        assert "kubernetes-server" in registry.static_servers
    
    def test_initialization_with_none_config(self):
        """Test initialization with None configuration falls back to defaults."""
        registry = MCPServerRegistry(config=None)
        
        # Should use default configurations
        assert "kubernetes-server" in registry.static_servers
        assert registry.static_servers["kubernetes-server"].server_type == "kubernetes"
    
    def test_static_servers_isolation(self):
        """Test that different registry instances have isolated server stores."""
        registry1 = MCPServerRegistry()
        registry2 = MCPServerRegistry()
        
        # Should be separate instances
        assert registry1.static_servers is not registry2.static_servers
        
        # But should have same content
        assert set(registry1.static_servers.keys()) == set(registry2.static_servers.keys())
    
    def test_mcp_server_config_instantiation(self):
        """Test that MCPServerConfig is properly instantiated for each server."""
        with patch('tarsy.services.mcp_server_registry.MCPServerConfig') as mock_mcp_config:
            mock_config_instance = Mock()
            mock_mcp_config.return_value = mock_config_instance
            
            test_server_config = MCPServerFactory.create_test_server()
            custom_config = {"test-server": test_server_config}
            
            registry = MCPServerRegistry(config=custom_config)
            
            # Verify MCPServerConfig was called with correct parameters
            mock_mcp_config.assert_called_once_with(
                server_id="test-server",
                server_type="test", 
                enabled=True,
                connection_params={"command": "test", "args": ["--test"], "env": {}},
                instructions="Test MCP server for testing"
            )
            
            assert registry.static_servers["test-server"] == mock_config_instance


@pytest.mark.unit
class TestServerConfigRetrieval:
    """Test server configuration retrieval methods."""
    
    @pytest.fixture
    def sample_registry(self):
        """Create a registry with known server configurations for testing."""
        return MCPServerRegistry(config={
            "kubernetes-server": MCPServerFactory.create_kubernetes_server(),
            "docker-server": MCPServerFactory.create_docker_server(),
            "disabled-server": MCPServerFactory.create_disabled_server()
        })
    
    def test_get_server_config_existing_server(self, sample_registry):
        """Test getting configuration for existing servers."""
        k8s_config = sample_registry.get_server_config("kubernetes-server")
        assert k8s_config is not None
        assert isinstance(k8s_config, MCPServerConfig)
        assert k8s_config.server_id == "kubernetes-server"
        assert k8s_config.server_type == "kubernetes"
        assert k8s_config.enabled is True
        
        docker_config = sample_registry.get_server_config("docker-server")
        assert docker_config is not None
        assert docker_config.server_id == "docker-server"
        assert docker_config.enabled is True
    
    def test_get_server_config_non_existing_server(self, sample_registry):
        """Test getting configuration for non-existing servers raises ValueError."""
        with pytest.raises(ValueError, match="MCP server 'non-existent-server' not found"):
            sample_registry.get_server_config("non-existent-server")
            
        with pytest.raises(ValueError, match="MCP server 'unknown-server' not found"):
            sample_registry.get_server_config("unknown-server")
            
        with pytest.raises(ValueError, match="MCP server 'missing-server' not found"):
            sample_registry.get_server_config("missing-server")
    
    def test_get_server_config_case_sensitive(self, sample_registry):
        """Test that server config lookup is case sensitive."""
        # Exact case should work
        assert sample_registry.get_server_config("kubernetes-server") is not None
        
        # Different case should raise ValueError
        with pytest.raises(ValueError, match="MCP server 'Kubernetes-Server' not found"):
            sample_registry.get_server_config("Kubernetes-Server")
            
        with pytest.raises(ValueError, match="MCP server 'KUBERNETES-SERVER' not found"):
            sample_registry.get_server_config("KUBERNETES-SERVER")
            
        with pytest.raises(ValueError, match="MCP server 'kubernetes_server' not found"):
            sample_registry.get_server_config("kubernetes_server")
    
    def test_get_server_config_with_special_characters(self, sample_registry):
        """Test server config lookup with special characters."""
        # Exact match should work
        assert sample_registry.get_server_config("kubernetes-server") is not None
        
        # Different special characters should raise ValueError
        with pytest.raises(ValueError, match="MCP server 'kubernetes_server' not found"):
            sample_registry.get_server_config("kubernetes_server")
            
        with pytest.raises(ValueError, match="MCP server 'kubernetes.server' not found"):
            sample_registry.get_server_config("kubernetes.server")
            
        with pytest.raises(ValueError, match="MCP server 'kubernetes server' not found"):
            sample_registry.get_server_config("kubernetes server")
    
    def test_get_server_configs_multiple_existing_servers(self, sample_registry):
        """Test getting configurations for multiple existing servers."""
        server_ids = ["kubernetes-server", "docker-server"]
        configs = sample_registry.get_server_configs(server_ids)
        
        assert len(configs) == 2
        assert all(isinstance(config, MCPServerConfig) for config in configs)
        
        # Check order is preserved
        assert configs[0].server_id == "kubernetes-server"
        assert configs[1].server_id == "docker-server"
    
    def test_get_server_configs_mixed_existing_non_existing(self, sample_registry):
        """Test getting configurations with mix of existing and non-existing servers."""
        server_ids = ["kubernetes-server", "non-existent", "docker-server", "also-missing"]
        configs = sample_registry.get_server_configs(server_ids)
        
        # Should only return existing servers
        assert len(configs) == 2
        assert configs[0].server_id == "kubernetes-server"
        assert configs[1].server_id == "docker-server"
    
    def test_get_server_configs_all_non_existing(self, sample_registry):
        """Test getting configurations for all non-existing servers."""
        server_ids = ["non-existent-1", "non-existent-2", "missing"]
        configs = sample_registry.get_server_configs(server_ids)
        
        assert configs == []
        assert len(configs) == 0
    
    def test_get_server_configs_empty_list(self, sample_registry):
        """Test getting configurations with empty server ID list."""
        configs = sample_registry.get_server_configs([])
        
        assert configs == []
        assert len(configs) == 0
    
    def test_get_server_configs_duplicate_server_ids(self, sample_registry):
        """Test getting configurations with duplicate server IDs."""
        server_ids = ["kubernetes-server", "docker-server", "kubernetes-server"]
        configs = sample_registry.get_server_configs(server_ids)
        
        # Should include duplicates
        assert len(configs) == 3
        assert configs[0].server_id == "kubernetes-server"
        assert configs[1].server_id == "docker-server"
        assert configs[2].server_id == "kubernetes-server"
        
        # Should be same instance
        assert configs[0] is configs[2]
    
    def test_get_all_server_ids(self, sample_registry):
        """Test getting all configured server IDs."""
        server_ids = sample_registry.get_all_server_ids()
        
        expected_ids = ["kubernetes-server", "docker-server", "disabled-server"]
        assert set(server_ids) == set(expected_ids)
        assert len(server_ids) == 3
        assert isinstance(server_ids, list)
    
    def test_get_all_server_ids_returns_list(self, sample_registry):
        """Test that get_all_server_ids returns a list."""
        server_ids = sample_registry.get_all_server_ids()
        assert isinstance(server_ids, list)
    
    def test_get_all_server_ids_empty_registry(self):
        """Test get_all_server_ids with empty registry."""
        # Create registry with truly empty config
        registry = MCPServerRegistry()
        registry.static_servers.clear()  # Make it truly empty
        
        server_ids = registry.get_all_server_ids()
        assert isinstance(server_ids, list)
        assert len(server_ids) == 0
        assert server_ids == []


@pytest.mark.unit
class TestDefaultConfigurations:
    """Test default server configuration handling."""
    
    def test_default_configurations_contain_kubernetes_server(self):
        """Test that default configurations include kubernetes-server."""
        registry = MCPServerRegistry()
        
        # Should have kubernetes-server in defaults
        assert "kubernetes-server" in registry.static_servers
        k8s_config = registry.static_servers["kubernetes-server"]
        assert k8s_config.server_type == "kubernetes"
        assert k8s_config.enabled is True
    
    def test_default_configurations_structure(self):
        """Test the structure of default server configurations."""
        registry = MCPServerRegistry()
        
        # All keys should be strings (server IDs)
        for server_id in registry.static_servers.keys():
            assert isinstance(server_id, str)
            assert len(server_id) > 0
        
        # All values should be MCPServerConfig instances
        for config in registry.static_servers.values():
            assert isinstance(config, MCPServerConfig)
            assert hasattr(config, 'server_id')
            assert hasattr(config, 'server_type')
            assert hasattr(config, 'enabled')
    
    def test_default_configurations_not_empty(self):
        """Test that default configurations are not empty."""
        registry = MCPServerRegistry()
        
        assert len(registry.static_servers) > 0
        assert registry.static_servers  # Truthy check
    
    def test_access_to_default_servers_class_constant(self):
        """Test that _DEFAULT_SERVERS class constant exists and is accessible."""
        # Should be able to access the class constant
        assert hasattr(MCPServerRegistry, '_DEFAULT_SERVERS')
        assert isinstance(MCPServerRegistry._DEFAULT_SERVERS, dict)
        assert "kubernetes-server" in MCPServerRegistry._DEFAULT_SERVERS
    
    def test_default_kubernetes_server_configuration(self):
        """Test specific default kubernetes-server configuration."""
        registry = MCPServerRegistry()
        k8s_config = registry.static_servers["kubernetes-server"]
        
        assert k8s_config.server_id == "kubernetes-server"
        assert k8s_config.server_type == "kubernetes"
        assert k8s_config.enabled is True
        assert k8s_config.connection_params is not None
        assert "command" in k8s_config.connection_params
        assert "args" in k8s_config.connection_params
        assert k8s_config.instructions is not None
        assert len(k8s_config.instructions) > 0


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error scenarios."""
    
    def test_registry_with_special_character_server_ids(self):
        """Test registry with special characters in server IDs."""
        special_config = {
            "server-with-dashes": MCPServerFactory.create_test_server(server_id="server-with-dashes"),
            "server_with_underscores": MCPServerFactory.create_test_server(server_id="server_with_underscores"),
            "server.with.dots": MCPServerFactory.create_test_server(server_id="server.with.dots"),
            "server/with/slashes": MCPServerFactory.create_test_server(server_id="server/with/slashes")
        }
        
        registry = MCPServerRegistry(config=special_config)
        
        # All should be accessible
        assert registry.get_server_config("server-with-dashes") is not None
        assert registry.get_server_config("server_with_underscores") is not None
        assert registry.get_server_config("server.with.dots") is not None
        assert registry.get_server_config("server/with/slashes") is not None
    
    def test_registry_with_numeric_server_ids(self):
        """Test registry with numeric or mixed server IDs."""
        numeric_config = {
            "server123": MCPServerFactory.create_test_server(server_id="server123"),
            "123server": MCPServerFactory.create_test_server(server_id="123server"),
            "server-2024": MCPServerFactory.create_test_server(server_id="server-2024")
        }
        
        registry = MCPServerRegistry(config=numeric_config)
        
        assert registry.get_server_config("server123") is not None
        assert registry.get_server_config("123server") is not None
        assert registry.get_server_config("server-2024") is not None
    
    def test_registry_with_unicode_server_ids(self):
        """Test registry with unicode characters in server IDs."""
        unicode_config = {
            "serverWithÜnicode": MCPServerFactory.create_test_server(server_id="serverWithÜnicode"),
            "server🚀space": MCPServerFactory.create_test_server(server_id="server🚀space")
        }
        
        registry = MCPServerRegistry(config=unicode_config)
        
        assert registry.get_server_config("serverWithÜnicode") is not None
        assert registry.get_server_config("server🚀space") is not None
    
    def test_registry_with_very_long_server_ids(self):
        """Test registry with very long server IDs and configurations."""
        long_server_id = "very-long-server-id-" * 10  # 200+ characters
        long_config = {
            long_server_id: {
                "server_id": long_server_id,
                "server_type": "test",
                "enabled": True,
                "connection_params": {"command": "test", "args": []},
                "instructions": "Very long instructions " * 100  # Very long instructions
            }
        }
        
        registry = MCPServerRegistry(config=long_config)
        assert registry.get_server_config(long_server_id) is not None
    
    def test_registry_with_empty_string_server_id(self):
        """Test registry behavior with empty string server ID."""
        empty_config = {
            "": {
                "server_id": "",
                "server_type": "empty",
                "enabled": True,
                 "connection_params": {"command": "test", "args": []}
            }
        }
        
        registry = MCPServerRegistry(config=empty_config)
        
        # Should handle empty string server ID
        assert registry.get_server_config("") is not None
        assert "" in registry.get_all_server_ids()
    
    def test_get_server_config_with_non_string_input(self):
        """Test get_server_config with non-string inputs."""
        registry = MCPServerRegistry()
        
        # Should handle non-string inputs by raising ValueError
        with pytest.raises(ValueError, match="MCP server '123' not found"):
            registry.get_server_config(123)
            
        with pytest.raises(ValueError, match="MCP server 'None' not found"):
            registry.get_server_config(None)
            
        with pytest.raises(ValueError, match="MCP server 'True' not found"):
            registry.get_server_config(True)
        with pytest.raises(ValueError, match="MCP server 'False' not found"):
            registry.get_server_config(False)
    
    def test_get_server_configs_with_non_string_input(self):
        """Test get_server_configs with non-string inputs in list."""
        registry = MCPServerRegistry()
        
        # Should handle non-string inputs gracefully (dict.get behavior)
        server_ids = ["kubernetes-server", 123, None, "non-existent"]
        configs = registry.get_server_configs(server_ids)
        
        # Should only return the valid string server that exists
        assert len(configs) == 1
        assert configs[0].server_id == "kubernetes-server"


@pytest.mark.unit
class TestRegistryLogging:
    """Test logging functionality in MCPServerRegistry."""
    
    def test_initialization_logging(self, caplog):
        """Test that initialization logs correct information."""
        with caplog.at_level("INFO"):
            registry = MCPServerRegistry()
        
        # Should log number of servers
        log_messages = [record.message for record in caplog.records]
        registry_logs = [msg for msg in log_messages if "Initialized MCP Server Registry with" in msg]
        assert len(registry_logs) > 0
        
        # Should mention the number of servers
        registry_log = registry_logs[0]
        assert "servers" in registry_log
        assert str(len(registry.static_servers)) in registry_log
    
    def test_initialization_logging_with_custom_config(self, caplog):
        """Test logging with custom server configuration."""
        custom_config = {
            "server1": {"server_id": "server1", "server_type": "test", "enabled": True, "connection_params": {"command": "test", "args": []}},
            "server2": {"server_id": "server2", "server_type": "test", "enabled": True, "connection_params": {"command": "test", "args": []}}
        }
        
        with caplog.at_level("INFO"):
            registry = MCPServerRegistry(config=custom_config)
        
        # Should log correct count
        log_messages = [record.message for record in caplog.records]
        registry_logs = [msg for msg in log_messages if "Initialized MCP Server Registry with" in msg]
        assert len(registry_logs) > 0
        
        registry_log = registry_logs[0]
        assert "2 total servers" in registry_log
    
    def test_initialization_logging_with_empty_config(self, caplog):
        """Test logging with empty configuration (falls back to defaults)."""
        with caplog.at_level("INFO"):
            registry = MCPServerRegistry(config={})
        
        # Should log default servers count (since empty dict falls back to defaults)
        log_messages = [record.message for record in caplog.records]
        registry_logs = [msg for msg in log_messages if "Initialized MCP Server Registry with" in msg]
        assert len(registry_logs) > 0
        
        registry_log = registry_logs[0]
        assert str(len(registry.static_servers)) + " total servers" in registry_log


@pytest.mark.unit
class TestServerConfigObjectIntegration:
    """Test integration with MCPServerConfig objects."""
    
    def test_server_config_objects_have_correct_attributes(self):
        """Test that created MCPServerConfig objects have expected attributes."""
        registry = MCPServerRegistry()
        
        for server_id, config in registry.static_servers.items():
            assert isinstance(config, MCPServerConfig)
            assert hasattr(config, 'server_id')
            assert hasattr(config, 'server_type') 
            assert hasattr(config, 'enabled')
            assert config.server_id == server_id
    
    def test_server_config_objects_maintain_data_integrity(self):
        """Test that MCPServerConfig objects maintain data integrity."""
        custom_config = {
            "test-server": {
                "server_id": "test-server",
                "server_type": "integration",
                "enabled": False,
                "connection_params": {"host": "localhost", "port": 8080},
                "instructions": "Test server instructions"
            }
        }
        
        registry = MCPServerRegistry(config=custom_config)
        config = registry.get_server_config("test-server")
        
        assert config.server_id == "test-server"
        assert config.server_type == "integration"
        assert config.enabled is False
        assert config.connection_params == {"host": "localhost", "port": 8080}
        assert config.instructions == "Test server instructions"
    
    def test_server_config_immutability_after_creation(self):
        """Test that server config objects are isolated after creation."""
        registry1 = MCPServerRegistry()
        registry2 = MCPServerRegistry()
        
        config1 = registry1.get_server_config("kubernetes-server")
        config2 = registry2.get_server_config("kubernetes-server")
        
        # Should be different instances with same data
        assert config1 is not config2
        assert config1.server_id == config2.server_id
        assert config1.server_type == config2.server_type 