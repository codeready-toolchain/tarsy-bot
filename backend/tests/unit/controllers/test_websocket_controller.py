"""
Unit tests for WebSocket controller.

Tests WebSocket endpoint, message handling, and EventListener integration.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import WebSocketDisconnect

from tarsy.controllers.websocket_controller import websocket_endpoint


@pytest.mark.unit
class TestWebSocketEndpointConnection:
    """Test WebSocket connection establishment."""

    @pytest.mark.asyncio
    async def test_connection_establishment_sends_confirmation(self):
        """Test that WebSocket connection sends confirmation message."""
        mock_websocket = AsyncMock()
        mock_websocket.receive_text.side_effect = WebSocketDisconnect()

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.disconnect = Mock()

            with patch("tarsy.controllers.websocket_controller.get_event_system"):
                try:
                    await websocket_endpoint(mock_websocket)
                except WebSocketDisconnect:
                    pass

                # Should connect
                mock_manager.connect.assert_called_once()
                
                # Should send connection confirmation
                assert mock_websocket.send_json.called
                call_args = mock_websocket.send_json.call_args[0][0]
                assert call_args["type"] == "connection.established"
                assert "connection_id" in call_args

    @pytest.mark.asyncio
    async def test_connection_cleanup_on_disconnect(self):
        """Test that disconnect properly cleans up resources."""
        mock_websocket = AsyncMock()
        mock_websocket.receive_text.side_effect = WebSocketDisconnect()

        mock_event_listener = AsyncMock()
        mock_event_system = Mock()
        mock_event_system.get_listener.return_value = mock_event_listener

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.disconnect = Mock()

            with patch("tarsy.controllers.websocket_controller.get_event_system", return_value=mock_event_system):
                try:
                    await websocket_endpoint(mock_websocket)
                except WebSocketDisconnect:
                    pass

                # Should disconnect
                mock_manager.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_cleanup_when_event_system_fails(self):
        """Test that disconnect is always called even if event system fails."""
        mock_websocket = AsyncMock()
        
        # Subscribe to a channel first
        subscribe_msg = json.dumps({"action": "subscribe", "channel": "sessions"})
        mock_websocket.receive_text.side_effect = [subscribe_msg, WebSocketDisconnect()]

        # Mock event system to fail during cleanup
        mock_event_listener = AsyncMock()
        mock_event_system = Mock()
        mock_event_system.get_listener.return_value = mock_event_listener

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.subscribe = Mock()
            mock_manager.disconnect = Mock()

            # First call succeeds (for subscription), second call fails (for cleanup)
            call_count = 0
            def get_event_system_side_effect():
                nonlocal call_count
                call_count += 1
                if call_count <= 2:  # First two calls succeed (subscription)
                    return mock_event_system
                else:  # Third call fails (cleanup)
                    raise RuntimeError("Event system unavailable")
            
            with patch("tarsy.controllers.websocket_controller.get_event_system", side_effect=get_event_system_side_effect):
                try:
                    await websocket_endpoint(mock_websocket)
                except WebSocketDisconnect:
                    pass

                # Should still disconnect even though event system failed
                mock_manager.disconnect.assert_called_once()


@pytest.mark.unit
class TestWebSocketEndpointSubscribe:
    """Test subscribe action handling."""

    @pytest.mark.asyncio
    async def test_subscribe_action_registers_with_event_listener(self):
        """Test that subscribe action registers callback with EventListener."""
        mock_websocket = AsyncMock()
        
        # First call: connection confirmation, second: subscribe, third: disconnect
        subscribe_message = json.dumps({"action": "subscribe", "channel": "sessions"})
        mock_websocket.receive_text.side_effect = [subscribe_message, WebSocketDisconnect()]

        mock_event_listener = AsyncMock()
        mock_event_system = Mock()
        mock_event_system.get_listener.return_value = mock_event_listener

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.subscribe = Mock()
            mock_manager.disconnect = Mock()

            with patch("tarsy.controllers.websocket_controller.get_event_system", return_value=mock_event_system):
                try:
                    await websocket_endpoint(mock_websocket)
                except WebSocketDisconnect:
                    pass

                # Should subscribe to connection manager
                mock_manager.subscribe.assert_called_once()
                
                # Should register with EventListener
                mock_event_listener.subscribe.assert_called_once()
                subscribe_args = mock_event_listener.subscribe.call_args
                assert subscribe_args[0][0] == "sessions"  # channel
                assert callable(subscribe_args[0][1])  # callback

                # Should send confirmation
                confirmation_calls = [
                    call for call in mock_websocket.send_json.call_args_list
                    if call[0][0].get("type") == "subscription.confirmed"
                ]
                assert len(confirmation_calls) == 1
                assert confirmation_calls[0][0][0]["channel"] == "sessions"

    @pytest.mark.asyncio
    async def test_subscribe_to_session_specific_channel(self):
        """Test subscribing to session-specific channel."""
        mock_websocket = AsyncMock()
        
        subscribe_message = json.dumps({"action": "subscribe", "channel": "session:test-123"})
        mock_websocket.receive_text.side_effect = [subscribe_message, WebSocketDisconnect()]

        mock_event_listener = AsyncMock()
        mock_event_system = Mock()
        mock_event_system.get_listener.return_value = mock_event_listener

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.subscribe = Mock()
            mock_manager.disconnect = Mock()

            with patch("tarsy.controllers.websocket_controller.get_event_system", return_value=mock_event_system):
                try:
                    await websocket_endpoint(mock_websocket)
                except WebSocketDisconnect:
                    pass

                # Should subscribe to session-specific channel
                subscribe_args = mock_event_listener.subscribe.call_args
                assert subscribe_args[0][0] == "session:test-123"

    @pytest.mark.asyncio
    async def test_subscribe_duplicate_channel_skipped(self):
        """Test that duplicate subscription to same channel is skipped."""
        mock_websocket = AsyncMock()
        
        # Subscribe twice to same channel
        subscribe_message = json.dumps({"action": "subscribe", "channel": "sessions"})
        mock_websocket.receive_text.side_effect = [
            subscribe_message,
            subscribe_message,
            WebSocketDisconnect()
        ]

        mock_event_listener = AsyncMock()
        mock_event_system = Mock()
        mock_event_system.get_listener.return_value = mock_event_listener

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.subscribe = Mock()
            mock_manager.disconnect = Mock()

            with patch("tarsy.controllers.websocket_controller.get_event_system", return_value=mock_event_system):
                try:
                    await websocket_endpoint(mock_websocket)
                except WebSocketDisconnect:
                    pass

                # Should only subscribe once to EventListener
                assert mock_event_listener.subscribe.call_count == 1


@pytest.mark.unit
class TestWebSocketEndpointUnsubscribe:
    """Test unsubscribe action handling."""

    @pytest.mark.asyncio
    async def test_unsubscribe_action_removes_from_event_listener(self):
        """Test that unsubscribe removes callback from EventListener."""
        mock_websocket = AsyncMock()
        
        subscribe_msg = json.dumps({"action": "subscribe", "channel": "sessions"})
        unsubscribe_msg = json.dumps({"action": "unsubscribe", "channel": "sessions"})
        mock_websocket.receive_text.side_effect = [subscribe_msg, unsubscribe_msg, WebSocketDisconnect()]

        mock_event_listener = AsyncMock()
        mock_event_system = Mock()
        mock_event_system.get_listener.return_value = mock_event_listener

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.subscribe = Mock()
            mock_manager.unsubscribe = Mock()
            mock_manager.disconnect = Mock()

            with patch("tarsy.controllers.websocket_controller.get_event_system", return_value=mock_event_system):
                try:
                    await websocket_endpoint(mock_websocket)
                except WebSocketDisconnect:
                    pass

                # Should unsubscribe from connection manager
                mock_manager.unsubscribe.assert_called_once()
                
                # Should remove from EventListener
                mock_event_listener.unsubscribe.assert_called_once()

                # Should send cancellation confirmation
                cancellation_calls = [
                    call for call in mock_websocket.send_json.call_args_list
                    if call[0][0].get("type") == "subscription.cancelled"
                ]
                assert len(cancellation_calls) == 1


@pytest.mark.unit
class TestWebSocketEndpointCatchup:
    """Test catchup mechanism for missed events."""

    @pytest.mark.asyncio
    async def test_catchup_fetches_missed_events(self):
        """Test that catchup fetches and sends missed events from database."""
        mock_websocket = AsyncMock()
        
        catchup_msg = json.dumps({"action": "catchup", "channel": "sessions", "last_event_id": 42})
        mock_websocket.receive_text.side_effect = [catchup_msg, WebSocketDisconnect()]

        # Mock event repository
        mock_event1 = Mock()
        mock_event1.id = 43
        mock_event1.payload = {"type": "session.started", "session_id": "test-1"}
        mock_event2 = Mock()
        mock_event2.id = 44
        mock_event2.payload = {"type": "session.completed", "session_id": "test-1"}
        
        mock_event_repo = AsyncMock()
        mock_event_repo.get_events_after.return_value = [mock_event1, mock_event2]

        mock_session = AsyncMock()
        mock_session_factory = Mock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock()

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.disconnect = Mock()

            with patch("tarsy.controllers.websocket_controller.get_event_system"):
                with patch("tarsy.controllers.websocket_controller.get_async_session_factory", return_value=mock_session_factory):
                    with patch("tarsy.controllers.websocket_controller.EventRepository", return_value=mock_event_repo):
                        try:
                            await websocket_endpoint(mock_websocket)
                        except WebSocketDisconnect:
                            pass

                        # Should fetch events after last_event_id
                        mock_event_repo.get_events_after.assert_called_once_with(
                            channel="sessions",
                            after_id=42,
                            limit=100
                        )

                        # Should send both events with id injected
                        event_sends = [
                            call for call in mock_websocket.send_json.call_args_list
                            if call[0][0].get("type") in ["session.started", "session.completed"]
                        ]
                        assert len(event_sends) == 2
                        
                        # Verify id is injected into payloads (for dashboard compatibility)
                        assert event_sends[0][0][0]["id"] == 43
                        assert event_sends[1][0][0]["id"] == 44

    @pytest.mark.asyncio
    async def test_catchup_with_default_last_event_id(self):
        """Test catchup with no last_event_id defaults to 0."""
        mock_websocket = AsyncMock()
        
        catchup_msg = json.dumps({"action": "catchup", "channel": "sessions"})
        mock_websocket.receive_text.side_effect = [catchup_msg, WebSocketDisconnect()]

        mock_event_repo = AsyncMock()
        mock_event_repo.get_events_after.return_value = []

        mock_session = AsyncMock()
        mock_session_factory = Mock()
        mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_factory.return_value.__aexit__ = AsyncMock()

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.disconnect = Mock()

            with patch("tarsy.controllers.websocket_controller.get_event_system"):
                with patch("tarsy.controllers.websocket_controller.get_async_session_factory", return_value=mock_session_factory):
                    with patch("tarsy.controllers.websocket_controller.EventRepository", return_value=mock_event_repo):
                        try:
                            await websocket_endpoint(mock_websocket)
                        except WebSocketDisconnect:
                            pass

                        # Should default to after_id=0
                        mock_event_repo.get_events_after.assert_called_once()
                        call_kwargs = mock_event_repo.get_events_after.call_args[1]
                        assert call_kwargs["after_id"] == 0


@pytest.mark.unit
class TestWebSocketEndpointPing:
    """Test ping/pong keepalive."""

    @pytest.mark.asyncio
    async def test_ping_responds_with_pong(self):
        """Test that ping action responds with pong."""
        mock_websocket = AsyncMock()
        
        ping_msg = json.dumps({"action": "ping"})
        mock_websocket.receive_text.side_effect = [ping_msg, WebSocketDisconnect()]

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.disconnect = Mock()

            with patch("tarsy.controllers.websocket_controller.get_event_system"):
                try:
                    await websocket_endpoint(mock_websocket)
                except WebSocketDisconnect:
                    pass

                # Should respond with pong
                pong_calls = [
                    call for call in mock_websocket.send_json.call_args_list
                    if call[0][0].get("type") == "pong"
                ]
                assert len(pong_calls) == 1


@pytest.mark.unit
class TestWebSocketEndpointErrorHandling:
    """Test error handling in WebSocket endpoint."""

    @pytest.mark.asyncio
    async def test_malformed_json_handled_gracefully(self):
        """Test that malformed JSON doesn't crash the connection."""
        mock_websocket = AsyncMock()
        
        # Send invalid JSON followed by disconnect
        mock_websocket.receive_text.side_effect = [
            "invalid{json",
            WebSocketDisconnect()
        ]

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.disconnect = Mock()

            with patch("tarsy.controllers.websocket_controller.get_event_system"):
                try:
                    await websocket_endpoint(mock_websocket)
                except (WebSocketDisconnect, json.JSONDecodeError):
                    pass

                # Should still cleanup
                mock_manager.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_action_ignored(self):
        """Test that unknown action is ignored gracefully."""
        mock_websocket = AsyncMock()
        
        unknown_msg = json.dumps({"action": "unknown_action", "data": "test"})
        mock_websocket.receive_text.side_effect = [unknown_msg, WebSocketDisconnect()]

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.disconnect = Mock()

            with patch("tarsy.controllers.websocket_controller.get_event_system"):
                try:
                    await websocket_endpoint(mock_websocket)
                except WebSocketDisconnect:
                    pass

                # Should continue processing and cleanup properly
                mock_manager.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_channel_in_subscribe(self):
        """Test subscribe without channel is ignored."""
        mock_websocket = AsyncMock()
        
        invalid_subscribe = json.dumps({"action": "subscribe"})  # Missing channel
        mock_websocket.receive_text.side_effect = [invalid_subscribe, WebSocketDisconnect()]

        mock_event_listener = AsyncMock()
        mock_event_system = Mock()
        mock_event_system.get_listener.return_value = mock_event_listener

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.subscribe = Mock()
            mock_manager.disconnect = Mock()

            with patch("tarsy.controllers.websocket_controller.get_event_system", return_value=mock_event_system):
                try:
                    await websocket_endpoint(mock_websocket)
                except WebSocketDisconnect:
                    pass

                # Should not subscribe without channel
                mock_manager.subscribe.assert_not_called()
                mock_event_listener.subscribe.assert_not_called()


