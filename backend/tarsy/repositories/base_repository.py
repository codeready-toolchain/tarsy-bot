"""
Base repository pattern for database operations.

Provides common database operations and session management using SQLModel
for all repository classes in the system.
"""

import logging
from abc import ABC
from typing import Any, Generic, Optional, TypeVar

from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlmodel import Session, SQLModel, select

from tarsy.database.init_db import create_database_engine

logger = logging.getLogger(__name__)

# Generic type for SQLModel classes
ModelType = TypeVar("ModelType", bound=SQLModel)


class BaseRepository(ABC, Generic[ModelType]):
    """
    Abstract base repository providing common database operations.
    
    This class provides a foundation for all repository classes with
    common CRUD operations, session management, and query patterns.
    """
    
    def __init__(self, session: Session, model_class: type[ModelType]):
        """
        Initialize base repository with database session and model class.
        
        Args:
            session: SQLModel database session
            model_class: The SQLModel class this repository manages
        """
        self.session = session
        self.model_class = model_class
    
    def create(self, obj: ModelType) -> ModelType:
        """
        Create a new record in the database.
        
        Args:
            obj: The model instance to create
            
        Returns:
            The created model instance with database-generated fields populated
        """
        try:
            self.session.add(obj)
            self.session.commit()
            self.session.refresh(obj)
            logger.debug(f"Created {self.model_class.__name__} with ID: {getattr(obj, 'id', 'N/A')}")
            return obj
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to create {self.model_class.__name__}: {str(e)}")
            raise
    
    def get_by_id(self, id_value: Any) -> Optional[ModelType]:
        """
        Retrieve a record by its primary key.
        
        Args:
            id_value: The primary key value
            
        Returns:
            The model instance if found, None otherwise
        """
        try:
            statement = select(self.model_class).where(
                getattr(self.model_class, self._get_primary_key_field()) == id_value
            )
            result = self.session.exec(statement).first()
            return result
        except Exception as e:
            logger.error(f"Failed to get {self.model_class.__name__} by ID {id_value}: {str(e)}")
            raise
    
    def update(self, obj: ModelType) -> ModelType:
        """
        Update an existing record in the database.
        
        Args:
            obj: The model instance to update
            
        Returns:
            The updated model instance
        """
        try:
            self.session.add(obj)
            self.session.commit()
            self.session.refresh(obj)
            logger.debug(f"Updated {self.model_class.__name__} with ID: {getattr(obj, 'id', 'N/A')}")
            return obj
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to update {self.model_class.__name__}: {str(e)}")
            raise
    
    def _get_primary_key_field(self) -> str:
        """
        Get the name of the primary key field for this model.
        
        Returns:
            The primary key field name
        """
        # Try to get primary key from SQLModel field annotations
        try:
            for field_name, field_info in self.model_class.__fields__.items():
                # Check if field_info has primary_key attribute directly
                if hasattr(field_info, 'primary_key') and field_info.primary_key:
                    return field_name
                # Check nested field_info structure
                if hasattr(field_info, 'field_info') and hasattr(field_info.field_info, 'primary_key'):
                    if field_info.field_info.primary_key:
                        return field_name
        except Exception:
            pass
        
        # Fallback to common primary key names
        for common_pk in ['session_id', 'interaction_id', 'communication_id', 'id']:
            if hasattr(self.model_class, common_pk):
                return common_pk
        
        raise ValueError(f"No primary key field found for {self.model_class.__name__}")


class DatabaseManager:
    """
    Database connection and session management.
    
    Provides centralized database configuration and session management
    for all repository classes.
    """
    
    def __init__(self, database_url: str):
        """
        Initialize database manager with connection URL.
        
        Args:
            database_url: SQLAlchemy database connection string
        """
        self.database_url = database_url
        self.engine: Optional[Engine] = None
        self.session_factory: Optional[sessionmaker] = None
        
    def initialize(self) -> None:
        """Initialize database engine and session factory using optimized configuration."""
        try:
            # Use the enhanced database engine creation with type-specific optimizations
            self.engine = create_database_engine(self.database_url)
            
            # Enable WAL mode for SQLite for better concurrency
            if self.database_url.startswith('sqlite'):
                with self.engine.connect() as conn:
                    conn.execute(text("PRAGMA journal_mode=WAL"))
                    conn.execute(text("PRAGMA synchronous=NORMAL")) 
                    conn.execute(text("PRAGMA cache_size=10000"))
                    conn.execute(text("PRAGMA temp_store=memory"))
                    conn.execute(text("PRAGMA wal_autocheckpoint=1000"))
                    conn.commit()
                    logger.info("SQLite configured for better concurrency with WAL mode")
            
            self.session_factory = sessionmaker(
                bind=self.engine,
                class_=Session,
                expire_on_commit=False
            )
            
            safe_url = make_url(self.database_url).render_as_string(hide_password=True)
            logger.info(f"Database initialized with URL: {safe_url}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {str(e)}")
            raise
    
    def create_tables(self) -> None:
        """Create all tables defined by SQLModel models."""
        try:
            if not self.engine:
                raise RuntimeError("Database not initialized")
                
            SQLModel.metadata.create_all(self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {str(e)}")
            raise
    
    def get_session(self) -> Session:
        """
        Get a new database session.
        
        Returns:
            A new SQLModel Session instance
        """
        if not self.session_factory:
            raise RuntimeError("Database not initialized")
            
        return self.session_factory()
    
    def close(self) -> None:
        """Close database connections."""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connections closed") 