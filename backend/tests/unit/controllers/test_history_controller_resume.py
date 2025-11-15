"""
Unit tests for resume endpoint in history controller.

Tests the POST /sessions/{session_id}/resume endpoint for resuming paused sessions.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import BackgroundTasks, HTTPException

from tarsy.controllers.history_controller import resume_session
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession


class TestResumeEndpoint:
    """Test suite for session resume endpoint."""
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_resume_paused_session_success(self) -> None:
        """Test successfully resuming a paused session."""
        session_id = "test-session-paused"
        
        # Create mock session with PAUSED status
        mock_session = MagicMock(spec=AlertSession)
        mock_session.session_id = session_id
        mock_session.status = AlertSessionStatus.PAUSED.value
        
        # Create mock history service
        mock_history_service = MagicMock()
        mock_history_service.get_session.return_value = mock_session
        
        # Create background tasks
        background_tasks = BackgroundTasks()
        
        # Patch get_alert_service at the source
        with patch('tarsy.services.alert_service.get_alert_service') as mock_get_alert:
            mock_alert_service = MagicMock()
            mock_alert_service.resume_paused_session = AsyncMock()
            mock_get_alert.return_value = mock_alert_service
            
            # Call the endpoint
            result = await resume_session(
                session_id=session_id,
                background_tasks=background_tasks,
                history_service=mock_history_service
            )
        
        # Verify response
        assert result["success"] is True
        assert result["message"] == "Session resume initiated"
        assert result["status"] == "resuming"
        
        # Verify get_session was called
        mock_history_service.get_session.assert_called_once_with(session_id)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_resume_session_not_found(self) -> None:
        """Test resuming a non-existent session returns 404."""
        session_id = "non-existent-session"
        
        # Create mock history service returning None
        mock_history_service = MagicMock()
        mock_history_service.get_session.return_value = None
        
        background_tasks = BackgroundTasks()
        
        # Call the endpoint and expect HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await resume_session(
                session_id=session_id,
                background_tasks=background_tasks,
                history_service=mock_history_service
            )
        
        # Verify 404 error
        assert exc_info.value.status_code == 404
        assert f"Session {session_id} not found" in str(exc_info.value.detail)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "session_status",
        [
            AlertSessionStatus.PENDING.value,
            AlertSessionStatus.IN_PROGRESS.value,
            AlertSessionStatus.COMPLETED.value,
            AlertSessionStatus.FAILED.value,
            AlertSessionStatus.CANCELLED.value,
            AlertSessionStatus.CANCELING.value,
        ],
    )
    async def test_resume_session_not_paused_returns_400(self, session_status: str) -> None:
        """Test resuming a session that is not paused returns 400."""
        session_id = "test-session-not-paused"
        
        # Create mock session with non-PAUSED status
        mock_session = MagicMock(spec=AlertSession)
        mock_session.session_id = session_id
        mock_session.status = session_status
        
        # Create mock history service
        mock_history_service = MagicMock()
        mock_history_service.get_session.return_value = mock_session
        
        background_tasks = BackgroundTasks()
        
        # Call the endpoint and expect HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await resume_session(
                session_id=session_id,
                background_tasks=background_tasks,
                history_service=mock_history_service
            )
        
        # Verify 400 error
        assert exc_info.value.status_code == 400
        assert "is not paused" in str(exc_info.value.detail)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_resume_session_alert_service_unavailable(self) -> None:
        """Test resuming when alert service is unavailable returns 500."""
        session_id = "test-session-service-unavailable"
        
        # Create mock session with PAUSED status
        mock_session = MagicMock(spec=AlertSession)
        mock_session.session_id = session_id
        mock_session.status = AlertSessionStatus.PAUSED.value
        
        # Create mock history service
        mock_history_service = MagicMock()
        mock_history_service.get_session.return_value = mock_session
        
        background_tasks = BackgroundTasks()
        
        # Patch get_alert_service to return None
        with patch('tarsy.services.alert_service.get_alert_service') as mock_get_alert:
            mock_get_alert.return_value = None
            
            # Call the endpoint and expect HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await resume_session(
                    session_id=session_id,
                    background_tasks=background_tasks,
                    history_service=mock_history_service
                )
        
        # Verify 500 error
        assert exc_info.value.status_code == 500
        assert "Alert service not available" in str(exc_info.value.detail)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_resume_session_background_task_added(self) -> None:
        """Test that resume triggers background task execution."""
        session_id = "test-session-background"
        
        # Create mock session with PAUSED status
        mock_session = MagicMock(spec=AlertSession)
        mock_session.session_id = session_id
        mock_session.status = AlertSessionStatus.PAUSED.value
        
        # Create mock history service
        mock_history_service = MagicMock()
        mock_history_service.get_session.return_value = mock_session
        
        # Create background tasks
        background_tasks = BackgroundTasks()
        
        # Patch get_alert_service
        with patch('tarsy.services.alert_service.get_alert_service') as mock_get_alert:
            mock_alert_service = MagicMock()
            mock_alert_service.resume_paused_session = AsyncMock()
            mock_get_alert.return_value = mock_alert_service
            
            # Call the endpoint
            await resume_session(
                session_id=session_id,
                background_tasks=background_tasks,
                history_service=mock_history_service
            )
        
        # Verify background task was added
        assert len(background_tasks.tasks) == 1

