"""
Unit tests for EventSystemManager.

This module tests the event system lifecycle and channel management.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from tarsy.services.events.manager import (
    EventSystemManager,
    get_event_system,
    set_event_system,
)


@pytest.mark.unit
class TestEventSystemManagerInitialization:
    """Test EventSystemManager initialization."""

    def test_init_with_default_settings(self):
        """Test initialization with default settings."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()

        manager = EventSystemManager(database_url, session_factory)

        assert manager.database_url == database_url
        assert manager.db_session_factory == session_factory
        assert manager.event_retention_hours == 24
        assert manager.event_cleanup_interval_hours == 6
        assert manager.event_listener is None
        assert manager.cleanup_service is None
        assert manager._channel_handlers == {}

    def test_init_with_custom_settings(self):
        """Test initialization with custom settings."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()

        manager = EventSystemManager(
            database_url,
            session_factory,
            event_retention_hours=48,
            event_cleanup_interval_hours=12,
        )

        assert manager.event_retention_hours == 48
        assert manager.event_cleanup_interval_hours == 12

    def test_init_with_sqlite_url(self):
        """Test initialization with SQLite URL."""
        database_url = "sqlite+aiosqlite:///test.db"
        session_factory = Mock()

        manager = EventSystemManager(database_url, session_factory)

        assert manager.database_url == database_url


@pytest.mark.unit
class TestEventSystemManagerLifecycle:
    """Test EventSystemManager start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_listener_and_cleanup_service(self):
        """Test that start() creates listener and cleanup service."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        mock_listener = AsyncMock()
        mock_cleanup = AsyncMock()

        with patch("tarsy.services.events.manager.create_event_listener", return_value=mock_listener):
            with patch("tarsy.services.events.manager.EventCleanupService", return_value=mock_cleanup):
                await manager.start()

                assert manager.event_listener is mock_listener
                assert manager.cleanup_service is mock_cleanup
                mock_listener.start.assert_called_once()
                mock_cleanup.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_passes_correct_cleanup_parameters(self):
        """Test that start() passes correct parameters to cleanup service."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(
            database_url,
            session_factory,
            event_retention_hours=48,
            event_cleanup_interval_hours=12,
        )

        mock_listener = AsyncMock()
        mock_cleanup_class = Mock(return_value=AsyncMock())

        with patch("tarsy.services.events.manager.create_event_listener", return_value=mock_listener):
            with patch("tarsy.services.events.manager.EventCleanupService", mock_cleanup_class):
                await manager.start()

                mock_cleanup_class.assert_called_once_with(
                    db_session_factory=session_factory,
                    retention_hours=48,
                    cleanup_interval_hours=12,
                )

    @pytest.mark.asyncio
    async def test_stop_stops_listener_and_cleanup(self):
        """Test that stop() stops both listener and cleanup service."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        mock_listener = AsyncMock()
        mock_cleanup = AsyncMock()

        with patch("tarsy.services.events.manager.create_event_listener", return_value=mock_listener):
            with patch("tarsy.services.events.manager.EventCleanupService", return_value=mock_cleanup):
                await manager.start()
                await manager.stop()

                mock_cleanup.stop.assert_called_once()
                mock_listener.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        """Test that stop() when not started does nothing."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        # Should not raise
        await manager.stop()

    @pytest.mark.asyncio
    async def test_multiple_start_stop_cycles(self):
        """Test multiple start/stop cycles."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        mock_listener = AsyncMock()
        mock_cleanup = AsyncMock()

        with patch("tarsy.services.events.manager.create_event_listener", return_value=mock_listener):
            with patch("tarsy.services.events.manager.EventCleanupService", return_value=mock_cleanup):
                # Start and stop multiple times
                for _ in range(3):
                    await manager.start()
                    assert manager.event_listener is not None
                    assert manager.cleanup_service is not None

                    await manager.stop()


@pytest.mark.unit
class TestEventSystemManagerChannelHandlers:
    """Test EventSystemManager channel handler management."""

    @pytest.mark.asyncio
    async def test_register_channel_handler_subscribes_to_listener(self):
        """Test that register_channel_handler subscribes to listener."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        mock_listener = AsyncMock()

        with patch("tarsy.services.events.manager.create_event_listener", return_value=mock_listener):
            with patch("tarsy.services.events.manager.EventCleanupService", return_value=AsyncMock()):
                await manager.start()

                handler = AsyncMock()
                await manager.register_channel_handler("test_channel", handler)

                mock_listener.subscribe.assert_called_once_with("test_channel", handler)
                assert manager._channel_handlers["test_channel"] == handler

    @pytest.mark.asyncio
    async def test_register_multiple_channel_handlers(self):
        """Test registering multiple channel handlers."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        mock_listener = AsyncMock()

        with patch("tarsy.services.events.manager.create_event_listener", return_value=mock_listener):
            with patch("tarsy.services.events.manager.EventCleanupService", return_value=AsyncMock()):
                await manager.start()

                handler1 = AsyncMock()
                handler2 = AsyncMock()

                await manager.register_channel_handler("channel1", handler1)
                await manager.register_channel_handler("channel2", handler2)

                assert len(manager._channel_handlers) == 2
                assert manager._channel_handlers["channel1"] == handler1
                assert manager._channel_handlers["channel2"] == handler2

    @pytest.mark.asyncio
    async def test_register_channel_handler_not_started_raises_error(self):
        """Test that registering handler when not started raises error."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        handler = AsyncMock()

        with pytest.raises(RuntimeError, match="Event system not started"):
            await manager.register_channel_handler("test_channel", handler)


