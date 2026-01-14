"""
Unit tests for alert submission with session creation.

Tests that the submit_alert endpoint creates the session in the database
before returning the response to the client, eliminating race conditions.
"""

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tarsy.main import app
from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
from tarsy.models.db_models import AlertSession


@pytest.mark.unit
class TestAlertSubmissionSessionCreation:
    """Test session creation during alert submission."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def valid_alert_data(self):
        """Valid alert data for testing."""
        return {
            "alert_type": "kubernetes",
            "data": {
                "namespace": "test-namespace",
                "pod_name": "test-pod-12345",
                "message": "Test alert for session creation verification",
                "severity": "critical"
            }
        }

    @pytest.fixture
    def mock_chain_definition(self):
        """Mock chain definition."""
        return ChainConfigModel(
            chain_id="test-chain",
            alert_types=["kubernetes"],
            stages=[
                ChainStageConfigModel(
                    name="analysis",
                    agent="KubernetesAgent"
                )
            ]
        )

    @pytest.fixture(autouse=True)
    def mock_alert_service(self, mock_chain_definition):
        """Mock alert_service for all tests in this class."""
        with patch('tarsy.main.alert_service') as mock_service:
            mock_chain_registry = Mock()
            mock_chain_registry.get_default_alert_type.return_value = "kubernetes"
            mock_service.chain_registry = mock_chain_registry
            mock_service.get_chain_for_alert.return_value = mock_chain_definition
            mock_service.session_manager = Mock()
            yield mock_service

    def test_submit_alert_creates_session_before_response(
        self, client, valid_alert_data, mock_alert_service, mock_chain_definition
    ):
        """Test that session is created in database before API response is returned."""
        # Arrange - Mock session creation to return True
        mock_alert_service.session_manager.create_chain_history_session.return_value = True
        
        # Mock background processing
        app.state.process_alert_callback = AsyncMock()
        
        # Act
        response = client.post("/api/v1/alerts", json=valid_alert_data)
        
        # Assert response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "session_id" in data
        session_id = data["session_id"]
        
        # Verify chain was selected
        mock_alert_service.get_chain_for_alert.assert_called_once_with("kubernetes")
        
        # Verify session was created before response
        mock_alert_service.session_manager.create_chain_history_session.assert_called_once()
        call_args = mock_alert_service.session_manager.create_chain_history_session.call_args
        chain_context = call_args[0][0]
        chain_def = call_args[0][1]
        
        assert chain_context.session_id == session_id
        assert chain_def == mock_chain_definition
        
        # Verify background task was started
        app.state.process_alert_callback.assert_called_once()

    def test_submit_alert_returns_400_for_invalid_alert_type(
        self, client, valid_alert_data, mock_alert_service
    ):
        """Test that invalid alert type returns 400 error."""
        # Arrange - Override get_chain_for_alert to raise ValueError
        mock_alert_service.get_chain_for_alert.side_effect = ValueError(
            "No chain found for alert type 'invalid_type'"
        )
        
        valid_alert_data["alert_type"] = "invalid_type"
        
        # Act
        response = client.post("/api/v1/alerts", json=valid_alert_data)
        
        # Assert
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "error" in data["detail"]
        assert data["detail"]["error"] == "Invalid alert type"
        assert "No chain found" in data["detail"]["message"]

    def test_submit_alert_returns_500_when_session_creation_fails(
        self, client, valid_alert_data, mock_alert_service
    ):
        """Test that session creation failure returns 500 error."""
        # Arrange - Session creation fails
        mock_alert_service.session_manager.create_chain_history_session.return_value = False
        
        # Act
        response = client.post("/api/v1/alerts", json=valid_alert_data)
        
        # Assert
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "error" in data["detail"]
        assert data["detail"]["error"] == "Session creation failed"

