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
from tarsy.utils.timestamp import now_us
from tests.utils import MockFactory, TestUtils, SessionFactory


class TestHistoryService:
    """Test suite for HistoryService class."""
    
    @pytest.fixture
    def mock_settings(self, isolated_test_settings):
        """Create mock settings for testing."""
        return isolated_test_settings
    
    @pytest.fixture
    def history_service(self, mock_settings):
        """Create HistoryService instance with mocked dependencies."""
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            service._initialization_attempted = True
            service._is_healthy = True
            return service
    
    @pytest.mark.parametrize("history_enabled,expected_enabled,expected_url", [
        (True, True, "sqlite:///:memory:"),  # History enabled
        (False, False, None),  # History disabled
    ])
    @pytest.mark.unit
    def test_initialization_scenarios(self, history_enabled, expected_enabled, expected_url):
        """Test service initialization for various scenarios."""
        mock_settings = MockFactory.create_mock_settings(
            history_enabled=history_enabled,
            history_database_url=expected_url
        )
        
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            assert service.is_enabled == expected_enabled
            assert service.enabled == expected_enabled  # Test enabled property
            if history_enabled:
                assert service.settings.history_enabled == True
                assert service.settings.history_database_url == expected_url
    
    @pytest.mark.parametrize("failure_type,expected_result,expected_attempted,expected_healthy", [
        ("success", True, True, True),  # Successful initialization
        ("database_failure", False, True, False),  # Database connection failure
        ("schema_failure", False, True, False),  # Schema creation failure
        ("disabled", False, False, False),  # Service disabled
    ])
    @pytest.mark.unit
    @patch('tarsy.services.history_service.DatabaseManager')
    def test_initialize_scenarios(self, mock_db_manager_class, failure_type, expected_result, expected_attempted, expected_healthy):
        """Test service initialization for various failure scenarios."""
        # Create mock settings based on scenario
        mock_settings = MockFactory.create_mock_settings(
            history_enabled=failure_type != "disabled",
            history_database_url="sqlite:///test.db" if failure_type != "disabled" else None
        )
        
        # Set up database manager based on scenario
        if failure_type == "success":
            mock_db_instance = Mock()
            mock_db_manager_class.return_value = mock_db_instance
        elif failure_type == "database_failure":
            mock_db_manager_class.side_effect = Exception("Database connection failed")
        elif failure_type == "schema_failure":
            mock_db_instance = Mock()
            mock_db_instance.initialize.return_value = None
            mock_db_instance.create_tables.side_effect = Exception("Schema creation failed")
            mock_db_manager_class.return_value = mock_db_instance
        
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            result = service.initialize()
            
            assert result == expected_result
            assert service._initialization_attempted == expected_attempted
            assert service._is_healthy == expected_healthy
            
            if failure_type == "success":
                mock_db_instance.initialize.assert_called_once()
                mock_db_instance.create_tables.assert_called_once()
    
    @pytest.mark.parametrize("service_enabled,expected_repo", [
        (True, "mock_repo"),  # Service enabled
        (False, None),  # Service disabled
    ])
    @pytest.mark.unit
    @patch('tarsy.services.history_service.HistoryRepository')
    def test_get_repository_scenarios(self, mock_repo_class, history_service, service_enabled, expected_repo):
        """Test repository access for various scenarios."""
        dependencies = MockFactory.create_mock_history_service_dependencies()
        
        history_service.is_enabled = service_enabled
        if service_enabled:
            history_service.db_manager = dependencies['db_manager']
            mock_repo_class.return_value = dependencies['repository']
        
        with history_service.get_repository() as repo:
            if expected_repo == "mock_repo":
                assert repo == dependencies['repository']
            else:
                assert repo is None
    
    @pytest.mark.parametrize("scenario,service_enabled,repo_side_effect,expected_session_id", [
        ("success", True, None, "test-session-id"),  # Successful creation
        ("disabled", False, None, None),  # Service disabled
        ("exception", True, Exception("Database error"), None),  # Database error
    ])
    @pytest.mark.unit
    def test_create_session_scenarios(self, history_service, scenario, service_enabled, repo_side_effect, expected_session_id):
        """Test session creation for various scenarios."""
        dependencies = MockFactory.create_mock_history_service_dependencies()
        
        history_service.is_enabled = service_enabled
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            if repo_side_effect:
                mock_get_repo.side_effect = repo_side_effect
            else:
                mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
                mock_get_repo.return_value.__exit__.return_value = None
            
            session_id = history_service.create_session(
                alert_id="test-alert-123",
                alert_data={"alert_type": "test", "environment": "test"},
                agent_type="TestAgent",
                alert_type="test_alert"
            )
            
            assert session_id == expected_session_id
            if scenario == "success":
                dependencies['repository'].create_alert_session.assert_called_once()
    
    @pytest.mark.parametrize("status,error_message,final_analysis,existing_analysis,expected_status,expected_analysis,expected_completion", [
        ("completed", None, None, None, "completed", None, True),  # Basic completion
        ("completed", None, "# Alert Analysis\n\nSuccessfully resolved the Kubernetes issue.", None, 
         "completed", "# Alert Analysis\n\nSuccessfully resolved the Kubernetes issue.", True),  # With final analysis
        ("in_progress", None, None, "Existing analysis", "in_progress", "Existing analysis", False),  # Preserve existing analysis
    ])
    @pytest.mark.unit
    def test_update_session_status_scenarios(self, history_service, status, error_message, final_analysis, existing_analysis, expected_status, expected_analysis, expected_completion):
        """Test session status update for various scenarios."""
        dependencies = MockFactory.create_mock_history_service_dependencies()
        mock_session = SessionFactory.create_test_session(
            status=status,
            final_analysis=existing_analysis
        )
        dependencies['repository'].get_alert_session.return_value = mock_session
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            result = history_service.update_session_status(
                session_id="test-session-id",
                status=status,
                error_message=error_message,
                final_analysis=final_analysis
            )
            
            assert result == True
            assert mock_session.status == expected_status
            if expected_analysis:
                assert mock_session.final_analysis == expected_analysis
            if expected_completion:
                assert mock_session.completed_at_us is not None
            dependencies['repository'].update_alert_session.assert_called_once_with(mock_session)
    
    @pytest.mark.unit 
    @patch('tarsy.main.dashboard_manager')
    @patch('asyncio.run')
    @patch('asyncio.get_event_loop')
    def test_update_session_status_calls_dashboard_service(self, mock_get_loop, mock_asyncio_run, mock_dashboard_manager, history_service):
        """Test that session status update actually calls dashboard service."""
        dependencies = MockFactory.create_mock_history_service_dependencies()
        mock_session = SessionFactory.create_test_session(status="pending")
        dependencies['repository'].get_alert_session.return_value = mock_session
        
        # Setup mock dashboard update service
        mock_update_service = Mock()
        mock_dashboard_manager.update_service = mock_update_service
        
        # Mock asyncio to simulate non-async context (so it uses asyncio.run)
        mock_loop = Mock()
        mock_loop.is_running.return_value = False  # Not in async context
        mock_get_loop.return_value = mock_loop
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
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
            dependencies['repository'].update_alert_session.assert_called_once_with(mock_session)
            
            # Verify dashboard service is called via asyncio.run
            mock_asyncio_run.assert_called_once()
            called_coro = mock_asyncio_run.call_args[0][0]
            assert str(called_coro).find('process_session_status_change') != -1, \
                f"Expected process_session_status_change call, got: {called_coro}"
    
    @pytest.mark.unit 
    @patch('tarsy.main.dashboard_manager', None)  # Simulate dashboard_manager not available
    def test_update_session_status_without_dashboard_service(self, history_service):
        """Test that session status update works gracefully without dashboard service."""
        dependencies = MockFactory.create_mock_history_service_dependencies()
        mock_session = SessionFactory.create_test_session(status="pending")
        dependencies['repository'].get_alert_session.return_value = mock_session
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Call update_session_status - should work even without dashboard service
            result = history_service.update_session_status(
                session_id="test-session-id", 
                status="completed"
            )
            
            # Verify the basic functionality still works
            assert result == True
            assert mock_session.status == "completed"
            dependencies['repository'].update_alert_session.assert_called_once_with(mock_session)
    
    @pytest.mark.parametrize("interaction_type,interaction_data", [
        ("llm", {
            "session_id": "test-session-id",
            "model_name": "gpt-4",
            "step_description": "Test LLM call",
            "request_json": {"messages": [{"role": "user", "content": "Test prompt"}]},
            "response_json": {"choices": [{"message": {"role": "assistant", "content": "Test response"}, "finish_reason": "stop"}]}
        }),
        ("mcp", {
            "session_id": "test-session-id",
            "server_name": "test-server",
            "communication_type": "tool_call",
            "tool_name": "test_tool",
            "step_description": "Test MCP call",
            "success": True
        })
    ])
    @pytest.mark.unit
    def test_log_interaction_success(self, history_service, interaction_type, interaction_data):
        """Test successful interaction logging for both LLM and MCP."""
        dependencies = MockFactory.create_mock_history_service_dependencies()
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            if interaction_type == "llm":
                from tarsy.models.unified_interactions import LLMInteraction
                interaction = LLMInteraction(**interaction_data)
                result = history_service.log_llm_interaction(interaction)
                dependencies['repository'].create_llm_interaction.assert_called_once()
            else:
                from tarsy.models.unified_interactions import MCPInteraction
                interaction = MCPInteraction(**interaction_data)
                result = history_service.log_mcp_interaction(interaction)
                dependencies['repository'].create_mcp_communication.assert_called_once()
            
            assert result == True
    
    @pytest.mark.parametrize("service_enabled,expected_sessions,expected_count", [
        (True, 3, 3),  # Service enabled with sessions
        (False, 0, 0),  # Service disabled
    ])
    @pytest.mark.unit
    def test_get_sessions_list_scenarios(self, history_service, service_enabled, expected_sessions, expected_count):
        """Test sessions list retrieval for various scenarios."""
        dependencies = MockFactory.create_mock_history_service_dependencies()
        
        if service_enabled:
            # Phase 3: Repository now returns PaginatedSessions model
            session_overviews = MockFactory.create_mock_session_overviews(count=expected_sessions)
            dependencies['repository'].get_alert_sessions.return_value = MockFactory.create_mock_paginated_sessions(
                sessions=session_overviews,
                total_items=expected_count
            )
        else:
            # When service is disabled, get_repository returns None
            dependencies = None
        
        history_service.is_enabled = service_enabled
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            if service_enabled:
                mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
                mock_get_repo.return_value.__exit__.return_value = None
            else:
                mock_get_repo.return_value.__enter__.return_value = None
                mock_get_repo.return_value.__exit__.return_value = None
            
            sessions, total_count = history_service.get_sessions_list(
                filters={"status": "completed"} if service_enabled else None,
                page=1,
                page_size=20
            )
            
            assert len(sessions) == expected_sessions
            assert total_count == expected_count
            if service_enabled:
                dependencies['repository'].get_alert_sessions.assert_called_once()
    
    @pytest.mark.unit
    def test_get_session_timeline_success(self, history_service):
        """Test successful session timeline retrieval."""
        from tarsy.models.history_models import DetailedSession, DetailedStage, LLMInteraction, MCPInteraction, LLMEventDetails, MCPEventDetails
        from tarsy.models.constants import AlertSessionStatus, StageStatus
        from tarsy.models.unified_interactions import LLMMessage
        
        dependencies = MockFactory.create_mock_history_service_dependencies()
        
        # Create a proper DetailedSession mock object
        mock_detailed_session = DetailedSession(
            session_id="test-session-id",
            alert_id="alert-123", 
            alert_type="TestAlert",
            agent_type="TestAgent",
            status=AlertSessionStatus.COMPLETED,
            started_at_us=1000000,
            completed_at_us=2000000,
            error_message=None,
            alert_data={},
            final_analysis=None,
            session_metadata={},
            chain_id="test-chain-123",
            chain_definition={},
            current_stage_index=None,
            current_stage_id=None,
            total_interactions=2,
            llm_interaction_count=1,
            mcp_communication_count=1,
            stages=[]
        )
        
        dependencies['repository'].get_session_timeline.return_value = mock_detailed_session
        
        expected_timeline_data = {
            "session": {
                "session_id": "test-session-id",
                "alert_id": "alert-123",
                "alert_data": {},
                "agent_type": "TestAgent",
                "alert_type": "TestAlert",
                "status": "completed",
                "started_at_us": 1000000,
                "completed_at_us": 2000000,
                "error_message": None,
                "final_analysis": None,
                "session_metadata": {},
                "total_interactions": 2,
                "llm_interaction_count": 1,
                "mcp_communication_count": 1,
                "chain_id": "test-chain-123",
                "chain_definition": {},
                "current_stage_index": None,
                "current_stage_id": None
            },
            "chronological_timeline": [],
            "llm_interactions": [],
            "mcp_communications": []
        }
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            timeline = history_service.get_session_timeline("test-session-id")
            
            assert timeline == expected_timeline_data
            assert timeline["session"]["session_id"] == "test-session-id"
            assert timeline["session"]["status"] == "completed"
    
    @pytest.mark.parametrize("connection_success,expected_result", [
        (True, True),  # Connection successful
        (False, False),  # Connection failed
    ])
    @pytest.mark.unit
    def test_database_connection_scenarios(self, history_service, connection_success, expected_result):
        """Test database connection for various scenarios."""
        dependencies = MockFactory.create_mock_history_service_dependencies()
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            if connection_success:
                mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
                mock_get_repo.return_value.__exit__.return_value = None
            else:
                mock_get_repo.side_effect = Exception("Connection failed")
            
            result = history_service.test_database_connection()
            
            assert result == expected_result
            if connection_success:
                dependencies['repository'].get_alert_sessions.assert_called_once_with(page=1, page_size=1)
    

    @pytest.mark.unit
    def test_get_active_sessions(self, history_service):
        """Test active sessions retrieval."""
        dependencies = MockFactory.create_mock_history_service_dependencies()
        mock_active_sessions = [SessionFactory.create_in_progress_session() for _ in range(2)]
        dependencies['repository'].get_active_sessions.return_value = mock_active_sessions
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            active_sessions = history_service.get_active_sessions()
            
            assert len(active_sessions) == 2
            dependencies['repository'].get_active_sessions.assert_called_once()
    

    @pytest.mark.parametrize("operation_type,error_type,expected_result,expected_calls", [
        ("success_after_retry", "database is locked", "success", 2),  # Succeeds after retry
        ("exhausts_retries", "database is locked", None, 4),  # Fails after max retries
        ("non_retryable", "syntax error", None, 1),  # Fails immediately
    ])
    @pytest.mark.unit
    @patch('time.sleep')
    def test_retry_database_operation_scenarios(self, mock_sleep, history_service, operation_type, error_type, expected_result, expected_calls):
        """Test retry database operation for various scenarios."""
        call_count = 0
        
        def mock_operation():
            nonlocal call_count
            call_count += 1
            if operation_type == "success_after_retry" and call_count == 1:
                raise Exception(error_type)
            elif operation_type == "exhausts_retries":
                raise Exception(error_type)
            elif operation_type == "non_retryable":
                raise Exception(error_type)
            return "success"
        
        result = history_service._retry_database_operation("test_operation", mock_operation)
        
        assert result == expected_result
        assert call_count == expected_calls
        
        if operation_type == "success_after_retry":
            mock_sleep.assert_called_once()  # Should have slept once for retry
        elif operation_type == "exhausts_retries":
            assert mock_sleep.call_count == history_service.max_retries  # Should retry max_retries times
        else:  # non_retryable
            mock_sleep.assert_not_called()  # Should not retry for non-retryable errors

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


