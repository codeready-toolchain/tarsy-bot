"""
Phase 2: Tests using the context models in real scenarios.

This module demonstrates how the ChainContext and StageContext models
work in actual test scenarios, alongside the existing models.
"""


from tarsy.agents.prompts.builders import PromptBuilder
from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.constants import StageStatus
from tarsy.models.processing_context import ChainContext, StageContext, ToolWithServer
from tests.unit.models.test_context_factories import (
    AvailableToolsFactory,
    ChainContextFactory,
    MockAgentFactory,
    StageContextFactory,
    create_test_chain_context,
    create_test_stage_context,
)


class TestNewChainContextUsage:
    """Test ChainContext in realistic scenarios."""
    
    def test_basic_chain_context_creation(self):
        """Test creating and using a basic ChainContext."""
        context = create_test_chain_context()
        
        # Verify basic properties
        assert context.alert_type == "kubernetes"
        assert context.session_id == "test-session-123"
        assert context.current_stage_name == "analysis"
        assert isinstance(context.alert_data, dict)
        assert context.alert_data["pod"] == "test-pod"
        
        # Test methods
        original_data = context.get_original_alert_data()
        assert original_data == context.alert_data
        assert original_data is not context.alert_data  # Should be a copy
        
        assert context.get_runbook_content() == ""  # No runbook set
        assert context.get_previous_stages_results() == []  # No previous stages
    
    def test_chain_context_with_runbook(self):
        """Test ChainContext with runbook content."""
        context = ChainContextFactory.create_with_runbook()
        
        assert context.alert_type == "kubernetes"
        assert "failing-pod" in context.alert_data["pod"]
        assert context.alert_data["severity"] == "critical"
        assert context.chain_id == "k8s-troubleshooting-chain"
        
        runbook = context.get_runbook_content()
        assert "# Pod Failure Runbook" in runbook
        assert "Investigation Steps" in runbook
    
    def test_chain_context_with_stage_progression(self):
        """Test ChainContext as it progresses through stages."""
        context = ChainContextFactory.create_with_stage_results()
        
        # Verify initial state
        assert context.current_stage_name == "remediation"
        assert len(context.stage_outputs) == 2
        
        # Verify previous stages are returned in order
        previous_stages = context.get_previous_stages_results()
        assert len(previous_stages) == 2
        
        # Check execution order preservation
        stage_names = [stage_name for stage_name, _ in previous_stages]
        assert stage_names == ["data-collection", "analysis"]
        
        # Verify stage data
        data_collection_name, data_collection_result = previous_stages[0]
        assert data_collection_name == "data-collection"
        assert data_collection_result.agent_name == "DataCollectionAgent"
        assert "instance metrics" in data_collection_result.result_summary
        
        analysis_name, analysis_result = previous_stages[1]
        assert analysis_name == "analysis"
        assert analysis_result.agent_name == "AnalysisAgent"
        assert "memory leak" in analysis_result.result_summary
    
    def test_complex_alert_data_handling(self):
        """Test ChainContext with complex, nested alert data."""
        context = ChainContextFactory.create_complex_alert_data()
        
        assert context.alert_type == "KubernetesPodCrashLooping"
        
        # Test accessing nested data
        alert_data = context.get_original_alert_data()
        assert alert_data["pod_info"]["name"] == "api-server-7d4b9c8f6-xyz123"
        assert alert_data["pod_info"]["restart_count"] == 15
        assert alert_data["cluster_info"]["region"] == "us-east-1"
        assert alert_data["annotations"]["monitoring.io/alert-level"] == "critical"
        
        # Verify complex data structure preservation
        assert isinstance(alert_data["pod_info"]["labels"], dict)
        assert alert_data["pod_info"]["labels"]["app"] == "api-server"
        assert isinstance(alert_data["pod_info"]["last_state"]["terminated"], dict)
    
    def test_adding_new_stage_results(self):
        """Test adding stage results to ChainContext."""
        context = create_test_chain_context()
        
        # Initially no stage results
        assert len(context.stage_outputs) == 0
        assert context.get_previous_stages_results() == []
        
        # Add first stage result
        first_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="FirstAgent",
            timestamp_us=1234567890,
            result_summary="First stage completed",
            stage_name="first-stage"
        )
        context.add_stage_result("first-stage", first_result)
        
        # Verify first stage
        assert len(context.stage_outputs) == 1
        previous = context.get_previous_stages_results()
        assert len(previous) == 1
        assert previous[0] == ("first-stage", first_result)
        
        # Add second stage result
        second_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="SecondAgent",
            timestamp_us=1234567891,
            result_summary="Second stage completed",
            stage_name="second-stage"
        )
        context.add_stage_result("second-stage", second_result)
        
        # Verify both stages in order
        previous = context.get_previous_stages_results()
        assert len(previous) == 2
        assert previous[0] == ("first-stage", first_result)
        assert previous[1] == ("second-stage", second_result)