@pytest.mark.unit
class TestEventSystemManagerGetListener:
    """Test EventSystemManager get_listener method."""

    @pytest.mark.asyncio
    async def test_get_listener_returns_listener(self):
        """Test that get_listener returns the event listener."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        mock_listener = AsyncMock()

        with patch("tarsy.services.events.manager.create_event_listener", return_value=mock_listener):
            with patch("tarsy.services.events.manager.EventCleanupService", return_value=AsyncMock()):
                await manager.start()

                listener = manager.get_listener()

                assert listener is mock_listener

    def test_get_listener_not_started_raises_error(self):
        """Test that get_listener when not started raises error."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        with pytest.raises(RuntimeError, match="Event system not started"):
            manager.get_listener()


@pytest.mark.unit
class TestEventSystemGlobalFunctions:
    """Test global event system getter/setter functions."""

    def teardown_method(self):
        """Reset global state after each test."""
        # Reset global state
        import tarsy.services.events.manager as manager_module
        manager_module._event_system = None

    def test_set_and_get_event_system(self):
        """Test setting and getting global event system."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        set_event_system(manager)
        retrieved = get_event_system()

        assert retrieved is manager

    def test_get_event_system_not_initialized_raises_error(self):
        """Test that get_event_system when not initialized raises error."""
        with pytest.raises(RuntimeError, match="Event system not initialized"):
            get_event_system()

    def test_set_event_system_replaces_existing(self):
        """Test that set_event_system replaces existing manager."""
        session_factory = Mock()

        manager1 = EventSystemManager("postgresql://user:pass@localhost/db1", session_factory)
        manager2 = EventSystemManager("postgresql://user:pass@localhost/db2", session_factory)

        set_event_system(manager1)
        set_event_system(manager2)

        retrieved = get_event_system()
        assert retrieved is manager2


@pytest.mark.unit
class TestEventSystemManagerErrorHandling:
    """Test EventSystemManager error handling."""

    @pytest.mark.asyncio
    async def test_start_handles_listener_creation_error(self):
        """Test that start() handles listener creation errors."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        with patch("tarsy.services.events.manager.create_event_listener", side_effect=Exception("Listener error")):
            with pytest.raises(Exception, match="Listener error"):
                await manager.start()

    @pytest.mark.asyncio
    async def test_start_handles_listener_start_error(self):
        """Test that start() handles listener start errors."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        mock_listener = AsyncMock()
        mock_listener.start.side_effect = Exception("Start error")

        with patch("tarsy.services.events.manager.create_event_listener", return_value=mock_listener):
            with pytest.raises(Exception, match="Start error"):
                await manager.start()

    @pytest.mark.asyncio
    async def test_start_handles_cleanup_service_error(self):
        """Test that start() handles cleanup service errors."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        mock_listener = AsyncMock()
        mock_cleanup = AsyncMock()
        mock_cleanup.start.side_effect = Exception("Cleanup error")

        with patch("tarsy.services.events.manager.create_event_listener", return_value=mock_listener):
            with patch("tarsy.services.events.manager.EventCleanupService", return_value=mock_cleanup):
                with pytest.raises(Exception, match="Cleanup error"):
                    await manager.start()

    @pytest.mark.asyncio
    async def test_stop_handles_cleanup_stop_error(self):
        """Test that stop() handles cleanup stop errors gracefully."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        mock_listener = AsyncMock()
        mock_cleanup = AsyncMock()
        mock_cleanup.stop.side_effect = Exception("Stop error")

        with patch("tarsy.services.events.manager.create_event_listener", return_value=mock_listener):
            with patch("tarsy.services.events.manager.EventCleanupService", return_value=mock_cleanup):
                await manager.start()

                # Stop should raise the error
                with pytest.raises(Exception, match="Stop error"):
                    await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_handles_listener_stop_error(self):
        """Test that stop() handles listener stop errors gracefully."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        mock_listener = AsyncMock()
        mock_listener.stop.side_effect = Exception("Listener stop error")
        mock_cleanup = AsyncMock()

        with patch("tarsy.services.events.manager.create_event_listener", return_value=mock_listener):
            with patch("tarsy.services.events.manager.EventCleanupService", return_value=mock_cleanup):
                await manager.start()

                # Stop should raise the error after cleanup stops
                with pytest.raises(Exception, match="Listener stop error"):
                    await manager.stop()


