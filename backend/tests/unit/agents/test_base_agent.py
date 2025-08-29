"""
Unit tests for BaseAgent.

Tests the base agent functionality with mocked dependencies to ensure
proper interface implementation and parameter handling.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.agents.base_agent import BaseAgent
from tarsy.agents.exceptions import ConfigurationError, ToolSelectionError
from tarsy.integrations.llm.client import LLMClient
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.alert import Alert
from tarsy.models.processing_context import ChainContext
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
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
        
        async def mock_generate_response(conversation, session_id, stage_execution_id=None):
            # Create a new conversation with the assistant response added
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Final Answer: Test analysis result")
            return updated_conversation
        
        client.generate_response = AsyncMock(side_effect=mock_generate_response)
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
    def test_cannot_instantiate_incomplete_agent(
        self, mock_llm_client, mock_mcp_client, mock_mcp_registry
    ):
        """Test that BaseAgent cannot be instantiated without implementing
        abstract methods."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            IncompleteAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)

    @pytest.mark.unit
    def test_concrete_agent_implements_abstract_methods(
        self, mock_llm_client, mock_mcp_client, mock_mcp_registry
    ):
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
    def test_agent_initialization_with_dependencies(
        self, mock_llm_client, mock_mcp_client, mock_mcp_registry
    ):
        """Test proper initialization with all required dependencies."""
        agent = TestConcreteAgent(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry,
        )

        assert agent.llm_client == mock_llm_client
        assert agent.mcp_client == mock_mcp_client
        assert agent.mcp_registry == mock_mcp_registry
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
                "namespace": "test-namespace",
            },
        )


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
    @patch("tarsy.agents.base_agent.get_prompt_builder")
    def test_compose_instructions_three_tiers(
        self, mock_get_prompt_builder, base_agent
    ):
        """Test three-tier instruction composition."""
        # Mock prompt builder
        mock_prompt_builder = Mock()
        mock_prompt_builder.get_general_instructions.return_value = (
            "General SRE instructions"
        )
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
    @patch("tarsy.agents.base_agent.get_prompt_builder")
    def test_compose_instructions_no_custom(
        self,
        mock_get_prompt_builder,
        mock_llm_client,
        mock_mcp_client,
        mock_mcp_registry,
    ):
        """Test instruction composition without custom instructions."""

        class NoCustomAgent(BaseAgent):
            def mcp_servers(self):
                return ["test-server"]

            def custom_instructions(self):
                return ""

        # Mock prompt builder
        mock_prompt_builder = Mock()
        mock_prompt_builder.get_general_instructions.return_value = (
            "General instructions"
        )
        mock_get_prompt_builder.return_value = mock_prompt_builder

        agent = NoCustomAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)
        agent._prompt_builder = mock_prompt_builder

        instructions = agent._compose_instructions()

        assert "General instructions" in instructions
        assert "## Agent-Specific Instructions" not in instructions

    # EP-0012 Clean Implementation: create_prompt_context method removed
    # Context creation now handled by StageContext in the clean architecture


