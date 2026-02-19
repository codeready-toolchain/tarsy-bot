"""Base infrastructure for history service operations."""

import logging
from typing import  Final, TypeVar

from tarsy.repositories.history_repository import HistoryRepository
from tarsy.services.base_service import BaseService

T = TypeVar("T")

logger = logging.getLogger(__name__)


class _NoInteractionsSentinel:
    """Sentinel to distinguish 'no interactions found' from database failures."""
    def __repr__(self) -> str:
        return "<NO_INTERACTIONS>"


NO_INTERACTIONS: Final[_NoInteractionsSentinel] = _NoInteractionsSentinel()


class BaseHistoryInfra(BaseService[HistoryRepository]):
    """Core infrastructure: DB access, retry logic, health tracking."""
    
    def __init__(self) -> None:
        super().__init__(HistoryRepository, non_retriable_ops=["create_session"])
    
    def initialize(self) -> bool:
        """Initialize database connection and schema."""
        try:
            super()._initialize()
            logger.info("History service initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize history service: {str(e)}")
            logger.info("History service will operate in degraded mode (logging only)")
            return False
