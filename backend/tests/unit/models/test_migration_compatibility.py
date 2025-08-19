"""
TEMPORARY Phase 1 migration compatibility tests.

These tests verify that the TEMPORARY conversion methods work correctly during
the migration from old context models to new context models.

⚠️  IMPORTANT: This entire test file will be COMPLETELY REMOVED in Phase 6 cleanup.
All tests in this file are TEMPORARY and exist only to verify migration safety.
"""

import pytest
from unittest.mock import Mock
from typing import Dict, Any

from tarsy.models.alert_processing import AlertProcessingData
from tarsy.models.processing_context import ChainContext, StageContext, AvailableTools
from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.constants import StageStatus
from tarsy.agents.iteration_controllers.base_iteration_controller import IterationContext


class TestAlertProcessingDataCompatibility:
    """TEMPORARY: Test AlertProcessingData conversion to ChainContext."""
    
    def create_test_alert_processing_data(self) -> AlertProcessingData:
        """Create a test AlertProcessingData instance."""
        return AlertProcessingData(
            alert_type="kubernetes",
            alert_data={
                "pod_name": "failing-pod",
                "namespace": "production",
                "severity": "critical",
                "environment": "prod"
            },
            runbook_content="# Emergency Pod Failure Runbook\nInvestigate the pod failure.",
            chain_id="test-chain-123"
        )
    
    def test_to_chain_context_basic_conversion(self):
        """TEMPORARY: Test basic conversion from AlertProcessingData to ChainContext."""
        alert_data = self.create_test_alert_processing_data()
        alert_data.current_stage_name = "analysis"
        
        session_id = "test-session-456"
        chain_context = alert_data.to_chain_context(session_id)
        
        # Verify all data is preserved
        assert isinstance(chain_context, ChainContext)
        assert chain_context.alert_type == "kubernetes"
        assert chain_context.alert_data["pod_name"] == "failing-pod"
        assert chain_context.session_id == session_id  # FIXED: Session ID injected
        assert chain_context.current_stage_name == "analysis"
        assert chain_context.runbook_content == "# Emergency Pod Failure Runbook\nInvestigate the pod failure."
        assert chain_context.chain_id == "test-chain-123"
        assert chain_context.stage_outputs == {}
    
    def test_to_chain_context_with_stage_outputs(self):
        """TEMPORARY: Test conversion with existing stage outputs."""
        alert_data = self.create_test_alert_processing_data()
        alert_data.current_stage_name = "investigation"
        
        # Add stage results
        stage_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="DataCollectionAgent",
            timestamp_us=1234567890,
            result_summary="Collected pod metrics and logs",
            stage_name="data-collection",
            stage_description="Data Collection Stage"
        )
        alert_data.add_stage_result("data-collection", stage_result)
        
        chain_context = alert_data.to_chain_context("test-session")
        
        # Verify stage outputs are preserved
        assert len(chain_context.stage_outputs) == 1
        assert "data-collection" in chain_context.stage_outputs
        assert chain_context.stage_outputs["data-collection"] == stage_result
        
        # Verify previous stages can be retrieved
        previous_stages = chain_context.get_previous_stages_results()
        assert len(previous_stages) == 1
        assert previous_stages[0] == ("data-collection", stage_result)
    
    def test_to_chain_context_handles_none_stage_name(self):
        """TEMPORARY: Test conversion when current_stage_name is None."""
        alert_data = self.create_test_alert_processing_data()
        alert_data.current_stage_name = None
        
        chain_context = alert_data.to_chain_context("test-session")
        
        # Should default to "unknown" when None
        assert chain_context.current_stage_name == "unknown"
    
    def test_to_chain_context_with_none_values(self):
        """TEMPORARY: Test conversion with None values for optional fields."""
        alert_data = AlertProcessingData(
            alert_type="test-type",
            alert_data={"test": "data"},
            runbook_content=None,  # None values
            chain_id=None
        )
        
        chain_context = alert_data.to_chain_context("test-session")
        
        # None values should be preserved
        assert chain_context.runbook_content is None
        assert chain_context.chain_id is None
        assert chain_context.get_runbook_content() == ""  # Helper returns empty string
    
    def test_to_chain_context_data_preservation(self):
        """TEMPORARY: Test that all original data is preserved during conversion."""
        original_alert_data = {
            "complex_nested": {
                "array": [1, 2, 3],
                "object": {"key": "value"}
            },
            "timestamp": 1234567890,
            "environment": "staging"
        }
        
        alert_data = AlertProcessingData(
            alert_type="complex-alert",
            alert_data=original_alert_data
        )
        
        chain_context = alert_data.to_chain_context("test-session")
        
        # Verify complex data structures are preserved
        assert chain_context.alert_data["complex_nested"]["array"] == [1, 2, 3]
        assert chain_context.alert_data["complex_nested"]["object"]["key"] == "value"
        assert chain_context.alert_data["timestamp"] == 1234567890
        
        # Verify get_original_alert_data returns copy
        retrieved_data = chain_context.get_original_alert_data()
        assert retrieved_data == original_alert_data
        assert retrieved_data is not original_alert_data  # Should be a copy


