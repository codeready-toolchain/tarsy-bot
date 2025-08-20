"""
Unit tests for AlertService template integration.

Tests that template resolution works correctly when AlertService
creates MCPServerRegistry with Settings, ensuring end-to-end 
template functionality.
"""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest
import yaml

from tarsy.config.settings import Settings
from tarsy.models.constants import IterationStrategy
from tarsy.services.alert_service import AlertService


@pytest.mark.unit
class TestAlertServiceTemplateIntegration:
    """Test template integration in AlertService initialization."""
    
    @patch('tarsy.services.alert_service.RunbookService')
    @patch('tarsy.services.alert_service.get_history_service')
    @patch('tarsy.services.alert_service.ChainRegistry')
    @patch('tarsy.services.alert_service.MCPClient')
    @patch('tarsy.services.alert_service.LLMManager')
    def test_alert_service_passes_settings_to_mcp_registry(
        self, mock_llm_manager, mock_mcp_client, mock_chain_registry, 
        mock_history_service, mock_runbook_service
    ):
        """Test that AlertService passes Settings to MCPServerRegistry."""
        settings = Settings()
        
        with patch('tarsy.services.alert_service.MCPServerRegistry') as mock_registry_class:
            mock_registry = Mock()
            mock_registry_class.return_value = mock_registry
            
            alert_service = AlertService(settings)
            
            # Verify MCPServerRegistry was created with settings and configured_servers
            mock_registry_class.assert_called_once_with(
                settings=settings,
                configured_servers={}  # Empty dict when no config is loaded
            )
            assert alert_service.mcp_server_registry == mock_registry
    
    def test_alert_service_template_resolution_integration(self):
        """Test that template resolution works through AlertService initialization."""
        with patch.dict(os.environ, {'KUBECONFIG': '/integration/test/kubeconfig'}):
            settings = Settings()
            
            # Mock other services to focus on MCP registry
            with patch('tarsy.services.alert_service.RunbookService'), \
                 patch('tarsy.services.alert_service.get_history_service'), \
                 patch('tarsy.services.alert_service.ChainRegistry'), \
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
                 patch('tarsy.services.alert_service.ChainRegistry'), \
                 patch('tarsy.services.alert_service.MCPClient'), \
                 patch('tarsy.services.alert_service.LLMManager'):
                
                alert_service = AlertService(settings)
                
                # Get kubernetes server config
                k8s_config = alert_service.mcp_server_registry.get_server_config("kubernetes-server")
                
                # Verify expanded default was used (not tilde literal)
                assert ".kube/config" in str(k8s_config.connection_params["args"])
                assert "~" not in str(k8s_config.connection_params["args"])
    
    @patch('tarsy.services.alert_service.logger')
    def test_alert_service_template_error_handling(self, mock_logger):
        """Test AlertService handles template resolution errors gracefully."""
        # Create a custom Settings that would cause template errors
        mock_settings = Mock(spec=Settings)
        mock_settings.agent_config_path = None  # Prevent agent config loading
        mock_settings.get_template_default.return_value = None
        
        # Mock other services
        with patch('tarsy.services.alert_service.RunbookService'), \
             patch('tarsy.services.alert_service.get_history_service'), \
             patch('tarsy.services.alert_service.ChainRegistry'), \
             patch('tarsy.services.alert_service.MCPClient'), \
             patch('tarsy.services.alert_service.LLMManager'):
            
            # Should not raise exception - AlertService should initialize successfully
            # Template resolution errors are handled in MCPServerRegistry with fallback
            alert_service = AlertService(mock_settings)
            
            # Service should be created successfully 
            assert alert_service.mcp_server_registry is not None
            assert alert_service.settings == mock_settings

    def test_alert_service_configurable_agent_configuration_loading(self):
        """Test that AlertService properly loads configurable agent and chain configurations from files."""
        # Create a test configuration file with configurable agents and chains
        config_yaml = """
agents:
  security-analyzer:
    alert_types: ["security", "intrusion"]
    mcp_servers: ["kubernetes-server"]
    iteration_strategy: react
    custom_instructions: "Analyze security alerts using ReAct reasoning"
  
  performance-monitor:
    alert_types: ["performance", "resource-usage"]
    mcp_servers: ["kubernetes-server"]
    iteration_strategy: react
    custom_instructions: "Monitor performance metrics"

  data-collector:
    alert_types: ["kubernetes"]
    mcp_servers: ["custom-k8s-server"]
    iteration_strategy: react-stage
    custom_instructions: "Collect data from Kubernetes cluster"

  analyzer:
    alert_types: ["kubernetes"]
    mcp_servers: ["custom-k8s-server"]
    iteration_strategy: react-final-analysis
    custom_instructions: "Analyze collected data and provide insights"

agent_chains:
  security-analysis-chain:
    alert_types: ["security", "intrusion"]
    stages:
      - name: "analysis"
        agent: "ConfigurableAgent:security-analyzer"
        iteration_strategy: "react"
  
  kubernetes-analysis-chain:
    alert_types: ["kubernetes"]
    stages:
      - name: "data-collection"
        agent: "ConfigurableAgent:data-collector"
        iteration_strategy: "react-stage"
      - name: "analysis"
        agent: "ConfigurableAgent:analyzer"
        iteration_strategy: "react-final-analysis"

mcp_servers:
  custom-k8s-server:
    server_id: custom-k8s-server
    server_type: kubernetes
    enabled: true
    connection_params:
      kubeconfig: "/custom/path/kubeconfig"
    instructions: "Custom Kubernetes troubleshooting"
        """
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(yaml.safe_load(config_yaml), f)
            temp_path = f.name
        
        try:
            # Create settings with the config file path
            settings = Settings()
            settings.agent_config_path = temp_path
            
            # Mock other services
            with patch('tarsy.services.alert_service.RunbookService'), \
                 patch('tarsy.services.alert_service.get_history_service'), \
                 patch('tarsy.services.alert_service.ChainRegistry'), \
                 patch('tarsy.services.alert_service.MCPServerRegistry'), \
                 patch('tarsy.services.alert_service.MCPClient'), \
                 patch('tarsy.services.alert_service.LLMManager'):
                
                # Create AlertService
                alert_service = AlertService(settings)
                
                # Verify configuration was loaded correctly
                assert len(alert_service.parsed_config.agents) == 4
                assert "security-analyzer" in alert_service.parsed_config.agents
                assert "performance-monitor" in alert_service.parsed_config.agents
                assert "data-collector" in alert_service.parsed_config.agents
                assert "analyzer" in alert_service.parsed_config.agents
                
                # Verify agent configurations
                security_config = alert_service.parsed_config.agents["security-analyzer"]
                assert security_config.alert_types == ["security", "intrusion"]
                assert security_config.iteration_strategy == IterationStrategy.REACT
                assert "ReAct reasoning" in security_config.custom_instructions
                
                performance_config = alert_service.parsed_config.agents["performance-monitor"]
                assert performance_config.alert_types == ["performance", "resource-usage"]
                assert performance_config.iteration_strategy == IterationStrategy.REACT
                assert "Monitor performance metrics" in performance_config.custom_instructions
                
                # Verify MCP server configuration
                assert len(alert_service.parsed_config.mcp_servers) == 1
                assert "custom-k8s-server" in alert_service.parsed_config.mcp_servers
                
                k8s_config = alert_service.parsed_config.mcp_servers["custom-k8s-server"]
                assert k8s_config.server_id == "custom-k8s-server"
                assert k8s_config.server_type == "kubernetes"
                assert k8s_config.enabled is True
                assert "/custom/path/kubeconfig" in str(k8s_config.connection_params)
                
                # Verify chain configuration was loaded
                assert len(alert_service.parsed_config.agent_chains) == 2
                assert "security-analysis-chain" in alert_service.parsed_config.agent_chains
                assert "kubernetes-analysis-chain" in alert_service.parsed_config.agent_chains
                
                # Verify security chain configuration
                security_chain = alert_service.parsed_config.agent_chains["security-analysis-chain"]
                assert security_chain.alert_types == ["security", "intrusion"]
                assert len(security_chain.stages) == 1
                assert security_chain.stages[0].name == "analysis"
                assert security_chain.stages[0].agent == "ConfigurableAgent:security-analyzer"
                assert security_chain.stages[0].iteration_strategy == "react"
                
                # Verify kubernetes chain configuration
                k8s_chain = alert_service.parsed_config.agent_chains["kubernetes-analysis-chain"]
                assert k8s_chain.alert_types == ["kubernetes"]
                assert len(k8s_chain.stages) == 2
                assert k8s_chain.stages[0].name == "data-collection"
                assert k8s_chain.stages[0].agent == "ConfigurableAgent:data-collector"
                assert k8s_chain.stages[0].iteration_strategy == "react-stage"
                assert k8s_chain.stages[1].name == "analysis"
                assert k8s_chain.stages[1].agent == "ConfigurableAgent:analyzer"
                assert k8s_chain.stages[1].iteration_strategy == "react-final-analysis"
                
        finally:
            os.unlink(temp_path)