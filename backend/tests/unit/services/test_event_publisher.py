"""Unit tests for EventPublisher."""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from tarsy.services.events.publisher import EventPublisher, publish_event
from tarsy.models.event_models import (
    SessionCreatedEvent,
    SessionStartedEvent,
    LLMInteractionEvent,
    MCPToolCallEvent,
    StageStartedEvent,
)
from tarsy.models.db_models import Event
from tarsy.repositories.event_repository import EventRepository


@pytest.mark.unit
class TestEventPublisherPublish:
    """Test EventPublisher.publish method."""

    @pytest.fixture
    def mock_event_repo(self):
        """Create a mock EventRepository."""
        repo = Mock(spec=EventRepository)
        repo.create_event = AsyncMock()
        repo.session = Mock()
        repo.session.bind = Mock()
        repo.session.execute = AsyncMock()
        repo.session.commit = AsyncMock()
        return repo

    @pytest.fixture
    def publisher(self, mock_event_repo):
        """Create EventPublisher with mocked repository."""
        return EventPublisher(mock_event_repo)

    @pytest.mark.asyncio
    async def test_publish_session_created_event_postgresql(
        self, publisher, mock_event_repo
    ):
        """Test publishing SessionCreatedEvent to PostgreSQL."""
        # Setup PostgreSQL dialect
        mock_event_repo.session.bind.dialect.name = "postgresql"

        # Mock created event
        mock_db_event = Event(
            id=123,
            channel="sessions",
            payload={"type": "session.created", "session_id": "sess-abc"},
            created_at=datetime.now(timezone.utc),
        )
        mock_event_repo.create_event.return_value = mock_db_event

        # Create and publish event
        event = SessionCreatedEvent(session_id="sess-abc", alert_type="test_alert")
        event_id = await publisher.publish("sessions", event)

        # Verify event was persisted
        assert event_id == 123
        mock_event_repo.create_event.assert_awaited_once()
        call_args = mock_event_repo.create_event.call_args
        assert call_args[1]["channel"] == "sessions"
        assert call_args[1]["payload"]["type"] == "session.created"
        assert call_args[1]["payload"]["session_id"] == "sess-abc"

        # Verify NOTIFY was called for PostgreSQL
        mock_event_repo.session.execute.assert_awaited_once()
        call_args = mock_event_repo.session.execute.call_args
        notify_sql = str(call_args[0][0])
        # Channel name is quoted to support special characters (e.g., "session:abc-123")
        assert 'NOTIFY "sessions"' in notify_sql
        # Payload should be parameterized (not embedded in SQL)
        assert ":payload" in notify_sql
        # Verify payload parameter is passed correctly
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1] if call_args[1] else {}
        assert "payload" in params or "session.created" in str(params)

        # Verify commit
        mock_event_repo.session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publish_session_started_event_sqlite(self, publisher, mock_event_repo):
        """Test publishing SessionStartedEvent to SQLite."""
        # Setup SQLite dialect
        mock_event_repo.session.bind.dialect.name = "sqlite"

        # Mock created event
        mock_db_event = Event(
            id=456,
            channel="sessions",
            payload={"type": "session.started", "session_id": "sess-xyz", "alert_type": "test_alert"},
            created_at=datetime.now(timezone.utc),
        )
        mock_event_repo.create_event.return_value = mock_db_event

        # Create and publish event
        event = SessionStartedEvent(session_id="sess-xyz", alert_type="test_alert")
        event_id = await publisher.publish("sessions", event)

        # Verify event was persisted
        assert event_id == 456
        mock_event_repo.create_event.assert_awaited_once()

        # Verify NOTIFY was NOT called for SQLite
        mock_event_repo.session.execute.assert_not_awaited()

        # Verify commit
        mock_event_repo.session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publish_llm_interaction_event(self, publisher, mock_event_repo):
        """Test publishing LLMInteractionEvent."""
        mock_event_repo.session.bind.dialect.name = "postgresql"

        mock_db_event = Event(
            id=789,
            channel="session:sess-123",
            payload={
                "type": "llm.interaction",
                "session_id": "sess-123",
                "interaction_id": "int-456",
                "stage_id": "stage-789",
            },
            created_at=datetime.now(timezone.utc),
        )
        mock_event_repo.create_event.return_value = mock_db_event

        event = LLMInteractionEvent(
            session_id="sess-123",
            interaction_id="int-456",
            stage_id="stage-789",
        )
        event_id = await publisher.publish("session:sess-123", event)

        assert event_id == 789
        mock_event_repo.create_event.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publish_mcp_tool_call_event(self, publisher, mock_event_repo):
        """Test publishing MCPToolCallEvent."""
        mock_event_repo.session.bind.dialect.name = "postgresql"

        mock_db_event = Event(
            id=321,
            channel="session:sess-abc",
            payload={
                "type": "mcp.tool_call",
                "session_id": "sess-abc",
                "interaction_id": "int-789",
                "stage_id": "stage-456",
                "tool_name": "test_tool",
            },
            created_at=datetime.now(timezone.utc),
        )
        mock_event_repo.create_event.return_value = mock_db_event

        event = MCPToolCallEvent(
            session_id="sess-abc",
            interaction_id="int-789",
            stage_id="stage-456",
            tool_name="test_tool",
        )
        event_id = await publisher.publish("session:sess-abc", event)

        assert event_id == 321

    @pytest.mark.asyncio
    async def test_publish_stage_started_event(self, publisher, mock_event_repo):
        """Test publishing StageStartedEvent."""
        mock_event_repo.session.bind.dialect.name = "sqlite"

        mock_db_event = Event(
            id=111,
            channel="session:sess-test",
            payload={
                "type": "stage.started",
                "session_id": "sess-test",
                "stage_id": "stage-222",
                "stage_name": "test_stage",
            },
            created_at=datetime.now(timezone.utc),
        )
        mock_event_repo.create_event.return_value = mock_db_event

        event = StageStartedEvent(
            session_id="sess-test", stage_id="stage-222", stage_name="test_stage"
        )
        event_id = await publisher.publish("session:sess-test", event)

        assert event_id == 111

    @pytest.mark.asyncio
    async def test_publish_with_special_characters_in_payload(
        self, publisher, mock_event_repo
    ):
        """Test publishing event with special characters (single quotes, JSON)."""
        mock_event_repo.session.bind.dialect.name = "postgresql"

        mock_db_event = Event(
            id=999,
            channel="sessions",
            payload={"type": "session.created", "session_id": "it's-a-test"},
            created_at=datetime.now(timezone.utc),
        )
        mock_event_repo.create_event.return_value = mock_db_event

        # Event with single quote in session_id
        event = SessionCreatedEvent(
            session_id="it's-a-test", alert_type="test with 'quotes'"
        )
        event_id = await publisher.publish("sessions", event)

        # Verify NOTIFY was called (payload is now bound as parameter)
        mock_event_repo.session.execute.assert_awaited_once()
        call_args = mock_event_repo.session.execute.call_args
        notify_sql = str(call_args[0][0])
        # Verify channel is quoted
        assert 'NOTIFY "sessions"' in notify_sql
        # Verify payload is passed as parameter, not embedded in SQL
        assert ":payload" in notify_sql
        # Verify payload parameter is passed correctly (second positional arg or kwargs)
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1] if call_args[1] else {}
        assert "payload" in params or "it's-a-test" in str(params)

        assert event_id == 999

    @pytest.mark.asyncio
    async def test_publish_with_malicious_channel_name(
        self, publisher, mock_event_repo
    ):
        """Test that malicious channel names cannot cause SQL injection."""
        mock_event_repo.session.bind.dialect.name = "postgresql"

        mock_db_event = Event(
            id=888,
            channel='test"; DROP TABLE events; --',
            payload={"type": "session.created", "session_id": "sess-123"},
            created_at=datetime.now(timezone.utc),
        )
        mock_event_repo.create_event.return_value = mock_db_event

        # Attempt SQL injection via channel name
        malicious_channel = 'test"; DROP TABLE events; --'
        event = SessionCreatedEvent(session_id="sess-123", alert_type="test")
        event_id = await publisher.publish(malicious_channel, event)

        # Verify event was published
        assert event_id == 888
        mock_event_repo.session.execute.assert_awaited_once()

        # Verify that the channel is properly escaped in NOTIFY
        call_args = mock_event_repo.session.execute.call_args
        notify_sql = str(call_args[0][0])
        # Channel should be quoted and escaped (double quotes escaped as "")
        # The malicious payload should be treated as a literal identifier
        assert 'NOTIFY "test""; DROP TABLE events; --"' in notify_sql
        # Payload should be parameterized
        assert ":payload" in notify_sql
        # Verify payload parameter is passed correctly (second positional arg or kwargs)
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1] if call_args[1] else {}
        assert "payload" in params or "session.created" in str(params)

    @pytest.mark.asyncio
    async def test_publish_with_double_quotes_in_channel(
        self, publisher, mock_event_repo
    ):
        """Test that double quotes in channel names are properly escaped."""
        mock_event_repo.session.bind.dialect.name = "postgresql"

        mock_db_event = Event(
            id=777,
            channel='channel"with"quotes',
            payload={"type": "session.created", "session_id": "sess-123"},
            created_at=datetime.now(timezone.utc),
        )
        mock_event_repo.create_event.return_value = mock_db_event

        # Channel with double quotes
        channel_with_quotes = 'channel"with"quotes'
        event = SessionCreatedEvent(session_id="sess-123", alert_type="test")
        event_id = await publisher.publish(channel_with_quotes, event)

        assert event_id == 777
        mock_event_repo.session.execute.assert_awaited_once()

        # Verify double quotes are escaped as ""
        call_args = mock_event_repo.session.execute.call_args
        notify_sql = str(call_args[0][0])
        # Double quotes should be escaped by doubling them
        assert 'NOTIFY "channel""with""quotes"' in notify_sql

    @pytest.mark.asyncio
    async def test_publish_database_error_during_create(self, publisher, mock_event_repo):
        """Test handling of database errors during event creation."""
        mock_event_repo.create_event.side_effect = OperationalError(
            "DB connection lost", None, None
        )

        event = SessionCreatedEvent(session_id="sess-fail", alert_type="test")

        with pytest.raises(OperationalError, match="DB connection lost"):
            await publisher.publish("sessions", event)

        # Commit should not be called if create fails
        mock_event_repo.session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_publish_database_error_during_notify(self, publisher, mock_event_repo):
        """Test handling of database errors during NOTIFY."""
        mock_event_repo.session.bind.dialect.name = "postgresql"

        mock_db_event = Event(
            id=555,
            channel="sessions",
            payload={"type": "session.created"},
            created_at=datetime.now(timezone.utc),
        )
        mock_event_repo.create_event.return_value = mock_db_event

        # NOTIFY fails
        mock_event_repo.session.execute.side_effect = OperationalError(
            "NOTIFY failed", None, None
        )

        event = SessionCreatedEvent(session_id="sess-notify-fail", alert_type="test")

        # Should propagate NOTIFY errors
        with pytest.raises(OperationalError, match="NOTIFY failed"):
            await publisher.publish("sessions", event)

    @pytest.mark.asyncio
    async def test_publish_commit_error(self, publisher, mock_event_repo):
        """Test handling of commit errors."""
        mock_event_repo.session.bind.dialect.name = "sqlite"

        mock_db_event = Event(
            id=777,
            channel="sessions",
            payload={"type": "session.created"},
            created_at=datetime.now(timezone.utc),
        )
        mock_event_repo.create_event.return_value = mock_db_event

        mock_event_repo.session.commit.side_effect = OperationalError(
            "Commit failed", None, None
        )

        event = SessionCreatedEvent(session_id="sess-commit-fail", alert_type="test")

        with pytest.raises(OperationalError, match="Commit failed"):
            await publisher.publish("sessions", event)

    @pytest.mark.asyncio
    async def test_publish_invalid_pydantic_event(self, publisher, mock_event_repo):
        """Test that invalid Pydantic models raise ValidationError."""
        # This should be caught at event creation time, not publish time
        with pytest.raises(ValidationError):
            # Missing required field
            SessionCreatedEvent(alert_type="test")  # session_id is required


