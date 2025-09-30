"""
Unit tests for AlertService - Main alert processing orchestrator.

Tests the complete alert processing workflow including agent selection,
delegation, error handling, progress tracking, and history management.
"""

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.config.settings import Settings
from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
from tarsy.models.alert import Alert
from tarsy.models.alert_processing import AlertKey
from tarsy.models.processing_context import ChainContext
from tarsy.services.alert_service import AlertService
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
            history_enabled=True,
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
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager:
            
            service = AlertService(mock_settings)
            
            assert service.settings == mock_settings
            assert service.runbook_service == mock_runbook.return_value
            assert service.history_service == mock_history.return_value
            assert service.chain_registry == mock_chain_registry.return_value
            assert service.mcp_server_registry == mock_mcp_registry.return_value
            assert service.mcp_client == mock_mcp_client.return_value
            assert service.llm_manager == mock_llm_manager.return_value
            assert service.agent_factory is None  # Not initialized yet
    
    def test_initialization_with_dependencies(self, mock_settings):
        """Test that dependencies are created with correct parameters."""
        with patch('tarsy.services.alert_service.RunbookService') as mock_runbook, \
             patch('tarsy.services.alert_service.get_history_service') as mock_history, \
             patch('tarsy.services.alert_service.ChainRegistry') as mock_chain_registry, \
             patch('tarsy.services.alert_service.MCPServerRegistry') as mock_mcp_registry, \
             patch('tarsy.services.alert_service.MCPClient') as mock_mcp_client, \
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager:
            
            service = AlertService(mock_settings)
            
            # Verify RunbookService created with settings and None for http_client
            mock_runbook.assert_called_once_with(mock_settings, None)
            
            # Verify MCP client created with settings and registry
            mock_mcp_client.assert_called_once_with(
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
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager, \
             patch('tarsy.services.alert_service.AgentFactory') as mock_agent_factory:
            
            service = AlertService(mock_settings)
            
            # Setup mocks for initialize()
            service.mcp_client = AsyncMock()
            service.mcp_client.get_failed_servers = Mock(return_value={})  # No failed servers by default
            service.llm_manager = Mock()
            service.llm_manager.is_available.return_value = True
            service.llm_manager.list_available_providers.return_value = ["test-provider"]
            service.agent_factory = mock_agent_factory.return_value
            
            yield service
    
    @pytest.mark.asyncio
    async def test_initialize_success(self, alert_service):
        """Test successful async initialization."""
        with patch('tarsy.services.alert_service.AgentFactory') as mock_factory:
            await alert_service.initialize()
            
            # Verify MCP client initialization
            alert_service.mcp_client.initialize.assert_called_once()
            
            # Verify LLM availability check
            alert_service.llm_manager.is_available.assert_called_once()
            
            # Verify agent factory creation
            mock_factory.assert_called_once_with(
                llm_client=alert_service.llm_manager,
                mcp_client=alert_service.mcp_client,
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
        from tarsy.services.system_warnings_service import (
            SystemWarningsService,
            get_warnings_service,
        )

        # Reset singleton for clean test
        SystemWarningsService._instance = None

        # Simulate two MCP servers failing
        alert_service.mcp_client.get_failed_servers.return_value = {
            "argocd-server": "Type=FileNotFoundError | Message=[Errno 2] No such file or directory",
            "github-server": "Type=ConnectionError | Message=Connection refused"
        }

        # Should NOT raise - initialization continues with warnings
        await alert_service.initialize()

        # Verify individual warnings were added for each failed server
        warnings_service = get_warnings_service()
        warnings = warnings_service.get_warnings()
        assert len(warnings) == 2
        
        # Check first warning (argocd-server)
        assert warnings[0].category == "mcp_initialization"
        assert "argocd-server" in warnings[0].message
        assert "FileNotFoundError" in warnings[0].message
        assert "Check argocd-server configuration" in warnings[0].details
        
        # Check second warning (github-server)
        assert warnings[1].category == "mcp_initialization"
        assert "github-server" in warnings[1].message
        assert "ConnectionError" in warnings[1].message
        assert "Check github-server configuration" in warnings[1].details

        # Verify agent factory was still initialized
        assert alert_service.agent_factory is not None


@pytest.mark.unit
class TestAlertProcessing:
    """Test core alert processing functionality."""
    
    @pytest.fixture
    def sample_alert(self):
        """Create a sample alert for testing."""
        return AlertFactory.create_kubernetes_alert(
            severity="critical",
            data={
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
        mock_settings = MockFactory.create_mock_settings(
            github_token="test_token",
            history_enabled=True,
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
        mock_history_service = Mock(spec=HistoryService)
        mock_history_service.is_enabled = True
        mock_history_service.create_session.return_value = True
        mock_history_service.update_session_status = Mock()
        mock_history_service.store_llm_interaction = Mock()
        mock_history_service.store_mcp_interaction = Mock()
        service.history_service = mock_history_service
        
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
        
        # Convert Alert object to dictionary for the new interface
        alert_dict = alert_to_api_format(sample_alert)
        
        # Create ChainContext from alert_dict for the new interface
        chain_context = ChainContext(
            alert_type=alert_dict.alert_type,
            alert_data=alert_dict.alert_data,
            session_id=str(uuid.uuid4()),
            current_stage_name="test-stage",
            runbook_content=None
        )
        
        # Process alert with required alert_id parameter
        result = await service.process_alert(chain_context, "test_alert_123")
        
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
        assert chain_context.alert_data == alert_dict.alert_data
        assert chain_context.runbook_content == "Mock runbook content"
        assert chain_context.session_id is not None
        assert chain_context.alert_type == alert_dict.alert_type


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
        alert_dict = alert_to_api_format(unsupported_alert)
        chain_context = ChainContext(
            alert_type=alert_dict.alert_type,
            alert_data=alert_dict.alert_data,
            session_id=str(uuid.uuid4()),
            current_stage_name="test-stage",
            runbook_content=None
        )
        result = await service.process_alert(chain_context, "test_alert_123")
        
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
        
        alert_dict = alert_to_api_format(sample_alert)
        chain_context = ChainContext(
            alert_type=alert_dict.alert_type,
            alert_data=alert_dict.alert_data,
            session_id=str(uuid.uuid4()),
            current_stage_name="test-stage",
            runbook_content=None
        )
        result = await service.process_alert(chain_context, "test_alert_123")
        
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
        
        alert_dict = alert_to_api_format(sample_alert)
        chain_context = ChainContext(
            alert_type=alert_dict.alert_type,
            alert_data=alert_dict.alert_data,
            session_id=str(uuid.uuid4()),
            current_stage_name="test-stage",
            runbook_content=None
        )
        result = await service.process_alert(chain_context, "test_alert_123")
        
        assert "Chain processing failed" in result  # Chain architecture error format

    @pytest.mark.asyncio
    async def test_process_alert_llm_unavailable(self, initialized_service, sample_alert):
        """Test error handling when LLM is unavailable."""
        service, dependencies = initialized_service
        
        # Set up the service with our mocked dependencies
        service.chain_registry = dependencies['chain_registry']
        service.runbook_service = dependencies['runbook']
        service.llm_manager = dependencies['llm_manager']
        
        dependencies['llm_manager'].is_available.return_value = False
        
        alert_dict = alert_to_api_format(sample_alert)
        chain_context = ChainContext(
            alert_type=alert_dict.alert_type,
            alert_data=alert_dict.alert_data,
            session_id=str(uuid.uuid4()),
            current_stage_name="test-stage",
            runbook_content=None
        )
        result = await service.process_alert(chain_context, "test_alert_123")
        
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
        
        alert_dict = alert_to_api_format(sample_alert)
        chain_context = ChainContext(
            alert_type=alert_dict.alert_type,
            alert_data=alert_dict.alert_data,
            session_id=str(uuid.uuid4()),
            current_stage_name="test-stage",
            runbook_content=None
        )
        result = await service.process_alert(chain_context, "test_alert_123")
        
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
        
        alert_dict = alert_to_api_format(sample_alert)
        chain_context = ChainContext(
            alert_type=alert_dict.alert_type,
            alert_data=alert_dict.alert_data,
            session_id=str(uuid.uuid4()),
            current_stage_name="test-stage",
            runbook_content=None
        )
        result = await service.process_alert(chain_context, "test_alert_123")
        
        assert "Runbook download failed" in result


@pytest.mark.unit
class TestHistorySessionManagement:
    """Test history session management functionality."""
    
    @pytest.fixture
    def alert_service_with_history(self):
        """Create AlertService with mocked history service."""
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
            service.history_service.is_enabled = True
            
            yield service
    
    @pytest.fixture
    def sample_alert(self):
        """Create sample alert for history testing."""
        return Alert(
            alert_type="kubernetes",
            runbook="https://github.com/company/runbooks/blob/main/k8s.md",
            severity="critical",
            timestamp=now_us(),
            data={
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
        
        service._update_session_status("session_123", "in_progress")
        
        service.history_service.update_session_status.assert_called_once_with(
            session_id="session_123",
            status="in_progress"
        )
    
    def test_update_session_status_disabled(self, alert_service_with_history):
        """Test session status update when service is disabled."""
        service = alert_service_with_history
        service.history_service.is_enabled = False
        
        service._update_session_status("session_123", "in_progress")
        
        service.history_service.update_session_status.assert_not_called()
    
    def test_update_session_completed_success(self, alert_service_with_history):
        """Test marking session as completed."""
        service = alert_service_with_history
        
        service._update_session_completed("session_123", "completed")
        
        service.history_service.update_session_status.assert_called_once_with(
            session_id="session_123",
            status="completed",
            final_analysis=None
        )
    
    def test_update_session_completed_with_final_analysis(self, alert_service_with_history):
        """Test marking session as completed with final analysis."""
        service = alert_service_with_history
        analysis = "# Alert Analysis\n\nSuccessfully resolved the issue."
        
        service._update_session_completed("session_123", "completed", analysis)
        
        service.history_service.update_session_status.assert_called_once_with(
            session_id="session_123",
            status="completed",
            final_analysis=analysis
        )
    
    def test_update_session_error_success(self, alert_service_with_history):
        """Test marking session as failed with error."""
        service = alert_service_with_history
        
        service._update_session_error("session_123", "Processing failed")
        
        service.history_service.update_session_status.assert_called_once_with(
            session_id="session_123",
            status="failed",
            error_message="Processing failed"
        )


@pytest.mark.unit
class TestResponseFormatting:
    """Test response formatting methods."""
    
    @pytest.fixture
    def alert_service(self):
        """Create basic AlertService for formatting tests."""
        mock_settings = Mock(spec=Settings)
        mock_settings.agent_config_path = None  # No agent config for unit tests
        
        with patch('tarsy.services.alert_service.RunbookService'), \
             patch('tarsy.services.alert_service.get_history_service'), \
             patch('tarsy.services.alert_service.ChainRegistry'), \
             patch('tarsy.services.alert_service.MCPServerRegistry'), \
             patch('tarsy.services.alert_service.MCPClient'), \
             patch('tarsy.services.alert_service.LLMManager'):
            
            return AlertService(mock_settings)
    
    @pytest.fixture
    def sample_alert(self):
        """Create sample alert for formatting tests."""
        return Alert(
            alert_type="kubernetes",
            runbook="https://github.com/company/runbooks/blob/main/k8s.md",
            severity="critical",
            timestamp=now_us(),
            data={
                "environment": "production",
                "cluster": "main-cluster",
                "namespace": "test-namespace",
                "message": "Namespace is terminating",
                "alert": "NamespaceTerminating"
            }
        )
    
    def test_format_success_response(self, alert_service, sample_alert):
        """Test formatting successful response."""
        alert_dict = alert_to_api_format(sample_alert)
        chain_context = ChainContext(
            alert_type=alert_dict.alert_type,
            alert_data=alert_dict.alert_data,
            session_id=str(uuid.uuid4()),
            current_stage_name="test-stage",
            runbook_content=None
        )
        
        result = alert_service._format_success_response(
            chain_context=chain_context,
            agent_name="KubernetesAgent",
            analysis="Detailed analysis result",
            iterations=3,
            timestamp_us=1704110400000000  # 2024-01-01T12:00:00Z in microseconds since epoch
        )
        
        assert "# Alert Analysis Report" in result
        assert "**Alert Type:** kubernetes" in result  
        assert "**Processing Agent:** KubernetesAgent" in result
        assert "**Timestamp:** 1704110400000000" in result
        assert "## Analysis" in result
        assert "Detailed analysis result" in result
        assert "*Processed by KubernetesAgent in 3 iterations*" in result
    
    def test_format_success_response_without_timestamp(self, alert_service, sample_alert):
        """Test formatting successful response without timestamp."""
        alert_dict = alert_to_api_format(sample_alert)
        chain_context = ChainContext(
            alert_type=alert_dict.alert_type,
            alert_data=alert_dict.alert_data,
            session_id=str(uuid.uuid4()),
            current_stage_name="test-stage",
            runbook_content=None
        )
        
        result = alert_service._format_success_response(
            chain_context=chain_context,
            agent_name="KubernetesAgent",
            analysis="Test analysis",
            iterations=1
        )
        
        # Should include current timestamp
        assert "**Timestamp:**" in result
        assert "# Alert Analysis Report" in result
    
    def test_format_error_response_basic(self, alert_service, sample_alert):
        """Test formatting basic error response."""
        alert_dict = alert_to_api_format(sample_alert)
        chain_context = ChainContext(
            alert_type=alert_dict.alert_type,
            alert_data=alert_dict.alert_data,
            session_id=str(uuid.uuid4()),
            current_stage_name="test-stage",
            runbook_content=None
        )
        
        result = alert_service._format_error_response(
            chain_context=chain_context,
            error="Test error occurred"
        )
        
        assert "# Alert Processing Error" in result
        assert "**Alert Type:** kubernetes" in result
        assert "Test error occurred" in result
    
    def test_format_error_response_with_agent(self, alert_service, sample_alert):
        """Test formatting error response with agent information."""
        alert_dict = alert_to_api_format(sample_alert)
        chain_context = ChainContext(
            alert_type=alert_dict.alert_type,
            alert_data=alert_dict.alert_data,
            session_id=str(uuid.uuid4()),
            current_stage_name="test-stage",
            runbook_content=None
        )
        
        result = alert_service._format_error_response(
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
             patch('tarsy.services.alert_service.LLMManager'):
            
            service = AlertService(mock_settings)
            service.runbook_service = AsyncMock()
            service.mcp_client = AsyncMock()
            
            yield service
    
    @pytest.mark.asyncio
    async def test_close_success(self, alert_service_with_resources):
        """Test successful resource cleanup."""
        service = alert_service_with_resources
        
        await service.close()
        
        service.runbook_service.close.assert_called_once()
        service.mcp_client.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_with_exception(self, alert_service_with_resources):
        """Test cleanup with exception handling."""
        service = alert_service_with_resources
        service.runbook_service.close.side_effect = Exception("Cleanup failed")
        
        # Should not raise exception
        await service.close()
        
        # Only the first cleanup method should be attempted due to exception handling
        service.runbook_service.close.assert_called_once()
        service.mcp_client.close.assert_not_called() 


@pytest.mark.unit
class TestAlertServiceDuplicatePrevention:
    """Test alert duplicate prevention and concurrency handling."""
    
    @pytest.fixture
    def sample_alert(self):
        """Create sample alert for duplicate prevention testing."""
        return Alert(
            alert_type="kubernetes",
            runbook="https://github.com/company/runbooks/blob/main/k8s.md",
            severity="critical",
            timestamp=now_us(),
            data={
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
        mock_settings.history_enabled = True
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
            severity="high",
            data={
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
        from tarsy.models.constants import StageStatus
        from tarsy.utils.timestamp import now_us
        
        chain_context = ChainContext(
            alert_type="test_alert",
            alert_data={"test": "data"},
            session_id="test_session",
            current_stage_name="test_stage"
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
        from tarsy.models.constants import StageStatus
        from tarsy.utils.timestamp import now_us
        
        chain_context = ChainContext(
            alert_type="test_alert",
            alert_data={"test": "data"},
            session_id="test_session",
            current_stage_name="test_stage"
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
        from tarsy.models.constants import StageStatus
        from tarsy.utils.timestamp import now_us
        
        chain_context = ChainContext(
            alert_type="test_alert",
            alert_data={"test": "data"},
            session_id="test_session",
            current_stage_name="test_stage"
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
        chain_context = ChainContext(
            alert_type="test_alert",
            alert_data={"test": "data"},
            session_id="test_session",
            current_stage_name="test_stage"
        )
        
        # No stage results added
        aggregated_error = alert_service._aggregate_stage_errors(chain_context)
        
        # Should return fallback message
        assert aggregated_error == "Chain processing failed: One or more stages failed without detailed error messages"
    
    def test_aggregate_stage_errors_mixed_result_types(self, alert_service):
        """Test error aggregation handles different result types gracefully."""
        chain_context = ChainContext(
            alert_type="test_alert",
            alert_data={"test": "data"},
            session_id="test_session",
            current_stage_name="test_stage"
        )
        
        # Add a non-AgentExecutionResult object (edge case)
        chain_context.stage_outputs["invalid-result"] = {"not": "an_agent_result"}
        
        # Add valid failed result
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.constants import StageStatus
        from tarsy.utils.timestamp import now_us
        
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
        mock_settings = MockFactory.create_mock_settings(
            github_token="test_token",
            history_enabled=True,
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
        service.history_service.is_enabled = True
        service.history_service.create_session.return_value = True
        service.history_service.update_session_status = Mock()
        service.history_service.get_stage_execution = AsyncMock()
        service.history_service.update_session_current_stage = AsyncMock()
        
        # Mock stage execution methods
        service._create_stage_execution = AsyncMock(return_value="stage_exec_123")
        service._update_stage_execution_started = AsyncMock()
        service._update_stage_execution_completed = AsyncMock()
        service._update_stage_execution_failed = AsyncMock()
        service._update_session_current_stage = AsyncMock()
        
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
        
        chain_context = ChainContext(
            alert_type="test_alert",
            alert_data={"test": "data"},
            session_id="test_session",
            current_stage_name="test_stage"
        )
        
        # Mock agents - some successful, some failing
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.constants import StageStatus
        from tarsy.utils.timestamp import now_us
        
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
        def mock_get_agent(agent_identifier, iteration_strategy=None):
            if agent_identifier == 'DataAgent':
                agent = successful_agent
            elif agent_identifier == 'AnalysisAgent': 
                agent = failed_agent_1
            else:  # NotificationAgent
                agent = failed_agent_2
            
            agent.set_current_stage_execution_id = Mock()
            return agent
        
        service.agent_factory.get_agent.side_effect = mock_get_agent
        
        # Execute chain stages
        result = await service._execute_chain_stages(chain_definition, chain_context)
        
        # Verify result indicates failure with aggregated error
        from tarsy.models.constants import ChainStatus
        assert result.status == ChainStatus.FAILED
        assert result.error is not None
        assert "Chain processing failed with 2 stage failures:" in result.error
        assert "Stage 'analysis' (agent: AnalysisAgent): Missing required data fields" in result.error
        assert "Stage 'notification' (agent: NotificationAgent): SMTP server unreachable" in result.error
        assert result.final_analysis is None  # Should be None for failed chains
    
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
        
        chain_context = ChainContext(
            alert_type="test_alert",
            alert_data={"test": "data"},
            session_id="test_session",
            current_stage_name="test_stage"
        )
        
        # Mock successful agent
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.constants import StageStatus
        from tarsy.utils.timestamp import now_us
        
        successful_agent = AsyncMock()
        successful_agent.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="TestAgent",
            stage_name="analysis", 
            timestamp_us=now_us(),
            result_summary="Analysis complete",
            final_analysis="All systems operational"
        )
        
        def mock_get_agent(agent_identifier, iteration_strategy=None):
            agent = successful_agent
            agent.set_current_stage_execution_id = Mock()
            return agent
        
        service.agent_factory.get_agent.side_effect = mock_get_agent
        
        # Execute chain stages
        result = await service._execute_chain_stages(chain_definition, chain_context)
        
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
        
        chain_context = ChainContext(
            alert_type="test_alert",
            alert_data={"test": "data"},
            session_id="test_session",
            current_stage_name="test_stage"
        )
        
        # Mock agent that throws exception
        failing_agent = AsyncMock()
        failing_agent.process_alert.side_effect = Exception("Unexpected agent failure")
        
        def mock_get_agent(agent_identifier, iteration_strategy=None):
            agent = failing_agent
            agent.set_current_stage_execution_id = Mock()
            return agent
        
        service.agent_factory.get_agent.side_effect = mock_get_agent
        
        # Execute chain stages
        result = await service._execute_chain_stages(chain_definition, chain_context)
        
        # Verify exception is handled and results in failed status with error
        from tarsy.models.constants import ChainStatus
        assert result.status == ChainStatus.FAILED
        assert result.error is not None
        assert "Chain processing failed: Stage 'failing-stage' (agent: FailingAgent): Unexpected agent failure" in result.error
        assert result.final_analysis is None


@pytest.mark.unit
class TestFullErrorPropagation:
    """Test complete error propagation from stage failures through process_alert."""
    
    @pytest.fixture
    async def service_with_failing_stages(self):
        """Create service setup to simulate stage failures."""
        mock_settings = MockFactory.create_mock_settings(
            github_token="test_token", 
            history_enabled=True,
            agent_config_path=None
        )
        
        dependencies = MockFactory.create_mock_alert_service_dependencies()
        service = AlertService(mock_settings)
        
        # Setup service with dependencies
        service.agent_factory = Mock()
        service.chain_registry = dependencies['chain_registry']
        service.runbook_service = dependencies['runbook']
        service.llm_manager = dependencies['llm_manager']
        service.history_service = Mock()
        service.history_service.is_enabled = True
        service.history_service.create_session.return_value = True
        service.history_service.update_session_status = Mock()
        
        # Mock stage execution methods
        service._create_stage_execution = AsyncMock(return_value="stage_exec_123")
        service._update_stage_execution_started = AsyncMock()
        service._update_stage_execution_completed = AsyncMock()
        service._update_stage_execution_failed = AsyncMock()
        service._update_session_current_stage = AsyncMock()
        
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
        from tarsy.utils.timestamp import now_us
        
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
        
        def mock_get_agent(agent_identifier, iteration_strategy=None):
            if agent_identifier == 'Agent1':
                agent = failing_agent_1
            else:  # Agent2
                agent = failing_agent_2
            
            agent.set_current_stage_execution_id = Mock()
            return agent
        
        service.agent_factory.get_agent.side_effect = mock_get_agent
        
        # Create chain context with runbook URL
        chain_context = ChainContext(
            alert_type="error-test",
            alert_data={
                "test": "error_data",
                "runbook": "https://example.com/test-runbook"
            },
            session_id=str(uuid.uuid4()),
            current_stage_name="test_stage"
        )
        
        # Process alert
        result = await service.process_alert(chain_context, "test_alert_123")
        
        # Verify the formatted error response contains aggregated errors
        assert "# Alert Processing Error" in result
        assert "Chain processing failed with 2 stage failures:" in result
        assert "Stage 'stage1' (agent: Agent1): Database connection lost" in result
        assert "Stage 'stage2' (agent: Agent2): API rate limit exceeded" in result
        assert "**Alert Type:** error-test" in result
        
        # Verify history service was updated with the detailed error
        service.history_service.update_session_status.assert_called()
        error_call_args = [call for call in service.history_service.update_session_status.call_args_list 
                          if call[1].get('status') == 'failed']
        assert len(error_call_args) > 0
        
        # Verify the error message passed to history contains the aggregated error
        error_message = error_call_args[0][1]['error_message']
        assert "Chain processing failed with 2 stage failures:" in error_message
    
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
        from tarsy.utils.timestamp import now_us
        
        failing_agent = AsyncMock()
        failing_agent.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="OnlyAgent",
            stage_name="only-stage",
            timestamp_us=now_us(),
            result_summary="Single stage failed",
            error_message="Critical system error detected"
        )
        
        def mock_get_agent(agent_identifier, iteration_strategy=None):
            agent = failing_agent
            agent.set_current_stage_execution_id = Mock()
            return agent
        
        service.agent_factory.get_agent.side_effect = mock_get_agent
        
        # Create chain context with runbook URL
        chain_context = ChainContext(
            alert_type="error-test",
            alert_data={
                "test": "single_error",
                "runbook": "https://example.com/single-test-runbook"
            },
            session_id=str(uuid.uuid4()),
            current_stage_name="test_stage"
        )
        
        # Process alert
        result = await service.process_alert(chain_context, "single_alert_123")
        
        # Verify single failure format (not numbered list)
        assert "# Alert Processing Error" in result
        assert "Chain processing failed: Stage 'only-stage' (agent: OnlyAgent): Critical system error detected" in result
        # Should NOT contain "with X stage failures:" since it's a single failure
        assert "stage failures:" not in result


@pytest.mark.unit
class TestAlertServiceValidationAndCaching:
    """Test AlertService alert ID validation and TTL caching functionality."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock(spec=Settings)
        settings.github_token = "test_token"
        settings.history_enabled = True
        settings.agent_config_path = None  # No agent config for unit tests
        return settings
    
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
    def alert_service(self, mock_settings, mock_dependencies):
        """Create AlertService instance for testing."""
        service = AlertService(mock_settings)
        return service
    
    def test_alert_id_registration_and_validation(self, alert_service):
        """Test alert ID registration and existence checking."""
        alert_id = "test-alert-123"
        
        # Initially, alert should not exist
        assert not alert_service.alert_exists(alert_id)
        
        # Register the alert ID
        alert_service.register_alert_id(alert_id)
        
        # Now alert should exist
        assert alert_service.alert_exists(alert_id)
        
        # Test with different alert ID - should not exist
        assert not alert_service.alert_exists("different-alert-456")
    
    def test_alert_session_mapping(self, alert_service):
        """Test alert-to-session ID mapping functionality."""
        alert_id = "test-alert-123"
        session_id = "session-456"
        
        # Initially, no session mapping should exist
        assert alert_service.get_session_id_for_alert(alert_id) is None
        
        # Store the mapping
        alert_service.store_alert_session_mapping(alert_id, session_id)
        
        # Should now return the session ID
        assert alert_service.get_session_id_for_alert(alert_id) == session_id
        
        # Different alert should still return None
        assert alert_service.get_session_id_for_alert("different-alert") is None
    
    def test_combined_alert_registration_and_mapping(self, alert_service):
        """Test combined workflow of alert registration and session mapping."""
        alert_id = "test-alert-789"
        session_id = "session-999"
        
        # Register alert and create session mapping
        alert_service.register_alert_id(alert_id)
        alert_service.store_alert_session_mapping(alert_id, session_id)
        
        # Verify both work together
        assert alert_service.alert_exists(alert_id)
        assert alert_service.get_session_id_for_alert(alert_id) == session_id
    
    def test_cache_clear_functionality(self, alert_service):
        """Test cache clearing functionality."""
        alert_id = "test-alert-clear"
        session_id = "session-clear"
        
        # Register alert and session mapping
        alert_service.register_alert_id(alert_id)
        alert_service.store_alert_session_mapping(alert_id, session_id)
        
        # Verify they exist
        assert alert_service.alert_exists(alert_id)
        assert alert_service.get_session_id_for_alert(alert_id) == session_id
        
        # Clear caches
        alert_service.clear_caches()
        
        # Verify everything is cleared
        assert not alert_service.alert_exists(alert_id)
        assert alert_service.get_session_id_for_alert(alert_id) is None
    
    def test_ttl_cache_properties(self, alert_service):
        """Test TTL cache specific properties and behavior."""
        # Test that the caches are TTLCache instances with correct properties
        from cachetools import TTLCache
        
        assert isinstance(alert_service.alert_session_mapping, TTLCache)
        assert isinstance(alert_service.valid_alert_ids, TTLCache)
        
        # Verify cache configurations
        assert alert_service.alert_session_mapping.maxsize == 10000
        assert alert_service.valid_alert_ids.maxsize == 10000
        assert alert_service.alert_session_mapping.ttl == 4 * 3600  # 4 hours
        assert alert_service.valid_alert_ids.ttl == 4 * 3600  # 4 hours
    
    @pytest.mark.asyncio
    async def test_close_clears_caches(self, alert_service):
        """Test that closing the service clears caches."""
        alert_id = "test-alert-close"
        
        # Register an alert
        alert_service.register_alert_id(alert_id)
        assert alert_service.alert_exists(alert_id)
        
        # Close the service
        await alert_service.close()
        
        # Cache should be cleared
        assert not alert_service.alert_exists(alert_id)
    
    def test_multiple_alert_ids(self, alert_service):
        """Test handling multiple alert IDs."""
        alert_ids = ["alert-1", "alert-2", "alert-3", "alert-4", "alert-5"]
        session_ids = ["session-1", "session-2", "session-3", "session-4", "session-5"]
        
        # Register multiple alerts with session mappings
        for alert_id, session_id in zip(alert_ids, session_ids, strict=False):
            alert_service.register_alert_id(alert_id)
            alert_service.store_alert_session_mapping(alert_id, session_id)
        
        # Verify all alerts exist and have correct mappings
        for alert_id, expected_session_id in zip(alert_ids, session_ids, strict=False):
            assert alert_service.alert_exists(alert_id)
            assert alert_service.get_session_id_for_alert(alert_id) == expected_session_id
        
        # Verify non-existent alert doesn't interfere
        assert not alert_service.alert_exists("non-existent-alert")
    
    def test_alert_exists_edge_cases(self, alert_service):
        """Test alert_exists method with edge cases."""
        # Test with empty string
        assert not alert_service.alert_exists("")
        
        # Test with None (should handle gracefully)
        try:
            result = alert_service.alert_exists(None)
            assert not result  # Should return False
        except (TypeError, AttributeError):
            # It's acceptable if it raises an error for None
            pass
        
        # Test with very long alert ID
        long_alert_id = "a" * 1000
        assert not alert_service.alert_exists(long_alert_id)
        alert_service.register_alert_id(long_alert_id)
        assert alert_service.alert_exists(long_alert_id)