class TestNewStageContextUsage:
    """Test StageContext in realistic scenarios."""
    
    def test_basic_stage_context_creation(self):
        """Test creating and using a basic StageContext."""
        context = create_test_stage_context()
        
        # Verify property access works
        assert context.alert_data["pod"] == "test-pod"
        assert context.session_id == "test-session-123"
        assert context.stage_name == "analysis"
        assert context.agent_name == "KubernetesAgent"
        assert context.runbook_content == ""
        assert "kubernetes-server" in context.mcp_servers
        
        # Test methods
        assert not context.has_previous_stages()
        assert context.format_previous_stages_context() == "No previous stage context available."
    
    def test_stage_context_with_previous_stages(self):
        """Test StageContext with previous completed stages."""
        context = StageContextFactory.create_with_previous_stages()
        
        # Verify it has previous stages
        assert context.has_previous_stages()
        
        # Check previous stages data
        previous = context.previous_stages_results
        assert len(previous) == 2
        
        # Test formatted context generation
        formatted = context.format_previous_stages_context()
        assert "## Results from 'Data Collection' stage:" in formatted
        assert "Collected instance metrics" in formatted
        assert "## Results from 'Root Cause Analysis' stage:" in formatted
        assert "memory leak" in formatted
    
    def test_kubernetes_troubleshooting_scenario(self):
        """Test StageContext in a complete Kubernetes troubleshooting scenario."""
        context = StageContextFactory.create_kubernetes_scenario()
        
        # Verify Kubernetes-specific setup
        assert context.alert_data["pod"] == "failing-pod"
        assert context.alert_data["severity"] == "critical"
        assert context.agent_name == "KubernetesAgent"
        assert "kubernetes-server" in context.mcp_servers
        
        # Verify runbook content
        runbook = context.runbook_content
        assert "# Pod Failure Runbook" in runbook
        assert "Check pod logs" in runbook
        
        # Verify tools are available
        builder = PromptBuilder()
        tools_format = builder._format_available_actions(context.available_tools.tools)
        assert "kubernetes-server.get_pods" in tools_format
        assert "kubernetes-server.get_pod_logs" in tools_format
        assert "kubernetes-server.describe_pod" in tools_format
    
    def test_complex_scenario_with_mixed_tools(self):
        """Test StageContext with complex alert and mixed tools."""
        context = StageContextFactory.create_complex_scenario()
        
        # Verify complex alert data access
        assert context.alert_data["pod_info"]["restart_count"] == 15
        assert context.alert_data["cluster_info"]["name"] == "prod-cluster-east"
        
        # Verify mixed tools availability
        tools = context.available_tools
        assert len(tools.tools) >= 6  # K8s + AWS + monitoring tools
        
        builder = PromptBuilder()
        tools_format = builder._format_available_actions(tools.tools)
        assert "kubernetes-server" in tools_format
        assert "aws-server" in tools_format
        assert "monitoring-server" in tools_format
    
    def test_property_access_performance(self):
        """Test that property access doesn't cause performance issues."""
        context = create_test_stage_context()
        
        # Access properties multiple times (should be fast)
        for _ in range(100):
            _ = context.alert_data
            _ = context.session_id
            _ = context.stage_name
            _ = context.agent_name
            _ = context.mcp_servers
        
        # Should complete quickly without issues
        assert context.session_id == "test-session-123"


class TestAvailableToolsUsage:
    """Test AvailableTools in realistic scenarios."""
    
    def test_kubernetes_tools_usage(self):
        """Test AvailableTools with Kubernetes tools."""
        tools = AvailableToolsFactory.create_kubernetes_tools()
        
        assert len(tools.tools) == 3
        assert all(isinstance(tool, ToolWithServer) for tool in tools.tools)
        
        # Test tool details
        get_pods_tool = next(tool for tool in tools.tools if tool.tool.name == "get_pods")
        assert get_pods_tool.server == "kubernetes-server"
        assert "pod information" in get_pods_tool.tool.description
        # Check that tool has parameters in inputSchema
        input_schema = get_pods_tool.tool.inputSchema
        assert input_schema is not None
        assert 'properties' in input_schema
        assert len(input_schema['properties']) == 2
        
        # Test prompt formatting
        builder = PromptBuilder()
        prompt = builder._format_available_actions(tools.tools)
        assert "**kubernetes-server.get_pods**: Get pod information and status" in prompt
        assert "**kubernetes-server.get_pod_logs**: Get logs from a specific pod" in prompt
    
    def test_mixed_tools_scenario(self):
        """Test AvailableTools with tools from multiple servers."""
        tools = AvailableToolsFactory.create_mixed_tools()
        
        # Should have tools from multiple servers
        servers = {tool.server for tool in tools.tools}
        assert "kubernetes-server" in servers
        assert "aws-server" in servers
        assert "monitoring-server" in servers
        
        # Test comprehensive prompt format
        builder = PromptBuilder()
        prompt = builder._format_available_actions(tools.tools)
        assert "kubernetes-server.get_pods" in prompt
        assert "aws-server.describe_instances" in prompt
        assert "monitoring-server.query_prometheus" in prompt
    




    



