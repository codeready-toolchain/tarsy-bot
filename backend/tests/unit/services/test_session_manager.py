"""
Unit tests for SessionManager.

Tests the session management functionality including creation,
status updates, and error handling.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tarsy.models.constants import AlertSessionStatus
from tarsy.services.session_manager import SessionManager
from tests.utils import AlertFactory


@pytest.mark.unit
class TestSessionManagerInitialization:
    """Test SessionManager initialization."""
    
    def test_initialization_with_history_service(self):
        """Test that SessionManager initializes with history service."""
        history_service = Mock()
        
        manager = SessionManager(history_service=history_service)
        
        assert manager.history_service == history_service


@pytest.mark.unit
class TestCreateChainHistorySession:
    """Test chain history session creation."""
    
    def test_create_chain_history_session_success(self):
        """Test creating a history session successfully."""
        history_service = Mock()
        history_service.create_session = Mock(return_value=True)
        
        manager = SessionManager(history_service=history_service)
        
        # Create mock chain context
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.processing_context import ChainContext
        
        alert = AlertFactory.create_kubernetes_alert()
        processing_alert = ProcessingAlert(
            alert_type=alert.alert_type or "kubernetes",
            severity=alert.data.get("severity", "critical"),
            timestamp=alert.timestamp,
            environment=alert.data.get("environment", "production"),
            runbook_url=alert.runbook,
            alert_data=alert.data
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="session-1"
        )
        
        # Create mock chain definition
        chain_definition = SimpleNamespace(
            chain_id="test-chain",
            stages=[]
        )
        
        result = manager.create_chain_history_session(chain_context, chain_definition)
        
        assert result is True
        history_service.create_session.assert_called_once_with(
            chain_context=chain_context,
            chain_definition=chain_definition
        )
    
    def test_create_chain_history_session_history_disabled(self):
        """Test that session creation returns False when history is disabled."""
        history_service = Mock()
        
        manager = SessionManager(history_service=history_service)
        
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.processing_context import ChainContext
        
        alert = AlertFactory.create_kubernetes_alert()
        processing_alert = ProcessingAlert(
            alert_type=alert.alert_type or "kubernetes",
            severity=alert.data.get("severity", "critical"),
            timestamp=alert.timestamp,
            environment=alert.data.get("environment", "production"),
            runbook_url=alert.runbook,
            alert_data=alert.data
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="session-1"
        )
        
        chain_definition = SimpleNamespace(chain_id="test-chain", stages=[])
        
        result = manager.create_chain_history_session(chain_context, chain_definition)
        
        assert result is False
    
    def test_create_chain_history_session_creation_failed(self):
        """Test handling when session creation fails."""
        history_service = Mock()
        history_service.create_session = Mock(return_value=False)
        
        manager = SessionManager(history_service=history_service)
        
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.processing_context import ChainContext
        
        alert = AlertFactory.create_kubernetes_alert()
        processing_alert = ProcessingAlert(
            alert_type=alert.alert_type or "kubernetes",
            severity=alert.data.get("severity", "critical"),
            timestamp=alert.timestamp,
            environment=alert.data.get("environment", "production"),
            runbook_url=alert.runbook,
            alert_data=alert.data
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="session-1"
        )
        
        chain_definition = SimpleNamespace(chain_id="test-chain", stages=[])
        
        result = manager.create_chain_history_session(chain_context, chain_definition)
        
        assert result is False


@pytest.mark.unit
class TestUpdateSessionStatus:
    """Test session status updates."""
    
    def test_update_session_status_to_in_progress(self):
        """Test updating session status to IN_PROGRESS."""
        history_service = Mock()
        history_service.update_session_status = Mock()
        
        manager = SessionManager(history_service=history_service)
        
        manager.update_session_status(
            session_id="session-1",
            status=AlertSessionStatus.IN_PROGRESS.value
        )
        
        history_service.update_session_status.assert_called_once_with(
            session_id="session-1",
            status=AlertSessionStatus.IN_PROGRESS.value,
            error_message=None,
            final_analysis=None,
            final_analysis_summary=None,
            pause_metadata=None
        )
    
    def test_update_session_status_to_completed(self):
        """Test updating session status to COMPLETED with analysis."""
        history_service = Mock()
        history_service.update_session_status = Mock()
        
        manager = SessionManager(history_service=history_service)
        
        manager.update_session_status(
            session_id="session-1",
            status=AlertSessionStatus.COMPLETED.value,
            final_analysis="Analysis complete",
            final_analysis_summary="Summary"
        )
        
        history_service.update_session_status.assert_called_once_with(
            session_id="session-1",
            status=AlertSessionStatus.COMPLETED.value,
            error_message=None,
            final_analysis="Analysis complete",
            final_analysis_summary="Summary",
            pause_metadata=None
        )
    
    def test_update_session_status_to_paused(self):
        """Test updating session status to PAUSED with metadata."""
        history_service = Mock()
        history_service.update_session_status = Mock()
        
        manager = SessionManager(history_service=history_service)
        
        pause_meta = {
            "reason": "max_iterations_reached",
            "current_iteration": 5,
            "message": "Paused after 5 iterations"
        }
        
        manager.update_session_status(
            session_id="session-1",
            status=AlertSessionStatus.PAUSED.value,
            pause_metadata=pause_meta
        )
        
        history_service.update_session_status.assert_called_once_with(
            session_id="session-1",
            status=AlertSessionStatus.PAUSED.value,
            error_message=None,
            final_analysis=None,
            final_analysis_summary=None,
            pause_metadata=pause_meta
        )
    
    def test_update_session_status_no_session_id(self):
        """Test that update is skipped when session_id is None."""
        history_service = Mock()
        
        manager = SessionManager(history_service=history_service)
        
        # Should not raise an error and should not call history service
        manager.update_session_status(
            session_id=None,
            status=AlertSessionStatus.IN_PROGRESS.value
        )
        
        history_service.update_session_status.assert_not_called()
    
    def test_update_session_status_history_disabled(self):
        """Test that update is skipped when history is disabled."""
        history_service = Mock()
        
        manager = SessionManager(history_service=history_service)
        
        manager.update_session_status(
            session_id="session-1",
            status=AlertSessionStatus.IN_PROGRESS.value
        )
        
        # Should not call update_session_status when disabled
        history_service.update_session_status.assert_not_called()
    
    def test_update_session_status_raises_on_exception(self):
        """Test that exceptions from history service are propagated."""
        history_service = Mock()
        history_service.update_session_status = Mock(side_effect=RuntimeError("Database connection failed"))
        
        manager = SessionManager(history_service=history_service)
        
        # Exception should be raised, not swallowed
        with pytest.raises(RuntimeError, match="Database connection failed"):
            manager.update_session_status(
                session_id="session-1",
                status=AlertSessionStatus.IN_PROGRESS.value
            )


@pytest.mark.unit
class TestUpdateSessionError:
    """Test session error handling."""
    
    def test_update_session_error(self):
        """Test marking session as failed with error message."""
        history_service = Mock()
        history_service.update_session_status = Mock()
        
        manager = SessionManager(history_service=history_service)
        
        manager.update_session_error("session-1", "Test error occurred")
        
        history_service.update_session_status.assert_called_once_with(
            session_id="session-1",
            status=AlertSessionStatus.FAILED.value,
            error_message="Test error occurred"
        )
    
    def test_update_session_error_no_session_id(self):
        """Test that error update is skipped when session_id is None."""
        history_service = Mock()
        
        manager = SessionManager(history_service=history_service)
        
        manager.update_session_error(None, "Test error")
        
        history_service.update_session_status.assert_not_called()
    
    def test_update_session_error_history_disabled(self):
        """Test that error update is skipped when history is disabled."""
        history_service = Mock()
        
        manager = SessionManager(history_service=history_service)
        
        manager.update_session_error("session-1", "Test error")
        
        history_service.update_session_status.assert_not_called()
    
    def test_update_session_error_swallows_exception(self):
        """Test that exceptions from history service are logged but not raised.
        
        This is intentional behavior since update_session_error is called from
        exception handlers and we don't want to mask the original error.
        """
        history_service = Mock()
        history_service.update_session_status = Mock(side_effect=RuntimeError("Database connection failed"))
        
        manager = SessionManager(history_service=history_service)
        
        # Exception should be swallowed, not raised
        manager.update_session_error("session-1", "Original error message")
        
        # Verify the call was attempted
        history_service.update_session_status.assert_called_once()

