"""Background service for cleaning up old history data from alert_sessions table."""

import asyncio
import logging
from typing import Callable, Optional

from sqlmodel import Session

from tarsy.repositories.history_repository import HistoryRepository
from tarsy.utils.timestamp import now_us

logger = logging.getLogger(__name__)


class HistoryCleanupService:
    """
    Periodically cleans up old alert processing history based on retention policy.

    Runs as background task on each pod (idempotent - multiple pods
    running cleanup simultaneously is safe).
    Uses HistoryRepository for type-safe database operations with CASCADE deletes.
    """

    def __init__(
        self,
        db_session_factory: Callable[[], Session],
        retention_days: int = 90,
        cleanup_interval_hours: int = 12,
    ):
        """
        Initialize history cleanup service.

        Args:
            db_session_factory: Context manager that yields sync database session
            retention_days: Keep history for N days (default: 90)
            cleanup_interval_hours: Run cleanup every N hours (default: 12)
        """
        self.db_session_factory = db_session_factory
        self.retention_days = retention_days
        self.cleanup_interval_hours = cleanup_interval_hours

        self.cleanup_task: Optional[asyncio.Task] = None
        self.running = False

    async def start(self) -> None:
        """Start background cleanup task."""
        self.running = True
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info(
            f"History cleanup service started "
            f"(retention: {self.retention_days} days, "
            f"interval: {self.cleanup_interval_hours}h)"
        )

    async def stop(self) -> None:
        """Stop cleanup task gracefully."""
        self.running = False

        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("History cleanup service stopped")

    async def _cleanup_loop(self) -> None:
        """Background task that runs cleanup periodically."""
        while self.running:
            try:
                await self._cleanup_old_history()

                # Wait until next cleanup
                await asyncio.sleep(self.cleanup_interval_hours * 3600)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in history cleanup loop: {e}", exc_info=True)
                # Back off on errors to avoid tight error loops
                await asyncio.sleep(300)  # Wait 5 minutes

    async def _cleanup_old_history(self) -> int:
        """
        Delete history records older than retention period using repository.
        
        Returns:
            Number of sessions deleted
        """
        try:
            # Run synchronous database operation in thread pool to avoid blocking event loop
            deleted_count = await asyncio.to_thread(self._delete_old_sessions)

            if deleted_count > 0:
                logger.info(
                    f"Cleaned up {deleted_count} alert session(s) older than "
                    f"{self.retention_days} days"
                )
            else:
                logger.debug("No old history data to clean up")
            
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old history: {e}", exc_info=True)
            raise

    def _delete_old_sessions(self) -> int:
        """
        Delete old sessions synchronously (called from thread pool).

        Returns:
            Number of sessions deleted
        """
        with self.db_session_factory() as session:
            # Create repository instance
            history_repo = HistoryRepository(session)

            # Calculate cutoff timestamp (microseconds since epoch)
            # Delete sessions started before retention_days ago
            retention_microseconds = self.retention_days * 24 * 3600 * 1_000_000
            cutoff_timestamp_us = now_us() - retention_microseconds

            # Delete old sessions (CASCADE handles related records)
            deleted_count = history_repo.delete_sessions_older_than(cutoff_timestamp_us)

            return deleted_count

