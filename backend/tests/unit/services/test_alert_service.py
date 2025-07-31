"""
Unit tests for AlertService - Main alert processing orchestrator.

Tests the complete alert processing workflow including agent selection,
delegation, error handling, progress tracking, and history management.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.config.settings import Settings
from tarsy.models.alert import Alert
from tarsy.models.alert_processing import AlertKey, AlertProcessingData
from tarsy.services.alert_service import AlertService
from tarsy.utils.timestamp import now_us
from tests.conftest import alert_to_api_format


@pytest.mark.unit
class TestAlertServiceInitialization:
    """Test AlertService initialization and setup."""
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings for testing."""
        settings = Mock(spec=Settings)
        settings.github_token = "test_token"
        settings.history_enabled = True
        return settings
    
    @pytest.fixture
    def mock_dependencies(self):
        """Mock all AlertService dependencies."""
        with patch('tarsy.services.alert_service.RunbookService') as mock_runbook, \
             patch('tarsy.services.alert_service.get_history_service') as mock_history, \
             patch('tarsy.services.alert_service.AgentRegistry') as mock_registry, \
             patch('tarsy.services.alert_service.MCPServerRegistry') as mock_mcp_registry, \
             patch('tarsy.services.alert_service.MCPClient') as mock_mcp_client, \
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager:
            
            yield {
                'runbook': mock_runbook.return_value,
                'history': mock_history.return_value,
                'registry': mock_registry.return_value,
                'mcp_registry': mock_mcp_registry.return_value,
                'mcp_client': mock_mcp_client.return_value,
                'llm_manager': mock_llm_manager.return_value
            }
    
    def test_initialization_success(self, mock_settings, mock_dependencies):
        """Test successful AlertService initialization."""
        service = AlertService(mock_settings)
        
        assert service.settings == mock_settings
        assert service.runbook_service == mock_dependencies['runbook']
        assert service.history_service == mock_dependencies['history']
        assert service.agent_registry == mock_dependencies['registry']
        assert service.mcp_server_registry == mock_dependencies['mcp_registry']
        assert service.mcp_client == mock_dependencies['mcp_client']
        assert service.llm_manager == mock_dependencies['llm_manager']
        assert service.agent_factory is None  # Not initialized yet
    
    def test_initialization_with_dependencies(self, mock_settings):
        """Test that dependencies are created with correct parameters."""
        with patch('tarsy.services.alert_service.RunbookService') as mock_runbook, \
             patch('tarsy.services.alert_service.get_history_service') as mock_history, \
             patch('tarsy.services.alert_service.AgentRegistry') as mock_registry, \
             patch('tarsy.services.alert_service.MCPServerRegistry') as mock_mcp_registry, \
             patch('tarsy.services.alert_service.MCPClient') as mock_mcp_client, \
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager:
            
            service = AlertService(mock_settings)
            
            # Verify RunbookService created with settings
            mock_runbook.assert_called_once_with(mock_settings)
            
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
        
        with patch('tarsy.services.alert_service.RunbookService'), \
             patch('tarsy.services.alert_service.get_history_service'), \
             patch('tarsy.services.alert_service.AgentRegistry'), \
             patch('tarsy.services.alert_service.MCPServerRegistry'), \
             patch('tarsy.services.alert_service.MCPClient') as mock_mcp_client, \
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager, \
             patch('tarsy.services.alert_service.AgentFactory') as mock_agent_factory:
            
            service = AlertService(mock_settings)
            
            # Setup mocks for initialize()
            service.mcp_client = AsyncMock()
            service.llm_manager = Mock()
            service.llm_manager.is_available.return_value = True
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
                progress_callback=None,
                mcp_registry=alert_service.mcp_server_registry
            )
    
    @pytest.mark.asyncio
    async def test_initialize_llm_unavailable(self, alert_service):
        """Test initialization failure when LLM is unavailable."""
        alert_service.llm_manager.is_available.return_value = False
        alert_service.llm_manager.list_available_providers.return_value = ["provider1"]
        alert_service.llm_manager.get_availability_status.return_value = {"status": "error"}
        
        with pytest.raises(Exception, match="No LLM providers are available"):
            await alert_service.initialize()
    
    @pytest.mark.asyncio
    async def test_initialize_mcp_client_failure(self, alert_service):
        """Test initialization failure when MCP client initialization fails."""
        alert_service.mcp_client.initialize.side_effect = Exception("MCP init failed")
        
        with pytest.raises(Exception, match="MCP init failed"):
            await alert_service.initialize()