class TestNewModelsInRealScenarios:
    """Test new models in scenarios that simulate real usage."""
    
    def test_multi_stage_processing_flow(self):
        """Test simulating a multi-stage processing flow with new models."""
        # Stage 1: Data Collection
        context = ChainContextFactory.create_with_runbook()
        
        # Simulate data collection stage completion
        data_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="DataCollectionAgent",
            stage_name="data-collection",
            stage_description="Data Collection",
            timestamp_us=1000000,
            result_summary="Collected pod logs, metrics, and cluster state"
        )
        context.add_stage_result("data-collection", data_result)
        
        # Stage 2: Analysis
        context.current_stage_name = "analysis"
        analysis_stage = StageContext(
            chain_context=context,
            available_tools=AvailableToolsFactory.create_kubernetes_tools(),
            agent=MockAgentFactory.create_kubernetes_agent()
        )
        
        # Verify analysis stage has access to previous data
        assert analysis_stage.has_previous_stages()
        previous_context = analysis_stage.format_previous_stages_context()
        assert "Collected pod logs" in previous_context
        
        # Simulate analysis completion
        analysis_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="AnalysisAgent",
            stage_name="analysis",
            timestamp_us=2000000,
            result_summary="Identified root cause: resource limits exceeded"
        )
        context.add_stage_result("analysis", analysis_result)
        
        # Stage 3: Remediation
        context.current_stage_name = "remediation"
        remediation_stage = StageContext(
            chain_context=context,
            available_tools=AvailableToolsFactory.create_kubernetes_tools(),
            agent=MockAgentFactory.create_kubernetes_agent()
        )
        
        # Verify remediation stage has access to all previous stages
        previous = remediation_stage.previous_stages_results
        assert len(previous) == 2
        assert previous[0][0] == "data-collection"
        assert previous[1][0] == "analysis"
        
        # Verify formatted context includes both stages
        formatted = remediation_stage.format_previous_stages_context()
        assert "Collected pod logs" in formatted
        assert "resource limits exceeded" in formatted
    
    def test_error_handling_scenario(self):
        """Test new models in error handling scenarios."""
        context = create_test_chain_context()
        
        # Simulate a failed stage
        failed_result = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="FailedAgent",
            stage_name="failed-stage",
            timestamp_us=1000000,
            result_summary="Stage failed due to timeout",
            error_message="Connection timeout after 30 seconds"
        )
        context.add_stage_result("failed-stage", failed_result)
        
        # Failed stages should not appear in previous_stages_results (only completed)
        previous = context.get_previous_stages_results()
        assert len(previous) == 0  # Failed stage filtered out
        
        # But should still be in stage_outputs
        assert len(context.stage_outputs) == 1
        assert "failed-stage" in context.stage_outputs
        assert context.stage_outputs["failed-stage"].error_message == "Connection timeout after 30 seconds"
    
    def test_performance_with_large_data(self):
        """Test new models handle large data efficiently."""
        # Create large alert data
        large_data = {
            "metadata": {"timestamp": "2024-01-15T10:30:00Z"},
            "large_list": [f"item_{i}" for i in range(1000)],
            "nested_data": {
                f"key_{i}": {
                    "sub_key": f"value_{i}",
                    "numbers": list(range(10))
                } for i in range(100)
            }
        }
        
        context = ChainContext(
            alert_type="large-data-test",
            alert_data=large_data,
            session_id="large-data-session",
            current_stage_name="processing"
        )
        
        # Should handle large data efficiently
        assert len(context.alert_data["large_list"]) == 1000
        assert len(context.alert_data["nested_data"]) == 100
        
        # Property access should still be fast
        original = context.get_original_alert_data()
        assert original == large_data
        assert original is not large_data  # Should be a copy
