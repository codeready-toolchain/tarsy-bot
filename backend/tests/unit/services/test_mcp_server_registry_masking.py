"""
Unit tests for MCPServerRegistry masking configuration support.

Tests focus on practical masking integration scenarios:
- Server config retrieval with masking configurations
- Built-in vs configured server masking support
- Safe config lookup for masking service integration
"""

import pytest

from tarsy.models.agent_config import MCPServerConfigModel
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tests.utils import MCPServerMaskingFactory


@pytest.mark.unit
class TestMCPServerRegistryMaskingIntegration:
    """Test registry integration with masking configurations."""
    
    def test_builtin_server_config_with_masking(self):
        """Test built-in server config retrieval with masking configured."""
        # Use default registry - built-in kubernetes server has masking configured
        registry = MCPServerRegistry()
        
        # Get kubernetes server config
        config = registry.get_server_config_safe("kubernetes-server")
        
        assert config is not None
        assert isinstance(config, MCPServerConfigModel)
        # Built-in kubernetes server has masking configuration
        assert config.data_masking is not None
        assert config.data_masking.enabled is True
        assert "kubernetes" in config.data_masking.pattern_groups
        assert "certificate" in config.data_masking.patterns
        assert "token" in config.data_masking.patterns
    
    def test_server_config_with_basic_masking(self):
        """Test server config with basic masking configuration."""
        # Create server with masking config
        server_config_data = {
            "test-server": MCPServerMaskingFactory.create_test_server_config()
        }
        
        registry = MCPServerRegistry(config=server_config_data)
        config = registry.get_server_config_safe("test-server")
        
        assert config is not None
        assert config.data_masking is not None
        assert config.data_masking.enabled is True
        assert "basic" in config.data_masking.pattern_groups
    
    def test_server_config_with_comprehensive_masking(self):
        """Test server config with comprehensive masking configuration."""
        server_config_data = {
            "secure-server": MCPServerMaskingFactory.create_secure_server_config()
        }
        
        registry = MCPServerRegistry(config=server_config_data)
        config = registry.get_server_config_safe("secure-server")
        
        assert config is not None
        assert config.data_masking is not None
        assert config.data_masking.enabled is True
        assert "security" in config.data_masking.pattern_groups
        assert "token" in config.data_masking.patterns
        assert len(config.data_masking.custom_patterns) == 1
        assert config.data_masking.custom_patterns[0].name == "server_id"
    
    def test_server_config_with_disabled_masking(self):
        """Test server config with explicitly disabled masking."""
        server_config_data = {
            "dev-server": {
                "server_id": "dev-server",
                "server_type": "development",
                "enabled": True,
                "transport": {"type": "stdio", "command": "dev", "args": []},
                "instructions": "Development server with disabled masking",
                "data_masking": {
                    "enabled": False,
                    "pattern_groups": ["basic"]  # Should be ignored when disabled
                }
            }
        }
        
        registry = MCPServerRegistry(config=server_config_data)
        config = registry.get_server_config_safe("dev-server")
        
        assert config is not None
        assert config.data_masking is not None
        assert config.data_masking.enabled is False
        # Pattern groups should still be preserved even when disabled
        assert "basic" in config.data_masking.pattern_groups
    
    def test_multiple_servers_with_different_masking_configs(self):
        """Test registry with multiple servers having different masking setups."""
        server_configs = {
            "no-masking-server": {
                "server_id": "no-masking-server",
                "server_type": "basic",
                "enabled": True,
                "transport": {"type": "stdio", "command": "basic", "args": []},
                "instructions": "Basic server without masking"
                # No data_masking field - should default to None
            },
            "basic-masking-server": {
                "server_id": "basic-masking-server",
                "server_type": "secured",
                "enabled": True,
                "transport": {"type": "stdio", "command": "secured", "args": []},
                "instructions": "Server with basic masking",
                "data_masking": {
                    "enabled": True,
                    "pattern_groups": ["basic"]
                }
            },
            "disabled-masking-server": {
                "server_id": "disabled-masking-server",
                "server_type": "test",
                "enabled": True,
                "transport": {"type": "stdio", "command": "test", "args": []},
                "instructions": "Test server with disabled masking",
                "data_masking": {
                    "enabled": False
                }
            }
        }
        
        registry = MCPServerRegistry(config=server_configs)
        
        # Test no masking server
        no_masking = registry.get_server_config_safe("no-masking-server")
        assert no_masking is not None
        assert no_masking.data_masking is None
        
        # Test basic masking server
        basic_masking = registry.get_server_config_safe("basic-masking-server")
        assert basic_masking is not None
        assert basic_masking.data_masking is not None
        assert basic_masking.data_masking.enabled is True
        
        # Test disabled masking server
        disabled_masking = registry.get_server_config_safe("disabled-masking-server")
        assert disabled_masking is not None
        assert disabled_masking.data_masking is not None
        assert disabled_masking.data_masking.enabled is False


