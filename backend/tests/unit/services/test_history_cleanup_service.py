"""Unit tests for HistoryCleanupService."""

import asyncio
from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest

from tarsy.services.history_cleanup_service import HistoryCleanupService


@pytest.mark.unit
class TestHistoryCleanupServiceInitialization:
    """Test HistoryCleanupService initialization."""

    def test_init_with_default_parameters(self):
        """Test initialization with default parameters."""
        mock_factory = Mock()

        service = HistoryCleanupService(mock_factory)

        assert service.db_session_factory == mock_factory
        assert service.retention_days == 90
        assert service.cleanup_interval_hours == 12
        assert service.cleanup_task is None
        assert service.running is False

    def test_init_with_custom_parameters(self):
        """Test initialization with custom parameters."""
        mock_factory = Mock()

        service = HistoryCleanupService(
            mock_factory, retention_days=30, cleanup_interval_hours=24
        )

        assert service.retention_days == 30
        assert service.cleanup_interval_hours == 24


@pytest.mark.unit
class TestHistoryCleanupServiceLifecycle:
    """Test HistoryCleanupService start/stop lifecycle."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        return Mock()

    @pytest.fixture
    def service(self, mock_session_factory):
        """Create HistoryCleanupService with mocked factory."""
        return HistoryCleanupService(
            mock_session_factory, retention_days=90, cleanup_interval_hours=12
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

        await service.start()
        second_task = service.cleanup_task

        # Second start creates a new task
        assert first_task is not second_task

        # Clean up
        await service.stop()


@pytest.mark.unit
class TestHistoryCleanupServiceCleanup:
    """Test history cleanup functionality."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        session = Mock()
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=False)
        return session

    @pytest.fixture
    def mock_session_factory(self, mock_session):
        """Create a mock session factory that returns the mock session."""

        @contextmanager
        def factory():
            yield mock_session

        return factory

    @pytest.fixture
    def service(self, mock_session_factory):
        """Create HistoryCleanupService with mocked factory."""
        return HistoryCleanupService(
            mock_session_factory, retention_days=90, cleanup_interval_hours=12
        )

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_sessions(self, service, mock_session):
        """Test that cleanup deletes sessions older than retention period."""
        from tarsy.models.db_models import AlertSession

        # Mock repository delete method
        with patch(
            "tarsy.services.history_cleanup_service.HistoryRepository"
        ) as mock_repo_class:
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.delete_sessions_older_than.return_value = 5

            # Run cleanup
            await service._cleanup_old_history()

            # Verify delete was called with appropriate cutoff
            mock_repo.delete_sessions_older_than.assert_called_once()
            cutoff_arg = mock_repo.delete_sessions_older_than.call_args[0][0]

            # Verify cutoff is approximately 90 days ago (within 1 second tolerance)
            from tarsy.utils.timestamp import now_us

            expected_cutoff = now_us() - (90 * 24 * 3600 * 1_000_000)
            assert abs(cutoff_arg - expected_cutoff) < 1_000_000  # Within 1 second

    @pytest.mark.asyncio
    async def test_cleanup_respects_retention_period(self, service, mock_session):
        """Test that cleanup uses correct retention period."""
        # Set custom retention period
        service.retention_days = 30

        with patch(
            "tarsy.services.history_cleanup_service.HistoryRepository"
        ) as mock_repo_class:
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.delete_sessions_older_than.return_value = 3

            await service._cleanup_old_history()

            # Verify cutoff is approximately 30 days ago
            cutoff_arg = mock_repo.delete_sessions_older_than.call_args[0][0]

            from tarsy.utils.timestamp import now_us

            expected_cutoff = now_us() - (30 * 24 * 3600 * 1_000_000)
            assert abs(cutoff_arg - expected_cutoff) < 1_000_000  # Within 1 second

    @pytest.mark.asyncio
    async def test_cleanup_with_no_old_sessions(self, service, mock_session):
        """Test cleanup when no sessions need to be deleted."""
        with patch(
            "tarsy.services.history_cleanup_service.HistoryRepository"
        ) as mock_repo_class:
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.delete_sessions_older_than.return_value = 0

            await service._cleanup_old_history()

            mock_repo.delete_sessions_older_than.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_database_error_propagates(self, service, mock_session):
        """Test that database errors in cleanup propagate correctly."""
        from sqlalchemy.exc import OperationalError

        with patch(
            "tarsy.services.history_cleanup_service.HistoryRepository"
        ) as mock_repo_class:
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.delete_sessions_older_than.side_effect = OperationalError(
                "Database error", None, None
            )

            with pytest.raises(OperationalError):
                await service._cleanup_old_history()

    @pytest.mark.asyncio
    async def test_cleanup_handles_generic_exceptions(self, service, mock_session):
        """Test that generic exceptions are caught and re-raised."""
        with patch(
            "tarsy.services.history_cleanup_service.HistoryRepository"
        ) as mock_repo_class:
            mock_repo = Mock()
            mock_repo_class.return_value = mock_repo
            mock_repo.delete_sessions_older_than.side_effect = Exception(
                "Unexpected error"
            )

            with pytest.raises(Exception, match="Unexpected error"):
                await service._cleanup_old_history()


