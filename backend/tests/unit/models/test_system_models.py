"""Unit tests for system models."""

import pytest
from pydantic import ValidationError

from tarsy.models.system_models import SystemWarning


@pytest.mark.unit
class TestSystemWarning:
    """Test cases for SystemWarning model."""

    def test_system_warning_creation(self) -> None:
        """Test creating a valid SystemWarning."""
        warning = SystemWarning(
            warning_id="mcp_initialization_1706616000000000",
            category="mcp_initialization",
            message="MCP Server 'kubernetes-server' failed to initialize",
            details="Connection timeout after 30 seconds",
            timestamp=1706616000000000,
        )

        assert warning.warning_id == "mcp_initialization_1706616000000000"
        assert warning.category == "mcp_initialization"
        assert warning.message == "MCP Server 'kubernetes-server' failed to initialize"
        assert warning.details == "Connection timeout after 30 seconds"
        assert warning.timestamp == 1706616000000000

    def test_system_warning_without_details(self) -> None:
        """Test creating a SystemWarning without optional details."""
        warning = SystemWarning(
            warning_id="runbook_service_1706616001000000",
            category="runbook_service",
            message="Runbook service disabled",
            timestamp=1706616001000000,
        )

        assert warning.warning_id == "runbook_service_1706616001000000"
        assert warning.category == "runbook_service"
        assert warning.message == "Runbook service disabled"
        assert warning.details is None
        assert warning.timestamp == 1706616001000000

    def test_system_warning_missing_required_field(self) -> None:
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SystemWarning(
                warning_id="test_id",
                category="test_category",
                # Missing message
                timestamp=1706616000000000,
            )

        error = exc_info.value
        assert "message" in str(error)

    def test_system_warning_serialization(self) -> None:
        """Test serialization of SystemWarning to dict."""
        warning = SystemWarning(
            warning_id="test_warning_123",
            category="test_category",
            message="Test message",
            details="Test details",
            timestamp=1706616000000000,
        )

        warning_dict = warning.model_dump()

        assert warning_dict == {
            "warning_id": "test_warning_123",
            "category": "test_category",
            "message": "Test message",
            "details": "Test details",
            "timestamp": 1706616000000000,
        }

    def test_system_warning_deserialization(self) -> None:
        """Test deserialization of SystemWarning from dict."""
        warning_dict = {
            "warning_id": "test_warning_456",
            "category": "test_category",
            "message": "Test message",
            "timestamp": 1706616000000000,
        }

        warning = SystemWarning(**warning_dict)

        assert warning.warning_id == "test_warning_456"
        assert warning.category == "test_category"
        assert warning.message == "Test message"
        assert warning.details is None
        assert warning.timestamp == 1706616000000000
