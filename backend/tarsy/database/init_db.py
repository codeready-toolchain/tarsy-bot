"""
Database Initialization Module

Handles database schema creation and initialization for the history service.
"""

import logging
from typing import Optional

from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlmodel import Session, SQLModel, create_engine, text

from tarsy.config.settings import get_settings

# Import all SQLModel table classes to ensure they are registered for schema creation
from tarsy.models.db_models import AlertSession, StageExecution  # noqa: F401
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction  # noqa: F401

logger = logging.getLogger(__name__)


def create_database_tables(database_url: str) -> bool:
    """
    Create database tables using SQLModel metadata.
    
    Args:
        database_url: Database connection string
        
    Returns:
        True if tables created successfully, False otherwise
    """
    try:
        # Create engine
        engine = create_engine(database_url, echo=False)
        
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
        if not settings.history_database_url:
            logger.error("History database URL not configured but history service is enabled")
            return False
        
        if settings.history_retention_days <= 0:
            logger.warning(f"Invalid retention days ({settings.history_retention_days}), using default 90 days")
        
        # Create database tables
        success = create_database_tables(settings.history_database_url)
        
        if success:
            logger.info("History database initialization completed successfully")
            logger.info(f"Database: {settings.history_database_url.split('/')[-1]}")
            logger.info(f"Retention policy: {settings.history_retention_days} days")
        else:
            logger.error("History database initialization failed")
        
        return success
        
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")
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
            database_url = settings.history_database_url
        
        # Create engine and test connection
        engine = create_engine(database_url, echo=False)
        
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
            "database_url": settings.history_database_url if settings.history_enabled else None,
            "database_name": settings.history_database_url.split('/')[-1] if settings.history_enabled else None,
            "retention_days": settings.history_retention_days if settings.history_enabled else None,
            "connection_test": test_database_connection() if settings.history_enabled else False
        }
        
    except Exception as e:
        logger.error(f"Failed to get database info: {str(e)}")
        return {
            "enabled": False,
            "error": str(e)
        } 