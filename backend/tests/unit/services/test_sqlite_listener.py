"""
Unit tests for SQLiteEventListener.

This module tests SQLite-based event listening via polling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from tarsy.models.db_models import Event
from tarsy.services.events.sqlite_listener import SQLiteEventListener


@pytest.mark.unit
class TestSQLiteEventListenerInitialization:
    """Test SQLiteEventListener initialization."""

    def test_init_with_default_poll_interval(self):
        """Test initialization with default poll interval."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        assert listener.database_url == database_url
        assert listener.poll_interval == 0.5
        assert listener.running is False
        assert listener.polling_task is None
        assert listener.last_event_id == {}
        assert listener.engine is None

    def test_init_with_custom_poll_interval(self):
        """Test initialization with custom poll interval."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url, poll_interval=5.0)

        assert listener.database_url == database_url
        assert listener.poll_interval == 5.0

    def test_init_with_very_short_poll_interval(self):
        """Test initialization with very short poll interval."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url, poll_interval=0.1)

        assert listener.poll_interval == 0.1

    def test_init_callbacks_empty(self):
        """Test that callbacks are initially empty."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        assert listener.callbacks == {}


@pytest.mark.unit
class TestSQLiteEventListenerLifecycle:
    """Test SQLiteEventListener start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_engine_and_task(self):
        """Test that start() creates engine and polling task."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        with patch("tarsy.services.events.sqlite_listener.create_async_engine") as mock_create:
            mock_engine = AsyncMock()
            mock_create.return_value = mock_engine
            
            with patch.object(listener, "_poll_loop", new_callable=AsyncMock):
                await listener.start()

                assert listener.running is True
                assert listener.engine is mock_engine
                assert listener.polling_task is not None
                assert not listener.polling_task.done()

                await listener.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_task_and_disposes_engine(self):
        """Test that stop() cancels task and disposes engine."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url, poll_interval=10.0)

        mock_engine = AsyncMock()

        with patch("tarsy.services.events.sqlite_listener.create_async_engine", return_value=mock_engine):
            with patch.object(listener, "_poll_loop", new_callable=AsyncMock):
                await listener.start()
                await listener.stop()

                assert listener.running is False
                assert listener.polling_task.done()
                mock_engine.dispose.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Test that stop() when not running does nothing."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        # Should not raise any errors
        await listener.stop()

        assert listener.running is False


@pytest.mark.unit
class TestSQLiteEventListenerSubscriptions:
    """Test SQLiteEventListener subscription management."""

    @pytest.mark.asyncio
    async def test_subscribe_to_channel(self):
        """Test subscribing to a channel."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        callback = AsyncMock()
        await listener.subscribe("test_channel", callback)

        assert "test_channel" in listener.callbacks
        assert callback in listener.callbacks["test_channel"]
        assert listener.last_event_id["test_channel"] == 0

    @pytest.mark.asyncio
    async def test_subscribe_multiple_callbacks_to_same_channel(self):
        """Test subscribing multiple callbacks to the same channel."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        callback1 = AsyncMock()
        callback2 = AsyncMock()

        await listener.subscribe("test_channel", callback1)
        await listener.subscribe("test_channel", callback2)

        assert len(listener.callbacks["test_channel"]) == 2
        assert callback1 in listener.callbacks["test_channel"]
        assert callback2 in listener.callbacks["test_channel"]

    @pytest.mark.asyncio
    async def test_subscribe_to_multiple_channels(self):
        """Test subscribing to multiple different channels."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        callback1 = AsyncMock()
        callback2 = AsyncMock()

        await listener.subscribe("channel1", callback1)
        await listener.subscribe("channel2", callback2)

        assert "channel1" in listener.callbacks
        assert "channel2" in listener.callbacks
        assert callback1 in listener.callbacks["channel1"]
        assert callback2 in listener.callbacks["channel2"]

    @pytest.mark.asyncio
    async def test_unsubscribe_from_channel(self):
        """Test unsubscribing from a channel removes it when empty."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        callback = AsyncMock()
        await listener.subscribe("test_channel", callback)
        await listener.unsubscribe("test_channel", callback)

        # Channel should be removed when no callbacks remain
        assert "test_channel" not in listener.callbacks

    @pytest.mark.asyncio
    async def test_unsubscribe_one_of_multiple_callbacks(self):
        """Test unsubscribing one callback when multiple are subscribed."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        callback1 = AsyncMock()
        callback2 = AsyncMock()

        await listener.subscribe("test_channel", callback1)
        await listener.subscribe("test_channel", callback2)

        await listener.unsubscribe("test_channel", callback1)

        assert len(listener.callbacks["test_channel"]) == 1
        assert callback2 in listener.callbacks["test_channel"]
        assert callback1 not in listener.callbacks["test_channel"]

    @pytest.mark.asyncio
    async def test_unsubscribe_from_nonexistent_channel(self):
        """Test unsubscribing from a channel that doesn't exist."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        callback = AsyncMock()
        # Should not raise any errors
        await listener.unsubscribe("nonexistent_channel", callback)


