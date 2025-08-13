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
             patch('tarsy.database.init_db.Session') as mock_session, \
             patch('tarsy.database.init_db.logger') as mock_logger, \
             patch('tarsy.database.init_db.text') as mock_text:
            
            # Mock engine and session
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            mock_session_instance = Mock()
            mock_session.return_value.__enter__.return_value = mock_session_instance
            mock_exec_result = Mock()
            mock_session_instance.exec.return_value = mock_exec_result
            mock_exec_result.first.return_value = 1
            
            # Mock SQLModel metadata
            mock_metadata = Mock()
            mock_sqlmodel.metadata = mock_metadata
            
            # Mock text() function
            mock_select_query = Mock()
            mock_text.return_value = mock_select_query
            
            result = create_database_tables("sqlite:///test.db")
            
            assert result is True
            mock_create_engine.assert_called_once_with("sqlite:///test.db", echo=False)
            mock_metadata.create_all.assert_called_once_with(mock_engine)
            mock_session.assert_called_once_with(mock_engine)
            
            # Assert connection test was performed
            mock_text.assert_called_once_with("SELECT 1")
            mock_session_instance.exec.assert_called_once_with(mock_select_query)
            mock_exec_result.first.assert_called_once()
            
            # Assert success logging was called
            mock_logger.info.assert_called_once_with("Database tables created successfully for: test.db")
    
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
            call_args_list = mock_logger.info.call_args_list
            assert any(call.args and "initialization completed successfully" in call.args[0] for call in call_args_list)
            assert any(call.args and "Database: test_history.db" in call.args[0] for call in call_args_list)
            assert any(call.args and "Retention policy: 60 days" in call.args[0] for call in call_args_list)
