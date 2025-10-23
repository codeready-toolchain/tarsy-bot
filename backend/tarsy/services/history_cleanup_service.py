"""Background service for cleaning up old history data from alert_sessions table."""

import asyncio
import logging
import time
from typing import Callable, ContextManager, Optional

from sqlmodel import Session

from tarsy.repositories.history_repository import HistoryRepository
from tarsy.utils.timestamp import now_us

logger = logging.getLogger(__name__)


class HistoryCleanupService:
    """
    Periodically cleans up old alert processing history and orphaned sessions.

    Runs as background task on each pod (idempotent - multiple pods
    running cleanup simultaneously is safe).
    
    Two cleanup operations:
    1. Orphaned sessions: Checked every N minutes (default: 10)
    2. Old history retention: Checked every M hours (default: 12)
    
    Uses HistoryRepository for type-safe database operations with CASCADE deletes.
    """

    def __init__(
        self,
        db_session_factory: Callable[[], ContextManager[Session]],
        retention_days: int = 90,
        retention_cleanup_interval_hours: int = 12,
        orphaned_timeout_minutes: int = 30,
        orphaned_check_interval_minutes: int = 10,
    ):
        """
        Initialize history cleanup service.

        Args:
            db_session_factory: Context manager that yields sync database session
            retention_days: Keep history for N days (default: 90)
            retention_cleanup_interval_hours: Run retention cleanup every N hours (default: 12)
            orphaned_timeout_minutes: Mark sessions as orphaned if no activity for N minutes (default: 30)
            orphaned_check_interval_minutes: Check for orphaned sessions every N minutes (default: 10)
        """
        self.db_session_factory = db_session_factory
        self.retention_days = retention_days
        self.retention_cleanup_interval_hours = retention_cleanup_interval_hours
        self.orphaned_timeout_minutes = orphaned_timeout_minutes
        self.orphaned_check_interval_minutes = orphaned_check_interval_minutes

        self.cleanup_task: Optional[asyncio.Task] = None
        self.running = False
        self.last_retention_cleanup_time: float = 0.0  # Track last retention cleanup

    async def start(self) -> None:
        """Start background cleanup task."""
        # Guard against double start to prevent duplicate background tasks
        if self.cleanup_task and not self.cleanup_task.done():
            logger.warning("History cleanup service already running; ignoring start()")
            return
        
        self.running = True
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())

        logger.info(
            f"History cleanup service started "
            f"(orphaned sessions: check every {self.orphaned_check_interval_minutes}m, "
            f"timeout: {self.orphaned_timeout_minutes}m | "
            f"retention: {self.retention_days} days, "
            f"check every {self.retention_cleanup_interval_hours}h)"
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
            # Clear task reference to make state explicit
            self.cleanup_task = None

        logger.info("History cleanup service stopped")

    async def _cleanup_loop(self) -> None:
        """
        Background task that runs cleanup periodically.
        
        Checks for orphaned sessions every N minutes.
        Checks for old history retention every M hours.
        """
        while self.running:
            try:
                # Always check for orphaned sessions
                await self._cleanup_orphaned_sessions()
                
                # Only cleanup old history when interval has elapsed
                if self._should_run_retention_cleanup():
                    await self._cleanup_old_history()
                    self._update_last_retention_cleanup()
                
                # Wait until next orphaned session check
                await asyncio.sleep(self.orphaned_check_interval_minutes * 60)

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
    
    async def _cleanup_orphaned_sessions(self) -> int:
        """
        Check for and mark orphaned sessions as failed.
        
        Returns:
            Number of sessions marked as failed
        """
        try:
            # Run synchronous database operation in thread pool to avoid blocking event loop
            cleaned_count = await asyncio.to_thread(self._cleanup_orphaned_sync)

            if cleaned_count > 0:
                logger.info(
                    f"Marked {cleaned_count} orphaned session(s) as failed "
                    f"(inactive for {self.orphaned_timeout_minutes}+ minutes)"
                )
            else:
                logger.debug("No orphaned sessions to clean up")
            
            return cleaned_count

        except Exception as e:
            logger.error(f"Failed to cleanup orphaned sessions: {e}", exc_info=True)
            raise
    
    def _cleanup_orphaned_sync(self) -> int:
        """
        Mark orphaned sessions as failed synchronously (called from thread pool).
        
        Returns:
            Number of sessions marked as failed
        """
        from tarsy.services.history_service import get_history_service
        
        # Get history service instance
        history_service = get_history_service()
        
        # Call the existing cleanup_orphaned_sessions method
        return history_service.cleanup_orphaned_sessions(self.orphaned_timeout_minutes)
    
    def _should_run_retention_cleanup(self) -> bool:
        """
        Check if enough time has elapsed since last retention cleanup.
        
        Returns:
            True if retention cleanup should run, False otherwise
        """
        if self.last_retention_cleanup_time == 0.0:
            # Never run before - run now
            return True
        
        elapsed_hours = (time.time() - self.last_retention_cleanup_time) / 3600
        return elapsed_hours >= self.retention_cleanup_interval_hours
    
    def _update_last_retention_cleanup(self) -> None:
        """Update the timestamp of the last retention cleanup."""
        self.last_retention_cleanup_time = time.time()

