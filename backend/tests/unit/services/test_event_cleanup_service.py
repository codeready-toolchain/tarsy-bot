"""Unit tests for EventCleanupService."""

import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch
from sqlalchemy.exc import OperationalError

from tarsy.services.events.cleanup import EventCleanupService
from tarsy.repositories.event_repository import EventRepository


@pytest.mark.unit
class TestEventCleanupServiceInitialization:
    """Test EventCleanupService initialization."""

    def test_init_with_default_parameters(self):
        """Test initialization with default parameters."""
        mock_factory = Mock()
        
        service = EventCleanupService(mock_factory)

        assert service.db_session_factory == mock_factory
        assert service.retention_hours == 24
        assert service.cleanup_interval_hours == 6
        assert service.cleanup_task is None
        assert service.running is False

    def test_init_with_custom_parameters(self):
        """Test initialization with custom parameters."""
        mock_factory = Mock()
        
        service = EventCleanupService(
            mock_factory,
            retention_hours=48,
            cleanup_interval_hours=12
        )

        assert service.retention_hours == 48
        assert service.cleanup_interval_hours == 12


@pytest.mark.unit
class TestEventCleanupServiceLifecycle:
    """Test EventCleanupService start/stop lifecycle."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        return AsyncMock()

    @pytest.fixture
    def service(self, mock_session_factory):
        """Create EventCleanupService with mocked factory."""
        return EventCleanupService(
            mock_session_factory,
            retention_hours=24,
            cleanup_interval_hours=6
        )

    @pytest.mark.asyncio
    async def test_start_creates_cleanup_task(self, service):
        """Test that start() creates a background task."""
        await service.start()

        assert service.running is True
        assert service.cleanup_task is not None
        assert isinstance(service.cleanup_task, asyncio.Task)

        # Clean up
        await service.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_cleanup_task(self, service):
        """Test that stop() cancels the background task."""
        await service.start()
        
        # Verify task is running
        assert service.cleanup_task is not None
        assert not service.cleanup_task.done()

        await service.stop()

        assert service.running is False
        assert service.cleanup_task.done()

    @pytest.mark.asyncio
    async def test_stop_handles_already_stopped_service(self, service):
        """Test that stop() is safe to call on non-running service."""
        # Stop without start should not raise
        await service.stop()

        assert service.running is False
        assert service.cleanup_task is None

    @pytest.mark.asyncio
    async def test_multiple_start_calls(self, service):
        """Test behavior with multiple start calls."""
        await service.start()
        first_task = service.cleanup_task

        # Start again - creates new task
        await service.start()
        second_task = service.cleanup_task

        # Should be different tasks
        assert first_task != second_task

        # Clean up
        await service.stop()


@pytest.mark.unit
class TestEventCleanupServiceCleanup:
    """Test EventCleanupService cleanup functionality."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    @pytest.fixture
    def mock_session_factory(self, mock_session):
        """Create a mock session factory."""
        factory = Mock(return_value=mock_session)
        return factory

    @pytest.fixture
    def service(self, mock_session_factory):
        """Create EventCleanupService with mocked factory."""
        return EventCleanupService(
            mock_session_factory,
            retention_hours=24,
            cleanup_interval_hours=6
        )

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_events(self, service, mock_session):
        """Test that cleanup successfully deletes old events."""
        with patch('tarsy.services.events.cleanup.EventRepository') as mock_repo_class:
            mock_repo = Mock(spec=EventRepository)
            mock_repo.delete_events_before = AsyncMock(return_value=42)
            mock_repo_class.return_value = mock_repo

            await service._cleanup_old_events()

            # Verify repository was created with session
            mock_repo_class.assert_called_once_with(mock_session)

            # Verify delete was called
            mock_repo.delete_events_before.assert_awaited_once()
            
            # Verify cutoff time is approximately correct (within last 24 hours)
            call_args = mock_repo.delete_events_before.call_args[0][0]
            assert isinstance(call_args, datetime)
            assert call_args.tzinfo == timezone.utc
            
            expected_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            time_diff = abs((call_args - expected_cutoff).total_seconds())
            assert time_diff < 5  # Within 5 seconds

            # Verify commit
            mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_with_no_old_events(self, service, mock_session):
        """Test cleanup when no old events exist."""
        with patch('tarsy.services.events.cleanup.EventRepository') as mock_repo_class:
            mock_repo = Mock(spec=EventRepository)
            mock_repo.delete_events_before = AsyncMock(return_value=0)
            mock_repo_class.return_value = mock_repo

            await service._cleanup_old_events()

            # Should still commit even with 0 deletions
            mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_with_custom_retention_period(self, mock_session_factory, mock_session):
        """Test cleanup respects custom retention period."""
        service = EventCleanupService(
            mock_session_factory,
            retention_hours=48,  # Custom retention
            cleanup_interval_hours=6
        )

        with patch('tarsy.services.events.cleanup.EventRepository') as mock_repo_class:
            mock_repo = Mock(spec=EventRepository)
            mock_repo.delete_events_before = AsyncMock(return_value=10)
            mock_repo_class.return_value = mock_repo

            await service._cleanup_old_events()

            # Verify cutoff time uses 48 hours
            call_args = mock_repo.delete_events_before.call_args[0][0]
            expected_cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
            time_diff = abs((call_args - expected_cutoff).total_seconds())
            assert time_diff < 5  # Within 5 seconds

    @pytest.mark.asyncio
    async def test_cleanup_database_error_propagates(self, service, mock_session):
        """Test that database errors are logged and propagated."""
        with patch('tarsy.services.events.cleanup.EventRepository') as mock_repo_class:
            mock_repo = Mock(spec=EventRepository)
            mock_repo.delete_events_before = AsyncMock(
                side_effect=OperationalError("DB error", None, None)
            )
            mock_repo_class.return_value = mock_repo

            with pytest.raises(OperationalError, match="DB error"):
                await service._cleanup_old_events()

    @pytest.mark.asyncio
    async def test_cleanup_commit_error_propagates(self, service, mock_session):
        """Test that commit errors are propagated."""
        mock_session.commit.side_effect = OperationalError("Commit failed", None, None)

        with patch('tarsy.services.events.cleanup.EventRepository') as mock_repo_class:
            mock_repo = Mock(spec=EventRepository)
            mock_repo.delete_events_before = AsyncMock(return_value=5)
            mock_repo_class.return_value = mock_repo

            with pytest.raises(OperationalError, match="Commit failed"):
                await service._cleanup_old_events()


