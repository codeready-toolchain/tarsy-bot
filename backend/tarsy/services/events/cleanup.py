"""Background service for cleaning up old events from the events table."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from tarsy.repositories.event_repository import EventRepository

logger = logging.getLogger(__name__)


class EventCleanupService:
    """
    Periodically cleans up old events from events table.

    Runs as background task on each pod (idempotent - multiple pods
    running cleanup simultaneously is safe).
    Uses EventRepository for type-safe database operations.
    """

    def __init__(
        self,
        db_session_factory: Callable[[], AsyncSession],
        retention_hours: int = 24,
        cleanup_interval_hours: int = 6,
    ):
        """
        Initialize event cleanup service.

        Args:
            db_session_factory: Async context manager that yields database session
            retention_hours: Keep events for N hours (default: 24)
            cleanup_interval_hours: Run cleanup every N hours (default: 6)
        """
        self.db_session_factory = db_session_factory
        self.retention_hours = retention_hours
        self.cleanup_interval_hours = cleanup_interval_hours

        self.cleanup_task: Optional[asyncio.Task] = None
        self.running = False

    async def start(self) -> None:
        """Start background cleanup task."""
        self.running = True
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info(
            f"Event cleanup service started "
            f"(retention: {self.retention_hours}h, "
            f"interval: {self.cleanup_interval_hours}h)"
        )

    async def stop(self) -> None:
        """Stop cleanup task gracefully."""
        self.running = False

        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("Event cleanup service stopped")

    async def _cleanup_loop(self) -> None:
        """Background task that runs cleanup periodically."""
        while self.running:
            try:
                await self._cleanup_old_events()

                # Wait until next cleanup
                await asyncio.sleep(self.cleanup_interval_hours * 3600)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}", exc_info=True)
                # Back off on errors to avoid tight error loops
                await asyncio.sleep(300)  # Wait 5 minutes

    async def _cleanup_old_events(self) -> None:
        """Delete events older than retention period using repository."""
        try:
            async with self.db_session_factory() as session:
                # Create repository instance
                event_repo = EventRepository(session)

                # Calculate cutoff time (use UTC for consistency)
                # Remove timezone info to match database column (TIMESTAMP WITHOUT TIME ZONE)
                cutoff_time = (datetime.now(timezone.utc) - timedelta(
                    hours=self.retention_hours
                )).replace(tzinfo=None)

                # Delete old events using repository (type-safe)
                deleted_count = await event_repo.delete_events_before(cutoff_time)

                await session.commit()

                if deleted_count > 0:
                    logger.info(
                        f"Cleaned up {deleted_count} event(s) older than "
                        f"{self.retention_hours} hours"
                    )
                else:
                    logger.debug("No old events to clean up")

        except Exception as e:
            logger.error(f"Failed to cleanup old events: {e}", exc_info=True)
            raise

