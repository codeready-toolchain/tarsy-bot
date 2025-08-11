"""
Unit tests for DashboardConnectionManager.
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from tarsy.models.websocket_models import (
    ChannelType
)
from tarsy.services.dashboard_connection_manager import DashboardConnectionManager


@pytest.fixture
def connection_manager():
    """Create a DashboardConnectionManager instance for testing."""
    return DashboardConnectionManager()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


class TestDashboardConnectionManager:
    """Test basic DashboardConnectionManager functionality."""
    
    @pytest.mark.unit
    def test_initialization(self, connection_manager):
        """Test DashboardConnectionManager initialization."""
        assert isinstance(connection_manager.active_connections, dict)
        assert isinstance(connection_manager.user_subscriptions, dict)
        assert isinstance(connection_manager.channel_subscribers, dict)
        assert len(connection_manager.active_connections) == 0
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_connect_user(self, connection_manager, mock_websocket):
        """Test connecting a user WebSocket."""
        user_id = "test_user"
        
        await connection_manager.connect(mock_websocket, user_id)
        
        # Verify connection stored
        assert user_id in connection_manager.active_connections
        assert connection_manager.active_connections[user_id] == mock_websocket
        
        # Verify subscription tracking initialized
        assert user_id in connection_manager.user_subscriptions
        assert len(connection_manager.user_subscriptions[user_id]) == 0
        
        # Verify WebSocket was accepted
        mock_websocket.accept.assert_called_once()
    
    @pytest.mark.unit
    def test_disconnect_user(self, connection_manager, mock_websocket):
        """Test disconnecting a user."""
        user_id = "test_user"
        
        # Set up connection and subscriptions
        connection_manager.active_connections[user_id] = mock_websocket
        connection_manager.user_subscriptions[user_id] = {"dashboard_updates", "session_123"}
        connection_manager.channel_subscribers["dashboard_updates"] = {user_id}
        connection_manager.channel_subscribers["session_123"] = {user_id}
        
        # Disconnect user
        connection_manager.disconnect(user_id)
        
        # Verify cleanup
        assert user_id not in connection_manager.active_connections
        assert user_id not in connection_manager.user_subscriptions
        assert user_id not in connection_manager.channel_subscribers.get("dashboard_updates", set())
        assert user_id not in connection_manager.channel_subscribers.get("session_123", set())
    
    @pytest.mark.unit
    def test_disconnect_nonexistent_user(self, connection_manager):
        """Test disconnecting a user that doesn't exist."""
        # Should not raise exception
        connection_manager.disconnect("nonexistent_user")
    
    @pytest.mark.unit
    def test_subscribe_to_channel(self, connection_manager, mock_websocket):
        """Test subscribing user to a channel."""
        user_id = "test_user"
        channel = ChannelType.DASHBOARD_UPDATES
        
        # Set up connection
        connection_manager.active_connections[user_id] = mock_websocket
        
        success = connection_manager.subscribe_to_channel(user_id, channel)
        
        assert success is True
        assert channel in connection_manager.user_subscriptions[user_id]
        assert user_id in connection_manager.channel_subscribers[channel]
    
    @pytest.mark.unit
    def test_subscribe_inactive_user(self, connection_manager):
        """Test subscribing inactive user to channel."""
        user_id = "inactive_user"
        channel = ChannelType.DASHBOARD_UPDATES
        
        success = connection_manager.subscribe_to_channel(user_id, channel)
        
        assert success is False
        # User subscriptions entry is created but remains empty
        assert user_id in connection_manager.user_subscriptions
        assert len(connection_manager.user_subscriptions[user_id]) == 0
    
    @pytest.mark.unit
    def test_unsubscribe_from_channel(self, connection_manager, mock_websocket):
        """Test unsubscribing user from a channel."""
        user_id = "test_user"
        channel = ChannelType.SYSTEM_HEALTH
        
        # Set up subscription
        connection_manager.active_connections[user_id] = mock_websocket
        connection_manager.user_subscriptions[user_id] = {channel}
        connection_manager.channel_subscribers[channel] = {user_id}
        
        success = connection_manager.unsubscribe_from_channel(user_id, channel)
        
        assert success is True
        assert channel not in connection_manager.user_subscriptions[user_id]
        assert channel not in connection_manager.channel_subscribers  # Should be cleaned up
    

    @pytest.mark.unit
    def test_get_channel_subscribers(self, connection_manager):
        """Test getting channel subscribers."""
        channel = ChannelType.DASHBOARD_UPDATES
        users = {"user1", "user2", "user3"}
        
        connection_manager.channel_subscribers[channel] = users
        
        result = connection_manager.get_channel_subscribers(channel)
        
        assert result == users
        assert result is not connection_manager.channel_subscribers[channel]  # Should be copy
    
    @pytest.mark.unit
    def test_get_channel_subscribers_nonexistent(self, connection_manager):
        """Test getting subscribers for nonexistent channel."""
        result = connection_manager.get_channel_subscribers("nonexistent_channel")
        assert result == set()


