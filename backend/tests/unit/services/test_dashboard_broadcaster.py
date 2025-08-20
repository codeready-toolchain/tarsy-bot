"""
Test dashboard broadcaster with simplified immediate-only broadcasting.
"""

from collections import deque
from unittest.mock import AsyncMock, MagicMock

import pytest

from tarsy.models.websocket_models import (
    ChannelType,
    DashboardUpdate,
    SessionUpdate,
)
from tarsy.services.dashboard_broadcaster import DashboardBroadcaster


class TestDashboardBroadcaster:
    """Test DashboardBroadcaster functionality."""
    
    @pytest.fixture
    def mock_connection_manager(self):
        """Mock connection manager."""
        manager = MagicMock()
        manager.get_channel_subscribers = MagicMock(return_value={"user1", "user2", "user3"})
        manager.send_to_user = AsyncMock(return_value=True)
        return manager
    
    @pytest.fixture 
    def broadcaster(self, mock_connection_manager):
        """Create broadcaster instance."""
        return DashboardBroadcaster(mock_connection_manager)
    
    @pytest.mark.unit
    def test_initialization(self, broadcaster, mock_connection_manager):
        """Test broadcaster initialization."""
        assert broadcaster.connection_manager == mock_connection_manager
        assert isinstance(broadcaster.throttle_limits, dict)
        assert isinstance(broadcaster.user_message_counts, dict)
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_broadcast_message_basic(self, broadcaster, mock_connection_manager):
        """Test basic message broadcasting."""
        message = DashboardUpdate(data={"test": "data"})
        channel = ChannelType.DASHBOARD_UPDATES
        
        sent_count = await broadcaster.broadcast_message(channel, message)
        
        assert sent_count == 3  # Should send to all 3 users
        assert mock_connection_manager.send_to_user.call_count == 3
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_broadcast_message_with_exclusions(self, broadcaster, mock_connection_manager):
        """Test broadcasting with user exclusions."""
        message = SessionUpdate(session_id="123", data={"status": "active"})
        channel = ChannelType.session_channel("123")
        exclude_users = {"user1"}
        
        sent_count = await broadcaster.broadcast_message(channel, message, exclude_users)
        
        assert sent_count == 2  # Should send to 2 users (excluding user1)
        assert mock_connection_manager.send_to_user.call_count == 2
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_broadcast_dashboard_update(self, broadcaster, mock_connection_manager):
        """Test broadcasting dashboard update."""
        data = {"sessions": 5, "active_alerts": 2}
        
        sent_count = await broadcaster.broadcast_dashboard_update(data)
        
        assert sent_count == 3
        mock_connection_manager.send_to_user.assert_called()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_broadcast_session_update(self, broadcaster, mock_connection_manager):
        """Test broadcasting session update."""
        session_id = "session_123"
        data = {"status": "processing", "progress": 50}
        
        sent_count = await broadcaster.broadcast_session_update(session_id, data)
        
        assert sent_count == 3
        mock_connection_manager.send_to_user.assert_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_broadcast_interaction_update(self, broadcaster, mock_connection_manager):
        """Test broadcasting interaction update."""
        session_id = "session_123"
        interaction_data = {"type": "llm", "message": "Processing..."}
        
        # Reset call count since it might be affected by buffering behavior
        mock_connection_manager.send_to_user.reset_mock()
        
        sent_count = await broadcaster.broadcast_interaction_update(session_id, interaction_data)
        
        # Interaction updates might be sent to both session channel and dashboard
        # so the count might be higher than 3
        assert sent_count >= 3
        mock_connection_manager.send_to_user.assert_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_broadcast_message_no_subscribers(self, broadcaster, mock_connection_manager):
        """Test broadcasting when no subscribers exist."""
        mock_connection_manager.get_channel_subscribers.return_value = set()
        
        message = DashboardUpdate(data={"test": "data"})
        channel = ChannelType.DASHBOARD_UPDATES
        
        sent_count = await broadcaster.broadcast_message(channel, message)
        
        assert sent_count == 0
        mock_connection_manager.send_to_user.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_broadcast_message_send_failure(self, broadcaster, mock_connection_manager):
        """Test broadcasting when send_to_user fails."""
        mock_connection_manager.send_to_user.return_value = False
        
        message = DashboardUpdate(data={"test": "data"})
        channel = ChannelType.DASHBOARD_UPDATES
        
        sent_count = await broadcaster.broadcast_message(channel, message)
        
        assert sent_count == 0  # No successful sends
        assert mock_connection_manager.send_to_user.call_count == 3

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_session_message_buffering(self, broadcaster, mock_connection_manager):
        """Test session message buffering functionality."""
        session_id = "test_session"
        channel = ChannelType.session_channel(session_id)
        
        # First broadcast with no subscribers should buffer
        mock_connection_manager.get_channel_subscribers.return_value = set()
        message = SessionUpdate(session_id=session_id, data={"status": "starting"})
        
        sent_count = await broadcaster.broadcast_message(channel, message)
        assert sent_count == 0
        
        # Check message was added to buffer
        assert channel in broadcaster.session_message_buffer
        assert len(broadcaster.session_message_buffer[channel]) == 1

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_session_buffer_flush_on_first_subscriber(self, broadcaster, mock_connection_manager):
        """Test that buffered messages are flushed when first subscriber connects."""
        session_id = "test_session"
        channel = ChannelType.session_channel(session_id)
        
        # Add a message to buffer (no subscribers)
        mock_connection_manager.get_channel_subscribers.return_value = set()
        buffered_message = SessionUpdate(session_id=session_id, data={"status": "buffered"})
        await broadcaster.broadcast_message(channel, buffered_message)
        
        # Now add subscribers and send another message
        mock_connection_manager.get_channel_subscribers.return_value = {"user1"}
        new_message = SessionUpdate(session_id=session_id, data={"status": "live"})
        
        sent_count = await broadcaster.broadcast_message(channel, new_message)
        
        # Should send buffered message + new message
        assert sent_count == 2  # 2 messages sent to 1 user
        assert mock_connection_manager.send_to_user.call_count == 2
        
        # Buffer should be cleared
        assert len(broadcaster.session_message_buffer.get(channel, [])) == 0

    @pytest.mark.unit
    def test_throttling_initialization(self, broadcaster):
        """Test throttling state initialization."""
        user_id = "test_user"
        channel = "test_channel"
        
        # First call should not throttle
        should_throttle = broadcaster._should_throttle_user(user_id, channel)
        assert should_throttle is False

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_cleanup_task_management(self, broadcaster):
        """Test cleanup task start/stop."""
        # Start cleanup task (need event loop)
        broadcaster.start_cleanup_task()
        assert broadcaster._cleanup_task is not None
        
        # Stop cleanup task
        broadcaster.stop_cleanup_task()
        # Task should be cancelled (can't easily test without actual task execution)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_cleanup_expired_messages(self, broadcaster):
        """Test cleanup of expired buffered messages."""
        from datetime import datetime, timedelta

        # Add some messages to buffer (use session channel format)
        from tarsy.models.websocket_models import ChannelType
        from tarsy.services.dashboard_broadcaster import TimestampedMessage
        channel = ChannelType.session_channel("test_session")
        
        # Add expired message (TTL is 300 seconds)
        expired_time = datetime.now() - timedelta(seconds=400)  # Much older than TTL
        expired_msg = TimestampedMessage({"data": "expired"}, expired_time)
        
        # Add fresh message
        fresh_time = datetime.now()
        fresh_msg = TimestampedMessage({"data": "fresh"}, fresh_time)
        
        broadcaster.session_message_buffer[channel] = deque([expired_msg, fresh_msg])
        
        await broadcaster._cleanup_expired_messages()
        
        # Only fresh message should remain
        remaining = broadcaster.session_message_buffer[channel]
        assert len(remaining) == 1
        assert remaining[0].message["data"] == "fresh"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_buffer_size_limit(self, broadcaster):
        """Test that buffer respects size limits."""
        from tarsy.services.dashboard_broadcaster import MAX_MESSAGES_PER_SESSION
        
        channel = "test_channel"
        
        # Add more messages than the limit
        for i in range(MAX_MESSAGES_PER_SESSION + 5):
            message_data = {"index": i}
            await broadcaster._add_message_to_buffer(channel, message_data)
        
        # Buffer should be limited to MAX_MESSAGES_PER_SESSION
        buffer = broadcaster.session_message_buffer[channel]
        assert len(buffer) == MAX_MESSAGES_PER_SESSION
        
        # Should contain the most recent messages
        assert buffer[-1].message["index"] == MAX_MESSAGES_PER_SESSION + 4