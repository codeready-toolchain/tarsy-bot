"""
Unit tests for WebSocket models.

Tests the Pydantic models used for WebSocket communications,
including message validation, serialization, and type handling.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

import pytest
from pydantic import ValidationError

from tarsy.models.websocket_models import (
    ChannelType,
    ConnectionEstablished,
    DashboardUpdate,
    ErrorMessage,
    SessionUpdate,
    SubscriptionMessage,
    SubscriptionResponse,
    SystemHealthUpdate,
    WebSocketMessage,
)


class TestWebSocketMessage:
    """Test suite for WebSocketMessage base class."""
    
    @pytest.mark.unit
    def test_basic_creation(self):
        """Test basic WebSocket message creation with automatic timestamp."""
        message = WebSocketMessage(type="test")
        assert message.type == "test"
        assert isinstance(message.timestamp_us, int)
        assert message.timestamp_us > 0
    
    @pytest.mark.unit
    def test_custom_timestamp(self):
        """Test WebSocket message with custom unix timestamp."""
        custom_timestamp_us = 1734567890123456  # Example unix timestamp in microseconds
        message = WebSocketMessage(type="test", timestamp_us=custom_timestamp_us)
        assert message.timestamp_us == custom_timestamp_us
    
    @pytest.mark.unit
    def test_serialization(self):
        """Test WebSocket message serialization."""
        message = WebSocketMessage(type="test")
        data = message.model_dump()
        
        assert data["type"] == "test"
        assert "timestamp_us" in data
        assert isinstance(data["timestamp_us"], int)


class TestSubscriptionMessage:
    """Test subscription message model."""
    
    @pytest.mark.unit
    def test_subscribe_message(self):
        """Test subscribe message creation."""
        message = SubscriptionMessage(type="subscribe", channel="dashboard_updates")
        assert message.type == "subscribe"
        assert message.channel == "dashboard_updates"
    
    @pytest.mark.unit
    def test_unsubscribe_message(self):
        """Test unsubscribe message creation."""
        message = SubscriptionMessage(type="unsubscribe", channel="session_123")
        assert message.type == "unsubscribe"
        assert message.channel == "session_123"
    
    @pytest.mark.unit
    def test_invalid_type(self):
        """Test subscription message with invalid type."""
        with pytest.raises(ValidationError):
            SubscriptionMessage(type="invalid", channel="test")
    
    @pytest.mark.unit
    def test_missing_channel(self):
        """Test subscription message without channel."""
        with pytest.raises(ValidationError):
            SubscriptionMessage(type="subscribe")
    
    @pytest.mark.unit
    def test_serialization(self):
        """Test subscription message serialization."""
        message = SubscriptionMessage(type="subscribe", channel="test")
        data = message.model_dump()
        
        assert data["type"] == "subscribe"
        assert data["channel"] == "test"


class TestSubscriptionResponse:
    """Test subscription response model."""
    
    @pytest.mark.unit
    def test_successful_response(self):
        """Test successful subscription response."""
        response = SubscriptionResponse(
            action="subscribe",
            channel="dashboard_updates",
            success=True,
            message="Successfully subscribed"
        )
        
        assert response.type == "subscription_response"
        assert response.action == "subscribe"
        assert response.channel == "dashboard_updates"
        assert response.success is True
        assert response.message == "Successfully subscribed"
    
    @pytest.mark.unit
    def test_failed_response(self):
        """Test failed subscription response."""
        response = SubscriptionResponse(
            action="subscribe",
            channel="invalid_channel",
            success=False,
            message="Channel not found"
        )
        
        assert response.success is False
        assert response.message == "Channel not found"
    
    @pytest.mark.unit
    def test_without_message(self):
        """Test subscription response without message."""
        response = SubscriptionResponse(
            action="unsubscribe",
            channel="test",
            success=True
        )
        
        assert response.message is None


class TestConnectionEstablished:
    """Test connection established message."""
    
    @pytest.mark.unit
    def test_creation(self):
        """Test connection established message creation."""
        message = ConnectionEstablished(user_id="test_user")
        assert message.type == "connection_established"
        assert message.user_id == "test_user"
    
    @pytest.mark.unit
    def test_serialization(self):
        """Test connection established serialization."""
        message = ConnectionEstablished(user_id="test_user")
        data = message.model_dump()
        
        assert data["type"] == "connection_established"
        assert data["user_id"] == "test_user"


class TestErrorMessage:
    """Test error message model."""
    
    @pytest.mark.unit
    def test_basic_error(self):
        """Test basic error message."""
        error = ErrorMessage(message="Something went wrong")
        assert error.type == "error"
        assert error.message == "Something went wrong"
        assert error.code is None
    
    @pytest.mark.unit
    def test_error_with_code(self):
        """Test error message with code."""
        error = ErrorMessage(message="Invalid channel", code="INVALID_CHANNEL")
        assert error.message == "Invalid channel"
        assert error.code == "INVALID_CHANNEL"


class TestDashboardUpdate:
    """Test dashboard update message."""
    
    @pytest.mark.unit
    def test_creation(self):
        """Test dashboard update creation."""
        data = {"key": "value", "number": 42}
        update = DashboardUpdate(data=data)
        
        assert update.type == "dashboard_update"
        assert update.data == data
        assert update.channel == "dashboard_updates"
    
    @pytest.mark.unit
    def test_complex_data(self):
        """Test dashboard update with complex data."""
        data = {
            "session_id": "123",
            "status": "processing",
            "interactions": [
                {"type": "llm", "duration": 1500},
                {"type": "mcp", "tool": "kubectl"}
            ]
        }
        update = DashboardUpdate(data=data)
        assert update.data == data


class TestSessionUpdate:
    """Test session update message."""
    
    @pytest.mark.unit
    def test_creation(self):
        """Test session update creation."""
        data = {"step": "analysis", "progress": 50}
        update = SessionUpdate(session_id="session_123", data=data)
        
        assert update.type == "session_update"
        assert update.session_id == "session_123"
        assert update.data == data
        assert update.channel is None  # Will be set by broadcaster
    
    @pytest.mark.unit
    def test_with_channel(self):
        """Test session update with explicit channel."""
        update = SessionUpdate(
            session_id="session_123",
            data={"test": "data"},
            channel="custom_channel"
        )
        assert update.channel == "custom_channel"


class TestSystemHealthUpdate:
    """Test system health update message."""
    
    @pytest.mark.unit
    def test_healthy_status(self):
        """Test healthy system status."""
        services = {"database": "healthy", "llm": "healthy"}
        update = SystemHealthUpdate(status="healthy", services=services)
        
        assert update.type == "system_health"
        assert update.status == "healthy"
        assert update.services == services
        assert update.channel == "system_health"
    
    @pytest.mark.unit
    def test_degraded_status(self):
        """Test degraded system status."""
        services = {"database": "healthy", "llm": "degraded"}
        update = SystemHealthUpdate(status="degraded", services=services)
        assert update.status == "degraded"
    
    @pytest.mark.unit
    def test_invalid_status(self):
        """Test invalid system status."""
        with pytest.raises(ValidationError):
            SystemHealthUpdate(status="invalid", services={})



class TestChannelType:
    """Test channel type utilities."""
    
    @pytest.mark.unit
    def test_constants(self):
        """Test channel type constants."""
        assert ChannelType.DASHBOARD_UPDATES == "dashboard_updates"
        assert ChannelType.SYSTEM_HEALTH == "system_health"
    
    @pytest.mark.unit
    def test_session_channel_generation(self):
        """Test session channel name generation."""
        channel = ChannelType.session_channel("123")
        assert channel == "session_123"
    
    @pytest.mark.unit
    def test_is_session_channel(self):
        """Test session channel detection."""
        assert ChannelType.is_session_channel("session_123") is True
        assert ChannelType.is_session_channel("dashboard_updates") is False
        assert ChannelType.is_session_channel("system_health") is False
        assert ChannelType.is_session_channel("session_") is True
        assert ChannelType.is_session_channel("") is False
    
    @pytest.mark.unit
    def test_extract_session_id(self):
        """Test session ID extraction from channel name."""
        assert ChannelType.extract_session_id("session_123") == "123"
        assert ChannelType.extract_session_id("session_abc_def") == "abc_def"
        assert ChannelType.extract_session_id("session_") == ""
        assert ChannelType.extract_session_id("dashboard_updates") is None
        assert ChannelType.extract_session_id("") is None


class TestMessageUnions:
    """Test message union types."""
    
    @pytest.mark.unit
    def test_incoming_message_types(self):
        """Test that incoming message types are properly validated."""
        # SubscriptionMessage should be valid IncomingMessage
        sub_msg = SubscriptionMessage(type="subscribe", channel="test")
        assert isinstance(sub_msg, SubscriptionMessage)
        
        # Other message types should not be in IncomingMessage union
        # (This is more of a type checking test, but we can verify structure)
        assert hasattr(sub_msg, 'type')
        assert hasattr(sub_msg, 'channel')
    
    @pytest.mark.unit
    def test_outgoing_message_types(self):
        """Test that outgoing message types are properly structured."""
        # Test each type of outgoing message
        messages = [
            SubscriptionResponse(action="subscribe", channel="test", success=True),
            ConnectionEstablished(user_id="test"),
            ErrorMessage(message="test error"),
            DashboardUpdate(data={"test": "data"})
        ]
        
        for msg in messages:
            assert hasattr(msg, 'type')
            assert hasattr(msg, 'timestamp_us')
            # Verify serialization works
            data = msg.model_dump()
            assert isinstance(data, dict)
            assert 'type' in data


class TestMessageSerialization:
    """Test message serialization and deserialization."""
    
    @pytest.mark.unit
    def test_round_trip_serialization(self):
        """Test that messages can be serialized and deserialized."""
        original = DashboardUpdate(data={"test": "value", "number": 42})
        
        # Serialize
        data = original.model_dump()
        
        # Deserialize
        reconstructed = DashboardUpdate(**data)
        
        assert reconstructed.type == original.type
        assert reconstructed.data == original.data
        assert reconstructed.channel == original.channel
    
    @pytest.mark.unit
    def test_json_serialization(self):
        """Test JSON serialization compatibility."""
        import json
        
        message = SessionUpdate(
            session_id="test_123", 
            data={"status": "active", "count": 5}
        )
        
        # Convert to dict with proper datetime handling
        data = message.model_dump()
        
        # Should be JSON serializable (with datetime handling)
        json_str = json.dumps(data, default=str)  # Convert datetime to string
        assert json_str is not None
        
        # Should be able to parse back
        parsed_data = json.loads(json_str)
        assert parsed_data["type"] == "session_update"
        assert parsed_data["session_id"] == "test_123"


if __name__ == "__main__":
    pytest.main([__file__]) 