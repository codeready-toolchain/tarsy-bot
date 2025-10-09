"""Event repository for database operations."""

import logging
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from tarsy.models.db_models import Event

logger = logging.getLogger(__name__)


class EventRepository:
    """
    Repository for event table operations.

    Provides type-safe database access for event CRUD operations,
    following tarsy's repository pattern adapted for async operations.
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize event repository with database session.

        Args:
            session: Async database session for operations
        """
        self.session = session

    async def create_event(self, channel: str, payload: dict) -> Event:
        """
        Create and persist a new event.

        Args:
            channel: Event channel name
            payload: Event payload as dictionary

        Returns:
            Created Event with generated ID and timestamp

        Raises:
            SQLAlchemyError: If database operation fails
        """
        try:
            # Create event instance (created_at set by database default)
            event = Event(channel=channel, payload=payload)

            self.session.add(event)
            await self.session.flush()  # Get generated ID without committing
            await self.session.refresh(event)  # Load database defaults

            logger.debug(f"Created event {event.id} on channel '{channel}'")

            return event

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to create event on '{channel}': {e}")
            raise

    async def get_events_after(
        self, channel: str, after_id: int, limit: int = 100
    ) -> list[Event]:
        """
        Get events on channel after specified ID (for catchup).

        Args:
            channel: Event channel to query
            after_id: Return events with ID greater than this
            limit: Maximum number of events to return (default: 100)

        Returns:
            List of Event objects ordered by ID ascending
        """
        try:
            statement = (
                select(Event)
                .where(Event.channel == channel)
                .where(Event.id > after_id)
                .order_by(Event.id.asc())
                .limit(limit)
            )

            result = await self.session.execute(statement)
            events = result.scalars().all()

            logger.debug(
                f"Retrieved {len(events)} event(s) on '{channel}' after ID {after_id}"
            )

            return list(events)

        except Exception as e:
            logger.error(f"Failed to get events on '{channel}' after {after_id}: {e}")
            raise

    async def delete_events_before(self, before_time: datetime) -> int:
        """
        Delete events older than specified time (for cleanup).

        Args:
            before_time: Delete events created before this timestamp

        Returns:
            Number of events deleted

        Raises:
            SQLAlchemyError: If database operation fails
        """
        try:
            statement = delete(Event).where(Event.created_at < before_time)
            result = await self.session.execute(statement)

            deleted_count = result.rowcount

            if deleted_count > 0:
                logger.debug(f"Deleted {deleted_count} event(s) before {before_time}")

            return deleted_count

        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to delete events before {before_time}: {e}")
            raise

