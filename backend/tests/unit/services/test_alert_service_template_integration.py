"""
Unit tests for AlertService template integration.

Tests that template resolution works correctly when AlertService
creates MCPServerRegistry with Settings, ensuring end-to-end 
template functionality.
"""

import os
import pytest
from unittest.mock import patch, Mock

from tarsy.config.settings import Settings
from tarsy.services.alert_service import AlertService


@pytest.mark.unit
class TestAlertServiceTemplateIntegration:
    """Test template integration in AlertService initialization."""
    
    @patch('tarsy.services.alert_service.RunbookService')
    @patch('tarsy.services.alert_service.get_history_service')
    @patch('tarsy.services.alert_service.AgentRegistry')
    @patch('tarsy.services.alert_service.MCPClient')
    @patch('tarsy.services.alert_service.LLMManager')
    def test_alert_service_passes_settings_to_mcp_registry(
        self, mock_llm_manager, mock_mcp_client, mock_agent_registry, 
        mock_history_service, mock_runbook_service
    ):
        """Test that AlertService passes Settings to MCPServerRegistry."""
        settings = Settings()
        
        with patch('tarsy.services.alert_service.MCPServerRegistry') as mock_registry_class:
            mock_registry = Mock()
            mock_registry_class.return_value = mock_registry
            
            alert_service = AlertService(settings)
            
            # Verify MCPServerRegistry was created with settings
            mock_registry_class.assert_called_once_with(settings=settings)
            assert alert_service.mcp_server_registry == mock_registry
    
    def test_alert_service_template_resolution_integration(self):
        """Test that template resolution works through AlertService initialization."""
        with patch.dict(os.environ, {'KUBECONFIG': '/integration/test/kubeconfig'}):
            settings = Settings()
            
            # Mock other services to focus on MCP registry
            with patch('tarsy.services.alert_service.RunbookService'), \
                 patch('tarsy.services.alert_service.get_history_service'), \
                 patch('tarsy.services.alert_service.AgentRegistry'), \
                 patch('tarsy.services.alert_service.MCPClient'), \
                 patch('tarsy.services.alert_service.LLMManager'):
                
                alert_service = AlertService(settings)
                
                # Get the actual kubernetes server config through the service
                k8s_config = alert_service.mcp_server_registry.get_server_config("kubernetes-server")
                
                # Verify template was resolved with environment variable
                assert "/integration/test/kubeconfig" in k8s_config.connection_params["args"]
    
    def test_alert_service_template_defaults_integration(self):
        """Test that settings defaults work through AlertService."""
        # Clear environment to force use of defaults
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            
            # Mock other services
            with patch('tarsy.services.alert_service.RunbookService'), \
                 patch('tarsy.services.alert_service.get_history_service'), \
                 patch('tarsy.services.alert_service.AgentRegistry'), \
                 patch('tarsy.services.alert_service.MCPClient'), \
                 patch('tarsy.services.alert_service.LLMManager'):
                
                alert_service = AlertService(settings)
                
                # Get kubernetes server config
                k8s_config = alert_service.mcp_server_registry.get_server_config("kubernetes-server")
                
                # Verify default was used
                assert "~/.kube/config" in k8s_config.connection_params["args"]
    
    @patch('tarsy.services.alert_service.logger')
    def test_alert_service_template_error_handling(self, mock_logger):
        """Test AlertService handles template resolution errors gracefully."""
        # Create a custom Settings that would cause template errors
        mock_settings = Mock(spec=Settings)
        mock_settings.get_template_default.return_value = None
        
        # Mock other services
        with patch('tarsy.services.alert_service.RunbookService'), \
             patch('tarsy.services.alert_service.get_history_service'), \
             patch('tarsy.services.alert_service.AgentRegistry'), \
             patch('tarsy.services.alert_service.MCPClient'), \
             patch('tarsy.services.alert_service.LLMManager'):
            
            # Should not raise exception - AlertService should initialize successfully
            # Template resolution errors are handled in MCPServerRegistry with fallback
            alert_service = AlertService(mock_settings)
            
            # Service should be created successfully 
            assert alert_service.mcp_server_registry is not None
            assert alert_service.settings == mock_settings