@pytest.mark.unit
class TestMCPServerRegistryMaskingServiceIntegration:
    """Test registry methods used by DataMaskingService."""
    
    def test_get_server_config_safe_for_masking_service(self):
        """Test the safe config retrieval method used by DataMaskingService."""
        server_configs = {
            "masked-server": {
                "server_id": "masked-server",
                "server_type": "production",
                "enabled": True,
                "transport": {"type": "stdio", "command": "prod", "args": []},
                "instructions": "Production server with masking",
                "data_masking": {
                    "enabled": True,
                    "pattern_groups": ["security"],
                    "patterns": ["api_key", "password"]
                }
            }
        }
        
        registry = MCPServerRegistry(config=server_configs)
        
        # Test successful retrieval
        config = registry.get_server_config_safe("masked-server")
        assert config is not None
        assert hasattr(config, 'data_masking')
        assert config.data_masking is not None
        assert config.data_masking.enabled is True
        
        # Test non-existent server (should return None, not raise exception)
        config = registry.get_server_config_safe("non-existent-server")
        assert config is None
    
    def test_masking_config_validation_during_registry_initialization(self):
        """Test that invalid masking configs fail during registry initialization."""
        # Invalid masking config should fail during MCPServerConfigModel creation
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            server_configs = {
                "invalid-server": {
                    "server_id": "invalid-server",
                    "server_type": "test",
                    "enabled": True,
                    "transport": {"type": "stdio", "command": "test", "args": []},
                    "instructions": "Server with invalid masking config",
                    "data_masking": {
                        "enabled": True,
                        "custom_patterns": [
                            {
                                "name": "invalid_pattern",
                                "pattern": "[invalid regex(",  # Invalid regex
                                "replacement": "__MASKED__",
                                "description": "Invalid pattern"
                            }
                        ]
                    }
                }
            }
            MCPServerRegistry(config=server_configs)
    
    def test_realistic_production_masking_scenarios(self):
        """Test realistic production scenarios with masking configurations."""
        production_configs = {
            # Kubernetes server with comprehensive masking
            "kubernetes-prod": {
                "server_id": "kubernetes-prod",
                "server_type": "kubernetes",
                "enabled": True,
                "transport": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y", "kubernetes-mcp-server@latest"]
                },
                "instructions": "Production Kubernetes server with security masking",
                "data_masking": {
                    "enabled": True,
                    "pattern_groups": ["kubernetes", "security"],
                    "custom_patterns": [
                        {
                            "name": "k8s_token",
                            "pattern": r"token:\s*[A-Za-z0-9\-_]{40,}",
                            "replacement": "token: __MASKED_K8S_TOKEN__",
                            "description": "Kubernetes service account tokens"
                        }
                    ]
                }
            },
            # Development server with disabled masking
            "kubernetes-dev": {
                "server_id": "kubernetes-dev",
                "server_type": "kubernetes",
                "enabled": True,
                "transport": {
                    "type": "stdio",
                    "command": "npx",
                    "args": ["-y", "kubernetes-mcp-server@latest", "--dev"]
                },
                "instructions": "Development Kubernetes server - masking disabled for debugging",
                "data_masking": {
                    "enabled": False,
                    "pattern_groups": ["kubernetes"]  # Defined but disabled
                }
            },
            # Simple server without masking
            "simple-server": {
                "server_id": "simple-server",
                "server_type": "simple",
                "enabled": True,
                "transport": {"type": "stdio", "command": "simple", "args": []},
                "instructions": "Simple server with no sensitive data"
                # No masking configuration
            }
        }
        
        registry = MCPServerRegistry(config=production_configs)
        
        # Test production server with masking
        prod_config = registry.get_server_config_safe("kubernetes-prod")
        assert prod_config is not None
        assert prod_config.data_masking is not None
        assert prod_config.data_masking.enabled is True
        assert "kubernetes" in prod_config.data_masking.pattern_groups
        assert "security" in prod_config.data_masking.pattern_groups
        assert len(prod_config.data_masking.custom_patterns) == 1
        
        # Test development server with disabled masking
        dev_config = registry.get_server_config_safe("kubernetes-dev")
        assert dev_config is not None
        assert dev_config.data_masking is not None
        assert dev_config.data_masking.enabled is False
        
        # Test simple server without masking
        simple_config = registry.get_server_config_safe("simple-server")
        assert simple_config is not None
        assert simple_config.data_masking is None
        
        # Verify all servers are accessible
        all_server_ids = registry.get_all_server_ids()
        assert "kubernetes-prod" in all_server_ids
        assert "kubernetes-dev" in all_server_ids
        assert "simple-server" in all_server_ids
        assert len(all_server_ids) == 3