class TestMessageSending:
    """Test message sending functionality."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_send_to_user_success(self, connection_manager, mock_websocket):
        """Test successfully sending message to user."""
        user_id = "test_user"
        message = {"type": "test", "data": "hello"}
        
        connection_manager.active_connections[user_id] = mock_websocket
        
        success = await connection_manager.send_to_user(user_id, message)
        
        assert success is True
        mock_websocket.send_text.assert_called_once()
        
        # Verify message was properly serialized
        call_args = mock_websocket.send_text.call_args[0][0]
        sent_data = json.loads(call_args)
        assert sent_data["type"] == "test"
        assert sent_data["data"] == "hello"
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_send_to_user_with_datetime(self, connection_manager, mock_websocket):
        """Test sending message with datetime serialization."""
        user_id = "test_user"
        test_time = datetime(2023, 1, 1, 12, 0, 0)
        message = {"type": "test", "timestamp": test_time}
        
        connection_manager.active_connections[user_id] = mock_websocket
        
        success = await connection_manager.send_to_user(user_id, message)
        
        assert success is True
        mock_websocket.send_text.assert_called_once()
        
        # Verify datetime was serialized
        call_args = mock_websocket.send_text.call_args[0][0]
        sent_data = json.loads(call_args)
        assert sent_data["timestamp"] == test_time.isoformat()
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_send_to_inactive_user(self, connection_manager):
        """Test sending message to inactive user."""
        user_id = "inactive_user"
        message = {"type": "test"}
        
        success = await connection_manager.send_to_user(user_id, message)
        
        assert success is False
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_send_to_user_websocket_error(self, connection_manager, mock_websocket):
        """Test handling WebSocket send error."""
        user_id = "test_user"
        message = {"type": "test"}
        
        # Mock WebSocket to raise exception
        mock_websocket.send_text.side_effect = Exception("Connection error")
        connection_manager.active_connections[user_id] = mock_websocket
        
        success = await connection_manager.send_to_user(user_id, message)
        
        assert success is False
        # User should be disconnected after error
        assert user_id not in connection_manager.active_connections
    




class TestSubscriptionMessageHandling:
    """Test subscription message handling."""
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_handle_valid_subscription(self, connection_manager, mock_websocket):
        """Test handling valid subscription message."""
        user_id = "test_user"
        message = {
            "type": "subscribe",
            "channel": ChannelType.DASHBOARD_UPDATES
        }
        
        connection_manager.active_connections[user_id] = mock_websocket
        
        await connection_manager.handle_subscription_message(user_id, message)
        
        # Verify response was sent to user
        mock_websocket.send_text.assert_called_once()
        sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_message["success"] is True
        assert sent_message["action"] == "subscribe"
        assert sent_message["channel"] == ChannelType.DASHBOARD_UPDATES
        
        # Verify user was subscribed
        assert ChannelType.DASHBOARD_UPDATES in connection_manager.user_subscriptions[user_id]
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_handle_valid_unsubscription(self, connection_manager, mock_websocket):
        """Test handling valid unsubscription message."""
        user_id = "test_user"
        channel = "session_123"
        message = {
            "type": "unsubscribe",
            "channel": channel
        }
        
        # Set up existing subscription
        connection_manager.active_connections[user_id] = mock_websocket
        connection_manager.user_subscriptions[user_id] = {channel}
        connection_manager.channel_subscribers[channel] = {user_id}
        
        await connection_manager.handle_subscription_message(user_id, message)
        
        # Verify response was sent to user
        mock_websocket.send_text.assert_called_once()
        sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_message["success"] is True
        assert sent_message["action"] == "unsubscribe"
        assert sent_message["channel"] == channel
        
        # Verify user was unsubscribed
        assert channel not in connection_manager.user_subscriptions[user_id]
        assert user_id not in connection_manager.channel_subscribers.get(channel, set())
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_handle_invalid_subscription_message(self, connection_manager, mock_websocket):
        """Test handling invalid subscription message format."""
        user_id = "test_user"
        invalid_message = {
            "type": "invalid_type",
            "channel": "test"
        }
        
        connection_manager.active_connections[user_id] = mock_websocket
        
        await connection_manager.handle_subscription_message(user_id, invalid_message)
        
        # Verify error response was sent
        mock_websocket.send_text.assert_called_once()
        
        # Verify error message content
        call_args = mock_websocket.send_text.call_args[0][0]
        response_data = json.loads(call_args)
        assert response_data["type"] == "error"
        assert "Invalid subscription message format" in response_data["message"]
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_handle_invalid_channel_subscription(self, connection_manager, mock_websocket):
        """Test handling subscription to invalid channel."""
        user_id = "test_user"
        message = {
            "type": "subscribe",
            "channel": "invalid_channel"
        }
        
        connection_manager.active_connections[user_id] = mock_websocket
        
        await connection_manager.handle_subscription_message(user_id, message)
        
        # Verify response was sent
        mock_websocket.send_text.assert_called_once()
        sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_message["success"] is False
        assert sent_message["action"] == "subscribe"
        assert sent_message["channel"] == "invalid_channel"
        assert "Unknown channel" in sent_message["message"]
        
        # Verify user was not subscribed (since it failed)
        user_subs = connection_manager.user_subscriptions.get(user_id, set())
        assert "invalid_channel" not in user_subs
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_handle_subscription_message_exception(self, connection_manager, mock_websocket):
        """Test handling unexpected exception in subscription processing."""
        user_id = "test_user"
        message = {
            "type": "subscribe",
            "channel": ChannelType.DASHBOARD_UPDATES
        }
        
        connection_manager.active_connections[user_id] = mock_websocket
        
        # Make WebSocket send_text raise an exception
        mock_websocket.send_text.side_effect = Exception("WebSocket error")
        
        # Should not raise an exception (should handle gracefully)
        await connection_manager.handle_subscription_message(user_id, message)
        
        # Verify send_text was attempted
        mock_websocket.send_text.assert_called_once()


class TestChannelValidation:
    """Test channel validation functionality."""
    
    @pytest.mark.unit
    def test_is_valid_channel_predefined_channels(self, connection_manager):
        """Test validation of predefined channels."""
        # Test dashboard updates channel
        assert connection_manager._is_valid_channel(ChannelType.DASHBOARD_UPDATES) is True
        
        # Test system health channel
        assert connection_manager._is_valid_channel(ChannelType.SYSTEM_HEALTH) is True
    
    @pytest.mark.unit
    def test_is_valid_channel_session_channels(self, connection_manager):
        """Test validation of session channels."""
        # Valid session channels
        assert connection_manager._is_valid_channel("session_123") is True
        assert connection_manager._is_valid_channel("session_abc_def") is True
        assert connection_manager._is_valid_channel("session_uuid-1234-5678") is True
        
        # Session channel with empty session ID should be invalid
        assert connection_manager._is_valid_channel("session_") is False
        
        # Just "session" without underscore should be invalid
        assert connection_manager._is_valid_channel("session") is False
    
    @pytest.mark.unit
    def test_is_valid_channel_invalid_channels(self, connection_manager):
        """Test validation of invalid channels."""
        # Completely invalid channels
        assert connection_manager._is_valid_channel("invalid_channel") is False
        assert connection_manager._is_valid_channel("random_text") is False
        assert connection_manager._is_valid_channel("") is False
        
        # Channels that look like session channels but aren't
        assert connection_manager._is_valid_channel("sessions_123") is False  # plural
        assert connection_manager._is_valid_channel("Session_123") is False   # uppercase
        assert connection_manager._is_valid_channel("_session_123") is False  # prefix
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_handle_system_health_subscription(self, connection_manager, mock_websocket):
        """Test handling subscription to system health channel."""
        user_id = "test_user"
        message = {
            "type": "subscribe",
            "channel": ChannelType.SYSTEM_HEALTH
        }
        
        connection_manager.active_connections[user_id] = mock_websocket
        
        await connection_manager.handle_subscription_message(user_id, message)
        
        # Verify successful response
        mock_websocket.send_text.assert_called_once()
        sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
        assert sent_message["success"] is True
        assert sent_message["action"] == "subscribe"
        assert sent_message["channel"] == ChannelType.SYSTEM_HEALTH
        
        # Verify user was subscribed
        assert ChannelType.SYSTEM_HEALTH in connection_manager.user_subscriptions[user_id]
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_handle_various_session_channel_subscriptions(self, connection_manager, mock_websocket):
        """Test handling subscriptions to various valid session channel formats."""
        user_id = "test_user"
        connection_manager.active_connections[user_id] = mock_websocket
        
        # Test different session channel formats
        test_channels = [
            "session_simple",
            "session_uuid-1234-5678-9abc",
            "session_with_underscores_and_numbers_123"
        ]
        
        for channel in test_channels:
            mock_websocket.reset_mock()
            
            message = {
                "type": "subscribe",
                "channel": channel
            }
            
            await connection_manager.handle_subscription_message(user_id, message)
            
            # Verify successful response
            mock_websocket.send_text.assert_called_once()
            sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
            assert sent_message["success"] is True, f"Failed for channel: {channel}"
            assert sent_message["channel"] == channel
            
            # Verify user was subscribed
            assert channel in connection_manager.user_subscriptions[user_id]
    
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_handle_malformed_session_channel_subscription(self, connection_manager, mock_websocket):
        """Test handling subscription to malformed session channels."""
        user_id = "test_user"
        connection_manager.active_connections[user_id] = mock_websocket
        
        # Test malformed session channels
        malformed_channels = [
            "session_",      # Empty session ID
            "sessions_123",  # Plural form
            "Session_123"    # Wrong case
        ]
        
        for channel in malformed_channels:
            mock_websocket.reset_mock()
            
            message = {
                "type": "subscribe", 
                "channel": channel
            }
            
            await connection_manager.handle_subscription_message(user_id, message)
            
            # Verify error response
            mock_websocket.send_text.assert_called_once()
            sent_message = json.loads(mock_websocket.send_text.call_args[0][0])
            assert sent_message["success"] is False, f"Should have failed for channel: {channel}"
            assert sent_message["channel"] == channel
            assert "Unknown channel" in sent_message["message"]
            
            # Verify user was not subscribed
            user_subs = connection_manager.user_subscriptions.get(user_id, set())
            assert channel not in user_subs


if __name__ == "__main__":
    pytest.main([__file__]) 