"""
Unit tests for response formatting utilities.

Tests the response formatting functions for success responses,
chain responses, and error responses.
"""

from types import SimpleNamespace

import pytest

from tarsy.models.alert import ProcessingAlert
from tarsy.services.response_formatter import (
    format_chain_success_response,
    format_error_response,
    format_success_response,
)
from tests.utils import AlertFactory


def create_processing_alert_from_alert_factory(**overrides):
    """Helper to create ProcessingAlert from AlertFactory."""
    alert = AlertFactory.create_kubernetes_alert(**overrides)
    return ProcessingAlert(
        alert_type=alert.alert_type or "kubernetes",
        severity=alert.data.get("severity", "critical"),
        timestamp=alert.timestamp,
        environment=alert.data.get("environment", "production"),
        runbook_url=alert.runbook,
        alert_data=alert.data
    )


@pytest.mark.unit
class TestFormatSuccessResponse:
    """Test single-agent success response formatting."""
    
    def test_format_success_response_with_kubernetes_alert(self):
        """Test formatting success response for Kubernetes alert."""
        from tarsy.models.processing_context import ChainContext
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=create_processing_alert_from_alert_factory(),
            session_id="session-1"
        )
        
        result = format_success_response(
            chain_context=chain_context,
            agent_name="KubernetesAgent",
            analysis="Pod is in CrashLoopBackOff state",
            iterations=3,
            timestamp_us=1700000000000000
        )
        
        # Verify key components are present
        assert "# Alert Analysis Report" in result
        assert "**Alert Type:** kubernetes" in result
        assert "**Processing Agent:** KubernetesAgent" in result
        assert "**Timestamp:** 1700000000000000" in result
        assert "Pod is in CrashLoopBackOff state" in result
        assert "*Processed by KubernetesAgent in 3 iterations*" in result
    
    def test_format_success_response_with_custom_alert_type(self):
        """Test formatting response with custom alert type."""
        from tarsy.models.processing_context import ChainContext
        
        processing_alert = create_processing_alert_from_alert_factory()
        processing_alert.alert_type = "custom-alert"
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="session-1"
        )
        
        result = format_success_response(
            chain_context=chain_context,
            agent_name="TestAgent",
            analysis="Analysis result",
            iterations=1,
            timestamp_us=None
        )
        
        assert "**Alert Type:** custom-alert" in result
    
    def test_format_success_response_without_timestamp(self):
        """Test formatting response without explicit timestamp (uses current time)."""
        from tarsy.models.processing_context import ChainContext
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=create_processing_alert_from_alert_factory(),
            session_id="session-1"
        )
        
        result = format_success_response(
            chain_context=chain_context,
            agent_name="TestAgent",
            analysis="Test analysis",
            iterations=2
        )
        
        # Should have a timestamp even though we didn't provide one
        assert "**Timestamp:**" in result
    
    def test_format_success_response_with_zero_timestamp(self):
        """Test formatting response with timestamp=0 (Unix epoch)."""
        from tarsy.models.processing_context import ChainContext
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=create_processing_alert_from_alert_factory(),
            session_id="session-1"
        )
        
        result = format_success_response(
            chain_context=chain_context,
            agent_name="TestAgent",
            analysis="Test analysis",
            iterations=1,
            timestamp_us=0
        )
        
        # Should preserve the 0 timestamp, not treat it as missing
        assert "**Timestamp:** 0" in result


