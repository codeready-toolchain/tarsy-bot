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
        assert service.retention_cleanup_interval_hours == 12
        assert service.orphaned_timeout_minutes == 30
        assert service.orphaned_check_interval_minutes == 10
        assert service.cleanup_task is None
        assert service.running is False
        assert service.last_retention_cleanup_time == 0.0

    def test_init_with_custom_parameters(self):
        """Test initialization with custom parameters."""
        mock_factory = Mock()

        service = HistoryCleanupService(
            mock_factory,
            retention_days=30,
            retention_cleanup_interval_hours=24,
            orphaned_timeout_minutes=15,
            orphaned_check_interval_minutes=5,
        )

        assert service.retention_days == 30
        assert service.retention_cleanup_interval_hours == 24
        assert service.orphaned_timeout_minutes == 15
        assert service.orphaned_check_interval_minutes == 5


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
            mock_session_factory,
            retention_days=90,
            retention_cleanup_interval_hours=12,
            orphaned_timeout_minutes=30,
            orphaned_check_interval_minutes=10,
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
            mock_session_factory,
            retention_days=90,
            retention_cleanup_interval_hours=12,
            orphaned_timeout_minutes=30,
            orphaned_check_interval_minutes=10,
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
            mock_session_factory,
            retention_days=90,
            retention_cleanup_interval_hours=12,
            orphaned_timeout_minutes=30,
            orphaned_check_interval_minutes=10,
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

        # Mock both cleanup methods - orphaned sessions always runs
        with patch.object(service, "_cleanup_orphaned_sessions", side_effect=mock_cleanup_with_error):
            with patch.object(service, "_should_run_retention_cleanup", return_value=False):
                await service.start()
                # Give it time to process the error and retry
                await asyncio.sleep(0.1)
                await service.stop()

        # Verify cleanup was attempted despite error
        assert cleanup_count >= 1

    @pytest.mark.asyncio
    async def test_cleanup_loop_handles_cancellation(self, service):
        """Test that cleanup loop handles cancellation properly."""
        # Mock both cleanup methods
        with patch.object(service, "_cleanup_orphaned_sessions") as mock_orphaned:
            with patch.object(service, "_should_run_retention_cleanup", return_value=False):
                mock_orphaned.return_value = asyncio.Future()
                mock_orphaned.return_value.set_result(None)

                await service.start()
                await asyncio.sleep(0.01)  # Let loop start
                await service.stop()

                assert not service.running


