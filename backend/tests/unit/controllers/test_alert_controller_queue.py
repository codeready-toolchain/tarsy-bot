"""
Unit tests for alert controller queue validation
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tarsy.main import app

pytestmark = pytest.mark.unit


@pytest.fixture
def test_client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_alert_service():
    """Mock alert service."""
    with patch("tarsy.main.alert_service") as mock:
        mock_chain_registry = MagicMock()
        mock_chain_registry.get_default_alert_type.return_value = "generic"
        mock_chain_registry.list_available_alert_types.return_value = ["generic", "kubernetes"]
        mock.chain_registry = mock_chain_registry
        mock.get_chain_for_alert.return_value = {"stages": []}
        mock.session_manager = MagicMock()
        mock.session_manager.create_chain_history_session.return_value = True
        yield mock


@pytest.fixture
def mock_history_service():
    """Mock history service."""
    with patch("tarsy.services.history_service.get_history_service") as mock:
        service = MagicMock()
        service.repository = MagicMock()
        service.count_pending_sessions = MagicMock(return_value=0)
        mock.return_value = service
        yield service


@pytest.fixture
def mock_settings_with_queue_limit():
    """Mock settings with queue size limit."""
    with patch("tarsy.config.settings.get_settings") as mock:
        settings = MagicMock()
        settings.max_queue_size = 10
        settings.alert_data_masking_enabled = False
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_settings_no_queue_limit():
    """Mock settings without queue size limit."""
    with patch("tarsy.config.settings.get_settings") as mock:
        settings = MagicMock()
        settings.max_queue_size = None
        settings.alert_data_masking_enabled = False
        mock.return_value = settings
        yield settings


def test_submit_alert_queue_not_full(
    test_client,
    mock_alert_service,
    mock_history_service,
    mock_settings_with_queue_limit
):
    """Test submitting alert when queue has space."""
    # Queue has space (5 < 10)
    mock_history_service.count_pending_sessions.return_value = 5
    
    response = test_client.post(
        "/api/v1/alerts",
        json={
            "data": {"message": "test alert"}
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data
    assert data["status"] == "queued"


def test_submit_alert_queue_full(
    test_client,
    mock_alert_service,
    mock_history_service,
    mock_settings_with_queue_limit
):
    """Test submitting alert when queue is full."""
    # Queue is full (10 >= 10)
    mock_history_service.count_pending_sessions.return_value = 10
    
    response = test_client.post(
        "/api/v1/alerts",
        json={
            "data": {"message": "test alert"}
        }
    )
    
    assert response.status_code == 429  # Too Many Requests
    data = response.json()
    assert "error" in data["detail"]
    assert data["detail"]["error"] == "Queue full"
    assert data["detail"]["queue_size"] == 10
    assert data["detail"]["max_queue_size"] == 10


def test_submit_alert_no_queue_limit(
    test_client,
    mock_alert_service,
    mock_history_service,
    mock_settings_no_queue_limit
):
    """Test submitting alert when queue has no size limit."""
    # Even with many pending, should succeed
    mock_history_service.count_pending_sessions.return_value = 1000
    
    response = test_client.post(
        "/api/v1/alerts",
        json={
            "data": {"message": "test alert"}
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data


def test_submit_alert_queue_check_not_called_when_no_limit(
    test_client,
    mock_alert_service,
    mock_history_service,
    mock_settings_no_queue_limit
):
    """Test queue check is skipped when no limit configured."""
    response = test_client.post(
        "/api/v1/alerts",
        json={
            "data": {"message": "test alert"}
        }
    )
    
    assert response.status_code == 200
    # count_pending_sessions should not be called
    mock_history_service.count_pending_sessions.assert_not_called()


def test_submit_alert_queue_limit_boundary(
    test_client,
    mock_alert_service,
    mock_history_service,
    mock_settings_with_queue_limit
):
    """Test queue limit at exact boundary."""
    # Queue at limit - 1 (9 < 10) - should succeed
    mock_history_service.count_pending_sessions.return_value = 9
    
    response = test_client.post(
        "/api/v1/alerts",
        json={
            "data": {"message": "test alert"}
        }
    )
    
    assert response.status_code == 200
    
    # Queue at limit (10 >= 10) - should fail
    mock_history_service.count_pending_sessions.return_value = 10
    
    response = test_client.post(
        "/api/v1/alerts",
        json={
            "data": {"message": "test alert"}
        }
    )
    
    assert response.status_code == 429