class TestIterationContextCompatibility:
    """TEMPORARY: Test IterationContext conversion to StageContext."""
    
    def create_mock_agent(self) -> Mock:
        """Create a mock BaseAgent for testing."""
        agent = Mock()
        agent.__class__.__name__ = "TestAgent"
        agent.mcp_servers.return_value = ["kubernetes-server", "monitoring-server"]
        return agent
    
    def create_test_iteration_context(self) -> IterationContext:
        """Create a test IterationContext instance."""
        alert_data = AlertProcessingData(
            alert_type="kubernetes",
            alert_data={"pod": "test-pod", "namespace": "default"},
            current_stage_name="analysis"
        )
        
        available_tools = [
            {"server": "k8s", "name": "get_pods", "description": "Get pod information"},
            {"server": "monitoring", "name": "get_metrics", "description": "Get pod metrics"}
        ]
        
        return IterationContext(
            alert_data=alert_data,
            runbook_content="# Test Runbook\nAnalyze the pod issues.",
            available_tools=available_tools,
            session_id="test-session-789",
            agent=self.create_mock_agent()
        )
    
    def test_to_stage_context_basic_conversion(self):
        """TEMPORARY: Test basic conversion from IterationContext to StageContext."""
        iteration_context = self.create_test_iteration_context()
        
        stage_context = iteration_context.to_stage_context()
        
        # Verify StageContext is created
        assert isinstance(stage_context, StageContext)
        assert isinstance(stage_context.chain_context, ChainContext)
        assert isinstance(stage_context.available_tools, AvailableTools)
        
        # Verify data access through properties
        assert stage_context.session_id == "test-session-789"
        assert stage_context.alert_data["pod"] == "test-pod"
        assert stage_context.runbook_content == "# Test Runbook\nAnalyze the pod issues."
        assert stage_context.stage_name == "analysis"
        assert stage_context.agent_name == "TestAgent"
        assert stage_context.mcp_servers == ["kubernetes-server", "monitoring-server"]
    
    def test_to_stage_context_with_alert_processing_data(self):
        """TEMPORARY: Test conversion when alert_data is AlertProcessingData."""
        alert_processing_data = AlertProcessingData(
            alert_type="aws",
            alert_data={"instance_id": "i-123456"},
            current_stage_name="investigation",
            chain_id="chain-456"
        )
        
        iteration_context = IterationContext(
            alert_data=alert_processing_data,
            runbook_content="AWS Investigation Runbook",
            available_tools=[{"server": "aws", "name": "describe_instances", "description": "Describe EC2 instances"}],
            session_id="aws-session",
            agent=self.create_mock_agent()
        )
        
        stage_context = iteration_context.to_stage_context()
        
        # Verify ChainContext is created correctly via AlertProcessingData conversion
        assert stage_context.chain_context.alert_type == "aws"
        assert stage_context.chain_context.chain_id == "chain-456"
        assert stage_context.chain_context.current_stage_name == "investigation"
        assert stage_context.session_id == "aws-session"
    
    def test_to_stage_context_with_raw_dict_alert_data(self):
        """TEMPORARY: Test conversion when alert_data is a raw dictionary."""
        raw_alert_data = {"service": "database", "error": "connection timeout"}
        
        iteration_context = IterationContext(
            alert_data=raw_alert_data,
            runbook_content="Database Troubleshooting",
            available_tools=[{"server": "db", "name": "check_connections", "description": "Check database connections"}],
            session_id="db-session",
            agent=self.create_mock_agent()
        )
        
        stage_context = iteration_context.to_stage_context()
        
        # When raw dict is used, ChainContext should use defaults
        assert stage_context.chain_context.alert_type == "unknown"  # Default for raw dict
        assert stage_context.chain_context.current_stage_name == "unknown"  # Default
        assert stage_context.chain_context.alert_data == raw_alert_data
        assert stage_context.session_id == "db-session"
    
    def test_to_stage_context_tools_conversion(self):
        """TEMPORARY: Test that available_tools are converted to AvailableTools."""
        legacy_tools = [
            {"server": "k8s", "name": "get_pods", "description": "Get pods"},
            {"server": "monitoring", "name": "get_metrics", "description": "Get metrics"},
            {"name": "incomplete_tool"}  # Missing fields to test legacy handling
        ]
        
        iteration_context = IterationContext(
            alert_data={"test": "data"},
            runbook_content="Test",
            available_tools=legacy_tools,
            session_id="test-session",
            agent=self.create_mock_agent()
        )
        
        stage_context = iteration_context.to_stage_context()
        
        # Verify tools are converted to AvailableTools
        assert isinstance(stage_context.available_tools, AvailableTools)
        assert len(stage_context.available_tools.tools) == 3
        
        # Test that prompt format works
        prompt_format = stage_context.available_tools.to_prompt_format()
        assert "k8s.get_pods: Get pods" in prompt_format
        assert "monitoring.get_metrics: Get metrics" in prompt_format


