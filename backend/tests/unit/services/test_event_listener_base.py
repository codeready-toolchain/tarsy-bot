"""
Unit tests for EventListener base class.

This module tests the abstract EventListener base class behaviors,
particularly edge cases in the cleanup logic.
"""

import time
from typing import Dict
from unittest.mock import AsyncMock

import pytest

from tarsy.services.events.base import EventListener


class ConcreteEventListener(EventListener):
    """Concrete implementation of EventListener for testing."""

    def __init__(self) -> None:
        super().__init__()
        self.started = False
        self.stopped = False
        self.registered_channels: Dict[str, bool] = {}
        self.cleaned_up_channels: Dict[str, bool] = {}

    async def start(self) -> None:
        """Start the listener."""
        self.running = True
        self.started = True

    async def stop(self) -> None:
        """Stop the listener."""
        self.running = False
        self.stopped = True

    async def _register_channel(self, channel: str) -> None:
        """Track channel registration."""
        self.registered_channels[channel] = True

    async def _cleanup_channel(self, channel: str) -> None:
        """Track channel cleanup."""
        self.cleaned_up_channels[channel] = True


@pytest.mark.unit
class TestEventListenerCleanup:
    """Test EventListener cleanup behavior."""

    @pytest.mark.asyncio
    async def test_cleanup_stale_channels_with_orphaned_activity(self):
        """Test that cleanup handles channels in last_activity but not in callbacks.
        
        This is a regression test for a KeyError that could occur when
        last_activity has entries for channels that don't exist in callbacks.
        """
        listener = ConcreteEventListener()
        await listener.start()

        # Simulate orphaned state: channel exists in last_activity but not in callbacks
        # This can happen if callbacks dict is manually cleared or becomes inconsistent
        listener.last_activity["orphaned_channel"] = time.time() - 120  # Old timestamp

        # Should not raise KeyError
        await listener.cleanup_stale_channels(max_idle_seconds=60)

        # Verify the orphaned channel was cleaned up
        assert "orphaned_channel" not in listener.last_activity
        assert "orphaned_channel" not in listener.callbacks
        assert listener.cleaned_up_channels.get("orphaned_channel") is True

    @pytest.mark.asyncio
    async def test_cleanup_stale_channels_with_callbacks_but_no_activity(self):
        """Test that cleanup handles channels in callbacks but not in last_activity."""
        listener = ConcreteEventListener()
        await listener.start()

        # Subscribe to a channel (creates entry in both callbacks and last_activity)
        callback = AsyncMock()
        await listener.subscribe("test_channel", callback)

        # Manually remove from last_activity to simulate inconsistency
        del listener.last_activity["test_channel"]

        # Should not raise KeyError (channel has subscribers so won't be cleaned)
        await listener.cleanup_stale_channels(max_idle_seconds=60)

        # Channel should still exist (has active subscriber)
        assert "test_channel" in listener.callbacks
        assert "test_channel" not in listener.cleaned_up_channels

    @pytest.mark.asyncio
    async def test_cleanup_stale_channels_with_idle_no_subscribers(self):
        """Test cleanup removes channels that are both idle AND have no subscribers."""
        listener = ConcreteEventListener()
        await listener.start()

        # Create a stale channel: old activity, no subscribers
        listener.last_activity["stale_channel"] = time.time() - 120
        listener.callbacks["stale_channel"] = []  # Empty list = no subscribers

        await listener.cleanup_stale_channels(max_idle_seconds=60)

        # Should be cleaned up
        assert "stale_channel" not in listener.callbacks
        assert "stale_channel" not in listener.last_activity
        assert listener.cleaned_up_channels.get("stale_channel") is True

    @pytest.mark.asyncio
    async def test_cleanup_stale_channels_preserves_active_channels(self):
        """Test that cleanup preserves channels with recent activity."""
        listener = ConcreteEventListener()
        await listener.start()

        # Create an active channel
        callback = AsyncMock()
        await listener.subscribe("active_channel", callback)
        listener.last_activity["active_channel"] = time.time()  # Recent activity

        await listener.cleanup_stale_channels(max_idle_seconds=60)

        # Should be preserved
        assert "active_channel" in listener.callbacks
        assert "active_channel" in listener.last_activity
        assert "active_channel" not in listener.cleaned_up_channels

    @pytest.mark.asyncio
    async def test_cleanup_stale_channels_preserves_channels_with_subscribers(self):
        """Test that cleanup preserves idle channels that still have subscribers."""
        listener = ConcreteEventListener()
        await listener.start()

        # Create an idle channel with subscribers
        callback = AsyncMock()
        await listener.subscribe("idle_with_subs", callback)
        listener.last_activity["idle_with_subs"] = time.time() - 120  # Old

        await listener.cleanup_stale_channels(max_idle_seconds=60)

        # Should be preserved (has active subscriber)
        assert "idle_with_subs" in listener.callbacks
        assert "idle_with_subs" in listener.last_activity
        assert "idle_with_subs" not in listener.cleaned_up_channels

    @pytest.mark.asyncio
    async def test_cleanup_with_multiple_mixed_channels(self):
        """Test cleanup with a mix of channels in different states."""
        listener = ConcreteEventListener()
        await listener.start()

        # Active channel with subscribers
        await listener.subscribe("active", AsyncMock())
        listener.last_activity["active"] = time.time()

        # Idle channel with subscribers
        await listener.subscribe("idle_with_subs", AsyncMock())
        listener.last_activity["idle_with_subs"] = time.time() - 120

        # Stale channel without subscribers
        listener.callbacks["stale_no_subs"] = []
        listener.last_activity["stale_no_subs"] = time.time() - 120

        # Orphaned in last_activity only
        listener.last_activity["orphaned"] = time.time() - 120

        await listener.cleanup_stale_channels(max_idle_seconds=60)

        # Verify results
        assert "active" in listener.callbacks  # Preserved: active
        assert "idle_with_subs" in listener.callbacks  # Preserved: has subs
        assert "stale_no_subs" not in listener.callbacks  # Cleaned: stale + no subs
        assert "orphaned" not in listener.last_activity  # Cleaned: orphaned

        # Verify cleanup was called for removed channels
        assert listener.cleaned_up_channels.get("stale_no_subs") is True
        assert listener.cleaned_up_channels.get("orphaned") is True
        assert "active" not in listener.cleaned_up_channels
        assert "idle_with_subs" not in listener.cleaned_up_channels


