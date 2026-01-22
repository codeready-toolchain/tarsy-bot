"""
Unit tests for the CancellationTracker.
"""

import asyncio

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
    
    @pytest.mark.asyncio
    async def test_concurrent_marking_same_session(self):
        """Test that concurrent marking of the same session is thread-safe."""
        session_id = "concurrent-session"
        
        def mark_session():
            cancellation_tracker.mark_cancelled(session_id)
            return cancellation_tracker.is_user_cancel(session_id)
        
        # Run 50 concurrent operations on the same session
        results = await asyncio.gather(*[
            asyncio.to_thread(mark_session) for _ in range(50)
        ])
        
        # All should succeed and session should be marked
        assert all(results), "All concurrent marks should succeed"
        assert cancellation_tracker.is_user_cancel(session_id) is True
    
    @pytest.mark.asyncio
    async def test_concurrent_marking_different_sessions(self):
        """Test that concurrent marking of different sessions is thread-safe."""
        
        def mark_and_check(session_id: str):
            cancellation_tracker.mark_cancelled(session_id)
            return cancellation_tracker.is_user_cancel(session_id)
        
        # Mark 100 different sessions concurrently
        results = await asyncio.gather(*[
            asyncio.to_thread(mark_and_check, f"session-{i}") 
            for i in range(100)
        ])
        
        # All should be marked successfully
        assert all(results), "All concurrent marks should succeed"
        
        # Verify all sessions are still marked after concurrent access
        for i in range(100):
            assert cancellation_tracker.is_user_cancel(f"session-{i}") is True
    
    @pytest.mark.asyncio
    async def test_concurrent_mixed_operations(self):
        """Test concurrent mix of mark, check, and clear operations."""
        session_ids = [f"mixed-session-{i}" for i in range(10)]
        
        # Pre-mark half of them
        for i in range(5):
            cancellation_tracker.mark_cancelled(session_ids[i])
        
        def mark_op(session_id: str):
            cancellation_tracker.mark_cancelled(session_id)
        
        def check_op(session_id: str):
            return cancellation_tracker.is_user_cancel(session_id)
        
        def clear_op(session_id: str):
            cancellation_tracker.clear(session_id)
        
        # Create a mix of operations running concurrently
        operations = []
        for session_id in session_ids:
            operations.extend([
                asyncio.to_thread(mark_op, session_id),
                asyncio.to_thread(check_op, session_id),
                asyncio.to_thread(clear_op, session_id),
                asyncio.to_thread(mark_op, session_id),
                asyncio.to_thread(check_op, session_id),
            ])
        
        # Run all operations concurrently (should not corrupt state or crash)
        # The main goal is to verify no race conditions cause crashes or data corruption
        await asyncio.gather(*operations)
        
        # After concurrent operations, the final state is non-deterministic due to race conditions
        # but the tracker should still be in a valid state (no corruption)
        # We just verify that we can still interact with it safely
        for session_id in session_ids:
            # These operations should complete without error
            cancellation_tracker.mark_cancelled(session_id)
            assert cancellation_tracker.is_user_cancel(session_id) is True
            cancellation_tracker.clear(session_id)
            assert cancellation_tracker.is_user_cancel(session_id) is False