class TestBidirectionalCompatibility:
    """TEMPORARY: Test that conversions work in various scenarios."""
    
    def test_alert_processing_to_chain_to_stage_context(self):
        """TEMPORARY: Test full conversion chain: AlertProcessingData → ChainContext → StageContext."""
        # Create AlertProcessingData
        alert_data = AlertProcessingData(
            alert_type="integration-test",
            alert_data={"test_field": "test_value", "severity": "high"},
            runbook_content="Integration Test Runbook",
            chain_id="integration-chain",
            current_stage_name="integration-stage"
        )
        
        # Add a stage result
        stage_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="IntegrationAgent",
            timestamp_us=1234567890,
            result_summary="Integration test completed"
        )
        alert_data.add_stage_result("previous-stage", stage_result)
        
        # Convert to ChainContext
        chain_context = alert_data.to_chain_context("integration-session")
        
        # Create IterationContext with ChainContext data
        agent = Mock()
        agent.__class__.__name__ = "IntegrationTestAgent"
        agent.mcp_servers.return_value = ["test-server"]
        
        iteration_context = IterationContext(
            alert_data=alert_data,  # Use original AlertProcessingData
            runbook_content=chain_context.get_runbook_content(),
            available_tools=[{"server": "test", "name": "test_tool", "description": "Test tool"}],
            session_id=chain_context.session_id,
            agent=agent
        )
        
        # Convert to StageContext
        stage_context = iteration_context.to_stage_context()
        
        # Verify end-to-end data preservation
        assert stage_context.chain_context.alert_type == "integration-test"
        assert stage_context.alert_data["test_field"] == "test_value"
        assert stage_context.session_id == "integration-session"
        assert stage_context.stage_name == "integration-stage"
        assert stage_context.runbook_content == "Integration Test Runbook"
        
        # Verify stage results are preserved
        assert len(stage_context.previous_stages_results) == 1
        assert stage_context.previous_stages_results[0][0] == "previous-stage"
        assert stage_context.previous_stages_results[0][1] == stage_result
        
        # Verify formatted context works
        formatted_context = stage_context.format_previous_stages_context()
        assert "Integration test completed" in formatted_context
    
    def test_conversion_error_handling(self):
        """TEMPORARY: Test that conversion handles edge cases gracefully."""
        # Test with minimal AlertProcessingData
        minimal_alert = AlertProcessingData(
            alert_type="minimal",
            alert_data={"minimal": True}
        )
        
        chain_context = minimal_alert.to_chain_context("minimal-session")
        
        # Should handle None values gracefully
        assert chain_context.current_stage_name == "unknown"
        assert chain_context.runbook_content is None
        assert chain_context.chain_id is None
        assert chain_context.get_runbook_content() == ""
        
        # Test IterationContext with minimal data (but valid - not empty dict)
        minimal_iteration = IterationContext(
            alert_data={"minimal": "data"},  # Non-empty dict to satisfy validation
            runbook_content="",
            available_tools=[],
            session_id="minimal-session",
            agent=None
        )
        
        stage_context = minimal_iteration.to_stage_context()
        
        # Should create valid StageContext even with minimal data
        assert stage_context.session_id == "minimal-session"
        assert stage_context.alert_data == {"minimal": "data"}
        assert stage_context.runbook_content == ""
        assert len(stage_context.available_tools.tools) == 0
        assert stage_context.available_tools.to_prompt_format() == "No tools available."


