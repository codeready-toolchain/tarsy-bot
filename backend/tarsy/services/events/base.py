"""Abstract base class for event listeners."""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)

# Type alias for async event callbacks
AsyncCallback = Callable[[dict], Awaitable[None]]


class EventListener(ABC):
    """Abstract base class for event listener implementations."""

    def __init__(self) -> None:
        self.callbacks: Dict[str, List[AsyncCallback]] = {}
        self.running: bool = False
        self.last_activity: Dict[str, float] = {}  # Track last activity per channel
        self._cleanup_task: asyncio.Task | None = None  # Background cleanup task

    @abstractmethod
    async def start(self) -> None:
        """Initialize and start the event listener."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the event listener and clean up resources."""
        pass
    
    async def _start_cleanup_task(self) -> None:
        """Start background task for periodic stale channel cleanup."""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Started stale channel cleanup task")
    
    async def _stop_cleanup_task(self) -> None:
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("Stopped stale channel cleanup task")
    
    async def _cleanup_loop(self) -> None:
        """Background task that periodically cleans up stale channels."""
        while self.running:
            try:
                await asyncio.sleep(60)  # Run cleanup every 60 seconds
                await self.cleanup_stale_channels(max_idle_seconds=60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}", exc_info=True)

    async def subscribe(self, channel: str, callback: AsyncCallback) -> None:
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
        self.last_activity[channel] = time.time()  # Track subscription time

    async def unsubscribe(self, channel: str, callback: AsyncCallback) -> None:
        """
        Unsubscribe callback from a channel.

        Args:
            channel: Channel name
            callback: Callback function to remove
        """
        if channel in self.callbacks and callback in self.callbacks[channel]:
            self.callbacks[channel].remove(callback)
            logger.debug(f"Unsubscribed callback from channel '{channel}'")
            
            # Clean up channel if no more callbacks (prevent polling empty channels)
            if not self.callbacks[channel]:
                del self.callbacks[channel]
                if channel in self.last_activity:
                    del self.last_activity[channel]
                await self._cleanup_channel(channel)
                logger.info(f"Removed empty channel '{channel}' from polling")
    
    @abstractmethod
    async def _cleanup_channel(self, channel: str) -> None:
        """
        Optional cleanup when a channel is removed.
        
        Override in subclasses to perform additional cleanup (e.g., remove last_event_id tracking).
        """

    @abstractmethod
    async def _register_channel(self, channel: str) -> None:
        """Implementation-specific channel registration."""
        pass

    async def _dispatch_to_callbacks(self, channel: str, event: dict) -> None:
        """Dispatch event to all registered callbacks."""
        # Update activity time on event dispatch
        self.last_activity[channel] = time.time()
        
        for callback in self.callbacks.get(channel, []):
            asyncio.create_task(self._safe_callback(callback, event))

    async def _safe_callback(self, callback: AsyncCallback, event: dict) -> None:
        """Execute callback with error handling."""
        try:
            await callback(event)
        except Exception as e:
            logger.error(f"Error in event callback: {e}", exc_info=True)
    
    async def cleanup_stale_channels(self, max_idle_seconds: int = 60) -> None:
        """
        Clean up channels with no active subscribers.
        
        Activity-based cleanup: Only removes channels that are both:
        1. Idle (no events dispatched) for max_idle_seconds
        2. Have zero active callbacks (no subscribers)
        
        Args:
            max_idle_seconds: Maximum idle time before cleanup (default: 60 seconds)
        """
        now = time.time()
        channels_to_cleanup = []
        
        # Find idle channels with no subscribers
        for channel, last_time in list(self.last_activity.items()):
            idle_time = now - last_time
            callback_count = len(self.callbacks.get(channel, []))
            
            # Only cleanup if idle AND no subscribers
            if idle_time > max_idle_seconds and callback_count == 0:
                channels_to_cleanup.append(channel)
        
        # Cleanup identified channels
        for channel in channels_to_cleanup:
            logger.debug(f"Cleaning up idle channel '{channel}' (no subscribers)")
            # Safely remove from both dictionaries (may not exist in callbacks)
            self.callbacks.pop(channel, None)
            self.last_activity.pop(channel, None)
            # Only call cleanup after successful removal
            await self._cleanup_channel(channel)

