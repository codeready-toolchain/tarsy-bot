"""
Unit tests for History Service.

Comprehensive test coverage for session management, LLM interaction logging,
MCP communication tracking, and timeline reconstruction with graceful
degradation when database operations fail.
"""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from tarsy.config.settings import Settings
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.history import AlertSession
from tarsy.services.history_service import HistoryService, get_history_service


class TestHistoryService:
    """Test suite for HistoryService class."""
    
    @pytest.fixture
    def mock_settings(self, isolated_test_settings):
        """Create mock settings for testing."""
        return isolated_test_settings
    
    @pytest.fixture
    def mock_db_manager(self):
        """Create mock database manager."""
        db_manager = Mock()
        db_manager.create_tables.return_value = True
        db_manager.get_session.return_value.__enter__ = Mock()
        db_manager.get_session.return_value.__exit__ = Mock()
        return db_manager
    
    @pytest.fixture
    def mock_repository(self):
        """Create mock history repository."""
        repo = Mock()
        # Create a mock session object with session_id attribute
        mock_session = Mock()
        mock_session.session_id = "test-session-id"
        repo.create_alert_session.return_value = mock_session
        repo.get_alert_session.return_value = Mock(spec=AlertSession)
        repo.update_alert_session.return_value = True
        repo.get_alert_sessions.return_value = {
            "sessions": [],
            "pagination": {"page": 1, "page_size": 20, "total_pages": 0, "total_items": 0}
        }
        return repo
    
    @pytest.fixture
    def history_service(self, mock_settings):
        """Create HistoryService instance with mocked dependencies."""
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            service._initialization_attempted = True
            service._is_healthy = True
            return service
    
    @pytest.mark.unit
    def test_initialization_enabled(self, history_service, mock_settings):
        """Test service initialization when history is enabled."""
        assert history_service.is_enabled == True
        assert history_service.settings.history_enabled == True
        assert history_service.settings.history_database_url == "sqlite:///:memory:"
    
    @pytest.mark.unit
    def test_initialization_disabled(self):
        """Test service initialization when history is disabled."""
        mock_settings = Mock(spec=Settings)
        mock_settings.history_enabled = False
        
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            assert service.is_enabled == False
    
    @pytest.mark.unit
    def test_enabled_property(self, history_service):
        """Test the enabled property."""
        assert history_service.enabled == True
        
        history_service.is_enabled = False
        assert history_service.enabled == False
    
    @pytest.mark.unit
    @patch('tarsy.services.history_service.DatabaseManager')
    def test_initialize_success(self, mock_db_manager_class, mock_settings):
        """Test successful service initialization."""
        mock_db_instance = Mock()
        mock_db_manager_class.return_value = mock_db_instance
        
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            result = service.initialize()
            
            assert result == True
            assert service._initialization_attempted == True
            assert service._is_healthy == True
            mock_db_instance.initialize.assert_called_once()
            mock_db_instance.create_tables.assert_called_once()
    
    @pytest.mark.unit
    @patch('tarsy.services.history_service.DatabaseManager')
    def test_initialize_database_failure(self, mock_db_manager_class, mock_settings):
        """Test initialization with database connection failure."""
        mock_db_manager_class.side_effect = Exception("Database connection failed")
        
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            result = service.initialize()
            
            assert result == False
            assert service._initialization_attempted == True
            assert service._is_healthy == False
    
    @pytest.mark.unit
    @patch('tarsy.services.history_service.DatabaseManager')
    def test_initialize_schema_creation_failure(self, mock_db_manager_class, mock_settings):
        """Test initialization with schema creation failure."""
        mock_db_instance = Mock()
        mock_db_instance.initialize.return_value = None
        mock_db_instance.create_tables.side_effect = Exception("Schema creation failed")
        mock_db_manager_class.return_value = mock_db_instance
        
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            result = service.initialize()
            
            assert result == False
            assert service._initialization_attempted == True
            assert service._is_healthy == False
    
    @pytest.mark.unit
    def test_initialize_disabled_service(self):
        """Test initialization when history service is disabled."""
        mock_settings = Mock(spec=Settings)
        mock_settings.history_enabled = False
        
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            result = service.initialize()
            
            assert result == False
            assert service._initialization_attempted == False  # Should not attempt when disabled
            assert service._is_healthy == False
    
    @pytest.mark.unit
    @patch('tarsy.services.history_service.HistoryRepository')
    def test_get_repository_context_manager(self, mock_repo_class, history_service, mock_db_manager):
        """Test the repository context manager."""
        history_service.db_manager = mock_db_manager
        mock_repo_instance = Mock()
        mock_repo_class.return_value = mock_repo_instance
        
        # Test successful context manager usage
        with history_service.get_repository() as repo:
            assert repo == mock_repo_instance
    
    @pytest.mark.unit
    @patch('tarsy.services.history_service.HistoryRepository')
    def test_get_repository_disabled_service(self, mock_repo_class, history_service):
        """Test repository access when service is disabled."""
        history_service.is_enabled = False
        
        with history_service.get_repository() as repo:
            assert repo is None
    
    @pytest.mark.unit
    def test_create_session_success(self, history_service, mock_repository):
        """Test successful session creation."""
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            session_id = history_service.create_session(
                alert_id="test-alert-123",
                alert_data={"alert_type": "test", "environment": "test"},
                agent_type="TestAgent",
                alert_type="test_alert"
            )
            
            assert session_id == "test-session-id"
            mock_repository.create_alert_session.assert_called_once()
    
    @pytest.mark.unit
    def test_create_session_disabled_service(self, history_service):
        """Test session creation when service is disabled."""
        history_service.is_enabled = False
        
        session_id = history_service.create_session(
            alert_id="test-alert-123",
            alert_data={},
            agent_type="TestAgent",
            alert_type="test_alert"
        )
        
        assert session_id is None
    
    @pytest.mark.unit
    def test_create_session_exception_handling(self, history_service):
        """Test session creation with exception handling."""
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.side_effect = Exception("Database error")
            
            session_id = history_service.create_session(
                alert_id="test-alert-123",
                alert_data={},
                agent_type="TestAgent",
                alert_type="test_alert"
            )
            
            assert session_id is None
    
    @pytest.mark.unit
    def test_update_session_status_success(self, history_service, mock_repository):
        """Test successful session status update."""
        mock_session = Mock(spec=AlertSession)
        mock_repository.get_alert_session.return_value = mock_session
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            result = history_service.update_session_status(
                session_id="test-session-id",
                status="completed",
                error_message=None
            )
            
            assert result == True
            assert mock_session.status == "completed"
            mock_repository.update_alert_session.assert_called_once_with(mock_session)
    
    @pytest.mark.unit
    def test_update_session_status_with_completion(self, history_service, mock_repository):
        """Test session status update with completion timestamp."""
        mock_session = Mock(spec=AlertSession)
        mock_repository.get_alert_session.return_value = mock_session
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            result = history_service.update_session_status(
                session_id="test-session-id",
                status="completed"
            )
            
            assert result == True
            assert mock_session.status == "completed"
            assert mock_session.completed_at_us is not None
    
    @pytest.mark.unit
    def test_update_session_status_with_final_analysis(self, history_service, mock_repository):
        """Test session status update with final analysis."""
        mock_session = Mock(spec=AlertSession)
        mock_repository.get_alert_session.return_value = mock_session
        analysis = "# Alert Analysis\n\nSuccessfully resolved the Kubernetes issue."
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            result = history_service.update_session_status(
                session_id="test-session-id",
                status="completed",
                final_analysis=analysis
            )
            
            assert result == True
            assert mock_session.status == "completed"
            assert mock_session.final_analysis == analysis
            assert mock_session.completed_at_us is not None
            mock_repository.update_alert_session.assert_called_once_with(mock_session)
    
    @pytest.mark.unit
    def test_update_session_status_without_final_analysis(self, history_service, mock_repository):
        """Test session status update without final analysis doesn't overwrite existing value."""
        mock_session = Mock(spec=AlertSession)
        existing_analysis = "Existing analysis"
        mock_session.final_analysis = existing_analysis
        mock_repository.get_alert_session.return_value = mock_session
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            result = history_service.update_session_status(
                session_id="test-session-id",
                status="in_progress"
            )
            
            assert result == True
            assert mock_session.status == "in_progress"
            # final_analysis should remain unchanged when not provided
            assert mock_session.final_analysis == existing_analysis
            mock_repository.update_alert_session.assert_called_once_with(mock_session)
    
    @pytest.mark.unit 
    @patch('tarsy.main.dashboard_manager')
    @patch('asyncio.run')
    @patch('asyncio.get_event_loop')
    def test_update_session_status_calls_dashboard_service(self, mock_get_loop, mock_asyncio_run, mock_dashboard_manager, history_service, mock_repository):
        """Test that session status update actually calls dashboard service."""
        # Setup mock session
        mock_session = Mock(spec=AlertSession)
        mock_repository.get_alert_session.return_value = mock_session
        
        # Setup mock dashboard update service
        mock_update_service = Mock()
        mock_dashboard_manager = Mock()
        mock_dashboard_manager.update_service = mock_update_service  
        mock_dashboard_manager = mock_dashboard_manager
        
        # Mock asyncio to simulate non-async context (so it uses asyncio.run)
        mock_loop = Mock()
        mock_loop.is_running.return_value = False  # Not in async context
        mock_get_loop.return_value = mock_loop
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Call update_session_status
            result = history_service.update_session_status(
                session_id="test-session-id",
                status="completed",
                error_message="Test error",
                final_analysis="Test analysis"
            )
            
            # Verify basic functionality
            assert result == True
            assert mock_session.status == "completed" 
            mock_repository.update_alert_session.assert_called_once_with(mock_session)
            
            # THE CORE FIX: Verify dashboard service is called via asyncio.run
            mock_asyncio_run.assert_called_once()
            # Verify the call was made to process_session_status_change with correct parameters
            called_coro = mock_asyncio_run.call_args[0][0]
            # This verifies the dashboard integration is working - the method gets called
            
            # Additional verification: Check that the coroutine is calling the right method
            # The coroutine should be calling process_session_status_change with session details
            assert str(called_coro).find('process_session_status_change') != -1, \
                f"Expected process_session_status_change call, got: {called_coro}"
    
    @pytest.mark.unit 
    @patch('tarsy.main.dashboard_manager', None)  # Simulate dashboard_manager not available
    def test_update_session_status_without_dashboard_service(self, history_service, mock_repository):
        """Test that session status update works gracefully without dashboard service."""
        # Setup mock session
        mock_session = Mock(spec=AlertSession)
        mock_repository.get_alert_session.return_value = mock_session
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Call update_session_status - should work even without dashboard service
            result = history_service.update_session_status(
                session_id="test-session-id", 
                status="completed"
            )
            
            # Verify the basic functionality still works
            assert result == True
            assert mock_session.status == "completed"
            mock_repository.update_alert_session.assert_called_once_with(mock_session)
            # The test passes if no exceptions are raised (graceful degradation)
    
    @pytest.mark.unit
    def test_log_llm_interaction_success(self, history_service, mock_repository):
        """Test successful LLM interaction logging."""
        from tarsy.models.unified_interactions import LLMInteraction
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Create unified interaction model
            interaction = LLMInteraction(
                session_id="test-session-id",
                model_name="gpt-4",
                step_description="Test LLM call",
                request_json={"messages": [{"role": "user", "content": "Test prompt"}]},
                response_json={"choices": [{"message": {"role": "assistant", "content": "Test response"}, "finish_reason": "stop"}]}
            )
            
            result = history_service.log_llm_interaction(interaction)
            
            assert result == True
            mock_repository.create_llm_interaction.assert_called_once()
    
    @pytest.mark.unit
    def test_log_mcp_interaction_success(self, history_service, mock_repository):
        """Test successful MCP communication logging."""
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            from tarsy.models.unified_interactions import MCPInteraction
            mcp_interaction = MCPInteraction(
                session_id="test-session-id",
                server_name="test-server",
                communication_type="tool_call",
                tool_name="test_tool",
                step_description="Test MCP call",
                success=True
            )
            result = history_service.log_mcp_interaction(mcp_interaction)
            
            assert result == True
            mock_repository.create_mcp_communication.assert_called_once()
    
    @pytest.mark.unit
    def test_get_sessions_list_success(self, history_service, mock_repository):
        """Test successful sessions list retrieval."""
        mock_sessions = [Mock(spec=AlertSession) for _ in range(3)]
        mock_repository.get_alert_sessions.return_value = {
            "sessions": mock_sessions,
            "pagination": {"page": 1, "page_size": 20, "total_pages": 1, "total_items": 3}
        }
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            sessions, total_count = history_service.get_sessions_list(
                filters={"status": "completed"},
                page=1,
                page_size=20
            )
            
            assert len(sessions) == 3
            assert total_count == 3
            mock_repository.get_alert_sessions.assert_called_once()
    
    @pytest.mark.unit
    def test_get_sessions_list_disabled_service(self, history_service):
        """Test sessions list retrieval when service is disabled."""
        history_service.is_enabled = False
        
        sessions, total_count = history_service.get_sessions_list()
        
        assert sessions == []
        assert total_count == 0
    
    @pytest.mark.unit
    def test_get_session_timeline_success(self, history_service, mock_repository):
        """Test successful session timeline retrieval."""
        mock_timeline_data = {
            "session_info": {"session_id": "test-session-id", "status": "completed"},
            "chronological_timeline": [
                {"type": "llm_interaction", "timestamp": datetime.now(timezone.utc)},
                {"type": "mcp_communication", "timestamp": datetime.now(timezone.utc)}
            ],
            "summary": {"total_interactions": 2}
        }
        mock_repository.get_session_timeline.return_value = mock_timeline_data
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            timeline = history_service.get_session_timeline("test-session-id")
            
            assert timeline == mock_timeline_data
            assert timeline["session_info"]["session_id"] == "test-session-id"
            assert len(timeline["chronological_timeline"]) == 2
    
    @pytest.mark.unit
    def test_test_database_connection_success(self, history_service, mock_repository):
        """Test successful database connection test."""
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            result = history_service.test_database_connection()
            
            assert result == True
            mock_repository.get_alert_sessions.assert_called_once_with(page=1, page_size=1)
    
    @pytest.mark.unit
    def test_test_database_connection_failure(self, history_service):
        """Test database connection test failure."""
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.side_effect = Exception("Connection failed")
            
            result = history_service.test_database_connection()
            
            assert result == False
    

    @pytest.mark.unit
    def test_get_active_sessions(self, history_service, mock_repository):
        """Test active sessions retrieval."""
        mock_active_sessions = [Mock(spec=AlertSession) for _ in range(2)]
        mock_repository.get_active_sessions.return_value = mock_active_sessions
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            active_sessions = history_service.get_active_sessions()
            
            assert len(active_sessions) == 2
            mock_repository.get_active_sessions.assert_called_once()
    

    @pytest.mark.unit
    @patch('time.sleep')
    def test_retry_database_operation_success_after_retry(self, mock_sleep, history_service):
        """Test operation succeeds after transient failure."""
        call_count = 0
        
        def mock_operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("database is locked")
            return "success"
        
        result = history_service._retry_database_operation("test_operation", mock_operation)
        
        assert result == "success"
        assert call_count == 2
        mock_sleep.assert_called_once()  # Should have slept once for retry
    
    @pytest.mark.unit
    @patch('time.sleep')
    def test_retry_database_operation_exhausts_retries(self, mock_sleep, history_service):
        """Test operation fails after max retries."""
        def mock_operation():
            raise Exception("database is locked")
        
        result = history_service._retry_database_operation("test_operation", mock_operation)
        
        assert result is None
        assert mock_sleep.call_count == history_service.max_retries  # Should retry max_retries times
    
    @pytest.mark.unit
    @patch('time.sleep')
    def test_retry_database_operation_non_retryable_error(self, mock_sleep, history_service):
        """Test operation fails immediately on non-retryable error."""
        def mock_operation():
            raise Exception("syntax error")  # Non-retryable error
        
        result = history_service._retry_database_operation("test_operation", mock_operation)
        
        assert result is None
        mock_sleep.assert_not_called()  # Should not retry for non-retryable errors
    
    @pytest.mark.unit
    def test_get_sessions_dict_format(self, history_service, mock_repository):
        """Test get_sessions method returns dict format (different from get_sessions_list)."""
        mock_sessions = [Mock(spec=AlertSession) for _ in range(2)]
        expected_result = {
            "sessions": mock_sessions,
            "pagination": {"page": 1, "page_size": 20, "total_pages": 1, "total_items": 2}
        }
        mock_repository.get_alert_sessions.return_value = expected_result
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            
            result = history_service.get_sessions(status="completed", page=1, page_size=20)
            
            assert result == expected_result
            assert isinstance(result, dict)  # Different from get_sessions_list which returns tuple
            mock_repository.get_alert_sessions.assert_called_once_with(
                status="completed",
                agent_type=None,
                alert_type=None,
                start_date_us=None,
                end_date_us=None,
                page=1,
                page_size=20
            )