@pytest.mark.unit
class TestHistoryCleanupServiceLoopBehavior:
    """Test cleanup loop behavior and error handling."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""

        @contextmanager
        def factory():
            yield Mock()

        return factory

    @pytest.fixture
    def service(self, mock_session_factory):
        """Create service with mocked factory."""
        return HistoryCleanupService(
            mock_session_factory, retention_days=90, cleanup_interval_hours=12
        )

    @pytest.mark.asyncio
    async def test_cleanup_loop_handles_errors_gracefully(self, service):
        """Test that cleanup loop handles errors without crashing."""
        cleanup_count = 0

        async def mock_cleanup_with_error():
            nonlocal cleanup_count
            cleanup_count += 1
            if cleanup_count == 1:
                raise Exception("Simulated cleanup error")
            # On second call, let it succeed but stop the loop
            service.running = False

        with patch.object(service, "_cleanup_old_history", side_effect=mock_cleanup_with_error):
            await service.start()
            # Give it time to process the error and retry
            await asyncio.sleep(0.1)
            await service.stop()

        # Verify cleanup was attempted despite error
        assert cleanup_count >= 1

    @pytest.mark.asyncio
    async def test_cleanup_loop_handles_cancellation(self, service):
        """Test that cleanup loop handles cancellation properly."""
        with patch.object(service, "_cleanup_old_history") as mock_cleanup:
            mock_cleanup.return_value = asyncio.Future()
            mock_cleanup.return_value.set_result(None)

            await service.start()
            await asyncio.sleep(0.01)  # Let loop start
            await service.stop()

            assert not service.running


@pytest.mark.unit
class TestHistoryCleanupServiceEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_zero_retention_days(self):
        """Test service with zero retention days."""
        mock_factory = Mock()
        service = HistoryCleanupService(mock_factory, retention_days=0)

        assert service.retention_days == 0

    def test_very_long_retention(self):
        """Test service with very long retention period."""
        mock_factory = Mock()
        service = HistoryCleanupService(
            mock_factory, retention_days=3650  # 10 years
        )

        assert service.retention_days == 3650

    def test_frequent_cleanup(self):
        """Test service with very frequent cleanup interval."""
        mock_factory = Mock()
        service = HistoryCleanupService(
            mock_factory, retention_days=90, cleanup_interval_hours=1  # Every hour
        )

        assert service.cleanup_interval_hours == 1

    def test_infrequent_cleanup(self):
        """Test service with infrequent cleanup interval."""
        mock_factory = Mock()
        service = HistoryCleanupService(
            mock_factory, retention_days=90, cleanup_interval_hours=168  # Once a week
        )

        assert service.cleanup_interval_hours == 168

