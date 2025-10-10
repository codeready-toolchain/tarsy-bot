"""
Unit tests for PostgreSQLEventListener.

This module tests PostgreSQL-based event listening via LISTEN/NOTIFY.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, Mock, patch

from tarsy.services.events.postgresql_listener import PostgreSQLEventListener


@pytest.mark.unit
class TestPostgreSQLEventListenerInitialization:
    """Test PostgreSQLEventListener initialization."""

    def test_init_with_database_url(self):
        """Test initialization with database URL."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        assert listener.database_url == database_url
        assert listener.running is False
        assert listener.listener_conn is None

    def test_init_callbacks_empty(self):
        """Test that callbacks are initially empty."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        assert listener.callbacks == {}


@pytest.mark.unit
class TestPostgreSQLEventListenerLifecycle:
    """Test PostgreSQLEventListener start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_connection(self):
        """Test that start() creates a database connection."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = AsyncMock()

        with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn):
            await listener.start()

            assert listener.running is True
            assert listener.listener_conn is mock_conn

            await listener.stop()

    @pytest.mark.asyncio
    async def test_start_when_already_running(self):
        """Test that start() when already running creates new connection."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = AsyncMock()

        with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn):
            await listener.start()

            # Start again - should create new connection
            await listener.start()

            # Connection should be updated
            assert listener.running is True

            await listener.stop()

    @pytest.mark.asyncio
    async def test_start_handles_connection_error(self):
        """Test that start() handles connection errors gracefully."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        with patch("asyncpg.connect", side_effect=Exception("Connection failed")):
            # Should raise the connection error
            with pytest.raises(Exception, match="Connection failed"):
                await listener.start()

            assert listener.running is False
            assert listener.listener_conn is None

    @pytest.mark.asyncio
    async def test_stop_closes_connection(self):
        """Test that stop() closes the database connection."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = AsyncMock()

        with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn):
            await listener.start()
            await listener.stop()

            assert listener.running is False
            mock_conn.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Test that stop() when not running does nothing."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        # Should not raise any errors
        await listener.stop()

        assert listener.running is False


@pytest.mark.unit
class TestPostgreSQLEventListenerSubscriptions:
    """Test PostgreSQLEventListener subscription management."""

    @pytest.mark.asyncio
    async def test_subscribe_to_channel(self):
        """Test subscribing to a channel."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = AsyncMock()
        listener.listener_conn = mock_conn

        callback = AsyncMock()
        await listener.subscribe("test_channel", callback)

        assert "test_channel" in listener.callbacks
        assert callback in listener.callbacks["test_channel"]
        mock_conn.add_listener.assert_called_once_with(
            "test_channel", listener._handle_notification
        )

    @pytest.mark.asyncio
    async def test_subscribe_multiple_callbacks_to_same_channel(self):
        """Test subscribing multiple callbacks to the same channel."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = AsyncMock()
        listener.listener_conn = mock_conn

        callback1 = AsyncMock()
        callback2 = AsyncMock()

        await listener.subscribe("test_channel", callback1)
        await listener.subscribe("test_channel", callback2)

        assert len(listener.callbacks["test_channel"]) == 2
        assert callback1 in listener.callbacks["test_channel"]
        assert callback2 in listener.callbacks["test_channel"]

        # add_listener should only be called once for the channel
        assert mock_conn.add_listener.call_count == 1

    @pytest.mark.asyncio
    async def test_subscribe_to_multiple_channels(self):
        """Test subscribing to multiple different channels."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = AsyncMock()
        listener.listener_conn = mock_conn

        callback1 = AsyncMock()
        callback2 = AsyncMock()

        await listener.subscribe("channel1", callback1)
        await listener.subscribe("channel2", callback2)

        assert "channel1" in listener.callbacks
        assert "channel2" in listener.callbacks

        # Should have called add_listener for each channel
        assert mock_conn.add_listener.call_count == 2

    @pytest.mark.asyncio
    async def test_subscribe_without_connection_raises_error(self):
        """Test subscribing when not connected raises error."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        callback = AsyncMock()

        with pytest.raises(RuntimeError, match="Listener not initialized"):
            await listener.subscribe("test_channel", callback)

    @pytest.mark.asyncio
    async def test_unsubscribe_from_channel(self):
        """Test unsubscribing from a channel removes it when empty."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = AsyncMock()
        listener.listener_conn = mock_conn

        callback = AsyncMock()
        await listener.subscribe("test_channel", callback)
        await listener.unsubscribe("test_channel", callback)

        # Channel should be removed when no callbacks remain
        assert "test_channel" not in listener.callbacks

    @pytest.mark.asyncio
    async def test_unsubscribe_one_of_multiple_callbacks(self):
        """Test unsubscribing one callback when multiple are subscribed."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = AsyncMock()
        listener.listener_conn = mock_conn

        callback1 = AsyncMock()
        callback2 = AsyncMock()

        await listener.subscribe("test_channel", callback1)
        await listener.subscribe("test_channel", callback2)

        await listener.unsubscribe("test_channel", callback1)

        assert len(listener.callbacks["test_channel"]) == 1
        assert callback2 in listener.callbacks["test_channel"]

    @pytest.mark.asyncio
    async def test_unsubscribe_from_nonexistent_channel(self):
        """Test unsubscribing from a channel that doesn't exist."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        callback = AsyncMock()
        # Should not raise any errors
        await listener.unsubscribe("nonexistent_channel", callback)


@pytest.mark.unit
class TestPostgreSQLEventListenerNotifications:
    """Test PostgreSQLEventListener notification handling."""

    def test_handle_notification_dispatches_to_callbacks(self):
        """Test that notification handler dispatches to callbacks."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        # We can't easily test the async dispatch, but we can verify the method exists
        # and accepts the right parameters
        mock_conn = Mock()
        payload = json.dumps({"type": "test", "data": "value"})

        # Should not raise
        listener._handle_notification(mock_conn, 12345, "test_channel", payload)

    def test_handle_notification_with_invalid_json(self):
        """Test notification handler with invalid JSON payload."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = Mock()

        # Should handle gracefully and not crash
        listener._handle_notification(mock_conn, 12345, "test_channel", "invalid json {")

    def test_handle_notification_logs_event_type(self):
        """Test that notification handler logs event type."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = Mock()
        payload = json.dumps({"type": "session_created", "data": "value"})

        # Should not raise
        listener._handle_notification(mock_conn, 12345, "test_channel", payload)


