"""
Unit tests for WebSocketConnectionManager.

Tests connection lifecycle, subscription management, broadcasting, and error handling.
"""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from tarsy.services.websocket_connection_manager import WebSocketConnectionManager


@pytest.mark.unit
class TestWebSocketConnectionManagerInitialization:
    """Test WebSocketConnectionManager initialization."""

    def test_initialization_creates_empty_state(self):
        """Test that initialization creates empty connection state."""
        manager = WebSocketConnectionManager()

        assert manager.connections == {}
        assert manager.subscriptions == {}
        assert manager.channel_subscribers == {}


@pytest.mark.unit
class TestWebSocketConnectionManagerConnect:
    """Test WebSocket connection establishment."""

    @pytest.mark.asyncio
    async def test_connect_accepts_websocket_and_stores_connection(self):
        """Test that connect accepts WebSocket and stores connection."""
        manager = WebSocketConnectionManager()
        mock_websocket = AsyncMock()
        connection_id = "test-connection-1"

        await manager.connect(connection_id, mock_websocket)

        mock_websocket.accept.assert_called_once()
        assert connection_id in manager.connections
        assert manager.connections[connection_id] is mock_websocket
        assert connection_id in manager.subscriptions
        assert manager.subscriptions[connection_id] == set()

    @pytest.mark.asyncio
    async def test_connect_multiple_connections(self):
        """Test connecting multiple WebSocket connections."""
        manager = WebSocketConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws3 = AsyncMock()

        await manager.connect("conn1", mock_ws1)
        await manager.connect("conn2", mock_ws2)
        await manager.connect("conn3", mock_ws3)

        assert len(manager.connections) == 3
        assert len(manager.subscriptions) == 3
        assert "conn1" in manager.connections
        assert "conn2" in manager.connections
        assert "conn3" in manager.connections


@pytest.mark.unit
class TestWebSocketConnectionManagerDisconnect:
    """Test WebSocket disconnection and cleanup."""

    @pytest.mark.asyncio
    async def test_disconnect_removes_connection_and_subscriptions(self):
        """Test that disconnect removes connection and cleans up subscriptions."""
        manager = WebSocketConnectionManager()
        mock_websocket = AsyncMock()
        connection_id = "test-connection-1"

        await manager.connect(connection_id, mock_websocket)
        manager.subscribe(connection_id, "channel1")
        manager.subscribe(connection_id, "channel2")

        manager.disconnect(connection_id)

        assert connection_id not in manager.connections
        assert connection_id not in manager.subscriptions
        assert "channel1" not in manager.channel_subscribers
        assert "channel2" not in manager.channel_subscribers

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_shared_channels(self):
        """Test that disconnect only removes specific connection from shared channels."""
        manager = WebSocketConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect("conn1", mock_ws1)
        await manager.connect("conn2", mock_ws2)

        manager.subscribe("conn1", "shared_channel")
        manager.subscribe("conn2", "shared_channel")

        manager.disconnect("conn1")

        # conn2 should still be subscribed to shared_channel
        assert "shared_channel" in manager.channel_subscribers
        assert "conn2" in manager.channel_subscribers["shared_channel"]
        assert "conn1" not in manager.channel_subscribers.get("shared_channel", set())

    def test_disconnect_nonexistent_connection(self):
        """Test that disconnecting nonexistent connection doesn't raise errors."""
        manager = WebSocketConnectionManager()

        # Should not raise
        manager.disconnect("nonexistent-connection")

    @pytest.mark.asyncio
    async def test_disconnect_removes_empty_channels(self):
        """Test that disconnect removes channels with no remaining subscribers."""
        manager = WebSocketConnectionManager()
        mock_websocket = AsyncMock()

        await manager.connect("conn1", mock_websocket)
        manager.subscribe("conn1", "channel1")
        manager.subscribe("conn1", "channel2")

        manager.disconnect("conn1")

        # Channels should be removed when empty
        assert "channel1" not in manager.channel_subscribers
        assert "channel2" not in manager.channel_subscribers


