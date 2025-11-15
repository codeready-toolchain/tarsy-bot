"""
Unit tests for pause/resume event publishing.

Tests that session.paused and session.resumed events are correctly published.
"""

import pytest
from unittest.mock import AsyncMock, patch

from tarsy.services.events.event_helpers import (
    publish_session_paused,
    publish_session_resumed
)
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.event_models import SessionPausedEvent, SessionResumedEvent
from tarsy.models.pause_metadata import PauseReason


class TestPauseResumeEvents:
    """Test suite for pause/resume event publishing."""
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_publish_session_paused_without_metadata(self) -> None:
        """Test publishing session.paused event without metadata."""
        session_id = "test-session-123"
        
        with patch('tarsy.services.events.event_helpers.get_async_session_factory') as mock_factory, \
             patch('tarsy.services.events.event_helpers.publish_event', new_callable=AsyncMock) as mock_publish:
            
            # Setup mock session factory - factory() returns async context manager
            mock_session = AsyncMock()
            mock_context_manager = AsyncMock()
            mock_context_manager.__aenter__.return_value = mock_session
            mock_context_manager.__aexit__.return_value = None
            mock_factory.return_value = lambda: mock_context_manager
            
            # Call the function
            await publish_session_paused(session_id)
            
            # Verify publish_event was called twice (global + session-specific)
            assert mock_publish.call_count == 2
            
            # Verify first call (global channel)
            first_call = mock_publish.call_args_list[0]
            assert first_call[0][1] == "sessions"
            event = first_call[0][2]
            assert isinstance(event, SessionPausedEvent)
            assert event.session_id == session_id
            assert event.status == AlertSessionStatus.PAUSED.value
            assert event.pause_metadata is None
            
            # Verify second call (session-specific channel)
            second_call = mock_publish.call_args_list[1]
            assert second_call[0][1] == f"session:{session_id}"
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_publish_session_paused_with_metadata(self) -> None:
        """Test publishing session.paused event with metadata."""
        session_id = "test-session-456"
        pause_metadata = {
            "reason": PauseReason.MAX_ITERATIONS_REACHED.value,
            "iteration": 30,
            "stage_id": "initial-analysis"
        }
        
        with patch('tarsy.services.events.event_helpers.get_async_session_factory') as mock_factory, \
             patch('tarsy.services.events.event_helpers.publish_event', new_callable=AsyncMock) as mock_publish:
            
            # Setup mock session factory - factory() returns async context manager
            mock_session = AsyncMock()
            mock_context_manager = AsyncMock()
            mock_context_manager.__aenter__.return_value = mock_session
            mock_context_manager.__aexit__.return_value = None
            mock_factory.return_value = lambda: mock_context_manager
            
            # Call the function
            await publish_session_paused(session_id, pause_metadata)
            
            # Verify publish_event was called twice (global + session-specific)
            assert mock_publish.call_count == 2
            
            # Verify first call (global channel) - event contains metadata
            first_call = mock_publish.call_args_list[0]
            event = first_call[0][2]
            assert isinstance(event, SessionPausedEvent)
            assert event.pause_metadata == pause_metadata
            
            # Verify second call (session-specific channel) - same event type
            second_call = mock_publish.call_args_list[1]
            assert second_call[0][1] == f"session:{session_id}"
            second_event = second_call[0][2]
            assert isinstance(second_event, SessionPausedEvent)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_publish_session_paused_handles_errors_gracefully(self) -> None:
        """Test that publish_session_paused handles errors without raising."""
        session_id = "test-session-error"
        
        with patch('tarsy.services.events.event_helpers.get_async_session_factory') as mock_factory:
            # Simulate an error
            mock_factory.side_effect = Exception("Database connection failed")
            
            # Should not raise exception
            await publish_session_paused(session_id)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_publish_session_resumed(self) -> None:
        """Test publishing session.resumed event."""
        session_id = "test-session-789"
        
        with patch('tarsy.services.events.event_helpers.get_async_session_factory') as mock_factory, \
             patch('tarsy.services.events.event_helpers.publish_event', new_callable=AsyncMock) as mock_publish:
            
            # Setup mock session factory - factory() returns async context manager
            mock_session = AsyncMock()
            mock_context_manager = AsyncMock()
            mock_context_manager.__aenter__.return_value = mock_session
            mock_context_manager.__aexit__.return_value = None
            mock_factory.return_value = lambda: mock_context_manager
            
            # Call the function
            await publish_session_resumed(session_id)
            
            # Verify publish_event was called twice (global + session-specific)
            assert mock_publish.call_count == 2
            
            # Verify first call (global channel)
            first_call = mock_publish.call_args_list[0]
            assert first_call[0][1] == "sessions"
            event = first_call[0][2]
            assert isinstance(event, SessionResumedEvent)
            assert event.session_id == session_id
            assert event.status == AlertSessionStatus.IN_PROGRESS.value
            
            # Verify second call (session-specific channel) - same event type
            second_call = mock_publish.call_args_list[1]
            assert second_call[0][1] == f"session:{session_id}"
            second_event = second_call[0][2]
            assert isinstance(second_event, SessionResumedEvent)
    
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_publish_session_resumed_handles_errors_gracefully(self) -> None:
        """Test that publish_session_resumed handles errors without raising."""
        session_id = "test-session-error-resume"
        
        with patch('tarsy.services.events.event_helpers.get_async_session_factory') as mock_factory:
            # Simulate an error
            mock_factory.side_effect = Exception("Database connection failed")
            
            # Should not raise exception
            await publish_session_resumed(session_id)

