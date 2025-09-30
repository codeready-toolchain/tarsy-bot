"""Unit tests for system controller."""

import pytest
from fastapi.testclient import TestClient

from tarsy.main import app
from tarsy.services.system_warnings_service import SystemWarningsService


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_warnings_singleton() -> None:
    """Reset warnings singleton before each test."""
    SystemWarningsService._instance = None


@pytest.mark.unit
def test_get_system_warnings_empty(client: TestClient) -> None:
    """Test getting system warnings when none exist."""
    response = client.get("/api/v1/system/warnings")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.unit
def test_get_system_warnings_with_warnings(client: TestClient) -> None:
    """Test getting system warnings when warnings exist."""
    from tarsy.models.system_models import WarningCategory
    from tarsy.services.system_warnings_service import get_warnings_service

    # Add some warnings
    warnings_service = get_warnings_service()
    warnings_service.add_warning(
        WarningCategory.MCP_INITIALIZATION,
        "MCP Server 'kubernetes-server' failed to initialize",
        "Connection timeout after 30 seconds",
    )
    warnings_service.add_warning(
        WarningCategory.RUNBOOK_SERVICE,
        "Runbook service disabled",
        "Set GITHUB_TOKEN environment variable",
    )

    response = client.get("/api/v1/system/warnings")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 2

    # Check first warning
    assert data[0]["category"] == WarningCategory.MCP_INITIALIZATION
    assert data[0]["message"] == "MCP Server 'kubernetes-server' failed to initialize"
    assert data[0]["details"] == "Connection timeout after 30 seconds"
    assert "warning_id" in data[0]
    assert "timestamp" in data[0]

    # Check second warning
    assert data[1]["category"] == WarningCategory.RUNBOOK_SERVICE
    assert data[1]["message"] == "Runbook service disabled"
    assert data[1]["details"] == "Set GITHUB_TOKEN environment variable"
    assert "warning_id" in data[1]
    assert "timestamp" in data[1]


@pytest.mark.unit
def test_get_system_warnings_response_format(client: TestClient) -> None:
    """Test that system warnings response follows correct format."""
    from tarsy.services.system_warnings_service import get_warnings_service

    warnings_service = get_warnings_service()
    warnings_service.add_warning("test_category", "test message", "test details")

    response = client.get("/api/v1/system/warnings")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    warning = data[0]
    assert isinstance(warning, dict)
    assert set(warning.keys()) == {
        "warning_id",
        "category",
        "message",
        "details",
        "timestamp",
    }
    assert isinstance(warning["warning_id"], str)
    assert isinstance(warning["category"], str)
    assert isinstance(warning["message"], str)
    assert isinstance(warning["timestamp"], int)


@pytest.mark.unit
def test_get_system_warnings_without_details(client: TestClient) -> None:
    """Test getting system warnings when details field is None."""
    from tarsy.services.system_warnings_service import get_warnings_service

    warnings_service = get_warnings_service()
    warnings_service.add_warning("test_category", "test message")

    response = client.get("/api/v1/system/warnings")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["details"] is None
