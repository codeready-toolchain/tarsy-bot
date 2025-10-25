"""
Unit tests for session cancellation endpoint and orphan detection.

Tests the POST /api/v1/sessions/{session_id}/cancel endpoint and the
background orphan detection task.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tarsy.controllers.history_controller import (
    check_cancellation_completion,
    router,
)
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession
from tarsy.services.history_service import get_history_service
from tarsy.utils.timestamp import now_us
from tests.utils import MockFactory


class TestCancelSessionEndpoint:
    """Test suite for cancel_session endpoint."""

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

    @pytest.fixture
    def mock_history_service(self):
        """Create mock history service."""
        service = MockFactory.create_mock_history_service()
        return service

    @pytest.mark.unit
    def test_cancel_session_success_for_active_session(
        self, app, client, mock_history_service
    ) -> None:
        """Test successful cancellation of an active session."""
        session_id = "active-session-123"

        # Mock session retrieval
        mock_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.IN_PROGRESS.value,
            started_at_us=now_us(),
            chain_id="chain-1"
        )
        mock_history_service.get_session.return_value = mock_session

        # Mock successful status update
        mock_history_service.update_session_to_canceling.return_value = (True, AlertSessionStatus.CANCELING.value)

        # Override dependency
        app.dependency_overrides[get_history_service] = lambda: mock_history_service

        # Mock event publishing and background task check function
        with patch('tarsy.services.events.event_helpers.publish_cancel_request', new_callable=AsyncMock) as mock_publish:
            with patch('tarsy.controllers.history_controller.check_cancellation_completion', new_callable=AsyncMock) as mock_bg_task:
                response = client.post(f"/api/v1/history/sessions/{session_id}/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "canceling"
        assert "Cancellation request sent" in data["message"]

        # Verify methods called (get_session called once by endpoint, background task is mocked)
        mock_history_service.get_session.assert_called_once_with(session_id)
        mock_history_service.update_session_to_canceling.assert_called_once_with(session_id)
        mock_publish.assert_called_once_with(session_id)
        # Verify background task was scheduled
        mock_bg_task.assert_called_once()

    @pytest.mark.unit
    def test_cancel_session_not_found(self, app, client, mock_history_service) -> None:
        """Test cancellation returns 404 when session doesn't exist."""
        session_id = "nonexistent-session"

        mock_history_service.get_session.return_value = None

        app.dependency_overrides[get_history_service] = lambda: mock_history_service

        response = client.post(f"/api/v1/history/sessions/{session_id}/cancel")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower() or session_id in data["detail"]
    
    @pytest.mark.unit
    @pytest.mark.parametrize(
        "terminal_status",
        [
            AlertSessionStatus.COMPLETED.value,
            AlertSessionStatus.FAILED.value,
            AlertSessionStatus.CANCELLED.value,
        ],
    )
    def test_cancel_session_already_terminal(
        self, app, client, mock_history_service, terminal_status: str
    ) -> None:
        """Test cancellation returns 400 when session is already terminal."""
        session_id = "terminal-session"
        
        # Mock session with terminal status
        mock_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=terminal_status,
            started_at_us=now_us(),
            completed_at_us=now_us(),
            chain_id="chain-1"
        )
        mock_history_service.get_session.return_value = mock_session
        
        # Mock update returns False for terminal status
        mock_history_service.update_session_to_canceling.return_value = (False, terminal_status)
        
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Mock event publishing and background task to avoid import errors
        with patch('tarsy.services.events.event_helpers.publish_cancel_request', new_callable=AsyncMock):
            with patch('tarsy.controllers.history_controller.check_cancellation_completion', new_callable=AsyncMock):
                response = client.post(f"/api/v1/history/sessions/{session_id}/cancel")
        
        assert response.status_code == 400
        data = response.json()
        assert terminal_status in data["detail"] or "cannot cancel" in data["detail"].lower()
    
    @pytest.mark.unit
    def test_cancel_session_idempotent_for_already_canceling(
        self, app, client, mock_history_service
    ) -> None:
        """Test cancellation is idempotent when session is already CANCELING."""
        session_id = "canceling-session"
        
        # Mock session already in CANCELING state
        mock_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.CANCELING.value,
            started_at_us=now_us(),
            chain_id="chain-1"
        )
        mock_history_service.get_session.return_value = mock_session
        
        # Mock update returns success (idempotent)
        mock_history_service.update_session_to_canceling.return_value = (True, AlertSessionStatus.CANCELING.value)
        
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Mock both event publishing and background task to prevent hanging
        with patch('tarsy.services.events.event_helpers.publish_cancel_request', new_callable=AsyncMock):
            with patch('tarsy.controllers.history_controller.check_cancellation_completion', new_callable=AsyncMock):
                response = client.post(f"/api/v1/history/sessions/{session_id}/cancel")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["status"] == "canceling"