@pytest.mark.unit
class TestWebSocketConnectionManagerSubscribe:
    """Test channel subscription functionality."""

    @pytest.mark.asyncio
    async def test_subscribe_adds_connection_to_channel(self):
        """Test that subscribe adds connection to channel."""
        manager = WebSocketConnectionManager()
        mock_websocket = AsyncMock()
        connection_id = "test-connection-1"

        await manager.connect(connection_id, mock_websocket)
        manager.subscribe(connection_id, "test_channel")

        assert "test_channel" in manager.subscriptions[connection_id]
        assert "test_channel" in manager.channel_subscribers
        assert connection_id in manager.channel_subscribers["test_channel"]

    @pytest.mark.asyncio
    async def test_subscribe_to_multiple_channels(self):
        """Test subscribing single connection to multiple channels."""
        manager = WebSocketConnectionManager()
        mock_websocket = AsyncMock()
        connection_id = "test-connection-1"

        await manager.connect(connection_id, mock_websocket)
        manager.subscribe(connection_id, "channel1")
        manager.subscribe(connection_id, "channel2")
        manager.subscribe(connection_id, "channel3")

        assert len(manager.subscriptions[connection_id]) == 3
        assert "channel1" in manager.subscriptions[connection_id]
        assert "channel2" in manager.subscriptions[connection_id]
        assert "channel3" in manager.subscriptions[connection_id]

    @pytest.mark.asyncio
    async def test_subscribe_multiple_connections_to_same_channel(self):
        """Test multiple connections subscribing to same channel."""
        manager = WebSocketConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws3 = AsyncMock()

        await manager.connect("conn1", mock_ws1)
        await manager.connect("conn2", mock_ws2)
        await manager.connect("conn3", mock_ws3)

        manager.subscribe("conn1", "shared_channel")
        manager.subscribe("conn2", "shared_channel")
        manager.subscribe("conn3", "shared_channel")

        assert len(manager.channel_subscribers["shared_channel"]) == 3
        assert "conn1" in manager.channel_subscribers["shared_channel"]
        assert "conn2" in manager.channel_subscribers["shared_channel"]
        assert "conn3" in manager.channel_subscribers["shared_channel"]

    def test_subscribe_unknown_connection(self):
        """Test subscribing with unknown connection ID."""
        manager = WebSocketConnectionManager()

        # Should handle gracefully without raising
        manager.subscribe("unknown-connection", "test_channel")

        # Channel should not be created
        assert "test_channel" not in manager.channel_subscribers


@pytest.mark.unit
class TestWebSocketConnectionManagerUnsubscribe:
    """Test channel unsubscription functionality."""

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_connection_from_channel(self):
        """Test that unsubscribe removes connection from channel."""
        manager = WebSocketConnectionManager()
        mock_websocket = AsyncMock()
        connection_id = "test-connection-1"

        await manager.connect(connection_id, mock_websocket)
        manager.subscribe(connection_id, "test_channel")
        manager.unsubscribe(connection_id, "test_channel")

        assert "test_channel" not in manager.subscriptions[connection_id]
        # Channel should be removed when empty
        assert "test_channel" not in manager.channel_subscribers

    @pytest.mark.asyncio
    async def test_unsubscribe_keeps_other_connections_subscribed(self):
        """Test that unsubscribe doesn't affect other connections."""
        manager = WebSocketConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect("conn1", mock_ws1)
        await manager.connect("conn2", mock_ws2)

        manager.subscribe("conn1", "test_channel")
        manager.subscribe("conn2", "test_channel")

        manager.unsubscribe("conn1", "test_channel")

        # conn2 should still be subscribed
        assert "test_channel" in manager.channel_subscribers
        assert "conn2" in manager.channel_subscribers["test_channel"]
        assert "conn1" not in manager.channel_subscribers["test_channel"]

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_empty_channel(self):
        """Test that unsubscribe removes channel when last subscriber leaves."""
        manager = WebSocketConnectionManager()
        mock_websocket = AsyncMock()

        await manager.connect("conn1", mock_websocket)
        manager.subscribe("conn1", "test_channel")
        manager.unsubscribe("conn1", "test_channel")

        # Channel should be removed when no subscribers remain
        assert "test_channel" not in manager.channel_subscribers

    def test_unsubscribe_unknown_connection(self):
        """Test unsubscribing with unknown connection."""
        manager = WebSocketConnectionManager()

        # Should handle gracefully without raising
        manager.unsubscribe("unknown-connection", "test_channel")

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_channel(self):
        """Test unsubscribing from channel connection never subscribed to."""
        manager = WebSocketConnectionManager()
        mock_websocket = AsyncMock()

        await manager.connect("conn1", mock_websocket)

        # Should handle gracefully
        manager.unsubscribe("conn1", "nonexistent_channel")