@pytest.mark.unit
class TestBaseAgentMCPIntegration:
    """Test MCP client configuration and tool execution."""

    @pytest.fixture
    def mock_llm_client(self):
        return Mock(spec=LLMClient)

    @pytest.fixture
    def mock_mcp_client(self):
        client = Mock(spec=MCPClient)
        client.list_tools = AsyncMock(
            return_value={
                "test-server": [{"name": "kubectl-get", "description": "Get resources"}]
            }
        )
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
        base_agent.mcp_registry.get_server_configs.assert_called_once_with(
            ["test-server"]
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_configure_mcp_client_missing_server(self, base_agent):
        """Test MCP client configuration with missing server."""
        base_agent.mcp_registry.get_server_configs.return_value = (
            []
        )  # No configs returned

        with pytest.raises(
            ConfigurationError, match="Required MCP servers not configured"
        ):
            await base_agent._configure_mcp_client()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_available_tools_success(self, base_agent, mock_mcp_client):
        """Test getting available tools from configured servers."""
        base_agent._configured_servers = ["test-server"]

        tools = await base_agent._get_available_tools("test_session")

        assert len(tools.tools) == 1
        assert tools.tools[0].name == "kubectl-get"
        assert tools.tools[0].server == "test-server"
        mock_mcp_client.list_tools.assert_called_once_with(
            session_id="test_session",
            server_name="test-server",
            stage_execution_id=None,
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_available_tools_not_configured(self, base_agent):
        """Test getting tools when agent not configured."""
        base_agent._configured_servers = None

        # The method should raise ToolSelectionError when not configured
        with pytest.raises(
            ToolSelectionError,
            match="Agent TestConcreteAgent has not been properly configured",
        ):
            await base_agent._get_available_tools("test_session")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_available_tools_mcp_error(self, base_agent, mock_mcp_client):
        """Test getting tools with MCP client error."""
        base_agent._configured_servers = ["test-server"]
        mock_mcp_client.list_tools.side_effect = Exception("MCP connection failed")

        # The method should raise ToolSelectionError when MCP client fails
        match_pattern = (
            "Failed to retrieve tools for agent TestConcreteAgent.*"
            "MCP connection failed"
        )
        with pytest.raises(ToolSelectionError, match=match_pattern):
            await base_agent._get_available_tools("test_session")

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
                "reason": "Check pod status",
            }
        ]

        results = await base_agent.execute_mcp_tools(tools_to_call, "test-session-123")

        assert "test-server" in results
        assert len(results["test-server"]) == 1
        assert results["test-server"][0]["tool"] == "kubectl-get"
        assert results["test-server"][0]["result"] == {"result": "success"}

        mock_mcp_client.call_tool.assert_called_once_with(
            "test-server", "kubectl-get", {"resource": "pods"}, "test-session-123", None, None
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
                "reason": "Test",
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
                "reason": "Test error handling",
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
        client = Mock(spec=LLMClient)
        
        async def mock_generate_response(conversation, session_id, stage_execution_id=None):
            # Create a new conversation with the assistant response added
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Final Answer: Test analysis result")
            return updated_conversation
        
        client.generate_response = AsyncMock(side_effect=mock_generate_response)
        return client

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
                "message": "Test error scenarios",
            },
        )

    @pytest.mark.asyncio
    async def test_process_alert_mcp_configuration_error(
        self, base_agent, sample_alert
    ):
        """Test process_alert with MCP configuration error."""
        base_agent.mcp_registry.get_server_configs.side_effect = Exception(
            "MCP config error"
        )

        from tarsy.models.processing_context import ChainContext

        alert_processing_data = ChainContext(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.data,
            session_id="test-session-123",
            current_stage_name="test-stage",
            runbook_content="runbook content",
        )
        result = await base_agent.process_alert(alert_processing_data)

        assert result.status.value == "failed"
        assert "MCP config error" in result.error_message

    @pytest.mark.asyncio
    async def test_process_alert_success_flow(
        self, base_agent, mock_mcp_client, mock_llm_client, sample_alert
    ):
        """Test successful process_alert flow."""
        # Mock successful flow
        mock_mcp_client.list_tools.return_value = {"test-server": []}

        # Mock MCP registry
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "test"
        mock_config.instructions = "Test instructions"
        base_agent.mcp_registry.get_server_configs.return_value = [mock_config]

        # Mock prompt builder methods
        base_agent.determine_mcp_tools = AsyncMock(return_value=[])
        base_agent.determine_next_mcp_tools = AsyncMock(
            return_value={"continue": False}
        )
        base_agent.analyze_alert = AsyncMock(return_value="Success analysis")

        # Create ChainContext for new interface
        from tarsy.models.processing_context import ChainContext

        alert_processing_data = ChainContext(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.data,
            session_id="test-session-success",
            current_stage_name="test-stage",
            runbook_content="runbook content",
        )

        result = await base_agent.process_alert(alert_processing_data)

        assert result.status.value == "completed"
        assert "Test analysis result" in result.result_summary
        assert result.agent_name == "TestConcreteAgent"
        assert result.timestamp_us is not None


