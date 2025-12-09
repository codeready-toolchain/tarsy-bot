"""
Unit tests for response formatting utilities.

Tests the response formatting functions for success responses,
chain responses, and error responses.
"""

import pytest
from types import SimpleNamespace

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
        assert "**Environment:** production" in result
        assert "**Severity:** critical" in result
        assert "**Timestamp:** 1700000000000000" in result
        assert "Pod is in CrashLoopBackOff state" in result
        assert "*Processed by KubernetesAgent in 3 iterations*" in result
    
    def test_format_success_response_with_custom_environment(self):
        """Test formatting response with custom environment."""
        from tarsy.models.processing_context import ChainContext
        
        processing_alert = create_processing_alert_from_alert_factory()
        processing_alert.environment = "staging"
        processing_alert.alert_data["environment"] = "staging"
        
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
        
        assert "**Environment:** staging" in result
    
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
        assert "**Environment:** production" in result
        assert "**Severity:** critical" in result
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
        assert "*Processed through 1 stages*" in result


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
        assert "**Environment:** production" in result
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
    
    @pytest.mark.parametrize(
        "severity,environment",
        [
            ("critical", "production"),
            ("high", "staging"),
            ("medium", "development"),
            ("low", "test"),
            ("info", "production"),
        ],
    )
    def test_format_response_with_various_severities_and_environments(
        self, severity: str, environment: str
    ):
        """Test that responses correctly format various severity and environment combinations."""
        from tarsy.models.processing_context import ChainContext
        
        processing_alert = create_processing_alert_from_alert_factory()
        processing_alert.severity = severity
        processing_alert.environment = environment
        processing_alert.alert_data["severity"] = severity
        processing_alert.alert_data["environment"] = environment
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="session-1"
        )
        
        result = format_success_response(
            chain_context=chain_context,
            agent_name="TestAgent",
            analysis="Test",
            iterations=1
        )
        
        assert f"**Severity:** {severity}" in result
        assert f"**Environment:** {environment}" in result
    
    def test_format_response_with_missing_alert_data_fields(self):
        """Test that responses handle missing alert data fields gracefully."""
        from tarsy.models.processing_context import ChainContext
        from tarsy.models.alert import ProcessingAlert
        
        # Create alert with minimal data
        alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=1700000000000000,
            environment="production",
            runbook_url=None,
            alert_data={}  # Empty alert_data
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
        
        # Should use defaults when fields are missing
        assert "**Severity:** warning" in result
        assert "**Environment:** production" in result

