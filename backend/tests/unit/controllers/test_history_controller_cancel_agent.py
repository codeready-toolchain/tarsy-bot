"""
Unit tests for the cancel_agent endpoint.

Tests the POST /api/v1/sessions/{session_id}/stages/{execution_id}/cancel endpoint.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tarsy.controllers.history_controller import router
from tarsy.models.api_models import CancelAgentResponse
from tarsy.models.constants import AlertSessionStatus, StageStatus


@pytest.mark.unit
class TestCancelAgentEndpoint:
    """Test suite for cancel_agent endpoint."""

    @pytest.fixture
    def app(self):
        """Create FastAPI application with history router."""
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_cancel_agent_endpoint_success(self, app, client) -> None:
        """Test successful agent cancellation."""
        session_id = "test-session-123"
        execution_id = "stage-exec-1"
        
        mock_alert_service = MagicMock()
        mock_alert_service.cancel_agent = AsyncMock(
            return_value=CancelAgentResponse(
                success=True,
                session_status=AlertSessionStatus.PAUSED.value,
                stage_status=StageStatus.PAUSED.value
            )
        )
        
        with patch(
            'tarsy.services.alert_service.get_alert_service',
            return_value=mock_alert_service
        ):
            response = client.post(
                f"/api/v1/history/sessions/{session_id}/stages/{execution_id}/cancel"
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["session_status"] == AlertSessionStatus.PAUSED.value
        assert data["stage_status"] == StageStatus.PAUSED.value
        
        mock_alert_service.cancel_agent.assert_called_once_with(session_id, execution_id)

    def test_cancel_agent_endpoint_validation_error_returns_400(
        self, app, client
    ) -> None:
        """Test that validation errors return 400."""
        session_id = "test-session-123"
        execution_id = "stage-exec-1"
        
        mock_alert_service = MagicMock()
        mock_alert_service.cancel_agent = AsyncMock(
            side_effect=ValueError("Stage execution is not paused")
        )
        
        with patch(
            'tarsy.services.alert_service.get_alert_service',
            return_value=mock_alert_service
        ):
            response = client.post(
                f"/api/v1/history/sessions/{session_id}/stages/{execution_id}/cancel"
            )
        
        assert response.status_code == 400
        data = response.json()
        assert "is not paused" in data["detail"]

    def test_cancel_agent_endpoint_session_not_found_returns_400(
        self, app, client
    ) -> None:
        """Test that session not found returns 400."""
        session_id = "nonexistent-session"
        execution_id = "stage-exec-1"
        
        mock_alert_service = MagicMock()
        mock_alert_service.cancel_agent = AsyncMock(
            side_effect=ValueError(f"Session {session_id} not found")
        )
        
        with patch(
            'tarsy.services.alert_service.get_alert_service',
            return_value=mock_alert_service
        ):
            response = client.post(
                f"/api/v1/history/sessions/{session_id}/stages/{execution_id}/cancel"
            )
        
        assert response.status_code == 400
        data = response.json()
        assert "not found" in data["detail"]

    def test_cancel_agent_endpoint_service_unavailable_returns_500(
        self, app, client
    ) -> None:
        """Test that service unavailable returns 500."""
        session_id = "test-session-123"
        execution_id = "stage-exec-1"
        
        with patch(
            'tarsy.services.alert_service.get_alert_service',
            return_value=None
        ):
            response = client.post(
                f"/api/v1/history/sessions/{session_id}/stages/{execution_id}/cancel"
            )
        
        assert response.status_code == 500
        data = response.json()
        assert "not available" in data["detail"]

    def test_cancel_agent_endpoint_internal_error_returns_500(
        self, app, client
    ) -> None:
        """Test that unexpected errors return 500."""
        session_id = "test-session-123"
        execution_id = "stage-exec-1"
        
        mock_alert_service = MagicMock()
        mock_alert_service.cancel_agent = AsyncMock(
            side_effect=Exception("Unexpected database error")
        )
        
        with patch(
            'tarsy.services.alert_service.get_alert_service',
            return_value=mock_alert_service
        ):
            response = client.post(
                f"/api/v1/history/sessions/{session_id}/stages/{execution_id}/cancel"
            )
        
        assert response.status_code == 500
        data = response.json()
        assert "Failed to cancel agent" in data["detail"]

    def test_cancel_agent_endpoint_returns_correct_response_model(
        self, app, client
    ) -> None:
        """Test that endpoint returns CancelAgentResponse model."""
        session_id = "test-session-123"
        execution_id = "stage-exec-1"
        
        mock_alert_service = MagicMock()
        mock_alert_service.cancel_agent = AsyncMock(
            return_value=CancelAgentResponse(
                success=True,
                session_status=AlertSessionStatus.IN_PROGRESS.value,
                stage_status=StageStatus.COMPLETED.value
            )
        )
        
        with patch(
            'tarsy.services.alert_service.get_alert_service',
            return_value=mock_alert_service
        ):
            response = client.post(
                f"/api/v1/history/sessions/{session_id}/stages/{execution_id}/cancel"
            )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response has expected fields
        assert "success" in data
        assert "session_status" in data
        assert "stage_status" in data
        
        # Verify we can create CancelAgentResponse from response
        response_model = CancelAgentResponse(**data)
        assert response_model.success is True
        assert response_model.session_status == AlertSessionStatus.IN_PROGRESS.value
        assert response_model.stage_status == StageStatus.COMPLETED.value

