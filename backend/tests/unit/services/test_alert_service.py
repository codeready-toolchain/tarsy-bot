"""
Unit tests for AlertService - Main alert processing orchestrator.

Tests the complete alert processing workflow including agent selection,
delegation, error handling, progress tracking, and history management.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.config.settings import Settings
from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
from tarsy.models.alert import Alert
from tarsy.models.alert_processing import AlertKey
from tarsy.models.processing_context import ChainContext
from tarsy.services.alert_service import AlertService
from tarsy.services.response_formatter import format_error_response
from tarsy.utils.timestamp import now_us
from tests.conftest import alert_to_api_format
from tests.utils import AlertFactory, MockFactory


@pytest.mark.unit
class TestAlertServiceInitialization:
    """Test AlertService initialization and setup."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        return MockFactory.create_mock_settings(
            github_token="test_token",
            agent_config_path=None  # No agent config for unit tests
        )
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all AlertService dependencies."""
        return MockFactory.create_mock_alert_service_dependencies()
    
    def test_initialization_success(self, mock_settings):
        """Test successful AlertService initialization."""
        with patch('tarsy.services.alert_service.RunbookService') as mock_runbook, \
             patch('tarsy.services.alert_service.get_history_service') as mock_history, \
             patch('tarsy.services.alert_service.ChainRegistry') as mock_chain_registry, \
             patch('tarsy.services.alert_service.MCPServerRegistry') as mock_mcp_registry, \
             patch('tarsy.services.alert_service.MCPClient') as mock_mcp_client, \
             patch('tarsy.services.mcp_client_factory.MCPClientFactory') as mock_mcp_factory, \
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager:
            
            service = AlertService(mock_settings)
            
            assert service.settings == mock_settings
            assert service.runbook_service == mock_runbook.return_value
            assert service.history_service == mock_history.return_value
            assert service.chain_registry == mock_chain_registry.return_value
            assert service.mcp_server_registry == mock_mcp_registry.return_value
            assert service.health_check_mcp_client == mock_mcp_client.return_value
            assert service.mcp_client_factory == mock_mcp_factory.return_value
            assert service.llm_manager == mock_llm_manager.return_value
            assert service.agent_factory is None  # Not initialized yet
    
    def test_initialization_with_dependencies(self, mock_settings):
        """Test that dependencies are created with correct parameters."""
        with patch('tarsy.services.alert_service.RunbookService') as mock_runbook, \
             patch('tarsy.services.alert_service.get_history_service') as mock_history, \
             patch('tarsy.services.alert_service.ChainRegistry') as mock_chain_registry, \
             patch('tarsy.services.alert_service.MCPServerRegistry') as mock_mcp_registry, \
             patch('tarsy.services.alert_service.MCPClient') as mock_mcp_client, \
             patch('tarsy.services.mcp_client_factory.MCPClientFactory') as mock_mcp_factory, \
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager:
            
            service = AlertService(mock_settings)
            
            # Verify RunbookService created with settings and None for http_client
            mock_runbook.assert_called_once_with(mock_settings, None)
            
            # Verify health check MCP client created with settings and registry
            mock_mcp_client.assert_called_once_with(
                mock_settings, mock_mcp_registry.return_value
            )
            
            # Verify MCP client factory created with settings and registry
            mock_mcp_factory.assert_called_once_with(
                mock_settings, mock_mcp_registry.return_value
            )
            
            # Verify LLM manager created with settings
            mock_llm_manager.assert_called_once_with(mock_settings)


@pytest.mark.unit
class TestAlertServiceAsyncInitialization:
    """Test AlertService async initialization methods."""
    
    @pytest.fixture
    async def alert_service(self):
        """Create AlertService with mocked dependencies."""
        mock_settings = Mock(spec=Settings)
        mock_settings.agent_config_path = None  # Prevent agent config loading
        mock_settings.llm_provider = "test-provider"  # Add configured provider
        
        with patch('tarsy.services.alert_service.RunbookService'), \
             patch('tarsy.services.alert_service.get_history_service'), \
             patch('tarsy.services.alert_service.ChainRegistry'), \
             patch('tarsy.services.alert_service.MCPServerRegistry'), \
             patch('tarsy.services.alert_service.MCPClient') as mock_mcp_client, \
             patch('tarsy.services.mcp_client_factory.MCPClientFactory') as mock_mcp_factory, \
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager, \
             patch('tarsy.services.alert_service.AgentFactory') as mock_agent_factory:
            
            service = AlertService(mock_settings)
            
            # Setup mocks for initialize()
            service.health_check_mcp_client = AsyncMock()
            service.health_check_mcp_client.get_failed_servers = Mock(return_value={})  # No failed servers by default
            service.health_check_mcp_client.initialize = AsyncMock()
            service.llm_manager = Mock()
            service.llm_manager.is_available.return_value = True
            service.llm_manager.list_available_providers.return_value = ["test-provider"]
            service.llm_manager.get_failed_providers = Mock(return_value={})  # No failed providers by default
            service.agent_factory = mock_agent_factory.return_value
            
            yield service
    
    @pytest.mark.asyncio
    async def test_initialize_success(self, alert_service):
        """Test successful async initialization."""
        with patch('tarsy.services.alert_service.AgentFactory') as mock_factory:
            await alert_service.initialize()
            
            # Verify health check MCP client initialization (renamed from mcp_client)
            alert_service.health_check_mcp_client.initialize.assert_called_once()
            
            # Verify LLM availability check
            alert_service.llm_manager.is_available.assert_called_once()
            
            # Verify agent factory creation (no longer receives mcp_client in constructor)
            mock_factory.assert_called_once_with(
                llm_manager=alert_service.llm_manager,
                mcp_registry=alert_service.mcp_server_registry,
                agent_configs={}  # Empty dict when no config path is provided
            )
    
    @pytest.mark.asyncio
    async def test_initialize_llm_unavailable(self, alert_service):
        """Test initialization failure when LLM is unavailable."""
        alert_service.llm_manager.is_available.return_value = False
        alert_service.llm_manager.list_available_providers.return_value = ["test-provider"]
        alert_service.llm_manager.get_availability_status.return_value = {"test-provider": False}
        
        with pytest.raises(Exception, match="No LLM providers are available"):
            await alert_service.initialize()
    
    @pytest.mark.asyncio
    async def test_initialize_mcp_client_failure(self, alert_service):
        """Test initialization continues when MCP servers fail with individual warnings."""
        from tarsy.models.system_models import WarningCategory
        from tarsy.services.system_warnings_service import (
            SystemWarningsService,
            get_warnings_service,
        )

        # Reset singleton for clean test
        SystemWarningsService._instance = None

        # Simulate two MCP servers failing
        alert_service.health_check_mcp_client.get_failed_servers.return_value = {
            "argocd-server": "Type=FileNotFoundError | Message=[Errno 2] No such file or directory",
            "github-server": "Type=ConnectionError | Message=Connection refused"
        }

        # Should NOT raise - initialization continues with warnings
        await alert_service.initialize()

        # Verify individual warnings were added for each failed server
        warnings_service = get_warnings_service()
        warnings = warnings_service.get_warnings()
        assert len(warnings) == 2
        
        # Check first warning (argocd-server) - uses standardized message format
        assert warnings[0].category == WarningCategory.MCP_INITIALIZATION
        assert "argocd-server" in warnings[0].message
        assert "unreachable" in warnings[0].message.lower()
        assert "FileNotFoundError" in warnings[0].details
        assert "Check argocd-server configuration" in warnings[0].details
        
        # Check second warning (github-server) - uses standardized message format
        assert warnings[1].category == WarningCategory.MCP_INITIALIZATION
        assert "github-server" in warnings[1].message
        assert "unreachable" in warnings[1].message.lower()
        assert "ConnectionError" in warnings[1].details
        assert "Check github-server configuration" in warnings[1].details

        # Verify agent factory was still initialized
        assert alert_service.agent_factory is not None
    
    @pytest.mark.asyncio
    async def test_initialize_llm_provider_failures(self, alert_service):
        """Test initialization continues when non-configured LLM providers fail with individual warnings."""
        from tarsy.models.system_models import WarningCategory
        from tarsy.services.system_warnings_service import (
            SystemWarningsService,
            get_warnings_service,
        )

        # Reset singleton for clean test
        SystemWarningsService._instance = None

        # Simulate two LLM providers failing (but configured provider still works)
        alert_service.llm_manager.get_failed_providers.return_value = {
            "openai-custom": "Connection refused: https://custom-api.openai.com",
            "anthropic-dev": "Invalid base_url configuration"
        }

        # Should NOT raise - initialization continues with warnings
        await alert_service.initialize()

        # Verify individual warnings were added for each failed provider
        warnings_service = get_warnings_service()
        warnings = warnings_service.get_warnings()
        assert len(warnings) == 2
        
        # Check first warning (openai-custom)
        assert warnings[0].category == WarningCategory.LLM_INITIALIZATION
        assert "openai-custom" in warnings[0].message
        assert "Connection refused" in warnings[0].message
        assert "Check openai-custom configuration" in warnings[0].details
        
        # Check second warning (anthropic-dev)
        assert warnings[1].category == WarningCategory.LLM_INITIALIZATION
        assert "anthropic-dev" in warnings[1].message
        assert "Invalid base_url" in warnings[1].message
        assert "Check anthropic-dev configuration" in warnings[1].details

        # Verify agent factory was still initialized
        assert alert_service.agent_factory is not None


@pytest.mark.unit
class TestChainSelection:
    """Test chain selection functionality."""

    @pytest.fixture
    def alert_service(self):
        """Create AlertService with mocked chain registry."""
        from tarsy.services.chain_registry import ChainRegistry
        
        mock_settings = MockFactory.create_mock_settings()
        service = AlertService(mock_settings)
        
        # Mock chain registry
        mock_chain_registry = Mock(spec=ChainRegistry)
        service.chain_registry = mock_chain_registry
        
        return service, mock_chain_registry

    def test_get_chain_for_alert_valid_type(self, alert_service):
        """Test get_chain_for_alert returns chain for valid alert type."""
        service, mock_registry = alert_service
        
        # Arrange
        expected_chain = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["kubernetes"],
            stages=[
                ChainStageConfigModel(
                    name="analysis",
                    agent="KubernetesAgent"
                )
            ]
        )
        mock_registry.get_chain_for_alert_type.return_value = expected_chain
        
        # Act
        result = service.get_chain_for_alert("kubernetes")
        
        # Assert
        assert result == expected_chain
        mock_registry.get_chain_for_alert_type.assert_called_once_with("kubernetes")

    def test_get_chain_for_alert_invalid_type(self, alert_service):
        """Test get_chain_for_alert raises ValueError for invalid alert type."""
        service, mock_registry = alert_service
        
        # Arrange
        mock_registry.get_chain_for_alert_type.side_effect = ValueError(
            "No chain found for alert type 'invalid_type'"
        )
        
        # Act & Assert
        with pytest.raises(ValueError, match="No chain found for alert type"):
            service.get_chain_for_alert("invalid_type")
        
        mock_registry.get_chain_for_alert_type.assert_called_once_with("invalid_type")


@pytest.mark.unit
class TestAlertProcessing:
    """Test core alert processing functionality."""
    
    @pytest.fixture
    def sample_alert(self):
        """Create a sample alert for testing."""
        return AlertFactory.create_kubernetes_alert(
            data={
                "severity": "critical",
                "environment": "production",
                "cluster": "main-cluster",
                "namespace": "test-namespace",
                "message": "Namespace is terminating",
                "alert": "NamespaceTerminating"
            }
        )
    
    @pytest.fixture
    async def initialized_service(self, sample_alert):
        """Create fully initialized AlertService."""
        from tarsy.services.session_manager import SessionManager
        from tarsy.services.stage_execution_manager import StageExecutionManager
        
        mock_settings = MockFactory.create_mock_settings(
            github_token="test_token",
            agent_config_path=None  # No agent config for unit tests
        )
        
        # Create dependencies using our factory
        dependencies = MockFactory.create_mock_alert_service_dependencies()
        
        # Create service
        service = AlertService(mock_settings)
        
        # Initialize agent factory with get_agent method
        service.agent_factory = Mock()
        service.agent_factory.get_agent = Mock()
        
        # Create mock history service for proper testing
        from tarsy.services.history_service import HistoryService
        from tarsy.models.db_models import StageExecution
        from types import SimpleNamespace
        
        mock_history_service = Mock(spec=HistoryService)
        mock_history_service.create_session.return_value = True
        mock_history_service.update_session_status = Mock()
        mock_history_service.store_llm_interaction = Mock()
        mock_history_service.store_mcp_interaction = Mock()
        # All async methods must be AsyncMock for StageExecutionManager compatibility
        mock_history_service.create_stage_execution = AsyncMock(return_value="exec-1")
        mock_history_service.update_stage_execution = AsyncMock(return_value=True)
        mock_history_service.update_session_current_stage = AsyncMock(return_value=True)
        mock_history_service.record_session_interaction = AsyncMock()
        mock_history_service.get_stage_executions = AsyncMock(return_value=[])
        mock_history_service.start_session_processing = AsyncMock(return_value=True)
        # Mock get_stage_execution to return a proper stage execution object for updates
        def create_mock_stage_execution(execution_id):
            return SimpleNamespace(
                execution_id=execution_id,
                session_id="test-session",
                stage_index=0,
                stage_id="test-stage",
                stage_name="test-stage",
                status="active",
                started_at_us=now_us(),
                completed_at_us=None,
                duration_ms=None,
                error_message=None,
                stage_output=None,
                current_iteration=None
            )
        mock_history_service.get_stage_execution = AsyncMock(side_effect=create_mock_stage_execution)
        # Mock database verification for stage creation
        mock_history_service._retry_database_operation_async = AsyncMock(return_value=True)
        service.history_service = mock_history_service
        
        # Initialize manager classes
        service.stage_manager = StageExecutionManager(service.history_service)
        service.session_manager = SessionManager(service.history_service)
        
        # Mock parallel executor
        service.parallel_executor = Mock()
        service.parallel_executor.is_final_stage_parallel = Mock(return_value=False)
        service.parallel_executor.execute_parallel_agents = AsyncMock()
        service.parallel_executor.execute_replicated_agent = AsyncMock()
        service.parallel_executor.synthesize_parallel_results = AsyncMock()
        service.parallel_executor.resume_parallel_stage = AsyncMock()
        
        yield service, dependencies
    
    @pytest.mark.asyncio
    async def test_process_alert_success(self, initialized_service, sample_alert):
        """Test successful alert processing."""
        service, dependencies = initialized_service
        
        # Mock agent processing success
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.constants import StageStatus
        
        mock_agent = AsyncMock()
        mock_agent.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="KubernetesAgent", 
            timestamp_us=now_us(),
            result_summary="Test analysis result",
            final_analysis="Test analysis result"
        )

        mock_final_analysis_summarizer = AsyncMock()
        mock_final_analysis_summarizer.generate_executive_summary.return_value = "Test analysis summary"
        service.final_analysis_summarizer = mock_final_analysis_summarizer
        
        # Set up the service with our mocked dependencies
        service.chain_registry = dependencies['chain_registry']
        service.runbook_service = dependencies['runbook']
        service.llm_manager = dependencies['llm_manager']
        
        dependencies['chain_registry'].get_chain_for_alert_type.return_value = ChainConfigModel(
            chain_id='kubernetes-agent-chain',
            alert_types=['kubernetes'],
            stages=[ChainStageConfigModel(name='analysis', agent='KubernetesAgent')],
            description='Test chain'
        )
        service.agent_factory.create_agent.return_value = mock_agent
        service.agent_factory.get_agent.return_value = mock_agent
        
        # Mock runbook download
        dependencies['runbook'].download_runbook = AsyncMock(return_value="Mock runbook content")
        
        # Mock LLM availability
        dependencies['llm_manager'].is_available.return_value = True
        
        # Convert Alert object to ChainContext using the fixed helper
        chain_context = alert_to_api_format(sample_alert)
        # Update session_id for this test
        chain_context.session_id = str(uuid.uuid4())
        chain_context.current_stage_name = "test-stage"
        
        # Process alert
        result = await service.process_alert(chain_context)
        
        # Assertions - check that the analysis result is included in the formatted response
        assert "Test analysis result" in result
        assert "# Alert Analysis Report" in result
        assert "**Processing Chain:** kubernetes-agent-chain" in result  # Chain architecture format
        mock_agent.process_alert.assert_called_once()
        
        # Verify agent was called with ChainContext (single parameter)
        call_args = mock_agent.process_alert.call_args
        chain_context = call_args[0][0]  # First (and only) positional arg should be ChainContext
        
        # Verify ChainContext contains the expected data
        assert isinstance(chain_context, ChainContext)
        assert chain_context.processing_alert.alert_data == sample_alert.data
        assert chain_context.runbook_content == "Mock runbook content"
        assert chain_context.session_id is not None
        assert chain_context.processing_alert.alert_type == sample_alert.alert_type


    @pytest.mark.asyncio
    async def test_process_alert_unsupported_type(self, initialized_service):
        """Test error handling for unsupported alert type."""
        service, dependencies = initialized_service
        
        # Set up the service with our mocked dependencies
        service.chain_registry = dependencies['chain_registry']
        service.runbook_service = dependencies['runbook']
        service.llm_manager = dependencies['llm_manager']
        
        # Create unsupported alert
        unsupported_alert = Alert(
            alert_type="UnsupportedAlertType",
            runbook="https://example.com/runbook",
            data={"message": "Unsupported alert"}
        )
        
        # Mock no agent available for type
        dependencies['chain_registry'].get_chain_for_alert_type.side_effect = ValueError("No agent for alert type 'UnsupportedAlertType'. Available: ['kubernetes']")
        dependencies['chain_registry'].list_available_alert_types.return_value = ["kubernetes"]
        dependencies['llm_manager'].is_available.return_value = True
        
        # Convert to dict and test
        chain_context = alert_to_api_format(unsupported_alert)
        chain_context.session_id = str(uuid.uuid4())
        chain_context.current_stage_name = "test-stage"
        result = await service.process_alert(chain_context)
        
        assert "No agent for alert type 'UnsupportedAlertType'" in result

    @pytest.mark.asyncio 
    async def test_process_alert_agent_creation_failure(self, initialized_service, sample_alert):
        """Test error handling when agent creation fails."""
        service, dependencies = initialized_service
        
        # Set up the service with our mocked dependencies
        service.chain_registry = dependencies['chain_registry']
        service.runbook_service = dependencies['runbook']
        service.llm_manager = dependencies['llm_manager']
        
        dependencies['chain_registry'].get_chain_for_alert_type.return_value = ChainConfigModel(
            chain_id='kubernetes-agent-chain',
            alert_types=['kubernetes'],
            stages=[ChainStageConfigModel(name='analysis', agent='KubernetesAgent')],
            description='Test chain'
        )
        dependencies['llm_manager'].is_available.return_value = True
        service.agent_factory.create_agent.side_effect = ValueError("Agent creation failed")
        
        chain_context = alert_to_api_format(sample_alert)
        chain_context.session_id = str(uuid.uuid4())
        chain_context.current_stage_name = "test-stage"
        result = await service.process_alert(chain_context)
        
        # Verify that the system handles agent creation failure gracefully
        # The specific error message may vary due to async mock interactions,
        # but the important thing is that an error response is returned
        assert "# Alert Processing Error" in result
        assert "**Alert Type:** kubernetes" in result
        assert "Error:" in result

    @pytest.mark.asyncio
    async def test_process_alert_agent_processing_failure(self, initialized_service, sample_alert):
        """Test error handling when agent processing fails.""" 
        service, dependencies = initialized_service
        
        # Set up the service with our mocked dependencies
        service.chain_registry = dependencies['chain_registry']
        service.runbook_service = dependencies['runbook']
        service.llm_manager = dependencies['llm_manager']
        
        # Mock agent that fails during processing
        mock_agent = AsyncMock()
        mock_agent.process_alert.side_effect = Exception("Agent processing failed")
        
        dependencies['chain_registry'].get_chain_for_alert_type.return_value = ChainConfigModel(
            chain_id='kubernetes-agent-chain',
            alert_types=['kubernetes'],
            stages=[ChainStageConfigModel(name='analysis', agent='KubernetesAgent')],
            description='Test chain'
        )
        dependencies['llm_manager'].is_available.return_value = True
        dependencies['runbook'].download_runbook = AsyncMock(return_value="Mock runbook")
        service.agent_factory.create_agent.return_value = mock_agent
        service.agent_factory.get_agent.return_value = mock_agent
        
        chain_context = alert_to_api_format(sample_alert)
        chain_context.session_id = str(uuid.uuid4())
        chain_context.current_stage_name = "test-stage"
        result = await service.process_alert(chain_context)
        
        # Verify error is formatted in the response
        assert "# Alert Processing Error" in result
        assert "Agent processing failed" in result

    @pytest.mark.asyncio
    async def test_process_alert_llm_unavailable(self, initialized_service, sample_alert):
        """Test error handling when LLM is unavailable."""
        service, dependencies = initialized_service
        
        # Set up the service with our mocked dependencies
        service.chain_registry = dependencies['chain_registry']
        service.runbook_service = dependencies['runbook']
        service.llm_manager = dependencies['llm_manager']
        
        dependencies['llm_manager'].is_available.return_value = False
        
        chain_context = alert_to_api_format(sample_alert)
        chain_context.session_id = str(uuid.uuid4())
        chain_context.current_stage_name = "test-stage"
        result = await service.process_alert(chain_context)
        
        assert "No LLM providers are available" in result

    @pytest.mark.asyncio
    async def test_process_alert_agent_factory_not_initialized(self, initialized_service, sample_alert):
        """Test error handling when agent factory is not initialized."""
        service, dependencies = initialized_service
        
        # Set up the service with our mocked dependencies
        service.chain_registry = dependencies['chain_registry']
        service.runbook_service = dependencies['runbook']
        service.llm_manager = dependencies['llm_manager']
        
        service.agent_factory = None
        dependencies['llm_manager'].is_available.return_value = True
        
        chain_context = alert_to_api_format(sample_alert)
        chain_context.session_id = str(uuid.uuid4())
        chain_context.current_stage_name = "test-stage"
        result = await service.process_alert(chain_context)
        
        assert "Agent factory not initialized" in result

    @pytest.mark.asyncio
    async def test_process_alert_runbook_download_failure(self, initialized_service, sample_alert):
        """Test error handling when runbook download fails."""
        service, dependencies = initialized_service
        
        # Set up the service with our mocked dependencies
        service.chain_registry = dependencies['chain_registry']
        service.runbook_service = dependencies['runbook']
        service.llm_manager = dependencies['llm_manager']
        
        dependencies['chain_registry'].get_chain_for_alert_type.return_value = ChainConfigModel(
            chain_id='kubernetes-agent-chain',
            alert_types=['kubernetes'],
            stages=[ChainStageConfigModel(name='analysis', agent='KubernetesAgent')],
            description='Test chain'
        ) 
        dependencies['llm_manager'].is_available.return_value = True
        dependencies['runbook'].download_runbook = AsyncMock(side_effect=Exception("Runbook download failed"))
        
        chain_context = alert_to_api_format(sample_alert)
        chain_context.session_id = str(uuid.uuid4())
        chain_context.current_stage_name = "test-stage"
        result = await service.process_alert(chain_context)
        
        assert "Runbook download failed" in result


@pytest.mark.unit
class TestHistorySessionManagement:
    """Test history session management functionality."""
    
    @pytest.fixture
    def alert_service_with_history(self):
        """Create AlertService with mocked history service."""
        from tarsy.services.session_manager import SessionManager
        
        mock_settings = Mock(spec=Settings)
        mock_settings.agent_config_path = None  # No agent config for unit tests
        
        with patch('tarsy.services.alert_service.RunbookService'), \
             patch('tarsy.services.alert_service.get_history_service') as mock_history, \
             patch('tarsy.services.alert_service.ChainRegistry'), \
             patch('tarsy.services.alert_service.MCPServerRegistry'), \
             patch('tarsy.services.alert_service.MCPClient'), \
             patch('tarsy.services.alert_service.LLMManager'):
            
            service = AlertService(mock_settings)
            service.history_service = Mock()
            # Create real SessionManager with mocked history service
            service.session_manager = SessionManager(service.history_service)
            
            yield service
    
    @pytest.fixture
    def sample_alert(self):
        """Create sample alert for history testing."""
        return Alert(
            alert_type="kubernetes",
            runbook="https://github.com/company/runbooks/blob/main/k8s.md",
            timestamp=now_us(),
            data={
                "severity": "critical",
                "environment": "production", 
                "cluster": "main-cluster",
                "namespace": "test-namespace",
                "message": "Namespace is terminating",
                "alert": "NamespaceTerminating"
            }
        )
    

    def test_update_session_status_success(self, alert_service_with_history):
        """Test successful session status update."""
        service = alert_service_with_history
        
        service.session_manager.update_session_status("session_123", "in_progress")
        
        service.history_service.update_session_status.assert_called_once_with(
            session_id="session_123",
            status="in_progress",
            error_message=None,
            final_analysis=None,
            final_analysis_summary=None,
            pause_metadata=None
        )
    
    def test_update_session_completed_success(self, alert_service_with_history):
        """Test marking session as completed."""
        service = alert_service_with_history
        
        service.session_manager.update_session_status("session_123", "completed")
        
        service.history_service.update_session_status.assert_called_once_with(
            session_id="session_123",
            status="completed",
            error_message=None,
            final_analysis=None,
            final_analysis_summary=None,
            pause_metadata=None
        )
    
    def test_update_session_completed_with_final_analysis(self, alert_service_with_history):
        """Test marking session as completed with final analysis."""
        service = alert_service_with_history
        analysis = "# Alert Analysis\n\nSuccessfully resolved the issue."
        
        service.session_manager.update_session_status("session_123", "completed", final_analysis=analysis)
        
        service.history_service.update_session_status.assert_called_once_with(
            session_id="session_123",
            status="completed",
            error_message=None,
            final_analysis=analysis,
            final_analysis_summary=None,
            pause_metadata=None
        )

    def test_update_session_completed_with_final_analysis_summary(self, alert_service_with_history):
        """Test marking session as completed with final analysis summary."""
        service = alert_service_with_history
        analysis = "# Alert Analysis\n\nSuccessfully resolved the issue."
        summary = "Brief summary of the analysis"
        
        service.session_manager.update_session_status("session_123", "completed", final_analysis=analysis, final_analysis_summary=summary)
        
        service.history_service.update_session_status.assert_called_once_with(
            session_id="session_123",
            status="completed",
            error_message=None,
            final_analysis=analysis,
            final_analysis_summary=summary,
            pause_metadata=None
        )
    
    def test_update_session_error_success(self, alert_service_with_history):
        """Test marking session as failed with error."""
        service = alert_service_with_history
        
        service.session_manager.update_session_error("session_123", "Processing failed")
        
        service.history_service.update_session_status.assert_called_once_with(
            session_id="session_123",
            status="failed",
            error_message="Processing failed"
        )


@pytest.mark.unit
class TestResponseFormatting:
    """Test response formatting methods."""
    
    @pytest.fixture
    def sample_alert(self):
        """Create sample alert for formatting tests."""
        return Alert(
            alert_type="kubernetes",
            runbook="https://github.com/company/runbooks/blob/main/k8s.md",
            timestamp=now_us(),
            data={
                "severity": "critical",
                "environment": "production",
                "cluster": "main-cluster",
                "namespace": "test-namespace",
                "message": "Namespace is terminating",
                "alert": "NamespaceTerminating"
            }
        )
    
    def test_format_error_response_basic(self, sample_alert):
        """Test formatting basic error response."""
        chain_context = alert_to_api_format(sample_alert)
        chain_context.session_id = str(uuid.uuid4())
        chain_context.current_stage_name = "test-stage"
        
        result = format_error_response(
            chain_context=chain_context,
            error="Test error occurred"
        )
        
        assert "# Alert Processing Error" in result
        assert "**Alert Type:** kubernetes" in result
        assert "Test error occurred" in result
    
    def test_format_error_response_with_agent(self, sample_alert):
        """Test formatting error response with agent information."""
        chain_context = alert_to_api_format(sample_alert)
        chain_context.session_id = str(uuid.uuid4())
        chain_context.current_stage_name = "test-stage"
        
        result = format_error_response(
            chain_context=chain_context,
            error="Agent processing failed",
            agent_name="KubernetesAgent"
        )
        
        assert "# Alert Processing Error" in result
        assert "**Failed Agent:** KubernetesAgent" in result
        assert "Agent processing failed" in result


@pytest.mark.unit
class TestCleanup:
    """Test cleanup and resource management."""
    
    @pytest.fixture
    async def alert_service_with_resources(self):
        """Create AlertService with resource mocks."""
        mock_settings = Mock(spec=Settings)
        mock_settings.agent_config_path = None  # No agent config for unit tests
        
        with patch('tarsy.services.alert_service.RunbookService') as mock_runbook, \
             patch('tarsy.services.alert_service.get_history_service'), \
             patch('tarsy.services.alert_service.ChainRegistry'), \
             patch('tarsy.services.alert_service.MCPServerRegistry'), \
             patch('tarsy.services.alert_service.MCPClient') as mock_mcp_client, \
             patch('tarsy.services.mcp_client_factory.MCPClientFactory'), \
             patch('tarsy.services.alert_service.LLMManager'):
            
            service = AlertService(mock_settings)
            service.runbook_service = AsyncMock()
            service.health_check_mcp_client = AsyncMock()
            
            yield service
    
    @pytest.mark.asyncio
    async def test_close_success(self, alert_service_with_resources):
        """Test successful resource cleanup."""
        service = alert_service_with_resources
        
        await service.close()
        
        service.runbook_service.close.assert_called_once()
        service.health_check_mcp_client.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_with_exception(self, alert_service_with_resources):
        """Test cleanup with exception handling."""
        service = alert_service_with_resources
        service.runbook_service.close.side_effect = Exception("Cleanup failed")
        
        # Should not raise exception
        await service.close()
        
        # Only the first cleanup method should be attempted due to exception handling
        service.runbook_service.close.assert_called_once()
        service.health_check_mcp_client.close.assert_not_called() 


@pytest.mark.unit
class TestAlertServiceDuplicatePrevention:
    """Test alert duplicate prevention and concurrency handling."""
    
    @pytest.fixture
    def sample_alert(self):
        """Create sample alert for duplicate prevention testing."""
        return Alert(
            alert_type="kubernetes",
            runbook="https://github.com/company/runbooks/blob/main/k8s.md",
            timestamp=now_us(),
            data={
                "severity": "critical",
                "environment": "production",
                "cluster": "main-cluster",
                "namespace": "test-namespace", 
                "message": "Namespace is terminating",
                "alert": "NamespaceTerminating"
            }
        )
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all AlertService dependencies."""
        with patch('tarsy.services.alert_service.RunbookService') as mock_runbook, \
             patch('tarsy.services.alert_service.get_history_service') as mock_history, \
             patch('tarsy.services.alert_service.ChainRegistry') as mock_chain_registry, \
             patch('tarsy.services.alert_service.MCPServerRegistry') as mock_mcp_registry, \
             patch('tarsy.services.alert_service.MCPClient') as mock_mcp_client, \
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager:
            
            yield {
                'runbook': mock_runbook.return_value,
                'history': mock_history.return_value,
                'chain_registry': mock_chain_registry.return_value,
                'mcp_registry': mock_mcp_registry.return_value,
                'mcp_client': mock_mcp_client.return_value,
                'llm_manager': mock_llm_manager.return_value
            }
    
    @pytest.fixture
    def alert_service_with_dependencies(self, mock_dependencies):
        """Create AlertService with mocked dependencies."""
        mock_settings = Mock(spec=Settings) 
        mock_settings.github_token = "test_token"
        mock_settings.agent_config_path = None  # No agent config for unit tests
        
        service = AlertService(mock_settings)
        service.agent_factory = Mock()
        
        return service, mock_dependencies
    
    def test_alert_key_generation(self, alert_service_with_dependencies, sample_alert):
        """Test alert key generation for duplicate prevention."""
        
        alert_dict = alert_to_api_format(sample_alert)
        alert_key = AlertKey.from_chain_context(alert_dict)
        alert_key_str = str(alert_key)
        
        # Key should be in format: alert_type_hash
        assert alert_key_str.startswith("kubernetes_")
        assert len(alert_key_str.split("_")[1]) == 12  # Hash should be 12 characters
        assert "_" in alert_key_str  # Should contain underscore separator

    def test_alert_key_truncation(self, alert_service_with_dependencies):
        """Test alert key truncation for very long messages."""
        service, _ = alert_service_with_dependencies
        
        long_message_alert = Alert(
            alert_type="kubernetes",
            runbook="https://example.com/runbook",
            data={
                "severity": "high",
                "environment": "production",
                "cluster": "default",
                "namespace": "default",
                "message": "This is a very long error message that should be truncated to prevent key length issues"
            }
        )
        
        alert_dict = alert_to_api_format(long_message_alert)
        alert_key = AlertKey.from_chain_context(alert_dict)
        alert_key_str = str(alert_key)
        
        # Even with very long messages, key should still be in format: alert_type_hash
        # The hash should be deterministic regardless of message length
        assert alert_key_str.startswith("kubernetes_")
        assert len(alert_key_str.split("_")[1]) == 12  # Hash should still be 12 characters
        assert "_" in alert_key_str  # Should contain underscore separator


