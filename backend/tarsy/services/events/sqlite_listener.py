"""SQLite polling event listener for development mode."""

import asyncio
import logging
from typing import Dict, Optional

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
        # Convert sqlite:// URL to sqlite+aiosqlite:// for async support
        async_url = self.database_url
        if not async_url.startswith('sqlite+aiosqlite://'):
            # Handle both sqlite:// and sqlite:/// formats
            if async_url.startswith('sqlite:///'):
                async_url = async_url.replace('sqlite:///', 'sqlite+aiosqlite:///')
            elif async_url.startswith('sqlite://'):
                async_url = async_url.replace('sqlite://', 'sqlite+aiosqlite://')
        
        self.engine = create_async_engine(async_url)
        self.running = True
        self.polling_task = asyncio.create_task(self._poll_loop())
        
        # Start the universal cleanup task from base class
        await self._start_cleanup_task()

        logger.warning(
            f"Using SQLite polling for events (interval: {self.poll_interval}s). "
            "For production, use PostgreSQL"
        )

    async def stop(self) -> None:
        """Stop polling task."""
        self.running = False
        
        # Stop the universal cleanup task from base class
        await self._stop_cleanup_task()

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
    
    async def _cleanup_channel(self, channel: str) -> None:
        """Clean up tracking when channel is removed."""
        if channel in self.last_event_id:
            del self.last_event_id[channel]
            logger.info(f"Cleaned up tracking for channel: {channel}")

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

        # Log active channel count for monitoring connection leaks
        active_channels = [ch for ch in self.callbacks.keys() if self.callbacks.get(ch)]
        if active_channels:
            logger.debug(f"Polling {len(active_channels)} active channel(s): {active_channels}")

        async with self.engine.begin() as conn:
            # Create async session from connection
            from tarsy.repositories.event_repository import EventRepository

            async_session = AsyncSession(bind=conn, expire_on_commit=False)
            event_repo = EventRepository(async_session)

            for channel in list(self.callbacks.keys()):  # Use list() for safe iteration during deletion
                # Skip channels with no callbacks (safety check)
                if not self.callbacks.get(channel):
                    logger.warning(f"Found channel '{channel}' with no callbacks - skipping")
                    continue
                    
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

