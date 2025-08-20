"""
Unit tests for DashboardConnectionManager.
"""

import json
from datetime import datetime

import pytest

from tarsy.models.websocket_models import ChannelType
from tarsy.services.dashboard_connection_manager import DashboardConnectionManager
from tests.utils import DashboardConnectionFactory, TestUtils


@pytest.fixture
def connection_manager():
    """Create a DashboardConnectionManager instance for testing."""
    return DashboardConnectionManager()


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket connection."""
    return TestUtils.create_mock_websocket()


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

    @pytest.mark.parametrize("user_id,has_subscriptions,expected_cleanup", [
        ("test_user", True, True),  # User with subscriptions
        ("nonexistent_user", False, False),  # User that doesn't exist
    ])
    @pytest.mark.unit
    def test_disconnect_scenarios(self, connection_manager, mock_websocket, user_id, has_subscriptions, expected_cleanup):
        """Test disconnecting users for various scenarios."""
        if has_subscriptions:
            # Set up connection and subscriptions
            subscription_data = DashboardConnectionFactory.create_subscription_data(user_id=user_id)
            connection_manager.active_connections[user_id] = mock_websocket
            connection_manager.user_subscriptions[user_id] = subscription_data["subscriptions"]
            connection_manager.channel_subscribers["dashboard_updates"] = {user_id}
            connection_manager.channel_subscribers["session_123"] = {user_id}
        
        # Disconnect user
        connection_manager.disconnect(user_id)
        
        if expected_cleanup:
            # Verify cleanup
            assert user_id not in connection_manager.active_connections
            assert user_id not in connection_manager.user_subscriptions
            assert user_id not in connection_manager.channel_subscribers.get("dashboard_updates", set())
            assert user_id not in connection_manager.channel_subscribers.get("session_123", set())
        else:
            # Verify no changes for nonexistent user
            assert len(connection_manager.active_connections) == 0
            assert len(connection_manager.user_subscriptions) == 0
    
    @pytest.mark.parametrize("user_id,channel,is_active,expected_success", [
        ("test_user", ChannelType.DASHBOARD_UPDATES, True, True),  # Active user subscription
        ("inactive_user", ChannelType.DASHBOARD_UPDATES, False, False),  # Inactive user subscription
    ])
    @pytest.mark.unit
    def test_subscribe_scenarios(self, connection_manager, mock_websocket, user_id, channel, is_active, expected_success):
        """Test subscribing users to channels for various scenarios."""
        if is_active:
            # Set up connection
            connection_manager.active_connections[user_id] = mock_websocket
        
        success = connection_manager.subscribe_to_channel(user_id, channel)
        
        assert success is expected_success
        if expected_success:
            assert channel in connection_manager.user_subscriptions[user_id]
            assert user_id in connection_manager.channel_subscribers[channel]
        else:
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
    

    @pytest.mark.parametrize("channel,subscribers,expected_result", [
        (ChannelType.DASHBOARD_UPDATES, DashboardConnectionFactory.create_channel_subscribers()[ChannelType.DASHBOARD_UPDATES], {"user1", "user2", "user3"}),
        ("nonexistent_channel", None, set()),
    ])
    @pytest.mark.unit
    def test_get_channel_subscribers_scenarios(self, connection_manager, channel, subscribers, expected_result):
        """Test getting channel subscribers for various scenarios."""
        if subscribers is not None:
            connection_manager.channel_subscribers[channel] = subscribers
        
        result = connection_manager.get_channel_subscribers(channel)
        
        assert result == expected_result
        if subscribers is not None:
            assert result is not connection_manager.channel_subscribers[channel]  # Should be copy


class TestMessageSending:
    """Test message sending functionality."""
    
    @pytest.mark.parametrize("user_id,message,is_active,has_error,expected_success", [
        ("test_user", DashboardConnectionFactory.create_test_message(), True, False, True),  # Successful send
        ("test_user", DashboardConnectionFactory.create_test_message(type="test", timestamp=datetime(2023, 1, 1, 12, 0, 0)), True, False, True),  # With datetime
        ("inactive_user", DashboardConnectionFactory.create_test_message(type="test", data=None, timestamp=None), False, False, False),  # Inactive user
        ("test_user", DashboardConnectionFactory.create_test_message(type="test", data=None, timestamp=None), True, True, False),  # WebSocket error
    ])
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_send_to_user_scenarios(self, connection_manager, mock_websocket, user_id, message, is_active, has_error, expected_success):
        """Test sending messages to users for various scenarios."""
        if is_active:
            connection_manager.active_connections[user_id] = mock_websocket
            if has_error:
                # Mock WebSocket to raise exception
                mock_websocket.send_text.side_effect = Exception("Connection error")
        
        success = await connection_manager.send_to_user(user_id, message)
        
        assert success is expected_success
        
        if expected_success:
            mock_websocket.send_text.assert_called_once()
            
            # Verify message was properly serialized
            call_args = mock_websocket.send_text.call_args[0][0]
            sent_data = json.loads(call_args)
            
            # Check basic message structure
            assert sent_data["type"] == message["type"]
            
            # Check for datetime serialization
            if "timestamp" in message:
                assert sent_data["timestamp"] == message["timestamp"].isoformat()
            elif "data" in message:
                assert sent_data["data"] == message["data"]
        elif has_error:
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