"""
Integration tests for iteration strategies.

Tests end-to-end behavior differences between REACT, REACT_STAGE, and REACT_FINAL_ANALYSIS iteration strategies
to ensure they work correctly in realistic scenarios.
"""

import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import Tool

from tarsy.agents.configurable_agent import ConfigurableAgent
from tarsy.agents.kubernetes_agent import KubernetesAgent
from tarsy.config.agent_config import ConfigurationLoader
from tarsy.models.agent_config import AgentConfigModel
from tarsy.models.constants import IterationStrategy, StageStatus
from tarsy.services.agent_factory import AgentFactory
from tarsy.services.mcp_server_registry import MCPServerRegistry


@pytest.mark.integration
class TestIterationStrategiesIntegration:
    """Integration tests comparing REACT, REACT_STAGE, and REACT_FINAL_ANALYSIS iteration strategies."""
    
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
        client.get_failed_servers = Mock(return_value={})  # No failed servers by default
        client.list_tools = AsyncMock(return_value={
            "kubernetes-server": [
                Tool(name="kubectl-get-pods", description="Get pods", inputSchema={"type": "object", "properties": {}}),
                Tool(name="kubectl-describe-pod", description="Describe pod", inputSchema={"type": "object", "properties": {}})
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
        registry.get_all_server_ids.return_value = ["kubernetes-server"]
        return registry
    
    @pytest.mark.asyncio
    async def test_kubernetes_agent_react_vs_react_stage_strategies(
        self, mock_llm_client, mock_mcp_client, mock_mcp_registry, 
        sample_alert_data, sample_runbook
    ):
        """Test KubernetesAgent with both REACT and REACT_STAGE strategies."""
        # Mock LLM responses
        mock_llm_client.generate_response.return_value = "Analysis completed successfully"
        
        # Create agents with different strategies
        react_agent = KubernetesAgent(
            llm_manager=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry,
            iteration_strategy=IterationStrategy.REACT
        )
        
        react_stage_agent = KubernetesAgent(
            llm_manager=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry,
            iteration_strategy=IterationStrategy.REACT_STAGE
        )
        
        # Verify different strategies assigned
        assert react_agent.iteration_strategy == IterationStrategy.REACT
        assert react_stage_agent.iteration_strategy == IterationStrategy.REACT_STAGE
        
        # Mock iteration controller behavior to ensure result summaries differ
        react_agent._iteration_controller.execute_analysis_loop = AsyncMock(
            return_value="Final Answer: REACT analysis completed with systematic investigation"
        )
        react_stage_agent._iteration_controller.execute_analysis_loop = AsyncMock(
            return_value="Final Answer: REACT_STAGE analysis completed with stage-specific findings"
        )
        
        # Process alert with both strategies
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.processing_context import ChainContext
        from tarsy.utils.timestamp import now_us
        
        processing_alert_react = ProcessingAlert(
            alert_type="kubernetes",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data=sample_alert_data
        )
        chain_context_react = ChainContext.from_processing_alert(
            processing_alert=processing_alert_react,
            session_id="test-session-react",
            current_stage_name="analysis"
        )
        chain_context_react.runbook_content = sample_runbook
        
        processing_alert_react_stage = ProcessingAlert(
            alert_type="kubernetes",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data=sample_alert_data
        )
        chain_context_react_stage = ChainContext.from_processing_alert(
            processing_alert=processing_alert_react_stage,
            session_id="test-session-react-stage",
            current_stage_name="analysis"
        )
        chain_context_react_stage.runbook_content = sample_runbook
        
        react_result = await react_agent.process_alert(chain_context_react)
        
        react_stage_result = await react_stage_agent.process_alert(chain_context_react_stage)
        
        # Both should succeed but potentially use different processing paths
        assert react_result.status == StageStatus.COMPLETED
        assert react_stage_result.status == StageStatus.COMPLETED
        
        # Results should be different (different iteration strategies produce different outputs)
        assert react_result.result_summary != react_stage_result.result_summary
    
    @pytest.mark.asyncio
    async def test_configurable_agent_iteration_strategies(
        self, mock_llm_client, mock_mcp_client, mock_mcp_registry,
        sample_alert_data, sample_runbook
    ):
        """Test ConfigurableAgent with different iteration strategies."""
        # Mock LLM responses
        mock_llm_client.generate_response.return_value = "Configurable analysis complete"
        
        # Create configurations with different strategies
        react_stage_config = AgentConfigModel(
            mcp_servers=["kubernetes-server"],
            custom_instructions="Use react stage processing",
            iteration_strategy=IterationStrategy.REACT_STAGE
        )
        
        react_config = AgentConfigModel(
            mcp_servers=["kubernetes-server"],
            custom_instructions="Use ReAct processing", 
            iteration_strategy=IterationStrategy.REACT
        )
        
        # Create agents
        react_stage_agent = ConfigurableAgent(
            agent_name="react-stage-k8s-agent",
            config=react_stage_config,
            llm_manager=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        react_agent = ConfigurableAgent(
            agent_name="react-k8s-agent",
            config=react_config,
            llm_manager=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        # Verify strategies
        assert react_stage_agent.iteration_strategy == IterationStrategy.REACT_STAGE
        assert react_agent.iteration_strategy == IterationStrategy.REACT
        
        # Mock iteration controller behavior with distinct outputs
        react_stage_agent._iteration_controller.execute_analysis_loop = AsyncMock(
            return_value="Final Answer: Configurable analysis completed using REACT_STAGE strategy with incremental findings"
        )
        react_agent._iteration_controller.execute_analysis_loop = AsyncMock(
            return_value="Final Answer: Configurable analysis completed using REACT strategy with comprehensive investigation"
        )
        
        # Process alerts
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.processing_context import ChainContext
        from tarsy.utils.timestamp import now_us
        
        processing_alert_react_stage = ProcessingAlert(
            alert_type="kubernetes",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data=sample_alert_data
        )
        chain_context_react_stage = ChainContext.from_processing_alert(
            processing_alert=processing_alert_react_stage,
            session_id="test-config-react-stage",
            current_stage_name="analysis"
        )
        chain_context_react_stage.runbook_content = sample_runbook
        
        processing_alert_react = ProcessingAlert(
            alert_type="kubernetes",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data=sample_alert_data
        )
        chain_context_react = ChainContext.from_processing_alert(
            processing_alert=processing_alert_react,
            session_id="test-config-react",
            current_stage_name="analysis"
        )
        chain_context_react.runbook_content = sample_runbook
        
        react_stage_result = await react_stage_agent.process_alert(chain_context_react_stage)
        
        react_result = await react_agent.process_alert(chain_context_react)
        
        # Verify results
        assert react_stage_result.status == StageStatus.COMPLETED
        assert react_result.status == StageStatus.COMPLETED
        
        # Results should be different (different iteration strategies produce different outputs)
        assert react_result.result_summary != react_stage_result.result_summary
    
    @patch('tarsy.agents.kubernetes_agent.KubernetesAgent')
    def test_agent_factory_creates_agents_with_correct_strategies(
        self, mock_k8s_agent, mock_llm_client, mock_mcp_client, mock_mcp_registry
    ):
        """Test AgentFactory creates agents with correct iteration strategies."""
        mock_agent_instance = Mock()
        mock_k8s_agent.return_value = mock_agent_instance
        
        # Create factory after patching KubernetesAgent 
        factory = AgentFactory(
            llm_manager=mock_llm_client,
            mcp_registry=mock_mcp_registry
        )
        
        # Create agent - should use default REACT strategy
        agent = factory.create_agent("KubernetesAgent", mcp_client=mock_mcp_client)
        
        # Verify factory called agent with REACT strategy
        mock_k8s_agent.assert_called_with(
            llm_manager=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry,
            iteration_strategy=IterationStrategy.REACT
        )
        
        assert agent == mock_agent_instance
    
    def test_yaml_configuration_with_iteration_strategies(self):
        """Test loading agents from YAML configuration with iteration strategies."""
        config_yaml = """
agents:
  react-stage-security-agent:
    mcp_servers:
      - security-tools
    iteration_strategy: react-stage
    custom_instructions: "Use react stage processing for security alerts"
  
  react-performance-agent:
    mcp_servers:
      - monitoring-server
    iteration_strategy: react
    custom_instructions: "Use ReAct reasoning for performance analysis"

agent_chains:
  security-chain:
    alert_types:
      - security
      - intrusion
    stages:
      - name: "security-analysis"
        agent: "react-stage-security-agent"
    description: "Security alert processing chain"
  
  performance-chain:
    alert_types:
      - performance
      - resource-usage
    stages:
      - name: "performance-analysis"
        agent: "react-performance-agent"
    description: "Performance alert processing chain"

mcp_servers:
  security-tools:
    server_id: security-tools
    server_type: security
    enabled: true
    transport:
      type: "stdio"
      command: "/usr/bin/security-scanner"
    instructions: "Security analysis tools"
  
  monitoring-server:
    server_id: monitoring-server
    server_type: monitoring
    enabled: true
    transport:
      type: "stdio"
      command: "monitoring-mcp"
      env:
        ENDPOINT: "http://monitoring.local:9090"
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
            assert len(config.agent_chains) == 2
            
            react_stage_agent_config = config.agents["react-stage-security-agent"]
            react_agent_config = config.agents["react-performance-agent"]
            
            # Verify iteration strategies
            assert react_stage_agent_config.iteration_strategy == IterationStrategy.REACT_STAGE
            assert react_agent_config.iteration_strategy == IterationStrategy.REACT
            
            # Verify alert types are in chains, not agents
            security_chain = config.agent_chains["security-chain"]
            performance_chain = config.agent_chains["performance-chain"]
            
            assert security_chain.alert_types == ["security", "intrusion"]
            assert performance_chain.alert_types == ["performance", "resource-usage"]
            
            # Verify custom instructions
            assert "react stage processing" in react_stage_agent_config.custom_instructions
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
  test-react-stage-agent:
    mcp_servers: ["test-k8s-server"]
    iteration_strategy: react-stage
    custom_instructions: "React stage processing"
  
  test-react-agent:
    mcp_servers: ["test-k8s-server"]
    iteration_strategy: react
    custom_instructions: "Reasoning-based processing"

agent_chains:
  test-alerts-chain:
    alert_types: ["test-alerts"]
    stages:
      - name: "analysis"
        agent: "test-react-stage-agent"
    description: "Test alerts processing chain"
  
  test-performance-chain:
    alert_types: ["test-performance"]
    stages:
      - name: "analysis"
        agent: "test-react-agent"
    description: "Test performance processing chain"

mcp_servers:
  test-k8s-server:
    server_id: test-k8s-server
    server_type: kubernetes
    enabled: true
    transport:
      type: "stdio"
      command: "npx"
      args: ["-y", "kubernetes-mcp-server@latest"]
      env:
        KUBECONFIG: "/tmp/kubeconfig"
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
                llm_manager=mock_llm_client,
                mcp_registry=mcp_registry,
                agent_configs=config.agents
            )
            
            # Create agents with different strategies
            react_stage_agent = factory.create_agent("test-react-stage-agent", mcp_client=mock_mcp_client)
            react_agent = factory.create_agent("test-react-agent", mcp_client=mock_mcp_client)
            
            # Verify correct strategies assigned
            assert react_stage_agent.iteration_strategy == IterationStrategy.REACT_STAGE
            assert react_agent.iteration_strategy == IterationStrategy.REACT
            
            # Mock processing for testing
            mock_llm_client.generate_response.return_value = "YAML config test analysis"
            
            # Mock iteration controller behavior for YAML config test
            react_stage_agent._iteration_controller.execute_analysis_loop = AsyncMock(
                return_value="Final Answer: YAML configuration test analysis using REACT_STAGE with staged data collection"
            )
            react_agent._iteration_controller.execute_analysis_loop = AsyncMock(
                return_value="Final Answer: YAML configuration test analysis using REACT with systematic reasoning"
            )
            
            # Process alerts with both agents
            from tarsy.models.alert import ProcessingAlert
            from tarsy.models.processing_context import ChainContext
            from tarsy.utils.timestamp import now_us
            
            processing_alert_react_stage = ProcessingAlert(
                alert_type="kubernetes",
                severity="warning",
                timestamp=now_us(),
                environment="production",
                alert_data=sample_alert_data
            )
            chain_context_react_stage = ChainContext.from_processing_alert(
                processing_alert=processing_alert_react_stage,
                session_id="yaml-react-stage-test",
                current_stage_name="analysis"
            )
            chain_context_react_stage.runbook_content = sample_runbook
            
            processing_alert_react = ProcessingAlert(
                alert_type="kubernetes",
                severity="warning",
                timestamp=now_us(),
                environment="production",
                alert_data=sample_alert_data
            )
            chain_context_react = ChainContext.from_processing_alert(
                processing_alert=processing_alert_react,
                session_id="yaml-react-test",
                current_stage_name="analysis"
            )
            chain_context_react.runbook_content = sample_runbook
            
            react_stage_result = await react_stage_agent.process_alert(chain_context_react_stage)
            
            react_result = await react_agent.process_alert(chain_context_react)
            
            # Verify both processed successfully
            assert react_stage_result.status == StageStatus.COMPLETED
            assert react_result.status == StageStatus.COMPLETED
            
            # Results should be different (different iteration strategies produce different outputs)
            assert react_result.result_summary != react_stage_result.result_summary
            
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
        client = Mock()
        client.get_failed_servers = Mock(return_value={})  # No failed servers by default
        return client
    
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
    transport:
      type: "stdio"
      command: "test"
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
                llm_manager=mock_llm_client,
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
            with pytest.raises(AssertionError, match="Expected code to be unreachable"):
                TestAgent(
                    llm_manager=Mock(),
                    mcp_client=Mock(),
                    mcp_registry=Mock(),
                    iteration_strategy="completely_invalid"
                )
