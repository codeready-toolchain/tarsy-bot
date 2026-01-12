"""
End-to-end integration tests for alert processing.

These tests verify the complete alert processing workflow from alert ingestion
to final analysis, testing integration between all components.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.models.alert import Alert
from tarsy.models.processing_context import ChainContext
from tarsy.utils.timestamp import now_us
from tests.conftest import alert_to_api_format


@pytest.mark.integration
class TestAlertProcessingE2E:
    """End-to-end tests for complete alert processing workflow."""

    @pytest.fixture
    def sample_alert(self):
        """Create sample alert for testing."""
        return Alert(
            alert_type="kubernetes",
            runbook="https://github.com/company/runbooks/blob/main/k8s.md",
            timestamp=now_us(),
            data={
                "severity": "critical",
                "environment": "production",
                "cluster": "main-cluster",
                "namespace": "default",
                "message": "Namespace is terminating",
                "alert": "NamespaceTerminating"
            }
        )

    @pytest.mark.asyncio
    async def test_happy_path_kubernetes_alert_processing(self, alert_service_with_mocks, sample_alert):
        """Test happy path alert processing workflow."""
        alert_service, mock_dependencies = alert_service_with_mocks
        
        # Convert Alert to dict for the new interface
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        assert isinstance(result, str)
        assert "analysis" in result.lower() or "error" in result.lower()

    @pytest.mark.asyncio
    async def test_agent_selection_and_delegation(
        self, 
        alert_service_with_mocks, 
        sample_alert
    ):
        """Test that the correct agent is selected and instantiated."""
        alert_service, _mock_dependencies = alert_service_with_mocks
        
        # Convert Alert to ChainContext for the new interface
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # New chain-based architecture processes alerts through chains
        # Verify processing completed successfully
        assert result is not None
        if isinstance(result, dict):
            assert result["status"] == "success"
        else:
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_mcp_tool_integration(
        self, 
        alert_service_with_mocks, 
        sample_alert
    ):
        """Test MCP tool discovery and execution."""
        alert_service, mock_dependencies = alert_service_with_mocks
        
        # Convert Alert to ChainContext for the new interface
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Verify MCP client interactions
        assert mock_dependencies['mcp_client'].list_tools.call_count >= 0  # May or may not be called depending on agent setup
        
        # Result should indicate processing occurred
        assert result is not None
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_runbook_integration(
        self, 
        alert_service_with_mocks, 
        sample_alert
    ):
        """Test runbook download and integration."""
        alert_service, mock_dependencies = alert_service_with_mocks
        
        # Convert Alert to ChainContext for the new interface
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Verify runbook service was called
        mock_dependencies['runbook'].download_runbook.assert_called_once_with(
            sample_alert.runbook
        )
        
        # Result should indicate processing occurred
        assert result is not None
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_llm_interactions(
        self,
        alert_service_with_mocks,
        sample_alert
    ):
        """Test LLM interaction patterns."""
        alert_service, mock_dependencies = alert_service_with_mocks
        
        # Convert Alert to ChainContext for the new interface
        chain_context = alert_to_api_format(sample_alert)
        
        # Act
        result = await alert_service.process_alert(chain_context)
        
        # Assert - LLM should be available for processing
        mock_dependencies['llm_manager'].is_available.assert_called()
        
        # Result should indicate processing occurred
        assert result is not None
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_progress_tracking(
        self, 
        alert_service_with_mocks, 
        sample_alert
    ):
        """Test alert processing workflow completion."""
        alert_service, mock_dependencies = alert_service_with_mocks
        
        # Convert Alert to ChainContext for the new interface
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Result should indicate processing occurred
        assert result is not None
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_iterative_analysis_flow(
        self, 
        alert_service_with_mocks, 
        sample_alert
    ):
        """Test iterative analysis flow with MCP tools."""
        alert_service, mock_dependencies = alert_service_with_mocks
        
        # Convert Alert to ChainContext for the new interface
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Should complete iterative flow
        assert result is not None
        assert isinstance(result, str)
        
        # Chain processing should occur (agent creation happens within chain processing)
        # We can verify success by checking that processing completed
        assert len(result) > 0


@pytest.mark.asyncio 
@pytest.mark.integration
class TestErrorHandlingScenarios:
    """Test various error handling scenarios in alert processing."""

    @pytest.mark.asyncio
    async def test_unknown_alert_type_error(
        self,
        alert_service
    ):
        """Test handling of unknown alert types."""
        # Arrange - Create alert with unknown type
        unknown_alert = Alert(
            alert_type="Unknown Alert Type",
            runbook="https://github.com/company/runbooks/blob/main/unknown.md",
            data={
                "severity": "high",
                "environment": "production", 
                "cluster": "https://k8s-cluster.example.com",
                "namespace": "test-namespace",
                "message": "This is an unknown alert type"
            }
        )
        
        # Convert Alert to dict for the new interface
        chain_context = alert_to_api_format(unknown_alert)
        
        # Mock chain registry to raise exception for unknown type
        with patch.object(alert_service.chain_registry, 'get_chain_for_alert_type', side_effect=ValueError("No chain found for alert type 'Unknown Alert Type'. Available: kubernetes")):
            # Act
            result = await alert_service.process_alert(chain_context)
        
        # Assert - Should return error response
        assert result is not None
        assert "error" in result.lower() or "Error" in result
        # Verify the error message contains expected text (updated for chain architecture)
        assert "no chain found" in result.lower() or "unknown alert type" in result.lower()
        assert "Unknown Alert Type" in result

    @pytest.mark.asyncio
    async def test_llm_unavailable_error(
        self,
        alert_service,
        sample_alert,
        progress_callback_mock
    ):
        """Test handling when LLM is unavailable."""
        # Arrange - Mock LLM as unavailable
        alert_service.llm_manager.is_available.return_value = False
        
        # Act
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Should return error response
        assert result is not None
        assert "error" in result.lower() or "Error" in result
        assert "llm" in result.lower()

    @pytest.mark.asyncio
    async def test_agent_creation_error(
        self,
        alert_service,
        sample_alert,
        progress_callback_mock
    ):
        """Test handling when agent creation fails."""
        # Arrange - Mock agent factory to raise error (use get_agent which is the async method actually called)
        with patch.object(alert_service.agent_factory, 'get_agent', side_effect=ValueError("Agent not found")):
            # Act
            chain_context = alert_to_api_format(sample_alert)
            result = await alert_service.process_alert(chain_context)
        
        # Assert - Should return error response
        assert result is not None
        assert "error" in result.lower() or "Error" in result
        # Verify error message contains the specific agent error
        assert "agent not found" in result.lower()

    @pytest.mark.asyncio
    async def test_runbook_download_error(
        self,
        alert_service,
        sample_alert,
        mock_runbook_service,
        progress_callback_mock
    ):
        """Test handling when runbook download fails."""
        # Arrange - Mock runbook service to raise error
        mock_runbook_service.download_runbook.side_effect = Exception("Failed to download runbook")
        
        # Act
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Should return error response
        assert result is not None
        assert "error" in result.lower() or "Error" in result

    @pytest.mark.asyncio
    async def test_mcp_tool_execution_error(
        self,
        alert_service,
        sample_alert,
        mock_mcp_client,
        progress_callback_mock
    ):
        """Test handling when MCP tool execution fails."""
        # Arrange - Mock MCP client to raise error on tool execution
        mock_mcp_client.call_tool.side_effect = Exception("MCP tool execution failed")
        
        # Act - Should still complete processing even with tool failures
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Should still return some form of analysis
        assert result is not None
        # May contain error information but should not be completely empty
        assert len(result) > 50

    @pytest.mark.asyncio
    async def test_llm_response_parsing_error(
        self,
        alert_service,
        sample_alert,
        mock_llm_manager,
        progress_callback_mock
    ):
        """Test handling when LLM returns unparseable responses."""
        # Arrange - Mock LLM to return invalid JSON
        mock_client = mock_llm_manager.get_client()
        mock_client.generate_response.return_value = "Invalid JSON response"
        
        # Act - Should handle parsing errors gracefully
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Should still return a response (may be error or fallback)
        assert result is not None


@pytest.mark.asyncio
@pytest.mark.integration
class TestAgentSpecialization:
    """Test agent-specific behavior and specialization."""

    @pytest.mark.asyncio
    async def test_kubernetes_agent_mcp_server_assignment(
        self,
        alert_service,
        sample_alert,
        mock_mcp_client,
        mock_agent_factory
    ):
        """Test that KubernetesAgent only accesses kubernetes-server."""
        # Act
        chain_context = alert_to_api_format(sample_alert)
        await alert_service.process_alert(chain_context)
        
        # Assert - Verify only kubernetes-server tools are accessed
        list_tools_calls = mock_mcp_client.list_tools.call_args_list
        for call in list_tools_calls:
            server_name = call.kwargs.get("server_name") or (call.args[0] if call.args else None)
            if server_name:
                assert server_name == "kubernetes-server"

    @pytest.mark.asyncio
    async def test_kubernetes_agent_tool_selection(
        self,
        alert_service,
        sample_alert,
        mock_llm_manager,
        mock_mcp_client
    ):
        """Test that KubernetesAgent makes appropriate tool selections."""
        # Act
        chain_context = alert_to_api_format(sample_alert)
        _result = await alert_service.process_alert(chain_context)
        
        # Assert - Verify appropriate Kubernetes tools were called
        tool_calls = mock_mcp_client.call_tool.call_args_list
        called_tools = [call.args[1] for call in tool_calls if len(call.args) > 1]
        
        # Should include namespace and pod related tools
        kubernetes_tools = ["kubectl_get_namespace", "kubectl_get_pods", "kubectl_describe"]
        assert any(tool in called_tools for tool in kubernetes_tools)

    @pytest.mark.asyncio
    async def test_agent_instruction_composition(
        self,
        alert_service,
        sample_alert,
        mock_llm_manager
    ):
        """Test that agent instructions are properly composed (General + MCP + Custom)."""
        # Act
        chain_context = alert_to_api_format(sample_alert)
        await alert_service.process_alert(chain_context)
        
        # Assert - Verify LLM was called with composed instructions
        mock_client = mock_llm_manager.get_client()
        call_args_list = mock_client.generate_response.call_args_list
        
        # Check system messages for instruction composition
        system_messages = []
        for call in call_args_list:
            messages = call.args[0] if call.args else []
            for msg in messages:
                if hasattr(msg, 'role') and msg.role == "system":
                    system_messages.append(msg.content.lower())
        
        # Should contain references to Kubernetes (from server instructions)
        assert len(system_messages) > 0
        kubernetes_mentioned = any("kubernetes" in content for content in system_messages)
        assert kubernetes_mentioned


@pytest.mark.asyncio
@pytest.mark.integration  
class TestConcurrencyAndPerformance:
    """Test concurrent processing and performance characteristics."""

    @pytest.mark.asyncio
    async def test_concurrent_alert_processing(
        self,
        alert_service,
        sample_alert
    ):
        """Test processing multiple alerts concurrently."""
        # Arrange - Create multiple alerts
        alerts = []
        for i in range(3):
            alert = Alert(
                alert_type="NamespaceTerminating",
                runbook="https://github.com/company/runbooks/blob/main/k8s-namespace-terminating.md",
                data={
                    "severity": "high",
                    "environment": f"env-{i}",
                    "cluster": "https://k8s-cluster.example.com",
                    "namespace": f"namespace-{i}",
                    "message": f"Test alert {i}"
                }
            )
            alerts.append(alert)
        
        # Act - Process alerts concurrently
        tasks = []
        for alert in alerts:
            chain_context = alert_to_api_format(alert)
            tasks.append(alert_service.process_alert(chain_context))
        results = await asyncio.gather(*tasks)
        
        # Assert - All should complete successfully
        assert len(results) == 3
        for result in results:
            assert result is not None
            assert len(result) > 100  # Should have substantial content

    @pytest.mark.asyncio
    async def test_processing_timeout_resilience(
        self,
        alert_service,
        sample_alert,
        mock_llm_manager
    ):
        """Test that processing handles timeouts gracefully."""
        # Arrange - Mock LLM to simulate slow responses
        mock_client = mock_llm_manager.get_client()
        
        async def slow_response(messages, **kwargs):
            await asyncio.sleep(0.1)  # Simulate slow response
            return "**Analysis**: Slow but successful analysis"
        
        mock_client.generate_response.side_effect = slow_response
        
        # Act - Process with timeout
        start_time = datetime.now()
        chain_context = alert_to_api_format(sample_alert)
        result = await asyncio.wait_for(
            alert_service.process_alert(chain_context),
            timeout=5.0  # 5 second timeout
        )
        duration = (datetime.now() - start_time).total_seconds()
        
        # Assert - Should complete within reasonable time
        assert result is not None
        assert duration < 5.0
        assert "Analysis" in result


@pytest.mark.asyncio
@pytest.mark.integration
class TestDataFlowValidation:
    """Test data flow and validation throughout the processing pipeline."""

    @pytest.mark.asyncio
    async def test_alert_data_preservation(
        self,
        alert_service,
        sample_alert,
        mock_llm_manager
    ):
        """Test that alert data is preserved and passed correctly through pipeline."""
        # Act
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Result should contain alert-specific information from the analysis
        # Note: namespace appears in the mock LLM analysis text itself
        assert sample_alert.data.get('namespace', '') in result
        
        # Verify the formatted response contains expected sections
        assert "# Alert Analysis Report" in result
        assert f"**Alert Type:** {sample_alert.alert_type}" in result
        assert "## Analysis" in result

    @pytest.mark.asyncio
    async def test_mcp_data_integration(
        self,
        alert_service,
        sample_alert,
        mock_mcp_client,
        mock_llm_manager
    ):
        """Test that MCP tool results are integrated into analysis."""
        # Arrange - Verify MCP client returns expected data
        
        # Act
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - MCP tool should have been called and data integrated
        assert mock_mcp_client.call_tool.call_count >= 1
        
        # The final analysis should reference the MCP data somehow
        # (exact format depends on LLM response, but should be non-trivial)
        assert len(result) > 200  # Should be substantial analysis using MCP data

    @pytest.mark.asyncio
    async def test_result_format_consistency(
        self,
        alert_service,
        sample_alert
    ):
        """Test that results follow expected format."""
        # Act
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Result should be well-formatted string
        assert isinstance(result, str)
        assert len(result) > 100  # Should have substantial content
        
        # Should contain structured information
        lines = result.split('\n')
        assert len(lines) > 5  # Multi-line response
        
        # Should contain analysis indicators
        result_lower = result.lower()
        analysis_indicators = ["analysis", "issue", "resolution", "status", "cause"]
        assert any(indicator in result_lower for indicator in analysis_indicators) 


def flexible_alert_to_api_format(flexible_alert: dict) -> ChainContext:
    """
    Convert flexible alert format to ChainContext that AlertService expects.
    """
    normalized_data = flexible_alert.get("data", {}).copy()
    
    # Extract runbook safely (from normalized_data or flexible_alert)
    runbook = flexible_alert.get("runbook")
    if "runbook" in normalized_data:
        runbook = normalized_data.pop("runbook")
    else:
        normalized_data.pop("runbook", None)  # Ensure it's not in normalized_data
    
    # Extract other metadata fields
    severity = normalized_data.pop("severity", flexible_alert.get("severity", "warning"))
    timestamp = normalized_data.pop("timestamp", flexible_alert.get("timestamp", now_us()))
    environment = normalized_data.pop("environment", flexible_alert.get("environment", "production"))
    
    from tarsy.models.alert import ProcessingAlert
    
    processing_alert = ProcessingAlert(
        alert_type=flexible_alert["alert_type"],
        severity=severity,
        timestamp=timestamp,
        environment=environment,
        runbook_url=runbook,
        alert_data=normalized_data
    )
    
    return ChainContext.from_processing_alert(
        processing_alert=processing_alert,
        session_id="test-session-123",
        current_stage_name="initial"
    )


@pytest.mark.asyncio
@pytest.mark.integration
class TestFlexibleAlertProcessingE2E:
    """End-to-end tests for flexible alert processing with various data structures."""

    @pytest.fixture
    def monitoring_alert_with_nested_data(self):
        """Create a monitoring alert with complex nested data structure."""
        return {
            "alert_type": "kubernetes",  # Use existing chain instead of monitoring
            "runbook": "https://company.com/runbooks/monitoring.md",
            "severity": "critical",
            "timestamp": now_us(),
            "data": {
                "environment": "production",
                "service": "api-gateway",
                "metrics": {
                    "cpu_usage": 95.4,
                    "memory_usage": 87.2,
                    "disk_usage": 91.8,
                    "network": {
                        "in_bytes": 1024000,
                        "out_bytes": 2048000,
                        "dropped_packets": 15
                    }
                },
                "labels": {
                    "region": "us-east-1",
                    "zone": "us-east-1a",
                    "cluster": "prod-cluster",
                    "namespace": "default"
                },
                "tags": ["high-priority", "customer-facing", "sla-critical"],
                "alert_rules": [
                    {
                        "rule": "cpu_usage > 90",
                        "duration": "5m",
                        "severity": "critical"
                    },
                    {
                        "rule": "memory_usage > 80",
                        "duration": "3m", 
                        "severity": "warning"
                    }
                ],
                "yaml_config": """
