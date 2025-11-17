"""
Integration tests for edge cases and stress scenarios.

This module tests the system's behavior under various edge conditions,
including malformed data, resource constraints, and boundary conditions.
"""

import asyncio
from datetime import datetime

import pytest

from tarsy.models.alert import Alert
from tarsy.utils.timestamp import now_us
from tests.conftest import alert_to_api_format


@pytest.mark.integration
class TestEdgeCases:
    """Test edge cases that could cause system failures."""

    @pytest.mark.asyncio
    async def test_very_long_alert_message(self, alert_service_with_mocks):
        """Test processing alerts with very long messages."""
        alert_service, _ = alert_service_with_mocks
        
        # Create alert with very long message (>5000 characters)
        very_long_message = "A" * 5000 + " This is a test alert with an extremely long message that could potentially cause issues."
        
        long_alert = Alert(
            alert_type="kubernetes",
            runbook="https://example.com/runbook",
            timestamp=now_us(),
            data={
                "severity": "critical",
                "environment": "production",
                "cluster": "test-cluster",
                "namespace": "test-namespace",
                "message": very_long_message
            }
        )
        
        # Convert to API format for processing
        chain_context = alert_to_api_format(long_alert)
        
        result = await alert_service.process_alert(chain_context)
        
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_special_characters_in_alert_data(
        self,
        alert_service_with_mocks
    ):
        """Test processing alerts with special characters and unicode."""
        alert_service, _ = alert_service_with_mocks
        
        # Create alert with special characters including unicode, newlines, quotes
        special_message = """Alert with special chars: ñáéíóú 中文 🚨 
        "quoted text" with 'apostrophes' and \n newlines"""
        
        special_alert = Alert(
            alert_type="kubernetes",
            runbook="https://example.com/runbook",
            timestamp=now_us(),
            data={
                "severity": "warning",
                "environment": "production",
                "cluster": "test-cluster", 
                "namespace": "test-namespace",
                "message": special_message
            }
        )
        
        # Convert to ChainContext for new interface  
        chain_context = alert_to_api_format(special_alert)
        
        result = await alert_service.process_alert(chain_context)
        
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_empty_optional_fields(self, alert_service_with_mocks):
        """Test processing alerts with minimal data."""
        alert_service, _ = alert_service_with_mocks
        
        # Create minimal alert
        minimal_alert = Alert(
            alert_type="kubernetes",
            runbook="https://example.com/runbook",
            data={}  # Empty data
        )
        
        # Convert to ChainContext for new interface
        chain_context = alert_to_api_format(minimal_alert)
        
        result = await alert_service.process_alert(chain_context)
        
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_very_old_timestamp(self, alert_service_with_mocks):
        """Test processing alerts with very old timestamps."""
        alert_service, _ = alert_service_with_mocks
        
        # Create alert with old timestamp (Unix microseconds from 2020)
        old_timestamp = 1577836800000000  # 2020-01-01 00:00:00 UTC in microseconds
        
        old_alert = Alert(
            alert_type="kubernetes",
            runbook="https://example.com/runbook",
            timestamp=old_timestamp,
            data={
                "severity": "medium",
                "environment": "production",
                "cluster": "test-cluster",
                "namespace": "test-namespace",
                "message": "Old alert"
            }
        )
        
        # Convert to ChainContext for new interface
        chain_context = alert_to_api_format(old_alert)
        
        result = await alert_service.process_alert(chain_context)
        
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_malformed_runbook_url(self, alert_service_with_mocks):
        """Test processing alerts with malformed runbook URLs."""
        alert_service, _ = alert_service_with_mocks
        
        # Create alert with malformed runbook URL
        malformed_alert = Alert(
            alert_type="kubernetes",
            runbook="not-a-valid-url-format",
            timestamp=now_us(),
            data={
                "severity": "high",
                "environment": "production",
                "cluster": "test-cluster",
                "namespace": "test-namespace",
                "message": "Alert with malformed runbook URL"
            }
        )
        
        # Convert to ChainContext for new interface
        chain_context = alert_to_api_format(malformed_alert)
        
        result = await alert_service.process_alert(chain_context)
        
        # Should handle the malformed URL gracefully (likely return an error response)
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_extremely_rapid_successive_processing(
        self,
        alert_service,
        sample_alert
    ):
        """Test rapid successive processing of the same alert."""
        # Arrange - Create multiple identical processing requests
        num_requests = 5
        
        # Act - Fire off multiple requests simultaneously
        tasks = []
        for _ in range(num_requests):
            chain_context = alert_to_api_format(sample_alert)
            tasks.append(alert_service.process_alert(chain_context))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Assert - All should complete (may have varying results)
        assert len(results) == num_requests
        successful_results = [r for r in results if isinstance(r, str) and len(r) > 50]
        assert len(successful_results) >= num_requests // 2  # At least half should succeed

    @pytest.mark.asyncio
    async def test_processing_with_none_callback(
        self,
        alert_service,
        sample_alert
    ):
        """Test processing with None progress callback."""
        # Act - Process with no callback
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Should work without callback
        assert result is not None
        assert len(result) > 100


