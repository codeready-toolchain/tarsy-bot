"""
Unit tests for the CancellationTracker.
"""

import pytest

from tarsy.services import cancellation_tracker

@pytest.mark.unit
class TestCancellationTracker:
    """Tests for CancellationTracker functionality."""
    
    def setup_method(self):
        """Clear tracker state for each test."""
        cancellation_tracker._cancelled_sessions.clear()
    
    def test_mark_cancelled(self):
        """Test marking a session as user-cancelled."""
        session_id = "test-session-1"
        
        cancellation_tracker.mark_cancelled(session_id)
        
        assert cancellation_tracker.is_user_cancel(session_id) is True
    
    def test_is_user_cancel_returns_false_for_unknown(self):
        """Test that is_user_cancel returns False for unknown sessions (they are timeouts)."""
        assert cancellation_tracker.is_user_cancel("unknown-session") is False
    
    def test_clear(self):
        """Test clearing a session from the tracker."""
        session_id = "test-session-2"
        
        cancellation_tracker.mark_cancelled(session_id)
        assert cancellation_tracker.is_user_cancel(session_id) is True
        
        cancellation_tracker.clear(session_id)
        
        # After clear, session is no longer marked as user-cancelled (so it would be treated as timeout)
        assert cancellation_tracker.is_user_cancel(session_id) is False
    
    def test_clear_unknown_session_no_error(self):
        """Test that clearing an unknown session doesn't raise an error."""
        # Should not raise any exception
        cancellation_tracker.clear("unknown-session")
    
    def test_multiple_sessions(self):
        """Test tracking multiple sessions simultaneously."""
        cancellation_tracker.mark_cancelled("session-a")
        # session-b is NOT marked, so it should be treated as timeout
        
        assert cancellation_tracker.is_user_cancel("session-a") is True
        assert cancellation_tracker.is_user_cancel("session-b") is False  # Not marked = timeout
        
        cancellation_tracker.clear("session-a")
        
        assert cancellation_tracker.is_user_cancel("session-a") is False
    
    def test_idempotent_marking(self):
        """Test that marking the same session twice is fine."""
        session_id = "test-session-3"
        
        cancellation_tracker.mark_cancelled(session_id)
        cancellation_tracker.mark_cancelled(session_id)
        
        assert cancellation_tracker.is_user_cancel(session_id) is True