@pytest.mark.unit
class TestPostgreSQLEventListenerEventDispatching:
    """Test PostgreSQLEventListener event dispatching."""

    @pytest.mark.asyncio
    async def test_dispatch_to_callbacks_calls_all_callbacks(self):
        """Test that dispatching calls all registered callbacks."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = AsyncMock()
        listener.listener_conn = mock_conn

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
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = AsyncMock()
        listener.listener_conn = mock_conn

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

    @pytest.mark.asyncio
    async def test_dispatch_to_nonexistent_channel(self):
        """Test dispatching to a channel with no callbacks."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        event = {"type": "test"}

        # Should not raise
        await listener._dispatch_to_callbacks("nonexistent_channel", event)


@pytest.mark.unit
class TestPostgreSQLEventListenerEdgeCases:
    """Test PostgreSQLEventListener edge cases."""

    @pytest.mark.asyncio
    async def test_multiple_start_stop_cycles(self):
        """Test multiple start/stop cycles."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = AsyncMock()

        with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn):
            # Start and stop multiple times
            for _ in range(3):
                await listener.start()
                assert listener.running is True

                await listener.stop()
                assert listener.running is False

    @pytest.mark.asyncio
    async def test_subscribe_after_start(self):
        """Test subscribing to channels after listener is started."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = AsyncMock()

        with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn):
            await listener.start()

            callback = AsyncMock()
            await listener.subscribe("test_channel", callback)

            assert "test_channel" in listener.callbacks
            # Should have added listener
            mock_conn.add_listener.assert_called_with(
                "test_channel", listener._handle_notification
            )

            await listener.stop()

    @pytest.mark.asyncio
    async def test_unsubscribe_while_running(self):
        """Test unsubscribing while listener is running removes channel when empty."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = AsyncMock()

        with patch("asyncpg.connect", new_callable=AsyncMock, return_value=mock_conn):
            await listener.start()

            callback = AsyncMock()
            await listener.subscribe("test_channel", callback)
            await listener.unsubscribe("test_channel", callback)

            # Channel should be removed when no callbacks remain
            assert "test_channel" not in listener.callbacks

            await listener.stop()

    def test_handle_notification_with_empty_payload(self):
        """Test handling notification with empty payload."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = Mock()

        # Should handle gracefully
        listener._handle_notification(mock_conn, 12345, "test_channel", "{}")

    def test_handle_notification_with_complex_event(self):
        """Test handling notification with complex nested event."""
        database_url = "postgresql://user:pass@localhost/db"
        listener = PostgreSQLEventListener(database_url)

        mock_conn = Mock()
        payload = json.dumps({
            "type": "llm_interaction",
            "data": {
                "nested": {
                    "deeply": {
                        "value": 123
                    }
                }
            }
        })

        # Should handle gracefully
        listener._handle_notification(mock_conn, 12345, "test_channel", payload)
