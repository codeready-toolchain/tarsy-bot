"""History Service - manages session data and audit trails."""

import threading
from typing import Optional

from tarsy.services.history_service.history_service import HistoryService

_history_service: Optional[HistoryService] = None
_history_service_lock: threading.Lock = threading.Lock()


class HistoryServiceInitializationError(Exception):
    """Raised when HistoryService initialization fails."""

    pass


def get_history_service() -> HistoryService:
    """Get global history service instance.

    Uses double-checked locking for thread-safe lazy initialization.

    Returns:
        HistoryService: The singleton instance.

    Raises:
        HistoryServiceInitializationError: If initialization fails.
    """
    global _history_service

    # First check without lock (fast path)
    if _history_service is not None:
        return _history_service

    # Acquire lock for safe initialization
    with _history_service_lock:
        # Double-check after acquiring lock (re-read global to avoid type narrowing)
        existing = _history_service
        if existing is not None:
            return existing

        # Create and initialize the service
        service = HistoryService()
        if not service.initialize():
            raise HistoryServiceInitializationError(
                "Failed to initialize HistoryService. Check logs for details."
            )

        _history_service = service
        return service


__all__ = ["HistoryService", "HistoryServiceInitializationError", "get_history_service"]