@pytest.mark.unit
class TestMCPServerRegistryMaskingEdgeCases:
    """Test edge cases and error scenarios for masking configurations."""
    
    def test_empty_masking_config(self):
        """Test server with empty masking configuration."""
        server_configs = {
            "empty-masking-server": {
                "server_id": "empty-masking-server",
                "server_type": "test",
                "enabled": True,
                "transport": {"type": "stdio", "command": "test", "args": []},
                "instructions": "Server with empty masking config",
                "data_masking": {}  # Empty masking config should use defaults
            }
        }
        
        registry = MCPServerRegistry(config=server_configs)
        config = registry.get_server_config_safe("empty-masking-server")
        
        assert config is not None
        assert config.data_masking is not None
        # Should have default values
        assert config.data_masking.enabled is True  # Default value
        assert config.data_masking.pattern_groups == []  # Default empty list
        assert config.data_masking.patterns == []  # Default empty list
        assert config.data_masking.custom_patterns is None  # Default None
    
    def test_server_config_serialization_with_masking(self):
        """Test that server configs with masking can be serialized/deserialized."""
        server_configs = {
            "serializable-server": {
                "server_id": "serializable-server",
                "server_type": "test",
                "enabled": True,
                "transport": {"type": "stdio", "command": "test", "args": []},
                "instructions": "Server for serialization testing",
                "data_masking": {
                    "enabled": True,
                    "pattern_groups": ["basic"],
                    "patterns": ["api_key"],
                    "custom_patterns": [
                        {
                            "name": "test_pattern",
                            "pattern": r"test_\d+",
                            "replacement": "__MASKED_TEST__",
                            "description": "Test pattern for serialization"
                        }
                    ]
                }
            }
        }
        
        registry = MCPServerRegistry(config=server_configs)
        config = registry.get_server_config_safe("serializable-server")
        
        assert config is not None
        
        # Test serialization roundtrip
        config_dict = config.model_dump()
        restored_config = MCPServerConfigModel(**config_dict)
        
        assert restored_config.server_id == config.server_id
        assert restored_config.data_masking is not None
        assert restored_config.data_masking.enabled == config.data_masking.enabled
        assert restored_config.data_masking.pattern_groups == config.data_masking.pattern_groups
        assert len(restored_config.data_masking.custom_patterns) == 1