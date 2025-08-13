"""
Unit tests for MCPServerRegistry template resolution functionality.

Tests template variable expansion in MCP server configurations,
including settings defaults, environment variable precedence,
and error handling scenarios.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from tarsy.config.settings import Settings
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.models.agent_config import MCPServerConfigModel
from tests.utils import MCPServerMaskingFactory


@pytest.mark.unit
class TestMCPServerRegistryTemplateResolution:
    """Test template resolution in MCPServerRegistry."""
    
    def test_builtin_kubernetes_server_template_resolution_with_env(self):
        """Test built-in kubernetes-server template resolution with environment variable."""
        with patch.dict(os.environ, {'KUBECONFIG': '/custom/kube/config'}):
            settings = Settings()
            registry = MCPServerRegistry(settings=settings)
            
            k8s_config = registry.get_server_config("kubernetes-server")
            
            # Verify template was resolved with environment variable
            assert "/custom/kube/config" in k8s_config.connection_params["args"]
            # Should not use default since env var is set
            assert k8s_config.connection_params["args"][-1] == "/custom/kube/config"
    
    def test_builtin_kubernetes_server_template_resolution_with_default(self):
        """Test built-in kubernetes-server template resolution with settings default."""
        # Ensure KUBECONFIG is not in environment
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            registry = MCPServerRegistry(settings=settings)
            
            k8s_config = registry.get_server_config("kubernetes-server")
            
            # Verify template was resolved with expanded default value (not tilde literal)
            assert ".kube/config" in str(k8s_config.connection_params["args"])
            assert "~" not in str(k8s_config.connection_params["args"])  # Tilde should be expanded
    
    def test_configured_server_template_resolution(self):
        """Test template resolution in configured MCP servers."""
        configured_servers = {
            "template-server": MCPServerConfigModel(**MCPServerMaskingFactory.create_template_server_config())
        }
        
        env_vars = MCPServerMaskingFactory.create_template_environment_vars()
        with patch.dict(os.environ, env_vars):
            settings = Settings()
            registry = MCPServerRegistry(configured_servers=configured_servers, settings=settings)
            
            config = registry.get_server_config("template-server")
            
            # Verify templates were resolved
            assert config.connection_params["args"] == [
                "--token", "secret123", "--url", "http://test.com"
            ]
    
    def test_template_resolution_with_mixed_variables(self):
        """Test template resolution with both environment and default variables."""
        configured_servers = {
            "mixed-server": MCPServerConfigModel(
                server_id="mixed-server",
                server_type="test", 
                enabled=True,
                connection_params={
                    "args": ["--kubeconfig", "${KUBECONFIG}", "--token", "${MISSING_TOKEN}"]
                }
            )
        }
        
        # KUBECONFIG will use default, MISSING_TOKEN will cause fallback to original config
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            
            # Should succeed but use fallback config due to missing MISSING_TOKEN
            registry = MCPServerRegistry(configured_servers=configured_servers, settings=settings)
            
            config = registry.get_server_config("mixed-server")
            
            # Should use original template strings due to fallback
            assert "${KUBECONFIG}" in config.connection_params["args"]
            assert "${MISSING_TOKEN}" in config.connection_params["args"]
    
    def test_template_resolution_fallback_on_error(self):
        """Test that registry falls back to original config when template resolution fails."""
        # Create a server config with template that will fail
        config_with_template = {
            "failing-server": MCPServerMaskingFactory.create_failing_template_server_config()
        }
        
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            registry = MCPServerRegistry(config=config_with_template, settings=settings)
            
            # Should succeed but use original (non-resolved) config as fallback
            config = registry.get_server_config("failing-server")
            
            # Original template string should be preserved since resolution failed
            assert "${DEFINITELY_MISSING_VAR}" in config.connection_params["args"]
    
    def test_settings_integration_without_settings(self):
        """Test that registry works without Settings parameter (backwards compatibility)."""
        with patch.dict(os.environ, {'KUBECONFIG': '/env/kubeconfig'}):
            # No settings parameter - should still resolve from environment
            registry = MCPServerRegistry()
            
            k8s_config = registry.get_server_config("kubernetes-server")
            assert "/env/kubeconfig" in k8s_config.connection_params["args"]
    
    def test_complex_template_resolution(self):
        """Test complex template resolution scenarios."""
        configured_servers = {
            "complex-server": MCPServerConfigModel(**MCPServerMaskingFactory.create_complex_template_server_config())
        }
        
        env_vars = MCPServerMaskingFactory.create_template_environment_vars()
        with patch.dict(os.environ, env_vars):
            settings = Settings()
            registry = MCPServerRegistry(configured_servers=configured_servers, settings=settings)
            
            config = registry.get_server_config("complex-server")
            
            # Verify all templates resolved correctly
            assert config.connection_params["command"] == "complex-production"
            assert config.connection_params["args"] == ["--endpoint", "https://api.company.com:8443/api"]
            # CONFIG_PATH should be expanded absolute path, not tilde literal
            assert ".kube/config" in config.connection_params["env"]["CONFIG_PATH"]
            assert "~" not in config.connection_params["env"]["CONFIG_PATH"]
            assert config.connection_params["env"]["AUTH_TOKEN"] == "bearer-token-123"  # Environment


@pytest.mark.unit  
class TestMCPServerRegistryTemplateSettings:
    """Test Settings integration with template resolution."""
    
    def test_custom_settings_defaults(self):
        """Test that custom Settings defaults are used."""
        # Create Settings with custom defaults
        mock_settings = MagicMock(spec=Settings)
        mock_settings.get_template_default.side_effect = lambda var: {
            'KUBECONFIG': '/custom/default/kubeconfig',
            'CUSTOM_VAR': 'custom-default-value'
        }.get(var)
        
        configured_servers = {
            "custom-defaults-server": MCPServerConfigModel(
                server_id="custom-defaults-server",
                server_type="test",
                enabled=True,
                connection_params={
                    "args": ["--kubeconfig", "${KUBECONFIG}", "--custom", "${CUSTOM_VAR}"]
                }
            )
        }
        
        with patch.dict(os.environ, {}, clear=True):
            registry = MCPServerRegistry(configured_servers=configured_servers, settings=mock_settings)
            
            config = registry.get_server_config("custom-defaults-server")
            
            # Verify custom defaults were used
            assert config.connection_params["args"] == [
                "--kubeconfig", "/custom/default/kubeconfig",
                "--custom", "custom-default-value"
            ]
    
    def test_environment_overrides_settings_defaults(self):
        """Test that environment variables override settings defaults."""
        mock_settings = MagicMock(spec=Settings)
        mock_settings.get_template_default.return_value = "should-not-be-used"
        
        configured_servers = {
            "override-server": MCPServerConfigModel(
                server_id="override-server",
                server_type="test",
                enabled=True,
                connection_params={
                    "args": ["--value", "${TEST_VAR}"]
                }
            )
        }
        
        with patch.dict(os.environ, {'TEST_VAR': 'environment-value'}):
            registry = MCPServerRegistry(configured_servers=configured_servers, settings=mock_settings)
            
            config = registry.get_server_config("override-server")
            
            # Environment should override default
            assert config.connection_params["args"] == ["--value", "environment-value"]
            # The default value should not appear in the result
            assert "should-not-be-used" not in str(config.connection_params["args"])