@pytest.mark.unit
class TestHistoryServiceStageExecution:
    """Test suite for HistoryService stage execution methods - covers bug fixes."""
    
    @pytest.fixture
    def sample_stage_execution(self):
        """Sample stage execution for testing."""
        from tarsy.models.history import StageExecution
        from tarsy.models.constants import StageStatus
        return StageExecution(
            session_id="test-session",
            stage_id="test-stage-0",
            stage_index=0,
            stage_name="Test Stage",
            agent="KubernetesAgent", 
            status=StageStatus.PENDING.value
        )
    
    @pytest.mark.asyncio
    async def test_create_stage_execution_no_repository_raises_error(self, sample_stage_execution):
        """Test that RuntimeError is raised when repository is unavailable - covers bug fix."""
        service = HistoryService()
        
        # Mock get_repository to return None (repository unavailable)
        with patch.object(service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = None
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Should raise RuntimeError instead of returning fallback ID
            with pytest.raises(RuntimeError, match="Failed to create stage execution record"):
                await service.create_stage_execution(sample_stage_execution)
    
    @pytest.mark.asyncio
    async def test_create_stage_execution_database_failure_raises_error(self, sample_stage_execution):
        """Test that database failures cause RuntimeError instead of fallback - covers bug fix."""
        service = HistoryService()
        
        # Mock the retry mechanism to return None (simulating all retries failed)
        with patch.object(service, '_retry_database_operation', return_value=None):
            # Should raise RuntimeError instead of returning fallback ID  
            with pytest.raises(RuntimeError, match="Failed to create stage execution record"):
                await service.create_stage_execution(sample_stage_execution)
    
    @pytest.mark.asyncio
    async def test_create_stage_execution_success_returns_id(self, sample_stage_execution):
        """Test successful stage execution creation returns the ID."""
        service = HistoryService()
        
        # Mock successful repository operation
        with patch.object(service, '_retry_database_operation', return_value="stage-exec-123"):
            result = await service.create_stage_execution(sample_stage_execution)
            assert result == "stage-exec-123"


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
    

    
    @pytest.mark.parametrize("scenario,expected_agent_types,expected_alert_types", [
        ("success", 2, 1),  # Repository available
        ("no_repository", 0, 0),  # Repository unavailable
        ("exception", 0, 0),  # Repository exception
    ])
    @pytest.mark.unit
    def test_get_filter_options_scenarios(self, scenario, expected_agent_types, expected_alert_types):
        """Test filter options retrieval for various scenarios."""
        service = HistoryService()
        service.is_enabled = True
        
        if scenario == "success":
            service._is_healthy = True
            dependencies = MockFactory.create_mock_history_service_dependencies()
            
            with patch.object(service, 'get_repository') as mock_get_repo:
                mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
                mock_get_repo.return_value.__exit__.return_value = None
                
                result = service.get_filter_options()
                
                assert len(result["agent_types"]) == expected_agent_types
                assert len(result["alert_types"]) == expected_alert_types
                assert len(result["status_options"]) == 4
                assert len(result["time_ranges"]) == 2
                dependencies['repository'].get_filter_options.assert_called_once()
        
        elif scenario == "no_repository":
            service._is_healthy = False
            
            with patch.object(service, 'get_repository') as mock_get_repo:
                mock_get_repo.return_value.__enter__.return_value = None
                
                result = service.get_filter_options()
                
                assert result["agent_types"] == []
                assert result["alert_types"] == []
                assert len(result["status_options"]) == 4
                assert len(result["time_ranges"]) == 4
        
        else:  # exception
            with patch.object(service, 'get_repository') as mock_get_repo:
                mock_get_repo.side_effect = Exception("Database error")
                
                result = service.get_filter_options()
                
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
    
    # Create session dictionaries (not Mock objects)
    mock_active_sessions = []
    mock_all_sessions = []
    
    for session_data in test_sessions:
        # Convert to dictionary format that matches repository return
        session_dict = {}
        for key, value in session_data.items():
            # Convert enum values to strings
            if hasattr(value, 'value'):
                session_dict[key] = value.value
            else:
                session_dict[key] = value
        
        # Add required fields that the service expects
        session_dict.setdefault('alert_data', {})
        session_dict.setdefault('chain_id', 'test-chain')
        session_dict.setdefault('started_at_us', 1640995200000000)
        
        mock_all_sessions.append(session_dict)
        
        # Only pending and in_progress should be returned by the active query
        status_value = session_data["status"].value if hasattr(session_data["status"], 'value') else session_data["status"]
        if status_value in AlertSessionStatus.active_values():
            mock_active_sessions.append(session_dict)
    
    # Mock repository responses - Phase 3: Repository now returns PaginatedSessions model
    from tarsy.models.converters import alert_session_to_session_overview
    
    # Convert session dicts to AlertSession objects, then to SessionOverview models
    session_overviews = []
    for session_dict in mock_active_sessions:
        alert_session = AlertSession(**session_dict)
        session_overview = alert_session_to_session_overview(alert_session)
        session_overviews.append(session_overview)
    
    mock_repo.get_alert_sessions.return_value = MockFactory.create_mock_paginated_sessions(
        sessions=session_overviews,
        page_size=1000,
        total_items=len(session_overviews)
    )
    mock_repo.update_alert_session.return_value = True
    
    # Mock the context manager
    history_service.get_repository = Mock(return_value=Mock(__enter__=Mock(return_value=mock_repo), __exit__=Mock(return_value=None)))
    
    # Call cleanup method
    cleaned_count = history_service.cleanup_orphaned_sessions()
    
    # Verify correct number of sessions were cleaned up
    assert cleaned_count == 2, f"Expected 2 sessions to be cleaned up, got {cleaned_count}"
    
    # Verify get_alert_sessions was called with correct parameters
    mock_repo.get_alert_sessions.assert_called_once_with(
        status=AlertSessionStatus.active_values(),
        page_size=1000
    )
    
    # Verify each orphaned session was updated correctly
    assert mock_repo.update_alert_session.call_count == 2
    
    # Check that orphaned sessions were updated via repository calls
    update_calls = mock_repo.update_alert_session.call_args_list
    assert len(update_calls) == 2, f"Expected 2 update calls, got {len(update_calls)}"
    
    # Verify each call had correct status and error message
    for call in update_calls:
        updated_session = call[0][0]  # First argument of the call
        assert updated_session.status == AlertSessionStatus.FAILED.value
        assert updated_session.error_message == "Backend was restarted - session terminated unexpectedly"
        assert updated_session.completed_at_us is not None


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


class TestHistoryServiceSummaryMethods:
    """Test suite for new summary calculation methods."""
    
    @pytest.fixture
    def history_service(self, isolated_test_settings):
        """Create HistoryService instance for testing."""
        with patch('tarsy.services.history_service.get_settings', return_value=isolated_test_settings):
            service = HistoryService()
            service._initialization_attempted = True
            service._is_healthy = True
            return service
    
    @pytest.mark.unit
    def test_calculate_session_summary_with_chain_data(self, history_service):
        """Test calculate_session_summary with complete chain data."""
        from tarsy.models.constants import StageStatus
        
        # Create mock session data with timeline and chain information
        session_data = {
            'chronological_timeline': [
                {'type': 'llm', 'status': 'completed', 'duration_ms': 1500},
                {'type': 'llm', 'status': 'completed', 'duration_ms': 2000},
                {'type': 'mcp', 'status': 'completed', 'duration_ms': 500},
                {'type': 'mcp', 'status': 'failed', 'duration_ms': 300},
                {'type': 'system', 'status': 'completed', 'duration_ms': 100}
            ],
            'session': {
                'chain_id': 'test-chain-123'
            },
            'stages': [
                {'status': StageStatus.COMPLETED.value, 'agent': 'AgentA'},
                {'status': StageStatus.COMPLETED.value, 'agent': 'AgentB'},
                {'status': StageStatus.FAILED.value, 'agent': 'AgentA'}
            ]
        }
        
        # Calculate summary
        summary = history_service.calculate_session_summary(session_data)
        
        # Verify basic statistics
        assert summary['total_interactions'] == 5
        assert summary['llm_interactions'] == 2
        assert summary['mcp_communications'] == 2
        assert summary['system_events'] == 1
        assert summary['errors_count'] == 1  # One failed interaction
        assert summary['total_duration_ms'] == 4400  # Sum of all durations
        
        # Verify chain statistics
        assert 'chain_statistics' in summary
        assert summary['chain_statistics']['total_stages'] == 3
        assert summary['chain_statistics']['completed_stages'] == 2
        assert summary['chain_statistics']['failed_stages'] == 1
        assert summary['chain_statistics']['stages_by_agent'] == {'AgentA': 2, 'AgentB': 1}

    @pytest.mark.unit 
    def test_calculate_session_summary_no_chain_data(self, history_service):
        """Test calculate_session_summary without chain data."""
        # Create mock session data without chain information
        session_data = {
            'chronological_timeline': [
                {'type': 'llm', 'status': 'completed', 'duration_ms': 1000},
                {'type': 'mcp', 'status': 'completed', 'duration_ms': 500}
            ],
            'session': {}  # No chain_id
        }
        
        # Calculate summary
        summary = history_service.calculate_session_summary(session_data)
        
        # Verify basic statistics
        assert summary['total_interactions'] == 2
        assert summary['llm_interactions'] == 1
        assert summary['mcp_communications'] == 1
        assert summary['system_events'] == 0
        assert summary['errors_count'] == 0
        assert summary['total_duration_ms'] == 1500
        
        # Verify no chain statistics
        assert 'chain_statistics' not in summary

    @pytest.mark.unit
    def test_calculate_session_summary_empty_data(self, history_service):
        """Test calculate_session_summary with empty data."""
        # Empty session data
        session_data = {
            'chronological_timeline': [],
            'session': {}
        }
        
        # Calculate summary
        summary = history_service.calculate_session_summary(session_data)
        
        # Verify all counts are zero
        assert summary['total_interactions'] == 0
        assert summary['llm_interactions'] == 0
        assert summary['mcp_communications'] == 0
        assert summary['system_events'] == 0
        assert summary['errors_count'] == 0
        assert summary['total_duration_ms'] == 0
        
        # Verify no chain statistics
        assert 'chain_statistics' not in summary

    @pytest.mark.unit
    def test_calculate_session_summary_none_data(self, history_service):
        """Test calculate_session_summary with None input."""
        # Calculate summary with None input
        summary = history_service.calculate_session_summary(None)
        
        # Should return empty dict
        assert summary == {}

    @pytest.mark.unit
    def test_calculate_session_summary_missing_duration(self, history_service):
        """Test calculate_session_summary handles missing duration gracefully."""
        # Session data with some events missing duration_ms
        session_data = {
            'chronological_timeline': [
                {'type': 'llm', 'status': 'completed', 'duration_ms': 1000},
                {'type': 'mcp', 'status': 'completed'},  # Missing duration_ms
                {'type': 'system', 'status': 'failed', 'duration_ms': None}  # None duration
            ],
            'session': {}
        }
        
        # Calculate summary
        summary = history_service.calculate_session_summary(session_data)
        
        # Should handle missing durations gracefully
        assert summary['total_interactions'] == 3
        assert summary['total_duration_ms'] == 1000  # Only count non-None durations
        assert summary['errors_count'] == 1

    @pytest.mark.unit
    async def test_get_session_summary_success(self, history_service):
        """Test get_session_summary with successful data retrieval - Phase 3: Updated for new implementation."""
        session_id = "test-session-123"
        
        # Phase 3: get_session_summary now uses get_session_with_stages directly 
        mock_detailed_session = MockFactory.create_mock_detailed_session(
            session_id=session_id,
            chain_id="test-chain"
        )
        
        # Mock the repository to return our DetailedSession
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_session_with_stages.return_value = mock_detailed_session
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Get summary
            summary = await history_service.get_session_summary(session_id)
        
        # Verify repository method was called
        dependencies['repository'].get_session_with_stages.assert_called_once_with(session_id)
        
        # Verify summary structure
        assert summary is not None
        assert 'total_interactions' in summary
        assert 'llm_interactions' in summary
        assert 'chain_statistics' in summary
        assert summary['total_interactions'] == 1
        assert summary['llm_interactions'] == 1
        assert summary['chain_statistics']['total_stages'] == 1
        assert summary['chain_statistics']['completed_stages'] == 1

    @pytest.mark.unit
    async def test_get_session_summary_not_found(self, history_service):
        """Test get_session_summary when session doesn't exist - Phase 3: Updated for new implementation."""
        session_id = "non-existent-session"
        
        # Phase 3: Mock repository to return None (session not found)
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_session_with_stages.return_value = None
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Get summary
            summary = await history_service.get_session_summary(session_id)
        
        # Should return None
        assert summary is None
        
        # Verify repository method was called (retry logic calls it 4 times on failure)
        assert dependencies['repository'].get_session_with_stages.call_count == 4
        dependencies['repository'].get_session_with_stages.assert_called_with(session_id)

    @pytest.mark.unit
    async def test_get_session_summary_non_chain_session(self, history_service):
        """Test get_session_summary for session with minimal chain data - Phase 3: All sessions are chains now."""
        session_id = "minimal-chain-session"
        
        # Phase 3: All sessions are chains, but this one has minimal chain data
        mock_detailed_session = MockFactory.create_mock_detailed_session(
            session_id=session_id,
            chain_id="minimal-chain",
            total_interactions=2,
            mcp_communication_count=1,
            stages=[]  # No stages
        )
        
        # Mock the repository to return our DetailedSession
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_session_with_stages.return_value = mock_detailed_session
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Get summary
            summary = await history_service.get_session_summary(session_id)
        
        # Verify repository method was called
        dependencies['repository'].get_session_with_stages.assert_called_once_with(session_id)
        
        # Verify summary structure - all sessions have chain statistics now
        assert summary is not None
        assert summary['total_interactions'] == 2
        assert summary['llm_interactions'] == 1
        assert summary['mcp_communications'] == 1
        assert 'chain_statistics' in summary
        assert summary['chain_statistics']['total_stages'] == 0  # No stages

    @pytest.mark.unit
    async def test_get_session_summary_chain_session_without_stages(self, history_service):
        """Test get_session_summary when repository returns None (error case) - Phase 3: Updated."""
        session_id = "error-case-session"
        
        # Phase 3: Repository returns None due to error or session not found
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_session_with_stages.return_value = None  # Simulate error/not found
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Get summary
            summary = await history_service.get_session_summary(session_id)
        
        # Should return None when repository can't find session or has error
        assert summary is None
        
        # Verify repository method was called (retry logic calls it 4 times on failure)
        assert dependencies['repository'].get_session_with_stages.call_count == 4
        dependencies['repository'].get_session_with_stages.assert_called_with(session_id)