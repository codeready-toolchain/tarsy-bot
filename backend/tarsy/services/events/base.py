"""Abstract base class for event listeners."""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)


class EventListener(ABC):
    """Abstract base class for event listener implementations."""

    def __init__(self):
        self.callbacks: Dict[str, List[Callable]] = {}
        self.running: bool = False

    @abstractmethod
    async def start(self) -> None:
        """Initialize and start the event listener."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the event listener and clean up resources."""
        pass

    async def subscribe(self, channel: str, callback: Callable[[dict], None]) -> None:
        """
        Subscribe to events on a channel.

        Args:
            channel: Channel name (e.g., 'session_events')
            callback: Async function called when event received
        """
        if channel not in self.callbacks:
            self.callbacks[channel] = []
            await self._register_channel(channel)

        self.callbacks[channel].append(callback)

    async def unsubscribe(
        self, channel: str, callback: Callable[[dict], None]
    ) -> None:
        """
        Unsubscribe callback from a channel.

        Args:
            channel: Channel name
            callback: Callback function to remove
        """
        if channel in self.callbacks and callback in self.callbacks[channel]:
            self.callbacks[channel].remove(callback)
            logger.debug(f"Unsubscribed callback from channel '{channel}'")

    @abstractmethod
    async def _register_channel(self, channel: str) -> None:
        """Implementation-specific channel registration."""
        pass

    async def _dispatch_to_callbacks(self, channel: str, event: dict) -> None:
        """Dispatch event to all registered callbacks."""
        for callback in self.callbacks.get(channel, []):
            asyncio.create_task(self._safe_callback(callback, event))

    async def _safe_callback(self, callback: Callable, event: dict) -> None:
        """Execute callback with error handling."""
        try:
            await callback(event)
        except Exception as e:
            logger.error(f"Error in event callback: {e}", exc_info=True)

