"""History Service - manages session data and audit trails."""

from typing import Optional

from tarsy.services.history_service.history_service import HistoryService

_history_service: Optional[HistoryService] = None


def get_history_service() -> HistoryService:
    """Get global history service instance."""
    global _history_service
    if _history_service is None:
        _history_service = HistoryService()
        _history_service.initialize()
    return _history_service


__all__ = ['HistoryService', 'get_history_service']