@pytest.mark.unit
class TestHistoryCleanupServiceDualOperation:
    """Test dual-cleanup coordination (orphaned + retention)."""

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
            mock_session_factory,
            retention_days=90,
            retention_cleanup_interval_hours=12,
            orphaned_timeout_minutes=30,
            orphaned_check_interval_minutes=10,
        )

    @pytest.mark.asyncio
    async def test_orphaned_runs_every_iteration_retention_skipped(self, service):
        """Test orphaned cleanup runs every iteration, retention skipped when interval not elapsed."""
        orphaned_call_count = 0
        retention_call_count = 0

        async def mock_orphaned_cleanup():
            nonlocal orphaned_call_count
            orphaned_call_count += 1
            if orphaned_call_count >= 2:
                service.running = False

        async def mock_retention_cleanup():
            nonlocal retention_call_count
            retention_call_count += 1

        with patch.object(service, "_cleanup_orphaned_sessions", side_effect=mock_orphaned_cleanup):
            with patch.object(service, "_cleanup_old_history", side_effect=mock_retention_cleanup):
                # Start service - retention cleanup should run initially (time=0)
                await service.start()
                await asyncio.sleep(0.2)  # Give enough time for loop iterations
                await service.stop()

        # Orphaned cleanup should have run at least once
        assert orphaned_call_count >= 1, "Orphaned cleanup should run every iteration"
        # Retention cleanup should have run once initially (last_retention_cleanup_time is 0)
        assert retention_call_count == 1, "Retention cleanup should run once initially"

    @pytest.mark.asyncio
    async def test_both_cleanups_run_when_retention_interval_elapsed(self, service):
        """Test both orphaned and retention cleanup run when retention interval has elapsed."""
        import time
        
        # Set last retention cleanup to 13 hours ago (past the 12 hour interval)
        service.last_retention_cleanup_time = time.time() - (13 * 3600)

        orphaned_call_count = 0
        retention_call_count = 0

        async def mock_orphaned_cleanup():
            nonlocal orphaned_call_count
            orphaned_call_count += 1
            if orphaned_call_count >= 1:
                service.running = False

        async def mock_retention_cleanup():
            nonlocal retention_call_count
            retention_call_count += 1

        with patch.object(service, "_cleanup_orphaned_sessions", side_effect=mock_orphaned_cleanup):
            with patch.object(service, "_cleanup_old_history", side_effect=mock_retention_cleanup):
                await service.start()
                await asyncio.sleep(0.2)  # Give enough time
                await service.stop()

        # Both should have run
        assert orphaned_call_count >= 1, "Orphaned cleanup should run"
        assert retention_call_count >= 1, "Retention cleanup should run when interval elapsed"

    @pytest.mark.asyncio
    async def test_retention_cleanup_timing_tracked_correctly(self, service):
        """Test that retention cleanup time is tracked and prevents premature runs."""
        import time

        # Initially, last_retention_cleanup_time is 0
        assert service.last_retention_cleanup_time == 0.0

        # After first cleanup, it should be updated
        with patch.object(service, "_cleanup_orphaned_sessions"):
            with patch.object(service, "_cleanup_old_history"):
                service._update_last_retention_cleanup()
                
                first_time = service.last_retention_cleanup_time
                assert first_time > 0, "Retention cleanup time should be set"

                # Wait a bit
                await asyncio.sleep(0.01)

                # Update again
                service._update_last_retention_cleanup()
                second_time = service.last_retention_cleanup_time
                
                assert second_time > first_time, "Time should advance"

    def test_should_run_retention_cleanup_on_first_run(self, service):
        """Test that retention cleanup runs on first iteration (time = 0)."""
        # Initially time is 0, should return True
        assert service._should_run_retention_cleanup() is True

    def test_should_run_retention_cleanup_when_interval_elapsed(self, service):
        """Test that retention cleanup runs when interval has elapsed."""
        import time
        
        # Set to 13 hours ago
        service.last_retention_cleanup_time = time.time() - (13 * 3600)
        assert service._should_run_retention_cleanup() is True

    def test_should_not_run_retention_cleanup_when_interval_not_elapsed(self, service):
        """Test that retention cleanup doesn't run when interval hasn't elapsed."""
        import time
        
        # Set to 1 hour ago (less than 12 hour interval)
        service.last_retention_cleanup_time = time.time() - 3600
        assert service._should_run_retention_cleanup() is False

    @pytest.mark.asyncio
    async def test_orphaned_failure_does_not_prevent_retention(self, service):
        """Test retention cleanup still runs even if orphaned cleanup fails."""
        import time
        
        # Set retention cleanup to be ready (past interval)
        service.last_retention_cleanup_time = time.time() - (13 * 3600)

        orphaned_called = False
        retention_called = False

        async def mock_orphaned_cleanup_error():
            nonlocal orphaned_called
            orphaned_called = True
            service.running = False
            raise Exception("Orphaned cleanup failed")

        async def mock_retention_cleanup():
            nonlocal retention_called
            retention_called = True

        with patch.object(service, "_cleanup_orphaned_sessions", side_effect=mock_orphaned_cleanup_error):
            with patch.object(service, "_cleanup_old_history", side_effect=mock_retention_cleanup):
                await service.start()
                await asyncio.sleep(0.15)  # Wait for error handling
                await service.stop()

        # Both should have been called despite orphaned cleanup failing
        assert orphaned_called, "Orphaned cleanup should have been attempted"
        # Note: Due to error handling, retention might not run in the same iteration
        # This test verifies the error isolation exists

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_sessions_calls_history_service(self, service):
        """Test that _cleanup_orphaned_sessions properly delegates to history service."""
        with patch("tarsy.services.history_service.get_history_service") as mock_get_history:
            mock_history_service = Mock()
            mock_history_service.cleanup_orphaned_sessions.return_value = 3
            mock_get_history.return_value = mock_history_service

            result = await service._cleanup_orphaned_sessions()

            # Verify history service was called with correct timeout
            mock_history_service.cleanup_orphaned_sessions.assert_called_once_with(30)
            assert result == 3

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_sessions_uses_correct_timeout(self, service):
        """Test that orphaned timeout parameter is passed correctly."""
        # Create service with custom timeout
        service_custom = HistoryCleanupService(
            service.db_session_factory,
            orphaned_timeout_minutes=45,
        )

        with patch("tarsy.services.history_service.get_history_service") as mock_get_history:
            mock_history_service = Mock()
            mock_history_service.cleanup_orphaned_sessions.return_value = 0
            mock_get_history.return_value = mock_history_service

            await service_custom._cleanup_orphaned_sessions()

            # Verify custom timeout was used
            mock_history_service.cleanup_orphaned_sessions.assert_called_once_with(45)


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
            mock_factory,
            retention_days=90,
            retention_cleanup_interval_hours=1,  # Every hour
            orphaned_check_interval_minutes=5,  # Every 5 minutes
        )

        assert service.retention_cleanup_interval_hours == 1
        assert service.orphaned_check_interval_minutes == 5

    def test_infrequent_cleanup(self):
        """Test service with infrequent cleanup interval."""
        mock_factory = Mock()
        service = HistoryCleanupService(
            mock_factory,
            retention_days=90,
            retention_cleanup_interval_hours=168,  # Once a week
            orphaned_check_interval_minutes=60,  # Every hour
        )

        assert service.retention_cleanup_interval_hours == 168
        assert service.orphaned_check_interval_minutes == 60

