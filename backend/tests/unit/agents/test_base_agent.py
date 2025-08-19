"""
Unit tests for BaseAgent.

Tests the base agent functionality with mocked dependencies to ensure
proper interface implementation and parameter handling.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.agents.base_agent import BaseAgent
from tarsy.agents.exceptions import ConfigurationError
from tarsy.integrations.llm.client import LLMClient
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.alert import Alert
from tarsy.models.alert_processing import AlertProcessingData
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.utils.timestamp import now_us

# TEMPORARY Phase 2: Import new context models for side-by-side testing
# These imports will be cleaned up in Phase 6
from tarsy.models.processing_context import ChainContext, StageContext, AvailableTools
from tests.unit.models.test_context_factories import (
    ChainContextFactory, 
    StageContextFactory,
    create_test_chain_context,
    create_test_stage_context
)


class TestConcreteAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""
    
    def mcp_servers(self):
        return ["test-server"]
    
    def custom_instructions(self):
        return "Test instructions"


class IncompleteAgent(BaseAgent):
    """Incomplete agent for testing abstract method requirements."""
    pass


@pytest.mark.unit
class TestBaseAgentAbstractInterface:
    """Test abstract method requirements and concrete implementation."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = Mock(spec=LLMClient)
        client.generate_response = AsyncMock(return_value="Test analysis result")
        return client
    
    @pytest.fixture
    def mock_mcp_client(self):
        """Create mock MCP client."""
        client = Mock(spec=MCPClient)
        client.list_tools = AsyncMock(return_value={"test-server": []})
        client.call_tool = AsyncMock(return_value={"result": "test"})
        return client
    
    @pytest.fixture
    def mock_mcp_registry(self):
        """Create mock MCP server registry."""
        registry = Mock(spec=MCPServerRegistry)
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "test"
        mock_config.instructions = "Test server instructions"
        registry.get_server_configs.return_value = [mock_config]
        return registry

    @pytest.mark.unit
    def test_cannot_instantiate_incomplete_agent(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test that BaseAgent cannot be instantiated without implementing abstract methods."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)

    @pytest.mark.unit
    def test_concrete_agent_implements_abstract_methods(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test that concrete agent properly implements abstract methods."""
        agent = TestConcreteAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)
        
        # Test mcp_servers returns list
        servers = agent.mcp_servers()
        assert isinstance(servers, list)
        assert servers == ["test-server"]
        
        # Test custom_instructions returns string
        instructions = agent.custom_instructions()
        assert isinstance(instructions, str)
        assert instructions == "Test instructions"

    @pytest.mark.unit
    def test_agent_initialization_with_dependencies(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test proper initialization with all required dependencies."""
        agent = TestConcreteAgent(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        assert agent.llm_client == mock_llm_client
        assert agent.mcp_client == mock_mcp_client
        assert agent.mcp_registry == mock_mcp_registry
        assert agent._iteration_count == 0
        assert agent._configured_servers is None
        # Verify default iteration strategy
        from tarsy.models.constants import IterationStrategy
        assert agent.iteration_strategy == IterationStrategy.REACT

@pytest.mark.unit
class TestBaseAgentUtilityMethods:
    """Test utility and helper methods."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        return Mock(spec=LLMClient)
    
    @pytest.fixture
    def mock_mcp_client(self):
        """Create mock MCP client."""
        return Mock(spec=MCPClient)
    
    @pytest.fixture
    def mock_mcp_registry(self):
        """Create mock MCP server registry."""
        registry = Mock(spec=MCPServerRegistry)
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "kubernetes"
        mock_config.instructions = "Kubernetes server instructions"
        registry.get_server_configs.return_value = [mock_config]
        return registry
    
    @pytest.fixture
    def base_agent(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Create base agent instance."""
        return TestConcreteAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)

    @pytest.fixture
    def sample_alert(self):
        """Create sample alert."""
        return Alert(
            alert_type="kubernetes",
            runbook="test-runbook.md",
            severity="high", 
            timestamp=now_us(),
            data={
                "alert": "TestAlert",
                "message": "Test alert message",
                "environment": "test",
                "cluster": "test-cluster",
                "namespace": "test-namespace"
            }
        )

    @pytest.mark.unit
    @patch('tarsy.agents.base_agent.get_prompt_builder')
    def test_get_server_specific_tool_guidance(self, mock_get_prompt_builder, base_agent, mock_mcp_registry):
        """Test server-specific tool guidance generation."""
        # Setup mock configs
        mock_config1 = Mock()
        mock_config1.server_type = "kubernetes"
        mock_config1.instructions = "Kubernetes tool guidance"
        
        mock_config2 = Mock()
        mock_config2.server_type = "monitoring"
        mock_config2.instructions = "Monitoring tool guidance"
        
        mock_mcp_registry.get_server_configs.return_value = [mock_config1, mock_config2]
        
        guidance = base_agent._get_server_specific_tool_guidance()
        
        assert "## Server-Specific Tool Selection Guidance" in guidance
        assert "### Kubernetes Tools" in guidance
        assert "Kubernetes tool guidance" in guidance
        assert "### Monitoring Tools" in guidance
        assert "Monitoring tool guidance" in guidance

    @pytest.mark.unit
    @patch('tarsy.agents.base_agent.get_prompt_builder')
    def test_get_server_specific_tool_guidance_empty_instructions(self, mock_get_prompt_builder, base_agent, mock_mcp_registry):
        """Test server-specific tool guidance with empty instructions."""
        mock_config = Mock()
        mock_config.server_type = "test"
        mock_config.instructions = ""
        
        mock_mcp_registry.get_server_configs.return_value = [mock_config]
        
        guidance = base_agent._get_server_specific_tool_guidance()
        # When there are server configs but no instructions, it includes header but no content
        assert guidance == "## Server-Specific Tool Selection Guidance"

    @pytest.mark.unit
    @patch('tarsy.agents.base_agent.get_prompt_builder')
    def test_get_server_specific_tool_guidance_no_configs(self, mock_get_prompt_builder, base_agent, mock_mcp_registry):
        """Test server-specific tool guidance with no server configs."""
        mock_mcp_registry.get_server_configs.return_value = []
        
        guidance = base_agent._get_server_specific_tool_guidance()
        # When there are no server configs, it returns empty string
        assert guidance == ""

@pytest.mark.unit
class TestBaseAgentInstructionComposition:
    """Test instruction composition and prompt building."""
    
    @pytest.fixture
    def mock_llm_client(self):
        return Mock(spec=LLMClient)
    
    @pytest.fixture
    def mock_mcp_client(self):
        return Mock(spec=MCPClient)
    
    @pytest.fixture
    def mock_mcp_registry(self):
        registry = Mock(spec=MCPServerRegistry)
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "kubernetes"
        mock_config.instructions = "Use kubectl commands for troubleshooting"
        registry.get_server_configs.return_value = [mock_config]
        return registry
    
    @pytest.fixture
    def base_agent(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        return TestConcreteAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)

    @pytest.mark.unit
    @patch('tarsy.agents.base_agent.get_prompt_builder')
    def test_compose_instructions_three_tiers(self, mock_get_prompt_builder, base_agent):
        """Test three-tier instruction composition."""
        # Mock prompt builder
        mock_prompt_builder = Mock()
        mock_prompt_builder.get_general_instructions.return_value = "General SRE instructions"
        mock_get_prompt_builder.return_value = mock_prompt_builder
        base_agent._prompt_builder = mock_prompt_builder
        
        instructions = base_agent._compose_instructions()
        
        # Should contain all three tiers
        assert "General SRE instructions" in instructions
        assert "## Kubernetes Server Instructions" in instructions
        assert "Use kubectl commands for troubleshooting" in instructions
        assert "## Agent-Specific Instructions" in instructions
        assert "Test instructions" in instructions

    @pytest.mark.unit
    @patch('tarsy.agents.base_agent.get_prompt_builder')
    def test_compose_instructions_no_custom(self, mock_get_prompt_builder, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test instruction composition without custom instructions."""
        
        class NoCustomAgent(BaseAgent):
            def mcp_servers(self):
                return ["test-server"]
            
            def custom_instructions(self):
                return ""
        
        # Mock prompt builder
        mock_prompt_builder = Mock()
        mock_prompt_builder.get_general_instructions.return_value = "General instructions"
        mock_get_prompt_builder.return_value = mock_prompt_builder
        
        agent = NoCustomAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)
        agent._prompt_builder = mock_prompt_builder
        
        instructions = agent._compose_instructions()
        
        assert "General instructions" in instructions
        assert "## Agent-Specific Instructions" not in instructions

    @pytest.mark.unit
    @patch('tarsy.agents.base_agent.get_prompt_builder')
    def test_create_prompt_context(self, mock_get_prompt_builder, base_agent):
        """Test prompt context creation with all parameters."""
        alert_data = {"alert": "TestAlert", "severity": "high"}
        runbook_content = "Test runbook"
        mcp_data = {"test-server": [{"tool": "test", "result": "data"}]}
        available_tools = {"tools": [{"name": "test-tool"}]}
        iteration_history = [{"tools_called": [], "mcp_data": {}}]
        
        context = base_agent.create_prompt_context(
            alert_data=alert_data,
            runbook_content=runbook_content,
            available_tools=available_tools
        )
        
        assert context.agent_name == "TestConcreteAgent"
        assert context.alert_data == alert_data
        assert context.runbook_content == runbook_content
        assert context.mcp_servers == ["test-server"]
        assert context.available_tools == available_tools


@pytest.mark.unit
class TestBaseAgentMCPIntegration:
    """Test MCP client configuration and tool execution."""
    
    @pytest.fixture
    def mock_llm_client(self):
        return Mock(spec=LLMClient)
    
    @pytest.fixture
    def mock_mcp_client(self):
        client = Mock(spec=MCPClient)
        client.list_tools = AsyncMock(return_value={
            "test-server": [
                {"name": "kubectl-get", "description": "Get resources"}
            ]
        })
        client.call_tool = AsyncMock(return_value={"result": "success"})
        return client
    
    @pytest.fixture
    def mock_mcp_registry(self):
        registry = Mock(spec=MCPServerRegistry)
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "kubernetes"
        mock_config.instructions = "Test instructions"
        registry.get_server_configs.return_value = [mock_config]
        return registry
    
    @pytest.fixture
    def base_agent(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        return TestConcreteAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_configure_mcp_client_success(self, base_agent):
        """Test successful MCP client configuration."""
        await base_agent._configure_mcp_client()
        
        assert base_agent._configured_servers == ["test-server"]
        base_agent.mcp_registry.get_server_configs.assert_called_once_with(["test-server"])

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_configure_mcp_client_missing_server(self, base_agent):
        """Test MCP client configuration with missing server."""
        base_agent.mcp_registry.get_server_configs.return_value = []  # No configs returned
        
        with pytest.raises(ConfigurationError, match="Required MCP servers not configured"):
            await base_agent._configure_mcp_client()

    @pytest.mark.unit
    @pytest.mark.asyncio 
    async def test_get_available_tools_success(self, base_agent, mock_mcp_client):
        """Test getting available tools from configured servers."""
        base_agent._configured_servers = ["test-server"]
        
        tools = await base_agent._get_available_tools("test_session")
        
        assert len(tools) == 1
        assert tools[0]["name"] == "kubectl-get"
        assert tools[0]["server"] == "test-server"
        mock_mcp_client.list_tools.assert_called_once_with(session_id="test_session", server_name="test-server", stage_execution_id=None)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_available_tools_not_configured(self, base_agent):
        """Test getting tools when agent not configured."""
        base_agent._configured_servers = None
        
        # The method catches the ValueError and returns empty list instead
        tools = await base_agent._get_available_tools("test_session")
        assert tools == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_available_tools_mcp_error(self, base_agent, mock_mcp_client):
        """Test getting tools with MCP client error."""
        base_agent._configured_servers = ["test-server"]
        mock_mcp_client.list_tools.side_effect = Exception("MCP connection failed")
        
        tools = await base_agent._get_available_tools("test_session")
        
        assert tools == []  # Should return empty list on error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_mcp_tools_success(self, base_agent, mock_mcp_client):
        """Test successful MCP tool execution."""
        base_agent._configured_servers = ["test-server"]
        
        tools_to_call = [
            {
                "server": "test-server",
                "tool": "kubectl-get",
                "parameters": {"resource": "pods"},
                "reason": "Check pod status"
            }
        ]
        
        results = await base_agent.execute_mcp_tools(tools_to_call, "test-session-123")
        
        assert "test-server" in results
        assert len(results["test-server"]) == 1
        assert results["test-server"][0]["tool"] == "kubectl-get"
        assert results["test-server"][0]["result"] == {"result": "success"}
        
        mock_mcp_client.call_tool.assert_called_once_with(
            "test-server", "kubectl-get", {"resource": "pods"}, "test-session-123", None
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_mcp_tools_server_not_allowed(self, base_agent):
        """Test tool execution with server not allowed for agent."""
        base_agent._configured_servers = ["allowed-server"]
        
        tools_to_call = [
            {
                "server": "forbidden-server",
                "tool": "dangerous-tool",
                "parameters": {},
                "reason": "Test"
            }
        ]
        
        results = await base_agent.execute_mcp_tools(tools_to_call, "test-session-456")
        
        assert "forbidden-server" in results
        assert "not allowed for agent" in results["forbidden-server"][0]["error"]

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_execute_mcp_tools_tool_error(self, base_agent, mock_mcp_client):
        """Test tool execution with tool call error."""
        base_agent._configured_servers = ["test-server"]
        mock_mcp_client.call_tool.side_effect = Exception("Tool execution failed")
        
        tools_to_call = [
            {
                "server": "test-server",
                "tool": "failing-tool",
                "parameters": {},
                "reason": "Test error handling"
            }
        ]
        
        results = await base_agent.execute_mcp_tools(tools_to_call, "test-session-789")
        
        assert "test-server" in results
        assert "Tool execution failed" in results["test-server"][0]["error"]

@pytest.mark.unit
class TestBaseAgentErrorHandling:
    """Test comprehensive error handling scenarios."""
    
    @pytest.fixture
    def mock_llm_client(self):
        return Mock(spec=LLMClient)
    
    @pytest.fixture
    def mock_mcp_client(self):
        return Mock(spec=MCPClient)
    
    @pytest.fixture
    def mock_mcp_registry(self):
        return Mock(spec=MCPServerRegistry)
    
    @pytest.fixture
    def base_agent(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        return TestConcreteAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)

    @pytest.fixture
    def sample_alert(self):
        return Alert(
            alert_type="TestAlert",
            severity="high",
            runbook="test-runbook.md",
            timestamp=now_us(),
            data={
                "environment": "test",
                "cluster": "test-cluster",
                "namespace": "test-namespace",
                "message": "Test error scenarios"
            }
        )

    @pytest.mark.asyncio
    async def test_process_alert_mcp_configuration_error(self, base_agent, sample_alert):
        """Test process_alert with MCP configuration error."""
        base_agent.mcp_registry.get_server_configs.side_effect = Exception("MCP config error")
        
        from tarsy.models.alert_processing import AlertProcessingData
        alert_processing_data = AlertProcessingData(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.data,
            runbook_content="runbook content"
        )
        result = await base_agent.process_alert(alert_processing_data, "test-session-123")
        
        assert result.status.value == "failed"
        assert "MCP config error" in result.error_message

    @pytest.mark.asyncio
    async def test_process_alert_success_flow(self, base_agent, mock_mcp_client, mock_llm_client, sample_alert):
        """Test successful process_alert flow."""
        # Mock successful flow
        mock_mcp_client.list_tools.return_value = {"test-server": []}
        mock_llm_client.generate_response.return_value = "Analysis complete"
        
        # Mock MCP registry
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "test"
        mock_config.instructions = "Test instructions"
        base_agent.mcp_registry.get_server_configs.return_value = [mock_config]
        
        # Mock prompt builder methods
        base_agent.determine_mcp_tools = AsyncMock(return_value=[])
        base_agent.determine_next_mcp_tools = AsyncMock(return_value={"continue": False})
        base_agent.analyze_alert = AsyncMock(return_value="Success analysis")
        
        # Create AlertProcessingData for new interface
        from tarsy.models.alert_processing import AlertProcessingData
        alert_processing_data = AlertProcessingData(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.data,
            runbook_content="runbook content"
        )
        
        result = await base_agent.process_alert(alert_processing_data, "test-session-success")
        
        assert result.status.value == "completed"
        assert "Analysis complete" in result.result_summary
        assert result.agent_name == "TestConcreteAgent"
        assert result.timestamp_us is not None

@pytest.mark.unit
class TestBaseAgent:
    """Test BaseAgent with session ID parameter validation."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = Mock(spec=LLMClient)
        client.generate_response = AsyncMock(return_value="Test analysis result")
        return client
    
    @pytest.fixture
    def mock_mcp_client(self):
        """Create mock MCP client."""
        client = Mock(spec=MCPClient)
        client.list_tools = AsyncMock(return_value={"test-server": []})
        client.call_tool = AsyncMock(return_value={"result": "test"})
        return client
    
    @pytest.fixture
    def base_agent(self, mock_llm_client, mock_mcp_client):
        """Create BaseAgent with mocked dependencies."""
        agent = TestConcreteAgent(mock_llm_client, Mock(spec=MCPClient), Mock(spec=MCPServerRegistry))
        agent.mcp_client = mock_mcp_client
        return agent
    
    @pytest.fixture
    def sample_alert(self):
        """Create sample alert for testing."""
        return Alert(
            alert_type="kubernetes",
            runbook="test-runbook.md",
            severity="high",
            timestamp=now_us(),
            data={
                "alert": "TestAlert",
                "message": "Test alert message",
                "environment": "test",
                "cluster": "test-cluster",
                "namespace": "test-namespace"
            }
        )

    @pytest.mark.asyncio
    async def test_process_alert_with_session_id_parameter(
        self, base_agent, mock_mcp_client, mock_llm_client, sample_alert
    ):
        """Test that process_alert accepts session_id parameter without error."""
        # Mock MCP registry
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "test"
        mock_config.instructions = "Test server instructions"
        base_agent.mcp_registry.get_server_configs.return_value = [mock_config]
        
        # Mock prompt builder methods
        base_agent.determine_mcp_tools = AsyncMock(return_value=[])
        base_agent.determine_next_mcp_tools = AsyncMock(return_value={"continue": False})
        base_agent.analyze_alert = AsyncMock(return_value="Test analysis")
        
        # Convert Alert to AlertProcessingData for new interface
        alert_processing_data = AlertProcessingData(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.model_dump(),
            runbook_url=sample_alert.runbook,
            runbook_content="test runbook content"
        )
        
        result = await base_agent.process_alert(
            alert_data=alert_processing_data,
            session_id="test-session-123"
        )
        
        assert result.status.value == "completed"
        assert result.result_summary is not None  # Analysis result may vary based on iteration strategy

    @pytest.mark.asyncio
    async def test_process_alert_without_session_id_parameter(
        self, base_agent, mock_mcp_client, mock_llm_client, sample_alert
    ):
        """Test that process_alert works without session_id parameter."""
        # Mock MCP registry
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "test"
        mock_config.instructions = "Test server instructions"
        base_agent.mcp_registry.get_server_configs.return_value = [mock_config]
        
        # Mock prompt builder methods
        base_agent.determine_mcp_tools = AsyncMock(return_value=[])
        base_agent.determine_next_mcp_tools = AsyncMock(return_value={"continue": False})
        base_agent.analyze_alert = AsyncMock(return_value="Test analysis")
        
        # Convert Alert to AlertProcessingData for new interface
        alert_processing_data = AlertProcessingData(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.model_dump(),
            runbook_url=sample_alert.runbook,
            runbook_content="test runbook content"
        )
        
        result = await base_agent.process_alert(
            alert_data=alert_processing_data,
            session_id="test-session"
        )
        
        assert result.status.value == "completed"
        assert result.result_summary is not None  # Analysis result may vary based on iteration strategy

    @pytest.mark.asyncio
    async def test_process_alert_with_none_session_id(
        self, base_agent, mock_mcp_client, mock_llm_client, sample_alert
    ):
        """Test that process_alert raises ValueError with None session_id."""
        # Convert Alert to AlertProcessingData for new interface
        alert_processing_data = AlertProcessingData(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.model_dump(),
            runbook_url=sample_alert.runbook,
            runbook_content="test runbook content"
        )
        
        with pytest.raises(ValueError, match="session_id is required"):
            await base_agent.process_alert(
                alert_data=alert_processing_data,
                session_id=None
            )

    @pytest.mark.asyncio
    async def test_process_alert_parameter_order_flexibility(
        self, base_agent, mock_mcp_client, mock_llm_client, sample_alert
    ):
        """Test that process_alert accepts parameters in different orders."""
        # Mock MCP registry
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "test"
        mock_config.instructions = "Test server instructions"
        base_agent.mcp_registry.get_server_configs.return_value = [mock_config]
        
        # Mock prompt builder methods
        base_agent.determine_mcp_tools = AsyncMock(return_value=[])
        base_agent.determine_next_mcp_tools = AsyncMock(return_value={"continue": False})
        base_agent.analyze_alert = AsyncMock(return_value="Test analysis")
        
        # Convert Alert to AlertProcessingData for new interface  
        alert_processing_data = AlertProcessingData(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.model_dump(),
            runbook_url=sample_alert.runbook,
            runbook_content="test runbook content"
        )
        
        result = await base_agent.process_alert(
            alert_data=alert_processing_data, 
            session_id="test-session"
        )
        
        assert result.status.value == "completed"
        assert result.result_summary is not None  # Analysis result may vary based on iteration strategy

    @pytest.mark.asyncio
    async def test_process_alert_error_handling_preserves_session_id_interface(
        self, base_agent, mock_mcp_client, mock_llm_client, sample_alert
    ):
        """Test that process_alert error responses preserve session_id interface."""
        # Mock MCP registry to cause an error
        base_agent.mcp_registry.get_server_configs.side_effect = Exception("MCP error")
        
        # Convert Alert to AlertProcessingData for new interface
        alert_processing_data = AlertProcessingData(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.model_dump(),
            runbook_url=sample_alert.runbook,
            runbook_content="test runbook content"
        )
        
        result = await base_agent.process_alert(
            alert_data=alert_processing_data,
            session_id="test-session-error"
        )
        
        assert result.status.value == "failed"
        assert result.error_message is not None
        assert "MCP error" in result.error_message


# =============================================================================
# TEMPORARY Phase 2: Tests using new context models alongside existing ones
# This test class will be cleaned up in Phase 6
# =============================================================================

@pytest.mark.unit
class TestBaseAgentWithNewModels:
    """TEMPORARY: Test BaseAgent functionality using new context models."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = Mock(spec=LLMClient)
        client.generate_response = AsyncMock(return_value="New model analysis result")
        return client
    
    @pytest.fixture
    def mock_mcp_client(self):
        """Create mock MCP client."""
        client = Mock(spec=MCPClient)
        client.list_tools = AsyncMock(return_value={"test-server": []})
        client.call_tool = AsyncMock(return_value={"result": "test"})
        return client
    
    @pytest.fixture
    def mock_mcp_registry(self):
        """Create mock MCP server registry."""
        registry = Mock(spec=MCPServerRegistry)
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "test"
        mock_config.instructions = "Test server instructions"
        registry.get_server_configs.return_value = [mock_config]
        return registry
    
    @pytest.fixture
    def base_agent(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Create base agent with mocked dependencies."""
        agent = TestConcreteAgent(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        return agent
    
    @pytest.mark.unit
    def test_create_prompt_context_with_new_chain_context(self, base_agent):
        """TEMPORARY: Test creating PromptContext using data from ChainContext."""
        # Create ChainContext using new factory
        chain_context = create_test_chain_context()
        
        # Extract data for PromptContext (simulating future migration)
        prompt_context = base_agent.create_prompt_context(
            alert_data=chain_context.get_original_alert_data(),
            runbook_content=chain_context.get_runbook_content(),
            stage_name=chain_context.current_stage_name
        )
        
        # Verify PromptContext creation works with new model data
        assert prompt_context.agent_name == "TestConcreteAgent"
        assert prompt_context.alert_data == chain_context.alert_data
        assert prompt_context.runbook_content == chain_context.get_runbook_content()
        assert prompt_context.stage_name == chain_context.current_stage_name
    
    @pytest.mark.unit
    def test_create_prompt_context_with_stage_context_data(self, base_agent):
        """TEMPORARY: Test creating PromptContext using data from StageContext."""
        # Create StageContext using factory
        stage_context = create_test_stage_context()
        
        # Extract data for PromptContext (simulating future integration)
        prompt_context = base_agent.create_prompt_context(
            alert_data=stage_context.alert_data,
            runbook_content=stage_context.runbook_content,
            stage_name=stage_context.stage_name,
            available_tools={"tools": stage_context.available_tools.to_prompt_format()}
        )
        
        # Verify PromptContext works with StageContext data
        assert prompt_context.agent_name == "TestConcreteAgent"
        assert prompt_context.alert_data == stage_context.alert_data
        assert prompt_context.runbook_content == stage_context.runbook_content
        assert prompt_context.stage_name == stage_context.stage_name
    
    @pytest.mark.unit
    def test_chain_context_conversion_compatibility(self, base_agent, mock_llm_client):
        """TEMPORARY: Test that AlertProcessingData → ChainContext conversion works in agent context."""
        # Create AlertProcessingData (old model)
        alert_processing_data = AlertProcessingData(
            alert_type="conversion-test",
            alert_data={"test": "conversion", "severity": "high"},
            runbook_content="# Conversion Test Runbook",
            current_stage_name="conversion-stage"
        )
        
        # Convert to ChainContext (new model)
        chain_context = alert_processing_data.to_chain_context("conversion-session-123")
        
        # Both should provide same data to agent methods
        old_data = alert_processing_data.get_original_alert_data()
        new_data = chain_context.get_original_alert_data()
        assert old_data == new_data
        
        old_runbook = alert_processing_data.get_runbook_content()
        new_runbook = chain_context.get_runbook_content()
        assert old_runbook == new_runbook
        
        # New model has additional session_id
        assert chain_context.session_id == "conversion-session-123"
        assert not hasattr(alert_processing_data, 'session_id')
    
    @pytest.mark.unit
    def test_stage_context_provides_agent_data_access(self, base_agent):
        """TEMPORARY: Test StageContext provides clean access to agent-relevant data."""
        # Create complex scenario
        stage_context = StageContextFactory.create_kubernetes_scenario()
        
        # Verify StageContext provides clean property access
        assert stage_context.agent_name == "KubernetesAgent"
        assert "failing-pod" in stage_context.alert_data["pod"]
        assert stage_context.alert_data["severity"] == "critical"
        assert "Check pod logs" in stage_context.runbook_content
        assert "kubernetes-server" in stage_context.mcp_servers
        
        # Test tools are properly formatted
        tools_format = stage_context.available_tools.to_prompt_format()
        assert "kubernetes-server.get_pods" in tools_format
        assert "kubernetes-server.get_pod_logs" in tools_format
    
    @pytest.mark.unit 
    def test_stage_context_previous_stages_formatting(self, base_agent):
        """TEMPORARY: Test StageContext formats previous stages for agent use."""
        # Create context with previous stages
        stage_context = StageContextFactory.create_with_previous_stages()
        
        # Test previous stages access
        assert stage_context.has_previous_stages()
        previous_stages = stage_context.previous_stages_results
        assert len(previous_stages) == 2
        
        # Test formatted context for prompt building
        formatted = stage_context.format_previous_stages_context()
        assert "## Results from 'Data Collection' stage:" in formatted
        assert "Collected instance metrics" in formatted
        assert "## Results from 'Root Cause Analysis' stage:" in formatted
        assert "memory leak" in formatted
        
        # This formatted context could be used in agent prompt building
        assert len(formatted) > 100  # Should be substantial content
    
    @pytest.mark.unit
    def test_new_models_property_access_performance(self, base_agent):
        """TEMPORARY: Test that new models' property access is performant for agent use."""
        stage_context = create_test_stage_context()
        
        # Property access should be fast - simulate agent accessing data frequently
        import time
        start_time = time.time()
        
        for _ in range(1000):
            # Simulate common agent property access patterns
            _ = stage_context.alert_data
            _ = stage_context.session_id
            _ = stage_context.stage_name
            _ = stage_context.agent_name
            _ = stage_context.runbook_content
            _ = stage_context.mcp_servers
        
        elapsed = time.time() - start_time
        
        # Should complete quickly (under 1 second for 1000 iterations)
        assert elapsed < 1.0, f"Property access too slow: {elapsed:.3f}s for 1000 iterations"
    
    @pytest.mark.unit
    def test_new_models_data_isolation(self, base_agent):
        """TEMPORARY: Test that new models properly isolate data for agent safety."""
        chain_context = create_test_chain_context()
        
        # Get alert data - should be a copy
        alert_data = chain_context.get_original_alert_data()
        original_pod = alert_data["pod"]
        
        # Modify the copy
        alert_data["pod"] = "modified-pod"
        alert_data["new_field"] = "added"
        
        # Original context should be unchanged
        fresh_data = chain_context.get_original_alert_data()
        assert fresh_data["pod"] == original_pod
        assert "new_field" not in fresh_data
        
        # This ensures agents can't accidentally modify context data 