@pytest.mark.unit
class TestPublishEventConvenienceFunction:
    """Test publish_event convenience function."""

    @pytest.mark.asyncio
    async def test_publish_event_creates_publisher(self):
        """Test that publish_event creates EventPublisher internally."""
        mock_session = AsyncMock()
        mock_session.bind = Mock()
        mock_session.bind.dialect.name = "sqlite"

        # Mock the repository creation
        with patch(
            "tarsy.services.events.publisher.EventRepository"
        ) as mock_repo_class, patch(
            "tarsy.services.events.publisher.EventPublisher"
        ) as mock_publisher_class:

            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo

            mock_publisher = Mock()
            mock_publisher.publish = AsyncMock(return_value=123)
            mock_publisher_class.return_value = mock_publisher

            event = SessionCreatedEvent(session_id="sess-123", alert_type="test")
            event_id = await publish_event(mock_session, "sessions", event)

            # Verify repository was created with session
            mock_repo_class.assert_called_once_with(mock_session)

            # Verify publisher was created with repository
            mock_publisher_class.assert_called_once_with(mock_repo)

            # Verify publish was called
            mock_publisher.publish.assert_awaited_once_with("sessions", event)

            assert event_id == 123

    @pytest.mark.asyncio
    async def test_publish_event_propagates_errors(self):
        """Test that publish_event propagates errors."""
        mock_session = AsyncMock()
        mock_session.bind = Mock()

        with patch(
            "tarsy.services.events.publisher.EventRepository"
        ) as mock_repo_class, patch(
            "tarsy.services.events.publisher.EventPublisher"
        ) as mock_publisher_class:

            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo

            mock_publisher = Mock()
            mock_publisher.publish = AsyncMock(
                side_effect=OperationalError("DB error", None, None)
            )
            mock_publisher_class.return_value = mock_publisher

            event = SessionCreatedEvent(session_id="sess-fail", alert_type="test")

            with pytest.raises(OperationalError, match="DB error"):
                await publish_event(mock_session, "sessions", event)


