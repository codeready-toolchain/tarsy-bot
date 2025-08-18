"""
Integration tests for iteration strategies.

Tests end-to-end behavior differences between REGULAR and REACT iteration strategies
to ensure they work correctly in realistic scenarios.
"""

import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.agents.configurable_agent import ConfigurableAgent
from tarsy.models.constants import IterationStrategy, StageStatus
from tarsy.agents.kubernetes_agent import KubernetesAgent
from tarsy.config.agent_config import ConfigurationLoader
from tarsy.models.agent_config import AgentConfigModel
from tarsy.services.agent_factory import AgentFactory
from tarsy.services.mcp_server_registry import MCPServerRegistry


@pytest.mark.integration
class TestIterationStrategiesIntegration:
    """Integration tests comparing REGULAR vs REACT iteration strategies."""
    
    @pytest.fixture
    def sample_alert_data(self):
        """Sample alert for testing."""
        return {
            "alert": "PodCrashLoopBackOff",
            "message": "Pod is failing to start repeatedly",
            "severity": "critical",
            "environment": "production",
            "cluster": "prod-cluster",
            "namespace": "production",
            "pod": "web-app-123"
        }
    
    @pytest.fixture
    def sample_runbook(self):
        """Sample runbook content."""
        return """
        ## PodCrashLoopBackOff Troubleshooting
        
        1. Check pod logs
        2. Describe pod for events
        3. Check resource constraints
        4. Verify configuration
        """
    
    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM client for testing."""
        client = Mock()
        client.generate_response = AsyncMock()
        return client
    
    @pytest.fixture
    def mock_mcp_client(self):
        """Mock MCP client for testing."""
        client = Mock()
        client.list_tools = AsyncMock(return_value={
            "kubernetes-server": [
                {"name": "kubectl-get-pods", "description": "Get pods"},
                {"name": "kubectl-describe-pod", "description": "Describe pod"}
            ]
        })
        client.call_tool = AsyncMock(return_value={
            "status": "success",
            "output": "Pod logs retrieved"
        })
        return client
    
    @pytest.fixture
    def mock_mcp_registry(self):
        """Mock MCP server registry."""
        registry = Mock(spec=MCPServerRegistry)
        mock_config = Mock()
        mock_config.server_id = "kubernetes-server"
        mock_config.server_type = "kubernetes"
        mock_config.instructions = "Kubernetes troubleshooting tools"
        registry.get_server_configs.return_value = [mock_config]
        registry.get_server_config.return_value = mock_config
        return registry
    
    @pytest.mark.asyncio
    async def test_kubernetes_agent_regular_vs_react_strategies(
        self, mock_llm_client, mock_mcp_client, mock_mcp_registry, 
        sample_alert_data, sample_runbook
    ):
        """Test KubernetesAgent with both REGULAR and REACT strategies."""
        # Mock LLM responses
        mock_llm_client.generate_response.return_value = "Analysis completed successfully"
        
        # Create agents with different strategies
        regular_agent = KubernetesAgent(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry,
            iteration_strategy=IterationStrategy.REGULAR
        )
        
        react_agent = KubernetesAgent(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry,
            iteration_strategy=IterationStrategy.REACT
        )
        
        # Verify different strategies assigned
        assert regular_agent.iteration_strategy == IterationStrategy.REGULAR
        assert react_agent.iteration_strategy == IterationStrategy.REACT
        
        # Mock additional methods needed for processing
        for agent in [regular_agent, react_agent]:
            agent.determine_mcp_tools = AsyncMock(return_value=[])
            agent.determine_next_mcp_tools = AsyncMock(return_value={"continue": False})
            agent.analyze_alert = AsyncMock(return_value="Strategy-specific analysis")
        
        # Process alert with both strategies
        from tarsy.models.alert_processing import AlertProcessingData
        alert_processing_data = AlertProcessingData(
            alert_type="kubernetes",  # sample_alert_data is dict, not Alert object
            alert_data=sample_alert_data,
            runbook_content=sample_runbook
        )
        
        regular_result = await regular_agent.process_alert(
            alert_processing_data, "test-session-regular"
        )
        
        react_result = await react_agent.process_alert(
            alert_processing_data, "test-session-react"
        )
        
        # Both should succeed but potentially use different processing paths
        assert regular_result.status == StageStatus.COMPLETED
        assert react_result.status == StageStatus.COMPLETED
        
        # Results should be different (different iteration strategies produce different outputs)
        assert regular_result.result_summary != react_result.result_summary
    
    @pytest.mark.asyncio
    async def test_configurable_agent_iteration_strategies(
        self, mock_llm_client, mock_mcp_client, mock_mcp_registry,
        sample_alert_data, sample_runbook
    ):
        """Test ConfigurableAgent with different iteration strategies."""
        # Mock LLM responses
        mock_llm_client.generate_response.return_value = "Configurable analysis complete"
        
        # Create configurations with different strategies
        regular_config = AgentConfigModel(
            alert_types=["kubernetes"],
            mcp_servers=["kubernetes-server"],
            custom_instructions="Use regular processing",
            iteration_strategy=IterationStrategy.REGULAR
        )
        
        react_config = AgentConfigModel(
            alert_types=["kubernetes"],
            mcp_servers=["kubernetes-server"],
            custom_instructions="Use ReAct processing", 
            iteration_strategy=IterationStrategy.REACT
        )
        
        # Create agents
        regular_agent = ConfigurableAgent(
            agent_name="regular-k8s-agent",
            config=regular_config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        react_agent = ConfigurableAgent(
            agent_name="react-k8s-agent",
            config=react_config,
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        # Verify strategies
        assert regular_agent.iteration_strategy == IterationStrategy.REGULAR
        assert react_agent.iteration_strategy == IterationStrategy.REACT
        
        # Mock processing methods
        for agent in [regular_agent, react_agent]:
            agent.determine_mcp_tools = AsyncMock(return_value=[])
            agent.determine_next_mcp_tools = AsyncMock(return_value={"continue": False})
            agent.analyze_alert = AsyncMock(return_value="Configurable agent analysis")
        
        # Process alerts
        from tarsy.models.alert_processing import AlertProcessingData
        alert_processing_data = AlertProcessingData(
            alert_type="kubernetes",  # sample_alert_data is dict, not Alert object
            alert_data=sample_alert_data,
            runbook_content=sample_runbook
        )
        
        regular_result = await regular_agent.process_alert(
            alert_processing_data, "test-config-regular"
        )
        
        react_result = await react_agent.process_alert(
            alert_processing_data, "test-config-react"
        )
        
        # Verify results
        assert regular_result.status == StageStatus.COMPLETED
        assert react_result.status == StageStatus.COMPLETED
        
        # Results should be different (different iteration strategies produce different outputs)
        assert regular_result.result_summary != react_result.result_summary
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_agent_factory_creates_agents_with_correct_strategies(
        self, mock_k8s_agent, mock_llm_client, mock_mcp_client, mock_mcp_registry
    ):
        """Test AgentFactory creates agents with correct iteration strategies."""
        mock_agent_instance = Mock()
        mock_k8s_agent.return_value = mock_agent_instance
        
        # Create factory after patching KubernetesAgent 
        factory = AgentFactory(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        # Create agent - should use default REACT strategy
        agent = factory.create_agent("KubernetesAgent")
        
        # Verify factory called agent with REACT strategy
        mock_k8s_agent.assert_called_with(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry,
            iteration_strategy=IterationStrategy.REACT
        )
        
        assert agent == mock_agent_instance
    
    def test_yaml_configuration_with_iteration_strategies(self):
        """Test loading agents from YAML configuration with iteration strategies."""
        config_yaml = """