@pytest.mark.unit
class TestSQLiteEventListenerPolling:
    """Test SQLiteEventListener polling behavior."""

    @pytest.mark.asyncio
    async def test_poll_loop_respects_running_flag(self):
        """Test that poll loop stops when running flag is False."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)
        listener.running = False

        # Loop should exit immediately
        await listener._poll_loop()

        # If we get here without timeout, loop exited correctly

    @pytest.mark.asyncio
    async def test_poll_loop_polls_periodically(self):
        """Test that poll loop polls periodically."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url, poll_interval=1.0)

        poll_count = 0

        async def mock_poll():
            nonlocal poll_count
            poll_count += 1
            if poll_count >= 2:
                listener.running = False

        with patch.object(listener, "_poll_events", side_effect=mock_poll):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                listener.running = True
                await listener._poll_loop()

                assert poll_count >= 2

    @pytest.mark.asyncio
    async def test_poll_loop_handles_cancellation(self):
        """Test that poll loop handles cancellation."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        async def mock_poll():
            raise asyncio.CancelledError()

        with patch.object(listener, "_poll_events", side_effect=mock_poll):
            listener.running = True
            await listener._poll_loop()

            # Should exit cleanly

    @pytest.mark.asyncio
    async def test_poll_loop_handles_errors(self):
        """Test that poll loop handles errors and continues."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        poll_count = 0

        async def mock_poll():
            nonlocal poll_count
            poll_count += 1
            if poll_count == 1:
                raise Exception("Test error")
            listener.running = False

        with patch.object(listener, "_poll_events", side_effect=mock_poll):
            with patch("asyncio.sleep", new_callable=AsyncMock):
                listener.running = True
                await listener._poll_loop()

                # Should have attempted poll twice
                assert poll_count == 2

    @pytest.mark.asyncio
    async def test_poll_events_queries_all_channels(self):
        """Test that _poll_events queries all channels."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        # Subscribe to channels
        await listener.subscribe("channel1", AsyncMock())
        await listener.subscribe("channel2", AsyncMock())

        # Mock engine and repo
        mock_conn = AsyncMock()
        mock_engine = AsyncMock()
        mock_engine.begin = MagicMock(return_value=mock_conn)
        listener.engine = mock_engine

        mock_repo = Mock()
        mock_repo.get_events_after = AsyncMock(return_value=[])

        with patch("tarsy.services.events.sqlite_listener.AsyncSession"):
            with patch("tarsy.repositories.event_repository.EventRepository", return_value=mock_repo):
                await listener._poll_events()

                # Should have queried both channels
                assert mock_repo.get_events_after.call_count == 2

    @pytest.mark.asyncio
    async def test_poll_events_updates_last_event_id(self):
        """Test that _poll_events updates last_event_id."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        await listener.subscribe("test_channel", AsyncMock())

        # Create mock events
        mock_event1 = Mock(spec=Event)
        mock_event1.id = 10
        mock_event1.payload = {"type": "test"}

        mock_event2 = Mock(spec=Event)
        mock_event2.id = 20
        mock_event2.payload = {"type": "test"}

        mock_conn = AsyncMock()
        mock_engine = AsyncMock()
        mock_engine.begin = MagicMock(return_value=mock_conn)
        listener.engine = mock_engine

        mock_repo = Mock()
        mock_repo.get_events_after = AsyncMock(return_value=[mock_event1, mock_event2])

        with patch("tarsy.services.events.sqlite_listener.AsyncSession"):
            with patch("tarsy.repositories.event_repository.EventRepository", return_value=mock_repo):
                with patch.object(listener, "_dispatch_to_callbacks", new_callable=AsyncMock):
                    await listener._poll_events()

                    # Should have updated to highest ID
                    assert listener.last_event_id["test_channel"] == 20

    @pytest.mark.asyncio
    async def test_poll_events_handles_channel_errors(self):
        """Test that _poll_events handles errors on individual channels."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        await listener.subscribe("test_channel", AsyncMock())

        mock_conn = AsyncMock()
        mock_engine = AsyncMock()
        mock_engine.begin = MagicMock(return_value=mock_conn)
        listener.engine = mock_engine

        mock_repo = Mock()
        mock_repo.get_events_after = AsyncMock(side_effect=Exception("Query error"))

        with patch("tarsy.services.events.sqlite_listener.AsyncSession"):
            with patch("tarsy.repositories.event_repository.EventRepository", return_value=mock_repo):
                # Should not raise
                await listener._poll_events()


@pytest.mark.unit
class TestSQLiteEventListenerEventDispatching:
    """Test SQLiteEventListener event dispatching."""

    @pytest.mark.asyncio
    async def test_dispatch_to_callbacks_calls_all_callbacks(self):
        """Test that dispatching calls all registered callbacks."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        callback1 = AsyncMock()
        callback2 = AsyncMock()

        await listener.subscribe("test_channel", callback1)
        await listener.subscribe("test_channel", callback2)

        event = {"type": "test", "data": "value"}
        await listener._dispatch_to_callbacks("test_channel", event)

        # Give tasks time to execute
        await asyncio.sleep(0.01)

        callback1.assert_called_once_with(event)
        callback2.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_dispatch_to_callbacks_handles_exceptions(self):
        """Test that callback exceptions don't crash the dispatch."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        callback1 = AsyncMock(side_effect=Exception("Callback error"))
        callback2 = AsyncMock()

        await listener.subscribe("test_channel", callback1)
        await listener.subscribe("test_channel", callback2)

        event = {"type": "test"}
        await listener._dispatch_to_callbacks("test_channel", event)

        # Give tasks time to execute
        await asyncio.sleep(0.01)

        # Both should have been called
        callback1.assert_called_once()
        callback2.assert_called_once()


@pytest.mark.unit
class TestSQLiteEventListenerEdgeCases:
    """Test SQLiteEventListener edge cases."""

    @pytest.mark.asyncio
    async def test_multiple_start_stop_cycles(self):
        """Test multiple start/stop cycles."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        mock_engine = AsyncMock()

        with patch("tarsy.services.events.sqlite_listener.create_async_engine", return_value=mock_engine):
            with patch.object(listener, "_poll_loop", new_callable=AsyncMock):
                # Start and stop multiple times
                for _ in range(3):
                    await listener.start()
                    assert listener.running is True

                    await listener.stop()
                    assert listener.running is False

    @pytest.mark.asyncio
    async def test_poll_events_without_engine(self):
        """Test that _poll_events handles missing engine."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        # Should not raise
        await listener._poll_events()

    def test_very_large_last_event_id(self):
        """Test handling very large event IDs."""
        database_url = "sqlite+aiosqlite:///test.db"
        listener = SQLiteEventListener(database_url)

        listener.last_event_id["test"] = 9999999999

        # Should handle large IDs without issues
        assert listener.last_event_id["test"] == 9999999999