@pytest.mark.asyncio
@pytest.mark.integration
class TestStressScenarios:
    """Test system behavior under stress."""

    @pytest.mark.asyncio
    async def test_high_concurrency_different_alerts(
        self,
        alert_service
    ):
        """Test high concurrency with different alert types."""
        # Arrange - Create many different alerts
        alerts = []
        for i in range(10):
            alert = Alert(
                alert_type="NamespaceTerminating",
                runbook="https://github.com/company/runbooks/blob/main/k8s-namespace-terminating.md",
                data={
                    "severity": ["low", "medium", "high"][i % 3],
                    "environment": f"env-{i}",
                    "cluster": f"https://cluster-{i}.example.com",
                    "namespace": f"namespace-{i}",
                    "pod": f"pod-{i}",
                    "message": f"Stress test alert {i}",
                    "context": f"Stress test context for alert {i}"
                }
            )
            alerts.append(alert)
        
        # Act - Process all concurrently
        start_time = datetime.now()
        tasks = []
        for alert in alerts:
            chain_context = alert_to_api_format(alert)
            tasks.append(alert_service.process_alert(chain_context))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        duration = (datetime.now() - start_time).total_seconds()
        
        # Assert - Should handle high concurrency
        assert len(results) == 10
        successful_results = [r for r in results if isinstance(r, str) and len(r) > 50]
        assert len(successful_results) >= 8  # At least 80% success rate
        assert duration < 30  # Should complete within reasonable time

    @pytest.mark.asyncio
    async def test_rapid_fire_same_alert(
        self,
        alert_service,
        sample_alert
    ):
        """Test rapid-fire processing of the same alert."""
        # Arrange
        num_iterations = 15
        
        # Act - Process the same alert multiple times rapidly
        start_time = datetime.now()
        tasks = []
        
        for i in range(num_iterations):
            # Small delay between starts to simulate rapid but not simultaneous requests
            if i > 0:
                await asyncio.sleep(0.01)
            chain_context = alert_to_api_format(sample_alert)
            tasks.append(alert_service.process_alert(chain_context))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        duration = (datetime.now() - start_time).total_seconds()
        
        # Assert
        assert len(results) == num_iterations
        successful_results = [r for r in results if isinstance(r, str) and len(r) > 50]
        assert len(successful_results) >= num_iterations * 0.7  # At least 70% success rate
        assert duration < 60  # Should complete within 1 minute

    @pytest.mark.asyncio
    async def test_resource_exhaustion_simulation(
        self,
        alert_service,
        sample_alert,
        mock_llm_manager,
        mock_mcp_client
    ):
        """Test basic error handling when LLM fails."""
        # Arrange - Simple LLM failure simulation
        mock_llm_manager.get_client().generate_response.side_effect = Exception("Service unavailable")
        
        # Act - Try to process an alert
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Should handle the failure gracefully
        assert result is not None
        assert isinstance(result, str)
        assert "error" in result.lower() or "fail" in result.lower()

    @pytest.mark.asyncio
    async def test_memory_intensive_processing(
        self,
        alert_service,
        mock_llm_manager
    ):
        """Test processing with large data content."""
        # Arrange - Create alert with large context
        large_context = "Large context data: " + "x" * 10000  # 10KB context (reasonable size)
        
        large_alert = Alert(
            alert_type="NamespaceTerminating",
            runbook="https://github.com/company/runbooks/blob/main/k8s-namespace-terminating.md",
            data={
                "severity": "high",
                "environment": "production",
                "cluster": "https://k8s-cluster.example.com",
                "namespace": "memory-test-namespace",
                "message": "Memory intensive test alert",
                "context": large_context
            }
        )
        
        # Simple mock response - just ensure system can handle large input
        mock_llm_manager.get_client().generate_response.return_value = "**Analysis**: Successfully processed large alert data"
        
        # Act - Process the alert with large data
        chain_context = alert_to_api_format(large_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Should handle large data gracefully
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 50  # Should have some meaningful content


@pytest.mark.asyncio
@pytest.mark.integration
class TestBoundaryConditions:
    """Test boundary conditions and limits."""

    @pytest.mark.asyncio
    async def test_maximum_iterations_reached(
        self,
        alert_service,
        sample_alert,
        mock_llm_manager,
        mock_mcp_client,
        mock_settings
    ):
        """Test behavior when maximum iterations are reached."""
        # Arrange - Set low iteration limit and mock LLM to always continue
        mock_settings.max_llm_mcp_iterations = 2  # Very low limit
        
        iteration_count = 0
        async def always_continue_response(messages, **kwargs):
            nonlocal iteration_count
            iteration_count += 1
            
            user_content = ""
            for msg in messages:
                if hasattr(msg, 'content') and msg.content:
                    user_content += msg.content.lower()
            
            # Always return continue=true to test iteration limits
            if "continue" in user_content and iteration_count < 10:
                return '''```json
{"continue": true, "tools": [{"server": "kubernetes-server", "tool": "kubectl_get_pods",
  "parameters": {"namespace": "test"}, "reason": "Continue iteration"}]}
```'''
            
            return "**Analysis**: Max iterations test completed"
        
        mock_llm_manager.get_client().generate_response.side_effect = always_continue_response
        
        # Act
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Should stop at max iterations
        assert result is not None
        assert "Analysis" in result

    @pytest.mark.asyncio
    async def test_empty_mcp_tool_response(
        self,
        alert_service,
        sample_alert,
        mock_mcp_client
    ):
        """Test handling of empty MCP tool responses."""
        # Arrange - Mock MCP client to return empty responses
        mock_mcp_client.call_tool.return_value = {"status": "success", "output": ""}
        
        # Act
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Should handle empty responses gracefully
        assert result is not None
        assert len(result) > 50

    @pytest.mark.asyncio
    async def test_malformed_json_from_llm(
        self,
        alert_service,
        sample_alert,
        mock_llm_manager
    ):
        """Test handling of malformed JSON responses from LLM."""
        # Arrange - Mock LLM to return malformed JSON
        responses = [
            "This is not JSON at all",
            "```json\n{invalid: json}\n```",
            "```json\n[{\"missing_quotes: true}]\n```",
            "**Final Analysis**: Fallback after JSON errors"
        ]
        
        response_iter = iter(responses)
        async def malformed_json_response(messages, **kwargs):
            return next(response_iter, "Default response")
        
        mock_llm_manager.get_client().generate_response.side_effect = malformed_json_response
        
        # Act
        chain_context = alert_to_api_format(sample_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Should handle malformed JSON gracefully
        assert result is not None
        # Should eventually get to fallback analysis
        assert "Analysis" in result or len(result) > 50

    @pytest.mark.asyncio
    async def test_unicode_and_encoding_edge_cases(
        self,
        alert_service
    ):
        """Test handling of various Unicode and encoding scenarios."""
        # Arrange - Create alert with diverse Unicode content
        unicode_alert = Alert(
            alert_type="NamespaceTerminating",
            runbook="https://github.com/company/runbooks/blob/main/k8s-namespace-terminating.md",
            data={
                "severity": "high",
                "environment": "production",
                "cluster": "https://k8s-cluster.example.com",
                "namespace": "测试-namespace-тест",
                "pod": "pod-🚀-名前-имя",
                "message": "Unicode test: 你好世界 Здравствуй мир مرحبا بالعالم 🌍🚀💻",
                "context": "Mixed scripts: English 中文 Русский العربية 日本語 한国語"
            }
        )
        
        # Act
        chain_context = alert_to_api_format(unicode_alert)
        result = await alert_service.process_alert(chain_context)
        
        # Assert - Should handle Unicode correctly
        assert result is not None
        assert isinstance(result, str)
        # Should preserve some Unicode content
        assert "测试" in result or "namespace" in result

    @pytest.mark.asyncio
    async def test_very_slow_external_dependencies(
        self,
        alert_service,
        sample_alert,
        mock_llm_manager,
        mock_mcp_client,
        mock_runbook_service
    ):
        """Test handling of very slow external dependencies."""
        # Arrange - Mock all external services to be slow
        async def slow_llm_response(messages, **kwargs):
            await asyncio.sleep(0.2)  # 200ms delay
            return "**Analysis**: Slow LLM response"
        
        async def slow_mcp_call(server_name, tool_name, parameters):
            await asyncio.sleep(0.1)  # 100ms delay
            return {"status": "success", "output": "slow response"}
        
        async def slow_runbook_download(url):
            await asyncio.sleep(0.15)  # 150ms delay
            return "# Slow Runbook\nThis took a while to download."
        
        mock_llm_manager.get_client().generate_response.side_effect = slow_llm_response
        mock_mcp_client.call_tool.side_effect = slow_mcp_call
        mock_runbook_service.download_runbook.side_effect = slow_runbook_download
        
        # Act - Process with timeout
        start_time = datetime.now()
        chain_context = alert_to_api_format(sample_alert)
        result = await asyncio.wait_for(
            alert_service.process_alert(chain_context),
            timeout=10.0  # 10 second timeout
        )
        duration = (datetime.now() - start_time).total_seconds()
        
        # Assert - Should complete despite slow dependencies
        assert result is not None
        assert "Analysis" in result or "Slow" in result
        assert duration < 10.0  # Should complete within timeout 