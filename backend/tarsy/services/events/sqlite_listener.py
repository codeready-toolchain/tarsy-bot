"""SQLite polling event listener for development mode."""

import asyncio
import logging
from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from .base import EventListener

logger = logging.getLogger(__name__)


class SQLiteEventListener(EventListener):
    """SQLite-based event listener using polling (for dev/testing)."""

    def __init__(self, database_url: str, poll_interval: float = 0.5):
        """
        Initialize SQLite event listener.

        Args:
            database_url: SQLite database URL
            poll_interval: Polling interval in seconds (default: 0.5)
        """
        super().__init__()
        self.database_url = database_url
        self.poll_interval = poll_interval
        self.running = False
        self.polling_task: Optional[asyncio.Task] = None
        self.last_event_id: Dict[str, int] = {}
        self.engine: Optional[AsyncEngine] = None

    async def start(self) -> None:
        """Start polling background task."""
        self.engine = create_async_engine(self.database_url)
        self.running = True
        self.polling_task = asyncio.create_task(self._poll_loop())

        logger.warning(
            f"Using SQLite polling for events (interval: {self.poll_interval}s). "
            "For production, use PostgreSQL"
        )

    async def stop(self) -> None:
        """Stop polling task."""
        self.running = False

        if self.polling_task:
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                pass

        if self.engine:
            await self.engine.dispose()

        logger.info("SQLite event listener stopped")

    async def _register_channel(self, channel: str) -> None:
        """Initialize tracking for new channel."""
        self.last_event_id[channel] = 0
        logger.info(f"Subscribed to SQLite channel: {channel} (polling)")

    async def _poll_loop(self) -> None:
        """Background task that polls database periodically."""
        while self.running:
            try:
                await self._poll_events()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Back off on errors

    async def _poll_events(self) -> None:
        """Poll database for new events on all channels using repository."""
        if not self.engine:
            return

        async with self.engine.begin() as conn:
            # Create async session from connection
            from tarsy.repositories.event_repository import EventRepository

            async_session = AsyncSession(bind=conn, expire_on_commit=False)
            event_repo = EventRepository(async_session)

            for channel in self.callbacks.keys():
                last_id = self.last_event_id.get(channel, 0)

                try:
                    # Query for new events using repository (type-safe)
                    events = await event_repo.get_events_after(
                        channel=channel, after_id=last_id, limit=100
                    )

                    # Process new events
                    for event in events:
                        # Event.payload already contains the event dict
                        event_data = event.payload
                        # Include event_id for client tracking
                        event_data["id"] = event.id

                        await self._dispatch_to_callbacks(channel, event_data)
                        self.last_event_id[channel] = event.id

                except Exception as e:
                    logger.error(f"Error polling events on '{channel}': {e}")

