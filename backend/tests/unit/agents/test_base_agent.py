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
from mcp.types import Tool


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
                "test-server": [Tool(
                    name="kubectl-get", 
                    description="Get resources",
                    inputSchema={"type": "object", "properties": {}}
                )]
            }
        )
        
        # Mock call_tool with validation logic
        async def mock_call_tool_with_validation(
            server_name, tool_name, parameters, session_id=None,
            stage_execution_id=None, investigation_conversation=None,
            mcp_selection=None, configured_servers=None
        ):
            # Validate like MCPClient does
            if mcp_selection is not None:
                selected_server = next(
                    (s for s in mcp_selection.servers if s.name == server_name), None
                )
                if selected_server is None:
                    allowed_servers = [s.name for s in mcp_selection.servers]
                    raise ValueError(
                        f"Tool '{tool_name}' from server '{server_name}' not allowed by MCP selection. "
                        f"Allowed servers: {allowed_servers}"
                    )
                if selected_server.tools is not None and len(selected_server.tools) > 0:
                    if tool_name not in selected_server.tools:
                        raise ValueError(
                            f"Tool '{tool_name}' not allowed by MCP selection. "
                            f"Allowed tools from '{server_name}': {selected_server.tools}"
                        )
            elif configured_servers and server_name not in configured_servers:
                raise ValueError(
                    f"Tool '{tool_name}' from server '{server_name}' not allowed by agent configuration. "
                    f"Configured servers: {configured_servers}"
                )
            return {"result": "success"}
        
        client.call_tool = AsyncMock(side_effect=mock_call_tool_with_validation)
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
        assert tools.tools[0].tool.name == "kubectl-get"
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
    async def test_get_available_tools_with_server_selection(
        self, base_agent, mock_mcp_client, mock_mcp_registry
    ):
        """Test getting tools with user-provided server selection (all tools from servers)."""
        from tarsy.models.mcp_selection_models import MCPSelectionConfig, MCPServerSelection
        
        base_agent._configured_servers = ["default-server"]
        
        # Mock registry to return available servers
        mock_mcp_registry.get_all_server_ids.return_value = ["kubernetes-server", "argocd-server", "default-server"]
        
        # Mock list_tools to return different tools for different servers
        async def mock_list_tools_side_effect(session_id, server_name, stage_execution_id=None):
            if server_name == "kubernetes-server":
                return {
                    "kubernetes-server": [
                        Tool(name="kubectl-get", description="Get Kubernetes resources", inputSchema={}),
                        Tool(name="kubectl-describe", description="Describe Kubernetes resources", inputSchema={})
                    ]
                }
            elif server_name == "argocd-server":
                return {
                    "argocd-server": [
                        Tool(name="get-application", description="Get ArgoCD application", inputSchema={})
                    ]
                }
            return {}
        
        mock_mcp_client.list_tools.side_effect = mock_list_tools_side_effect
        
        # Create MCP selection (all tools from selected servers)
        mcp_selection = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="kubernetes-server"),
                MCPServerSelection(name="argocd-server")
            ]
        )
        
        # Get tools with selection
        tools = await base_agent._get_available_tools("test_session", mcp_selection=mcp_selection)
        
        # Verify we got tools from both selected servers (not the default one)
        assert len(tools.tools) == 3
        tool_names = {tool.tool.name for tool in tools.tools}
        assert tool_names == {"kubectl-get", "kubectl-describe", "get-application"}
        
        # Verify servers
        servers = {tool.server for tool in tools.tools}
        assert servers == {"kubernetes-server", "argocd-server"}
        
        # Verify list_tools was called for selected servers
        assert mock_mcp_client.list_tools.call_count == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_available_tools_with_tool_selection(
        self, base_agent, mock_mcp_client, mock_mcp_registry
    ):
        """Test getting tools with specific tool filtering."""
        from tarsy.models.mcp_selection_models import MCPSelectionConfig, MCPServerSelection
        
        base_agent._configured_servers = ["default-server"]
        
        # Mock registry
        mock_mcp_registry.get_all_server_ids.return_value = ["kubernetes-server", "argocd-server"]
        
        # Mock list_tools
        async def mock_list_tools_side_effect(session_id, server_name, stage_execution_id=None):
            if server_name == "kubernetes-server":
                return {
                    "kubernetes-server": [
                        Tool(name="kubectl-get", description="Get resources", inputSchema={}),
                        Tool(name="kubectl-describe", description="Describe resources", inputSchema={}),
                        Tool(name="kubectl-logs", description="Get logs", inputSchema={})
                    ]
                }
            elif server_name == "argocd-server":
                return {
                    "argocd-server": [
                        Tool(name="get-application", description="Get app", inputSchema={}),
                        Tool(name="sync-application", description="Sync app", inputSchema={})
                    ]
                }
            return {}
        
        mock_mcp_client.list_tools.side_effect = mock_list_tools_side_effect
        
        # Create MCP selection with specific tools
        mcp_selection = MCPSelectionConfig(
            servers=[
                MCPServerSelection(
                    name="kubernetes-server",
                    tools=["kubectl-get"]  # Only request specific tool
                ),
                MCPServerSelection(
                    name="argocd-server",
                    tools=["get-application"]
                )
            ]
        )
        
        # Get tools with selection
        tools = await base_agent._get_available_tools("test_session", mcp_selection=mcp_selection)
        
        # Verify we got only the requested tools
        assert len(tools.tools) == 2
        tool_names = {tool.tool.name for tool in tools.tools}
        assert tool_names == {"kubectl-get", "get-application"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_available_tools_with_mixed_selection(
        self, base_agent, mock_mcp_client, mock_mcp_registry
    ):
        """Test mixed selection: all tools from one server, specific tools from another."""
        from tarsy.models.mcp_selection_models import MCPSelectionConfig, MCPServerSelection
        
        base_agent._configured_servers = ["default-server"]
        
        # Mock registry
        mock_mcp_registry.get_all_server_ids.return_value = ["kubernetes-server", "argocd-server"]
        
        # Mock list_tools
        async def mock_list_tools_side_effect(session_id, server_name, stage_execution_id=None):
            if server_name == "kubernetes-server":
                return {
                    "kubernetes-server": [
                        Tool(name="kubectl-get", description="Get resources", inputSchema={}),
                        Tool(name="kubectl-describe", description="Describe resources", inputSchema={})
                    ]
                }
            elif server_name == "argocd-server":
                return {
                    "argocd-server": [
                        Tool(name="get-application", description="Get app", inputSchema={}),
                        Tool(name="sync-application", description="Sync app", inputSchema={})
                    ]
                }
            return {}
        
        mock_mcp_client.list_tools.side_effect = mock_list_tools_side_effect
        
        # Mixed selection: all tools from kubernetes-server, specific from argocd-server
        mcp_selection = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="kubernetes-server"),  # All tools (no tools field)
                MCPServerSelection(name="argocd-server", tools=["get-application"])  # Specific tool
            ]
        )
        
        # Get tools
        tools = await base_agent._get_available_tools("test_session", mcp_selection=mcp_selection)
        
        # Verify results
        assert len(tools.tools) == 3
        tool_names = {tool.tool.name for tool in tools.tools}
        assert tool_names == {"kubectl-get", "kubectl-describe", "get-application"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_available_tools_invalid_server_selection(
        self, base_agent, mock_mcp_client, mock_mcp_registry
    ):
        """Test error when selected server doesn't exist."""
        from tarsy.models.mcp_selection_models import MCPSelectionConfig, MCPServerSelection
        from tarsy.agents.exceptions import MCPServerSelectionError
        
        base_agent._configured_servers = ["default-server"]
        
        # Mock registry with available servers
        mock_mcp_registry.get_all_server_ids.return_value = ["kubernetes-server", "argocd-server"]
        
        # Try to select non-existent server
        mcp_selection = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="non-existent-server")
            ]
        )
        
        # Should raise MCPServerSelectionError
        with pytest.raises(MCPServerSelectionError) as exc_info:
            await base_agent._get_available_tools("test_session", mcp_selection=mcp_selection)
        
        # Verify error details
        error = exc_info.value
        assert "non-existent-server" in str(error)
        assert error.requested_servers == ["non-existent-server"]
        assert set(error.available_servers) == {"argocd-server", "kubernetes-server"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_available_tools_invalid_tool_selection(
        self, base_agent, mock_mcp_client, mock_mcp_registry
    ):
        """Test error when selected tool doesn't exist on server."""
        from tarsy.models.mcp_selection_models import MCPSelectionConfig, MCPServerSelection
        from tarsy.agents.exceptions import MCPToolSelectionError
        
        base_agent._configured_servers = ["default-server"]
        
        # Mock registry
        mock_mcp_registry.get_all_server_ids.return_value = ["kubernetes-server"]
        
        # Mock list_tools with available tools
        mock_mcp_client.list_tools.return_value = {
            "kubernetes-server": [
                Tool(name="kubectl-get", description="Get resources", inputSchema={}),
                Tool(name="kubectl-describe", description="Describe resources", inputSchema={})
            ]
        }
        
        # Try to select non-existent tool
        mcp_selection = MCPSelectionConfig(
            servers=[
                MCPServerSelection(
                    name="kubernetes-server",
                    tools=["non-existent-tool"]
                )
            ]
        )
        
        # Should raise MCPToolSelectionError
        with pytest.raises(MCPToolSelectionError) as exc_info:
            await base_agent._get_available_tools("test_session", mcp_selection=mcp_selection)
        
        # Verify error details
        error = exc_info.value
        assert error.server_name == "kubernetes-server"
        assert error.requested_tools == ["non-existent-tool"]
        assert set(error.available_tools) == {"kubectl-describe", "kubectl-get"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_available_tools_multiple_invalid_servers(
        self, base_agent, mock_mcp_client, mock_mcp_registry
    ):
        """Test error message when multiple servers are invalid."""
        from tarsy.models.mcp_selection_models import MCPSelectionConfig, MCPServerSelection
        from tarsy.agents.exceptions import MCPServerSelectionError
        
        base_agent._configured_servers = ["default-server"]
        
        # Mock registry
        mock_mcp_registry.get_all_server_ids.return_value = ["kubernetes-server"]
        
        # Try to select multiple non-existent servers
        mcp_selection = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="bad-server-1"),
                MCPServerSelection(name="bad-server-2"),
                MCPServerSelection(name="kubernetes-server")  # This one is valid
            ]
        )
        
        # Should raise MCPServerSelectionError
        with pytest.raises(MCPServerSelectionError) as exc_info:
            await base_agent._get_available_tools("test_session", mcp_selection=mcp_selection)
        
        # Verify error includes all missing servers
        error = exc_info.value
        assert "bad-server-1" in str(error)
        assert "bad-server-2" in str(error)

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
            "test-server", "kubectl-get", {"resource": "pods"}, "test-session-123", None, None, None, ["test-server"]
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
        assert "not allowed" in results["forbidden-server"][0]["error"]
        assert "configured servers" in results["forbidden-server"][0]["error"].lower()

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

        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type=sample_alert.alert_type,
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data=sample_alert.data
        )
        alert_processing_data = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="test-stage"
        )
        alert_processing_data.runbook_content = "runbook content"
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

        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type=sample_alert.alert_type,
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data=sample_alert.data
        )
        alert_processing_data = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-success",
            current_stage_name="test-stage"
        )
        alert_processing_data.runbook_content = "runbook content"

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
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type=sample_alert.alert_type,
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data=sample_alert.model_dump()
        )
        alert_processing_data = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="test-stage"
        )
        alert_processing_data.runbook_content = "test runbook content"

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
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type=sample_alert.alert_type,
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data=sample_alert.model_dump()
        )
        alert_processing_data = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="test-stage"
        )
        alert_processing_data.runbook_content = "test runbook content"

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
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"pod": "failing-pod", "message": "Pod failing"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-new",
            current_stage_name="analysis"
        )
        chain_context.runbook_content = "test runbook"

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
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"pod": "failing-pod"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="context-session-id",
            current_stage_name="analysis"
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
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"pod": "test-pod", "message": "Pod failing"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="analysis"
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


