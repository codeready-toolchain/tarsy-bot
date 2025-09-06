"""
Database dependency functions for FastAPI.

Provides database session dependencies using the existing synchronous pattern.
"""

from typing import Generator
from sqlmodel import Session, create_engine

from tarsy.config.settings import get_settings

# Create engine using existing pattern from init_db.py
def get_engine():
    """Get database engine for session creation."""
    settings = get_settings()
    return create_engine(settings.history_database_url, echo=False)

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