agents:
  regular-security-agent:
    alert_types:
      - security
      - intrusion
    mcp_servers:
      - security-tools
    iteration_strategy: regular
    custom_instructions: "Use regular processing for security alerts"
  
  react-performance-agent:
    alert_types:
      - performance
      - resource-usage
    mcp_servers:
      - monitoring-server
    iteration_strategy: react
    custom_instructions: "Use ReAct reasoning for performance analysis"

mcp_servers:
  security-tools:
    server_id: security-tools
    server_type: security
    enabled: true
    connection_params:
      command: "/usr/bin/security-scanner"
    instructions: "Security analysis tools"
  
  monitoring-server:
    server_id: monitoring-server
    server_type: monitoring
    enabled: true
    connection_params:
      endpoint: "http://monitoring.local:9090"
    instructions: "Performance monitoring tools"
        """
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_yaml)
            temp_path = f.name
        
        try:
            # Load configuration
            loader = ConfigurationLoader(temp_path)
            config = loader.load_and_validate()
            
            # Verify agent configurations loaded correctly
            assert len(config.agents) == 2
            
            regular_agent_config = config.agents["regular-security-agent"]
            react_agent_config = config.agents["react-performance-agent"]
            
            # Verify iteration strategies
            assert regular_agent_config.iteration_strategy == IterationStrategy.REGULAR
            assert react_agent_config.iteration_strategy == IterationStrategy.REACT
            
            # Verify other properties
            assert regular_agent_config.alert_types == ["security", "intrusion"]
            assert react_agent_config.alert_types == ["performance", "resource-usage"]
            
            # Verify custom instructions
            assert "regular processing" in regular_agent_config.custom_instructions
            assert "ReAct reasoning" in react_agent_config.custom_instructions
            
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_end_to_end_yaml_to_agent_execution(
        self, mock_llm_client, mock_mcp_client, sample_alert_data, sample_runbook
    ):
        """Test complete flow from YAML config to agent execution with different strategies."""
        config_yaml = """
