"""
Tests for session timeout handling in alert processing.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.models.alert import ProcessingAlert
from tarsy.models.processing_context import ChainContext
from tarsy.utils.timestamp import now_us


@pytest.mark.unit
class TestMarkSessionAsFailedFunction:
    """Test the fixed mark_session_as_failed function in main.py."""

    @pytest.mark.asyncio
    async def test_mark_session_as_failed_updates_status_and_publishes_event(self):
        """Test that mark_session_as_failed correctly updates session and publishes event."""
        from tarsy.main import mark_session_as_failed
        
        # Create test alert context
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="high",
            timestamp=now_us(),
            alert_data={"test": "data"}
        )
        alert_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123"
        )
        
        # Mock alert_service
        mock_alert_service = Mock()
        mock_session_manager = Mock()
        mock_session_manager.update_session_error = Mock()
        mock_alert_service.session_manager = mock_session_manager
        mock_alert_service.settings = Mock()
        mock_alert_service.settings.alert_processing_timeout = 900
        
        # Mock history service
        mock_history_service = Mock()
        mock_history_service.fail_active_stages_on_timeout = AsyncMock(return_value=0)
        
        # Mock the event publisher inside tarsy.main
        with patch('tarsy.main.alert_service', mock_alert_service), \
             patch('tarsy.services.history_service.get_history_service', return_value=mock_history_service), \
             patch('tarsy.services.events.event_helpers.publish_session_failed', new_callable=AsyncMock) as mock_publish:
            
            # Call mark_session_as_failed
            await mark_session_as_failed(alert_context, "Test error message")
            
            # Verify session status was updated
            mock_session_manager.update_session_error.assert_called_once_with(
                "test-session-123",
                "Test error message"
            )
            
            # Verify event was published
            mock_publish.assert_called_once_with("test-session-123")

    @pytest.mark.asyncio
    async def test_mark_session_as_failed_handles_missing_alert_service(self):
        """Test that mark_session_as_failed handles missing alert_service gracefully."""
        from tarsy.main import mark_session_as_failed
        
        # Create test alert context
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="high",
            timestamp=now_us(),
            alert_data={"test": "data"}
        )
        alert_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-456"
        )
        
        # Mock alert_service as None (not initialized)
        with patch('tarsy.main.alert_service', None):
            # Should not raise exception
            await mark_session_as_failed(alert_context, "Error message")
            # No assertions needed - just verify it doesn't crash

    @pytest.mark.asyncio
    async def test_mark_session_as_failed_handles_none_alert_context(self):
        """Test that mark_session_as_failed handles None alert gracefully."""
        from tarsy.main import mark_session_as_failed
        
        # Should not raise exception with None alert
        await mark_session_as_failed(None, "Error message")
        # No assertions needed - just verify it doesn't crash


@pytest.mark.unit 
class TestTimeoutErrorHandlingInMain:
    """Test that TimeoutError in process_alert_background uses fixed mark_session_as_failed."""

    @pytest.fixture
    def mock_alert_data(self):
        """Mock alert processing data."""
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="high",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"}
        )
        return ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-timeout"
        )

    @pytest.mark.asyncio
    async def test_timeout_error_calls_fixed_mark_session_as_failed(self, mock_alert_data):
        """Test that TimeoutError properly updates session status and publishes event."""
        from tarsy.main import process_alert_background
        
        # Create mock alert_service with proper structure
        mock_alert_service = Mock()
        
        # Make process_alert hang to trigger timeout
        async def slow_process(*args, **kwargs):
            await asyncio.sleep(10)
        
        mock_alert_service.process_alert = AsyncMock(side_effect=slow_process)
        mock_session_manager = Mock()
        mock_session_manager.update_session_error = Mock()
        mock_alert_service.session_manager = mock_session_manager
        
        # Mock history service
        mock_history_service = Mock()
        mock_history_service.fail_active_stages_on_timeout = AsyncMock(return_value=0)
        
        # Mock the event publisher
        with patch('tarsy.main.alert_service', mock_alert_service), \
             patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)), \
             patch('tarsy.main.get_settings') as mock_get_settings, \
             patch('tarsy.main.active_tasks_lock', asyncio.Lock()), \
             patch('tarsy.main.active_tasks', {}), \
             patch('tarsy.services.history_service.get_history_service', return_value=mock_history_service), \
             patch('tarsy.services.events.event_helpers.publish_session_failed', new_callable=AsyncMock) as mock_publish:
            
            # Configure settings with short timeout
            settings = Mock()
            settings.alert_processing_timeout = 0.1  # 100ms timeout
            mock_get_settings.return_value = settings
            
            # Run process_alert_background - should timeout and handle it
            await process_alert_background("test-session-timeout", mock_alert_data)
            
            # Verify session was marked as failed
            mock_session_manager.update_session_error.assert_called_once()
            call_args = mock_session_manager.update_session_error.call_args[0]
            assert call_args[0] == "test-session-timeout"
            assert "timeout" in call_args[1].lower()
            
            # Verify event was published
            mock_publish.assert_called_once_with("test-session-timeout")

    @pytest.mark.parametrize("error_type,error_message,expected_in_message,expected_session_id", [
        (ValueError, "Invalid data", "invalid", "test-err-val"),
        (ConnectionError, "Network failed", "connection", "test-err-conn"),
        (MemoryError, "Out of memory", "memory", "test-err-mem"),
        (Exception, "Unexpected error", "unexpected", "test-err-exc"),
    ])
    @pytest.mark.asyncio
    async def test_various_errors_call_mark_session_as_failed(
        self, error_type, error_message, expected_in_message, expected_session_id
    ):
        """Test that various error types properly call mark_session_as_failed."""
        from tarsy.main import process_alert_background
        
        # Create alert data with unique session ID for this test
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="high",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"}
        )
        mock_alert_data = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id=expected_session_id
        )
        
        # Create mock alert_service
        mock_alert_service = Mock()
        mock_alert_service.process_alert = AsyncMock(side_effect=error_type(error_message))
        mock_session_manager = Mock()
        mock_session_manager.update_session_error = Mock()
        mock_alert_service.session_manager = mock_session_manager
        
        # Mock history service
        mock_history_service = Mock()
        mock_history_service.fail_active_stages_on_timeout = AsyncMock(return_value=0)
        
        with patch('tarsy.main.alert_service', mock_alert_service), \
             patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)), \
             patch('tarsy.main.get_settings') as mock_get_settings, \
             patch('tarsy.main.active_tasks_lock', asyncio.Lock()), \
             patch('tarsy.main.active_tasks', {}), \
             patch('tarsy.services.history_service.get_history_service', return_value=mock_history_service), \
             patch('tarsy.services.events.event_helpers.publish_session_failed', new_callable=AsyncMock) as mock_publish:
            
            settings = Mock()
            settings.alert_processing_timeout = 10
            mock_get_settings.return_value = settings
            
            # Run process_alert_background
            await process_alert_background(expected_session_id, mock_alert_data)
            
            # Verify session was marked as failed
            mock_session_manager.update_session_error.assert_called_once()
            call_args = mock_session_manager.update_session_error.call_args[0]
            assert call_args[0] == expected_session_id
            assert expected_in_message in call_args[1].lower()
            
            # Verify event was published
            mock_publish.assert_called_once_with(expected_session_id)

