"""End-to-end integration tests for configurable agents."""

import os
import tempfile
from unittest.mock import Mock, patch

import pytest

from tarsy.agents.configurable_agent import ConfigurableAgent
from tarsy.config.agent_config import ConfigurationError, ConfigurationLoader
from tarsy.services.agent_factory import AgentFactory
from tarsy.services.agent_registry import AgentRegistry
from tarsy.services.mcp_server_registry import MCPServerRegistry


@pytest.mark.integration
class TestConfigurableAgentsIntegration:
    """Integration tests for the complete configurable agents workflow."""

    @pytest.fixture
    def sample_config_yaml(self):
        """Sample YAML configuration for testing."""
        return """
agents:
  security-agent:
    alert_types:
      - security
      - intrusion
    mcp_servers:
      - security-tools
      - vulnerability-scanner
    custom_instructions: "Focus on threat detection and incident response."
  
  performance-agent:
    alert_types:
      - performance
      - resource-usage
    mcp_servers:
      - monitoring-server
    custom_instructions: "Monitor system performance and resource utilization."

mcp_servers:
  security-tools:
    server_id: security-tools
    server_type: security
    enabled: true
    connection_params:
      host: "security.local"
      port: 8080
    instructions: "Comprehensive security analysis tools"
  
  vulnerability-scanner:
    server_id: vulnerability-scanner
    server_type: security
    enabled: true
    connection_params:
      endpoint: "https://vuln-scanner.local/api"
    instructions: "Vulnerability scanning and assessment"
  
  monitoring-server:
    server_id: monitoring-server
    server_type: monitoring
    enabled: true
    connection_params:
      metrics_endpoint: "http://prometheus.local:9090"
      grafana_url: "http://grafana.local:3000"
"""

    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM client for testing."""
        mock = Mock()
        mock.analyze = Mock(return_value="Analysis complete")
        return mock

    @pytest.fixture
    def mock_mcp_client(self):
        """Mock MCP client for testing."""
        mock = Mock()
        mock.execute_tool = Mock(return_value={"result": "success"})
        return mock

    @pytest.fixture
    def temp_config_file(self, sample_config_yaml):
        """Create a temporary configuration file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(sample_config_yaml)
            temp_path = f.name
        
        yield temp_path
        
        # Cleanup
        os.unlink(temp_path)

    def test_end_to_end_configuration_loading_and_agent_creation(self, temp_config_file, mock_llm_client, mock_mcp_client):
        """Test complete workflow: load config → populate registries → create agents."""
        # Step 1: Load and validate configuration
        loader = ConfigurationLoader(temp_config_file)
        config = loader.load_and_validate()
        
        # Verify configuration was loaded correctly
        assert len(config.agents) == 2
        assert len(config.mcp_servers) == 3
        assert "security-agent" in config.agents
        assert "performance-agent" in config.agents
        
        # Step 2: Initialize registries with configuration
        agent_registry = AgentRegistry(agent_configs=config.agents)
        mcp_registry = MCPServerRegistry(configured_servers=config.mcp_servers)
        
        # Step 3: Initialize agent factory
        agent_factory = AgentFactory(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mcp_registry,
            agent_configs=config.agents
        )
        
        # Step 4: Test agent lookup and creation
        # Get agent ID for security alert
        agent_id = agent_registry.get_agent_for_alert_type("security")
        assert agent_id == "ConfigurableAgent:security-agent"
        
        # Create the agent
        agent = agent_factory.create_agent(agent_id)
        assert isinstance(agent, ConfigurableAgent)
        assert agent.agent_name == "security-agent"
        
        # Verify agent properties
        assert agent.get_supported_alert_types() == ["security", "intrusion"]
        assert agent.mcp_servers() == ["security-tools", "vulnerability-scanner"]
        assert agent.custom_instructions() == "Focus on threat detection and incident response."

    def test_mixed_built_in_and_configured_agents_workflow(self, temp_config_file, mock_llm_client, mock_mcp_client):
        """Test workflow with both built-in and configured agents."""
        # Load configuration
        loader = ConfigurationLoader(temp_config_file)
        config = loader.load_and_validate()
        
        # Mock a built-in agent
        with patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent'}):
            with patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', {'kubernetes-server': {'server_type': 'kubernetes', 'enabled': True}}):
                # Initialize registries
                agent_registry = AgentRegistry(agent_configs=config.agents)
                mcp_registry = MCPServerRegistry(configured_servers=config.mcp_servers)
                
                # Test that both built-in and configured agents are available
                # Built-in agent
                builtin_agent_id = agent_registry.get_agent_for_alert_type("kubernetes")
                assert builtin_agent_id == "KubernetesAgent"
                
                # Configured agent
                configured_agent_id = agent_registry.get_agent_for_alert_type("security")
                assert configured_agent_id == "ConfigurableAgent:security-agent"
                
                # Test that both built-in and configured MCP servers are available
                # Built-in MCP server
                builtin_server = mcp_registry.get_server_config("kubernetes-server")
                assert builtin_server.server_type == "kubernetes"
                
                # Configured MCP server
                configured_server = mcp_registry.get_server_config("security-tools")
                assert configured_server.server_type == "security"
                assert configured_server.connection_params["host"] == "security.local"

    def test_agent_creation_for_multiple_alert_types(self, temp_config_file, mock_llm_client, mock_mcp_client):
        """Test that agents can handle multiple alert types correctly."""
        loader = ConfigurationLoader(temp_config_file)
        config = loader.load_and_validate()
        
        agent_registry = AgentRegistry(agent_configs=config.agents)
        mcp_registry = MCPServerRegistry(configured_servers=config.mcp_servers)
        agent_factory = AgentFactory(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mcp_registry,
            agent_configs=config.agents
        )
        
        # Test that security-agent handles both "security" and "intrusion" alert types
        security_agent_id = agent_registry.get_agent_for_alert_type("security")
        intrusion_agent_id = agent_registry.get_agent_for_alert_type("intrusion")
        
        assert security_agent_id == "ConfigurableAgent:security-agent"
        assert intrusion_agent_id == "ConfigurableAgent:security-agent"
        
        # Create agents for both alert types - should be the same agent configuration
        security_agent = agent_factory.create_agent(security_agent_id)
        intrusion_agent = agent_factory.create_agent(intrusion_agent_id)
        
        # Both should be the same type with same configuration
        assert isinstance(security_agent, ConfigurableAgent)
        assert isinstance(intrusion_agent, ConfigurableAgent)
        assert security_agent.agent_name == intrusion_agent.agent_name == "security-agent"
        assert security_agent.get_supported_alert_types() == intrusion_agent.get_supported_alert_types()

    def test_mcp_server_configuration_integration(self, temp_config_file, mock_llm_client, mock_mcp_client):
        """Test that MCP server configurations are properly integrated."""
        loader = ConfigurationLoader(temp_config_file)
        config = loader.load_and_validate()
        
        mcp_registry = MCPServerRegistry(configured_servers=config.mcp_servers)
        
        # Test detailed MCP server configurations
        security_tools = mcp_registry.get_server_config("security-tools")
        assert security_tools.server_type == "security"
        assert security_tools.enabled is True
        assert security_tools.connection_params["host"] == "security.local"
        assert security_tools.connection_params["port"] == 8080
        assert security_tools.instructions == "Comprehensive security analysis tools"
        
        vuln_scanner = mcp_registry.get_server_config("vulnerability-scanner")
        assert vuln_scanner.server_type == "security"
        assert vuln_scanner.connection_params["endpoint"] == "https://vuln-scanner.local/api"
        
        monitoring = mcp_registry.get_server_config("monitoring-server")
        assert monitoring.server_type == "monitoring"
        assert monitoring.connection_params["metrics_endpoint"] == "http://prometheus.local:9090"
        assert monitoring.connection_params["grafana_url"] == "http://grafana.local:3000"

    def test_error_handling_in_integration_workflow(self, mock_llm_client, mock_mcp_client):
        """Test error handling throughout the integration workflow."""
        # Test with invalid YAML
        invalid_yaml = "invalid: yaml: content: ["
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(invalid_yaml)
            temp_path = f.name
        
        try:
            loader = ConfigurationLoader(temp_path)
            
            with pytest.raises(ConfigurationError) as exc_info:
                loader.load_and_validate()
                
            assert "Invalid YAML format" in str(exc_info.value)
            
        finally:
            os.unlink(temp_path)

    def test_agent_creation_with_missing_mcp_server_reference(self, mock_llm_client, mock_mcp_client):
        """Test error handling when agent references non-existent MCP server."""
        invalid_config_yaml = """
agents:
  bad-agent:
    alert_types:
      - test
    mcp_servers:
      - non-existent-server
      
mcp_servers:
  existing-server:
    server_id: existing-server
    server_type: test
    connection_params:
      host: test.local
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(invalid_config_yaml)
            temp_path = f.name
        
        try:
            loader = ConfigurationLoader(temp_path)
            
            with pytest.raises(ConfigurationError) as exc_info:
                loader.load_and_validate()
                
            assert "references unknown MCP server 'non-existent-server'" in str(exc_info.value)
            
        finally:
            os.unlink(temp_path)

    def test_empty_configuration_integration(self, mock_llm_client, mock_mcp_client):
        """Test integration workflow with empty configuration."""
        empty_config_yaml = """
