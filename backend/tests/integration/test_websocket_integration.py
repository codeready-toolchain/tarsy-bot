"""
Integration tests for WebSocket system.

Tests the complete flow: EventPublisher → EventListener → WebSocket → Clients

These tests verify the REAL integration between:
1. Database event publishing (publish_event)
2. EventListener (SQLite polling or PostgreSQL NOTIFY)
3. WebSocketConnectionManager (broadcasting)
4. WebSocket clients (receiving events)
"""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tarsy.models.db_models import SQLModel
from tarsy.models.event_models import SessionCompletedEvent, SessionStartedEvent
from tarsy.services.events.channels import EventChannel
from tarsy.services.events.manager import EventSystemManager
from tarsy.services.events.publisher import publish_event
from tarsy.services.websocket_connection_manager import WebSocketConnectionManager


@pytest.fixture
async def test_db_path(tmp_path):
    """Create a temporary file path for test database."""
    return tmp_path / "test_websocket_integration.db"


@pytest.fixture
async def async_test_engine(test_db_path):
    """
    Create an async test engine using file-based SQLite.
    
    IMPORTANT: Must use file-based SQLite (not :memory:) so that multiple
    connections (test session and EventListener) can share the same database.
    """
    database_url = f"sqlite:///{test_db_path}"
    async_url = f"sqlite+aiosqlite:///{test_db_path}"
    
    engine = create_async_engine(async_url, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    
    await engine.dispose()
    
    # Clean up test database file
    if test_db_path.exists():
        test_db_path.unlink()


@pytest.fixture
async def async_test_session_factory(async_test_engine):
    """Create an async session factory for testing."""
    return async_sessionmaker(
        async_test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )


@pytest.fixture
async def event_system(test_db_path, async_test_session_factory):
    """
    Create and start a real EventSystemManager for integration tests.
    
    This includes:
    - Real SQLite event listener with polling
    - Event cleanup service
    - Proper lifecycle management
    
    Uses file-based SQLite so EventListener and test session share same DB.
    """
    # Use file-based database URL for shared access
    database_url = f"sqlite:///{test_db_path}"
    
    system = EventSystemManager(
        database_url=database_url,
        db_session_factory=async_test_session_factory,
        event_retention_hours=1,
        event_cleanup_interval_hours=24,  # Don't run during tests
    )
    
    # Create listener with faster polling for tests
    from tarsy.services.events.factory import create_event_listener
    listener = create_event_listener(database_url)
    if hasattr(listener, 'poll_interval'):
        listener.poll_interval = 0.1  # 100ms polling for tests
    
    system.event_listener = listener
    await system.event_listener.start()
    
    yield system
    
    # Cleanup
    await system.stop()


@pytest.mark.integration
class TestWebSocketEventListenerIntegration:
    """Test REAL integration between EventListener and WebSocket broadcasting."""

    @pytest.mark.asyncio
    async def test_event_published_to_db_broadcasts_to_websocket_clients(
        self, event_system, async_test_session_factory
    ):
        """
        Test that events published to database are broadcast to WebSocket clients.
        
        This is a REAL integration test:
        1. Publish event to database (via publish_event)
        2. SQLite EventListener polls and detects new event
        3. EventListener calls registered WebSocket callback
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

        # Subscribe clients to connection manager
        manager.subscribe("client1", EventChannel.SESSIONS)
        manager.subscribe("client2", EventChannel.SESSIONS)
        manager.subscribe("client3", "session:test-123")

        # Register WebSocket callback with EventListener (THIS IS THE KEY!)
        # This is what the websocket_controller does
        async def sessions_callback(event_dict: dict) -> None:
            await manager.broadcast_to_channel(EventChannel.SESSIONS, event_dict)

        event_listener = event_system.get_listener()
        await event_listener.subscribe(EventChannel.SESSIONS, sessions_callback)

        # Publish event to database
        event = SessionStartedEvent(
            session_id="test-123",
            alert_type="kubernetes"
        )

        async with async_test_session_factory() as session:
            await publish_event(session, EventChannel.SESSIONS, event)
            await session.commit()

        # Wait for EventListener to poll and detect the event
        # SQLite polls every 0.1s in tests, give it enough time
        await asyncio.sleep(0.3)

        # Verify WebSocket clients received the event via real EventListener
        # Note: EventListener adds 'id' field from database, so we check call was made
        # and verify the content contains expected fields
        assert mock_ws1.send_text.call_count == 1
        assert mock_ws2.send_text.call_count == 1
        mock_ws3.send_text.assert_not_called()  # Not subscribed to sessions channel
        
        # Verify the event content (EventListener adds 'id' from DB)
        received_event = json.loads(mock_ws1.send_text.call_args[0][0])
        assert received_event["type"] == "session.started"
        assert received_event["session_id"] == "test-123"
        assert received_event["alert_type"] == "kubernetes"
        assert "id" in received_event  # Added by EventListener from DB

        # Cleanup
        await event_listener.unsubscribe(EventChannel.SESSIONS, sessions_callback)

    @pytest.mark.asyncio
    async def test_dual_channel_publishing_reaches_correct_subscribers(
        self, event_system, async_test_session_factory
    ):
        """
        Test that events published to both channels reach appropriate subscribers.
        
        Real integration test: event_helpers publishes to both 'sessions' and 
        'session:{id}' channels, EventListener detects both, and appropriate
        WebSocket clients receive the events.
        """
        manager = WebSocketConnectionManager()
        mock_dashboard = AsyncMock()  # Subscribed to global 'sessions'
        mock_detail_view = AsyncMock()  # Subscribed to specific 'session:test-123'

        await manager.connect("dashboard", mock_dashboard)
        await manager.connect("detail", mock_detail_view)

        manager.subscribe("dashboard", EventChannel.SESSIONS)
        manager.subscribe("detail", "session:test-123")

        # Register callbacks with EventListener for both channels
        async def sessions_callback(event_dict: dict) -> None:
            await manager.broadcast_to_channel(EventChannel.SESSIONS, event_dict)

        async def session_specific_callback(event_dict: dict) -> None:
            await manager.broadcast_to_channel("session:test-123", event_dict)

        event_listener = event_system.get_listener()
        await event_listener.subscribe(EventChannel.SESSIONS, sessions_callback)
        await event_listener.subscribe("session:test-123", session_specific_callback)

        # Create event
        event = SessionStartedEvent(
            session_id="test-123",
            alert_type="kubernetes"
        )

        # Publish to both channels (this is what event_helpers does)
        async with async_test_session_factory() as session:
            await publish_event(session, EventChannel.SESSIONS, event)
            await publish_event(session, "session:test-123", event)
            await session.commit()

        # Wait for EventListener polling
        await asyncio.sleep(0.3)

        # Both should receive the event via real EventListener
        assert mock_dashboard.send_text.call_count == 1
        assert mock_detail_view.send_text.call_count == 1
        
        # Verify event content
        dashboard_event = json.loads(mock_dashboard.send_text.call_args[0][0])
        detail_event = json.loads(mock_detail_view.send_text.call_args[0][0])
        
        assert dashboard_event["type"] == "session.started"
        assert dashboard_event["session_id"] == "test-123"
        assert detail_event["type"] == "session.started"
        assert detail_event["session_id"] == "test-123"

        # Cleanup
        await event_listener.unsubscribe(EventChannel.SESSIONS, sessions_callback)
        await event_listener.unsubscribe("session:test-123", session_specific_callback)

    @pytest.mark.asyncio
    async def test_multiple_events_to_same_channel(
        self, event_system, async_test_session_factory
    ):
        """
        Test multiple events broadcast to same channel.
        
        Real integration test: publishes multiple events to database,
        EventListener detects all of them, WebSocket client receives all.
        """
        manager = WebSocketConnectionManager()
        mock_client = AsyncMock()

        await manager.connect("client1", mock_client)
        manager.subscribe("client1", EventChannel.SESSIONS)

        # Register callback with EventListener
        async def sessions_callback(event_dict: dict) -> None:
            await manager.broadcast_to_channel(EventChannel.SESSIONS, event_dict)

        event_listener = event_system.get_listener()
        await event_listener.subscribe(EventChannel.SESSIONS, sessions_callback)

        # Publish multiple events to database
        events = [
            SessionStartedEvent(session_id="test-1", alert_type="kubernetes"),
            SessionCompletedEvent(session_id="test-1", result="success"),
            SessionStartedEvent(session_id="test-2", alert_type="kubernetes"),
        ]

        async with async_test_session_factory() as session:
            for event in events:
                await publish_event(session, EventChannel.SESSIONS, event)
            await session.commit()

        # Wait for EventListener to poll and detect all events
        await asyncio.sleep(0.5)

        # Client should receive all events via real EventListener
        assert mock_client.send_text.call_count == 3

        # Cleanup
        await event_listener.unsubscribe(EventChannel.SESSIONS, sessions_callback)

    @pytest.mark.asyncio
    async def test_client_reconnection_and_catchup(
        self, async_test_session_factory
    ):
        """
        Test client reconnection and event catchup mechanism.
        
        Real integration test: tests EventRepository fetching missed events
        from database for client catchup after reconnection.
        """
        from tarsy.repositories.event_repository import EventRepository

        # Publish some events while client is disconnected
        event1 = SessionStartedEvent(session_id="test-1", alert_type="kubernetes")
        event2 = SessionStartedEvent(session_id="test-2", alert_type="kubernetes")

        async with async_test_session_factory() as session:
            await publish_event(session, EventChannel.SESSIONS, event1)
            await publish_event(session, EventChannel.SESSIONS, event2)
            await session.commit()

        # Client reconnects and requests catchup from database
        async with async_test_session_factory() as session:
            event_repo = EventRepository(session)
            missed_events = await event_repo.get_events_after(
                channel=EventChannel.SESSIONS,
                after_id=0,
                limit=100
            )

            # Should retrieve both events from database
            assert len(missed_events) >= 2
            assert any(e.payload.get("session_id") == "test-1" for e in missed_events)
            assert any(e.payload.get("session_id") == "test-2" for e in missed_events)

