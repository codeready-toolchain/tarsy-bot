"""
Integration tests for event system components.

These tests use in-memory SQLite databases to avoid file system artifacts
that could interfere with e2e tests.
"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tarsy.models.db_models import Event, SQLModel
from tarsy.repositories.event_repository import EventRepository
from tarsy.services.events.cleanup import EventCleanupService
from tarsy.services.events.publisher import EventPublisher
from tarsy.models.event_models import SessionCreatedEvent


@pytest_asyncio.fixture
async def async_test_engine():
    """Create an in-memory async database engine for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_test_session_factory(async_test_engine):
    """Create an async session factory for testing."""
    return async_sessionmaker(
        async_test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )


@pytest.mark.integration
class TestEventCleanupServiceIntegration:
    """Integration tests for EventCleanupService."""

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_events(self, async_test_session_factory):
        """Test that cleanup removes old events."""
        async with async_test_session_factory() as session:
            old_event = Event(
                channel="test",
                payload={"type": "test", "data": {}},
                created_at=datetime.now(timezone.utc) - timedelta(hours=25)
            )
            session.add(old_event)
            
            recent_event = Event(
                channel="test",
                payload={"type": "test", "data": {}},
                created_at=datetime.now(timezone.utc) - timedelta(hours=1)
            )
            session.add(recent_event)
            await session.commit()
        
        service = EventCleanupService(
            async_test_session_factory,
            retention_hours=24,
            cleanup_interval_hours=6
        )
        await service._cleanup_old_events()
        
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            events = await repo.get_events_after("test", after_id=0, limit=100)
            assert len(events) == 1

    @pytest.mark.asyncio
    async def test_cleanup_with_custom_retention(self, async_test_session_factory):
        """Test cleanup respects custom retention period."""
        async with async_test_session_factory() as session:
            event_25h = Event(
                channel="test",
                payload={"type": "test", "data": {"age": "25h"}},
                created_at=datetime.now(timezone.utc) - timedelta(hours=25)
            )
            session.add(event_25h)
            
            event_50h = Event(
                channel="test",
                payload={"type": "test", "data": {"age": "50h"}},
                created_at=datetime.now(timezone.utc) - timedelta(hours=50)
            )
            session.add(event_50h)
            await session.commit()
        
        service = EventCleanupService(
            async_test_session_factory,
            retention_hours=48,
            cleanup_interval_hours=6
        )
        await service._cleanup_old_events()
        
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            events = await repo.get_events_after("test", after_id=0, limit=100)
            assert len(events) == 1
            assert events[0].payload["data"]["age"] == "25h"


@pytest.mark.integration
class TestEventPublisherIntegration:
    """Integration tests for EventPublisher."""

    @pytest.mark.asyncio
    async def test_publish_event_persists(self, async_test_session_factory):
        """Test that publishing persists event to database."""
        event = SessionCreatedEvent(
            session_id="test-123",
            alert_type="test",
            timestamp_us=int(datetime.now(timezone.utc).timestamp() * 1_000_000)
        )
        
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            publisher = EventPublisher(repo)
            event_id = await publisher.publish("sessions", event)
            assert event_id > 0
        
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            events = await repo.get_events_after("sessions", after_id=0, limit=10)
            assert len(events) == 1
            assert events[0].payload["type"] == "session.created"
            assert events[0].payload["session_id"] == "test-123"

    @pytest.mark.asyncio
    async def test_publish_maintains_order(self, async_test_session_factory):
        """Test that multiple events maintain order."""
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
            assert event_ids[i] < event_ids[i + 1]


@pytest.mark.integration
class TestEventRepositoryIntegration:
    """Integration tests for EventRepository."""

    @pytest.mark.asyncio
    async def test_catchup_mechanism(self, async_test_session_factory):
        """Test catchup retrieves events after specific ID."""
        async with async_test_session_factory() as session:
            for i in range(5):
                event = Event(
                    channel="test",
                    payload={"type": "test", "data": {"index": i}},
                    created_at=datetime.now(timezone.utc)
                )
                session.add(event)
            await session.commit()
        
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            first_batch = await repo.get_events_after("test", after_id=0, limit=2)
            assert len(first_batch) == 2
            last_id = first_batch[-1].id
        
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            remaining = await repo.get_events_after("test", after_id=last_id, limit=10)
            assert len(remaining) == 3

    @pytest.mark.asyncio
    async def test_channel_isolation(self, async_test_session_factory):
        """Test that different channels are isolated."""
        async with async_test_session_factory() as session:
            for channel in ["channel_a", "channel_b"]:
                for i in range(3):
                    event = Event(
                        channel=channel,
                        payload={"type": "test", "data": {"channel": channel}},
                        created_at=datetime.now(timezone.utc)
                    )
                    session.add(event)
            await session.commit()
        
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            events_a = await repo.get_events_after("channel_a", after_id=0, limit=10)
            events_b = await repo.get_events_after("channel_b", after_id=0, limit=10)
            
            assert len(events_a) == 3
            assert len(events_b) == 3
            
            for event in events_a:
                assert event.payload["data"]["channel"] == "channel_a"
            for event in events_b:
                assert event.payload["data"]["channel"] == "channel_b"

