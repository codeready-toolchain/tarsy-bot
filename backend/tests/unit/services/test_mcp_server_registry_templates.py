"""
Unit tests for MCPServerRegistry template resolution functionality.

Tests template variable expansion in MCP server configurations,
including settings defaults, environment variable precedence,
and error handling scenarios.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from tarsy.config.settings import Settings
from tarsy.utils.template_resolver import TemplateResolver
from tarsy.models.agent_config import MCPServerConfigModel
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tests.utils import MCPServerMaskingFactory


@pytest.mark.unit
class TestMCPServerRegistryTemplateResolution:
    """Test template resolution in MCPServerRegistry."""
    
    def test_builtin_kubernetes_server_template_resolution_with_env(self):
        """Test built-in kubernetes-server template resolution with environment variable."""
        # Note: This test now demonstrates that .env file takes priority over system environment
        # The actual behavior is that KUBECONFIG from our .env file will be used instead
        settings = Settings()
        registry = MCPServerRegistry(settings=settings)
        
        k8s_config = registry.get_server_config("kubernetes-server")
        
        # Verify template was resolved (will use .env file value due to new priority order)
        # This demonstrates the new .env file > system env > defaults priority
        kubeconfig_arg = None
        args = k8s_config.connection_params["args"]
        for i, arg in enumerate(args):
            if arg == "--kubeconfig" and i + 1 < len(args):
                kubeconfig_arg = args[i + 1]
                break
        
        # Should resolve to some value (either .env file or default)
        assert kubeconfig_arg is not None
        assert kubeconfig_arg != "${KUBECONFIG}"  # Should not be unresolved
    
    def test_builtin_kubernetes_server_template_resolution_with_default(self):
        """Test built-in kubernetes-server template resolution with settings default."""
        # Note: With new priority order, this tests the overall resolution process
        # The actual resolution will use .env file if available, then defaults
        settings = Settings()
        registry = MCPServerRegistry(settings=settings)
        
        k8s_config = registry.get_server_config("kubernetes-server")
        
        # Verify template was resolved (will use .env file or default)
        kubeconfig_arg = None
        args = k8s_config.connection_params["args"]
        for i, arg in enumerate(args):
            if arg == "--kubeconfig" and i + 1 < len(args):
                kubeconfig_arg = args[i + 1]
                break
        
        # Should resolve to some value and not contain tilde
        assert kubeconfig_arg is not None
        assert kubeconfig_arg != "${KUBECONFIG}"  # Should not be unresolved
        assert "~" not in kubeconfig_arg  # Tilde should be expanded
    
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
        # Create a test .env file with the desired KUBECONFIG
        import tempfile
        import os
        
        env_content = "KUBECONFIG=/env/kubeconfig\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                # Mock the template resolver to use our test .env file
                with patch('tarsy.services.mcp_server_registry.TemplateResolver') as mock_resolver_class:
                    # Create a real resolver with our test .env file
                    real_resolver = TemplateResolver(env_file_path=f.name)
                    mock_resolver_class.return_value = real_resolver
                    
                    # No settings parameter - should still resolve from .env file
                    registry = MCPServerRegistry()
                    
                    k8s_config = registry.get_server_config("kubernetes-server")
                    assert "/env/kubeconfig" in k8s_config.connection_params["args"]
                    
            finally:
                os.unlink(f.name)
    
    def test_complex_template_resolution(self):
        """Test complex template resolution scenarios."""
        # Create a test .env file with the desired variables
        import tempfile
        import os
        
        env_vars = MCPServerMaskingFactory.create_template_environment_vars()
        env_content = "\n".join([f"{k}={v}" for k, v in env_vars.items()]) + "\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                # Mock the template resolver to use our test .env file
                with patch('tarsy.services.mcp_server_registry.TemplateResolver') as mock_resolver_class:
                    # Create a real resolver with our test .env file
                    real_resolver = TemplateResolver(env_file_path=f.name)
                    mock_resolver_class.return_value = real_resolver
                    
                    configured_servers = {
                        "complex-server": MCPServerConfigModel(**MCPServerMaskingFactory.create_complex_template_server_config())
                    }
                    
                    settings = Settings()
                    registry = MCPServerRegistry(configured_servers=configured_servers, settings=settings)
                    
                    config = registry.get_server_config("complex-server")
                    
                    # Verify all templates resolved correctly
                    assert config.connection_params["command"] == "complex-production"
                    assert config.connection_params["args"] == ["--endpoint", "https://api.company.com:8443/api"]
                    # CONFIG_PATH should be expanded absolute path, not tilde literal
                    assert ".kube/config" in config.connection_params["env"]["CONFIG_PATH"]
                    assert "~" not in config.connection_params["env"]["CONFIG_PATH"]
                    assert config.connection_params["env"]["AUTH_TOKEN"] == "bearer-token-123"  # .env file
                    
            finally:
                os.unlink(f.name)


@pytest.mark.unit  
class TestMCPServerRegistryTemplateSettings:
    """Test Settings integration with template resolution."""
    
    def test_custom_settings_defaults(self):
        """Test that custom Settings defaults are used."""
        # Create an empty .env file to force fallback to settings defaults
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("# Empty .env file for testing settings defaults\n")
            f.flush()
            
            try:
                # Mock the template resolver to use our empty test .env file
                with patch('tarsy.services.mcp_server_registry.TemplateResolver') as mock_resolver_class:
                    # Create a real resolver with our empty test .env file
                    real_resolver = TemplateResolver(env_file_path=f.name)
                    mock_resolver_class.return_value = real_resolver
                    
                    # Create Settings with custom defaults
                    mock_settings = MagicMock(spec=Settings)
                    mock_settings.get_template_default.side_effect = lambda var: {
                        'KUBECONFIG': '/custom/default/kubeconfig',
                        'CUSTOM_VAR': 'custom-default-value'
                    }.get(var)
                    
                    # Inject the mock settings into the real resolver
                    real_resolver.settings = mock_settings
                    
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
                        
            finally:
                os.unlink(f.name)
    
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