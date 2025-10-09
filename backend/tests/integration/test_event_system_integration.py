"""Integration tests for event system components."""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tarsy.models.db_models import Event
from tarsy.repositories.event_repository import EventRepository
from tarsy.services.events.cleanup import EventCleanupService
from tarsy.services.events.publisher import EventPublisher
from tarsy.models.event_models import SessionCreatedEvent


@pytest.fixture
async def async_test_engine():
    """Create an async in-memory database engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    
    # Create tables
    from tarsy.models.db_models import SQLModel
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield engine
    
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
class TestEventCleanupServiceIntegration:
    """Integration tests for EventCleanupService with real database."""

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_events(self, async_test_session_factory):
        """Test that cleanup successfully deletes old events."""
        # Create some test events with different ages
        async with async_test_session_factory() as session:
            # Create old event (25 hours ago - should be deleted with 24h retention)
            old_event = Event(
                channel="test_channel",
                payload={"type": "session.created", "data": {"session_id": "old-1"}},
                created_at=datetime.now(timezone.utc) - timedelta(hours=25)
            )
            session.add(old_event)
            
            # Create another old event (30 hours ago)
            very_old_event = Event(
                channel="test_channel",
                payload={"type": "session.created", "data": {"session_id": "old-2"}},
                created_at=datetime.now(timezone.utc) - timedelta(hours=30)
            )
            session.add(very_old_event)
            
            # Create recent event (1 hour ago - should NOT be deleted)
            recent_event = Event(
                channel="test_channel",
                payload={"type": "session.created", "data": {"session_id": "recent-1"}},
                created_at=datetime.now(timezone.utc) - timedelta(hours=1)
            )
            session.add(recent_event)
            
            await session.commit()
        
        # Run cleanup with 24-hour retention
        service = EventCleanupService(
            async_test_session_factory,
            retention_hours=24,
            cleanup_interval_hours=6
        )
        
        await service._cleanup_old_events()
        
        # Verify old events deleted, recent events remain
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            remaining_events = await repo.get_events_after("test_channel", after_id=0, limit=100)
            
            # Should only have the recent event
            assert len(remaining_events) == 1
            assert remaining_events[0].payload["data"]["session_id"] == "recent-1"

    @pytest.mark.asyncio
    async def test_cleanup_with_no_old_events(self, async_test_session_factory):
        """Test cleanup when no old events exist."""
        # Create only recent events
        async with async_test_session_factory() as session:
            recent_event = Event(
                channel="test_channel",
                payload={"type": "session.created", "data": {"session_id": "recent"}},
                created_at=datetime.now(timezone.utc) - timedelta(minutes=30)
            )
            session.add(recent_event)
            await session.commit()
        
        # Run cleanup
        service = EventCleanupService(
            async_test_session_factory,
            retention_hours=24,
            cleanup_interval_hours=6
        )
        
        await service._cleanup_old_events()
        
        # Verify event still exists
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            events = await repo.get_events_after("test_channel", after_id=0, limit=100)
            assert len(events) == 1

    @pytest.mark.asyncio
    async def test_cleanup_with_custom_retention_period(self, async_test_session_factory):
        """Test cleanup respects custom retention period."""
        # Create events at different ages
        async with async_test_session_factory() as session:
            # 25 hours old - should be deleted with 24h retention but not 48h
            event_25h = Event(
                channel="test_channel",
                payload={"type": "session.created", "data": {"session_id": "25h"}},
                created_at=datetime.now(timezone.utc) - timedelta(hours=25)
            )
            session.add(event_25h)
            
            # 50 hours old - should be deleted with 48h retention
            event_50h = Event(
                channel="test_channel",
                payload={"type": "session.created", "data": {"session_id": "50h"}},
                created_at=datetime.now(timezone.utc) - timedelta(hours=50)
            )
            session.add(event_50h)
            
            await session.commit()
        
        # Run cleanup with 48-hour retention
        service = EventCleanupService(
            async_test_session_factory,
            retention_hours=48,
            cleanup_interval_hours=6
        )
        
        await service._cleanup_old_events()
        
        # Verify only 50h event deleted, 25h event remains
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            events = await repo.get_events_after("test_channel", after_id=0, limit=100)
            
            assert len(events) == 1
            assert events[0].payload["data"]["session_id"] == "25h"

    @pytest.mark.asyncio
    async def test_cleanup_with_multiple_channels(self, async_test_session_factory):
        """Test cleanup works across multiple channels."""
        # Create old events on different channels
        async with async_test_session_factory() as session:
            for channel in ["channel_1", "channel_2", "channel_3"]:
                old_event = Event(
                    channel=channel,
                    payload={"type": "test", "data": {"channel": channel}},
                    created_at=datetime.now(timezone.utc) - timedelta(hours=25)
                )
                session.add(old_event)
                
                recent_event = Event(
                    channel=channel,
                    payload={"type": "test", "data": {"channel": channel}},
                    created_at=datetime.now(timezone.utc) - timedelta(hours=1)
                )
                session.add(recent_event)
            
            await session.commit()
        
        # Run cleanup
        service = EventCleanupService(
            async_test_session_factory,
            retention_hours=24,
            cleanup_interval_hours=6
        )
        
        await service._cleanup_old_events()
        
        # Verify only recent events remain on all channels
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            
            for channel in ["channel_1", "channel_2", "channel_3"]:
                events = await repo.get_events_after(channel, after_id=0, limit=100)
                assert len(events) == 1, f"Expected 1 event on {channel}"

    @pytest.mark.asyncio
    async def test_cleanup_empty_database(self, async_test_session_factory):
        """Test cleanup on empty database doesn't fail."""
        service = EventCleanupService(
            async_test_session_factory,
            retention_hours=24,
            cleanup_interval_hours=6
        )
        
        # Should not raise any errors
        await service._cleanup_old_events()
        
        # Verify no events exist
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            events = await repo.get_events_after("any_channel", after_id=0, limit=100)
            assert len(events) == 0