class TestOrphanDetectionBackgroundTask:
    """Test suite for check_cancellation_completion background task."""
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_orphan_detection_completes_early_when_status_changes(self) -> None:
        """Test that orphan detection exits early when session status changes from CANCELING."""
        session_id = "test-session-early-exit"
        
        mock_history_service = MockFactory.create_mock_history_service()
        
        # Create sessions with different statuses
        canceling_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.CANCELING.value,
            started_at_us=now_us(),
            chain_id="chain-1"
        )
        
        cancelled_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.CANCELLED.value,
            started_at_us=now_us(),
            completed_at_us=now_us(),
            chain_id="chain-1"
        )
        
        # First call returns CANCELING, second call returns CANCELLED
        mock_history_service.get_session.side_effect = [canceling_session, cancelled_session]
        
        with patch('tarsy.controllers.history_controller.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await check_cancellation_completion(
                session_id=session_id,
                history_service=mock_history_service,
                timeout_seconds=60
            )
        
        # Should have slept at least once (10 seconds), then detected status change and exited
        # The function sleeps first, then checks status
        assert mock_sleep.call_count >= 1
        mock_sleep.assert_called_with(10)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_orphan_detection_marks_as_cancelled_after_timeout(self) -> None:
        """Test that orphan detection marks session as CANCELLED after timeout."""
        session_id = "test-session-orphan"
        
        mock_history_service = MockFactory.create_mock_history_service()
        
        # Session stays in CANCELING state throughout
        canceling_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.CANCELING.value,
            started_at_us=now_us(),
            chain_id="chain-1"
        )
        mock_history_service.get_session.return_value = canceling_session
        
        with patch('tarsy.controllers.history_controller.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            with patch('tarsy.services.events.event_helpers.publish_session_cancelled', new_callable=AsyncMock) as mock_publish:
                await check_cancellation_completion(
                    session_id=session_id,
                    history_service=mock_history_service,
                    timeout_seconds=30  # Short timeout for testing
                )
        
        # Should have slept 3 times (30 seconds / 10 second intervals)
        assert mock_sleep.call_count == 3
        
        # Should have updated session status to CANCELLED
        mock_history_service.update_session_status.assert_called_once()
        call_args = mock_history_service.update_session_status.call_args
        assert call_args.kwargs['session_id'] == session_id
        assert call_args.kwargs['status'] == AlertSessionStatus.CANCELLED.value
        assert 'orphaned' in call_args.kwargs['error_message'].lower()
        
        # Should have published cancellation event
        mock_publish.assert_called_once_with(session_id)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_orphan_detection_handles_session_not_found(self) -> None:
        """Test that orphan detection handles session not found gracefully."""
        session_id = "nonexistent-session"
        
        mock_history_service = MockFactory.create_mock_history_service()
        mock_history_service.get_session.return_value = None
        
        with patch('tarsy.controllers.history_controller.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await check_cancellation_completion(
                session_id=session_id,
                history_service=mock_history_service,
                timeout_seconds=30
            )
        
        # Should have slept once, then detected session not found and exited
        assert mock_sleep.call_count == 1
        
        # Should NOT try to update or publish
        mock_history_service.update_session_status.assert_not_called()
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_orphan_detection_handles_status_change_in_final_interval(self) -> None:
        """Test orphan detection when status changes right before timeout."""
        session_id = "test-session-last-minute"
        
        mock_history_service = MockFactory.create_mock_history_service()
        
        # Session is CANCELING for most checks, then becomes CANCELLED at the end
        canceling_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.CANCELING.value,
            started_at_us=now_us(),
            chain_id="chain-1"
        )
        
        cancelled_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.CANCELLED.value,
            started_at_us=now_us(),
            completed_at_us=now_us(),
            chain_id="chain-1"
        )
        
        # Return CANCELING for first 2 checks, then CANCELLED for final check
        mock_history_service.get_session.side_effect = [
            canceling_session,
            canceling_session,
            cancelled_session,  # Status changes just before final check
        ]
        
        with patch('tarsy.controllers.history_controller.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            with patch('tarsy.services.events.event_helpers.publish_session_cancelled', new_callable=AsyncMock) as mock_publish:
                await check_cancellation_completion(
                    session_id=session_id,
                    history_service=mock_history_service,
                    timeout_seconds=20  # 2 intervals
                )
        
        # Should have slept 2 times (20 seconds / 10 second intervals)
        assert mock_sleep.call_count == 2
        
        # Should NOT have updated status or published (status already changed)
        mock_history_service.update_session_status.assert_not_called()
        mock_publish.assert_not_called()