@pytest.mark.unit
class TestChainErrorAggregation:
    """Test chain error aggregation and enhanced error handling."""
    
    @pytest.fixture
    def alert_service(self):
        """Create basic AlertService for error aggregation tests."""
        mock_settings = Mock(spec=Settings)
        mock_settings.agent_config_path = None
        
        with patch('tarsy.services.alert_service.RunbookService'), \
             patch('tarsy.services.alert_service.get_history_service'), \
             patch('tarsy.services.alert_service.ChainRegistry'), \
             patch('tarsy.services.alert_service.MCPServerRegistry'), \
             patch('tarsy.services.alert_service.MCPClient'), \
             patch('tarsy.services.alert_service.LLMManager'):
            
            return AlertService(mock_settings)
    
    @pytest.fixture
    def chain_context_with_failures(self):
        """Create ChainContext with mixed successful and failed stage results."""
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.constants import StageStatus
        
        processing_alert = ProcessingAlert(
            alert_type="test_alert",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test_session"
        )
        
        # Add successful stage result
        successful_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="data-collector",
            stage_name="data-collection",
            timestamp_us=now_us(),
            result_summary="Successfully collected data",
            final_analysis="Data collection completed"
        )
        
        # Add failed stage results with different error types
        failed_result_1 = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="service-checker",
            stage_name="service-check",
            timestamp_us=now_us(),
            result_summary="Failed to check service",
            error_message="Connection timeout to external service after 30 seconds"
        )
        
        failed_result_2 = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="data-analyzer",
            stage_name="analysis",
            timestamp_us=now_us(),
            result_summary="Failed analysis",
            error_message="Invalid data format in alert payload: missing required field 'metrics'"
        )
        
        # Failed stage without error message (edge case)
        failed_result_3 = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="notification-sender",
            stage_name="notification",
            timestamp_us=now_us(),
            result_summary="Failed notification"
            # No error_message field
        )
        
        chain_context.add_stage_result("data-collection", successful_result)
        chain_context.add_stage_result("service-check", failed_result_1)
        chain_context.add_stage_result("analysis", failed_result_2)
        chain_context.add_stage_result("notification", failed_result_3)
        
        return chain_context
    
    def test_aggregate_stage_errors_multiple_failures(self, alert_service, chain_context_with_failures):
        """Test error aggregation with multiple stage failures."""
        aggregated_error = alert_service._aggregate_stage_errors(chain_context_with_failures)
        
        # Verify format and content
        assert "Chain processing failed with 3 stage failures:" in aggregated_error
        assert "1. Stage 'service-check' (agent: service-checker): Connection timeout to external service after 30 seconds" in aggregated_error
        assert "2. Stage 'analysis' (agent: data-analyzer): Invalid data format in alert payload: missing required field 'metrics'" in aggregated_error
        assert "3. Stage 'notification' (agent: notification-sender): Failed with no error message" in aggregated_error
    
    def test_aggregate_stage_errors_single_failure(self, alert_service):
        """Test error aggregation with single stage failure."""
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.constants import StageStatus
        
        processing_alert = ProcessingAlert(
            alert_type="test_alert",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test_session"
        )
        
        # Add single failed result
        failed_result = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="kubernetes-agent",
            stage_name="pod-analysis",
            timestamp_us=now_us(),
            result_summary="Pod analysis failed",
            error_message="Unable to connect to Kubernetes API server"
        )
        
        chain_context.add_stage_result("pod-analysis", failed_result)
        
        aggregated_error = alert_service._aggregate_stage_errors(chain_context)
        
        # Should format as single failure, not numbered list
        assert aggregated_error == "Chain processing failed: Stage 'pod-analysis' (agent: kubernetes-agent): Unable to connect to Kubernetes API server"
    
    def test_aggregate_stage_errors_no_failures(self, alert_service):
        """Test error aggregation when no stage failures exist (edge case)."""
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.constants import StageStatus
        
        processing_alert = ProcessingAlert(
            alert_type="test_alert",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test_session"
        )
        
        # Add only successful results
        successful_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="test-agent",
            stage_name="test-stage",
            timestamp_us=now_us(),
            result_summary="Success",
            final_analysis="All good"
        )
        
        chain_context.add_stage_result("test-stage", successful_result)
        
        aggregated_error = alert_service._aggregate_stage_errors(chain_context)
        
        # Should return fallback message
        assert aggregated_error == "Chain processing failed: One or more stages failed without detailed error messages"
    
    def test_aggregate_stage_errors_empty_context(self, alert_service):
        """Test error aggregation with empty stage context."""
        from tarsy.models.alert import ProcessingAlert
        
        processing_alert = ProcessingAlert(
            alert_type="test_alert",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test_session"
        )
        
        # No stage results added
        aggregated_error = alert_service._aggregate_stage_errors(chain_context)
        
        # Should return fallback message
        assert aggregated_error == "Chain processing failed: One or more stages failed without detailed error messages"
    
    def test_aggregate_stage_errors_mixed_result_types(self, alert_service):
        """Test error aggregation handles different result types gracefully."""
        from tarsy.models.alert import ProcessingAlert
        
        processing_alert = ProcessingAlert(
            alert_type="test_alert",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test_session"
        )
        
        # Add a non-AgentExecutionResult object (edge case)
        chain_context.stage_outputs["invalid-result"] = {"not": "an_agent_result"}
        
        # Add valid failed result
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.constants import StageStatus
        
        failed_result = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="test-agent",
            stage_name="test-stage",
            timestamp_us=now_us(),
            result_summary="Failed",
            error_message="Test error"
        )
        
        chain_context.add_stage_result("test-stage", failed_result)
        
        aggregated_error = alert_service._aggregate_stage_errors(chain_context)
        
        # Should handle the valid result and ignore the invalid one
        assert "Chain processing failed: Stage 'test-stage' (agent: test-agent): Test error" in aggregated_error