@pytest.mark.unit
class TestEventPublisherEventSerialization:
    """Test event serialization and payload handling."""

    @pytest.fixture
    def mock_event_repo(self):
        """Create a mock EventRepository."""
        repo = Mock(spec=EventRepository)
        repo.create_event = AsyncMock()
        repo.session = Mock()
        repo.session.bind = Mock()
        repo.session.bind.dialect.name = "sqlite"
        repo.session.execute = AsyncMock()
        repo.session.commit = AsyncMock()
        return repo

    @pytest.fixture
    def publisher(self, mock_event_repo):
        """Create EventPublisher with mocked repository."""
        return EventPublisher(mock_event_repo)

    @pytest.mark.asyncio
    async def test_event_model_dump_includes_all_fields(
        self, publisher, mock_event_repo
    ):
        """Test that event.model_dump() includes all fields."""
        mock_db_event = Event(
            id=100,
            channel="sessions",
            payload={},
            created_at=datetime.now(timezone.utc),
        )
        mock_event_repo.create_event.return_value = mock_db_event

        event = LLMInteractionEvent(
            session_id="sess-123",
            interaction_id="int-456",
            stage_id="stage-789",
        )

        await publisher.publish("sessions", event)

        # Check the payload passed to create_event
        call_args = mock_event_repo.create_event.call_args
        payload = call_args[1]["payload"]

        assert payload["type"] == "llm.interaction"
        assert payload["session_id"] == "sess-123"
        assert payload["interaction_id"] == "int-456"
        assert payload["stage_id"] == "stage-789"

    @pytest.mark.asyncio
    async def test_event_with_optional_fields(self, publisher, mock_event_repo):
        """Test event with optional fields."""
        mock_db_event = Event(
            id=200,
            channel="sessions",
            payload={},
            created_at=datetime.now(timezone.utc),
        )
        mock_event_repo.create_event.return_value = mock_db_event

        # MCPToolCallEvent has optional stage_id
        event = MCPToolCallEvent(
            session_id="sess-abc",
            interaction_id="int-123",
            tool_name="tool",
            # stage_id is optional
        )

        await publisher.publish("sessions", event)

        call_args = mock_event_repo.create_event.call_args
        payload = call_args[1]["payload"]

        assert "stage_id" in payload  # Should be present (None or omitted based on Pydantic config)