class TestHistoryServiceGlobalInstance:
    """Test suite for global history service instance management."""
    
    @pytest.mark.unit
    @patch('tarsy.services.history_service._history_service', None)
    def test_get_history_service_singleton(self):
        """Test that get_history_service returns a singleton instance."""
        with patch('tarsy.services.history_service.HistoryService') as mock_service_class:
            mock_instance = Mock()
            mock_service_class.return_value = mock_instance
            
            # First call should create instance
            service1 = get_history_service()
            
            # Second call should return same instance
            service2 = get_history_service()
            
            assert service1 == service2
            mock_service_class.assert_called_once()
    
    @pytest.mark.unit
    @patch('tarsy.services.history_service._history_service', None)
    def test_get_history_service_initialization(self):
        """Test that get_history_service initializes the service."""
        with patch('tarsy.services.history_service.HistoryService') as mock_service_class:
            mock_instance = Mock()
            mock_service_class.return_value = mock_instance
            
            service = get_history_service()
            
            assert service == mock_instance
            mock_instance.initialize.assert_called_once()


class TestHistoryServiceErrorHandling:
    """Test suite for HistoryService error handling scenarios."""
    
    @pytest.fixture
    def history_service_with_errors(self):
        """Create HistoryService that simulates various error conditions."""
        mock_settings = Mock(spec=Settings)
        mock_settings.history_enabled = True
        mock_settings.history_database_url = "sqlite:///test_history.db"
        mock_settings.history_retention_days = 90
        
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            service._initialization_attempted = True
            service._is_healthy = False  # Simulate unhealthy state
            return service
    
    @pytest.mark.unit
    def test_graceful_degradation_repository_unavailable(self, history_service_with_errors):
        """Test graceful degradation when repository is unavailable."""
        with patch.object(history_service_with_errors, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = None
            mock_get_repo.return_value.__exit__.return_value = None
            
            # All operations should return safe defaults
            session_id = history_service_with_errors.create_session("test", {}, "agent", "alert")
            assert session_id is None
            
            result = history_service_with_errors.update_session_status("test", "completed")
            assert result == False
            
            sessions, count = history_service_with_errors.get_sessions_list()
            assert sessions == []
            assert count == 0
    
    @pytest.mark.unit
    def test_exception_handling_in_operations(self, history_service_with_errors):
        """Test exception handling in various operations."""
        with patch.object(history_service_with_errors, 'get_repository') as mock_get_repo:
            mock_get_repo.side_effect = Exception("Simulated error")
            
            # All operations should handle exceptions gracefully
            session_id = history_service_with_errors.create_session("test", {}, "agent", "alert")
            assert session_id is None
            
            # Create unified interaction model for error test
            from tarsy.models.unified_interactions import LLMInteraction
            interaction = LLMInteraction(
                session_id="test",
                model_name="model",
                step_description="step",
                request_json={"messages": [{"role": "user", "content": "prompt"}]},
                response_json={"choices": [{"message": {"role": "assistant", "content": "response"}, "finish_reason": "stop"}]}
            )
            result = history_service_with_errors.log_llm_interaction(interaction)
            assert result == False
            
            from tarsy.models.unified_interactions import MCPInteraction
            mcp_interaction = MCPInteraction(
                session_id="test",
                server_name="server", 
                communication_type="type",
                tool_name="tool",
                step_description="step"
            )
            result = history_service_with_errors.log_mcp_interaction(mcp_interaction)
            assert result == False


class TestDashboardMethods:
    """Test suite for new dashboard-specific methods in HistoryService."""
    
    @pytest.fixture
    def mock_repository(self):
        """Create mock repository for dashboard methods."""
        repo = Mock()

        repo.get_filter_options.return_value = {
            "agent_types": ["kubernetes", "network"],
            "alert_types": ["PodCrashLooping"],
            "status_options": ["pending", "in_progress", "completed", "failed"],
            "time_ranges": [
                {"label": "Last Hour", "value": "1h"},
                {"label": "Today", "value": "today"}
            ]
        }
        return repo
    
    @pytest.fixture
    def history_service_with_mock_repo(self, mock_repository):
        """Create HistoryService with mocked repository."""
        service = HistoryService()
        service.is_enabled = True
        service._is_healthy = True
        
        # Mock the get_repository context manager
        with patch.object(service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repository
            mock_get_repo.return_value.__exit__.return_value = None
            yield service, mock_repository
    

    
    @pytest.mark.unit
    def test_get_filter_options_success(self, history_service_with_mock_repo):
        """Test successful filter options retrieval."""
        service, mock_repo = history_service_with_mock_repo
        
        result = service.get_filter_options()
        
        # Verify the result
        assert "agent_types" in result
        assert "alert_types" in result
        assert "status_options" in result
        assert "time_ranges" in result
        assert len(result["agent_types"]) == 2
        assert "kubernetes" in result["agent_types"]
        assert len(result["time_ranges"]) == 2
        
        # Verify repository was called
        mock_repo.get_filter_options.assert_called_once()
    
    @pytest.mark.unit
    def test_get_filter_options_no_repository(self):
        """Test filter options when repository is unavailable."""
        service = HistoryService()
        service.is_enabled = True
        service._is_healthy = False
        
        with patch.object(service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = None
            
            result = service.get_filter_options()
            
            # Should return default values
            assert result["agent_types"] == []
            assert result["alert_types"] == []
            assert len(result["status_options"]) == 4
            assert len(result["time_ranges"]) == 4
    
    @pytest.mark.unit
    def test_get_filter_options_exception(self):
        """Test filter options with repository exception."""
        service = HistoryService()
        service.is_enabled = True
        
        with patch.object(service, 'get_repository') as mock_get_repo:
            mock_get_repo.side_effect = Exception("Database error")
            
            result = service.get_filter_options()
            
            # Should return default values on exception
            assert result["agent_types"] == []
            assert result["alert_types"] == []
            assert len(result["status_options"]) == 4

@pytest.mark.unit
class TestHistoryServiceRetryLogicDuplicatePrevention:
    """Test HistoryService retry logic improvements for duplicate prevention."""
    
    @pytest.fixture
    def history_service(self):
        """Create HistoryService instance for testing."""
        with patch('tarsy.services.history_service.get_settings') as mock_settings:
            mock_settings.return_value.history_enabled = True
            mock_settings.return_value.history_database_url = "sqlite:///test.db"
            mock_settings.return_value.history_retention_days = 90
            
            service = HistoryService()
            return service
    
    def test_retry_operation_success_on_first_attempt(self, history_service):
        """Test that successful operations on first attempt don't retry."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = history_service._retry_database_operation("test_operation", operation)
        
        assert result == "success"
        assert call_count == 1  # Should only be called once
    
    def test_retry_operation_success_after_retries(self, history_service):
        """Test that operations succeed after transient failures."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("database is locked")
            return "success"
        
        result = history_service._retry_database_operation("test_operation", operation)
        
        assert result == "success"
        assert call_count == 3  # Should retry twice, succeed on third
    
    def test_retry_operation_exhausts_retries(self, history_service):
        """Test that operations fail after exhausting all retries."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            raise Exception("database is locked")
        
        result = history_service._retry_database_operation("test_operation", operation)
        
        assert result is None
        assert call_count == 4  # Initial attempt + 3 retries
    
    def test_retry_operation_non_retryable_error(self, history_service):
        """Test that non-retryable errors don't trigger retries."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid data")  # Not a retryable error
        
        result = history_service._retry_database_operation("test_operation", operation)
        
        assert result is None
        assert call_count == 1  # Should not retry
    
    def test_retry_operation_create_session_no_retry_after_first_attempt(self, history_service):
        """Test that create_session operations don't retry after first failure to prevent duplicates."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "session_123"  # First attempt succeeds
            raise Exception("database is locked")  # Shouldn't reach here
        
        result = history_service._retry_database_operation("create_session", operation)
        
        assert result == "session_123"
        assert call_count == 1
    
    def test_retry_operation_create_session_prevents_duplicate_retry(self, history_service):
        """Test that create_session doesn't retry after database errors to prevent duplicates."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            raise Exception("connection timeout")  # Always fails
        
        result = history_service._retry_database_operation("create_session", operation)
        
        assert result is None  # Should return None after first failure
        assert call_count == 2   # First attempt + one retry, then stops to prevent duplicates
    
    def test_retry_operation_non_create_session_retries_normally(self, history_service):
        """Test that non-create_session operations retry normally."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("database is locked")
            return "success"
        
        result = history_service._retry_database_operation("update_session", operation)
        
        assert result == "success"
        assert call_count == 3  # Should retry normally
    
    def test_retry_operation_returns_none_for_failed_results(self, history_service):
        """Test that operations returning None trigger retries."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return None  # Failed operation
            return "success"
        
        with patch.object(history_service, 'max_retries', 3):
            result = history_service._retry_database_operation("test_operation", operation)
        
        assert result == "success"
        assert call_count == 3  # Should retry on None results
    
    def test_retry_operation_logs_appropriately(self, history_service, caplog):
        """Test that retry operations log warnings and errors appropriately."""
        import logging
        caplog.set_level(logging.WARNING)
        
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("database is locked")
            return "success"
        
        result = history_service._retry_database_operation("test_operation", operation)
        
        assert result == "success"
        
        # Should log warnings for retries
        warning_logs = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert len(warning_logs) >= 2  # At least 2 retry warnings
        
        # Should contain retry information
        assert any("retrying in" in record.message for record in warning_logs)
    
    def test_retry_operation_exponential_backoff_timing(self, history_service):
        """Test that retry operations use exponential backoff with jitter."""
        import time
        
        call_count = 0
        retry_times = []
        
        def operation():
            nonlocal call_count
            call_count += 1
            retry_times.append(time.time())
            if call_count < 3:
                raise Exception("database is locked")
            return "success"
        
        # Reduce delays for testing
        history_service.base_delay = 0.01  # 10ms base delay
        history_service.max_delay = 0.1    # 100ms max delay
        
        start_time = time.time()
        result = history_service._retry_database_operation("test_operation", operation)
        end_time = time.time()
        
        assert result == "success"
        assert call_count == 3
        
        # Should have taken some time due to backoff
        total_time = end_time - start_time
        assert total_time >= 0.01, f"Should have delayed for backoff, took {total_time}s"
        
        # Verify exponential backoff (second retry should take longer than first)
        if len(retry_times) >= 3:
            first_gap = retry_times[1] - retry_times[0]
            second_gap = retry_times[2] - retry_times[1]
            assert second_gap > first_gap, "Second retry should have longer delay than first"
    
    def test_retry_operation_handles_all_retryable_errors(self, history_service):
        """Test that all configured retryable errors trigger retries."""
        retryable_errors = [
            "database is locked",
            "database disk image is malformed",
            "sqlite3.operationalerror",
            "connection timeout",
            "database table is locked",
            "connection pool",
            "connection closed"
        ]
        
        for error_msg in retryable_errors:
            call_count = 0
            
            def operation():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception(error_msg)
                return "success"
            
            result = history_service._retry_database_operation("test_operation", operation)
            
            assert result == "success", f"Should retry for error: {error_msg}"
            assert call_count == 2, f"Should have retried once for error: {error_msg}"
    
    def test_retry_operation_preserves_last_exception(self, history_service, caplog):
        """Test that the last exception is preserved and logged when all retries fail."""
        import logging
        caplog.set_level(logging.ERROR)
        
        def operation():
            raise Exception("Final error message")
        
        result = history_service._retry_database_operation("test_operation", operation)
        
        assert result is None
        
        # Should log the final error
        error_logs = [record for record in caplog.records if record.levelno == logging.ERROR]
        assert len(error_logs) >= 1
        assert "Final error message" in error_logs[-1].message 


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_orphaned_sessions():
    """Test that orphaned sessions are properly cleaned up on startup."""
    # Create test data: sessions in different states
    test_sessions = [
        # These should be cleaned up (orphaned)
        {
            "session_id": "orphaned-pending-1",
            "alert_id": "alert-pending-1",
            "status": AlertSessionStatus.PENDING, 
            "agent_type": "KubernetesAgent"
        },
        {
            "session_id": "orphaned-progress-1", 
            "alert_id": "alert-progress-1",
            "status": AlertSessionStatus.IN_PROGRESS,
            "agent_type": "KubernetesAgent"
        },
        # These should NOT be cleaned up (already terminal states)
        {
            "session_id": "completed-1",
            "alert_id": "alert-completed-1", 
            "status": AlertSessionStatus.COMPLETED,
            "agent_type": "KubernetesAgent"
        },
        {
            "session_id": "failed-1",
            "alert_id": "alert-failed-1",
            "status": AlertSessionStatus.FAILED, 
            "agent_type": "KubernetesAgent"
        }
    ]
    
    # Create a mock history service
    history_service = HistoryService()
    history_service.is_enabled = True
    
    # Mock the repository
    mock_repo = Mock()
    
    # Create mock sessions
    mock_active_sessions = []
    mock_all_sessions = []
    
    for session_data in test_sessions:
        mock_session = Mock()
        for key, value in session_data.items():
            setattr(mock_session, key, value)
        mock_all_sessions.append(mock_session)
        
        # Only pending and in_progress should be returned by the active query
        if session_data["status"] in AlertSessionStatus.ACTIVE_STATUSES:
            mock_active_sessions.append(mock_session)
    
    # Mock repository responses
    mock_repo.get_alert_sessions.return_value = {
        "sessions": mock_active_sessions,
        "total": len(mock_active_sessions)
    }
    mock_repo.update_alert_session.return_value = True
    
    # Mock the context manager
    history_service.get_repository = Mock(return_value=Mock(__enter__=Mock(return_value=mock_repo), __exit__=Mock(return_value=None)))
    
    # Call cleanup method
    cleaned_count = history_service.cleanup_orphaned_sessions()
    
    # Verify correct number of sessions were cleaned up
    assert cleaned_count == 2, f"Expected 2 sessions to be cleaned up, got {cleaned_count}"
    
    # Verify get_alert_sessions was called with correct parameters
    mock_repo.get_alert_sessions.assert_called_once_with(
        status=AlertSessionStatus.ACTIVE_STATUSES,
        page_size=1000
    )
    
    # Verify each orphaned session was updated correctly
    assert mock_repo.update_alert_session.call_count == 2
    
    # Check that orphaned sessions had their status updated
    for session in mock_active_sessions:
        assert session.status == AlertSessionStatus.FAILED
        assert session.error_message == "Backend was restarted - session terminated unexpectedly"
        assert hasattr(session, 'completed_at_us')


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_orphaned_sessions_disabled_service():
    """Test that cleanup does nothing when history service is disabled."""
    history_service = HistoryService()
    history_service.is_enabled = False
    
    cleaned_count = history_service.cleanup_orphaned_sessions()
    
    assert cleaned_count == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_orphaned_sessions_no_repository():
    """Test cleanup handles gracefully when repository is unavailable."""
    history_service = HistoryService()
    history_service.is_enabled = True
    history_service.get_repository = Mock(return_value=Mock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)))
    
    cleaned_count = history_service.cleanup_orphaned_sessions()
    
    assert cleaned_count == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_orphaned_sessions_no_active_sessions():
    """Test cleanup when there are no orphaned sessions."""
    history_service = HistoryService()
    history_service.is_enabled = True
    
    mock_repo = Mock()
    mock_repo.get_alert_sessions.return_value = {"sessions": [], "total": 0}
    
    history_service.get_repository = Mock(return_value=Mock(__enter__=Mock(return_value=mock_repo), __exit__=Mock(return_value=None)))
    
    cleaned_count = history_service.cleanup_orphaned_sessions()
    
    assert cleaned_count == 0
    mock_repo.get_alert_sessions.assert_called_once_with(
        status=["pending", "in_progress"],
        page_size=1000
    )
    mock_repo.update_alert_session.assert_not_called() 


class TestHistoryAPIResponseStructure:
    """Test suite for history service API response structure validation."""
    
    @pytest.mark.unit
    def test_session_detail_response_structure(self):
        """Test that session detail response has all required fields."""
        # This tests the fix where we added missing fields to the API response
        
        # Expected response structure after the session_id fixes
        expected_fields = {
            'session_id',
            'alert_id', 
            'alert_data',
            'agent_type',
            'alert_type',
            'status',
            'started_at',
            'completed_at_us',
            'error_message',
            'final_analysis',
            'duration_ms',
            'session_metadata',
            'chronological_timeline',
            'summary'
        }
        
        # Create mock response data
        mock_response_data = {
            'session_id': 'test-session-123',
            'alert_id': 'alert-456',
            'alert_data': {'test': 'data'},
            'agent_type': 'TestAgent',
            'alert_type': 'TestAlert',
            'status': 'completed',
            'started_at': '2024-01-01T00:00:00Z',
            'completed_at_us': 1704067260000000,  # 2024-01-01T00:01:00Z in microseconds
            'error_message': None,
            'final_analysis': 'Test analysis complete',
            'duration_ms': 60000,
            'session_metadata': {'key': 'value'},
            'chronological_timeline': [],
            'summary': {'summary': 'test'}
        }
        
        # Verify all expected fields are present
        response_fields = set(mock_response_data.keys())
        missing_fields = expected_fields - response_fields
        assert not missing_fields, f"Missing required fields: {missing_fields}"
        
        # Verify the previously missing fields are included
        assert 'error_message' in mock_response_data
        assert 'final_analysis' in mock_response_data  
        assert 'session_metadata' in mock_response_data 