agents: {}
mcp_servers: {}
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(empty_config_yaml)
            temp_path = f.name
        
        try:
            # Should work with empty configuration
            loader = ConfigurationLoader(temp_path)
            config = loader.load_and_validate()
            
            assert len(config.agents) == 0
            assert len(config.mcp_servers) == 0
            
            # Initialize registries with empty configuration
            agent_registry = AgentRegistry(agent_configs=config.agents)
            mcp_registry = MCPServerRegistry(configured_servers=config.mcp_servers)
            agent_factory = AgentFactory(
                llm_client=mock_llm_client,
                mcp_client=mock_mcp_client,
                mcp_registry=mcp_registry,
                agent_configs=config.agents
            )
            
            # Should fail when trying to get non-existent agent
            with pytest.raises(ValueError):
                agent_registry.get_agent_for_alert_type("nonexistent")
                
        finally:
            os.unlink(temp_path)

    def test_configuration_conflict_with_built_in_agents(self, temp_config_file, mock_llm_client, mock_mcp_client):
        """Test that configured agents conflicting with built-in agents cause an error as per EP-0006 design."""
        # Create config that conflicts with a built-in agent
        conflict_config_yaml = """
agents:
  custom-kubernetes-agent:
    alert_types:
      - kubernetes  # This conflicts with built-in kubernetes agent
    mcp_servers:
      - custom-k8s-tools
      
mcp_servers:
  custom-k8s-tools:
    server_id: custom-k8s-tools
    server_type: kubernetes
    enabled: true
    instructions: "Custom Kubernetes monitoring"
    connection_params:
      host: k8s.local
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(conflict_config_yaml)
            temp_path = f.name
        
        try:
            # Mock built-in kubernetes agent
            with patch('tarsy.config.builtin_config.BUILTIN_AGENT_MAPPINGS', {'kubernetes': 'KubernetesAgent'}):
                loader = ConfigurationLoader(temp_path)
                
                # Should raise ConfigurationError due to conflict
                with pytest.raises(ConfigurationError) as exc_info:
                    loader.load_and_validate()
                
                # Verify the error message indicates the conflict
                assert "Alert type 'kubernetes' handled by both" in str(exc_info.value)
                assert "built-in:KubernetesAgent" in str(exc_info.value)
                assert "configured:custom-kubernetes-agent" in str(exc_info.value)
                
        finally:
            os.unlink(temp_path)

    def test_disabled_mcp_server_integration(self, mock_llm_client, mock_mcp_client):
        """Test integration with disabled MCP servers."""
        config_with_disabled_server = """
