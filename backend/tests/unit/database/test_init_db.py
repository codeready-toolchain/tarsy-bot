"""
Unit tests for database initialization module.

Tests database table creation, initialization, and connection testing functionality
to ensure the history service database is properly set up.
"""

from unittest.mock import Mock, patch, MagicMock
import pytest
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from tarsy.database.init_db import (
    create_database_tables,
    initialize_database,
    test_database_connection,
    get_database_info
)


@pytest.mark.unit
class TestCreateDatabaseTables:
    """Test create_database_tables function."""
    
    def test_create_database_tables_success(self):
        """Test successful database table creation."""
        with patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.SQLModel') as mock_sqlmodel, \
             patch('tarsy.database.init_db.Session') as mock_session:
            
            # Mock engine and session
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            mock_session_instance = Mock()
            mock_session.return_value.__enter__.return_value = mock_session_instance
            mock_session_instance.exec.return_value.first.return_value = 1
            
            # Mock SQLModel metadata
            mock_metadata = Mock()
            mock_sqlmodel.metadata = mock_metadata
            
            result = create_database_tables("sqlite:///test.db")
            
            assert result is True
            mock_create_engine.assert_called_once_with("sqlite:///test.db", echo=False)
            mock_metadata.create_all.assert_called_once_with(mock_engine)
            mock_session.assert_called_once_with(mock_engine)
    
    def test_create_database_tables_errors(self):
        """Test database table creation with various error conditions."""
        # Test operational error
        with patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_create_engine.side_effect = OperationalError("Connection failed", None, None)
            result = create_database_tables("sqlite:///test.db")
            assert result is False
            mock_logger.error.assert_called_once()
        
        # Test SQLAlchemy error
        with patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.SQLModel') as mock_sqlmodel, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            mock_sqlmodel.metadata.create_all.side_effect = SQLAlchemyError("Schema error")
            result = create_database_tables("sqlite:///test.db")
            assert result is False
            mock_logger.error.assert_called_once()
        
        # Test session test failure
        with patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.SQLModel') as mock_sqlmodel, \
             patch('tarsy.database.init_db.Session') as mock_session, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            mock_session_instance = Mock()
            mock_session.return_value.__enter__.return_value = mock_session_instance
            mock_session_instance.exec.side_effect = OperationalError("Query failed", None, None)
            mock_metadata = Mock()
            mock_sqlmodel.metadata = mock_metadata
            
            result = create_database_tables("sqlite:///test.db")
            assert result is False
            mock_logger.error.assert_called_once()


@pytest.mark.unit
class TestInitializeDatabase:
    """Test initialize_database function."""
    
    def test_initialize_database_scenarios(self):
        """Test database initialization with various scenarios."""
        # Test successful initialization
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.create_database_tables') as mock_create_tables, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = "sqlite:///history.db"
            mock_settings.history_retention_days = 90
            mock_get_settings.return_value = mock_settings
            mock_create_tables.return_value = True
            
            result = initialize_database()
            assert result is True
            mock_create_tables.assert_called_once_with("sqlite:///history.db")
        
        # Test history disabled
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_settings = Mock()
            mock_settings.history_enabled = False
            mock_get_settings.return_value = mock_settings
            
            result = initialize_database()
            assert result is True
        
        # Test missing URL
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = None
            mock_get_settings.return_value = mock_settings
            
            result = initialize_database()
            assert result is False
        
        # Test table creation failure
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.create_database_tables') as mock_create_tables, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = "sqlite:///history.db"
            mock_settings.history_retention_days = 90
            mock_get_settings.return_value = mock_settings
            mock_create_tables.return_value = False
            
            result = initialize_database()
            assert result is False