@pytest.mark.unit
class TestBaseAgentSummarization:
    """Test BaseAgent summarization integration (EP-0015)."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        client = Mock(spec=LLMClient)
        client.generate_response = AsyncMock()
        return client
    
    @pytest.fixture
    def mock_mcp_client(self):
        """Create mock MCP client."""
        client = Mock(spec=MCPClient)
        client.list_tools = AsyncMock(return_value={"test-server": []})
        client.call_tool = AsyncMock(return_value={"result": "success"})
        return client
    
    @pytest.fixture
    def mock_mcp_registry(self):
        """Create mock MCP registry."""
        registry = Mock(spec=MCPServerRegistry)
        mock_config = Mock()
        mock_config.server_id = "test-server"
        mock_config.server_type = "test"
        mock_config.instructions = "Test server instructions"
        registry.get_server_configs.return_value = [mock_config]
        return registry
    
    @pytest.mark.asyncio
    async def test_execute_mcp_tools_with_investigation_conversation(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test execute_mcp_tools passes investigation conversation for summarization."""
        agent = TestConcreteAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)
        agent._configured_servers = ["test-server"]
        
        # Create sample investigation conversation
        investigation_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are an expert SRE"),
            LLMMessage(role=MessageRole.USER, content="Investigate the alert"),
            LLMMessage(role=MessageRole.ASSISTANT, content="I need to check system status")
        ])
        
        tools_to_call = [
            {
                "server": "test-server",
                "tool": "kubectl-get",
                "parameters": {"resource": "pods"},
                "reason": "Check pod status with context",
            }
        ]
        
        results = await agent.execute_mcp_tools(
            tools_to_call, 
            "test-session-summarization",
            investigation_conversation
        )
        
        assert "test-server" in results
        assert len(results["test-server"]) == 1
        assert results["test-server"][0]["tool"] == "kubectl-get"
        
        # Verify MCP client was called with investigation conversation
        mock_mcp_client.call_tool.assert_called_once_with(
            "test-server", "kubectl-get", {"resource": "pods"}, "test-session-summarization", None, investigation_conversation, None, ["test-server"]
        )

    @pytest.mark.asyncio
    async def test_configure_mcp_client_creates_summarizer(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test that configure_mcp_client creates and injects summarizer when LLM client available."""
        agent = TestConcreteAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)
        
        # Act
        await agent._configure_mcp_client()
        
        # Assert - Should configure servers and inject summarizer
        assert agent._configured_servers == ["test-server"]
        
        # Verify summarizer was injected into MCP client
        assert hasattr(agent.mcp_client, 'summarizer')
        assert agent.mcp_client.summarizer is not None

    @pytest.mark.asyncio
    async def test_configure_mcp_client_no_summarizer_without_llm(self, mock_mcp_client, mock_mcp_registry):
        """Test that configure_mcp_client works without LLM client (no summarizer injection)."""
        # Create agent without LLM client
        agent = TestConcreteAgent(
            llm_client=None,  # No LLM client
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        await agent._configure_mcp_client()
        
        # Should still configure servers but not inject summarizer
        assert agent._configured_servers == ["test-server"]
        # Summarizer should remain None or not be set
        summarizer = getattr(agent.mcp_client, 'summarizer', None)
        assert summarizer is None

    @pytest.mark.asyncio
    async def test_execute_mcp_tools_backward_compatibility_no_conversation(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test execute_mcp_tools maintains backward compatibility without investigation conversation."""
        agent = TestConcreteAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)
        agent._configured_servers = ["test-server"]
        
        tools_to_call = [
            {
                "server": "test-server",
                "tool": "kubectl-get", 
                "parameters": {"resource": "nodes"},
                "reason": "Check node status",
            }
        ]
        
        # Act - Call without investigation conversation (backward compatibility)
        results = await agent.execute_mcp_tools(tools_to_call, "test-session-compat")
        
        # Assert
        assert "test-server" in results
        assert len(results["test-server"]) == 1
        
        # Verify MCP client was called without investigation conversation (None)
        mock_mcp_client.call_tool.assert_called_once_with(
            "test-server", "kubectl-get", {"resource": "nodes"}, "test-session-compat", None, None, None, ["test-server"]
        )
