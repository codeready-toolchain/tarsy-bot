"""
Integration tests for WebSocket system.

Tests the complete flow: EventPublisher → EventListener → WebSocket → Clients
"""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tarsy.models.db_models import SQLModel
from tarsy.models.event_models import SessionStartedEvent
from tarsy.services.events.channels import EventChannel
from tarsy.services.events.publisher import publish_event
from tarsy.services.websocket_connection_manager import WebSocketConnectionManager


@pytest.fixture
async def async_test_engine(isolated_test_settings):
    """Create an async test engine."""
    engine = create_async_engine(
        isolated_test_settings.database_url.replace("sqlite:///", "sqlite+aiosqlite:///"),
        echo=False
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def async_test_session_factory(async_test_engine):
    """Create an async session factory for testing."""
    return async_sessionmaker(
        async_test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )


@pytest.mark.integration
class TestWebSocketEventListenerIntegration:
    """Test integration between EventListener and WebSocket broadcasting."""

    @pytest.mark.asyncio
    async def test_event_published_to_db_broadcasts_to_websocket_clients(
        self, async_test_session_factory, isolated_test_settings
    ):
        """
        Test that events published to database are broadcast to WebSocket clients.
        
        Flow:
        1. Publish event to database (via EventPublisher)
        2. EventListener receives event (PostgreSQL NOTIFY or SQLite poll)
        3. EventListener calls WebSocket callback
        4. WebSocket broadcasts to all subscribed clients
        """
        # Create connection manager and mock WebSocket clients
        manager = WebSocketConnectionManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws3 = AsyncMock()

        await manager.connect("client1", mock_ws1)
        await manager.connect("client2", mock_ws2)
        await manager.connect("client3", mock_ws3)

        # Subscribe clients to different channels
        manager.subscribe("client1", EventChannel.SESSIONS)
        manager.subscribe("client2", EventChannel.SESSIONS)
        manager.subscribe("client3", "session:test-123")

        # Create event and publish to database
        event = SessionStartedEvent(
            session_id="test-123",
            alert_type="kubernetes"
        )

        # Publish to global sessions channel
        async with async_test_session_factory() as session:
            await publish_event(session, EventChannel.SESSIONS, event)
            await session.commit()

        # Simulate EventListener receiving the event and calling our callback
        # In real system, this happens via PostgreSQL NOTIFY or SQLite polling
        event_dict = json.loads(event.model_dump_json())
        await manager.broadcast_to_channel(EventChannel.SESSIONS, event_dict)

        # Verify WebSocket clients received the event
        expected_json = json.dumps(event_dict)
        mock_ws1.send_text.assert_called_once_with(expected_json)
        mock_ws2.send_text.assert_called_once_with(expected_json)
        mock_ws3.send_text.assert_not_called()  # Not subscribed to sessions channel

    @pytest.mark.asyncio
    async def test_dual_channel_publishing_reaches_correct_subscribers(self):
        """
        Test that events published to both channels reach appropriate subscribers.
        
        Events are published to both 'sessions' and 'session:{id}' channels,
        so clients subscribed to either should receive the event.
        """
        manager = WebSocketConnectionManager()
        mock_dashboard = AsyncMock()  # Subscribed to global 'sessions'
        mock_detail_view = AsyncMock()  # Subscribed to specific 'session:test-123'

        await manager.connect("dashboard", mock_dashboard)
        await manager.connect("detail", mock_detail_view)

        manager.subscribe("dashboard", EventChannel.SESSIONS)
        manager.subscribe("detail", "session:test-123")

        # Create event
        event = SessionStartedEvent(
            session_id="test-123",
            alert_type="kubernetes"
        )

        # Publish to both channels (simulating real event_helpers behavior)
        event_dict = json.loads(event.model_dump_json())
        await manager.broadcast_to_channel(EventChannel.SESSIONS, event_dict)
        await manager.broadcast_to_channel("session:test-123", event_dict)

        # Both should receive the event
        expected_json = json.dumps(event_dict)
        mock_dashboard.send_text.assert_called_once_with(expected_json)
        mock_detail_view.send_text.assert_called_once_with(expected_json)

    @pytest.mark.asyncio
    async def test_multiple_events_to_same_channel(self):
        """Test multiple events broadcast to same channel."""
        manager = WebSocketConnectionManager()
        mock_client = AsyncMock()

        await manager.connect("client1", mock_client)
        manager.subscribe("client1", EventChannel.SESSIONS)

        # Broadcast multiple events
        events = [
            {"type": "session.started", "session_id": "test-1"},
            {"type": "session.completed", "session_id": "test-1"},
            {"type": "session.started", "session_id": "test-2"},
        ]

        for event in events:
            await manager.broadcast_to_channel(EventChannel.SESSIONS, event)

        # Client should receive all events
        assert mock_client.send_text.call_count == 3

    @pytest.mark.asyncio
    async def test_client_reconnection_and_catchup(
        self, async_test_session_factory, isolated_test_settings
    ):
        """Test client reconnection and event catchup mechanism."""
        from tarsy.repositories.event_repository import EventRepository

        # Publish some events while client is disconnected
        event1 = SessionStartedEvent(session_id="test-1", alert_type="kubernetes")
        event2 = SessionStartedEvent(session_id="test-2", alert_type="kubernetes")

        async with async_test_session_factory() as session:
            await publish_event(session, EventChannel.SESSIONS, event1)
            await publish_event(session, EventChannel.SESSIONS, event2)
            await session.commit()

        # Client reconnects and requests catchup
        async with async_test_session_factory() as session:
            event_repo = EventRepository(session)
            missed_events = await event_repo.get_events_after(
                channel=EventChannel.SESSIONS,
                after_id=0,
                limit=100
            )

            # Should receive both events
            assert len(missed_events) >= 2
            assert any(e.payload.get("session_id") == "test-1" for e in missed_events)
            assert any(e.payload.get("session_id") == "test-2" for e in missed_events)


@pytest.mark.integration
class TestWebSocketMultiClientScenarios:
    """Test scenarios with multiple WebSocket clients."""

    @pytest.mark.asyncio
    async def test_multiple_tabs_same_user(self):
        """Test multiple browser tabs (multiple connections) from same user."""
        manager = WebSocketConnectionManager()
        
        # Simulate 3 tabs from same user
        mock_tab1 = AsyncMock()
        mock_tab2 = AsyncMock()
        mock_tab3 = AsyncMock()

        await manager.connect("tab1", mock_tab1)
        await manager.connect("tab2", mock_tab2)
        await manager.connect("tab3", mock_tab3)

        # All tabs subscribe to sessions channel
        manager.subscribe("tab1", EventChannel.SESSIONS)
        manager.subscribe("tab2", EventChannel.SESSIONS)
        manager.subscribe("tab3", EventChannel.SESSIONS)

        # Broadcast event
        event = {"type": "session.started", "session_id": "test-123"}
        await manager.broadcast_to_channel(EventChannel.SESSIONS, event)

        # All tabs should receive the event
        expected_json = json.dumps(event)
        mock_tab1.send_text.assert_called_once_with(expected_json)
        mock_tab2.send_text.assert_called_once_with(expected_json)
        mock_tab3.send_text.assert_called_once_with(expected_json)

    @pytest.mark.asyncio
    async def test_dashboard_and_detail_views_simultaneously(self):
        """
        Test dashboard view and session detail view open simultaneously.
        
        Dashboard subscribes to 'sessions', detail view subscribes to 'session:{id}'
        """
        manager = WebSocketConnectionManager()
        
        mock_dashboard = AsyncMock()
        mock_detail = AsyncMock()

        await manager.connect("dashboard", mock_dashboard)
        await manager.connect("detail", mock_detail)

        manager.subscribe("dashboard", EventChannel.SESSIONS)
        manager.subscribe("detail", "session:test-123")

        # Event published to both channels (dual-channel pattern)
        event = {"type": "session.progress", "session_id": "test-123", "progress": 50}
        
        await manager.broadcast_to_channel(EventChannel.SESSIONS, event)
        await manager.broadcast_to_channel("session:test-123", event)

        # Dashboard receives from 'sessions' channel
        assert mock_dashboard.send_text.call_count == 1
        
        # Detail view receives from 'session:test-123' channel
        assert mock_detail.send_text.call_count == 1

    @pytest.mark.asyncio
    async def test_one_tab_closes_others_continue(self):
        """Test that closing one tab doesn't affect others."""
        manager = WebSocketConnectionManager()
        
        mock_tab1 = AsyncMock()
        mock_tab2 = AsyncMock()

        await manager.connect("tab1", mock_tab1)
        await manager.connect("tab2", mock_tab2)

        manager.subscribe("tab1", EventChannel.SESSIONS)
        manager.subscribe("tab2", EventChannel.SESSIONS)

        # Tab1 disconnects
        manager.disconnect("tab1")

        # Broadcast event
        event = {"type": "session.started", "session_id": "test-123"}
        await manager.broadcast_to_channel(EventChannel.SESSIONS, event)

        # Only tab2 should receive it
        mock_tab1.send_text.assert_not_called()
        mock_tab2.send_text.assert_called_once()


@pytest.mark.integration
class TestWebSocketChannelIsolation:
    """Test that channels are properly isolated."""

    @pytest.mark.asyncio
    async def test_events_only_reach_subscribed_channels(self):
        """Test that events only reach clients subscribed to that channel."""
        manager = WebSocketConnectionManager()
        
        mock_sessions_client = AsyncMock()
        mock_session1_client = AsyncMock()
        mock_session2_client = AsyncMock()

        await manager.connect("sessions_client", mock_sessions_client)
        await manager.connect("session1_client", mock_session1_client)
        await manager.connect("session2_client", mock_session2_client)

        manager.subscribe("sessions_client", EventChannel.SESSIONS)
        manager.subscribe("session1_client", "session:test-1")
        manager.subscribe("session2_client", "session:test-2")

        # Broadcast to session:test-1
        event = {"type": "session.progress", "session_id": "test-1"}
        await manager.broadcast_to_channel("session:test-1", event)

        # Only session1_client should receive it
        mock_sessions_client.send_text.assert_not_called()
        mock_session1_client.send_text.assert_called_once()
        mock_session2_client.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_receiving_events(self):
        """Test that unsubscribing stops event delivery."""
        manager = WebSocketConnectionManager()
        
        mock_client = AsyncMock()

        await manager.connect("client1", mock_client)
        manager.subscribe("client1", EventChannel.SESSIONS)

        # Send event while subscribed
        event1 = {"type": "session.started", "session_id": "test-1"}
        await manager.broadcast_to_channel(EventChannel.SESSIONS, event1)
        assert mock_client.send_text.call_count == 1

        # Unsubscribe
        manager.unsubscribe("client1", EventChannel.SESSIONS)

        # Send event after unsubscribe
        event2 = {"type": "session.started", "session_id": "test-2"}
        await manager.broadcast_to_channel(EventChannel.SESSIONS, event2)
        
        # Should still be 1 (didn't receive event2)
        assert mock_client.send_text.call_count == 1


@pytest.mark.integration
class TestWebSocketErrorResilience:
    """Test WebSocket error handling and resilience."""

    @pytest.mark.asyncio
    async def test_broadcast_continues_despite_client_send_failure(self):
        """Test that failed send to one client doesn't affect others."""
        manager = WebSocketConnectionManager()
        
        mock_failing_client = AsyncMock()
        mock_working_client = AsyncMock()

        # First client will fail to send
        mock_failing_client.send_text.side_effect = Exception("Connection closed")
        mock_working_client.send_text.return_value = None

        await manager.connect("failing", mock_failing_client)
        await manager.connect("working", mock_working_client)

        manager.subscribe("failing", EventChannel.SESSIONS)
        manager.subscribe("working", EventChannel.SESSIONS)

        # Broadcast event
        event = {"type": "session.started", "session_id": "test-123"}
        await manager.broadcast_to_channel(EventChannel.SESSIONS, event)

        # Both should be called, even though first failed
        mock_failing_client.send_text.assert_called_once()
        mock_working_client.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_rapid_subscribe_unsubscribe_cycles(self):
        """Test rapid subscription/unsubscription doesn't cause issues."""
        manager = WebSocketConnectionManager()
        mock_client = AsyncMock()

        await manager.connect("client1", mock_client)

        # Rapidly subscribe and unsubscribe
        for _ in range(10):
            manager.subscribe("client1", EventChannel.SESSIONS)
            manager.unsubscribe("client1", EventChannel.SESSIONS)

        # Final state should be consistent
        assert EventChannel.SESSIONS not in manager.subscriptions.get("client1", set())
        assert EventChannel.SESSIONS not in manager.channel_subscribers


@pytest.mark.integration
class TestWebSocketPerformance:
    """Test WebSocket performance characteristics."""

    @pytest.mark.asyncio
    async def test_broadcast_to_many_clients(self):
        """Test broadcasting to many simultaneous clients."""
        manager = WebSocketConnectionManager()
        
        # Create 50 mock clients
        clients = []
        for i in range(50):
            mock_client = AsyncMock()
            client_id = f"client{i}"
            await manager.connect(client_id, mock_client)
            manager.subscribe(client_id, EventChannel.SESSIONS)
            clients.append(mock_client)

        # Broadcast event
        event = {"type": "session.started", "session_id": "test-123"}
        await manager.broadcast_to_channel(EventChannel.SESSIONS, event)

        # All clients should receive the event
        for client in clients:
            client.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_many_channels_per_connection(self):
        """Test connection subscribed to many channels."""
        manager = WebSocketConnectionManager()
        mock_client = AsyncMock()

        await manager.connect("client1", mock_client)

        # Subscribe to 20 different session channels
        for i in range(20):
            manager.subscribe("client1", f"session:test-{i}")

        # Verify subscription state
        assert len(manager.subscriptions["client1"]) == 20

        # Broadcast to one channel
        event = {"type": "session.progress"}
        await manager.broadcast_to_channel("session:test-10", event)

        # Should receive exactly one event
        mock_client.send_text.assert_called_once()