agents:
  test-regular-agent:
    alert_types: ["test-alerts"]
    mcp_servers: ["test-k8s-server"]
    iteration_strategy: regular
    custom_instructions: "Simple processing"
  
  test-react-agent:
    alert_types: ["test-performance"] 
    mcp_servers: ["test-k8s-server"]
    iteration_strategy: react
    custom_instructions: "Reasoning-based processing"

mcp_servers:
  test-k8s-server:
    server_id: test-k8s-server
    server_type: kubernetes
    enabled: true
    connection_params:
      kubeconfig: "/tmp/kubeconfig"
    instructions: "Kubernetes troubleshooting"
        """
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_yaml)
            temp_path = f.name
        
        try:
            # Load configuration
            loader = ConfigurationLoader(temp_path)
            config = loader.load_and_validate()
            
            # Create MCP registry
            mcp_registry = MCPServerRegistry(configured_servers=config.mcp_servers)
            
            # Mock the get_server_config method
            mock_server_config = Mock()
            mock_server_config.server_id = "test-k8s-server"
            mock_server_config.server_type = "kubernetes"
            mock_server_config.instructions = "Kubernetes troubleshooting"
            mcp_registry.get_server_config = Mock(return_value=mock_server_config)
            mcp_registry.get_server_configs = Mock(return_value=[mock_server_config])
            
            # Create agent factory
            factory = AgentFactory(
                llm_client=mock_llm_client,
                mcp_client=mock_mcp_client,
                mcp_registry=mcp_registry,
                agent_configs=config.agents
            )
            
            # Create agents with different strategies
            regular_agent = factory.create_agent("ConfigurableAgent:test-regular-agent")
            react_agent = factory.create_agent("ConfigurableAgent:test-react-agent")
            
            # Verify correct strategies assigned
            assert regular_agent.iteration_strategy == IterationStrategy.REGULAR
            assert react_agent.iteration_strategy == IterationStrategy.REACT
            
            # Mock processing for testing
            mock_llm_client.generate_response.return_value = "YAML config test analysis"
            
            for agent in [regular_agent, react_agent]:
                agent.determine_mcp_tools = AsyncMock(return_value=[])
                agent.determine_next_mcp_tools = AsyncMock(return_value={"continue": False})
                agent.analyze_alert = AsyncMock(return_value="YAML test analysis")
            
            # Process alerts with both agents
            from tarsy.models.alert_processing import AlertProcessingData
            alert_processing_data = AlertProcessingData(
                alert_type="kubernetes",  # sample_alert_data is dict, not Alert object
                alert_data=sample_alert_data,
                runbook_content=sample_runbook
            )
            
            regular_result = await regular_agent.process_alert(
                alert_processing_data, "yaml-regular-test"
            )
            
            react_result = await react_agent.process_alert(
                alert_processing_data, "yaml-react-test"
            )
            
            # Verify both processed successfully
            assert regular_result.status == StageStatus.COMPLETED
            assert react_result.status == StageStatus.COMPLETED
            
            # Results should be different (different iteration strategies produce different outputs)
            assert regular_result.result_summary != react_result.result_summary
            
        finally:
            os.unlink(temp_path)


@pytest.mark.integration  
class TestIterationStrategyErrorHandling:
    """Test error scenarios related to iteration strategies."""
    
    @pytest.fixture
    def mock_llm_client(self):
        return Mock()
    
    @pytest.fixture
    def mock_mcp_client(self):
        return Mock()
    
    @pytest.fixture
    def mock_mcp_registry(self):
        return Mock()
    
    def test_invalid_iteration_strategy_in_yaml_fails_gracefully(self):
        """Test that invalid iteration strategy in YAML fails with helpful error."""
        config_yaml = """