@pytest.mark.unit
class TestEventPublisherChannelHandling:
    """Test channel name handling."""

    @pytest.fixture
    def mock_event_repo(self):
        """Create a mock EventRepository."""
        repo = Mock(spec=EventRepository)
        repo.create_event = AsyncMock()
        repo.session = Mock()
        repo.session.bind = Mock()
        repo.session.bind.dialect.name = "sqlite"
        repo.session.commit = AsyncMock()
        return repo

    @pytest.fixture
    def publisher(self, mock_event_repo):
        """Create EventPublisher with mocked repository."""
        return EventPublisher(mock_event_repo)

    @pytest.mark.asyncio
    async def test_publish_to_global_channel(self, publisher, mock_event_repo):
        """Test publishing to global 'sessions' channel."""
        mock_db_event = Event(
            id=1, channel="sessions", payload={}, created_at=datetime.now(timezone.utc)
        )
        mock_event_repo.create_event.return_value = mock_db_event

        event = SessionCreatedEvent(session_id="sess-123", alert_type="test")
        await publisher.publish("sessions", event)

        call_args = mock_event_repo.create_event.call_args
        assert call_args[1]["channel"] == "sessions"

    @pytest.mark.asyncio
    async def test_publish_to_session_specific_channel(self, publisher, mock_event_repo):
        """Test publishing to session-specific channel."""
        mock_db_event = Event(
            id=2,
            channel="session:sess-xyz",
            payload={},
            created_at=datetime.now(timezone.utc),
        )
        mock_event_repo.create_event.return_value = mock_db_event

        event = LLMInteractionEvent(
            session_id="sess-xyz",
            interaction_id="int-123",
            stage_id="stage-456",
        )
        await publisher.publish("session:sess-xyz", event)

        call_args = mock_event_repo.create_event.call_args
        assert call_args[1]["channel"] == "session:sess-xyz"

