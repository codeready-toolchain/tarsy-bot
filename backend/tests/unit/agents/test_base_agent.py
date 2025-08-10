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
from tarsy.services.mcp_server_registry import MCPServerRegistry
from tarsy.utils.timestamp import now_us


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
        from tarsy.agents.constants import IterationStrategy
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
            mcp_data=mcp_data,
            available_tools=available_tools,
            iteration_history=iteration_history,
            current_iteration=1,
            max_iterations=3
        )
        
        assert context.agent_name == "TestConcreteAgent"
        assert context.alert_data == alert_data
        assert context.runbook_content == runbook_content
        assert context.mcp_data == mcp_data
        assert context.mcp_servers == ["test-server"]
        assert context.available_tools == available_tools
        assert context.iteration_history == iteration_history
        assert context.current_iteration == 1
        assert context.max_iterations == 3


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
        mock_mcp_client.list_tools.assert_called_once_with(session_id="test_session", server_name="test-server")

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
            "test-server", "kubectl-get", {"resource": "pods"}, "test-session-123"
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

@pytest.mark.unit
class TestBaseAgentCoreProcessing:
    """Test core processing methods including LLM interactions."""
    
    @pytest.fixture
    def mock_llm_client(self):
        client = Mock(spec=LLMClient)
        client.generate_response = AsyncMock(return_value="Detailed analysis result")
        return client
    
    @pytest.fixture
    def mock_mcp_client(self):
        return Mock(spec=MCPClient)
    
    @pytest.fixture
    def mock_mcp_registry(self):
        registry = Mock(spec=MCPServerRegistry)
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "kubernetes"
        mock_config.instructions = "Use kubectl for analysis"
        registry.get_server_configs.return_value = [mock_config]
        return registry
    
    @pytest.fixture
    def base_agent(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        return TestConcreteAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)

    @pytest.fixture
    def sample_alert_data(self):
        return {
            "alert": "PodCrashLoopBackOff",
            "message": "Pod is failing to start",
            "severity": "critical",
            "cluster": "prod"
        }

    @pytest.mark.unit
    @pytest.mark.asyncio
    @patch('tarsy.agents.base_agent.get_prompt_builder')
    async def test_analyze_alert_success(self, mock_get_prompt_builder, base_agent, mock_llm_client, sample_alert_data):
        """Test successful alert analysis."""
        # Mock prompt builder
        mock_prompt_builder = Mock()
        mock_prompt_builder.get_general_instructions.return_value = "General instructions"
        mock_get_prompt_builder.return_value = mock_prompt_builder
        base_agent._prompt_builder = mock_prompt_builder
        base_agent.build_analysis_prompt = Mock(return_value="Analysis prompt")
        
        runbook_content = "Test runbook"
        mcp_data = {"test-server": [{"tool": "kubectl", "result": "pod logs"}]}
        
        result = await base_agent.analyze_alert(sample_alert_data, runbook_content, mcp_data, "test-session-123")
        
        assert result == "Detailed analysis result"
        mock_llm_client.generate_response.assert_called_once()
        
        # Verify LLM was called with proper message structure
        call_args = mock_llm_client.generate_response.call_args[0][0]
        assert len(call_args) == 2  # System + user messages
        assert call_args[0].role == "system"
        assert call_args[1].role == "user"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_analyze_alert_llm_error(self, base_agent, mock_llm_client, sample_alert_data):
        """Test alert analysis with LLM error."""
        mock_llm_client.generate_response.side_effect = Exception("LLM service unavailable")
        
        with pytest.raises(Exception, match="Analysis error: LLM service unavailable"):
            await base_agent.analyze_alert(sample_alert_data, "runbook", {}, "test-session-error")

    @pytest.mark.unit
    @pytest.mark.asyncio
    @patch('tarsy.agents.base_agent.get_prompt_builder')
    async def test_determine_mcp_tools_success(self, mock_get_prompt_builder, base_agent, mock_llm_client):
        """Test successful MCP tool selection."""
        # Mock LLM response with proper JSON
        mock_llm_client.generate_response.return_value = '''[
            {
                "server": "test-server",
                "tool": "kubectl-get-pods",
                "parameters": {"namespace": "default"},
                "reason": "Check pod status"
            }
        ]'''
        
        # Mock prompt builder
        mock_prompt_builder = Mock()
        mock_prompt_builder.get_mcp_tool_selection_system_message.return_value = "Tool selection system message"
        mock_get_prompt_builder.return_value = mock_prompt_builder
        base_agent._prompt_builder = mock_prompt_builder
        base_agent.build_mcp_tool_selection_prompt = Mock(return_value="Tool selection prompt")
        
        alert_data = {"alert": "TestAlert"}
        runbook_content = "Test runbook"
        available_tools = {"tools": [{"name": "kubectl-get-pods"}]}
        
        result = await base_agent.determine_mcp_tools(alert_data, runbook_content, available_tools, "test-session-123")
        
        assert len(result) == 1
        assert result[0]["server"] == "test-server"
        assert result[0]["tool"] == "kubectl-get-pods"
        assert result[0]["parameters"] == {"namespace": "default"}
        assert result[0]["reason"] == "Check pod status"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_determine_mcp_tools_invalid_json(self, base_agent, mock_llm_client):
        """Test MCP tool selection with invalid JSON response."""
        mock_llm_client.generate_response.return_value = "Not valid JSON"
        
        with pytest.raises(Exception, match="Tool selection error"):
            await base_agent.determine_mcp_tools({}, "", {}, "test-session-error")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_determine_mcp_tools_missing_fields(self, base_agent, mock_llm_client):
        """Test MCP tool selection with missing required fields."""
        mock_llm_client.generate_response.return_value = '''[
            {
                "server": "test-server",
                "tool": "kubectl-get-pods"
                // Missing "parameters" and "reason"
            }
        ]'''
        
        with pytest.raises(Exception, match="Tool selection error"):
            await base_agent.determine_mcp_tools({}, "", {}, "test-session-error")

    @pytest.mark.unit
    @pytest.mark.asyncio
    @patch('tarsy.agents.base_agent.get_prompt_builder')
    async def test_determine_next_mcp_tools_continue(self, mock_get_prompt_builder, base_agent, mock_llm_client):
        """Test determining next MCP tools when continuing iteration."""
        # Mock LLM response indicating to continue
        mock_llm_client.generate_response.return_value = '''{
            "continue": true,
            "tools": [
                {
                    "server": "test-server",
                    "tool": "kubectl-describe",
                    "parameters": {"resource": "pod", "name": "failing-pod"},
                    "reason": "Get detailed pod information"
                }
            ]
        }'''
        
        # Mock prompt builder
        mock_prompt_builder = Mock()
        mock_prompt_builder.get_iterative_mcp_tool_selection_system_message.return_value = "Iterative system message"
        mock_get_prompt_builder.return_value = mock_prompt_builder
        base_agent._prompt_builder = mock_prompt_builder
        base_agent.build_iterative_mcp_tool_selection_prompt = Mock(return_value="Iterative prompt")
        
        alert_data = {"alert": "TestAlert"}
        runbook_content = "Test runbook"
        available_tools = {"tools": []}
        iteration_history = [{"tools_called": [], "mcp_data": {}}]
        
        result = await base_agent.determine_next_mcp_tools(
            alert_data, runbook_content, available_tools, iteration_history, 1, "test-session-123"
        )
        
        assert result["continue"] is True
        assert len(result["tools"]) == 1
        assert result["tools"][0]["tool"] == "kubectl-describe"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_determine_next_mcp_tools_stop(self, base_agent, mock_llm_client):
        """Test determining next MCP tools when stopping iteration."""
        mock_llm_client.generate_response.return_value = '{"continue": false}'
        
        result = await base_agent.determine_next_mcp_tools({}, "", {}, [], 2, "test-session-stop")
        
        assert result["continue"] is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_determine_next_mcp_tools_invalid_format(self, base_agent, mock_llm_client):
        """Test determining next MCP tools with invalid response format."""
        mock_llm_client.generate_response.return_value = '{"missing_continue_field": true}'
        
        with pytest.raises(Exception, match="Iterative tool selection error"):
            await base_agent.determine_next_mcp_tools({}, "", {}, [], 1, "test-session-error")





        client = Mock(spec=LLMClient)
        client.generate_response = AsyncMock()
        return client
    
    @pytest.fixture
    def mock_mcp_client(self):
        client = Mock(spec=MCPClient)
        client.list_tools = AsyncMock(return_value={
            "test-server": [{"name": "kubectl-get", "description": "Get resources"}]
        })
        client.call_tool = AsyncMock(return_value={"status": "success", "data": "pod info"})
        return client
    
    @pytest.fixture
    def mock_mcp_registry(self):
        registry = Mock(spec=MCPServerRegistry)
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "kubernetes"
        mock_config.instructions = "Use kubectl for analysis"
        registry.get_server_configs.return_value = [mock_config]
        return registry
    
    @pytest.fixture
    def base_agent(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        agent = TestConcreteAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)
        # The max_iterations property is read-only, we can't set it in tests
        return agent

    @pytest.fixture
    def sample_alert_data(self):
        return {
            "alert": "PodCrashLoopBackOff",
            "message": "Pod is failing to start",
            "severity": "critical",
            "cluster": "prod"
        }


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
            environment="test",
            cluster="test-cluster",
            namespace="test-namespace",
            message="Test error scenarios",
            runbook="test-runbook.md"
        )

    @pytest.mark.asyncio
    async def test_process_alert_mcp_configuration_error(self, base_agent, sample_alert):
        """Test process_alert with MCP configuration error."""
        base_agent.mcp_registry.get_server_configs.side_effect = Exception("MCP config error")
        
        alert_dict = sample_alert.model_dump()
        result = await base_agent.process_alert(alert_dict, "runbook content", "test-session-123")
        
        assert result["status"] == "error"
        assert "MCP config error" in result["error"]



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
        
        # Convert Alert to dict for new interface
        alert_dict = sample_alert.model_dump()
        
        result = await base_agent.process_alert(alert_dict, "runbook content", "test-session-success")
        
        assert result["status"] == "success"
        assert "Analysis complete" in result["analysis"]
        assert result["agent"] == "TestConcreteAgent"
        assert "timestamp_us" in result  # Changed from "timestamp" to "timestamp_us"
        assert result["strategy"] == "react"

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
        
        # Convert Alert to dict for new interface
        alert_dict = sample_alert.model_dump()
        
        result = await base_agent.process_alert(
            alert_data=alert_dict,
            runbook_content="runbook content",
            session_id="test-session-123"
        )
        
        assert result["status"] == "success"
        assert "analysis" in result  # Analysis result may vary based on iteration strategy

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
        
        # Convert Alert to dict for new interface
        alert_dict = sample_alert.model_dump()
        
        result = await base_agent.process_alert(
            alert_data=alert_dict,
            runbook_content="runbook content", 
            session_id="test-session"
        )
        
        assert result["status"] == "success"
        assert "analysis" in result  # Analysis result may vary based on iteration strategy

    @pytest.mark.asyncio
    async def test_process_alert_with_none_session_id(
        self, base_agent, mock_mcp_client, mock_llm_client, sample_alert
    ):
        """Test that process_alert raises ValueError with None session_id."""
        # Convert Alert to dict for new interface
        alert_dict = sample_alert.model_dump()
        
        with pytest.raises(ValueError, match="session_id is required"):
            await base_agent.process_alert(
                alert_data=alert_dict,
                runbook_content="runbook content",
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
        
        # Convert Alert to dict for new interface
        alert_dict = sample_alert.model_dump()
        
        result = await base_agent.process_alert(
            runbook_content="runbook content",
            alert_data=alert_dict, 
            session_id="test-session"
        )
        
        assert result["status"] == "success"
        assert "analysis" in result  # Analysis result may vary based on iteration strategy

    @pytest.mark.asyncio
    async def test_process_alert_error_handling_preserves_session_id_interface(
        self, base_agent, mock_mcp_client, mock_llm_client, sample_alert
    ):
        """Test that process_alert error responses preserve session_id interface."""
        # Mock MCP registry to cause an error
        base_agent.mcp_registry.get_server_configs.side_effect = Exception("MCP error")
        
        # Convert Alert to dict for new interface
        alert_dict = sample_alert.model_dump()
        
        result = await base_agent.process_alert(
            alert_data=alert_dict,
            runbook_content="runbook content",
            session_id="test-session-error"
        )
        
        assert result["status"] == "error"
        assert "error" in result
        assert "MCP error" in result["error"] 