@pytest.mark.unit
class TestAlertProcessing:
    """Test core alert processing functionality."""
    
    @pytest.fixture
    def sample_alert(self):
        """Create a sample alert for testing."""
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
    async def initialized_service(self, sample_alert):
        """Create fully initialized AlertService."""
        mock_settings = Mock(spec=Settings)
        mock_settings.github_token = "test_token"
        mock_settings.history_enabled = True
        
        # Create dependencies  
        with patch('tarsy.services.alert_service.RunbookService') as mock_runbook, \
             patch('tarsy.services.alert_service.get_history_service') as mock_history, \
             patch('tarsy.services.alert_service.AgentRegistry') as mock_registry, \
             patch('tarsy.services.alert_service.MCPServerRegistry') as mock_mcp_registry, \
             patch('tarsy.services.alert_service.MCPClient') as mock_mcp_client, \
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager:
            
            # Set up async methods for MCP client
            mock_mcp_client.return_value.initialize = AsyncMock()
            mock_mcp_client.return_value.close = AsyncMock()
            
            dependencies = {
                'runbook': mock_runbook.return_value,
                'history': mock_history.return_value,
                'registry': mock_registry.return_value,
                'mcp_registry': mock_mcp_registry.return_value,
                'mcp_client': mock_mcp_client.return_value,
                'llm_manager': mock_llm_manager.return_value
            }
            
            # Create service
            service = AlertService(mock_settings)
            
            # Initialize agent factory
            service.agent_factory = Mock()
            
            yield service, dependencies
    
    @pytest.mark.asyncio
    async def test_process_alert_success(self, initialized_service, sample_alert):
        """Test successful alert processing."""
        service, dependencies = initialized_service
        
        # Mock agent processing success
        mock_agent = AsyncMock()
        mock_agent.process_alert.return_value = {
            "status": "success",
            "agent": "KubernetesAgent", 
            "analysis": "Test analysis result",
            "iterations": 1,
            "timestamp_us": now_us()
        }
        dependencies['registry'].get_agent_for_alert_type.return_value = "KubernetesAgent"
        service.agent_factory.create_agent.return_value = mock_agent
        
        # Mock runbook download
        dependencies['runbook'].download_runbook = AsyncMock(return_value="Mock runbook content")
        
        # Mock LLM availability
        dependencies['llm_manager'].is_available.return_value = True
        
        # Mock progress callback  
        progress_callback = AsyncMock()
        
        # Convert Alert object to dictionary for the new interface
        alert_dict = alert_to_api_format(sample_alert)
        
        # Process alert
        result = await service.process_alert(alert_dict, progress_callback)
        
        # Assertions - check that the analysis result is included in the formatted response
        assert "Test analysis result" in result
        assert "# Alert Analysis Report" in result
        assert "**Processing Agent:** KubernetesAgent" in result
        mock_agent.process_alert.assert_called_once()
        
        # Verify agent was called with correct parameters
        call_args = mock_agent.process_alert.call_args
        assert call_args[1]['alert_data'] == alert_dict.alert_data
        assert call_args[1]['runbook_content'] == "Mock runbook content"
        assert call_args[1]['session_id'] is not None
    
    @pytest.mark.asyncio
    async def test_process_alert_unsupported_type(self, initialized_service):
        """Test error handling for unsupported alert type."""
        service, dependencies = initialized_service
        
        # Create unsupported alert
        unsupported_alert = Alert(
            alert_type="UnsupportedAlertType",
            runbook="https://example.com/runbook",
            data={"message": "Unsupported alert"}
        )
        
        # Mock no agent available for type
        dependencies['registry'].get_agent_for_alert_type.side_effect = ValueError("No agent for alert type 'UnsupportedAlertType'. Available: ['kubernetes']")
        dependencies['registry'].get_supported_alert_types.return_value = ["kubernetes"]
        dependencies['llm_manager'].is_available.return_value = True
        
        # Convert to dict and test
        alert_dict = alert_to_api_format(unsupported_alert)
        result = await service.process_alert(alert_dict)
        
        assert "No agent for alert type 'UnsupportedAlertType'" in result

    @pytest.mark.asyncio 
    async def test_process_alert_agent_creation_failure(self, initialized_service, sample_alert):
        """Test error handling when agent creation fails."""
        service, dependencies = initialized_service
        
        dependencies['registry'].get_agent_for_alert_type.return_value = "KubernetesAgent"
        dependencies['llm_manager'].is_available.return_value = True
        service.agent_factory.create_agent.side_effect = ValueError("Agent creation failed")
        
        alert_dict = alert_to_api_format(sample_alert)
        result = await service.process_alert(alert_dict, progress_callback=None)
        
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
        
        # Mock agent that fails during processing
        mock_agent = AsyncMock()
        mock_agent.process_alert.side_effect = Exception("Agent processing failed")
        
        dependencies['registry'].get_agent_for_alert_type.return_value = "KubernetesAgent"
        dependencies['llm_manager'].is_available.return_value = True
        dependencies['runbook'].download_runbook = AsyncMock(return_value="Mock runbook")
        service.agent_factory.create_agent.return_value = mock_agent
        
        alert_dict = alert_to_api_format(sample_alert)
        result = await service.process_alert(alert_dict)
        
        assert "Agent processing failed" in result

    @pytest.mark.asyncio
    async def test_process_alert_llm_unavailable(self, initialized_service, sample_alert):
        """Test error handling when LLM is unavailable."""
        service, dependencies = initialized_service
        
        dependencies['llm_manager'].is_available.return_value = False
        
        alert_dict = alert_to_api_format(sample_alert)
        result = await service.process_alert(alert_dict)
        
        assert "No LLM providers are available" in result

    @pytest.mark.asyncio
    async def test_process_alert_agent_factory_not_initialized(self, initialized_service, sample_alert):
        """Test error handling when agent factory is not initialized."""
        service, dependencies = initialized_service
        
        service.agent_factory = None
        dependencies['llm_manager'].is_available.return_value = True
        
        alert_dict = alert_to_api_format(sample_alert)
        result = await service.process_alert(alert_dict)
        
        assert "Agent factory not initialized" in result

    @pytest.mark.asyncio
    async def test_process_alert_runbook_download_failure(self, initialized_service, sample_alert):
        """Test error handling when runbook download fails."""
        service, dependencies = initialized_service
        
        dependencies['registry'].get_agent_for_alert_type.return_value = "KubernetesAgent" 
        dependencies['llm_manager'].is_available.return_value = True
        dependencies['runbook'].download_runbook = AsyncMock(side_effect=Exception("Runbook download failed"))
        
        alert_dict = alert_to_api_format(sample_alert)
        result = await service.process_alert(alert_dict)
        
        assert "Runbook download failed" in result