agents:
  bad-strategy-agent:
    alert_types: ["test"]
    mcp_servers: ["test-server"]
    iteration_strategy: invalid_strategy  # Invalid

mcp_servers:
  test-server:
    server_id: test-server
    server_type: test
    enabled: true
    connection_params: {}
        """
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(config_yaml)
            temp_path = f.name
        
        try:
            # Should fail during validation
            loader = ConfigurationLoader(temp_path)
            from tarsy.config.exceptions import ConfigurationError
            with pytest.raises(ConfigurationError):
                loader.load_and_validate()
                
        finally:
            os.unlink(temp_path)
    
    def test_configurable_agent_with_invalid_strategy_enum_value(
        self, mock_llm_client, mock_mcp_client, mock_mcp_registry
    ):
        """Test ConfigurableAgent initialization with invalid iteration strategy enum value."""
        # This test verifies that the enum validation works correctly
        with pytest.raises(ValueError):
            # Create config with invalid enum value directly (bypasses Pydantic)
            config = AgentConfigModel(
                alert_types=["test"],
                mcp_servers=["test-server"]
            )
            # Manually set invalid strategy to test error handling
            config.iteration_strategy = "invalid"
            
            ConfigurableAgent(
                agent_name="test-agent",
                config=config,
                llm_client=mock_llm_client,
                mcp_client=mock_mcp_client,
                mcp_registry=mock_mcp_registry
            )
    
    def test_base_agent_factory_method_error_handling(self):
        """Test BaseAgent factory method error handling for unknown strategies."""
        from tarsy.agents.base_agent import BaseAgent
        
        class TestAgent(BaseAgent):
            def mcp_servers(self):
                return ["test"]
            def custom_instructions(self):
                return "test"
        
        with patch('tarsy.agents.base_agent.get_prompt_builder'):
            with pytest.raises(ValueError, match="Unknown iteration strategy"):
                TestAgent(
                    llm_client=Mock(),
                    mcp_client=Mock(),
                    mcp_registry=Mock(),
                    iteration_strategy="completely_invalid"
                )
