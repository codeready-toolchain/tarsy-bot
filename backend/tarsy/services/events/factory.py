"""Factory function for creating event listeners."""

import logging

from .base import EventListener
from .postgresql_listener import PostgreSQLEventListener
from .sqlite_listener import SQLiteEventListener

logger = logging.getLogger(__name__)


def create_event_listener(database_url: str) -> EventListener:
    """
    Create appropriate event listener based on database type.

    Args:
        database_url: Database connection string

    Returns:
        EventListener implementation (PostgreSQL or SQLite)
    """
    if database_url.startswith("postgresql://"):
        logger.info("Creating PostgreSQL event listener (LISTEN/NOTIFY)")
        return PostgreSQLEventListener(database_url)

    elif database_url.startswith("sqlite://"):
        logger.info("Creating SQLite event listener (polling)")
        return SQLiteEventListener(database_url, poll_interval=0.5)

    else:
        raise ValueError(f"Unsupported database type: {database_url}")

