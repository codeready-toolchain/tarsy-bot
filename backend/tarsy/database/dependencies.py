"""
Database dependency functions for FastAPI.

Provides database session dependencies using the existing synchronous pattern.
"""

from typing import Generator
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from tarsy.config.settings import get_settings

# Module-level cached engine
_cached_engine: Engine | None = None

def get_engine() -> Engine:
    """Get database engine for session creation."""
    global _cached_engine
    if _cached_engine is None:
        settings = get_settings()
        _cached_engine = create_engine(settings.history_database_url, echo=False)
    return _cached_engine

def get_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency to provide database session.
    
    Uses the same synchronous session pattern as the rest of the codebase.
    
    Yields:
        Session: Database session for operations
    """
    engine = get_engine()
    with Session(engine) as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
