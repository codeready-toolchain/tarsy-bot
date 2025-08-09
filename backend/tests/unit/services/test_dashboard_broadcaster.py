"""
Test dashboard broadcaster with simplified immediate-only broadcasting.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

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