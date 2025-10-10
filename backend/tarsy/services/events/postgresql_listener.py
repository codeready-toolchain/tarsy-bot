"""PostgreSQL LISTEN/NOTIFY event listener."""

import asyncio
import json
import logging
from typing import Optional

import asyncpg

from .base import EventListener

logger = logging.getLogger(__name__)


class PostgreSQLEventListener(EventListener):
    """
    PostgreSQL LISTEN/NOTIFY event listener.

    Maintains dedicated connection for real-time notifications.
    """

    def __init__(self, database_url: str):
        super().__init__()
        self.database_url = database_url
        self.listener_conn: Optional[asyncpg.Connection] = None

    async def start(self) -> None:
        """Create dedicated connection for LISTEN."""
        try:
            # Create separate connection (not from pool) with timeout
            # Timeout prevents hanging during startup if DB is unreachable
            self.listener_conn = await asyncio.wait_for(
                asyncpg.connect(self.database_url),
                timeout=10.0  # 10 second timeout
            )
            self.running = True
            
            # Start the universal cleanup task from base class
            await self._start_cleanup_task()
            
            logger.info("PostgreSQL event listener connection established")
        except asyncio.TimeoutError:
            logger.error(
                "Timeout connecting to PostgreSQL for event listener after 10s. "
                "Check database connectivity and credentials."
            )
            raise
        except Exception as e:
            logger.error(f"Failed to create listener connection: {e}")
            raise

    async def stop(self) -> None:
        """Close listener connection."""
        self.running = False
        
        # Stop the universal cleanup task from base class
        await self._stop_cleanup_task()
        
        if self.listener_conn:
            await self.listener_conn.close()
            logger.info("PostgreSQL event listener connection closed")

    async def _register_channel(self, channel: str) -> None:
        """Add PostgreSQL listener for channel."""
        if not self.listener_conn:
            raise RuntimeError("Listener not initialized")

        await self.listener_conn.add_listener(channel, self._handle_notification)
        logger.info(f"Subscribed to PostgreSQL channel: {channel}")
    
    async def _cleanup_channel(self, channel: str) -> None:
        """Remove PostgreSQL listener for channel."""
        if self.listener_conn:
            try:
                await self.listener_conn.remove_listener(channel, self._handle_notification)
                logger.info(f"Unsubscribed from PostgreSQL channel: {channel}")
            except Exception as e:
                logger.warning(f"Failed to remove PostgreSQL listener for {channel}: {e}")

    def _handle_notification(
        self,
        connection: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """
        Called by asyncpg when NOTIFY received.

        Args:
            connection: Connection that received notification
            pid: Process ID of notifying backend
            channel: Channel name
            payload: JSON string payload
        """
        try:
            event = json.loads(payload)
            logger.debug(f"Received event on {channel}: {event.get('type', 'unknown')}")

            # Dispatch to callbacks (async)
            asyncio.create_task(self._dispatch_to_callbacks(channel, event))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in notification: {e}")
        except Exception as e:
            logger.error(f"Error handling notification: {e}", exc_info=True)

