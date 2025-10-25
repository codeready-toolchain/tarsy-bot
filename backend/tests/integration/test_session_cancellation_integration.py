"""
Integration tests for session cancellation with real database.

Tests the complete cancellation flow including database operations,
event publishing, and multi-pod coordination simulation.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession, SQLModel
from tarsy.repositories.event_repository import EventRepository
from tarsy.services.events.channels import EventChannel
from tarsy.services.events.event_helpers import publish_cancel_request, publish_session_cancelled
from tarsy.utils.timestamp import now_us


@pytest_asyncio.fixture
async def async_test_engine():
    """Create an in-memory async database engine for testing."""
    from tarsy import database
    
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    # Set the global async engine and session factory for tests
    # This allows event_helpers functions to work in integration tests
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    database.init_db._async_engine = engine
    database.init_db._async_session_factory = session_factory
    
    yield engine
    
    # Cleanup
    database.init_db._async_engine = None
    database.init_db._async_session_factory = None
    await engine.dispose()


@pytest_asyncio.fixture
async def async_test_session_factory(async_test_engine):
    """Create an async session factory for testing."""
    from tarsy import database
    return database.init_db._async_session_factory


@pytest_asyncio.fixture
async def test_session_in_db(async_test_session_factory):
    """Create a test session in the database."""
    session_id = "integration-test-session"
    
    async with async_test_session_factory() as session:
        test_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.IN_PROGRESS.value,
            started_at_us=now_us(),
            chain_id="test-chain-1"
        )
        session.add(test_session)
        await session.commit()
    
    return session_id


@pytest.mark.integration
class TestSessionCancellationIntegration:
    """Integration tests for session cancellation with real database."""
    
    @pytest.mark.asyncio
    async def test_cancel_request_event_published_to_database(
        self, async_test_session_factory, test_session_in_db
    ) -> None:
        """Test that cancel request event is published to database."""
        session_id = test_session_in_db
        
        # Publish cancel request
        await publish_cancel_request(session_id)
        
        # Verify event was published to cancellations channel
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            events = await repo.get_events_after(EventChannel.CANCELLATIONS, after_id=0, limit=10)
            
            assert len(events) > 0
            latest_event = events[-1]
            assert latest_event.payload["type"] == "session.cancel_requested"
            assert latest_event.payload["session_id"] == session_id
    
    @pytest.mark.asyncio
    async def test_cancelled_event_published_to_sessions_channel(
        self, async_test_session_factory, test_session_in_db
    ) -> None:
        """Test that cancelled event is published to sessions channel."""
        session_id = test_session_in_db
        
        # Publish cancelled event
        await publish_session_cancelled(session_id)
        
        # Verify event was published to sessions channel
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            events = await repo.get_events_after(EventChannel.SESSIONS, after_id=0, limit=10)
            
            assert len(events) > 0
            latest_event = events[-1]
            assert latest_event.payload["type"] == "session.cancelled"
            assert latest_event.payload["session_id"] == session_id
            assert latest_event.payload["status"] == "cancelled"
    
    @pytest.mark.asyncio
    async def test_cancelled_event_published_to_session_specific_channel(
        self, async_test_session_factory, test_session_in_db
    ) -> None:
        """Test that cancelled event is published to session-specific channel."""
        session_id = test_session_in_db
        
        # Publish cancelled event
        await publish_session_cancelled(session_id)
        
        # Verify event was published to session-specific channel
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            session_channel = f"session:{session_id}"
            events = await repo.get_events_after(session_channel, after_id=0, limit=10)
            
            assert len(events) > 0
            latest_event = events[-1]
            assert latest_event.payload["type"] == "session.cancelled"
            assert latest_event.payload["session_id"] == session_id
