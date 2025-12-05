"""
Integration tests for MCP Server Registry with .env file template resolution.

Tests the integration of the new .env file functionality with the MCP server registry,
including the new priority order and real-world scenarios.
"""

import os
import tempfile
from unittest.mock import patch

import pytest

from tarsy.config.settings import Settings
from tarsy.models.agent_config import MCPServerConfigModel
from tarsy.services.mcp_server_registry import MCPServerRegistry


@pytest.mark.unit
class TestMCPServerRegistryEnvFileIntegration:
    """Test MCP server registry integration with .env file template resolution."""
    
    def test_builtin_kubernetes_server_with_env_file_priority(self):
        """Test that .env file takes priority over system environment for built-in servers."""
        env_content = "TEST_KUBECONFIG_PRIORITY=/env/file/kubeconfig\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                # Create a custom builtin server config that uses our test variable
                test_builtin_servers = {
                    "test-kubernetes-server": {
                        "server_id": "test-kubernetes-server",
                        "server_type": "kubernetes",
                        "enabled": True,
                        "transport": {"type": "stdio",
                            "command": "npx",
                            "args": ["-y", "kubernetes-mcp-server@latest", "--kubeconfig", "${TEST_KUBECONFIG_PRIORITY}"]
                        },
                        "instructions": "Test Kubernetes operations"
                    }
                }
                
                # Set system environment variable (should be overridden by .env file)
                with patch.dict(os.environ, {'TEST_KUBECONFIG_PRIORITY': '/system/env/kubeconfig'}):
                    settings = Settings()
                    
                    # Create registry with custom builtin servers and test .env file
                    from tarsy.utils.template_resolver import TemplateResolver
                    template_resolver = TemplateResolver(settings=settings, env_file_path=f.name)
                    
                    with patch("tarsy.services.mcp_server_registry.TemplateResolver") as tr_cls:
                        tr_cls.return_value = template_resolver
                        registry = MCPServerRegistry(config=test_builtin_servers, settings=settings)
                    
                    test_config = registry.get_server_config("test-kubernetes-server")
                    
                    # Should use .env file value, not system environment
                    kubeconfig_arg = test_config.transport.args[-1]
                    assert kubeconfig_arg == "/env/file/kubeconfig"
                    
            finally:
                os.unlink(f.name)
    
    def test_configured_server_with_env_file_variables(self):
        """Test configured MCP servers using .env file template variables."""
        env_content = """
CUSTOM_SERVER_TOKEN=secret123
CUSTOM_SERVER_URL=https://custom.api.com
CUSTOM_SERVER_TIMEOUT=60
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                # Create a configured server that uses template variables
                custom_server_config = MCPServerConfigModel(
                    server_id="custom-server",
                    server_type="custom",
                    enabled=True,
                    transport={"type": "stdio",
                        "command": "custom-mcp-server",
                        "args": [
                            "--token", "${CUSTOM_SERVER_TOKEN}",
                            "--url", "${CUSTOM_SERVER_URL}",
                            "--timeout", "${CUSTOM_SERVER_TIMEOUT}"
                        ]
                    },
                    instructions="Custom server with token ${CUSTOM_SERVER_TOKEN}"
                )
                
                configured_servers = {
                    "custom-server": custom_server_config
                }
                
                settings = Settings()
                
                # Create registry with custom .env file
                from tarsy.utils.template_resolver import TemplateResolver
                template_resolver = TemplateResolver(settings=settings, env_file_path=f.name)
                
                with patch("tarsy.services.mcp_server_registry.TemplateResolver") as tr_cls:
                    tr_cls.return_value = template_resolver
                    registry = MCPServerRegistry(
                        configured_servers=configured_servers, 
                        settings=settings
                    )
                
                # Test resolution
                custom_config = registry.get_server_config("custom-server")
                
                args = custom_config.transport.args
                assert args[1] == "secret123"  # --token value
                assert args[3] == "https://custom.api.com"  # --url value
                assert args[5] == "60"  # --timeout value
                assert "Custom server with token secret123" in custom_config.instructions
                
            finally:
                os.unlink(f.name)
    
    def test_mixed_priority_sources_in_registry(self):
        """Test MCP registry with variables from different priority sources."""
        env_content = "TEST_HIGH_PRIORITY_VAR=env_file_value\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                # Create configured server using variables from all priority levels
                test_server_config = MCPServerConfigModel(
                    server_id="priority-test-server",
                    server_type="test",
                    enabled=True,
                    transport={"type": "stdio",
                        "command": "test-server",
                        "args": [
                            "--high", "${TEST_HIGH_PRIORITY_VAR}",      # From .env file
                            "--medium", "${TEST_MEDIUM_PRIORITY_VAR}",  # From system env
                            "--low", "${TEST_LOW_PRIORITY_VAR}"         # From settings default
                        ]
                    }
                )
                
                configured_servers = {
                    "priority-test-server": test_server_config
                }
                
                # Mock settings with default for LOW_PRIORITY_VAR
                from unittest.mock import MagicMock
                mock_settings = MagicMock()
                mock_settings.get_template_default.side_effect = lambda var: {
                    'TEST_LOW_PRIORITY_VAR': 'settings_default'
                }.get(var)
                
                # Set system environment for MEDIUM_PRIORITY_VAR
                with patch.dict(os.environ, {
                    'TEST_HIGH_PRIORITY_VAR': 'system_env_value',  # Should be overridden by .env
                    'TEST_MEDIUM_PRIORITY_VAR': 'system_env_value'  # Should be used
                                }):
                    # Create registry with custom template resolver
                    from tarsy.utils.template_resolver import TemplateResolver
                    template_resolver = TemplateResolver(settings=mock_settings, env_file_path=f.name)
                    
                    with patch("tarsy.services.mcp_server_registry.TemplateResolver") as tr_cls:
                        tr_cls.return_value = template_resolver
                        registry = MCPServerRegistry(
                            configured_servers=configured_servers,
                            settings=mock_settings
                        )
                    
                    test_config = registry.get_server_config("priority-test-server")
                    
                    args = test_config.transport.args
                    assert args[1] == "env_file_value"      # .env file wins
                    assert args[3] == "system_env_value"    # system env used
                    assert args[5] == "settings_default"    # settings default used
                    
            finally:
                os.unlink(f.name)
    
    def test_registry_handles_missing_env_file_gracefully(self):
        """Test that registry works when .env file is missing."""
        # Test with non-existent .env file
        settings = Settings()
        
        # Create template resolver with non-existent .env file
        from tarsy.utils.template_resolver import TemplateResolver
        template_resolver = TemplateResolver(
            settings=settings, 
            env_file_path="/nonexistent/.env"
        )
        
        # Should still work with system environment and defaults
        with patch.dict(os.environ, {'KUBECONFIG': '/system/kubeconfig'}):
            with patch("tarsy.services.mcp_server_registry.TemplateResolver") as tr_cls:
                tr_cls.return_value = template_resolver
                registry = MCPServerRegistry(settings=settings)
            
            k8s_config = registry.get_server_config("kubernetes-server")
            
            # Should use system environment value
            kubeconfig_arg = None
            args = k8s_config.transport.args
            for i, arg in enumerate(args):
                if arg == "--kubeconfig" and i + 1 < len(args):
                    kubeconfig_arg = args[i + 1]
                    break
            
            assert kubeconfig_arg == "/system/kubeconfig"


@pytest.mark.unit
class TestMCPServerRegistryErrorHandling:
    """Test MCP server registry error handling with .env file functionality."""
    
    def test_malformed_env_file_does_not_break_registry(self):
        """Test that malformed .env file doesn't prevent registry initialization."""
        env_content = """
VALID_VAR=valid_value
INVALID_LINE_NO_EQUALS
123STARTS_WITH_DIGIT=invalid
VALID_VAR2=another_valid
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                settings = Settings()
                
                # Create template resolver with malformed .env file
                from tarsy.utils.template_resolver import TemplateResolver
                template_resolver = TemplateResolver(settings=settings, env_file_path=f.name)
                
                # Should not raise error despite malformed lines
                with patch("tarsy.services.mcp_server_registry.TemplateResolver") as tr_cls:
                    tr_cls.return_value = template_resolver
                    registry = MCPServerRegistry(settings=settings)
                
                # Valid variables should be available
                assert template_resolver.env_file_vars['VALID_VAR'] == 'valid_value'
                assert template_resolver.env_file_vars['VALID_VAR2'] == 'another_valid'
                
                # Non-standard variable names are now loaded (no validation)
                assert template_resolver.env_file_vars['123STARTS_WITH_DIGIT'] == 'invalid'
                
                # Registry should still function normally
                assert len(registry.get_all_server_ids()) > 0
                
            finally:
                os.unlink(f.name)
    
    def test_template_resolution_error_fallback(self):
        """Test fallback behavior when template resolution fails."""
        # Create server config with missing template variable
        test_server_config = MCPServerConfigModel(
            server_id="error-test-server",
            server_type="test",
            enabled=True,
            transport={"type": "stdio",
                "command": "test-server",
                "args": ["--missing", "${COMPLETELY_MISSING_VAR}"]
            }
        )
        
        configured_servers = {
            "error-test-server": test_server_config
        }
        
        settings = Settings()
        
        # Should handle template resolution error gracefully
        # The registry should use fallback behavior (original config without resolution)
        registry = MCPServerRegistry(
            configured_servers=configured_servers,
            settings=settings
        )
        
        # Server should still be registered (with original config)
        assert "error-test-server" in registry.get_all_server_ids()
        
        # Should be able to get the config (though template not resolved)
        error_config = registry.get_server_config("error-test-server")
        assert error_config.server_id == "error-test-server"
