"""
Database Initialization Module

Handles database schema creation and initialization for the history service.
"""

import logging
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, text

from tarsy.config.settings import get_settings, Settings
from tarsy.database.migrations import run_migrations

# Import all SQLModel table classes to ensure they are registered for schema creation
from tarsy.models.db_models import AlertSession, StageExecution  # noqa: F401
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction  # noqa: F401

logger = logging.getLogger(__name__)


def detect_database_type(database_url: str) -> str:
    """
    Detect database type from connection URL.
    
    Args:
        database_url: Database connection string
        
    Returns:
        Database type ('postgresql' or 'sqlite')
        
    Raises:
        ValueError: For unsupported database schemes
    """
    parsed = urlparse(database_url)
    scheme = parsed.scheme.lower()
    
    if scheme.startswith('postgresql'):
        return 'postgresql'
    elif scheme.startswith('sqlite'):
        return 'sqlite'
    else:
        raise ValueError(f"Unsupported database scheme: {scheme}")


def create_database_engine(database_url: str, settings: Optional[Settings] = None) -> Engine:
    """
    Create database engine with type-specific optimizations.
    
    Args:
        database_url: Database connection string
        settings: Settings instance (will get default if None)
        
    Returns:
        SQLAlchemy engine configured for the database type
    """
    if settings is None:
        settings = get_settings()
        
    db_type = detect_database_type(database_url)
    
    if db_type == 'postgresql':
        # PostgreSQL-specific configuration with connection pooling
        return create_engine(
            database_url,
            echo=False,
            pool_size=settings.postgres_pool_size,
            max_overflow=settings.postgres_max_overflow,
            pool_timeout=settings.postgres_pool_timeout,
            pool_recycle=settings.postgres_pool_recycle,
            pool_pre_ping=settings.postgres_pool_pre_ping,
            # PostgreSQL-specific connection parameters
            connect_args={
                "application_name": "tarsy",
                "options": "-c timezone=UTC"
            }
        )
    else:  # SQLite
        # SQLite-specific configuration
        connect_args = {"check_same_thread": False}
        
        # Special handling for SQLite in-memory databases
        if database_url == "sqlite:///:memory:" or database_url.startswith("sqlite:///:memory:"):
            return create_engine(
                database_url,
                echo=False,
                poolclass=StaticPool,
                connect_args=connect_args
            )
        else:
            return create_engine(
                database_url,
                echo=False,
                connect_args=connect_args
            )


def create_database_tables(database_url: str) -> bool:
    """
    Create database tables using SQLModel metadata.
    
    Args:
        database_url: Database connection string
        
    Returns:
        True if tables created successfully, False otherwise
    """
    try:
        # Create engine with type-specific optimizations
        engine = create_database_engine(database_url)
        
        # Create all tables defined in SQLModel models
        SQLModel.metadata.create_all(engine)
        
        # Test connection with a simple query
        with Session(engine) as session:
            # Test basic connectivity
            session.exec(text("SELECT 1")).first()
        
        logger.info(f"Database tables created successfully for: {database_url.split('/')[-1]}")
        return True
        
    except OperationalError as e:
        logger.error(f"Database operational error during table creation: {str(e)}")
        return False
    except SQLAlchemyError as e:
        logger.error(f"SQLAlchemy error during table creation: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during table creation: {str(e)}")
        return False


def initialize_database() -> bool:
    """
    Initialize the history database based on configuration.
    
    Uses Alembic migrations to create and update database schema automatically.
    This replaces the old create_all() approach with proper version tracking.
    
    Returns:
        True if initialization successful or disabled, False if failed
    """
    try:
        settings = get_settings()
        
        # Check if history service is enabled
        if not settings.history_enabled:
            logger.info("History service disabled - skipping database initialization")
            return True
        
        # Validate configuration
        if not settings.database_url:
            logger.error("Database URL not configured but history service is enabled")
            return False
        
        if settings.history_retention_days <= 0:
            logger.warning(f"Invalid retention days ({settings.history_retention_days}), using default 90 days")
        
        # Run database migrations (creates tables and applies any pending migrations)
        logger.info("Initializing database with migration system...")
        success = run_migrations(settings.database_url)
        
        if success:
            logger.info("History database initialization completed successfully")
            logger.info(f"Database: {settings.database_url.split('/')[-1]}")
            logger.info(f"Retention policy: {settings.history_retention_days} days")
        else:
            logger.error("History database initialization failed")
        
        return success
        
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}", exc_info=True)
        return False