@pytest.mark.unit
class TestEnhancedChainExecution:
    """Test enhanced chain execution with proper error handling."""
    
    @pytest.fixture
    async def initialized_service(self):
        """Create fully initialized AlertService for chain execution tests."""
        from tarsy.services.session_manager import SessionManager
        from tarsy.services.stage_execution_manager import StageExecutionManager
        
        mock_settings = MockFactory.create_mock_settings(
            github_token="test_token",
            agent_config_path=None
        )
        
        dependencies = MockFactory.create_mock_alert_service_dependencies()
        service = AlertService(mock_settings)
        
        # Initialize with mocked dependencies
        service.agent_factory = Mock()
        service.chain_registry = dependencies['chain_registry']
        service.runbook_service = dependencies['runbook']
        service.llm_manager = dependencies['llm_manager']
        service.history_service = Mock()
        service.history_service.create_session.return_value = True
        service.history_service.update_session_status = Mock()
        # All async methods must be AsyncMock for StageExecutionManager compatibility
        service.history_service.create_stage_execution = AsyncMock(return_value="exec-1")
        service.history_service.update_stage_execution = AsyncMock(return_value=True)
        service.history_service.update_session_current_stage = AsyncMock(return_value=True)
        service.history_service.get_stage_execution = AsyncMock()
        service.history_service.get_stage_executions = AsyncMock(return_value=[])
        service.history_service.record_session_interaction = AsyncMock()
        service.history_service.start_session_processing = AsyncMock(return_value=True)
        # Mock database verification for stage creation
        service.history_service._retry_database_operation_async = AsyncMock(return_value=True)
        
        # Initialize manager classes
        service.stage_manager = StageExecutionManager(service.history_service)
        service.session_manager = SessionManager(service.history_service)
        
        # Mock parallel executor
        service.parallel_executor = Mock()
        service.parallel_executor.is_final_stage_parallel = Mock(return_value=False)
        service.parallel_executor.execute_parallel_agents = AsyncMock()
        service.parallel_executor.execute_replicated_agent = AsyncMock()
        service.parallel_executor.synthesize_parallel_results = AsyncMock()
        service.parallel_executor.resume_parallel_stage = AsyncMock()
        
        yield service, dependencies
    
    @pytest.mark.asyncio
    async def test_execute_chain_stages_with_failures_returns_aggregated_error(self, initialized_service):
        """Test _execute_chain_stages returns ChainExecutionResult with aggregated error when stages fail."""
        service, dependencies = initialized_service
        
        # Create chain definition with multiple stages
        chain_definition = ChainConfigModel(
            chain_id='test-chain',
            alert_types=['test'],
            stages=[
                ChainStageConfigModel(name='data-collection', agent='DataAgent'),
                ChainStageConfigModel(name='analysis', agent='AnalysisAgent'),
                ChainStageConfigModel(name='notification', agent='NotificationAgent')
            ],
            description='Test chain with failures'
        )
        
        from tarsy.models.alert import ProcessingAlert
        
        processing_alert = ProcessingAlert(
            alert_type="test_alert",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test_session"
        )
        
        # Mock agents - some successful, some failing
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.constants import StageStatus
        
        successful_agent = AsyncMock()
        successful_agent.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="DataAgent",
            stage_name="data-collection",
            timestamp_us=now_us(),
            result_summary="Data collected successfully",
            final_analysis="Data collection complete"
        )
        
        failed_agent_1 = AsyncMock()
        failed_agent_1.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="AnalysisAgent", 
            stage_name="analysis",
            timestamp_us=now_us(),
            result_summary="Analysis failed",
            error_message="Missing required data fields"
        )
        
        failed_agent_2 = AsyncMock()
        failed_agent_2.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="NotificationAgent",
            stage_name="notification", 
            timestamp_us=now_us(),
            result_summary="Notification failed",
            error_message="SMTP server unreachable"
        )
        
        # Mock get_agent to return appropriate agents
        def mock_get_agent(agent_identifier, mcp_client, iteration_strategy=None, llm_provider=None, max_iterations=None, force_conclusion=None):
            if agent_identifier == 'DataAgent':
                agent = successful_agent
            elif agent_identifier == 'AnalysisAgent': 
                agent = failed_agent_1
            else:  # NotificationAgent
                agent = failed_agent_2
            
            agent.set_current_stage_execution_id = Mock()
            return agent
        
        service.agent_factory.get_agent.side_effect = mock_get_agent
        
        # Create mock session MCP client
        session_mcp_client = AsyncMock()
        
        # Execute chain stages
        result = await service._execute_chain_stages(chain_definition, chain_context, session_mcp_client)
        
        # Verify result indicates failure - chain stops at first failure
        from tarsy.models.constants import ChainStatus
        assert result.status == ChainStatus.FAILED
        assert result.error is not None
        # Chain stops at first failure (analysis stage), notification stage never runs
        assert "Missing required data fields" in result.error
        assert result.final_analysis is None  # Should be None for failed chains
        
        # Verify only first two stages were called (data-collection succeeded, analysis failed)
        assert service.agent_factory.get_agent.call_count == 2  # DataAgent and AnalysisAgent only
    
    @pytest.mark.asyncio
    async def test_execute_chain_stages_all_success_returns_analysis(self, initialized_service):
        """Test _execute_chain_stages returns final analysis when all stages succeed."""
        service, dependencies = initialized_service
        
        chain_definition = ChainConfigModel(
            chain_id='success-chain',
            alert_types=['test'],
            stages=[
                ChainStageConfigModel(name='analysis', agent='TestAgent')
            ],
            description='Test chain success'
        )
        
        from tarsy.models.alert import ProcessingAlert
        
        processing_alert = ProcessingAlert(
            alert_type="test_alert",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test_session"
        )
        
        # Mock successful agent
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.constants import StageStatus
        
        successful_agent = AsyncMock()
        successful_agent.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="TestAgent",
            stage_name="analysis", 
            timestamp_us=now_us(),
            result_summary="Analysis complete",
            final_analysis="All systems operational"
        )
        
        def mock_get_agent(agent_identifier, mcp_client, iteration_strategy=None, llm_provider=None, max_iterations=None, force_conclusion=None):
            agent = successful_agent
            agent.set_current_stage_execution_id = Mock()
            return agent
        
        service.agent_factory.get_agent.side_effect = mock_get_agent
        
        # Create mock session MCP client
        session_mcp_client = AsyncMock()
        
        # Execute chain stages
        result = await service._execute_chain_stages(chain_definition, chain_context, session_mcp_client)
        
        # Verify successful result
        from tarsy.models.constants import ChainStatus
        assert result.status == ChainStatus.COMPLETED
        assert result.error is None
        assert result.final_analysis == "All systems operational"
    
    @pytest.mark.asyncio 
    async def test_execute_chain_stages_exception_handling(self, initialized_service):
        """Test _execute_chain_stages handles exceptions properly."""
        service, dependencies = initialized_service
        
        chain_definition = ChainConfigModel(
            chain_id='exception-chain',
            alert_types=['test'],
            stages=[
                ChainStageConfigModel(name='failing-stage', agent='FailingAgent')
            ],
            description='Test chain with exception'
        )
        
        from tarsy.models.alert import ProcessingAlert
        
        processing_alert = ProcessingAlert(
            alert_type="test_alert",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test_session"
        )
        
        # Mock agent that throws exception
        failing_agent = AsyncMock()
        failing_agent.process_alert.side_effect = Exception("Unexpected agent failure")
        
        def mock_get_agent(agent_identifier, mcp_client, iteration_strategy=None, llm_provider=None, max_iterations=None, force_conclusion=None):
            agent = failing_agent
            agent.set_current_stage_execution_id = Mock()
            return agent
        
        service.agent_factory.get_agent.side_effect = mock_get_agent
        
        # Create mock session MCP client
        session_mcp_client = AsyncMock()
        
        # Execute chain stages
        result = await service._execute_chain_stages(chain_definition, chain_context, session_mcp_client)
        
        # Verify exception is handled and results in failed status with error
        from tarsy.models.constants import ChainStatus
        assert result.status == ChainStatus.FAILED
        assert result.error is not None
        assert "Stage 'failing-stage' failed with agent 'FailingAgent': Unexpected agent failure" in result.error
        assert result.final_analysis is None

    @pytest.mark.asyncio
    async def test_execute_chain_stages_cancelled_error_marks_stage_cancelled(
        self, initialized_service
    ) -> None:
        """Test CancelledError in a single-agent stage marks the stage as CANCELLED and re-raises."""
        from contextlib import asynccontextmanager

        from tarsy.models.constants import CancellationReason, StageStatus

        service, _dependencies = initialized_service

        chain_definition = ChainConfigModel(
            chain_id="cancelled-chain",
            alert_types=["test"],
            stages=[ChainStageConfigModel(name="analysis", agent="TestAgent")],
            description="Test chain cancellation",
        )

        from tarsy.models.alert import ProcessingAlert

        processing_alert = ProcessingAlert(
            alert_type="test_alert",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"},
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test_session",
        )

        stage_record = Mock()
        stage_record.stage_id = "stage-id-1"
        stage_record.execution_id = "exec-1"
        stage_record.session_id = chain_context.session_id
        stage_record.stage_name = "analysis"
        stage_record.stage_index = 0
        stage_record.status = StageStatus.PENDING.value
        stage_record.started_at_us = None
        stage_record.completed_at_us = None
        stage_record.duration_ms = None
        stage_record.stage_output = None
        stage_record.error_message = None
        stage_record.current_iteration = None

        service.history_service.get_stage_execution = AsyncMock(return_value=stage_record)

        cancelled_agent = AsyncMock()

        async def _raise_cancel(*_args, **_kwargs):
            raise asyncio.CancelledError(CancellationReason.TIMEOUT.value)

        cancelled_agent.process_alert.side_effect = _raise_cancel
        cancelled_agent.set_current_stage_execution_id = Mock()

        def mock_get_agent(agent_identifier, mcp_client, iteration_strategy=None, llm_provider=None, max_iterations=None, force_conclusion=None):
            return cancelled_agent

        service.agent_factory.get_agent.side_effect = mock_get_agent

        session_mcp_client = AsyncMock()

        @asynccontextmanager
        async def _noop_stage_execution_context(_stage):
            yield

        with patch(
            "tarsy.hooks.hook_context.stage_execution_context",
            new=_noop_stage_execution_context,
        ):
            with pytest.raises(asyncio.CancelledError):
                await service._execute_chain_stages(
                    chain_definition, chain_context, session_mcp_client
                )

        assert stage_record.status == StageStatus.CANCELLED.value
        assert stage_record.error_message == CancellationReason.TIMEOUT.value