@pytest.mark.unit
class TestEventSystemManagerEdgeCases:
    """Test EventSystemManager edge cases."""

    def teardown_method(self):
        """Reset global state after each test."""
        import tarsy.services.events.manager as manager_module
        manager_module._event_system = None

    @pytest.mark.asyncio
    async def test_register_same_channel_twice(self):
        """Test registering the same channel twice updates the handler."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(database_url, session_factory)

        mock_listener = AsyncMock()

        with patch("tarsy.services.events.manager.create_event_listener", return_value=mock_listener):
            with patch("tarsy.services.events.manager.EventCleanupService", return_value=AsyncMock()):
                await manager.start()

                handler1 = AsyncMock()
                handler2 = AsyncMock()

                await manager.register_channel_handler("test_channel", handler1)
                await manager.register_channel_handler("test_channel", handler2)

                # Second handler should replace first
                assert manager._channel_handlers["test_channel"] == handler2
                assert mock_listener.subscribe.call_count == 2

    @pytest.mark.asyncio
    async def test_with_very_short_retention_and_cleanup_intervals(self):
        """Test with very short retention and cleanup intervals."""
        database_url = "postgresql://user:pass@localhost/db"
        session_factory = Mock()
        manager = EventSystemManager(
            database_url,
            session_factory,
            event_retention_hours=1,
            event_cleanup_interval_hours=1,
        )

        mock_listener = AsyncMock()
        mock_cleanup_class = Mock(return_value=AsyncMock())

        with patch("tarsy.services.events.manager.create_event_listener", return_value=mock_listener):
            with patch("tarsy.services.events.manager.EventCleanupService", mock_cleanup_class):
                await manager.start()

                # Verify cleanup service was created with correct params
                mock_cleanup_class.assert_called_once()
                call_kwargs = mock_cleanup_class.call_args.kwargs
                assert call_kwargs["retention_hours"] == 1
                assert call_kwargs["cleanup_interval_hours"] == 1

    def test_global_manager_is_none_initially(self):
        """Test that global manager is None initially."""
        import tarsy.services.events.manager as manager_module

        # Ensure it's reset
        manager_module._event_system = None

        with pytest.raises(RuntimeError, match="Event system not initialized"):
            get_event_system()

