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
    
    def test_create_database_tables_operational_error(self):
        """Test database table creation with operational error."""
        with patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_create_engine.side_effect = OperationalError("Connection failed", None, None)
            
            result = create_database_tables("sqlite:///test.db")
            
            assert result is False
            mock_logger.error.assert_called_once()
            assert "Database operational error" in mock_logger.error.call_args[0][0]
    
    def test_create_database_tables_sqlalchemy_error(self):
        """Test database table creation with SQLAlchemy error."""
        with patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.SQLModel') as mock_sqlmodel, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            mock_sqlmodel.metadata.create_all.side_effect = SQLAlchemyError("Schema error")
            
            result = create_database_tables("sqlite:///test.db")
            
            assert result is False
            mock_logger.error.assert_called_once()
            assert "SQLAlchemy error" in mock_logger.error.call_args[0][0]
    
    def test_create_database_tables_unexpected_error(self):
        """Test database table creation with unexpected error."""
        with patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_create_engine.side_effect = Exception("Unexpected error")
            
            result = create_database_tables("sqlite:///test.db")
            
            assert result is False
            mock_logger.error.assert_called_once()
            assert "Unexpected error" in mock_logger.error.call_args[0][0]
    
    def test_create_database_tables_session_test_failure(self):
        """Test database table creation when session test fails."""
        with patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.SQLModel') as mock_sqlmodel, \
             patch('tarsy.database.init_db.Session') as mock_session, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            # Mock engine and session
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            mock_session_instance = Mock()
            mock_session.return_value.__enter__.return_value = mock_session_instance
            mock_session_instance.exec.side_effect = OperationalError("Query failed", None, None)
            
            # Mock SQLModel metadata
            mock_metadata = Mock()
            mock_sqlmodel.metadata = mock_metadata
            
            result = create_database_tables("sqlite:///test.db")
            
            assert result is False
            mock_logger.error.assert_called_once()


@pytest.mark.unit
class TestInitializeDatabase:
    """Test initialize_database function."""
    
    def test_initialize_database_success(self):
        """Test successful database initialization."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.create_database_tables') as mock_create_tables, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            # Mock settings
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = "sqlite:///history.db"
            mock_settings.history_retention_days = 90
            mock_get_settings.return_value = mock_settings
            
            # Mock successful table creation
            mock_create_tables.return_value = True
            
            result = initialize_database()
            
            assert result is True
            mock_create_tables.assert_called_once_with("sqlite:///history.db")
            mock_logger.info.assert_called()
            assert any("initialization completed successfully" in str(call) for call in mock_logger.info.call_args_list)
    
    def test_initialize_database_disabled(self):
        """Test database initialization when history service is disabled."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            # Mock settings with history disabled
            mock_settings = Mock()
            mock_settings.history_enabled = False
            mock_get_settings.return_value = mock_settings
            
            result = initialize_database()
            
            assert result is True
            mock_logger.info.assert_called_once()
            assert "History service disabled" in mock_logger.info.call_args[0][0]
    
    def test_initialize_database_no_url_configured(self):
        """Test database initialization with missing database URL."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            # Mock settings with history enabled but no URL
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = None
            mock_get_settings.return_value = mock_settings
            
            result = initialize_database()
            
            assert result is False
            mock_logger.error.assert_called_once()
            assert "History database URL not configured" in mock_logger.error.call_args[0][0]
    
    def test_initialize_database_invalid_retention_days(self):
        """Test database initialization with invalid retention days."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.create_database_tables') as mock_create_tables, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            # Mock settings with invalid retention days
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = "sqlite:///history.db"
            mock_settings.history_retention_days = -10
            mock_get_settings.return_value = mock_settings
            
            # Mock successful table creation
            mock_create_tables.return_value = True
            
            result = initialize_database()
            
            assert result is True
            mock_logger.warning.assert_called_once()
            assert "Invalid retention days" in mock_logger.warning.call_args[0][0]
    
    def test_initialize_database_table_creation_failure(self):
        """Test database initialization when table creation fails."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.create_database_tables') as mock_create_tables, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            # Mock settings
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = "sqlite:///history.db"
            mock_settings.history_retention_days = 90
            mock_get_settings.return_value = mock_settings
            
            # Mock failed table creation
            mock_create_tables.return_value = False
            
            result = initialize_database()
            
            assert result is False
            mock_logger.error.assert_called_once()
            assert "initialization failed" in mock_logger.error.call_args[0][0]
    
    def test_initialize_database_exception(self):
        """Test database initialization with unexpected exception."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_get_settings.side_effect = Exception("Settings error")
            
            result = initialize_database()
            
            assert result is False
            mock_logger.error.assert_called_once()
            assert "Database initialization error" in mock_logger.error.call_args[0][0]


