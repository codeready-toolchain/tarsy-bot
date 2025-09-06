"""
Database Package

Contains database initialization and management utilities.
"""

from .init_db import initialize_database
from .dependencies import get_session

__all__ = ["initialize_database", "get_session"] 