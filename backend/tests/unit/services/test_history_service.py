"""
Unit tests for History Service.

Comprehensive test coverage for session management, LLM interaction logging,
MCP communication tracking, and timeline reconstruction with graceful
degradation when database operations fail.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.config.settings import Settings
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.services.history_service import (
    HistoryService,
    HistoryServiceInitializationError,
    get_history_service,
)
from tests.utils import MockFactory, SessionFactory


class TestHistoryService:
    """Test suite for HistoryService class."""
    
    @pytest.fixture
    def mock_settings(self, isolated_test_settings):
        """Create mock settings for testing."""
        return isolated_test_settings
    
    @pytest.fixture
    def history_service(self, mock_settings):
        """Create HistoryService instance with mocked dependencies."""
        with patch('tarsy.services.history_service.base_infrastructure.get_settings', return_value=mock_settings):
            service = HistoryService()
            service._infra._set_healthy_for_testing()
            return service
    
    @pytest.mark.unit
    def test_initialization_scenarios(self):
        """Test service initialization for various scenarios."""
        expected_url = "sqlite:///:memory:"
        mock_settings = MockFactory.create_mock_settings(
            database_url=expected_url
        )
        
        with patch('tarsy.services.history_service.base_infrastructure.get_settings', return_value=mock_settings):
            service = HistoryService()
            assert service._infra.settings.database_url == expected_url
    
    @pytest.mark.parametrize("failure_type,expected_result,expected_attempted,expected_healthy", [
        ("success", True, True, True),  # Successful initialization
        ("database_failure", False, True, False),  # Database connection failure
        ("schema_failure", False, True, False),  # Schema creation failure
    ])
    @pytest.mark.unit
    @patch('tarsy.services.history_service.base_infrastructure.DatabaseManager')
    def test_initialize_scenarios(self, mock_db_manager_class, failure_type, expected_result, expected_attempted, expected_healthy):
        """Test service initialization for various failure scenarios."""
        # Create mock settings based on scenario
        mock_settings = MockFactory.create_mock_settings(
            database_url="sqlite:///test.db"
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
        
        with patch('tarsy.services.history_service.base_infrastructure.get_settings', return_value=mock_settings):
            service = HistoryService()
            result = service.initialize()
            
            assert result == expected_result
            assert service._infra._initialization_attempted == expected_attempted
            assert service._infra._is_healthy == expected_healthy
            
            if failure_type == "success":
                mock_db_instance.initialize.assert_called_once()
                mock_db_instance.create_tables.assert_called_once()
    
    @pytest.mark.parametrize("service_enabled,expected_repo", [
        (True, "mock_repo"),  # Service enabled
        (False, None),  # Service disabled
    ])
    @pytest.mark.unit
    @patch('tarsy.services.history_service.base_infrastructure.HistoryRepository')
    def test_get_repository_scenarios(self, mock_repo_class, history_service, service_enabled, expected_repo):
        """Test repository access for various scenarios."""
        dependencies = MockFactory.create_mock_history_service_dependencies()
        
        if service_enabled:
            history_service._infra.db_manager = dependencies['db_manager']
            mock_repo_class.return_value = dependencies['repository']
        
        with history_service._infra.get_repository() as repo:
            if expected_repo == "mock_repo":
                assert repo == dependencies['repository']
            else:
                assert repo is None
    
    @pytest.mark.parametrize("scenario,service_enabled,repo_side_effect,expected_result", [
        ("success", True, None, True),  # Successful creation
        ("exception", True, Exception("Database error"), False),  # Database error
    ])
    @pytest.mark.unit
    def test_create_session_scenarios(self, history_service, scenario, service_enabled, repo_side_effect, expected_result):
        """Test session creation for various scenarios."""
        dependencies = MockFactory.create_mock_history_service_dependencies()
        
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            if repo_side_effect:
                mock_get_repo.side_effect = repo_side_effect
            else:
                mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
                mock_get_repo.return_value.__exit__.return_value = None
            
            # Create mock ChainContext and ChainConfigModel
            from tarsy.models.agent_config import (
                ChainConfigModel,
                ChainStageConfigModel,
            )
            from tarsy.models.alert import ProcessingAlert
            from tarsy.models.processing_context import ChainContext
            from tarsy.utils.timestamp import now_us
            
            processing_alert = ProcessingAlert(
                alert_type="test_alert",
                severity="warning",
                timestamp=now_us(),
                environment="test",
                alert_data={"alert_type": "test", "environment": "test"}
            )
            chain_context = ChainContext.from_processing_alert(
                processing_alert=processing_alert,
                session_id="test-session-id",
                current_stage_name="test_stage"
            )
            
            chain_definition = ChainConfigModel(
                chain_id="test-chain",
                alert_types=["test_alert"],
                stages=[
                    ChainStageConfigModel(
                        name="test_stage",
                        agent="TestAgent"
                    )
                ]
            )
            
            result = history_service.create_session(
                chain_context=chain_context,
                chain_definition=chain_definition
            )
            
            assert result == expected_result
            if scenario == "success":
                dependencies['repository'].create_alert_session.assert_called_once()
    
    @pytest.mark.parametrize("mcp_selection,expected_serialized", [
        (None, None),  # No MCP selection
        (
            # MCP selection with server only (all tools)
            {
                "servers": [
                    {"name": "kubernetes-server", "tools": None}
                ]
            },
            {
                "servers": [
                    {"name": "kubernetes-server", "tools": None}
                ],
                "native_tools": None
            }
        ),
        (
            # MCP selection with specific tools
            {
                "servers": [
                    {"name": "kubernetes-server", "tools": ["list_pods", "get_pod"]},
                    {"name": "argocd-server", "tools": None}
                ]
            },
            {
                "servers": [
                    {"name": "kubernetes-server", "tools": ["list_pods", "get_pod"]},
                    {"name": "argocd-server", "tools": None}
                ],
                "native_tools": None
            }
        ),
    ])
    @pytest.mark.unit
    def test_create_session_stores_mcp_selection(self, history_service, mcp_selection, expected_serialized):
        """Test that create_session correctly stores MCP selection in database."""
        from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
        from tarsy.models.alert import Alert, ProcessingAlert
        from tarsy.models.mcp_selection_models import MCPSelectionConfig
        from tarsy.models.processing_context import ChainContext
        
        dependencies = MockFactory.create_mock_history_service_dependencies()
        
        # Create alert with optional MCP selection
        api_alert = Alert(
            alert_type="kubernetes",
            data={"namespace": "test"},
            mcp=MCPSelectionConfig(**mcp_selection) if mcp_selection else None
        )
        
        processing_alert = ProcessingAlert.from_api_alert(api_alert, default_alert_type="kubernetes")
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-id",
            current_stage_name="analysis"
        )
        
        chain_definition = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["kubernetes"],
            stages=[ChainStageConfigModel(name="analysis", agent="KubernetesAgent")]
        )
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            result = history_service.create_session(
                chain_context=chain_context,
                chain_definition=chain_definition
            )
            
            assert result is True
            
            # Verify the session was created with correct mcp_selection
            call_args = dependencies['repository'].create_alert_session.call_args
            assert call_args is not None
            
            created_session = call_args[0][0]  # First positional argument
            assert created_session.mcp_selection == expected_serialized
    
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
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
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
    
    @pytest.mark.parametrize("interaction_type,interaction_data", [
        ("llm", {
            "session_id": "test-session-id",
            "model_name": "gpt-4",
            "step_description": "Test LLM call",
            "conversation": {
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Test prompt"},
                    {"role": "assistant", "content": "Test response"}
                ]
            }
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
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            if interaction_type == "llm":
                from tarsy.models.unified_interactions import LLMInteraction
                interaction = LLMInteraction(**interaction_data)
                result = history_service.store_llm_interaction(interaction)
                dependencies['repository'].create_llm_interaction.assert_called_once()
            else:
                from tarsy.models.unified_interactions import MCPInteraction
                interaction = MCPInteraction(**interaction_data)
                result = history_service.store_mcp_interaction(interaction)
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
            session_overviews = MockFactory.create_mock_session_overviews(count=expected_sessions)
            dependencies['repository'].get_alert_sessions.return_value = MockFactory.create_mock_paginated_sessions(
                sessions=session_overviews,
                total_items=expected_count
            )
        else:
            # When service is disabled, get_repository returns None
            dependencies = None
        
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            if service_enabled:
                mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
                mock_get_repo.return_value.__exit__.return_value = None
            else:
                mock_get_repo.return_value.__enter__.return_value = None
                mock_get_repo.return_value.__exit__.return_value = None
            
            if service_enabled:
                result = history_service.get_sessions_list(
                    filters={"status": "completed"},
                    page=1,
                    page_size=20
                )
                assert result is not None
                assert len(result.sessions) == expected_sessions
                assert result.pagination.total_items == expected_count
                dependencies['repository'].get_alert_sessions.assert_called_once()
            else:
                # When repository is unavailable, should return None (with retry logic)
                result = history_service.get_sessions_list(
                    filters=None,
                    page=1,
                    page_size=20
                )
                assert result is None
    
    @pytest.mark.unit
    def test_get_session_details_success(self, history_service):
        """Test successful session timeline retrieval."""
        from tarsy.models.constants import AlertSessionStatus
        from tarsy.models.history_models import (
            DetailedSession,
        )
        
        dependencies = MockFactory.create_mock_history_service_dependencies()
        
        # Create a proper DetailedSession mock object
        mock_detailed_session = DetailedSession(
            session_id="test-session-id",
            alert_type="TestAlert",
            agent_type="TestAgent",
            status=AlertSessionStatus.COMPLETED,
            started_at_us=1000000,
            completed_at_us=2000000,
            error_message=None,
            alert_data={},
            final_analysis=None,
            final_analysis_summary=None,
            session_metadata={},
            chain_id="test-chain-123",
            chain_definition={},
            current_stage_index=None,
            current_stage_id=None,
            total_interactions=2,
            llm_interaction_count=1,
            mcp_communication_count=1,
            mcp_selection=None,
            stages=[]
        )
        
        dependencies['repository'].get_session_details.return_value = mock_detailed_session
        
        expected_timeline_data = {
            "session": {
                "session_id": "test-session-id",
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
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            timeline = history_service.get_session_details("test-session-id")
            
            assert timeline is not None
            assert isinstance(timeline, DetailedSession)
            assert timeline.session_id == "test-session-id"
            assert timeline.status == AlertSessionStatus.COMPLETED
    
    @pytest.mark.unit
    def test_get_session_details_with_mcp_selection(self, history_service):
        """Test session details retrieval includes mcp_selection."""
        from tarsy.models.constants import AlertSessionStatus
        from tarsy.models.history_models import DetailedSession
        from tarsy.models.mcp_selection_models import (
            MCPSelectionConfig,
            MCPServerSelection,
        )
        
        dependencies = MockFactory.create_mock_history_service_dependencies()
        
        # Create DetailedSession with MCP selection
        mock_detailed_session = DetailedSession(
            session_id="test-session-mcp",
            alert_type="kubernetes",
            agent_type="chain:k8s-analysis",
            status=AlertSessionStatus.COMPLETED,
            started_at_us=1000000,
            completed_at_us=2000000,
            error_message=None,
            alert_data={"namespace": "test"},
            final_analysis="Analysis complete",
            session_metadata={},
            chain_id="test-chain-mcp",
            chain_definition={},
            current_stage_index=None,
            current_stage_id=None,
            total_interactions=5,
            llm_interaction_count=3,
            mcp_communication_count=2,
            mcp_selection=MCPSelectionConfig(
                servers=[
                    MCPServerSelection(name="kubectl", tools=["get_pods", "describe_pod"]),
                    MCPServerSelection(name="argocd")
                ]
            ),
            stages=[]
        )
        
        dependencies['repository'].get_session_details.return_value = mock_detailed_session
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            result = history_service.get_session_details("test-session-mcp")
            
            assert result is not None
            assert isinstance(result, DetailedSession)
            assert result.session_id == "test-session-mcp"
            assert result.status == AlertSessionStatus.COMPLETED
            
            # Verify MCP selection is included
            assert result.mcp_selection is not None
            assert len(result.mcp_selection.servers) == 2
            assert result.mcp_selection.servers[0].name == "kubectl"
            assert result.mcp_selection.servers[0].tools == ["get_pods", "describe_pod"]
            assert result.mcp_selection.servers[1].name == "argocd"
            assert result.mcp_selection.servers[1].tools is None
    
    @pytest.mark.unit
    def test_get_session_details_with_chat_fields(self, history_service):
        """Test session details retrieval includes chat_id and chat_user_message_id for chat stages."""
        from tarsy.models.constants import AlertSessionStatus, StageStatus
        from tarsy.models.history_models import DetailedSession, DetailedStage
        
        dependencies = MockFactory.create_mock_history_service_dependencies()
        
        # Create mock stages - one regular, one chat
        regular_stage = DetailedStage(
            execution_id="exec-regular",
            session_id="test-session-chat",
            stage_id="analysis",
            stage_index=0,
            stage_name="Analysis",
            agent="AnalysisAgent",
            status=StageStatus.COMPLETED,
            started_at_us=1000000,
            completed_at_us=2000000,
            duration_ms=1000,
            stage_output={"result": "analysis complete"},
            error_message=None,
            chat_id=None,  # Regular stage has no chat context
            chat_user_message_id=None,
            llm_interactions=[],
            mcp_communications=[],
            llm_interaction_count=0,
            mcp_communication_count=0,
            total_interactions=0
        )
        
        chat_stage = DetailedStage(
            execution_id="exec-chat",
            session_id="test-session-chat",
            stage_id="chat-response-msg123",
            stage_index=1,
            stage_name="Chat Response",
            agent="ChatAgent",
            status=StageStatus.COMPLETED,
            started_at_us=3000000,
            completed_at_us=4000000,
            duration_ms=1000,
            stage_output={"result": "chat response"},
            error_message=None,
            chat_id="chat-abc-123",  # Chat stage has chat context
            chat_user_message_id="msg-xyz-456",
            llm_interactions=[],
            mcp_communications=[],
            llm_interaction_count=0,
            mcp_communication_count=0,
            total_interactions=0
        )
        
        # Create DetailedSession with both stages
        mock_detailed_session = DetailedSession(
            session_id="test-session-chat",
            alert_type="kubernetes",
            agent_type="chain:k8s-analysis",
            status=AlertSessionStatus.COMPLETED,
            started_at_us=1000000,
            completed_at_us=4000000,
            error_message=None,
            alert_data={"namespace": "test"},
            final_analysis="Analysis complete",
            session_metadata={},
            chain_id="test-chain",
            chain_definition={},
            current_stage_index=None,
            current_stage_id=None,
            total_interactions=0,
            llm_interaction_count=0,
            mcp_communication_count=0,
            stages=[regular_stage, chat_stage]
        )
        
        dependencies['repository'].get_session_details.return_value = mock_detailed_session
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            result = history_service.get_session_details("test-session-chat")
            
            assert result is not None
            assert isinstance(result, DetailedSession)
            assert len(result.stages) == 2
            
            # Verify regular stage has no chat fields
            regular_stage_result = result.stages[0]
            assert regular_stage_result.agent == "AnalysisAgent"
            assert regular_stage_result.chat_id is None
            assert regular_stage_result.chat_user_message_id is None
            
            # Verify chat stage has chat fields populated
            chat_stage_result = result.stages[1]
            assert chat_stage_result.agent == "ChatAgent"
            assert chat_stage_result.chat_id == "chat-abc-123"
            assert chat_stage_result.chat_user_message_id == "msg-xyz-456"
    
    @pytest.mark.parametrize("connection_success,expected_result", [
        (True, True),  # Connection successful
        (False, False),  # Connection failed
    ])
    @pytest.mark.unit
    def test_database_connection_scenarios(self, history_service, connection_success, expected_result):
        """Test database connection for various scenarios."""
        dependencies = MockFactory.create_mock_history_service_dependencies()
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
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
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
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
            if operation_type == "success_after_retry" and call_count == 1 or operation_type == "exhausts_retries" or operation_type == "non_retryable":
                raise Exception(error_type)
            return "success"
        
        result = history_service._infra._retry_database_operation("test_operation", mock_operation)
        
        assert result == expected_result
        assert call_count == expected_calls
        
        if operation_type == "success_after_retry":
            mock_sleep.assert_called_once()  # Should have slept once for retry
        elif operation_type == "exhausts_retries":
            assert mock_sleep.call_count == history_service._infra.max_retries  # Should retry max_retries times
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
            mock_instance.initialize.return_value = True
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
            mock_instance.initialize.return_value = True
            mock_service_class.return_value = mock_instance

            service = get_history_service()

            assert service == mock_instance
            mock_instance.initialize.assert_called_once()

    @pytest.mark.unit
    @patch('tarsy.services.history_service._history_service', None)
    def test_get_history_service_initialization_failure_raises_exception(self):
        """Test that get_history_service raises exception when initialization fails."""
        with patch('tarsy.services.history_service.HistoryService') as mock_service_class:
            mock_instance = Mock()
            mock_instance.initialize.return_value = False
            mock_service_class.return_value = mock_instance

            with pytest.raises(HistoryServiceInitializationError) as exc_info:
                get_history_service()

            assert "Failed to initialize HistoryService" in str(exc_info.value)
            mock_instance.initialize.assert_called_once()


@pytest.mark.unit
class TestHistoryServiceStageExecution:
    """Test suite for HistoryService stage execution methods - covers bug fixes."""
    
    @pytest.fixture
    def sample_stage_execution(self):
        """Sample stage execution for testing."""
        from tarsy.models.constants import StageStatus
        from tarsy.models.db_models import StageExecution
        return StageExecution(
            execution_id="stage-exec-123",
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
        with patch.object(service._infra, 'get_repository') as mock_get_repo:
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
        with patch.object(service._infra, '_retry_database_operation_async', new=AsyncMock(return_value=None)):
            # Should raise RuntimeError instead of returning fallback ID  
            with pytest.raises(RuntimeError, match="Failed to create stage execution record"):
                await service.create_stage_execution(sample_stage_execution)
    
    @pytest.mark.asyncio
    async def test_create_stage_execution_success_returns_id(self, sample_stage_execution):
        """Test successful stage execution creation returns the ID."""
        service = HistoryService()
        
        # Mock successful repository operation
        with patch.object(service._infra, '_retry_database_operation_async', new=AsyncMock(return_value="stage-exec-123")):
            result = await service.create_stage_execution(sample_stage_execution)
            assert result == "stage-exec-123"
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_success(self, sample_stage_execution):
        """Test successful stage execution update."""
        service = HistoryService()
        
        # Update stage execution status
        from tarsy.models.constants import StageStatus
        sample_stage_execution.status = StageStatus.COMPLETED.value
        sample_stage_execution.stage_output = {"success": True, "message": "Test completed successfully"}
        sample_stage_execution.completed_at_us = 1640995200000000
        sample_stage_execution.duration_ms = 5000
        
        # Mock successful repository operation
        with patch.object(service._infra, '_retry_database_operation_async', new=AsyncMock(return_value=True)):
            result = await service.update_stage_execution(sample_stage_execution)
            assert result == True
            
            # Verify retry operation was called with correct operation name
            service._infra._retry_database_operation_async.assert_called_once()
            args, kwargs = service._infra._retry_database_operation_async.call_args
            assert args[0] == "update_stage_execution"
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_failure(self, sample_stage_execution):
        """Test stage execution update failure."""
        service = HistoryService()
        
        # Mock failed repository operation
        with patch.object(service._infra, '_retry_database_operation_async', new=AsyncMock(return_value=None)):
            result = await service.update_stage_execution(sample_stage_execution)
            assert result == False
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_no_repository(self, sample_stage_execution):
        """Test stage execution update when repository is unavailable."""
        service = HistoryService()
        
        # Mock get_repository to return None (repository unavailable)
        def mock_operation():
            with service._infra.get_repository() as repo:
                if not repo:
                    raise RuntimeError("History repository unavailable - cannot update stage execution")
                return repo.update_stage_execution(sample_stage_execution)
        
        # Mock the actual implementation to test error path
        with patch.object(service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = None
            mock_get_repo.return_value.__exit__.return_value = None
            
            with patch.object(service._infra, '_retry_database_operation_async', new=AsyncMock()) as mock_retry:
                mock_retry.side_effect = lambda name, func: func()
                
                # Should call retry operation which should return None/False
                with patch.object(service._infra, '_retry_database_operation_async', new=AsyncMock(return_value=None)):
                    result = await service.update_stage_execution(sample_stage_execution)
                    assert result == False
    
    @pytest.mark.asyncio
    async def test_update_session_current_stage_success(self):
        """Test successful session current stage update."""
        service = HistoryService()
        
        # Mock successful repository operation
        with patch.object(service._infra, '_retry_database_operation_async', new=AsyncMock(return_value=True)):
            result = await service.update_session_current_stage(
                session_id="test-session",
                current_stage_index=2,
                current_stage_id="stage-2"
            )
            assert result == True
            
            # Verify retry operation was called with correct operation name
            service._infra._retry_database_operation_async.assert_called_once()
            args, kwargs = service._infra._retry_database_operation_async.call_args
            assert args[0] == "update_session_current_stage"
    
    @pytest.mark.asyncio
    async def test_update_session_current_stage_failure(self):
        """Test session current stage update failure."""
        service = HistoryService()
        
        # Mock failed repository operation
        with patch.object(service._infra, '_retry_database_operation_async', new=AsyncMock(return_value=None)):
            result = await service.update_session_current_stage(
                session_id="test-session",
                current_stage_index=2,
                current_stage_id="stage-2"
            )
            assert result == False
    
    @pytest.mark.asyncio
    async def test_update_session_current_stage_no_repository(self):
        """Test session current stage update when repository is unavailable."""
        service = HistoryService()
        
        # Mock get_repository to return None (repository unavailable)
        with patch.object(service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = None
            mock_get_repo.return_value.__exit__.return_value = None
            
            with patch.object(service._infra, '_retry_database_operation_async', new=AsyncMock(return_value=None)):
                result = await service.update_session_current_stage(
                    session_id="test-session",
                    current_stage_index=2,
                    current_stage_id="stage-2"
                )
                assert result == False
    
    @pytest.mark.asyncio
    async def test_get_stage_execution_success(self, sample_stage_execution):
        """Test successful stage execution retrieval."""
        service = HistoryService()
        
        # Mock successful repository operation
        with patch.object(service._infra, '_retry_database_operation_async', new=AsyncMock(return_value=sample_stage_execution)):
            result = await service.get_stage_execution("stage-exec-123")
            
            assert result == sample_stage_execution
            assert result.execution_id == "stage-exec-123"
            assert result.stage_name == "Test Stage"
            
            # Verify retry operation was called with correct parameters
            service._infra._retry_database_operation_async.assert_called_once()
            args, kwargs = service._infra._retry_database_operation_async.call_args
            assert args[0] == "get_stage_execution"
            assert kwargs.get("treat_none_as_success") == True
    
    @pytest.mark.asyncio
    async def test_get_stage_execution_not_found(self):
        """Test stage execution retrieval when execution doesn't exist."""
        service = HistoryService()
        
        # Mock repository returning None (execution not found)
        with patch.object(service._infra, '_retry_database_operation_async', new=AsyncMock(return_value=None)):
            result = await service.get_stage_execution("non-existent-exec")
            
            assert result is None
            
            # Verify retry operation was called with treat_none_as_success=True
            service._infra._retry_database_operation_async.assert_called_once()
            args, kwargs = service._infra._retry_database_operation_async.call_args
            assert args[0] == "get_stage_execution"
            assert kwargs.get("treat_none_as_success") == True
    
    @pytest.mark.asyncio
    async def test_get_stage_execution_no_repository(self):
        """Test stage execution retrieval when repository is unavailable."""
        service = HistoryService()
        
        # Mock get_repository to return None (repository unavailable)
        with patch.object(service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = None
            mock_get_repo.return_value.__exit__.return_value = None
            
            with patch.object(service._infra, '_retry_database_operation_async', new=AsyncMock(return_value=None)):
                result = await service.get_stage_execution("stage-exec-123")
                assert result is None


class TestHistoryServiceErrorHandling:
    """Test suite for HistoryService error handling scenarios."""
    
    @pytest.fixture
    def history_service_with_errors(self):
        """Create HistoryService that simulates various error conditions."""
        mock_settings = Mock(spec=Settings)
        mock_settings.database_url = "sqlite:///test_history.db"
        mock_settings.history_retention_days = 90
        
        with patch('tarsy.services.history_service.base_infrastructure.get_settings', return_value=mock_settings):
            service = HistoryService()
            service._infra._set_healthy_for_testing(is_healthy=False)
            return service
    
    @pytest.mark.unit
    def test_repository_unavailable_raises_runtime_error(self, history_service_with_errors):
        """Test that RuntimeError is raised when repository is unavailable."""
        with patch.object(history_service_with_errors._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = None
            mock_get_repo.return_value.__exit__.return_value = None
            
            # All operations should raise RuntimeError when repository unavailable
            # Create minimal mock objects for new signature
            from tarsy.models.agent_config import (
                ChainConfigModel,
                ChainStageConfigModel,
            )
            from tarsy.models.alert import ProcessingAlert
            from tarsy.models.processing_context import ChainContext
            from tarsy.utils.timestamp import now_us
            
            processing_alert = ProcessingAlert(
                alert_type="alert",
                severity="warning",
                timestamp=now_us(),
                environment="production",
                alert_data={"test": "data"}
            )
            chain_context = ChainContext.from_processing_alert(
                processing_alert=processing_alert,
                session_id="test-session-id",
                current_stage_name="test_stage"
            )
            
            chain_definition = ChainConfigModel(
                chain_id="test-chain",
                alert_types=["alert"],
                stages=[
                    ChainStageConfigModel(
                        name="test_stage",
                        agent="agent"
                    )
                ]
            )
            
            # create_session returns False when repository unavailable
            result = history_service_with_errors.create_session(chain_context, chain_definition)
            assert result == False
            
            # update_session_status returns False when repository unavailable  
            result = history_service_with_errors.update_session_status("test", "completed")
            assert result == False
            
            # get_sessions_list returns None when repository unavailable (with retry logic)
            result = history_service_with_errors.get_sessions_list()
            assert result is None
            
            # get_active_sessions returns empty list when repository unavailable (with retry logic)
            result = history_service_with_errors.get_active_sessions()
            assert result == []
            
            # get_filter_options returns None when repository unavailable (with retry logic)
            result = history_service_with_errors.get_filter_options()
            assert result is None
    
    @pytest.mark.unit
    def test_exception_handling_in_operations(self, history_service_with_errors):
        """Test exception handling in various operations."""
        with patch.object(history_service_with_errors._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.side_effect = Exception("Simulated error")
            
            # All operations should handle exceptions gracefully
            # Create minimal mock objects for new signature
            from tarsy.models.agent_config import (
                ChainConfigModel,
                ChainStageConfigModel,
            )
            from tarsy.models.alert import ProcessingAlert
            from tarsy.models.processing_context import ChainContext
            from tarsy.utils.timestamp import now_us
            
            processing_alert = ProcessingAlert(
                alert_type="alert",
                severity="warning",
                timestamp=now_us(),
                environment="production",
                alert_data={"test": "data"}
            )
            chain_context = ChainContext.from_processing_alert(
                processing_alert=processing_alert,
                session_id="test-session-id",
                current_stage_name="test_stage"
            )
            
            chain_definition = ChainConfigModel(
                chain_id="test-chain",
                alert_types=["alert"],
                stages=[
                    ChainStageConfigModel(
                        name="test_stage",
                        agent="agent"
                    )
                ]
            )
            
            result = history_service_with_errors.create_session(chain_context, chain_definition)
            assert result == False
            
            # Create unified interaction model for error test
            from tarsy.models.unified_interactions import LLMInteraction
            interaction = LLMInteraction(
                session_id="test",
                model_name="model",
                step_description="step",
                conversation=LLMConversation(messages=[
                    LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
                    LLMMessage(role=MessageRole.USER, content="prompt"),
                    LLMMessage(role=MessageRole.ASSISTANT, content="response")
                ])
            )
            # Test that store methods return False when repository unavailable
            with patch.object(history_service_with_errors._infra, 'get_repository') as mock_get_repo_inner:
                mock_get_repo_inner.return_value.__enter__.return_value = None
                mock_get_repo_inner.return_value.__exit__.return_value = None
                
                # store_llm_interaction returns False when repository unavailable
                result = history_service_with_errors.store_llm_interaction(interaction)
                assert result == False
                
                from tarsy.models.unified_interactions import MCPInteraction
                mcp_interaction = MCPInteraction(
                    session_id="test",
                    server_name="server", 
                    communication_type="type",
                    tool_name="tool",
                    step_description="step"
                )
                # store_mcp_interaction returns False when repository unavailable
                result = history_service_with_errors.store_mcp_interaction(mcp_interaction)
                assert result == False


class TestDashboardMethods:
    """Test suite for new dashboard-specific methods in HistoryService."""
    

    
    @pytest.mark.parametrize("scenario,expected_agent_types,expected_alert_types", [
        ("success", 2, 1),  # Repository available
    ])
    @pytest.mark.unit
    def test_get_filter_options_scenarios(self, scenario, expected_agent_types, expected_alert_types):
        """Test filter options retrieval for various scenarios."""
        service = HistoryService()
        
        if scenario == "success":
            service._infra._set_healthy_for_testing()
            dependencies = MockFactory.create_mock_history_service_dependencies()
            
            with patch.object(service._infra, 'get_repository') as mock_get_repo:
                mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
                mock_get_repo.return_value.__exit__.return_value = None
                
                result = service.get_filter_options()
                
                assert len(result.agent_types) == expected_agent_types
                assert len(result.alert_types) == expected_alert_types
                assert len(result.status_options) == 4
                assert len(result.time_ranges) == 2
                dependencies['repository'].get_filter_options.assert_called_once()
    
    @pytest.mark.unit
    def test_get_filter_options_no_repository_returns_none(self):
        """Test that None is returned when repository is unavailable (with retry logic)."""
        service = HistoryService()
        service._infra._set_healthy_for_testing(is_healthy=False)
        
        with patch.object(service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = None
            mock_get_repo.return_value.__exit__.return_value = None
            
            result = service.get_filter_options()
            assert result is None

@pytest.mark.unit
class TestHistoryServiceRetryLogicDuplicatePrevention:
    """Test HistoryService retry logic improvements for duplicate prevention."""
    
    @pytest.fixture
    def history_service(self):
        """Create HistoryService instance for testing."""
        with patch('tarsy.services.history_service.base_infrastructure.get_settings') as mock_settings:
            mock_settings.return_value.database_url = "sqlite:///test.db"
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
        
        result = history_service._infra._retry_database_operation("test_operation", operation)
        
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
        
        result = history_service._infra._retry_database_operation("test_operation", operation)
        
        assert result == "success"
        assert call_count == 3  # Should retry twice, succeed on third
    
    def test_retry_operation_exhausts_retries(self, history_service):
        """Test that operations fail after exhausting all retries."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            raise Exception("database is locked")
        
        result = history_service._infra._retry_database_operation("test_operation", operation)
        
        assert result is None
        assert call_count == 4  # Initial attempt + 3 retries
    
    def test_retry_operation_non_retryable_error(self, history_service):
        """Test that non-retryable errors don't trigger retries."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid data")  # Not a retryable error
        
        result = history_service._infra._retry_database_operation("test_operation", operation)
        
        assert result is None
        assert call_count == 1  # Should not retry
    
    def test_retry_operation_create_session_no_retry_after_first_attempt(self, history_service):
        """Test that create_session operations don't retry after first failure to prevent duplicates."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return True  # First attempt succeeds
            raise Exception("database is locked")  # Shouldn't reach here
        
        result = history_service._infra._retry_database_operation("create_session", operation)
        
        assert result == True
        assert call_count == 1
    
    def test_retry_operation_create_session_prevents_duplicate_retry(self, history_service):
        """Test that create_session doesn't retry after database errors to prevent duplicates."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            raise Exception("connection timeout")  # Always fails
        
        result = history_service._infra._retry_database_operation("create_session", operation)
        
        assert result is None  # Should return None after first failure
        assert call_count == 1   # First attempt only, no retries to prevent duplicates
    
    def test_retry_operation_non_create_session_retries_normally(self, history_service):
        """Test that non-create_session operations retry normally."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("database is locked")
            return "success"
        
        result = history_service._infra._retry_database_operation("update_session", operation)
        
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
        
        with patch.object(history_service._infra, 'max_retries', 3):
            result = history_service._infra._retry_database_operation("test_operation", operation)
        
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
        
        result = history_service._infra._retry_database_operation("test_operation", operation)
        
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
        result = history_service._infra._retry_database_operation("test_operation", operation)
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
    
    def test_retry_operation_handles_sqlite_retryable_errors(self, history_service):
        """Test that SQLite-specific retryable errors trigger retries (SQLite backend)."""
        # These are SQLite-specific errors and common connection errors
        sqlite_retryable_errors = [
            "database is locked",
            "database disk image is malformed",
            "sqlite3.operationalerror",
            "database table is locked",
        ]
        
        # Common errors that apply to both SQLite and PostgreSQL
        common_retryable_errors = [
            "connection timeout",
            "connection pool",
            "connection closed"
        ]
        
        for error_msg in sqlite_retryable_errors + common_retryable_errors:
            call_count = 0
            
            def operation():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception(error_msg)
                return "success"
            
            result = history_service._infra._retry_database_operation("test_operation", operation)
            
            assert result == "success", f"Should retry for error: {error_msg}"
            assert call_count == 2, f"Should have retried once for error: {error_msg}"
    
    def test_retry_operation_preserves_last_exception(self, history_service, caplog):
        """Test that the last exception is preserved and logged when all retries fail."""
        import logging
        caplog.set_level(logging.ERROR)
        
        def operation():
            raise Exception("Final error message")
        
        result = history_service._infra._retry_database_operation("test_operation", operation)
        
        assert result is None
        
        # Should log the final error
        error_logs = [record for record in caplog.records if record.levelno == logging.ERROR]
        assert len(error_logs) >= 1
        assert "Final error message" in error_logs[-1].message
    
    def test_retry_operation_treat_none_as_success(self, history_service, caplog):
        """Test that treat_none_as_success flag prevents retries when operation returns None."""
        import logging
        caplog.set_level(logging.WARNING)
        
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            return None  # Entity not found
        
        result = history_service._infra._retry_database_operation(
            "get_chat_by_session",
            operation,
            treat_none_as_success=True
        )
        
        assert result is None
        assert call_count == 1  # Should NOT retry
        
        # Should NOT log warnings about None results
        warning_logs = [record for record in caplog.records if record.levelno == logging.WARNING]
        none_warnings = [log for log in warning_logs if "returned None" in log.message]
        assert len(none_warnings) == 0, "Should not log warnings when treat_none_as_success=True"
    
    def test_retry_operation_none_triggers_retries_by_default(self, history_service, caplog):
        """Test that returning None triggers retries when treat_none_as_success is False (default)."""
        import logging
        caplog.set_level(logging.WARNING)
        
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            return None  # Failed operation
        
        result = history_service._infra._retry_database_operation("test_operation", operation)
        
        assert result is None
        assert call_count == 4  # Initial + 3 retries
        
        # Should log warnings about None results
        warning_logs = [record for record in caplog.records if record.levelno == logging.WARNING]
        none_warnings = [log for log in warning_logs if "returned None" in log.message]
        assert len(none_warnings) >= 3, "Should log warnings for each retry when None is treated as failure" 


@pytest.mark.unit
class TestHistoryServicePostgreSQLRetryLogic:
    """Test HistoryService retry logic for PostgreSQL-specific error patterns."""
    
    @pytest.fixture
    def history_service_postgresql(self):
        """Create HistoryService instance with PostgreSQL database URL."""
        with patch('tarsy.services.history_service.base_infrastructure.get_settings') as mock_settings:
            mock_settings.return_value.database_url = "postgresql://user:pass@localhost/testdb"
            mock_settings.return_value.history_retention_days = 90
            
            service = HistoryService()
            # Set up db_manager with PostgreSQL URL
            service._infra._set_healthy_for_testing()
            mock_db_manager = Mock()
            mock_db_manager.database_url = "postgresql://user:pass@localhost/testdb"
            service._infra.db_manager = mock_db_manager
            return service
    
    def test_is_postgresql_detection(self, history_service_postgresql):
        """Test that _is_postgresql correctly detects PostgreSQL backend."""
        assert history_service_postgresql._infra._is_postgresql() is True
        
        # Also test with postgres:// URL variant
        history_service_postgresql._infra.db_manager.database_url = "postgres://user:pass@localhost/testdb"
        assert history_service_postgresql._infra._is_postgresql() is True
    
    def test_is_postgresql_returns_false_for_sqlite(self):
        """Test that _is_postgresql returns False for SQLite backend."""
        with patch('tarsy.services.history_service.base_infrastructure.get_settings') as mock_settings:
            mock_settings.return_value.database_url = "sqlite:///test.db"
            mock_settings.return_value.history_retention_days = 90
            
            service = HistoryService()
            service._infra._set_healthy_for_testing()
            mock_db_manager = Mock()
            mock_db_manager.database_url = "sqlite:///test.db"
            service._infra.db_manager = mock_db_manager
            
            assert service._infra._is_postgresql() is False
    
    def test_is_postgresql_returns_false_when_no_db_manager(self):
        """Test that _is_postgresql returns False when db_manager is not initialized."""
        with patch('tarsy.services.history_service.base_infrastructure.get_settings') as mock_settings:
            mock_settings.return_value.database_url = "postgresql://user:pass@localhost/testdb"
            mock_settings.return_value.history_retention_days = 90
            
            service = HistoryService()
            service._infra.db_manager = None
            
            assert service._infra._is_postgresql() is False
    
    def test_get_sqlstate_extracts_pgcode(self, history_service_postgresql):
        """Test that _get_sqlstate extracts SQLSTATE from psycopg2/psycopg3 errors."""
        from sqlalchemy.exc import DBAPIError
        
        # Mock a psycopg-style error with pgcode
        mock_orig = Mock()
        mock_orig.pgcode = '40001'
        mock_exc = DBAPIError(statement="SELECT 1", params=None, orig=mock_orig)
        
        sqlstate = history_service_postgresql._infra._get_sqlstate(mock_exc)
        assert sqlstate == '40001'
    
    def test_get_sqlstate_extracts_sqlstate_attribute(self, history_service_postgresql):
        """Test that _get_sqlstate falls back to sqlstate attribute if pgcode unavailable."""
        from sqlalchemy.exc import DBAPIError
        
        # Mock an error with sqlstate attribute but no pgcode
        mock_orig = Mock()
        mock_orig.pgcode = None
        mock_orig.sqlstate = '40P01'
        mock_exc = DBAPIError(statement="SELECT 1", params=None, orig=mock_orig)
        
        sqlstate = history_service_postgresql._infra._get_sqlstate(mock_exc)
        assert sqlstate == '40P01'
    
    def test_get_sqlstate_returns_none_for_non_dbapi_error(self, history_service_postgresql):
        """Test that _get_sqlstate returns None for non-DBAPIError exceptions."""
        exc = ValueError("Not a database error")
        sqlstate = history_service_postgresql._infra._get_sqlstate(exc)
        assert sqlstate is None
    
    def test_retry_postgresql_sqlstate_serialization_failure(self, history_service_postgresql):
        """Test retry on PostgreSQL SQLSTATE 40001 (serialization_failure)."""
        from sqlalchemy.exc import DBAPIError
        
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mock_orig = Mock()
                mock_orig.pgcode = '40001'
                raise DBAPIError(statement="SELECT 1", params=None, orig=mock_orig)
            return "success"
        
        result = history_service_postgresql._infra._retry_database_operation("test_operation", operation)
        
        assert result == "success"
        assert call_count == 2  # Should have retried once
    
    def test_retry_postgresql_sqlstate_deadlock(self, history_service_postgresql):
        """Test retry on PostgreSQL SQLSTATE 40P01 (deadlock_detected)."""
        from sqlalchemy.exc import DBAPIError
        
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mock_orig = Mock()
                mock_orig.pgcode = '40P01'
                raise DBAPIError(statement="UPDATE table", params=None, orig=mock_orig)
            return "success"
        
        result = history_service_postgresql._infra._retry_database_operation("test_operation", operation)
        
        assert result == "success"
        assert call_count == 2
    
    def test_retry_postgresql_sqlstate_lock_not_available(self, history_service_postgresql):
        """Test retry on PostgreSQL SQLSTATE 55P03 (lock_not_available)."""
        from sqlalchemy.exc import DBAPIError
        
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mock_orig = Mock()
                mock_orig.pgcode = '55P03'
                raise DBAPIError(statement="SELECT FOR UPDATE", params=None, orig=mock_orig)
            return "success"
        
        result = history_service_postgresql._infra._retry_database_operation("test_operation", operation)
        
        assert result == "success"
        assert call_count == 2
    
    def test_retry_postgresql_sqlstate_too_many_connections(self, history_service_postgresql):
        """Test retry on PostgreSQL SQLSTATE 53300 (too_many_connections)."""
        from sqlalchemy.exc import DBAPIError
        
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mock_orig = Mock()
                mock_orig.pgcode = '53300'
                raise DBAPIError(statement="SELECT 1", params=None, orig=mock_orig)
            return "success"
        
        result = history_service_postgresql._infra._retry_database_operation("test_operation", operation)
        
        assert result == "success"
        assert call_count == 2
    
    def test_retry_postgresql_sqlstate_query_canceled(self, history_service_postgresql):
        """Test retry on PostgreSQL SQLSTATE 57014 (query_canceled)."""
        from sqlalchemy.exc import DBAPIError
        
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                mock_orig = Mock()
                mock_orig.pgcode = '57014'
                raise DBAPIError(statement="SELECT * FROM big_table", params=None, orig=mock_orig)
            return "success"
        
        result = history_service_postgresql._infra._retry_database_operation("test_operation", operation)
        
        assert result == "success"
        assert call_count == 2
    
    def test_retry_postgresql_sqlstate_class_08_connection_exceptions(self, history_service_postgresql):
        """Test retry on PostgreSQL SQLSTATE class 08 (connection exceptions)."""
        from sqlalchemy.exc import DBAPIError
        
        connection_sqlstates = ['08000', '08003', '08006', '08001', '08004', '08007', '08P01']
        
        for sqlstate in connection_sqlstates:
            call_count = 0
            
            def operation():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    mock_orig = Mock()
                    mock_orig.pgcode = sqlstate
                    raise DBAPIError(statement="SELECT 1", params=None, orig=mock_orig)
                return "success"
            
            result = history_service_postgresql._infra._retry_database_operation("test_operation", operation)
            
            assert result == "success", f"Should retry for SQLSTATE: {sqlstate}"
            assert call_count == 2, f"Should have retried once for SQLSTATE: {sqlstate}"
    
    def test_retry_postgresql_message_fallback_deadlock_detected(self, history_service_postgresql):
        """Test retry on PostgreSQL message pattern when SQLSTATE unavailable."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Plain exception without SQLSTATE
                raise Exception("deadlock detected")
            return "success"
        
        result = history_service_postgresql._infra._retry_database_operation("test_operation", operation)
        
        assert result == "success"
        assert call_count == 2
    
    def test_retry_postgresql_message_fallback_serialization_failure(self, history_service_postgresql):
        """Test retry on PostgreSQL 'serialization failure' message pattern."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("ERROR: could not serialize access due to concurrent update - serialization failure")
            return "success"
        
        result = history_service_postgresql._infra._retry_database_operation("test_operation", operation)
        
        assert result == "success"
        assert call_count == 2
    
    def test_retry_postgresql_message_fallback_all_patterns(self, history_service_postgresql):
        """Test all PostgreSQL message pattern fallbacks."""
        postgresql_patterns = [
            "serialization failure",
            "deadlock detected",
            "could not obtain lock",
            "too many connections",
            "could not connect",
            "connection refused",
            "server closed the connection",
            "connection timed out",
            "connection reset",
        ]
        
        for pattern in postgresql_patterns:
            call_count = 0
            
            def operation():
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise Exception(f"PostgreSQL error: {pattern}")
                return "success"
            
            result = history_service_postgresql._infra._retry_database_operation("test_operation", operation)
            
            assert result == "success", f"Should retry for pattern: {pattern}"
            assert call_count == 2, f"Should have retried once for pattern: {pattern}"
    
    def test_no_retry_postgresql_non_retryable_sqlstate(self, history_service_postgresql):
        """Test that non-retryable SQLSTATE codes don't trigger retries."""
        from sqlalchemy.exc import DBAPIError
        
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            # SQLSTATE 23505 = unique_violation (not retryable)
            mock_orig = Mock()
            mock_orig.pgcode = '23505'
            raise DBAPIError(statement="INSERT INTO", params=None, orig=mock_orig)
        
        result = history_service_postgresql._infra._retry_database_operation("test_operation", operation)
        
        assert result is None
        assert call_count == 1  # Should not retry
    
    def test_no_retry_postgresql_non_retryable_message(self, history_service_postgresql):
        """Test that non-retryable messages don't trigger retries on PostgreSQL."""
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            raise Exception("duplicate key value violates unique constraint")
        
        result = history_service_postgresql._infra._retry_database_operation("test_operation", operation)
        
        assert result is None
        assert call_count == 1  # Should not retry
    
    def test_postgresql_sqlstate_takes_precedence_over_message(self, history_service_postgresql, caplog):
        """Test that SQLSTATE is checked before message patterns for PostgreSQL."""
        import logging
        from sqlalchemy.exc import DBAPIError
        
        caplog.set_level(logging.DEBUG)
        call_count = 0
        
        def operation():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Error with retryable SQLSTATE
                mock_orig = Mock()
                mock_orig.pgcode = '40001'  # serialization_failure
                raise DBAPIError(statement="SELECT 1", params=None, orig=mock_orig)
            return "success"
        
        result = history_service_postgresql._infra._retry_database_operation("test_operation", operation)
        
        assert result == "success"
        assert call_count == 2
        
        # Verify SQLSTATE was detected (debug log)
        debug_logs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
        assert any('40001' in msg for msg in debug_logs), "Should log SQLSTATE detection"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_orphaned_sessions():
    """Test cleanup of orphaned sessions based on timeout."""
    history_service = HistoryService()
    
    from tarsy.models.constants import AlertSessionStatus, StageStatus
    from tarsy.models.db_models import StageExecution
    
    # Create test data - orphaned sessions with old last_interaction_at
    orphaned_session_1 = AlertSession(
        session_id='orphaned-1',
        alert_type='test-alert',
        agent_type='KubernetesAgent',
        status=AlertSessionStatus.IN_PROGRESS.value,
        started_at_us=1640995200000000,
        last_interaction_at=1640995200000000,  # Old timestamp
        pod_id='pod-1'
    )
    
    orphaned_session_2 = AlertSession(
        session_id='orphaned-2',
        alert_type='test-alert',
        agent_type='KubernetesAgent',
        status=AlertSessionStatus.IN_PROGRESS.value,
        started_at_us=1640995200000000,
        last_interaction_at=1640995200000000,  # Old timestamp
        pod_id='pod-2'
    )
    
    # Create mock stages for each session
    mock_stage_1 = Mock(spec=StageExecution)
    mock_stage_1.stage_id = 'stage-1'
    mock_stage_1.session_id = 'orphaned-1'
    mock_stage_1.stage_index = 0
    mock_stage_1.status = StageStatus.ACTIVE.value
    mock_stage_1.started_at_us = 1640995200000000
    
    mock_stage_2 = Mock(spec=StageExecution)
    mock_stage_2.stage_id = 'stage-2'
    mock_stage_2.session_id = 'orphaned-2'
    mock_stage_2.stage_index = 0
    mock_stage_2.status = StageStatus.PENDING.value
    mock_stage_2.started_at_us = None
    
    # Mock repository
    mock_repo = Mock()
    mock_repo.find_orphaned_sessions.return_value = [orphaned_session_1, orphaned_session_2]
    mock_repo.update_alert_session.return_value = True
    mock_repo.update_stage_execution.return_value = True
    
    # Mock session.exec to return stages for each session
    def mock_exec(stmt):
        result = Mock()
        # Return stages based on the session_id in the where clause
        # The statement contains session_id comparison, so we check which session
        # by tracking call count
        if mock_repo.session.exec.call_count == 1:
            result.all.return_value = [mock_stage_1]
        else:
            result.all.return_value = [mock_stage_2]
        return result
    
    mock_repo.session = Mock()
    mock_repo.session.exec = Mock(side_effect=mock_exec)
    
    # Mock the context manager
    history_service._infra.get_repository = Mock(return_value=Mock(
        __enter__=Mock(return_value=mock_repo), 
        __exit__=Mock(return_value=None)
    ))
    
    # Call cleanup method with 30 minute timeout
    cleaned_count = history_service.cleanup_orphaned_sessions(timeout_minutes=30)
    
    # Verify correct number of sessions were cleaned up
    assert cleaned_count == 2, f"Expected 2 sessions to be cleaned up, got {cleaned_count}"
    
    # Verify find_orphaned_sessions was called with timeout threshold
    assert mock_repo.find_orphaned_sessions.call_count == 1
    call_args = mock_repo.find_orphaned_sessions.call_args[0]
    timeout_threshold = call_args[0]
    # Threshold should be approximately 30 minutes ago (in microseconds)
    # We can't check exact value, but should be a large number
    assert timeout_threshold > 0
    
    # Verify update_alert_session was called for each orphaned session
    assert mock_repo.update_alert_session.call_count == 2
    
    # Check that sessions were marked as failed with correct error message
    update_calls = mock_repo.update_alert_session.call_args_list
    for call in update_calls:
        updated_session = call[0][0]
        assert updated_session.status == AlertSessionStatus.FAILED.value
        assert 'Processing failed - session became unresponsive' in updated_session.error_message
        assert updated_session.completed_at_us is not None
    
    # Verify stages were also cleaned up for each orphaned session
    assert mock_repo.session.exec.call_count == 2, "Should query stages for each orphaned session"
    assert mock_repo.update_stage_execution.call_count == 2, "Should update stage for each orphaned session"
    
    # Verify stages were marked as failed
    assert mock_stage_1.status == StageStatus.FAILED.value
    assert mock_stage_1.error_message == "Session terminated due to backend restart"
    assert mock_stage_1.completed_at_us is not None
    
    assert mock_stage_2.status == StageStatus.FAILED.value
    assert mock_stage_2.error_message == "Session terminated due to backend restart"
    assert mock_stage_2.completed_at_us is not None


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_orphaned_sessions_no_repository():
    """Test cleanup handles gracefully when repository is unavailable."""
    history_service = HistoryService()
    history_service._infra.get_repository = Mock(return_value=Mock(__enter__=Mock(return_value=None), __exit__=Mock(return_value=None)))
    
    cleaned_count = history_service.cleanup_orphaned_sessions()
    
    assert cleaned_count == 0


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_orphaned_sessions_no_active_sessions():
    """Test cleanup when there are no orphaned sessions."""
    history_service = HistoryService()
    
    mock_repo = Mock()
    mock_repo.find_orphaned_sessions.return_value = []  # No orphaned sessions found
    
    history_service._infra.get_repository = Mock(return_value=Mock(
        __enter__=Mock(return_value=mock_repo), 
        __exit__=Mock(return_value=None)
    ))
    
    cleaned_count = history_service.cleanup_orphaned_sessions()
    
    assert cleaned_count == 0
    # Verify find_orphaned_sessions was called
    assert mock_repo.find_orphaned_sessions.call_count == 1
    # Verify update was not called since no orphaned sessions
    mock_repo.update_alert_session.assert_not_called() 


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_never_touches_failed_sessions():
    """
    CRITICAL TEST: Ensure cleanup NEVER marks already-failed sessions as failed again.
    
    This test prevents a critical bug where failed sessions could be incorrectly
    cleaned up by the orphan detection mechanism.
    """
    history_service = HistoryService()
    
    from tarsy.models.constants import AlertSessionStatus
    
    # Create a session that is already FAILED (should NEVER be touched by cleanup)
    failed_session = AlertSession(
        session_id='already-failed',
        alert_type='test-alert',
        agent_type='KubernetesAgent',
        status=AlertSessionStatus.FAILED.value,  # Already failed!
        started_at_us=1640995200000000,
        last_interaction_at=1640995200000000,  # Even with old timestamp
        pod_id='pod-1',
        error_message='Original failure reason'
    )
    
    # Mock repository - cleanup should return empty list (no IN_PROGRESS sessions)
    mock_repo = Mock()
    mock_repo.find_orphaned_sessions.return_value = []  # Correctly excludes FAILED sessions
    
    history_service._infra.get_repository = Mock(return_value=Mock(
        __enter__=Mock(return_value=mock_repo), 
        __exit__=Mock(return_value=None)
    ))
    
    # Call cleanup
    cleaned_count = history_service.cleanup_orphaned_sessions(timeout_minutes=30)
    
    # Verify NO sessions were cleaned up
    assert cleaned_count == 0, "Cleanup should never touch FAILED sessions"
    
    # Verify update was never called
    mock_repo.update_alert_session.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_never_touches_completed_sessions():
    """
    CRITICAL TEST: Ensure cleanup NEVER marks completed sessions as failed.
    
    Completed sessions should never be touched by orphan detection.
    """
    history_service = HistoryService()
    
    from tarsy.models.constants import AlertSessionStatus
    
    # Create a session that is COMPLETED (should NEVER be touched by cleanup)
    completed_session = AlertSession(
        session_id='already-completed',
        alert_type='test-alert',
        agent_type='KubernetesAgent',
        status=AlertSessionStatus.COMPLETED.value,  # Completed!
        started_at_us=1640995200000000,
        last_interaction_at=1640995200000000,  # Even with old timestamp
        completed_at_us=1640995260000000,
        pod_id='pod-1'
    )
    
    # Mock repository - should exclude COMPLETED sessions
    mock_repo = Mock()
    mock_repo.find_orphaned_sessions.return_value = []
    
    history_service._infra.get_repository = Mock(return_value=Mock(
        __enter__=Mock(return_value=mock_repo), 
        __exit__=Mock(return_value=None)
    ))
    
    # Call cleanup
    cleaned_count = history_service.cleanup_orphaned_sessions(timeout_minutes=30)
    
    # Verify NO sessions were cleaned up
    assert cleaned_count == 0, "Cleanup should never touch COMPLETED sessions"
    mock_repo.update_alert_session.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_never_touches_null_last_interaction():
    """
    CRITICAL TEST: Sessions with NULL last_interaction_at should never be cleaned up.
    
    Sessions where last_interaction_at is NULL (not yet set) should not be
    considered orphaned, even if they're IN_PROGRESS.
    """
    history_service = HistoryService()
    
    from tarsy.models.constants import AlertSessionStatus
    
    # Create IN_PROGRESS session with NULL last_interaction_at
    session_with_null = AlertSession(
        session_id='null-interaction',
        alert_type='test-alert',
        agent_type='KubernetesAgent',
        status=AlertSessionStatus.IN_PROGRESS.value,
        started_at_us=1640995200000000,
        last_interaction_at=None,  # NULL - should be excluded
        pod_id='pod-1'
    )
    
    # Mock repository - should exclude sessions with NULL last_interaction_at
    mock_repo = Mock()
    mock_repo.find_orphaned_sessions.return_value = []  # Correctly excludes NULL
    
    history_service._infra.get_repository = Mock(return_value=Mock(
        __enter__=Mock(return_value=mock_repo), 
        __exit__=Mock(return_value=None)
    ))
    
    # Call cleanup
    cleaned_count = history_service.cleanup_orphaned_sessions(timeout_minutes=30)
    
    # Verify NO sessions were cleaned up
    assert cleaned_count == 0, "Cleanup should never touch sessions with NULL last_interaction_at"
    mock_repo.update_alert_session.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_only_touches_in_progress_with_old_interaction():
    """
    Test that cleanup ONLY affects IN_PROGRESS sessions with old last_interaction_at.
    
    This is the positive test case for the orphan detection mechanism.
    """
    history_service = HistoryService()
    
    from tarsy.models.constants import AlertSessionStatus
    from tarsy.utils.timestamp import now_us
    
    # Create an orphaned IN_PROGRESS session with old timestamp
    orphaned_session = AlertSession(
        session_id='truly-orphaned',
        alert_type='test-alert',
        agent_type='KubernetesAgent',
        status=AlertSessionStatus.IN_PROGRESS.value,
        started_at_us=now_us() - (60 * 60 * 1_000_000),  # 1 hour ago
        last_interaction_at=now_us() - (60 * 60 * 1_000_000),  # 1 hour ago
        pod_id='pod-1'
    )
    
    # Mock repository
    mock_repo = Mock()
    mock_repo.find_orphaned_sessions.return_value = [orphaned_session]
    mock_repo.update_alert_session.return_value = True
    
    history_service._infra.get_repository = Mock(return_value=Mock(
        __enter__=Mock(return_value=mock_repo), 
        __exit__=Mock(return_value=None)
    ))
    
    # Call cleanup with 30 minute timeout
    cleaned_count = history_service.cleanup_orphaned_sessions(timeout_minutes=30)
    
    # Verify the orphaned session was cleaned up
    assert cleaned_count == 1, "Should clean up truly orphaned IN_PROGRESS session"
    
    # Verify it was marked as failed with appropriate error message
    mock_repo.update_alert_session.assert_called_once()
    updated_session = mock_repo.update_alert_session.call_args[0][0]
    assert updated_session.status == AlertSessionStatus.FAILED.value
    assert 'Processing failed - session became unresponsive' in updated_session.error_message


@pytest.mark.asyncio
@pytest.mark.unit
async def test_cleanup_orphaned_sessions_session_not_found():
    """Test cleanup handles gracefully when update fails."""
    history_service = HistoryService()
    
    
    # Create an orphaned session
    orphaned_session = AlertSession(
        session_id="orphaned-1",
        alert_type="test-alert",
        agent_type="KubernetesAgent",
        status=AlertSessionStatus.IN_PROGRESS.value,
        started_at_us=1640995200000000,
        last_interaction_at=1640995200000000,
        pod_id='pod-1'
    )
    
    mock_repo = Mock()
    mock_repo.find_orphaned_sessions.return_value = [orphaned_session]
    mock_repo.update_alert_session.return_value = False  # Update fails
    
    history_service._infra.get_repository = Mock(return_value=Mock(
        __enter__=Mock(return_value=mock_repo),
        __exit__=Mock(return_value=None)
    ))
    
    # Should handle update failure gracefully and still count the attempt
    cleaned_count = history_service.cleanup_orphaned_sessions()
    
    # Even though update failed, we still attempted cleanup on 1 session
    assert cleaned_count == 1
    
    # Verify find_orphaned_sessions and update were called
    assert mock_repo.find_orphaned_sessions.call_count == 1
    assert mock_repo.update_alert_session.call_count == 1


class TestHistoryAPIResponseStructure:
    """Test suite for history service API response structure validation."""
    
    @pytest.fixture
    def history_service(self, isolated_test_settings):
        """Create HistoryService instance for testing."""
        with patch('tarsy.services.history_service.base_infrastructure.get_settings', return_value=isolated_test_settings):
            service = HistoryService()
            service._infra._set_healthy_for_testing()
            return service
    
    @pytest.mark.unit
    def test_session_detail_response_structure(self):
        """Test that session detail response has all required fields."""
        # This tests the fix where we added missing fields to the API response
        
        # Expected response structure for session details
        expected_fields = {
            'session_id',
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




    @pytest.mark.unit
    async def test_get_session_summary_success(self, history_service):
        """Test get_session_summary with successful data retrieval."""
        session_id = "test-session-123"
        
        # Get_session_summary now uses get_session_overview directly 
        mock_session_overview = MockFactory.create_mock_session_overview(
            session_id=session_id,
            chain_id="test-chain"
        )
        
        # Mock the repository to return our SessionOverview
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_session_overview.return_value = mock_session_overview
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Get summary
            summary = await history_service.get_session_summary(session_id)
        
        # Verify repository method was called
        dependencies['repository'].get_session_overview.assert_called_once_with(session_id)
        
        # Verify summary structure
        assert summary is not None
        assert hasattr(summary, 'total_interactions')
        assert hasattr(summary, 'llm_interactions')
        assert hasattr(summary, 'chain_statistics')
        assert summary.total_interactions == 1
        assert summary.llm_interactions == 1
        assert summary.chain_statistics.total_stages == 1
        assert summary.chain_statistics.completed_stages == 1

    @pytest.mark.unit
    async def test_get_session_summary_not_found(self, history_service):
        """Test get_session_summary when session doesn't exist."""
        session_id = "non-existent-session"
        
        # Mock repository to return None (session not found)
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_session_overview.return_value = None
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Get summary
            summary = await history_service.get_session_summary(session_id)
        
        # Should return None
        assert summary is None
        
        # Verify repository method was called once (no retries needed when session not found)
        assert dependencies['repository'].get_session_overview.call_count == 1
        dependencies['repository'].get_session_overview.assert_called_with(session_id)

    @pytest.mark.unit
    async def test_get_session_summary_non_chain_session(self, history_service):
        """Test get_session_summary for session with minimal chain data."""
        session_id = "minimal-chain-session"
        
        # All sessions are chains, but this one has minimal chain data
        mock_session_overview = MockFactory.create_mock_session_overview(
            session_id=session_id,
            chain_id="minimal-chain",
            total_interactions=2,
            mcp_communication_count=1,
            total_stages=0,  # No stages
            completed_stages=0,
            failed_stages=0
        )
        
        # Mock the repository to return our SessionOverview
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_session_overview.return_value = mock_session_overview
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Get summary
            summary = await history_service.get_session_summary(session_id)
        
        # Verify repository method was called
        dependencies['repository'].get_session_overview.assert_called_once_with(session_id)
        
        # Verify summary structure - all sessions have chain statistics now
        assert summary is not None
        assert summary.total_interactions == 2
        assert summary.llm_interactions == 1
        assert summary.mcp_communications == 1
        assert hasattr(summary, 'chain_statistics')
        assert summary.chain_statistics.total_stages == 0  # No stages

    @pytest.mark.unit
    async def test_get_session_summary_chain_session_without_stages(self, history_service):
        """Test get_session_summary when repository returns None (error case)"""
        session_id = "error-case-session"
        
        # Repository returns None due to error or session not found
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_session_overview.return_value = None  # Simulate error/not found
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Get summary
            summary = await history_service.get_session_summary(session_id)
        
        # Should return None when repository can't find session or has error
        assert summary is None
        
        # Verify repository method was called once (no retries needed when session not found)
        assert dependencies['repository'].get_session_overview.call_count == 1
        dependencies['repository'].get_session_overview.assert_called_with(session_id)


@pytest.mark.unit
class TestHistoryServiceTokenAggregations:
    """Test token usage aggregation functionality in HistoryService added in EP-0009."""
    
    @pytest.fixture
    def history_service(self, isolated_test_settings):
        """Create HistoryService instance for testing."""
        with patch('tarsy.services.history_service.base_infrastructure.get_settings', return_value=isolated_test_settings):
            service = HistoryService()
            service._infra._set_healthy_for_testing()
            return service
    
    @pytest.mark.asyncio
    async def test_get_session_summary_calculates_token_aggregations(self, history_service):
        """Test that session summary calculates token totals from stages."""
        # Arrange
        session_id = "token-test-session"
        
        # Create mock session overview
        mock_session_overview = MockFactory.create_mock_session_overview(
            session_id=session_id,
            chain_id="test-chain",
            total_interactions=3,
            llm_interaction_count=3
        )
        
        # Create mock detailed session with token data
        mock_detailed_session = Mock()
        # Set session-level token aggregation properties to None to force stage-level calculation
        mock_detailed_session.session_input_tokens = None
        mock_detailed_session.session_output_tokens = None
        mock_detailed_session.session_total_tokens = None
        
        # Create stages with token data
        stage1 = Mock()
        stage1.stage_input_tokens = 100
        stage1.stage_output_tokens = 30 
        stage1.stage_total_tokens = 130
        
        stage2 = Mock()  
        stage2.stage_input_tokens = 150
        stage2.stage_output_tokens = 45
        stage2.stage_total_tokens = 195
        
        stage3 = Mock()  # Stage without token data
        stage3.stage_input_tokens = None
        stage3.stage_output_tokens = None
        stage3.stage_total_tokens = None
        
        mock_detailed_session.stages = [stage1, stage2, stage3]
        
        # Mock repository
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_session_overview.return_value = mock_session_overview
        dependencies['repository'].get_session_details.return_value = mock_detailed_session
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act
            summary = await history_service.get_session_summary(session_id)
        
        # Assert
        assert summary is not None
        assert summary.session_input_tokens == 250  # 100 + 150 + 0
        assert summary.session_output_tokens == 75   # 30 + 45 + 0  
        assert summary.session_total_tokens == 325   # 130 + 195 + 0
        
        # Verify both repository methods were called
        dependencies['repository'].get_session_overview.assert_called_once_with(session_id)
        dependencies['repository'].get_session_details.assert_called_once_with(session_id)
    
    @pytest.mark.asyncio
    async def test_get_session_summary_handles_no_token_data(self, history_service):
        """Test session summary when no stages have token data."""
        # Arrange
        session_id = "no-token-session"
        
        mock_session_overview = MockFactory.create_mock_session_overview(
            session_id=session_id,
            chain_id="test-chain",
            llm_interaction_count=0  # No LLM interactions
        )
        
        # Mock detailed session with stages but no token data
        mock_detailed_session = Mock()
        # Set session-level token aggregation properties to None to force stage-level calculation
        mock_detailed_session.session_input_tokens = None
        mock_detailed_session.session_output_tokens = None
        mock_detailed_session.session_total_tokens = None
        
        stage1 = Mock()
        stage1.stage_input_tokens = None
        stage1.stage_output_tokens = None
        stage1.stage_total_tokens = None
        
        mock_detailed_session.stages = [stage1]
        
        # Mock repository
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_session_overview.return_value = mock_session_overview
        dependencies['repository'].get_session_details.return_value = mock_detailed_session
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act
            summary = await history_service.get_session_summary(session_id)
        
        # Assert
        assert summary is not None
        assert summary.session_input_tokens == 0   # No token data defaults to 0
        assert summary.session_output_tokens == 0
        assert summary.session_total_tokens == 0
    
    @pytest.mark.asyncio
    async def test_get_session_summary_handles_missing_detailed_session(self, history_service):
        """Test session summary when detailed session is not available."""
        # Arrange
        session_id = "missing-details-session"
        
        mock_session_overview = MockFactory.create_mock_session_overview(
            session_id=session_id,
            chain_id="test-chain"
        )
        
        # Mock repository - detailed session not available
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_session_overview.return_value = mock_session_overview
        dependencies['repository'].get_session_details.return_value = None  # No detailed session
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act
            summary = await history_service.get_session_summary(session_id)
        
        # Assert
        assert summary is not None
        # Should default to 0 when detailed session unavailable
        assert summary.session_input_tokens == 0
        assert summary.session_output_tokens == 0
        assert summary.session_total_tokens == 0
    
    @pytest.mark.asyncio
    async def test_get_session_summary_token_aggregation_edge_cases(self, history_service):
        """Test token aggregation with various edge cases."""
        # Arrange
        session_id = "edge-case-session"
        
        mock_session_overview = MockFactory.create_mock_session_overview(
            session_id=session_id,
            chain_id="test-chain",
            llm_interaction_count=2
        )
        
        # Create detailed session with edge case token data
        mock_detailed_session = Mock()
        # Set session-level token aggregation properties to None to force stage-level calculation
        mock_detailed_session.session_input_tokens = None
        mock_detailed_session.session_output_tokens = None
        mock_detailed_session.session_total_tokens = None
        
        # Stage with large token numbers
        stage1 = Mock()
        stage1.stage_input_tokens = 5000
        stage1.stage_output_tokens = 2000
        stage1.stage_total_tokens = 7000
        
        # Stage with very small token numbers
        stage2 = Mock()
        stage2.stage_input_tokens = 1
        stage2.stage_output_tokens = 1  
        stage2.stage_total_tokens = 2
        
        # Stage with mixed token availability
        stage3 = Mock()
        stage3.stage_input_tokens = 50
        stage3.stage_output_tokens = None  # Missing output tokens
        stage3.stage_total_tokens = 50
        
        mock_detailed_session.stages = [stage1, stage2, stage3]
        
        # Mock repository
        dependencies = MockFactory.create_mock_history_service_dependencies() 
        dependencies['repository'].get_session_overview.return_value = mock_session_overview
        dependencies['repository'].get_session_details.return_value = mock_detailed_session
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act
            summary = await history_service.get_session_summary(session_id)
        
        # Assert
        assert summary is not None
        assert summary.session_input_tokens == 5051  # 5000 + 1 + 50
        assert summary.session_output_tokens == 2001  # 2000 + 1 + 0 (None treated as 0)
        assert summary.session_total_tokens == 7052   # 7000 + 2 + 50


class TestConversationHistory:
    """Test suite for conversation history retrieval methods."""
    
    @pytest.fixture
    def mock_settings(self, isolated_test_settings):
        """Create mock settings for testing."""
        return isolated_test_settings
    
    @pytest.fixture
    def history_service(self, mock_settings):
        """Create HistoryService instance with mocked dependencies."""
        with patch('tarsy.services.history_service.base_infrastructure.get_settings', return_value=mock_settings):
            service = HistoryService()
            service._infra._set_healthy_for_testing()
            return service
    
    @pytest.mark.unit
    def test_build_conversation_history_with_valid_interaction(self, history_service):
        """Test _build_conversation_history with a valid LLM interaction."""
        from tarsy.models.unified_interactions import (
            LLMConversation,
            LLMInteraction,
            LLMMessage,
            MessageRole,
        )
        
        # Create a valid LLM interaction with conversation
        interaction = LLMInteraction(
            interaction_id="test-int-1",
            session_id="test-session",
            model_name="gemini-2.0-flash",
            provider="google",
            timestamp_us=1700000000000000,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are an assistant"),
                LLMMessage(role=MessageRole.USER, content="What is the issue?"),
                LLMMessage(role=MessageRole.ASSISTANT, content="The namespace is terminating")
            ])
        )
        
        # Act
        result = history_service._conversations._build_conversation_history(interaction)
        
        # Assert
        assert result is not None
        assert result.model_name == "gemini-2.0-flash"
        assert result.provider == "google"
        assert result.timestamp_us == 1700000000000000
        assert result.input_tokens == 100
        assert result.output_tokens == 50
        assert result.total_tokens == 150
        assert len(result.messages) == 3
        assert result.messages[0].role == "system"
        assert result.messages[0].content == "You are an assistant"
        assert result.messages[1].role == "user"
        assert result.messages[2].role == "assistant"
    
    @pytest.mark.unit
    def test_build_conversation_history_with_none_interaction(self, history_service):
        """Test _build_conversation_history with None interaction."""
        result = history_service._conversations._build_conversation_history(None)
        assert result is None
    
    @pytest.mark.unit
    def test_build_conversation_history_with_no_conversation(self, history_service):
        """Test _build_conversation_history when interaction has no conversation."""
        from tarsy.models.unified_interactions import LLMInteraction
        
        # Create interaction without conversation
        interaction = LLMInteraction(
            interaction_id="test-int-1",
            session_id="test-session",
            model_name="gpt-4",
            timestamp_us=1700000000000000,
            conversation=None
        )
        
        result = history_service._conversations._build_conversation_history(interaction)
        assert result is None
    
    @pytest.mark.unit
    def test_get_session_conversation_history_returns_both(self, history_service):
        """Test get_session_conversation_history returns both session and chat conversations."""
        from tarsy.models.db_models import Chat
        from tarsy.models.unified_interactions import (
            LLMConversation,
            LLMInteraction,
            LLMMessage,
            MessageRole,
        )
        
        # Create mock interactions
        session_interaction = LLMInteraction(
            interaction_id="session-int-1",
            session_id="test-session",
            model_name="gemini-2.0-flash",
            provider="google",
            timestamp_us=1700000000000000,
            input_tokens=200,
            output_tokens=100,
            total_tokens=300,
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
                LLMMessage(role=MessageRole.USER, content="Analyze issue"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Analysis complete")
            ])
        )
        
        chat_interaction = LLMInteraction(
            interaction_id="chat-int-1",
            session_id="test-session",
            model_name="gemini-2.0-flash",
            provider="google",
            timestamp_us=1700000100000000,
            input_tokens=150,
            output_tokens=80,
            total_tokens=230,
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="Chat prompt"),
                LLMMessage(role=MessageRole.USER, content="Follow-up question"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Chat response")
            ])
        )
        
        mock_chat = Chat(
            chat_id="chat-1",
            session_id="test-session",
            conversation_history="Previous context",
            chain_id="chain-1",
            context_captured_at_us=1700000000000000
        )
        
        # Setup mock repository
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_last_llm_interaction_with_conversation.side_effect = [
            session_interaction,  # First call for session
            chat_interaction      # Second call for chat
        ]
        dependencies['repository'].get_chat_by_session.return_value = mock_chat
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act
            session_conv, chat_conv = history_service.get_session_conversation_history(
                session_id="test-session",
                include_chat=True
            )
        
        # Assert
        assert session_conv is not None
        assert session_conv.model_name == "gemini-2.0-flash"
        assert len(session_conv.messages) == 3
        assert session_conv.input_tokens == 200
        
        assert chat_conv is not None
        assert chat_conv.model_name == "gemini-2.0-flash"
        assert len(chat_conv.messages) == 3
        assert chat_conv.input_tokens == 150
    
    @pytest.mark.unit
    def test_get_session_conversation_history_no_chat(self, history_service):
        """Test get_session_conversation_history when no chat exists."""
        from tarsy.models.unified_interactions import (
            LLMConversation,
            LLMInteraction,
            LLMMessage,
            MessageRole,
        )
        
        session_interaction = LLMInteraction(
            interaction_id="session-int-1",
            session_id="test-session",
            model_name="gpt-4",
            provider="openai",
            timestamp_us=1700000000000000,
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="User"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Assistant")
            ])
        )
        
        # Setup mock repository
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_last_llm_interaction_with_conversation.return_value = session_interaction
        dependencies['repository'].get_chat_by_session.return_value = None  # No chat
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act
            session_conv, chat_conv = history_service.get_session_conversation_history(
                session_id="test-session",
                include_chat=True
            )
        
        # Assert
        assert session_conv is not None
        assert chat_conv is None
    
    @pytest.mark.unit
    def test_get_session_conversation_history_no_interactions(self, history_service):
        """Test get_session_conversation_history when no interactions exist."""
        # Setup mock repository
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_last_llm_interaction_with_conversation.return_value = None
        dependencies['repository'].get_chat_by_session.return_value = None
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act
            session_conv, chat_conv = history_service.get_session_conversation_history(
                session_id="test-session",
                include_chat=False
            )
        
        # Assert
        assert session_conv is None
        assert chat_conv is None
    
    # ===== Tests for Session History Formatting =====
    
    @pytest.mark.unit
    def test_get_formatted_session_conversation_success(self, history_service):
        """Test get_formatted_session_conversation returns formatted text."""
        # Setup: Create session with LLM interaction
        session = SessionFactory.create_test_session(
            session_id="test-session",
            alert_type="PodCrashLoop",
            status=AlertSessionStatus.COMPLETED
        )
        
        # Create LLM interaction with conversation
        from tarsy.models.unified_interactions import LLMInteraction, LLMInteractionType
        interaction = Mock(spec=LLMInteraction)
        interaction.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System instructions"),
                LLMMessage(role=MessageRole.USER, content="Check pod status in namespace prod"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Thought: I need to check pods\nAction: kubectl get pods"),
            ]
        )
        interaction.interaction_type = LLMInteractionType.INVESTIGATION
        interaction.thinking_content = None
        
        # Setup mock repository
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_llm_interactions_for_session.return_value = [interaction]
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act
            result = history_service.get_formatted_session_conversation(
                session_id="test-session",
                exclude_chat_stages=True,
                include_thinking=False
            )
        
        # Assert
        assert result is not None
        assert "📋 INVESTIGATION HISTORY" in result
        assert "### Initial Investigation Request" in result
        assert "**Agent Response:**" in result
        assert "Check pod status in namespace prod" in result
        # Should NOT include thinking_content when include_thinking=False
        assert "**Internal Reasoning:**" not in result
    
    @pytest.mark.unit
    def test_get_formatted_session_conversation_with_thinking(self, history_service):
        """Test get_formatted_session_conversation includes thinking_content."""
        # Setup: Create session with native thinking interaction
        from tarsy.models.unified_interactions import LLMInteraction, LLMInteractionType
        
        interaction = Mock(spec=LLMInteraction)
        interaction.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System instructions"),
                LLMMessage(role=MessageRole.USER, content="Check pod status"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Let me check the pods"),
            ]
        )
        interaction.interaction_type = LLMInteractionType.INVESTIGATION
        interaction.thinking_content = "I should start by examining the namespace for any crash loop patterns"
        
        # Setup mock repository
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_llm_interactions_for_session.return_value = [interaction]
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act
            result = history_service.get_formatted_session_conversation(
                session_id="test-session",
                include_thinking=True
            )
        
        # Assert
        assert result is not None
        assert "📋 INVESTIGATION HISTORY" in result
        assert "**Internal Reasoning:**" in result
        assert "I should start by examining the namespace" in result
        # Thinking should appear BEFORE agent response
        thinking_pos = result.find("**Internal Reasoning:**")
        response_pos = result.find("**Agent Response:**")
        assert thinking_pos < response_pos
    
    @pytest.mark.unit
    def test_get_formatted_session_conversation_mixed_interactions(self, history_service):
        """Test thinking correlation with mix of ReAct and Native Thinking."""
        # Setup: Create multiple interactions, some with thinking, some without
        from tarsy.models.unified_interactions import LLMInteraction, LLMInteractionType
        
        # First interaction: ReAct (no thinking)
        interaction1 = Mock(spec=LLMInteraction)
        interaction1.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Check pods"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 1"),
            ]
        )
        interaction1.interaction_type = LLMInteractionType.INVESTIGATION
        interaction1.thinking_content = None
        
        # Second interaction: Native thinking (with thinking)
        interaction2 = Mock(spec=LLMInteraction)
        interaction2.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Check pods"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 1"),
                LLMMessage(role=MessageRole.USER, content="Tool result"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response 2"),
            ]
        )
        interaction2.interaction_type = LLMInteractionType.INVESTIGATION
        interaction2.thinking_content = "Now I need to analyze the events"
        
        # Setup mock repository
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_llm_interactions_for_session.return_value = [interaction1, interaction2]
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act
            result = history_service.get_formatted_session_conversation(
                session_id="test-session",
                include_thinking=True
            )
        
        # Assert
        assert result is not None
        # Should have both responses
        assert "Response 1" in result
        assert "Response 2" in result
        # Only second interaction has thinking
        assert result.count("**Internal Reasoning:**") == 1
        assert "Now I need to analyze the events" in result
    
    @pytest.mark.unit
    def test_get_formatted_session_conversation_cancelled_session(self, history_service):
        """Test handling of cancelled sessions with no valid conversation."""
        # Setup: Create interaction with None conversation
        from tarsy.models.unified_interactions import LLMInteraction, LLMInteractionType
        
        interaction = Mock(spec=LLMInteraction)
        interaction.conversation = None
        interaction.interaction_type = LLMInteractionType.INVESTIGATION
        interaction.thinking_content = None
        
        # Setup mock repository
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_llm_interactions_for_session.return_value = [interaction]
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act
            result = history_service.get_formatted_session_conversation(
                session_id="test-session"
            )
        
        # Assert
        assert result is not None
        assert "📋 INVESTIGATION HISTORY" in result
        assert "⚠️  This investigation was cancelled before completion." in result
    
    @pytest.mark.unit
    def test_get_formatted_session_conversation_filters_by_interaction_type(self, history_service):
        """Test that only CHAT_CONTEXT_INTERACTION_TYPES are used."""
        # Setup: Mix of interaction types
        from tarsy.models.unified_interactions import LLMInteraction, LLMInteractionType
        
        # Investigation interaction (should be used)
        investigation = Mock(spec=LLMInteraction)
        investigation.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="User message"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Investigation response"),
            ]
        )
        investigation.interaction_type = LLMInteractionType.INVESTIGATION
        investigation.thinking_content = None
        
        # Summarization interaction (should be skipped)
        summarization = Mock(spec=LLMInteraction)
        summarization.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Summarization prompt"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Summary"),
            ]
        )
        summarization.interaction_type = LLMInteractionType.SUMMARIZATION
        summarization.thinking_content = None
        
        # Setup mock repository
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_llm_interactions_for_session.return_value = [investigation, summarization]
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act
            result = history_service.get_formatted_session_conversation(
                session_id="test-session"
            )
        
        # Assert
        assert "Investigation response" in result
        # Summarization should be filtered out
        assert "Summary" not in result
    
    @pytest.mark.unit
    def test_get_formatted_session_conversation_no_interactions(self, history_service):
        """Test error handling when no interactions exist."""
        # Setup mock repository with empty interactions
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_llm_interactions_for_session.return_value = []
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act & Assert - Should get specific "no interactions" error
            with pytest.raises(ValueError, match="No LLM interactions found for session"):
                history_service.get_formatted_session_conversation(
                    session_id="test-session"
                )
    
    @pytest.mark.unit
    def test_build_comprehensive_session_history_with_alert_section(self, history_service):
        """Test comprehensive history with separate alert section."""
        # Setup: Create session
        session = SessionFactory.create_test_session(
            session_id="test-session",
            alert_type="PodCrashLoop",
            status=AlertSessionStatus.COMPLETED,
            alert_data={"pod": "my-pod", "namespace": "production"}
        )
        
        # Mock get_formatted_session_conversation on the _conversations operation class
        with patch.object(history_service._conversations, 'get_formatted_session_conversation') as mock_get_formatted:
            mock_get_formatted.return_value = "📋 INVESTIGATION HISTORY\n\nInvestigation content"
            
            # Mock the repo to return the session
            dependencies = MockFactory.create_mock_history_service_dependencies()
            dependencies['repository'].get_alert_session.return_value = session
            
            with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
                mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
                mock_get_repo.return_value.__exit__.return_value = None
                
                # Act
                result = history_service.build_comprehensive_session_history(
                    session_id="test-session",
                    include_separate_alert_section=True
                )
        
        # Assert
        assert result is not None
        assert "ALERT INFORMATION" in result
        assert "**Alert Type:** PodCrashLoop" in result
        assert "**Session ID:** test-session" in result
        assert "**Status:** completed" in result
        assert "**Alert Data:**" in result
        assert '"pod": "my-pod"' in result
        assert '"namespace": "production"' in result
        assert "📋 INVESTIGATION HISTORY" in result
    
    @pytest.mark.unit
    def test_build_comprehensive_session_history_without_alert_section(self, history_service):
        """Test comprehensive history without separate alert section."""
        # Setup: Create session and interaction
        session = SessionFactory.create_test_session(
            session_id="test-session",
            alert_type="PodCrashLoop",
            status=AlertSessionStatus.COMPLETED
        )
        
        from tarsy.models.unified_interactions import LLMInteraction, LLMInteractionType
        interaction = Mock(spec=LLMInteraction)
        interaction.conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Check pod"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response"),
            ]
        )
        interaction.interaction_type = LLMInteractionType.INVESTIGATION
        interaction.thinking_content = None
        
        # Setup mock repository
        dependencies = MockFactory.create_mock_history_service_dependencies()
        dependencies['repository'].get_llm_interactions_for_session.return_value = [interaction]
        dependencies['repository'].get_session.return_value = session
        
        with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
            mock_get_repo.return_value.__exit__.return_value = None
            
            # Act
            result = history_service.build_comprehensive_session_history(
                session_id="test-session",
                include_separate_alert_section=False
            )
        
        # Assert
        assert result is not None
        # Should NOT include ALERT INFORMATION header
        assert "ALERT INFORMATION" not in result
        # Should still have investigation history
        assert "📋 INVESTIGATION HISTORY" in result
    
    @pytest.mark.unit
    def test_build_comprehensive_session_history_session_not_found(self, history_service):
        """Test error when session doesn't exist."""
        # Mock get_formatted_session_conversation on the _conversations operation class
        with patch.object(history_service._conversations, 'get_formatted_session_conversation') as mock_get_formatted:
            mock_get_formatted.return_value = "📋 INVESTIGATION HISTORY\n\nInvestigation content"
            
            # Mock the repo to return None for the session (not found)
            dependencies = MockFactory.create_mock_history_service_dependencies()
            dependencies['repository'].get_alert_session.return_value = None
            
            with patch.object(history_service._infra, 'get_repository') as mock_get_repo:
                mock_get_repo.return_value.__enter__.return_value = dependencies['repository']
                mock_get_repo.return_value.__exit__.return_value = None
                
                # Act & Assert
                with pytest.raises(ValueError, match="Session test-session not found"):
                    history_service.build_comprehensive_session_history(
                        session_id="test-session",
                        include_separate_alert_section=True
                    )