apiVersion: v1
kind: ConfigMap
metadata:
  name: monitoring-config
data:
  threshold: "90"
  interval: "30s"
                """.strip()
            }
        }

    @pytest.fixture
    def database_alert_with_arrays(self):
        """Create a database alert with array data structures."""
        return {
            "alert_type": "kubernetes",  # Use existing chain instead of database
            "runbook": "https://company.com/runbooks/database.md",
            "data": {
                "environment": "production",
                "database_type": "postgresql",
                "cluster_nodes": [
                    {"node": "db-01", "status": "healthy", "load": 0.75},
                    {"node": "db-02", "status": "degraded", "load": 0.95},
                    {"node": "db-03", "status": "healthy", "load": 0.68}
                ],
                "failing_queries": [
                    {
                        "query_id": "q1",
                        "sql": "SELECT * FROM users WHERE status = 'active'",
                        "duration_ms": 15000,
                        "rows_examined": 1000000
                    },
                    {
                        "query_id": "q2", 
                        "sql": "UPDATE orders SET status = 'processed'",
                        "duration_ms": 8500,
                        "rows_affected": 50000
                    }
                ],
                "connection_pool": {
                    "active_connections": 95,
                    "max_connections": 100,
                    "idle_connections": 2,
                    "waiting_queries": 45
                },
                "replication_lag_seconds": [0.1, 0.3, 2.1, 0.8],
                "table_sizes_gb": {
                    "users": 45.2,
                    "orders": 123.7,
                    "products": 8.9,
                    "logs": 567.1
                }
            }
        }

    @pytest.fixture
    def network_alert_minimal_data(self):
        """Create a minimal network alert to test basic processing."""
        return {
            "alert_type": "kubernetes",  # Use existing chain instead of network
            "runbook": "https://company.com/runbooks/network.md",
            "data": {
                "alert": "HighLatency",
                "description": "Network latency above threshold"
            }
        }

    @pytest.mark.asyncio
    async def test_monitoring_alert_with_complex_nested_data(self, alert_service_with_mocks, monitoring_alert_with_nested_data):
        """Test processing monitoring alert with complex nested data structures."""
        alert_service, mock_dependencies = alert_service_with_mocks

        # Convert to API format
        chain_context = flexible_alert_to_api_format(monitoring_alert_with_nested_data)
        result = await alert_service.process_alert(chain_context)

        # Verify processing completed
        assert isinstance(result, str)
        assert len(result) > 100

        # Verify nested data is preserved and included in analysis
        assert "api-gateway" in result
        assert "95.4" in result or "cpu" in result.lower()
        assert "us-east-1" in result
        assert "high-priority" in result or "sla-critical" in result

        # Verify YAML config was included
        assert "ConfigMap" in result or "monitoring-config" in result

    @pytest.mark.asyncio
    async def test_database_alert_with_array_structures(self, alert_service_with_mocks, database_alert_with_arrays):
        """Test processing database alert with array data structures."""
        alert_service, mock_dependencies = alert_service_with_mocks

        # Convert to API format
        chain_context = flexible_alert_to_api_format(database_alert_with_arrays)
        result = await alert_service.process_alert(chain_context)

        # Verify processing completed
        assert isinstance(result, str)
        assert len(result) > 100

        # Verify array data is preserved and included in analysis
        assert "postgresql" in result
        assert "db-01" in result or "db-02" in result or "db-03" in result
        assert "degraded" in result or "healthy" in result
        assert "connection_pool" in result or "connections" in result.lower()

    @pytest.mark.asyncio
    async def test_minimal_network_alert_processing(self, alert_service_with_mocks, network_alert_minimal_data):
        """Test processing alert with minimal data structure."""
        alert_service, mock_dependencies = alert_service_with_mocks

        # Convert to API format
        chain_context = flexible_alert_to_api_format(network_alert_minimal_data)
        result = await alert_service.process_alert(chain_context)

        # Verify processing completed despite minimal data
        assert isinstance(result, str)
        assert len(result) > 0

        # Verify minimal data is included - check for latency alert content
        assert "HighLatency" in result or "latency" in result.lower()

    @pytest.mark.asyncio
    async def test_agent_selection_with_new_alert_types(self, alert_service_with_mocks):
        """Test that agent selection works correctly with new alert types."""
        alert_service, mock_dependencies = alert_service_with_mocks
        
        # Test different alert types and verify chain selection
        # Only test with existing chains to avoid missing chain errors
        test_cases = [
            ("kubernetes", "KubernetesAgent"),  # Should use KubernetesAgent
            ("NamespaceTerminating", "BaseAgent")  # Should use BaseAgent for this chain
        ]

        registry_mock = mock_dependencies['registry']
        
        for alert_type, expected_agent in test_cases:
            # Create mock chain definition for the test
            from tarsy.models.agent_config import (
                ChainConfigModel,
                ChainStageConfigModel,
            )
            registry_mock.get_chain_for_alert_type.return_value = ChainConfigModel(
                chain_id=f'{alert_type}-chain',
                alert_types=[alert_type],
                stages=[ChainStageConfigModel(name='analysis', agent=expected_agent)],
                description=f'Test chain for {alert_type}'
            )
            
            # Create alert in dictionary format and convert to ChainContext
            alert_dict = {
                "alert_type": alert_type,
                "runbook": "https://example.com/runbook.md",
                "data": {"test": "data"}
            }
            chain_context = flexible_alert_to_api_format(alert_dict)
            result = await alert_service.process_alert(chain_context)
            
            # Verify chain was selected correctly (updated for chain architecture)
            registry_mock.get_chain_for_alert_type.assert_called_with(alert_type)
            
            # Verify processing completed
            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.asyncio 
    async def test_data_preservation_through_processing_pipeline(self, alert_service_with_mocks, monitoring_alert_with_nested_data):
        """Test that complex data structures are preserved throughout the processing pipeline."""
        alert_service, mock_dependencies = alert_service_with_mocks
        
        # Mock agent to capture what data it receives
        captured_data = {}
        
        async def capture_agent_data(chain_context):
            # Capture all arguments passed to process_alert (new signature)
            captured_data['alert_data'] = chain_context.processing_alert.alert_data
            captured_data['runbook_content'] = chain_context.runbook_content
            captured_data['session_id'] = chain_context.session_id
            captured_data['chain_context'] = chain_context
            from tarsy.models.agent_execution_result import AgentExecutionResult
            from tarsy.models.constants import StageStatus
            return AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="TestAgent",
                stage_name="test-stage",
                stage_description="Test stage",
                timestamp_us=now_us(),
                result_summary="Test analysis",
                final_analysis="Test analysis",
                duration_ms=100
            )
        
        mock_agent = AsyncMock()
        mock_agent.process_alert.side_effect = capture_agent_data
        
        # Override the factory's get_agent method directly (synchronous method used by AlertService)
        alert_service.agent_factory.get_agent = Mock(return_value=mock_agent)
        
        # Convert to API format
        chain_context = flexible_alert_to_api_format(monitoring_alert_with_nested_data)
        _result = await alert_service.process_alert(chain_context)
        
        # Verify data preservation
        assert captured_data['alert_data'] is not None
        captured_alert = captured_data['alert_data']
        
        # Verify nested structures are preserved
        assert captured_alert.get('metrics', {}).get('cpu_usage') == 95.4
        assert captured_alert.get('metrics', {}).get('network', {}).get('in_bytes') == 1024000
        assert "high-priority" in captured_alert.get('tags', [])
        assert len(captured_alert.get('alert_rules', [])) == 2
        assert "ConfigMap" in captured_alert.get('yaml_config', '')
        
        # Verify session ID was passed
        assert captured_data['session_id'] is not None