@pytest.mark.unit  
class TestDatabaseConnection:
    """Test test_database_connection function."""
    
    def test_database_connection_success_with_url(self):
        """Test successful database connection with provided URL."""
        with patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.Session') as mock_session:
            
            # Mock engine and session
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            mock_session_instance = Mock()
            mock_session.return_value.__enter__.return_value = mock_session_instance
            mock_session_instance.exec.return_value.first.return_value = [1]
            
            result = test_database_connection("sqlite:///test.db")
            
            assert result is True
            mock_create_engine.assert_called_once_with("sqlite:///test.db", echo=False)
    
    def test_database_connection_success_from_settings(self):
        """Test successful database connection using settings."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.Session') as mock_session:
            
            # Mock settings
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = "sqlite:///history.db"
            mock_get_settings.return_value = mock_settings
            
            # Mock engine and session
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            mock_session_instance = Mock()
            mock_session.return_value.__enter__.return_value = mock_session_instance
            mock_session_instance.exec.return_value.first.return_value = [1]
            
            result = test_database_connection()
            
            assert result is True
            mock_create_engine.assert_called_once_with("sqlite:///history.db", echo=False)
    
    def test_database_connection_history_disabled(self):
        """Test database connection when history service is disabled."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings:
            
            # Mock settings with history disabled
            mock_settings = Mock()
            mock_settings.history_enabled = False
            mock_get_settings.return_value = mock_settings
            
            result = test_database_connection()
            
            assert result is False
    
    def test_database_connection_failure(self):
        """Test database connection failure."""
        with patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_create_engine.side_effect = Exception("Connection failed")
            
            result = test_database_connection("sqlite:///test.db")
            
            assert result is False
            mock_logger.debug.assert_called_once()
            assert "Database connection test failed" in mock_logger.debug.call_args[0][0]
    
    def test_database_connection_query_failure(self):
        """Test database connection when query execution fails."""
        with patch('tarsy.database.init_db.create_engine') as mock_create_engine, \
             patch('tarsy.database.init_db.Session') as mock_session, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            # Mock engine and session with query failure
            mock_engine = Mock()
            mock_create_engine.return_value = mock_engine
            mock_session_instance = Mock()
            mock_session.return_value.__enter__.return_value = mock_session_instance
            mock_session_instance.exec.side_effect = Exception("Query failed")
            
            result = test_database_connection("sqlite:///test.db")
            
            assert result is False
            mock_logger.debug.assert_called_once()


@pytest.mark.unit
class TestGetDatabaseInfo:
    """Test get_database_info function."""
    
    def test_get_database_info_enabled(self):
        """Test getting database info when history is enabled."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.test_database_connection') as mock_test_connection:
            
            # Mock settings
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = "sqlite:///history.db"
            mock_settings.history_retention_days = 90
            mock_get_settings.return_value = mock_settings
            
            # Mock connection test success
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
            mock_test_connection.assert_called_once()
    
    def test_get_database_info_disabled(self):
        """Test getting database info when history is disabled."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings:
            
            # Mock settings with history disabled
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
    
    def test_get_database_info_connection_test_failure(self):
        """Test getting database info when connection test fails."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.test_database_connection') as mock_test_connection:
            
            # Mock settings
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = "sqlite:///history.db"
            mock_settings.history_retention_days = 90
            mock_get_settings.return_value = mock_settings
            
            # Mock connection test failure
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
    
    def test_get_database_info_exception(self):
        """Test getting database info when an exception occurs."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.logger') as mock_logger:
            
            mock_get_settings.side_effect = Exception("Settings error")
            
            result = get_database_info()
            
            expected = {
                "enabled": False,
                "error": "Settings error"
            }
            
            assert result == expected
            mock_logger.error.assert_called_once()
            assert "Failed to get database info" in mock_logger.error.call_args[0][0]
    
    def test_get_database_info_complex_url_parsing(self):
        """Test getting database info with complex database URL parsing."""
        with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
             patch('tarsy.database.init_db.test_database_connection') as mock_test_connection:
            
            # Mock settings with complex URL
            mock_settings = Mock()
            mock_settings.history_enabled = True
            mock_settings.history_database_url = "postgresql://user:pass@localhost:5432/tarsy_history"
            mock_settings.history_retention_days = 30
            mock_get_settings.return_value = mock_settings
            
            # Mock connection test
            mock_test_connection.return_value = True
            
            result = get_database_info()
            
            expected = {
                "enabled": True,
                "database_url": "postgresql://user:pass@localhost:5432/tarsy_history",
                "database_name": "tarsy_history",
                "retention_days": 30,
                "connection_test": True
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
    
    def test_initialization_with_edge_case_urls(self):
        """Test database initialization with various URL formats."""
        test_urls = [
            "sqlite:///memory:",
            "postgresql://localhost/db",
            "mysql://user:pass@host:3306/db?charset=utf8",
            "sqlite:////absolute/path/db.sqlite"
        ]
        
        for url in test_urls:
            with patch('tarsy.database.init_db.get_settings') as mock_get_settings, \
                 patch('tarsy.database.init_db.create_database_tables') as mock_create_tables:
                
                # Mock settings
                mock_settings = Mock()
                mock_settings.history_enabled = True
                mock_settings.history_database_url = url
                mock_settings.history_retention_days = 30
                mock_get_settings.return_value = mock_settings
                
                # Mock successful table creation
                mock_create_tables.return_value = True
                
                result = initialize_database()
                
                assert result is True
                mock_create_tables.assert_called_once_with(url)
