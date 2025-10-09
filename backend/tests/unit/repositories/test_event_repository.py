"""Unit tests for EventRepository."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from tarsy.repositories.event_repository import EventRepository
from tarsy.models.db_models import Event


@pytest.mark.unit
class TestEventRepositoryCreate:
    """Test EventRepository.create_event method."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock(spec=AsyncSession)
        session.add = Mock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create EventRepository with mocked session."""
        return EventRepository(mock_session)

    @pytest.mark.asyncio
    async def test_create_event_success(self, repository, mock_session):
        """Test successful event creation."""
        channel = "test.channel"
        payload = {"key": "value", "count": 42}

        event = await repository.create_event(channel, payload)

        # Verify event was created correctly
        assert event.channel == channel
        assert event.payload == payload

        # Verify database operations
        mock_session.add.assert_called_once()
        added_event = mock_session.add.call_args[0][0]
        assert isinstance(added_event, Event)
        assert added_event.channel == channel
        assert added_event.payload == payload

        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(added_event)

    @pytest.mark.asyncio
    async def test_create_event_with_empty_payload(self, repository, mock_session):
        """Test creating event with empty payload."""
        channel = "test.channel"
        payload = {}

        event = await repository.create_event(channel, payload)

        assert event.channel == channel
        assert event.payload == {}
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_event_with_none_payload(self, repository, mock_session):
        """Test creating event with None payload."""
        channel = "test.channel"

        event = await repository.create_event(channel, None)

        assert event.channel == channel
        assert event.payload is None
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_event_with_complex_payload(self, repository, mock_session):
        """Test creating event with complex nested payload."""
        channel = "test.channel"
        payload = {
            "session_id": "sess-123",
            "metadata": {
                "nested": {"value": 42},
                "list": [1, 2, 3]
            },
            "tags": ["tag1", "tag2"]
        }

        event = await repository.create_event(channel, payload)

        assert event.channel == channel
        assert event.payload == payload
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_event_database_error(self, repository, mock_session):
        """Test handling of database errors during creation."""
        mock_session.flush.side_effect = OperationalError("DB error", None, None)

        with pytest.raises(OperationalError, match="DB error"):
            await repository.create_event("test.channel", {"key": "value"})

        # Verify rollback was called
        mock_session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_event_integrity_error(self, repository, mock_session):
        """Test handling of integrity constraint violations."""
        mock_session.flush.side_effect = IntegrityError("Constraint violation", None, None)

        with pytest.raises(IntegrityError, match="Constraint violation"):
            await repository.create_event("test.channel", {"key": "value"})

        mock_session.rollback.assert_awaited_once()


@pytest.mark.unit
class TestEventRepositoryGetEventsAfter:
    """Test EventRepository.get_events_after method."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock(spec=AsyncSession)
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create EventRepository with mocked session."""
        return EventRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_events_after_with_results(self, repository, mock_session):
        """Test retrieving events after a specific ID."""
        channel = "test.channel"
        after_id = 10

        # Mock events
        mock_events = [
            Event(id=11, channel=channel, payload={"data": "1"}, created_at=datetime.now(timezone.utc)),
            Event(id=12, channel=channel, payload={"data": "2"}, created_at=datetime.now(timezone.utc)),
            Event(id=13, channel=channel, payload={"data": "3"}, created_at=datetime.now(timezone.utc)),
        ]

        # Mock execute result
        mock_result = AsyncMock()
        mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=mock_events)))
        mock_session.execute = AsyncMock(return_value=mock_result)

        events = await repository.get_events_after(channel, after_id)

        assert len(events) == 3
        assert all(e.id > after_id for e in events)
        assert all(e.channel == channel for e in events)
        assert events[0].id == 11
        assert events[-1].id == 13

    @pytest.mark.asyncio
    async def test_get_events_after_no_results(self, repository, mock_session):
        """Test retrieving events when none exist after the ID."""
        mock_result = AsyncMock()
        mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=[])))
        mock_session.execute = AsyncMock(return_value=mock_result)

        events = await repository.get_events_after("test.channel", 100)

        assert events == []

    @pytest.mark.asyncio
    async def test_get_events_after_zero_id(self, repository, mock_session):
        """Test retrieving all events when after_id is 0."""
        mock_events = [
            Event(id=1, channel="test", payload={}, created_at=datetime.now(timezone.utc)),
            Event(id=2, channel="test", payload={}, created_at=datetime.now(timezone.utc)),
        ]

        mock_result = AsyncMock()
        mock_result.scalars = Mock(return_value=Mock(all=Mock(return_value=mock_events)))
        mock_session.execute = AsyncMock(return_value=mock_result)

        events = await repository.get_events_after("test", 0)

        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_get_events_after_database_error(self, repository, mock_session):
        """Test handling of database errors during retrieval."""
        mock_session.execute.side_effect = OperationalError("DB connection lost", None, None)

        with pytest.raises(OperationalError, match="DB connection lost"):
            await repository.get_events_after("test.channel", 10)


@pytest.mark.unit
class TestEventRepositoryDeleteEventsBefore:
    """Test EventRepository.delete_events_before method."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock(spec=AsyncSession)
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def repository(self, mock_session):
        """Create EventRepository with mocked session."""
        return EventRepository(mock_session)

    @pytest.mark.asyncio
    async def test_delete_events_before_success(self, repository, mock_session):
        """Test successful deletion of old events."""
        cutoff_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Mock delete result
        mock_result = Mock()
        mock_result.rowcount = 42
        mock_session.execute.return_value = mock_result

        deleted_count = await repository.delete_events_before(cutoff_time)

        assert deleted_count == 42
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_events_before_no_events(self, repository, mock_session):
        """Test deletion when no events match the criteria."""
        cutoff_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        mock_result = Mock()
        mock_result.rowcount = 0
        mock_session.execute.return_value = mock_result

        deleted_count = await repository.delete_events_before(cutoff_time)

        assert deleted_count == 0
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_events_before_database_error(self, repository, mock_session):
        """Test handling of database errors during deletion."""
        cutoff_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        mock_session.execute.side_effect = OperationalError("DB error", None, None)

        with pytest.raises(OperationalError, match="DB error"):
            await repository.delete_events_before(cutoff_time)


@pytest.mark.unit
class TestEventRepositoryContextManager:
    """Test EventRepository initialization."""

    def test_repository_requires_session(self):
        """Test that EventRepository requires a session."""
        with pytest.raises(TypeError):
            EventRepository()  # Should require session parameter

    def test_repository_with_valid_session(self):
        """Test creating repository with valid session."""
        mock_session = AsyncMock(spec=AsyncSession)
        repository = EventRepository(mock_session)

        assert repository.session == mock_session