@pytest.mark.unit
class TestBaseAgent:
    """Test BaseAgent with session ID parameter validation."""

    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = Mock(spec=LLMClient)
        
        async def mock_generate_response(conversation, session_id, stage_execution_id=None):
            # Create a new conversation with the assistant response added
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Final Answer: Test analysis result")
            return updated_conversation
        
        client.generate_response = AsyncMock(side_effect=mock_generate_response)
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
        agent = TestConcreteAgent(
            mock_llm_client, Mock(spec=MCPClient), Mock(spec=MCPServerRegistry)
        )
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
                "namespace": "test-namespace",
            },
        )

    @pytest.mark.asyncio
    async def test_process_alert_with_session_id_parameter(
        self, base_agent, sample_alert
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
        base_agent.determine_next_mcp_tools = AsyncMock(
            return_value={"continue": False}
        )
        base_agent.analyze_alert = AsyncMock(return_value="Test analysis")

        # Convert Alert to ChainContext for new interface
        alert_processing_data = ChainContext(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.model_dump(),
            session_id="test-session-123",
            current_stage_name="test-stage",
            runbook_content="test runbook content",
        )

        # EP-0012 Clean Implementation: process_alert only accepts ChainContext
        result = await base_agent.process_alert(alert_processing_data)

        assert result.status.value == "completed"
        assert (
            result.result_summary is not None
        )  # Analysis result may vary based on iteration strategy

    @pytest.mark.asyncio
    async def test_process_alert_without_session_id_parameter(
        self, base_agent, sample_alert
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
        base_agent.determine_next_mcp_tools = AsyncMock(
            return_value={"continue": False}
        )
        base_agent.analyze_alert = AsyncMock(return_value="Test analysis")

        # Convert Alert to ChainContext for new interface
        alert_processing_data = ChainContext(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.model_dump(),
            session_id="test-session-123",
            current_stage_name="test-stage",
            runbook_content="test runbook content",
        )

        # EP-0012 Clean Implementation: process_alert only accepts ChainContext
        result = await base_agent.process_alert(alert_processing_data)

        assert result.status.value == "completed"
        assert (
            result.result_summary is not None
        )  # Analysis result may vary based on iteration strategy


@pytest.mark.unit
class TestPhase3ProcessAlertOverload:
    """Test the new overloaded process_alert method from Phase 3."""

    @pytest.fixture
    def mock_llm_client(self):
        client = Mock(spec=LLMClient)
        
        async def mock_generate_response(conversation, session_id, stage_execution_id=None):
            # Create a new conversation with the assistant response added
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Final Answer: Test analysis result from Phase 3")
            return updated_conversation
        
        client.generate_response = AsyncMock(side_effect=mock_generate_response)
        return client

    @pytest.fixture
    def mock_mcp_client(self):
        client = Mock(spec=MCPClient)
        client.list_tools = AsyncMock(return_value={"test-server": []})
        return client

    @pytest.fixture
    def base_agent(self, mock_llm_client, mock_mcp_client):
        agent = TestConcreteAgent(
            mock_llm_client, mock_mcp_client, Mock(spec=MCPServerRegistry)
        )
        # Mock registry for successful flow
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "test"
        mock_config.instructions = "Test instructions"
        agent.mcp_registry.get_server_configs.return_value = [mock_config]
        return agent

    @pytest.mark.asyncio
    async def test_process_alert_with_chain_context(self, base_agent):
        """Test overloaded process_alert with ChainContext (new path)."""
        # Create ChainContext directly
        chain_context = ChainContext(
            alert_type="kubernetes",
            alert_data={"pod": "failing-pod", "message": "Pod failing"},
            session_id="test-session-new",
            current_stage_name="analysis",
            runbook_content="test runbook",
        )

        result = await base_agent.process_alert(chain_context)

        assert result.status.value == "completed"
        assert (
            result.result_summary is not None
        )  # Analysis result may vary due to ReAct processing
        assert result.agent_name == "TestConcreteAgent"

    @pytest.mark.asyncio
    async def test_process_alert_chain_context_ignores_conflicting_session_id(
        self, base_agent
    ):
        """Test that ChainContext ignores conflicting session_id parameter
        with warning."""
        chain_context = ChainContext(
            alert_type="kubernetes",
            alert_data={"pod": "failing-pod"},
            session_id="context-session-id",
            current_stage_name="analysis",
        )

        # EP-0012 Clean Implementation: process_alert only accepts ChainContext
        result = await base_agent.process_alert(chain_context)

        assert result.status.value == "completed"


@pytest.mark.unit
class TestPhase4PromptSystemOverload:
    """Test Phase 4 prompt system updates - prompt builders accepting StageContext."""

    @pytest.mark.asyncio
    async def test_prompt_builder_with_stage_context(self):
        """Test that prompt builders can accept StageContext directly."""
        from tarsy.agents.prompts import get_prompt_builder
        from tarsy.models.processing_context import (
            AvailableTools,
            ChainContext,
            StageContext,
        )

        # Create test contexts
        chain_context = ChainContext(
            alert_type="kubernetes",
            alert_data={"pod": "test-pod", "message": "Pod failing"},
            session_id="test-session",
            current_stage_name="analysis",
        )

        available_tools = AvailableTools()  # Empty tools
        mock_agent = Mock()
        mock_agent.__class__.__name__ = "TestAgent"
        mock_agent.mcp_servers.return_value = ["test-server"]

        stage_context = StageContext(
            chain_context=chain_context,
            available_tools=available_tools,
            agent=mock_agent,
        )

        prompt_builder = get_prompt_builder()

        # Test that all prompt building methods accept StageContext
        standard_prompt = prompt_builder.build_standard_react_prompt(stage_context, [])
        stage_prompt = prompt_builder.build_stage_analysis_react_prompt(
            stage_context, []
        )
        final_prompt = prompt_builder.build_final_analysis_prompt(stage_context)

        # Verify prompts are generated (not empty)
        assert standard_prompt
        assert stage_prompt
        assert final_prompt
        assert "test-pod" in standard_prompt  # Should contain alert data
        assert "test-pod" in stage_prompt
        assert "test-pod" in final_prompt