@pytest.mark.unit
class TestFormatChainSuccessResponse:
    """Test chain success response formatting."""
    
    def test_format_chain_success_response_with_multi_stage(self):
        """Test formatting chain success response with multiple stages."""
        from tarsy.models.processing_context import ChainContext
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=create_processing_alert_from_alert_factory(),
            session_id="session-1"
        )
        
        chain_definition = SimpleNamespace(
            chain_id="kubernetes-investigation",
            stages=[
                SimpleNamespace(name="investigation"),
                SimpleNamespace(name="analysis"),
                SimpleNamespace(name="remediation")
            ]
        )
        
        result = format_chain_success_response(
            chain_context=chain_context,
            chain_definition=chain_definition,
            analysis="Full chain analysis complete",
            timestamp_us=1700000000000000
        )
        
        # Verify key components
        assert "# Alert Analysis Report" in result
        assert "**Alert Type:** kubernetes" in result
        assert "**Processing Chain:** kubernetes-investigation" in result
        assert "**Stages:** 3" in result
        assert "Full chain analysis complete" in result
        assert "*Processed through 3 stages*" in result
    
    def test_format_chain_success_response_single_stage(self):
        """Test formatting chain response with single stage."""
        from tarsy.models.processing_context import ChainContext
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=create_processing_alert_from_alert_factory(),
            session_id="session-1"
        )
        
        chain_definition = SimpleNamespace(
            chain_id="simple-chain",
            stages=[SimpleNamespace(name="single-stage")]
        )
        
        result = format_chain_success_response(
            chain_context=chain_context,
            chain_definition=chain_definition,
            analysis="Single stage analysis",
            timestamp_us=None
        )
        
        assert "**Stages:** 1" in result
        assert "*Processed through 1 stage*" in result
    
    def test_format_chain_success_response_with_zero_timestamp(self):
        """Test formatting chain response with timestamp=0 (Unix epoch)."""
        from tarsy.models.processing_context import ChainContext
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=create_processing_alert_from_alert_factory(),
            session_id="session-1"
        )
        
        chain_definition = SimpleNamespace(
            chain_id="test-chain",
            stages=[SimpleNamespace(name="stage1")]
        )
        
        result = format_chain_success_response(
            chain_context=chain_context,
            chain_definition=chain_definition,
            analysis="Test analysis",
            timestamp_us=0
        )
        
        # Should preserve the 0 timestamp, not treat it as missing
        assert "**Timestamp:** 0" in result


@pytest.mark.unit
class TestFormatErrorResponse:
    """Test error response formatting."""
    
    def test_format_error_response_with_agent_name(self):
        """Test formatting error response with agent name."""
        from tarsy.models.processing_context import ChainContext
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=create_processing_alert_from_alert_factory(),
            session_id="session-1"
        )
        
        result = format_error_response(
            chain_context=chain_context,
            error="Connection to Kubernetes API failed",
            agent_name="KubernetesAgent"
        )
        
        # Verify key components
        assert "# Alert Processing Error" in result
        assert "**Alert Type:** kubernetes" in result
        assert "**Error:** Connection to Kubernetes API failed" in result
        assert "**Failed Agent:** KubernetesAgent" in result
        assert "## Troubleshooting" in result
    
    def test_format_error_response_without_agent_name(self):
        """Test formatting error response without agent name."""
        from tarsy.models.processing_context import ChainContext
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=create_processing_alert_from_alert_factory(),
            session_id="session-1"
        )
        
        result = format_error_response(
            chain_context=chain_context,
            error="Invalid alert type"
        )
        
        # Verify error is present but no agent name
        assert "**Error:** Invalid alert type" in result
        assert "**Failed Agent:**" not in result
    
    def test_format_error_response_includes_troubleshooting(self):
        """Test that error response includes troubleshooting section."""
        from tarsy.models.processing_context import ChainContext
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=create_processing_alert_from_alert_factory(),
            session_id="session-1"
        )
        
        result = format_error_response(
            chain_context=chain_context,
            error="Test error"
        )
        
        # Verify troubleshooting steps are present
        assert "## Troubleshooting" in result
        assert "Check that the alert type is supported" in result
        assert "Verify agent configuration in settings" in result
        assert "Ensure all required services are available" in result
        assert "Review logs for detailed error information" in result


@pytest.mark.unit
class TestResponseFormatting:
    """Test general response formatting behavior."""
    
    def test_format_response_contains_core_metadata(self):
        """Test that responses contain core metadata fields (alert type, timestamp)."""
        from tarsy.models.processing_context import ChainContext
        
        processing_alert = create_processing_alert_from_alert_factory()
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="session-1"
        )
        
        result = format_success_response(
            chain_context=chain_context,
            agent_name="TestAgent",
            analysis="Test analysis",
            iterations=1,
            timestamp_us=1700000000000000
        )
        
        # Verify core metadata is present
        assert "**Alert Type:** kubernetes" in result
        assert "**Timestamp:** 1700000000000000" in result
        assert "Test analysis" in result
    
    def test_format_response_does_not_depend_on_alert_data_structure(self):
        """Test that responses work regardless of alert_data structure."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.processing_context import ChainContext
        
        # Create alert with arbitrary alert_data (no assumed structure)
        alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=1700000000000000,
            environment="production",
            runbook_url=None,
            alert_data={"foo": "bar", "nested": {"data": "value"}}  # Arbitrary structure
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=alert,
            session_id="session-1"
        )
        
        result = format_success_response(
            chain_context=chain_context,
            agent_name="TestAgent",
            analysis="Test",
            iterations=1
        )
        
        # Should format successfully without expecting specific alert_data fields
        assert "# Alert Analysis Report" in result
        assert "**Alert Type:** test" in result