@pytest.mark.unit  
class TestDatabaseConnection:
    """Test test_database_connection function."""
    
    def test_database_connection_scenarios(self):
        """Test database connection with various scenarios."""
        # Test successful connection with URL
        with patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.Session') as mock_session:
            
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            mock_session_instance = Mock()
            mock_session.return_value.__enter__.return_value = mock_session_instance
            mock_session_instance.exec.return_value.first.return_value = [1]
            
            result = test_database_connection("sqlite:///test.db")
            assert result is True
            mock_create_engine.assert_called_once_with("sqlite:///test.db", echo=False)
        
        # Test successful connection from settings
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.Session') as mock_session:
            
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = "sqlite:///history.db"
            mock_get_settings.return_value = mock_settings
            
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            mock_session_instance = Mock()
            mock_session.return_value.__enter__.return_value = mock_session_instance
            mock_session_instance.exec.return_value.first.return_value = [1]
            
            result = test_database_connection()
            assert result is True
            mock_create_engine.assert_called_once_with("sqlite:///history.db", echo=False)
        
        # Test history disabled
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings:
            mock_settings = Mock()
            mock_settings.history_enabled = False
            mock_get_settings.return_value = mock_settings
            
            result = test_database_connection()
            assert result is False
        
        # Test connection failure
        with patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_create_engine.side_effect = Exception("Connection failed")
            result = test_database_connection("sqlite:///test.db")
            assert result is False


@pytest.mark.unit
class TestGetDatabaseInfo:
    """Test get_database_info function."""
    
    def test_get_database_info_scenarios(self):
        """Test getting database info with various scenarios."""
        # Test enabled with successful connection
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.test_database_connection') as mock_test_connection:
            
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = "sqlite:///history.db"
            mock_settings.history_retention_days = 90
            mock_get_settings.return_value = mock_settings
            mock_test_connection.return_value = True
            
            result = get_database_info()
            expected = {
                "enabled": True,
                "database_url": "sqlite:///history.db",
                "database_name": "history.db",
                "retention_days": 90,
                "connection_test": True
            }
            assert result == expected
        
        # Test disabled
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings:
            mock_settings = Mock()
            mock_settings.history_enabled = False
            mock_get_settings.return_value = mock_settings
            
            result = get_database_info()
            expected = {
                "enabled": False,
                "database_url": None,
                "database_name": None,
                "retention_days": None,
                "connection_test": False
            }
            assert result == expected
        
        # Test connection failure
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.test_database_connection') as mock_test_connection:
            
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = "sqlite:///history.db"
            mock_settings.history_retention_days = 90
            mock_get_settings.return_value = mock_settings
            mock_test_connection.return_value = False
            
            result = get_database_info()
            expected = {
                "enabled": True,
                "database_url": "sqlite:///history.db", 
                "database_name": "history.db",
                "retention_days": 90,
                "connection_test": False
            }
            assert result == expected
        
        # Test exception
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_get_settings.side_effect = Exception("Settings error")
            result = get_database_info()
            expected = {
                "enabled": False,
                "error": "Settings error"
            }
            assert result == expected


@pytest.mark.unit
class TestDatabaseInitIntegration:
    """Test integration scenarios for database initialization."""
    
    def test_full_initialization_flow_success(self):
        """Test the full database initialization flow."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.SQLModel') as mock_sqlmodel, \
             patch('tarsy.database.init_db.Session') as mock_session, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            # Mock settings
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = "sqlite:///test_history.db"
            mock_settings.history_retention_days = 60
            mock_get_settings.return_value = mock_settings
            
            # Mock successful database creation
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            mock_session_instance = Mock()
            mock_session.return_value.__enter__.return_value = mock_session_instance
            mock_session_instance.exec.return_value.first.return_value = 1
            mock_metadata = Mock()
            mock_sqlmodel.metadata = mock_metadata
            
            result = initialize_database()
            
            assert result is True
            # Verify the complete flow was executed
            mock_get_settings.assert_called_once()
            mock_create_engine.assert_called_once_with("sqlite:///test_history.db", echo=False)
            mock_metadata.create_all.assert_called_once_with(mock_engine)
            mock_session.assert_called_once_with(mock_engine)
            
            # Verify success logging
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("initialization completed successfully" in call for call in info_calls)
            assert any("Database: test_history.db" in call for call in info_calls)
            assert any("Retention policy: 60 days" in call for call in info_calls)
    