@pytest.mark.integration
class TestEventPublisherIntegration:
    """Integration tests for EventPublisher with real database."""

    @pytest.mark.asyncio
    async def test_publish_event_persists_to_database(self, async_test_session_factory):
        """Test that publishing an event persists it to the database."""
        # Create a test event
        event = SessionCreatedEvent(
            session_id="test-session-123",
            alert_type="test-alert",
            timestamp_us=int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        )
        
        # Publish the event
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            publisher = EventPublisher(repo)
            event_id = await publisher.publish("sessions", event)
            
            # Should return a valid ID
            assert event_id is not None
            assert event_id > 0
        
        # Verify event was persisted
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            events = await repo.get_events_after("sessions", after_id=0, limit=10)
            
            assert len(events) == 1
            assert events[0].id == event_id
            assert events[0].channel == "sessions"
            assert events[0].payload["type"] == "session.created"
            assert events[0].payload["session_id"] == "test-session-123"
            assert events[0].payload["alert_type"] == "test-alert"
            assert "timestamp_us" in events[0].payload

    @pytest.mark.asyncio
    async def test_publish_multiple_events_maintains_order(self, async_test_session_factory):
        """Test that multiple events are stored with incrementing IDs."""
        # Publish multiple events
        event_ids = []
        
        for i in range(5):
            event = SessionCreatedEvent(
                session_id=f"session-{i}",
                alert_type="test",
                timestamp_us=int(datetime.now(timezone.utc).timestamp() * 1_000_000)
            )
            
            async with async_test_session_factory() as session:
                repo = EventRepository(session)
                publisher = EventPublisher(repo)
                event_id = await publisher.publish("sessions", event)
                event_ids.append(event_id)
        
        # Verify IDs are incrementing
        for i in range(len(event_ids) - 1):
            assert event_ids[i] < event_ids[i + 1], "Event IDs should be incrementing"
        
        # Verify all events are retrievable in order
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            events = await repo.get_events_after("sessions", after_id=0, limit=10)
            
            assert len(events) == 5
            for i, event in enumerate(events):
                assert event.payload["session_id"] == f"session-{i}"
                assert event.payload["alert_type"] == "test"
                assert event.payload["type"] == "session.created"


@pytest.mark.integration
class TestEventRepositoryIntegration:
    """Integration tests for EventRepository with real database."""

    @pytest.mark.asyncio
    async def test_get_events_after_with_catchup(self, async_test_session_factory):
        """Test catchup mechanism retrieves events after a specific ID."""
        # Create multiple events
        async with async_test_session_factory() as session:
            for i in range(5):
                event = Event(
                    channel="test_channel",
                    payload={"type": "test", "data": {"index": i}},
                    created_at=datetime.now(timezone.utc)
                )
                session.add(event)
            await session.commit()
        
        # Get first 2 events
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            first_batch = await repo.get_events_after("test_channel", after_id=0, limit=2)
            
            assert len(first_batch) == 2
            assert first_batch[0].payload["data"]["index"] == 0
            assert first_batch[1].payload["data"]["index"] == 1
            last_id = first_batch[-1].id
        
        # Get remaining events using last_id (catchup)
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            remaining = await repo.get_events_after("test_channel", after_id=last_id, limit=10)
            
            assert len(remaining) == 3
            assert remaining[0].payload["data"]["index"] == 2
            assert remaining[1].payload["data"]["index"] == 3
            assert remaining[2].payload["data"]["index"] == 4

    @pytest.mark.asyncio
    async def test_get_events_respects_channel_isolation(self, async_test_session_factory):
        """Test that events from different channels are isolated."""
        # Create events on different channels
        async with async_test_session_factory() as session:
            for channel in ["channel_a", "channel_b"]:
                for i in range(3):
                    event = Event(
                        channel=channel,
                        payload={"type": "test", "data": {"channel": channel, "index": i}},
                        created_at=datetime.now(timezone.utc)
                    )
                    session.add(event)
            await session.commit()
        
        # Query each channel
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            
            events_a = await repo.get_events_after("channel_a", after_id=0, limit=10)
            events_b = await repo.get_events_after("channel_b", after_id=0, limit=10)
            
            # Each channel should have exactly 3 events
            assert len(events_a) == 3
            assert len(events_b) == 3
            
            # Verify channel isolation
            for event in events_a:
                assert event.payload["data"]["channel"] == "channel_a"
            
            for event in events_b:
                assert event.payload["data"]["channel"] == "channel_b"

