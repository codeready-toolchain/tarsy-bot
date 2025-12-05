"""Event system manager for lifecycle and channel management."""

from typing import Callable, Optional

from tarsy.services.events.base import EventListener
from tarsy.services.events.cleanup import EventCleanupService
from tarsy.services.events.factory import create_event_listener
from tarsy.utils.logger import get_logger

logger = get_logger(__name__)


class EventSystemManager:
    """
    Manages event system lifecycle and channel subscriptions.

    Centralizes event listener, cleanup service, and channel management
    to keep main.py clean and follow tarsy's service pattern.
    """

    def __init__(
        self,
        database_url: str,
        db_session_factory: Callable,
        event_retention_hours: int = 24,
        event_cleanup_interval_hours: int = 6,
    ):
        """
        Initialize event system manager.

        Args:
            database_url: Database connection string
            db_session_factory: Factory for database sessions
            event_retention_hours: Event retention period (hours)
            event_cleanup_interval_hours: Cleanup interval (hours)
        """
        self.database_url = database_url
        self.db_session_factory = db_session_factory
        self.event_retention_hours = event_retention_hours
        self.event_cleanup_interval_hours = event_cleanup_interval_hours

        self.event_listener: Optional[EventListener] = None
        self.cleanup_service: Optional[EventCleanupService] = None
        self._channel_handlers: dict[str, Callable] = {}

    async def start(self) -> None:
        """Initialize and start event system."""
        logger.info("Starting event system...")

        # 1. Create and start event listener (PostgreSQL or SQLite)
        self.event_listener = create_event_listener(self.database_url)
        await self.event_listener.start()

        # 2. Start cleanup service
        self.cleanup_service = EventCleanupService(
            db_session_factory=self.db_session_factory,
            retention_hours=self.event_retention_hours,
            cleanup_interval_hours=self.event_cleanup_interval_hours,
        )
        await self.cleanup_service.start()

        logger.info("Event system started successfully")

    async def stop(self) -> None:
        """Stop event system gracefully."""
        logger.info("Stopping event system...")

        if self.cleanup_service:
            await self.cleanup_service.stop()

        if self.event_listener:
            await self.event_listener.stop()

        logger.info("Event system stopped")

    async def register_channel_handler(self, channel: str, handler: Callable) -> None:
        """
        Register handler for a channel.

        Args:
            channel: Event channel name
            handler: Async callback function for events on this channel

        Raises:
            RuntimeError: If event system not started
        """
        if not self.event_listener:
            raise RuntimeError("Event system not started")

        await self.event_listener.subscribe(channel, handler)
        self._channel_handlers[channel] = handler

        logger.info(f"Registered handler for channel: {channel}")

    def get_listener(self) -> EventListener:
        """
        Get event listener for WebSocket endpoints.

        Returns:
            EventListener instance

        Raises:
            RuntimeError: If event system not started
        """
        if not self.event_listener:
            raise RuntimeError("Event system not started")
        return self.event_listener


# Global manager instance
_event_system: Optional[EventSystemManager] = None


def get_event_system() -> EventSystemManager:
    """
    Get global event system manager.

    Returns:
        EventSystemManager instance

    Raises:
        RuntimeError: If event system not initialized
    """
    if _event_system is None:
        raise RuntimeError("Event system not initialized")
    return _event_system


def set_event_system(manager: EventSystemManager) -> None:
    """
    Set global event system manager (called during startup).

    Args:
        manager: EventSystemManager instance to set as global
    """
    global _event_system
    _event_system = manager