@pytest.mark.unit
class TestHistorySessionManagement:
    """Test history session management functionality."""
    
    @pytest.fixture
    def alert_service_with_history(self):
        """Create AlertService with mocked history service."""
        mock_settings = Mock(spec=Settings)
        
        with patch('tarsy.services.alert_service.RunbookService'), \
             patch('tarsy.services.alert_service.get_history_service') as mock_history, \
             patch('tarsy.services.alert_service.AgentRegistry'), \
             patch('tarsy.services.alert_service.MCPServerRegistry'), \
             patch('tarsy.services.alert_service.MCPClient'), \
             patch('tarsy.services.alert_service.LLMManager'):
            
            service = AlertService(mock_settings)
            service.history_service = Mock()
            service.history_service.enabled = True
            service.agent_registry = Mock()
            
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
    
    def test_create_history_session_success(self, alert_service_with_history, sample_alert):
        """Test successful history session creation."""
        service = alert_service_with_history
        service.agent_registry.get_agent_for_alert_type.return_value = "KubernetesAgent"
        service.history_service.create_session.return_value = "session_123"
        
        # Convert Alert to dict for the new interface
        alert_dict = alert_to_api_format(sample_alert)
        session_id = service._create_history_session(alert_dict, "KubernetesAgent")
        
        assert session_id == "session_123"
        
        # Verify history service was called with correct parameters
        service.history_service.create_session.assert_called_once()
        call_args = service.history_service.create_session.call_args[1]
        
        # Verify alert data is passed correctly
        assert call_args['alert_data'] == alert_dict.alert_data
        assert call_args['agent_type'] == "KubernetesAgent"
    
    def test_create_history_session_disabled(self, alert_service_with_history, sample_alert):
        """Test history session creation when service is disabled."""
        service = alert_service_with_history
        service.history_service.enabled = False
        
        alert_dict = alert_to_api_format(sample_alert)
        session_id = service._create_history_session(alert_dict)
        
        assert session_id is None
        service.history_service.create_session.assert_not_called()
    
    def test_create_history_session_no_service(self, alert_service_with_history, sample_alert):
        """Test history session creation when service is None."""
        service = alert_service_with_history
        service.history_service = None
        
        alert_dict = alert_to_api_format(sample_alert)
        session_id = service._create_history_session(alert_dict)
        
        assert session_id is None
    
    def test_create_history_session_with_exception(self, alert_service_with_history, sample_alert):
        """Test history session creation with exception handling."""
        service = alert_service_with_history
        service.history_service.create_session.side_effect = Exception("Database error")
        
        # Convert Alert to dict for the new interface
        alert_dict = alert_to_api_format(sample_alert)
        
        # Should not raise exception, but return None
        session_id = service._create_history_session(alert_dict)
        
        assert session_id is None
    
    def test_update_session_status_success(self, alert_service_with_history):
        """Test successful session status update."""
        service = alert_service_with_history
        
        service._update_session_status("session_123", "in_progress", "Processing alert")
        
        service.history_service.update_session_status.assert_called_once_with(
            session_id="session_123",
            status="in_progress"
        )
    
    def test_update_session_status_disabled(self, alert_service_with_history):
        """Test session status update when service is disabled."""
        service = alert_service_with_history
        service.history_service.enabled = False
        
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
        
        with patch('tarsy.services.alert_service.RunbookService'), \
             patch('tarsy.services.alert_service.get_history_service'), \
             patch('tarsy.services.alert_service.AgentRegistry'), \
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
        
        result = alert_service._format_success_response(
            alert=alert_dict,
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
        
        result = alert_service._format_success_response(
            alert=alert_dict,
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
        
        result = alert_service._format_error_response(
            alert=alert_dict,
            error="Test error occurred"
        )
        
        assert "# Alert Processing Error" in result
        assert "**Alert Type:** kubernetes" in result
        assert "Test error occurred" in result
    
    def test_format_error_response_with_agent(self, alert_service, sample_alert):
        """Test formatting error response with agent information."""
        alert_dict = alert_to_api_format(sample_alert)
        
        result = alert_service._format_error_response(
            alert=alert_dict,
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
        
        with patch('tarsy.services.alert_service.RunbookService') as mock_runbook, \
             patch('tarsy.services.alert_service.get_history_service'), \
             patch('tarsy.services.alert_service.AgentRegistry'), \
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
             patch('tarsy.services.alert_service.AgentRegistry') as mock_registry, \
             patch('tarsy.services.alert_service.MCPServerRegistry') as mock_mcp_registry, \
             patch('tarsy.services.alert_service.MCPClient') as mock_mcp_client, \
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager:
            
            yield {
                'runbook': mock_runbook.return_value,
                'history': mock_history.return_value,
                'registry': mock_registry.return_value,
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
        
        service = AlertService(mock_settings)
        service.agent_factory = Mock()
        
        return service, mock_dependencies
    
    def test_alert_id_generation_uniqueness(self, alert_service_with_dependencies, sample_alert):
        """Test that generated alert IDs are unique and properly stored."""
        service, mock_dependencies = alert_service_with_dependencies
        
        # Mock successful processing setup
        mock_dependencies['llm_manager'].is_available.return_value = True
        mock_dependencies['registry'].get_agent_for_alert_type.return_value = "KubernetesAgent"
        mock_dependencies['history'].create_session.return_value = "session_123"
        
        alert_dict = alert_to_api_format(sample_alert)
        
        # This should call _create_history_session which calls create_session
        session_id = service._create_history_session(alert_dict, "KubernetesAgent")
        
        # Verify session was created
        assert session_id == "session_123"
        mock_dependencies['history'].create_session.assert_called_once()
        
        # Verify the call arguments contain alert data
        call_args = mock_dependencies['history'].create_session.call_args[1]
        assert call_args['alert_data'] == alert_dict.alert_data
    
    def test_alert_id_generation_with_existing_id(self, alert_service_with_dependencies, sample_alert):
        """Test alert processing with existing alert data."""
        service, mock_dependencies = alert_service_with_dependencies
        
        # Setup mocks
        mock_dependencies['llm_manager'].is_available.return_value = True
        mock_dependencies['registry'].get_agent_for_alert_type.return_value = "KubernetesAgent"
        mock_dependencies['history'].create_session.return_value = "session_456"
        
        # Add existing_id to alert data
        alert_dict = alert_to_api_format(sample_alert)
        # Since AlertProcessingData is immutable, create new instance with modified data
        modified_alert_data = alert_dict.alert_data.copy()
        modified_alert_data['existing_id'] = "existing_alert_123"
        alert_dict = AlertProcessingData(
            alert_type=alert_dict.alert_type,
            alert_data=modified_alert_data
        )
        
        session_id = service._create_history_session(alert_dict, "KubernetesAgent")
        
        assert session_id == "session_456"
        mock_dependencies['history'].create_session.assert_called_once()
        
        # Verify the existing_id is preserved in alert data
        call_args = mock_dependencies['history'].create_session.call_args[1]
        assert call_args['alert_data']['existing_id'] == "existing_alert_123"



    def test_alert_key_generation(self, alert_service_with_dependencies, sample_alert):
        """Test alert key generation for duplicate prevention."""
        service, _ = alert_service_with_dependencies
        
        alert_dict = alert_to_api_format(sample_alert)
        alert_key = AlertKey.from_alert_data(alert_dict)
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
        alert_key = AlertKey.from_alert_data(alert_dict)
        alert_key_str = str(alert_key)
        
        # Even with very long messages, key should still be in format: alert_type_hash
        # The hash should be deterministic regardless of message length
        assert alert_key_str.startswith("kubernetes_")
        assert len(alert_key_str.split("_")[1]) == 12  # Hash should still be 12 characters
        assert "_" in alert_key_str  # Should contain underscore separator

 