@pytest.mark.unit
class TestEventCleanupServiceLoop:
    """Test EventCleanupService cleanup loop behavior."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = AsyncMock()
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    @pytest.fixture
    def mock_session_factory(self, mock_session):
        """Create a mock session factory."""
        factory = Mock(return_value=mock_session)
        return factory

    @pytest.fixture
    def service(self, mock_session_factory):
        """Create EventCleanupService with short intervals for testing."""
        return EventCleanupService(
            mock_session_factory,
            retention_hours=1,
            cleanup_interval_hours=1
        )

    @pytest.mark.asyncio
    async def test_cleanup_loop_respects_running_flag(self, service):
        """Test that cleanup loop stops when running flag is False."""
        service.running = False

        # Loop should exit immediately when running is False
        await service._cleanup_loop()

        # If we get here without timeout, loop exited correctly

    @pytest.mark.asyncio
    async def test_cleanup_loop_handles_cancellation(self, service, mock_session):
        """Test that cleanup loop handles task cancellation gracefully."""
        # Mock cleanup to prevent actual work
        with patch.object(service, '_cleanup_old_events', new_callable=AsyncMock):
            await service.start()

            # Give the task a moment to start
            await asyncio.sleep(0.01)

            # Cancel and stop should work without errors
            await service.stop()

            # Task should be done
            assert service.cleanup_task.done()

    @pytest.mark.asyncio
    async def test_cleanup_loop_error_handling_logs_and_continues(self, service):
        """Test that errors in cleanup are logged but don't crash the loop."""
        # Create a cleanup that fails once then sets running to False
        cleanup_calls = []
        
        async def failing_cleanup():
            cleanup_calls.append(1)
            service.running = False  # Stop loop immediately
            if len(cleanup_calls) == 1:
                raise OperationalError("DB error", None, None)

        # Mock sleep to return immediately
        mock_sleep = AsyncMock()

        with patch.object(service, '_cleanup_old_events', side_effect=failing_cleanup):
            with patch('asyncio.sleep', mock_sleep):
                # Manually run one iteration of the loop
                service.running = True
                
                # This should handle the error and exit quickly
                await service._cleanup_loop()
                
                # Should have attempted cleanup
                assert len(cleanup_calls) >= 1
                # Should have tried to sleep (error backoff)
                assert mock_sleep.call_count >= 1


@pytest.mark.unit
class TestEventCleanupServiceConfiguration:
    """Test EventCleanupService configuration options."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        return AsyncMock()

    def test_very_short_retention(self, mock_session_factory):
        """Test service with very short retention period."""
        service = EventCleanupService(
            mock_session_factory,
            retention_hours=1,  # 1 hour retention
            cleanup_interval_hours=1
        )

        assert service.retention_hours == 1

    def test_very_long_retention(self, mock_session_factory):
        """Test service with very long retention period."""
        service = EventCleanupService(
            mock_session_factory,
            retention_hours=168,  # 1 week retention
            cleanup_interval_hours=24
        )

        assert service.retention_hours == 168
        assert service.cleanup_interval_hours == 24

    def test_frequent_cleanup(self, mock_session_factory):
        """Test service with frequent cleanup interval."""
        service = EventCleanupService(
            mock_session_factory,
            retention_hours=24,
            cleanup_interval_hours=1  # Every hour
        )

        assert service.cleanup_interval_hours == 1

    def test_infrequent_cleanup(self, mock_session_factory):
        """Test service with infrequent cleanup interval."""
        service = EventCleanupService(
            mock_session_factory,
            retention_hours=24,
            cleanup_interval_hours=24  # Once per day
        )

        assert service.cleanup_interval_hours == 24

