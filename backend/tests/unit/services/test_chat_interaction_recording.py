"""
Unit tests for chat interaction recording during message processing.

Tests the background task that keeps both session and chat timestamps
fresh during long-running chat message processing.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch

from tarsy.services.chat_service import ChatService


@pytest.mark.unit
class TestChatInteractionRecording:
    """Test chat interaction recording functionality."""
    
    @pytest.fixture
    def mock_history_service(self):
        """Mock history service with interaction recording methods."""
        mock = Mock()
        mock.record_session_interaction = AsyncMock()
        mock.record_chat_interaction = AsyncMock()
        return mock
    
    @pytest.fixture
    def chat_service(self, mock_history_service):
        """Create ChatService with mocked history service."""
        return ChatService(
            history_service=mock_history_service,
            agent_factory=Mock(),
            mcp_client_factory=AsyncMock()
        )
    
    @pytest.mark.asyncio
    async def test_interaction_recording_task_records_both(
        self, chat_service, mock_history_service
    ):
        """Test interaction recording updates both session and chat timestamps."""
        # Mock asyncio.sleep in the chat_service module to make it instant
        original_sleep = asyncio.sleep
        
        async def instant_sleep(delay):
            """Sleep instantly instead of the requested delay."""
            await original_sleep(0.01)  # Very short delay to yield control
        
        with patch("tarsy.services.chat_service.asyncio.sleep", side_effect=instant_sleep):
            task = await chat_service._start_interaction_recording_task(
                chat_id="chat-123",
                session_id="session-456"
            )
            
            try:
                # Give task a moment to execute several cycles
                await original_sleep(0.1)
                
                # Verify both recording methods were called
                assert mock_history_service.record_session_interaction.call_count >= 1
                assert mock_history_service.record_chat_interaction.call_count >= 1
                
                # Verify correct IDs were used
                mock_history_service.record_session_interaction.assert_called_with("session-456")
                mock_history_service.record_chat_interaction.assert_called_with("chat-123")
            
            finally:
                # Clean up task
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    @pytest.mark.asyncio
    async def test_interaction_recording_task_handles_errors(
        self, chat_service, mock_history_service
    ):
        """Test interaction recording continues after errors."""
        # Make first call fail, subsequent calls succeed
        mock_history_service.record_chat_interaction.side_effect = [
            Exception("Database error"),
            None,
            None
        ]
        
        # Mock asyncio.sleep in the chat_service module to make it instant
        original_sleep = asyncio.sleep
        
        async def instant_sleep(delay):
            """Sleep instantly instead of the requested delay."""
            await original_sleep(0.01)  # Very short delay to yield control
        
        with patch("tarsy.services.chat_service.asyncio.sleep", side_effect=instant_sleep):
            task = await chat_service._start_interaction_recording_task(
                chat_id="chat-123",
                session_id="session-456"
            )
            
            try:
                # Wait for multiple cycles
                await original_sleep(0.1)
                
                # Task should continue despite error
                assert mock_history_service.record_chat_interaction.call_count >= 2
            
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    @pytest.mark.asyncio
    async def test_interaction_recording_task_cancellation(
        self, chat_service, mock_history_service
    ):
        """Test interaction recording task can be cancelled cleanly."""
        task = await chat_service._start_interaction_recording_task(
            chat_id="chat-123",
            session_id="session-456"
        )
        
        # Cancel immediately
        task.cancel()
        
        # Should complete without hanging
        with pytest.raises(asyncio.CancelledError):
            await task
        
        # Task is done after cancellation
        assert task.done()