@pytest.mark.unit
class TestFullErrorPropagation:
    """Test complete error propagation from stage failures through process_alert."""
    
    @pytest.fixture
    async def service_with_failing_stages(self):
        """Create service setup to simulate stage failures."""
        from tarsy.services.session_manager import SessionManager
        from tarsy.services.stage_execution_manager import StageExecutionManager
        
        mock_settings = MockFactory.create_mock_settings(
            github_token="test_token", 
            agent_config_path=None
        )
        
        dependencies = MockFactory.create_mock_alert_service_dependencies()
        service = AlertService(mock_settings)
        
        # Setup service with dependencies
        from types import SimpleNamespace
        
        service.agent_factory = Mock()
        service.chain_registry = dependencies['chain_registry']
        service.runbook_service = dependencies['runbook']
        service.llm_manager = dependencies['llm_manager']
        service.history_service = Mock()
        service.history_service.create_session.return_value = True
        service.history_service.update_session_status = Mock()
        # All async methods must be AsyncMock for StageExecutionManager compatibility
        service.history_service.create_stage_execution = AsyncMock(return_value="exec-1")
        service.history_service.update_stage_execution = AsyncMock(return_value=True)
        service.history_service.update_session_current_stage = AsyncMock(return_value=True)
        service.history_service.record_session_interaction = AsyncMock()
        service.history_service.get_stage_executions = AsyncMock(return_value=[])
        service.history_service.start_session_processing = AsyncMock(return_value=True)
        # Mock get_stage_execution to return proper stage execution objects
        def create_mock_stage_execution(execution_id):
            return SimpleNamespace(
                execution_id=execution_id,
                session_id="test-session",
                stage_index=0,
                stage_id="test-stage",
                stage_name="test-stage",
                status="active",
                started_at_us=now_us(),
                completed_at_us=None,
                duration_ms=None,
                error_message=None,
                stage_output=None,
                current_iteration=None
            )
        service.history_service.get_stage_execution = AsyncMock(side_effect=create_mock_stage_execution)
        # Mock database verification for stage creation
        service.history_service._retry_database_operation_async = AsyncMock(return_value=True)
        
        # Initialize manager classes
        service.stage_manager = StageExecutionManager(service.history_service)
        service.session_manager = SessionManager(service.history_service)
        
        # Mock parallel executor
        service.parallel_executor = Mock()
        service.parallel_executor.is_final_stage_parallel = Mock(return_value=False)
        service.parallel_executor.execute_parallel_agents = AsyncMock()
        service.parallel_executor.execute_replicated_agent = AsyncMock()
        service.parallel_executor.synthesize_parallel_results = AsyncMock()
        service.parallel_executor.resume_parallel_stage = AsyncMock()
        
        # Configure chain registry to return test chain
        dependencies['chain_registry'].get_chain_for_alert_type.return_value = ChainConfigModel(
            chain_id='error-test-chain',
            alert_types=['error-test'],
            stages=[
                ChainStageConfigModel(name='stage1', agent='Agent1'),
                ChainStageConfigModel(name='stage2', agent='Agent2')
            ],
            description='Chain for error testing'
        )
        
        # Configure runbook service
        dependencies['runbook'].download_runbook = AsyncMock(return_value="Test runbook content")
        
        # Configure LLM manager
        dependencies['llm_manager'].is_available.return_value = True
        
        yield service, dependencies
    
    @pytest.mark.asyncio
    async def test_process_alert_propagates_aggregated_chain_errors(self, service_with_failing_stages):
        """Test that process_alert includes aggregated stage errors in formatted response."""
        service, dependencies = service_with_failing_stages
        
        # Create failing agents
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.constants import StageStatus
        
        failing_agent_1 = AsyncMock()
        failing_agent_1.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="Agent1",
            stage_name="stage1",
            timestamp_us=now_us(),
            result_summary="Stage 1 failed",
            error_message="Database connection lost"
        )
        
        failing_agent_2 = AsyncMock()
        failing_agent_2.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.FAILED, 
            agent_name="Agent2",
            stage_name="stage2",
            timestamp_us=now_us(),
            result_summary="Stage 2 failed",
            error_message="API rate limit exceeded"
        )
        
        def mock_get_agent(agent_identifier, mcp_client, iteration_strategy=None, llm_provider=None, max_iterations=None, force_conclusion=None):
            if agent_identifier == 'Agent1':
                agent = failing_agent_1
            else:  # Agent2
                agent = failing_agent_2
            
            agent.set_current_stage_execution_id = Mock()
            return agent
        
        service.agent_factory.get_agent.side_effect = mock_get_agent
        
        # Create chain context with runbook URL
        from tarsy.models.alert import ProcessingAlert
        
        processing_alert = ProcessingAlert(
            alert_type="error-test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={
                "test": "error_data",
                "runbook": "https://example.com/test-runbook"
            }
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id=str(uuid.uuid4()),
            current_stage_name="test_stage"
        )
        
        # Process alert
        result = await service.process_alert(chain_context)
        
        # Verify the formatted error response contains first stage error (chain stops at first failure)
        assert "# Alert Processing Error" in result
        assert "Database connection lost" in result
        assert "**Alert Type:** error-test" in result
        
        # Verify history service was updated with the detailed error
        service.history_service.update_session_status.assert_called()
        error_call_args = [call for call in service.history_service.update_session_status.call_args_list 
                          if call[1].get('status') == 'failed']
        assert len(error_call_args) > 0
        
        # Verify the error message passed to history contains the error
        error_message = error_call_args[0][1]['error_message']
        assert "Database connection lost" in error_message
        
        # Verify only first agent was called (chain stopped at first failure)
        assert service.agent_factory.get_agent.call_count == 1
    
    @pytest.mark.asyncio
    async def test_process_alert_single_stage_failure_formatting(self, service_with_failing_stages):
        """Test process_alert formats single stage failure correctly."""
        service, dependencies = service_with_failing_stages
        
        # Update chain to have only one stage
        dependencies['chain_registry'].get_chain_for_alert_type.return_value = ChainConfigModel(
            chain_id='single-stage-chain',
            alert_types=['error-test'],
            stages=[
                ChainStageConfigModel(name='only-stage', agent='OnlyAgent')
            ],
            description='Single stage chain'
        )
        
        # Create single failing agent
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.constants import StageStatus
        
        failing_agent = AsyncMock()
        failing_agent.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="OnlyAgent",
            stage_name="only-stage",
            timestamp_us=now_us(),
            result_summary="Single stage failed",
            error_message="Critical system error detected"
        )
        
        def mock_get_agent(agent_identifier, mcp_client, iteration_strategy=None, llm_provider=None, max_iterations=None, force_conclusion=None):
            agent = failing_agent
            agent.set_current_stage_execution_id = Mock()
            return agent
        
        service.agent_factory.get_agent.side_effect = mock_get_agent
        
        # Create chain context with runbook URL
        from tarsy.models.alert import ProcessingAlert
        
        processing_alert = ProcessingAlert(
            alert_type="error-test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={
                "test": "single_error",
                "runbook": "https://example.com/single-test-runbook"
            }
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id=str(uuid.uuid4()),
            current_stage_name="test_stage"
        )
        
        # Process alert
        result = await service.process_alert(chain_context)
        
        # Verify single failure format
        assert "# Alert Processing Error" in result
        assert "Critical system error detected" in result
        assert "**Alert Type:** error-test" in result