@pytest.mark.unit
class TestWebSocketEndpointEventListenerIntegration:
    """Test integration with EventListener system."""

    @pytest.mark.asyncio
    async def test_callback_registered_with_correct_closure(self):
        """Test that callback closure captures channel correctly."""
        mock_websocket = AsyncMock()
        
        # Subscribe to two different channels
        subscribe_msg1 = json.dumps({"action": "subscribe", "channel": "channel1"})
        subscribe_msg2 = json.dumps({"action": "subscribe", "channel": "channel2"})
        mock_websocket.receive_text.side_effect = [
            subscribe_msg1,
            subscribe_msg2,
            WebSocketDisconnect()
        ]

        captured_callbacks = {}
        
        async def mock_event_listener_subscribe(channel, callback):
            captured_callbacks[channel] = callback

        mock_event_listener = AsyncMock()
        mock_event_listener.subscribe.side_effect = mock_event_listener_subscribe
        
        mock_event_system = Mock()
        mock_event_system.get_listener.return_value = mock_event_listener

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.subscribe = Mock()
            mock_manager.disconnect = Mock()
            mock_manager.broadcast_to_channel = AsyncMock()

            with patch("tarsy.controllers.websocket_controller.get_event_system", return_value=mock_event_system):
                try:
                    await websocket_endpoint(mock_websocket)
                except WebSocketDisconnect:
                    pass

                # Verify callbacks were registered for both channels
                assert "channel1" in captured_callbacks
                assert "channel2" in captured_callbacks
                
                # Test that each callback broadcasts to correct channel
                test_event = {"type": "test"}
                await captured_callbacks["channel1"](test_event)
                mock_manager.broadcast_to_channel.assert_called_with("channel1", test_event)

    @pytest.mark.asyncio
    async def test_cleanup_unsubscribes_all_channels(self):
        """Test that cleanup unsubscribes from all EventListener channels."""
        mock_websocket = AsyncMock()
        
        # Subscribe to multiple channels
        subscribe_msg1 = json.dumps({"action": "subscribe", "channel": "channel1"})
        subscribe_msg2 = json.dumps({"action": "subscribe", "channel": "channel2"})
        subscribe_msg3 = json.dumps({"action": "subscribe", "channel": "channel3"})
        mock_websocket.receive_text.side_effect = [
            subscribe_msg1,
            subscribe_msg2,
            subscribe_msg3,
            WebSocketDisconnect()
        ]

        mock_event_listener = AsyncMock()
        mock_event_system = Mock()
        mock_event_system.get_listener.return_value = mock_event_listener

        with patch("tarsy.controllers.websocket_controller.connection_manager") as mock_manager:
            mock_manager.connect = AsyncMock()
            mock_manager.subscribe = Mock()
            mock_manager.disconnect = Mock()

            with patch("tarsy.controllers.websocket_controller.get_event_system", return_value=mock_event_system):
                try:
                    await websocket_endpoint(mock_websocket)
                except WebSocketDisconnect:
                    pass

                # Should unsubscribe from all 3 channels during cleanup
                assert mock_event_listener.unsubscribe.call_count == 3

