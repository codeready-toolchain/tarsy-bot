"""
Unit tests for HistoryService session cancellation methods.

Tests get_session and update_session_to_canceling methods with various scenarios.
"""

from unittest.mock import Mock, patch

import pytest

from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession
from tarsy.services.history_service import HistoryService
from tarsy.utils.timestamp import now_us
from tests.utils import MockFactory


class TestHistoryServiceCancellation:
    """Test suite for HistoryService cancellation-related methods."""
    
    @pytest.fixture
    def mock_settings(self, isolated_test_settings):
        """Create mock settings for testing."""
        return isolated_test_settings
    
    @pytest.fixture
    def history_service(self, mock_settings):
        """Create HistoryService instance with mocked dependencies."""
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            service._initialization_attempted = True
            service._is_healthy = True
            return service
    
    @pytest.mark.unit
    def test_get_session_returns_session_when_found(self, history_service) -> None:
        """Test that get_session returns session when it exists in database."""
        session_id = "test-session-123"
        expected_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.IN_PROGRESS.value,
            started_at_us=now_us(),
            chain_id="chain-1"
        )
        
        mock_repo = Mock()
        mock_repo.get_alert_session.return_value = expected_session
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo
            
            result = history_service.get_session(session_id)
            
            assert result is not None
            assert result.session_id == session_id
            assert result.status == AlertSessionStatus.IN_PROGRESS.value
            mock_repo.get_alert_session.assert_called_once_with(session_id)
    
    @pytest.mark.unit
    def test_get_session_returns_none_when_not_found(self, history_service) -> None:
        """Test that get_session returns None when session doesn't exist."""
        session_id = "nonexistent-session"
        
        mock_repo = Mock()
        mock_repo.get_alert_session.return_value = None
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo
            
            result = history_service.get_session(session_id)
            
            assert result is None
    
    @pytest.mark.unit
    def test_get_session_returns_none_when_service_disabled(self) -> None:
        """Test that get_session returns None when history service is disabled."""
        mock_settings = MockFactory.create_mock_settings(history_enabled=False)
        
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            
            result = service.get_session("any-session-id")
            
            assert result is None
    
    @pytest.mark.unit
    @pytest.mark.parametrize(
        "current_status,expected_success,expected_returned_status",
        [
            (AlertSessionStatus.PENDING.value, True, AlertSessionStatus.CANCELING.value),
            (AlertSessionStatus.IN_PROGRESS.value, True, AlertSessionStatus.CANCELING.value),
            (AlertSessionStatus.PAUSED.value, True, AlertSessionStatus.CANCELING.value),  # Can cancel paused sessions
            (AlertSessionStatus.CANCELING.value, True, AlertSessionStatus.CANCELING.value),  # Idempotent
            (AlertSessionStatus.COMPLETED.value, False, AlertSessionStatus.COMPLETED.value),
            (AlertSessionStatus.FAILED.value, False, AlertSessionStatus.FAILED.value),
            (AlertSessionStatus.CANCELLED.value, False, AlertSessionStatus.CANCELLED.value),
        ],
    )
    def test_update_session_to_canceling_scenarios(
        self,
        history_service,
        current_status: str,
        expected_success: bool,
        expected_returned_status: str
    ) -> None:
        """Test update_session_to_canceling with various current statuses."""
        session_id = "test-session-456"
        
        # Create a mock session with the current status
        mock_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=current_status,
            started_at_us=now_us(),
            chain_id="chain-1"
        )
        
        mock_repo = Mock()
        mock_repo.get_alert_session.return_value = mock_session
        
        if expected_success and current_status != AlertSessionStatus.CANCELING.value:
            # Only for non-idempotent cases, expect update to be called
            mock_repo.update_alert_session.return_value = True
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo
            
            success, returned_status = history_service.update_session_to_canceling(session_id)
            
            assert success == expected_success
            assert returned_status == expected_returned_status
            
            # Verify update was called only for non-terminal, non-canceling statuses
            if expected_success and current_status not in [
                AlertSessionStatus.CANCELING.value,
                AlertSessionStatus.COMPLETED.value,
                AlertSessionStatus.FAILED.value,
                AlertSessionStatus.CANCELLED.value
            ]:
                mock_repo.update_alert_session.assert_called_once()
    
    @pytest.mark.unit
    def test_update_session_to_canceling_session_not_found(self, history_service) -> None:
        """Test update_session_to_canceling returns False when session doesn't exist."""
        session_id = "nonexistent-session"
        
        mock_repo = Mock()
        mock_repo.get_alert_session.return_value = None
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo
            
            success, status = history_service.update_session_to_canceling(session_id)
            
            assert success is False
            assert status == "not_found"
    
    @pytest.mark.unit
    def test_update_session_to_canceling_when_service_disabled(self) -> None:
        """Test update_session_to_canceling returns False when service is disabled."""
        mock_settings = MockFactory.create_mock_settings(history_enabled=False)
        
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            
            success, status = service.update_session_to_canceling("any-session-id")
            
            assert success is False
            assert status == "unknown"
    
    @pytest.mark.unit
    def test_update_session_to_canceling_idempotent_for_already_canceling(
        self, history_service
    ) -> None:
        """Test that calling update_session_to_canceling on already CANCELING session is idempotent."""
        session_id = "test-session-789"
        
        mock_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.CANCELING.value,
            started_at_us=now_us(),
            chain_id="chain-1"
        )
        
        mock_repo = Mock()
        mock_repo.get_alert_session.return_value = mock_session
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo
            
            success, status = history_service.update_session_to_canceling(session_id)
            
            # Should succeed (idempotent)
            assert success is True
            assert status == AlertSessionStatus.CANCELING.value
            
            # Should NOT call update since already in correct state
            mock_repo.update_alert_session.assert_not_called()
    
    @pytest.mark.unit
    def test_update_session_to_canceling_handles_update_failure(self, history_service) -> None:
        """Test update_session_to_canceling handles database update failure gracefully."""
        session_id = "test-session-fail"
        
        mock_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.IN_PROGRESS.value,
            started_at_us=now_us(),
            chain_id="chain-1"
        )
        
        mock_repo = Mock()
        mock_repo.get_alert_session.return_value = mock_session
        mock_repo.update_alert_session.return_value = False  # Simulate update failure
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo
            
            success, status = history_service.update_session_to_canceling(session_id)
            
            assert success is False
            # Note: The session object is modified before update attempt, 
            # so status will be CANCELING even if update fails
            assert status in [AlertSessionStatus.IN_PROGRESS.value, AlertSessionStatus.CANCELING.value]