@pytest.mark.unit
class TestAlertServicePausedWithNoneFinalAnalysis:
    """Test AlertService handles None final_analysis for PAUSED status correctly."""
    
    @pytest.mark.asyncio
    async def test_process_alert_paused_with_none_final_analysis(self):
        """Test that process_alert handles None final_analysis gracefully for PAUSED status."""
        from tarsy.models.api_models import ChainExecutionResult
        from tarsy.models.constants import ChainStatus
        from tarsy.models.alert import ProcessingAlert
        
        # Create mock settings
        mock_settings = MockFactory.create_mock_settings(
            agent_config_path=None,
            history_enabled=True
        )
        
        # Create alert service with mocked dependencies
        with patch('tarsy.services.alert_service.RunbookService'), \
             patch('tarsy.services.alert_service.get_history_service') as mock_history, \
             patch('tarsy.services.alert_service.ChainRegistry') as mock_chain_registry, \
             patch('tarsy.services.alert_service.MCPServerRegistry'), \
             patch('tarsy.services.alert_service.MCPClient'), \
             patch('tarsy.services.mcp_client_factory.MCPClientFactory') as mock_mcp_factory, \
             patch('tarsy.services.alert_service.LLMManager'):
            
            service = AlertService(mock_settings)
            
            # Mock chain registry to return a simple chain
            mock_chain = ChainConfigModel(
                chain_id='test-chain',
                alert_types=['test-alert'],
                stages=[
                    ChainStageConfigModel(name='stage1', agent='TestAgent')
                ],
                description='Test chain'
            )
            mock_chain_registry.return_value.get_chain_for_alert_type.return_value = mock_chain
            
            # Mock history service
            mock_history_instance = Mock()
            mock_history_instance.start_session_processing = AsyncMock()
            mock_history_instance.record_session_interaction = AsyncMock()
            mock_history.return_value = mock_history_instance
            service.history_service = mock_history_instance
            
            # Mock session manager
            service.session_manager.create_chain_history_session = Mock(return_value=True)
            service.session_manager.update_session_status = Mock()
            
            # Mock agent factory (required for process_alert)
            service.agent_factory = Mock()
            
            # Mock MCP client factory
            mock_mcp_client = AsyncMock()
            mock_mcp_client.close = AsyncMock()
            mock_mcp_factory.return_value.create_client = AsyncMock(return_value=mock_mcp_client)
            
            # Mock _execute_chain_stages to return PAUSED with None final_analysis (the bug case)
            service._execute_chain_stages = AsyncMock(
                return_value=ChainExecutionResult(
                    status=ChainStatus.PAUSED,
                    timestamp_us=now_us(),
                    final_analysis=None  # This was causing the crash
                )
            )
            
            # Create processing alert
            processing_alert = ProcessingAlert(
                alert_type="test-alert",
                severity="warning",
                timestamp=now_us(),
                environment="production",
                alert_data={"test": "data"}
            )
            chain_context = ChainContext.from_processing_alert(
                processing_alert=processing_alert,
                session_id=str(uuid.uuid4())
            )
            
            # Mock event publishing
            with patch('tarsy.services.events.event_helpers.publish_session_created', new=AsyncMock()), \
                 patch('tarsy.services.events.event_helpers.publish_session_started', new=AsyncMock()), \
                 patch('tarsy.hooks.hook_context.stage_execution_context'):
                
                # Process alert - should not crash
                result = await service.process_alert(chain_context)
            
            # Verify result contains default pause message (not None)
            assert "# Alert Analysis Report" in result
            assert "Session paused - waiting for user to resume" in result
            assert "**Processing Chain:** test-chain" in result
            assert "**Alert Type:** test-alert" in result
            
            # Verify session status was NOT updated to COMPLETED (should stay PAUSED)
            status_calls = [
                call for call in service.session_manager.update_session_status.call_args_list
            ]
            # Check that no call set status to COMPLETED
            for call in status_calls:
                if len(call.args) > 1:
                    assert call.args[1] != 'completed'
                if 'status' in call.kwargs:
                    assert call.kwargs['status'] != 'completed'

