"""Type-safe event publishing for cross-pod event distribution."""

import json
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tarsy.models.event_models import BaseEvent
from tarsy.repositories.event_repository import EventRepository

logger = logging.getLogger(__name__)


class EventPublisher:
    """
    Publishes events to database and broadcasts via NOTIFY.

    Uses EventRepository for type-safe persistence, with PostgreSQL NOTIFY
    for real-time broadcast. SQLite mode relies on polling for delivery.
    """

    def __init__(self, event_repo: EventRepository):
        """
        Initialize event publisher with repository.

        Args:
            event_repo: EventRepository instance for database operations
        """
        self.event_repo = event_repo

    async def publish(self, channel: str, event: BaseEvent) -> int:
        """
        Publish event to channel.

        Args:
            channel: Channel name (e.g., 'sessions', 'session:abc-123')
            event: Pydantic event model (validates at publish time)

        Returns:
            Event ID for event tracking and catchup

        Raises:
            ValidationError: If event model validation fails
            SQLAlchemyError: If database operation fails

        Example:
            ```python
            from tarsy.models.event_models import SessionStartedEvent

            event = SessionStartedEvent(
                session_id="abc-123",
                alert_type="security_incident"
            )
            event_id = await publisher.publish(EventChannel.SESSIONS, event)
            ```
        """
        # Serialize Pydantic model to dict (already validated)
        event_dict = event.model_dump()

        # 1. Persist event using repository (type-safe, testable)
        db_event = await self.event_repo.create_event(
            channel=channel, payload=event_dict
        )

        # 2. Broadcast via NOTIFY (PostgreSQL only)
        # Detect database type to choose appropriate delivery mechanism
        db_dialect = self.event_repo.session.bind.dialect.name

        if db_dialect == "postgresql":
            # PostgreSQL: Use NOTIFY for real-time broadcast
            # Add event ID to payload for event catchup
            notify_payload = {**event_dict, "id": db_event.id}
            notify_payload_json = json.dumps(notify_payload)

            # NOTIFY is database-specific, no ORM abstraction exists
            # Using text() is the standard SQLAlchemy approach
            # Quote channel identifier and escape internal double quotes (SQL identifier rules)
            # Use parameter binding for payload to prevent SQL injection
            channel_escaped = channel.replace('"', '""')
            notify_sql = text(f'NOTIFY "{channel_escaped}", :payload')
            await self.event_repo.session.execute(
                notify_sql, {"payload": notify_payload_json}
            )
            # Note: No try/except - NOTIFY failures on PostgreSQL are real errors
        else:
            # SQLite: Polling handles delivery (see SQLiteEventListener)
            logger.debug(
                f"Event {db_event.id} created on '{channel}' (SQLite polling mode)"
            )

        # Commit transaction (event creation + NOTIFY if PostgreSQL)
        await self.event_repo.session.commit()

        logger.debug(f"Published event to '{channel}': {event.type} (id={db_event.id})")

        return db_event.id


async def publish_event(
    session: AsyncSession, channel: str, event: BaseEvent
) -> int:
    """
    Convenience function for type-safe event publishing.

    Args:
        session: Database session
        channel: Event channel
        event: Pydantic event model

    Returns:
        Event ID

    Example:
        ```python
        from tarsy.models.event_models import LLMInteractionEvent
        from tarsy.services.events.channels import EventChannel

        event = LLMInteractionEvent(
            session_id='abc-123',
            interaction_id='int-456',
            stage_id='stage-789'
        )

        event_id = await publish_event(
            db_session,
            EventChannel.session_details('abc-123'),
            event
        )
        ```
    """
    # Create repository and publisher for one-off usage
    event_repo = EventRepository(session)
    publisher = EventPublisher(event_repo)

    return await publisher.publish(channel, event)