agents:
  test-agent:
    alert_types:
      - test
    mcp_servers:
      - enabled-server
      
mcp_servers:
  enabled-server:
    server_id: enabled-server
    server_type: test
    enabled: true
    connection_params:
      host: test.local
  
  disabled-server:
    server_id: disabled-server
    server_type: test
    enabled: false
    connection_params:
      host: test.local
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_with_disabled_server)
            temp_path = f.name
        
        try:
            loader = ConfigurationLoader(temp_path)
            config = loader.load_and_validate()
            
            mcp_registry = MCPServerRegistry(configured_servers=config.mcp_servers)
            
            # Both servers should be accessible
            enabled_server = mcp_registry.get_server_config("enabled-server")
            disabled_server = mcp_registry.get_server_config("disabled-server")
            
            assert enabled_server.enabled is True
            assert disabled_server.enabled is False
            
        finally:
            os.unlink(temp_path)

    def test_complex_multi_agent_scenario(self, mock_llm_client, mock_mcp_client):
        """Test complex scenario with multiple agents and servers."""
        complex_config = """
agents:
  security-specialist:
    alert_types:
      - security
      - malware
    mcp_servers:
      - security-tools
      - threat-intel
  
  performance-monitor:
    alert_types:
      - performance
      - cpu-usage
      - memory-usage
    mcp_servers:
      - monitoring-stack
      - metrics-collector
  
  database-expert:
    alert_types:
      - database
      - sql-performance
    mcp_servers:
      - db-tools
      - query-analyzer

mcp_servers:
  security-tools:
    server_id: security-tools
    server_type: security
    enabled: true
    connection_params:
      host: security.local
  
  threat-intel:
    server_id: threat-intel
    server_type: security
    enabled: true
    connection_params:
      host: threat.local
  
  monitoring-stack:
    server_id: monitoring-stack
    server_type: monitoring
    enabled: true
    connection_params:
      host: monitoring.local
  
  metrics-collector:
    server_id: metrics-collector
    server_type: monitoring
    enabled: true
    connection_params:
      host: metrics.local
  
  db-tools:
    server_id: db-tools
    server_type: database
    enabled: true
    connection_params:
      host: db.local
  
  query-analyzer:
    server_id: query-analyzer
    server_type: database
    enabled: true
    connection_params:
      host: query.local
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(complex_config)
            temp_path = f.name
        
        try:
            # Load and validate
            loader = ConfigurationLoader(temp_path)
            config = loader.load_and_validate()
            
            # Initialize all components
            agent_registry = AgentRegistry(agent_configs=config.agents)
            mcp_registry = MCPServerRegistry(configured_servers=config.mcp_servers)
            agent_factory = AgentFactory(
                llm_client=mock_llm_client,
                mcp_client=mock_mcp_client,
                mcp_registry=mcp_registry,
                agent_configs=config.agents
            )
            
            # Test each alert type resolves to correct agent
            test_cases = [
                ("security", "ConfigurableAgent:security-specialist"),
                ("malware", "ConfigurableAgent:security-specialist"),
                ("performance", "ConfigurableAgent:performance-monitor"),
                ("cpu-usage", "ConfigurableAgent:performance-monitor"),
                ("memory-usage", "ConfigurableAgent:performance-monitor"),
                ("database", "ConfigurableAgent:database-expert"),
                ("sql-performance", "ConfigurableAgent:database-expert"),
            ]
            
            for alert_type, expected_agent_id in test_cases:
                agent_id = agent_registry.get_agent_for_alert_type(alert_type)
                assert agent_id == expected_agent_id
                
                # Create and verify agent
                agent = agent_factory.create_agent(agent_id)
                assert isinstance(agent, ConfigurableAgent)
                assert alert_type in agent.get_supported_alert_types()
            
            # Verify all MCP servers are accessible
            for server_id in ["security-tools", "threat-intel", "monitoring-stack", 
                             "metrics-collector", "db-tools", "query-analyzer"]:
                server_config = mcp_registry.get_server_config(server_id)
                assert server_config.enabled is True
                
        finally:
            os.unlink(temp_path) 