@pytest.mark.unit
class TestEventListenerUnsubscribe:
    """Test EventListener unsubscribe behavior."""

    @pytest.mark.asyncio
    async def test_unsubscribe_calls_cleanup_channel(self):
        """Test that unsubscribe calls _cleanup_channel when removing last callback."""
        listener = ConcreteEventListener()

        callback = AsyncMock()
        await listener.subscribe("test_channel", callback)

        assert "test_channel" in listener.callbacks
        assert listener.cleaned_up_channels.get("test_channel") is None

        # Unsubscribe the only callback
        await listener.unsubscribe("test_channel", callback)

        # Verify cleanup was called
        assert "test_channel" not in listener.callbacks
        assert "test_channel" not in listener.last_activity
        assert listener.cleaned_up_channels.get("test_channel") is True

    @pytest.mark.asyncio
    async def test_unsubscribe_does_not_cleanup_with_remaining_callbacks(self):
        """Test that unsubscribe doesn't cleanup when callbacks remain."""
        listener = ConcreteEventListener()

        callback1 = AsyncMock()
        callback2 = AsyncMock()
        await listener.subscribe("test_channel", callback1)
        await listener.subscribe("test_channel", callback2)

        # Unsubscribe one callback
        await listener.unsubscribe("test_channel", callback1)

        # Channel should still exist (callback2 remains)
        assert "test_channel" in listener.callbacks
        assert len(listener.callbacks["test_channel"]) == 1
        assert "test_channel" not in listener.cleaned_up_channels