@pytest.mark.unit
class TestWebSocketConnectionManagerBroadcast:
    """Test event broadcasting functionality."""

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_channel_subscribers(self):
        """Test that broadcast sends event to all subscribers of a channel."""
        manager = WebSocketConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws3 = AsyncMock()

        await manager.connect("conn1", mock_ws1)
        await manager.connect("conn2", mock_ws2)
        await manager.connect("conn3", mock_ws3)

        manager.subscribe("conn1", "test_channel")
        manager.subscribe("conn2", "test_channel")
        manager.subscribe("conn3", "test_channel")

        event = {"type": "test.event", "data": "hello"}
        await manager.broadcast_to_channel("test_channel", event)

        expected_json = json.dumps(event)
        mock_ws1.send_text.assert_called_once_with(expected_json)
        mock_ws2.send_text.assert_called_once_with(expected_json)
        mock_ws3.send_text.assert_called_once_with(expected_json)

    @pytest.mark.asyncio
    async def test_broadcast_to_nonexistent_channel(self):
        """Test broadcasting to channel with no subscribers."""
        manager = WebSocketConnectionManager()

        # Should handle gracefully without errors
        await manager.broadcast_to_channel("nonexistent_channel", {"type": "test"})

    @pytest.mark.asyncio
    async def test_broadcast_handles_send_errors(self):
        """Test that broadcast handles WebSocket send errors gracefully."""
        manager = WebSocketConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        # ws1 will fail to send
        mock_ws1.send_text.side_effect = Exception("Connection closed")
        mock_ws2.send_text.return_value = None

        await manager.connect("conn1", mock_ws1)
        await manager.connect("conn2", mock_ws2)

        manager.subscribe("conn1", "test_channel")
        manager.subscribe("conn2", "test_channel")

        event = {"type": "test.event"}
        await manager.broadcast_to_channel("test_channel", event)

        # Both should be called, even though ws1 failed
        mock_ws1.send_text.assert_called_once()
        mock_ws2.send_text.assert_called_once()

        # Connection should not be removed (controller handles disconnection)
        assert "conn1" in manager.connections
        assert "conn2" in manager.connections

    @pytest.mark.asyncio
    async def test_broadcast_only_to_channel_subscribers(self):
        """Test that broadcast only sends to subscribers of specific channel."""
        manager = WebSocketConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect("conn1", mock_ws1)
        await manager.connect("conn2", mock_ws2)

        manager.subscribe("conn1", "channel_a")
        manager.subscribe("conn2", "channel_b")

        event = {"type": "test.event"}
        await manager.broadcast_to_channel("channel_a", event)

        # Only conn1 should receive the event
        mock_ws1.send_text.assert_called_once()
        mock_ws2.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_with_complex_event_data(self):
        """Test broadcasting with complex nested event data."""
        manager = WebSocketConnectionManager()
        mock_websocket = AsyncMock()

        await manager.connect("conn1", mock_websocket)
        manager.subscribe("conn1", "test_channel")

        complex_event = {
            "type": "session.started",
            "session_id": "test-123",
            "alert_type": "kubernetes",
            "metadata": {
                "nested": {
                    "data": [1, 2, 3],
                    "flags": {"enabled": True}
                }
            }
        }

        await manager.broadcast_to_channel("test_channel", complex_event)

        # Verify JSON serialization works correctly
        expected_json = json.dumps(complex_event)
        mock_websocket.send_text.assert_called_once_with(expected_json)


@pytest.mark.unit
class TestWebSocketConnectionManagerEdgeCases:
    """Test edge cases and error scenarios."""

    @pytest.mark.asyncio
    async def test_connection_subscribed_to_same_channel_twice(self):
        """Test subscribing to same channel twice."""
        manager = WebSocketConnectionManager()
        mock_websocket = AsyncMock()

        await manager.connect("conn1", mock_websocket)
        manager.subscribe("conn1", "test_channel")
        manager.subscribe("conn1", "test_channel")

        # Should only be subscribed once
        assert len(manager.channel_subscribers["test_channel"]) == 1

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent connect/disconnect/subscribe operations."""
        manager = WebSocketConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect("conn1", mock_ws1)
        await manager.connect("conn2", mock_ws2)

        manager.subscribe("conn1", "channel1")
        manager.subscribe("conn2", "channel1")
        manager.disconnect("conn1")

        # conn2 should still be connected and subscribed
        assert "conn2" in manager.connections
        assert "channel1" in manager.channel_subscribers
        assert "conn2" in manager.channel_subscribers["channel1"]

    @pytest.mark.asyncio
    async def test_state_consistency_after_errors(self):
        """Test that manager maintains consistent state after errors."""
        manager = WebSocketConnectionManager()
        mock_websocket = AsyncMock()

        await manager.connect("conn1", mock_websocket)
        manager.subscribe("conn1", "channel1")

        # Simulate error during broadcast
        mock_websocket.send_text.side_effect = Exception("Send failed")
        await manager.broadcast_to_channel("channel1", {"type": "test"})

        # State should remain consistent
        assert "conn1" in manager.connections
        assert "channel1" in manager.subscriptions["conn1"]
        assert "conn1" in manager.channel_subscribers["channel1"]