def test_database_connection(database_url: Optional[str] = None) -> bool:
    """
    Test database connectivity.
    
    Args:
        database_url: Optional database URL, uses settings if not provided
        
    Returns:
        True if connection successful, False otherwise
    """
    try:
        if not database_url:
            settings = get_settings()
            if not settings.history_enabled:
                return False
            database_url = settings.database_url
        
        # Create engine with optimizations and test connection
        engine = create_database_engine(database_url)
        
        with Session(engine) as session:
            # Simple connectivity test
            result = session.exec(text("SELECT 1")).first()
            return result[0] == 1
            
    except Exception as e:
        logger.debug(f"Database connection test failed: {str(e)}")
        return False


def get_database_info() -> dict:
    """
    Get database configuration information.
    
    Returns:
        Dictionary containing database information
    """
    try:
        settings = get_settings()
        
        return {
            "enabled": settings.history_enabled,
            # Omit DSN to avoid credential leakage
            "database_name": settings.database_url.split('/')[-1] if settings.history_enabled else None,
            "retention_days": settings.history_retention_days if settings.history_enabled else None,
            "connection_test": test_database_connection() if settings.history_enabled else False,
        }
        
    except Exception as e:
        logger.error(f"Failed to get database info: {str(e)}")
        return {
            "enabled": False,
            "error": str(e)
        }


# Async database engine and session factory (for event system)
_async_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def create_async_database_engine(database_url: str, settings: Optional[Settings] = None) -> AsyncEngine:
    """
    Create async database engine for event system.
    
    Args:
        database_url: Database connection string
        settings: Settings instance (will get default if None)
        
    Returns:
        SQLAlchemy async engine configured for the database type
    """
    if settings is None:
        settings = get_settings()
        
    db_type = detect_database_type(database_url)
    
    if db_type == 'postgresql':
        # PostgreSQL async URL
        if not database_url.startswith('postgresql+asyncpg://'):
            database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://')
        
        # PostgreSQL-specific configuration with connection pooling
        return create_async_engine(
            database_url,
            echo=False,
            pool_size=settings.postgres_pool_size,
            max_overflow=settings.postgres_max_overflow,
            pool_timeout=settings.postgres_pool_timeout,
            pool_recycle=settings.postgres_pool_recycle,
            pool_pre_ping=settings.postgres_pool_pre_ping,
            connect_args={
                "server_settings": {"application_name": "tarsy-events"}
            }
        )
    else:  # SQLite
        # SQLite async URL
        if not database_url.startswith('sqlite+aiosqlite://'):
            database_url = database_url.replace('sqlite://', 'sqlite+aiosqlite://')
        
        connect_args = {"check_same_thread": False}
        
        # Special handling for SQLite in-memory databases
        if ':memory:' in database_url:
            return create_async_engine(
                database_url,
                echo=False,
                poolclass=StaticPool,
                connect_args=connect_args
            )
        else:
            return create_async_engine(
                database_url,
                echo=False,
                connect_args=connect_args
            )


def initialize_async_database(database_url: Optional[str] = None) -> None:
    """
    Initialize async database engine and session factory for event system.
    
    Args:
        database_url: Optional database URL, uses settings if not provided
    """
    global _async_engine, _async_session_factory
    
    if database_url is None:
        settings = get_settings()
        database_url = settings.database_url
    
    _async_engine = create_async_database_engine(database_url)
    _async_session_factory = async_sessionmaker(
        _async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    logger.info(f"Async database engine initialized for: {database_url.split('/')[-1]}")


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """
    Get async session factory for event system.
    
    Returns:
        Async session factory
        
    Raises:
        RuntimeError: If async database not initialized
    """
    if _async_session_factory is None:
        raise RuntimeError("Async database not initialized. Call initialize_async_database() first.")
    return _async_session_factory


async def dispose_async_database() -> None:
    """Dispose async database engine and cleanup resources."""
    global _async_engine, _async_session_factory
    
    if _async_engine:
        await _async_engine.dispose()
        logger.info("Async database engine disposed")
    
    _async_engine = None
    _async_session_factory = None 