class TestDataPreservationGuarantees:
    """TEMPORARY: Test that all data is preserved during conversions."""
    
    def test_no_data_loss_in_conversion(self):
        """TEMPORARY: Verify no data is lost during AlertProcessingData → ChainContext conversion."""
        complex_alert_data = {
            "nested": {
                "deeply": {
                    "nested": {
                        "value": "deep_value",
                        "array": [{"item": 1}, {"item": 2}]
                    }
                }
            },
            "array_of_objects": [
                {"id": 1, "name": "first"},
                {"id": 2, "name": "second", "metadata": {"tags": ["a", "b"]}}
            ],
            "special_chars": "!@#$%^&*()_+-=[]{}|;':\",./<>?",
            "unicode": "こんにちは 🌍 🚀",
            "numbers": [1, 2.5, -3, 0],
            "booleans": {"true_val": True, "false_val": False, "null_val": None}
        }
        
        alert_data = AlertProcessingData(
            alert_type="complex-data-test",
            alert_data=complex_alert_data,
            runbook_content="Complex data test runbook with\nmulti-line\ncontent.",
            chain_id="complex-chain-123"
        )
        
        chain_context = alert_data.to_chain_context("complex-session")
        
        # Verify all complex data is preserved exactly
        assert chain_context.alert_data["nested"]["deeply"]["nested"]["value"] == "deep_value"
        assert len(chain_context.alert_data["nested"]["deeply"]["nested"]["array"]) == 2
        assert chain_context.alert_data["array_of_objects"][1]["metadata"]["tags"] == ["a", "b"]
        assert chain_context.alert_data["special_chars"] == "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        assert chain_context.alert_data["unicode"] == "こんにちは 🌍 🚀"
        assert chain_context.alert_data["numbers"] == [1, 2.5, -3, 0]
        assert chain_context.alert_data["booleans"]["null_val"] is None
        
        # Verify runbook content with newlines is preserved
        assert "multi-line\ncontent" in chain_context.runbook_content
    
    def test_stage_results_preservation(self):
        """TEMPORARY: Verify stage results are preserved with all metadata."""
        alert_data = AlertProcessingData(
            alert_type="stage-results-test",
            alert_data={"test": "stage_results"},
            current_stage_name="current"
        )
        
        # Add multiple stage results with different statuses
        completed_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="CompletedAgent",
            stage_name="completed-stage",
            stage_description="Completed Stage Description",
            timestamp_us=1000000,
            result_summary="Completed successfully with detailed results",
            final_analysis="Final analysis for completed stage",
            duration_ms=5000
        )
        
        failed_result = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="FailedAgent", 
            stage_name="failed-stage",
            stage_description="Failed Stage Description",
            timestamp_us=2000000,
            result_summary="Failed due to timeout",
            error_message="Connection timeout after 30 seconds",
            duration_ms=30000
        )
        
        active_result = AgentExecutionResult(
            status=StageStatus.ACTIVE,
            agent_name="ActiveAgent",
            timestamp_us=3000000,
            result_summary="Currently processing data"
        )
        
        alert_data.add_stage_result("completed", completed_result)
        alert_data.add_stage_result("failed", failed_result)
        alert_data.add_stage_result("active", active_result)
        
        chain_context = alert_data.to_chain_context("stage-results-session")
        
        # Verify all stage results are preserved
        assert len(chain_context.stage_outputs) == 3
        assert chain_context.stage_outputs["completed"] == completed_result
        assert chain_context.stage_outputs["failed"] == failed_result
        assert chain_context.stage_outputs["active"] == active_result
        
        # Verify only completed results appear in previous_stages_results
        previous_stages = chain_context.get_previous_stages_results()
        assert len(previous_stages) == 1  # Only completed stage
        assert previous_stages[0] == ("completed", completed_result)
        
        # Verify all metadata is preserved
        retrieved_completed = chain_context.stage_outputs["completed"]
        assert retrieved_completed.stage_description == "Completed Stage Description"
        assert retrieved_completed.final_analysis == "Final analysis for completed stage"
        assert retrieved_completed.duration_ms == 5000
        
        retrieved_failed = chain_context.stage_outputs["failed"]
        assert retrieved_failed.error_message == "Connection timeout after 30 seconds"
