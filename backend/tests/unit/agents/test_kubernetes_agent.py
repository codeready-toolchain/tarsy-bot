"""
Comprehensive unit tests for KubernetesAgent.

Tests the Kubernetes-specialized agent implementation including abstract method
implementations, Kubernetes-specific functionality, and integration with BaseAgent.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.agents.exceptions import ConfigurationError, ToolSelectionError
from tarsy.agents.kubernetes_agent import KubernetesAgent
from tarsy.integrations.llm.client import LLMClient
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.agent_config import MCPServerConfigModel
from tarsy.models.alert import Alert
from tarsy.models.constants import IterationStrategy
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.services.mcp_server_registry import MCPServerRegistry
from mcp.types import Tool
from tarsy.utils.timestamp import now_us


@pytest.mark.unit
class TestKubernetesAgentInitialization:
    """Test KubernetesAgent initialization and dependency injection."""
    
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
        client.list_tools = AsyncMock(return_value={"kubernetes-server": []})
        client.call_tool = AsyncMock(return_value={"result": "test"})
        return client
    
    @pytest.fixture
    def mock_mcp_registry(self):
        """Create mock MCP registry."""
        registry = Mock(spec=MCPServerRegistry)
        server_config = MCPServerConfigModel(
            server_id="kubernetes-server",
            server_type="kubernetes",
            enabled=True,
            transport={"type": "stdio", "command": "npx", "args": ["-y", "kubernetes-mcp-server@latest"]},
            instructions="Kubernetes server instructions"
        )
        registry.get_server_configs.return_value = [server_config]
        return registry
    
    def test_initialization_with_required_dependencies(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test KubernetesAgent initialization with all required dependencies."""
        agent = KubernetesAgent(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        assert agent.llm_client is mock_llm_client
        assert agent.mcp_client is mock_mcp_client
        assert agent.mcp_registry is mock_mcp_registry
        assert agent._configured_servers is None
        # Verify default iteration strategy
        assert agent.iteration_strategy == IterationStrategy.REACT
    
    def test_initialization_with_custom_iteration_strategy(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test KubernetesAgent initialization with custom iteration strategy."""
        agent = KubernetesAgent(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry,
            iteration_strategy=IterationStrategy.REACT_STAGE
        )
        
        assert agent.iteration_strategy == IterationStrategy.REACT_STAGE
    
    def test_inheritance_from_base_agent(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test that KubernetesAgent properly inherits from BaseAgent."""
        agent = KubernetesAgent(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        # Check that it has BaseAgent attributes and methods
        assert hasattr(agent, 'max_iterations')
        assert hasattr(agent, 'process_alert')

        assert hasattr(agent, '_compose_instructions')
    
    def test_multiple_instances_independence(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test that multiple KubernetesAgent instances are independent."""
        agent1 = KubernetesAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)
        agent2 = KubernetesAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)
        
        assert agent1 is not agent2
        
        # Verify they are independent objects 
        assert agent1.llm_client is agent2.llm_client  # Same clients (shared)
        assert agent1.mcp_client is agent2.mcp_client
        assert agent1._configured_servers is agent2._configured_servers  # Both None initially

@pytest.mark.unit
class TestKubernetesAgentAbstractMethods:
    """Test implementation of abstract methods from BaseAgent."""
    
    @pytest.fixture
    def kubernetes_agent(self):
        """Create a KubernetesAgent instance for testing."""
        mock_llm = Mock(spec=LLMClient)
        mock_mcp = Mock(spec=MCPClient)
        mock_registry = Mock(spec=MCPServerRegistry)
        return KubernetesAgent(mock_llm, mock_mcp, mock_registry)
    
    def test_mcp_servers_returns_kubernetes_server(self, kubernetes_agent):
        """Test that mcp_servers() returns kubernetes-server."""
        servers = kubernetes_agent.mcp_servers()
        
        assert isinstance(servers, list)
        assert servers == ["kubernetes-server"]
        assert len(servers) == 1
    
    def test_mcp_servers_consistent_calls(self, kubernetes_agent):
        """Test that mcp_servers() returns consistent results across calls."""
        servers1 = kubernetes_agent.mcp_servers()
        servers2 = kubernetes_agent.mcp_servers()
        
        assert servers1 == servers2
        assert servers1 is not servers2  # Should be different list instances
    
    def test_custom_instructions_returns_empty_string(self, kubernetes_agent):
        """Test that custom_instructions() returns empty string."""
        instructions = kubernetes_agent.custom_instructions()
        
        assert isinstance(instructions, str)
        assert instructions == ""
    
    def test_custom_instructions_consistent_calls(self, kubernetes_agent):
        """Test that custom_instructions() returns consistent results."""
        instructions1 = kubernetes_agent.custom_instructions()
        instructions2 = kubernetes_agent.custom_instructions()
        
        assert instructions1 == instructions2

@pytest.mark.unit
class TestKubernetesAgentPromptBuilding:
    """Test Kubernetes-specific prompt building functionality."""
    
    @pytest.fixture
    def kubernetes_agent(self):
        """Create a KubernetesAgent instance for testing."""
        mock_llm = Mock(spec=LLMClient)
        mock_mcp = Mock(spec=MCPClient)
        mock_registry = Mock(spec=MCPServerRegistry)
        return KubernetesAgent(mock_llm, mock_mcp, mock_registry)
    
    @pytest.fixture
    def sample_alert_data(self):
        """Create sample alert data for testing."""
        return {
            "alert": "PodCrashLooping",
            "message": "Pod in namespace production is crash looping",
            "environment": "production",
            "severity": "critical",
            "cluster": "prod-cluster",
            "namespace": "production",
            "pod": "app-deployment-12345",
            "timestamp": "2024-01-01T12:00:00Z",
            "context": {"labels": {"app": "web-service"}}
        }
    
    @pytest.fixture
    def sample_available_tools(self):
        """Create sample available tools for testing."""
        return {
            "tools": [
                {
                    "name": "get_pod_status",
                    "description": "Get status of a specific pod",
                    "server": "kubernetes-server",
                    "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}}}
                },
                {
                    "name": "get_namespace_events",
                    "description": "Get events in a namespace",
                    "server": "kubernetes-server",
                    "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}}}
                }
            ]
        }

@pytest.mark.unit
class TestKubernetesAgentInheritedFunctionality:
    """Test that inherited BaseAgent functionality works correctly through KubernetesAgent."""
    
    @pytest.fixture
    def mock_dependencies(self):
        """Create all mocked dependencies."""
        mock_llm = Mock(spec=LLMClient)
        mock_llm.generate_response = AsyncMock(return_value="Test analysis result")
        
        mock_mcp = Mock(spec=MCPClient)
        mock_mcp.list_tools = AsyncMock(return_value={"kubernetes-server": []})
        mock_mcp.call_tool = AsyncMock(return_value={"result": "test"})
        
        mock_registry = Mock(spec=MCPServerRegistry)
        server_config = MCPServerConfigModel(
            server_id="kubernetes-server",
            server_type="kubernetes",
            enabled=True,
            transport={"type": "stdio", "command": "npx"},
            instructions="K8s instructions"
        )
        mock_registry.get_server_configs.return_value = [server_config]
        
        return mock_llm, mock_mcp, mock_registry
    
    @pytest.fixture
    def kubernetes_agent(self, mock_dependencies):
        """Create KubernetesAgent with mocked dependencies."""
        mock_llm, mock_mcp, mock_registry = mock_dependencies
        return KubernetesAgent(mock_llm, mock_mcp, mock_registry)
    
    @pytest.fixture
    def sample_alert(self):
        """Create sample Kubernetes alert for testing."""
        return Alert(
            alert_type="kubernetes",
            runbook="https://github.com/company/runbooks/blob/main/k8s.md",
            timestamp=now_us(),
            data={
                "severity": "critical",
                "alert": "PodCrashLoopBackOff",
                "environment": "production",
                "cluster": "main-cluster",
                "namespace": "default",
                "message": "Pod is in CrashLoopBackOff state"
            }
        )
    
    def test_kubernetes_mcp_servers(self, kubernetes_agent):
        """Test that KubernetesAgent returns appropriate MCP servers."""
        servers = kubernetes_agent.mcp_servers()
        
        assert isinstance(servers, list)
        assert "kubernetes-server" in servers
    
    @pytest.mark.asyncio
    async def test_configure_mcp_client_with_kubernetes_server(self, kubernetes_agent):
        """Test that _configure_mcp_client sets up kubernetes-server correctly."""
        await kubernetes_agent._configure_mcp_client()
        
        assert kubernetes_agent._configured_servers == ["kubernetes-server"]
        kubernetes_agent.mcp_registry.get_server_configs.assert_called_once_with(["kubernetes-server"])
    
    @pytest.mark.asyncio
    async def test_configure_mcp_client_missing_server_config(self, kubernetes_agent):
        """Test error handling when kubernetes-server config is missing."""
        kubernetes_agent.mcp_registry.get_server_configs.return_value = []
        
        with pytest.raises(ConfigurationError, match="Required MCP servers not configured"):
            await kubernetes_agent._configure_mcp_client()
    
    @pytest.mark.asyncio
    async def test_get_available_tools_from_kubernetes_server(self, kubernetes_agent):
        """Test that _get_available_tools retrieves tools from kubernetes-server."""
        kubernetes_agent._configured_servers = ["kubernetes-server"]
        mock_tools = [
            Tool(name="get_pod_status", description="Get pod status", inputSchema={"type": "object", "properties": {}}),
            Tool(name="get_namespace_events", description="Get namespace events", inputSchema={"type": "object", "properties": {}})
        ]
        kubernetes_agent.mcp_client.list_tools.return_value = {"kubernetes-server": mock_tools}
        
        tools = await kubernetes_agent._get_available_tools("test_session")
        
        assert len(tools.tools) == 2
        for tool in tools.tools:
            assert tool.server == "kubernetes-server"
            assert hasattr(tool.tool, 'name')
            assert hasattr(tool.tool, 'description')
        
        kubernetes_agent.mcp_client.list_tools.assert_called_once_with(session_id="test_session", server_name="kubernetes-server", stage_execution_id=None)
    
    @pytest.mark.asyncio
    async def test_get_available_tools_not_configured(self, kubernetes_agent):
        """Test that unconfigured agent raises ToolSelectionError."""
        kubernetes_agent._configured_servers = None
        
        # Should raise ToolSelectionError when not configured
        with pytest.raises(ToolSelectionError, match="Agent KubernetesAgent has not been properly configured"):
            await kubernetes_agent._get_available_tools("test_session")
    
    def test_compose_instructions_includes_kubernetes_server(self, kubernetes_agent):
        """Test that _compose_instructions includes kubernetes-server instructions."""
        with patch.object(kubernetes_agent, '_get_general_instructions', return_value="General instructions"):
            instructions = kubernetes_agent._compose_instructions()
        
        assert "General instructions" in instructions
        assert "Kubernetes Server Instructions" in instructions
        assert "K8s instructions" in instructions  # From the mock server config
    


@pytest.mark.unit
class TestKubernetesAgentLLMIntegration:
    """Test KubernetesAgent integration with LLM client."""
    
    @pytest.fixture
    def kubernetes_agent_with_mocks(self):
        """Create KubernetesAgent with properly mocked dependencies."""
        mock_llm = Mock(spec=LLMClient)
        mock_mcp = Mock(spec=MCPClient)
        mock_registry = Mock(spec=MCPServerRegistry)
        
        # Mock server config
        server_config = MCPServerConfigModel(
            server_id="kubernetes-server",
            server_type="kubernetes",
            enabled=True,
            transport={"type": "stdio", "command": "test"},
            instructions="Test K8s instructions"
        )
        mock_registry.get_server_configs.return_value = [server_config]
        
        agent = KubernetesAgent(mock_llm, mock_mcp, mock_registry)
        return agent, mock_llm, mock_mcp, mock_registry
    
    @pytest.fixture
    def sample_alert_data(self):
        """Sample alert data for testing."""
        return {
            "alert": "PodCrashLooping",
            "message": "Pod crashing",
            "namespace": "production"
        }

@pytest.mark.unit
class TestKubernetesAgentMCPIntegration:
    """Test KubernetesAgent integration with MCP client."""
    
    @pytest.fixture
    def kubernetes_agent_with_mocks(self):
        """Create KubernetesAgent with mocked dependencies."""
        mock_llm = Mock(spec=LLMClient)
        mock_mcp = Mock(spec=MCPClient)
        mock_registry = Mock(spec=MCPServerRegistry)
        
        server_config = MCPServerConfigModel(
            server_id="kubernetes-server",
            server_type="kubernetes",
            enabled=True,
            transport={"type": "stdio", "command": "test"},
            instructions="K8s instructions"
        )
        mock_registry.get_server_configs.return_value = [server_config]
        
        agent = KubernetesAgent(mock_llm, mock_mcp, mock_registry)
        return agent, mock_llm, mock_mcp, mock_registry
    
    @pytest.mark.asyncio
    async def test_execute_mcp_tools_with_kubernetes_server(self, kubernetes_agent_with_mocks):
        """Test executing MCP tools specifically for kubernetes-server."""
        agent, mock_llm, mock_mcp, mock_registry = kubernetes_agent_with_mocks
        agent._configured_servers = ["kubernetes-server"]
        
        mock_mcp.call_tool = AsyncMock(return_value={"result": "pod status data"})
        
        tools_to_call = [
            {
                "server": "kubernetes-server",
                "tool": "get_pod_status",
                "parameters": {"namespace": "production", "pod": "app-pod"},
                "reason": "Check pod status"
            }
        ]
        
        result = await agent.execute_mcp_tools(tools_to_call, session_id="test-session-123")
        
        assert "kubernetes-server" in result
        assert len(result["kubernetes-server"]) == 1
        
        tool_result = result["kubernetes-server"][0]
        assert tool_result["tool"] == "get_pod_status"
        assert tool_result["parameters"] == {"namespace": "production", "pod": "app-pod"}
        assert tool_result["result"] == {"result": "pod status data"}
        assert "timestamp" in tool_result
        
        mock_mcp.call_tool.assert_called_once_with(
            "kubernetes-server",
            "get_pod_status",
            {"namespace": "production", "pod": "app-pod"},
            "test-session-123",
            None,
            None,
            None,
            ["kubernetes-server"]
        )
    
    @pytest.mark.asyncio
    async def test_execute_mcp_tools_server_validation(self, kubernetes_agent_with_mocks):
        """Test that tool execution validates server is allowed for agent."""
        agent, mock_llm, mock_mcp, mock_registry = kubernetes_agent_with_mocks
        agent._configured_servers = ["kubernetes-server"]
        
        # Mock call_tool to perform validation
        async def mock_call_tool_with_validation(
            server_name, tool_name, parameters, session_id=None,
            stage_execution_id=None, investigation_conversation=None,
            mcp_selection=None, configured_servers=None
        ):
            if configured_servers and server_name not in configured_servers:
                raise ValueError(
                    f"Tool '{tool_name}' from server '{server_name}' not allowed by agent configuration. "
                    f"Configured servers: {configured_servers}"
                )
            return {"result": "success"}
        
        mock_mcp.call_tool = AsyncMock(side_effect=mock_call_tool_with_validation)
        
        tools_to_call = [
            {
                "server": "unauthorized-server",
                "tool": "some_tool",
                "parameters": {},
                "reason": "Test"
            }
        ]
        
        result = await agent.execute_mcp_tools(tools_to_call, session_id="test-session-123")
        
        # Should record error for unauthorized server
        assert "unauthorized-server" in result
        assert "error" in result["unauthorized-server"][0]
        assert "not allowed" in result["unauthorized-server"][0]["error"].lower()
        
        # MCP client call_tool should have been called (and raised the error)
        mock_mcp.call_tool.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_mcp_tools_error_handling(self, kubernetes_agent_with_mocks):
        """Test error handling during MCP tool execution."""
        agent, mock_llm, mock_mcp, mock_registry = kubernetes_agent_with_mocks
        agent._configured_servers = ["kubernetes-server"]
        
        mock_mcp.call_tool = AsyncMock(side_effect=Exception("Tool execution failed"))
        
        tools_to_call = [
            {
                "server": "kubernetes-server",
                "tool": "failing_tool",
                "parameters": {},
                "reason": "Test error handling"
            }
        ]
        
        result = await agent.execute_mcp_tools(tools_to_call, session_id="test-session-123")
        
        assert "kubernetes-server" in result
        tool_result = result["kubernetes-server"][0]
        assert tool_result["tool"] == "failing_tool"
        assert "error" in tool_result
        assert "Tool execution failed" in tool_result["error"]

@pytest.mark.unit
class TestKubernetesAgentErrorHandling:
    """Test KubernetesAgent error handling and edge cases."""
    
    @pytest.fixture
    def kubernetes_agent(self):
        """Create KubernetesAgent for error testing."""
        mock_llm = Mock(spec=LLMClient)
        mock_mcp = Mock(spec=MCPClient)
        mock_registry = Mock(spec=MCPServerRegistry)
        # Mock get_server_configs to return an empty list
        mock_registry.get_server_configs.return_value = []
        return KubernetesAgent(mock_llm, mock_mcp, mock_registry)

@pytest.mark.unit
class TestKubernetesAgentIntegrationScenarios:
    """Test KubernetesAgent in realistic integration scenarios."""
    
    @pytest.fixture
    def full_kubernetes_agent_setup(self):
        """Create fully configured KubernetesAgent for integration testing."""
        mock_llm = Mock(spec=LLMClient)
        mock_mcp = Mock(spec=MCPClient)
        mock_registry = Mock(spec=MCPServerRegistry)
        mock_callback = Mock()
        
        # Configure MCP registry with kubernetes-server
        server_config = MCPServerConfigModel(
            server_id="kubernetes-server",
            server_type="kubernetes", 
            enabled=True,
            transport={"type": "stdio", "command": "npx", "args": ["-y", "kubernetes-mcp-server@latest"]},
            instructions="Prioritize namespace-level resources for troubleshooting."
        )
        mock_registry.get_server_configs.return_value = [server_config]
        
        # Configure MCP client with available tools
        mock_tools = [
            {
                "name": "get_pod_status",
                "description": "Get status of pods in namespace",
                "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}}}
            },
            {
                "name": "get_namespace_events", 
                "description": "Get events in namespace",
                "inputSchema": {"type": "object", "properties": {"namespace": {"type": "string"}}}
            }
        ]
        mock_mcp.list_tools = AsyncMock(return_value={"kubernetes-server": mock_tools})
        
        agent = KubernetesAgent(mock_llm, mock_mcp, mock_registry)
        return agent, mock_llm, mock_mcp, mock_registry
    
    @pytest.fixture
    def pod_crash_alert(self):
        """Create realistic pod crash alert."""
        return Alert(
            alert_type="PodCrashLooping",
            runbook="https://runbook.example.com/pod-crash-troubleshooting",
            data={
                "message": "Pod app-deployment-abc123 in namespace production is crash looping with exit code 1",
                "environment": "production",
                "severity": "critical",
                "cluster": "prod-cluster-01",
                "namespace": "production",
                "pod": "app-deployment-abc123",
                "context": "Labels: app=web-service,version=v1.2.3; Restart count: 15; Last exit code: 1"
            }
        )
    
    @pytest.mark.asyncio
    async def test_complete_analysis_workflow(self, full_kubernetes_agent_setup):
        """Test complete workflow from alert to analysis."""
        from tarsy.models.processing_context import ChainContext
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        agent, mock_llm, mock_mcp, mock_registry = full_kubernetes_agent_setup
        
        # Mock the MCP client
        mock_mcp.list_tools.return_value = {"kubernetes-server": []}
        
        # Mock LLM to return proper LLMConversation object
        async def mock_generate_response(conversation, session_id, stage_execution_id=None):
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Final Answer: Pod analysis completed")
            return updated_conversation
        
        mock_llm.generate_response = AsyncMock(side_effect=mock_generate_response)
        
        # Mock agent methods for complete workflow
        agent.analyze_alert = AsyncMock(return_value="Detailed pod analysis")
        
        # Mock MCP registry
        mock_config = Mock()
        mock_config.server_id = "kubernetes-server"
        mock_config.server_type = "kubernetes"
        mock_config.instructions = "Use kubectl tools for analysis"
        agent.mcp_registry.get_server_configs.return_value = [mock_config]
        
        # Create pod crash alert
        pod_crash_alert = Alert(
            alert_type="kubernetes",
            runbook="https://runbooks.company.com/k8s-pod-crash",
            timestamp=now_us(),
            data={
                "severity": "critical",
                "alert": "PodCrashLoopBackOff",
                "environment": "production",
                "cluster": "prod-cluster", 
                "namespace": "production",
                "pod": "app-pod-123",
                "message": "Pod restart count: 15, exit code: 1"
            }
        )
        
        runbook_content = "# Kubernetes Pod Troubleshooting\\n..."
        
        # Create ChainContext for new interface
        processing_alert = ProcessingAlert(
            alert_type=pod_crash_alert.alert_type,
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data=pod_crash_alert.data
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="analysis"
        )
        chain_context.runbook_content = runbook_content
        
        result = await agent.process_alert(chain_context)
        
        assert result.status.value == "completed"
        assert result.result_summary is not None  # Analysis result may vary based on iteration strategy
        assert result.agent_name == "KubernetesAgent"

    def test_tool_selection_with_kubernetes_guidance(self, full_kubernetes_agent_setup):
        """Test that tool selection follows Kubernetes-specific patterns."""
        agent, mock_llm, mock_mcp, mock_registry = full_kubernetes_agent_setup
        
        # Create pod crash alert
        pod_crash_alert = Alert(
            alert_type="kubernetes", 
            runbook="https://runbooks.company.com/k8s-pod-crash",
            timestamp=now_us(),
            data={
                "severity": "critical",
                "alert": "PodCrashLoopBackOff",
                "environment": "production",
                "cluster": "prod-cluster",
                "namespace": "production", 
                "pod": "app-pod-123",
                "message": "Pod restart count: 15, exit code: 1"
            }
        )
        
        # Convert to dict for processing
        alert_dict = pod_crash_alert.model_dump()
        
        # Test that data is properly structured for tool selection
        assert alert_dict["alert_type"] == "kubernetes"
        assert alert_dict["data"]["alert"] == "PodCrashLoopBackOff"
        assert alert_dict["data"]["namespace"] == "production"
        assert alert_dict["data"]["pod"] == "app-pod-123"

    @pytest.mark.asyncio
    async def test_error_recovery_and_fallback(self, full_kubernetes_agent_setup):
        """Test that agent fails gracefully when MCP connection fails."""
        from tarsy.models.processing_context import ChainContext
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        agent, mock_llm, mock_mcp, mock_registry = full_kubernetes_agent_setup
        
        # Mock MCP configuration error
        mock_mcp.list_tools.side_effect = Exception("MCP connection failed")
        mock_llm.generate_response.return_value = "Analysis with limited tools"
        
        # Mock agent methods
        agent.analyze_alert = AsyncMock(return_value="Fallback analysis")
        
        # Mock MCP registry  
        mock_config = Mock()
        mock_config.server_id = "kubernetes-server"
        mock_config.server_type = "kubernetes"
        mock_config.instructions = "Use kubectl tools for analysis"
        agent.mcp_registry.get_server_configs.return_value = [mock_config]
        
        pod_crash_alert = Alert(
            alert_type="kubernetes",
            runbook="https://runbooks.company.com/k8s-pod-crash",
            timestamp=now_us(),
            data={
                "severity": "critical",
                "alert": "PodCrashLoopBackOff",
                "environment": "production",
                "cluster": "prod-cluster",
                "namespace": "production",
                "pod": "app-pod-123", 
                "message": "Pod restart count: 15, exit code: 1"
            }
        )
        
        from tarsy.models.processing_context import ChainContext
        processing_alert = ProcessingAlert(
            alert_type=pod_crash_alert.alert_type,
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data=pod_crash_alert.data
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="analysis"
        )
        chain_context.runbook_content = "runbook"
        result = await agent.process_alert(chain_context)
        
        # Agent should fail when it can't list tools since it can't perform its primary function
        assert result.status.value == "failed"
        assert "ToolSelectionError" in result.error_message or "Failed to retrieve tools" in result.error_message

    @pytest.mark.asyncio
    async def test_multiple_tool_iterations(self, full_kubernetes_agent_setup):
        """Test handling of multiple MCP tool iterations."""
        from tarsy.models.processing_context import ChainContext
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        agent, mock_llm, mock_mcp, mock_registry = full_kubernetes_agent_setup
        
        # Mock iterative tool calls with properly structured tool data
        mock_mcp.list_tools.return_value = {"kubernetes-server": [
            Tool(name="kubectl", description="Kubernetes command-line tool", inputSchema={"type": "object", "properties": {}})
        ]}
        mock_mcp.call_tool.return_value = {"result": "Pod details retrieved"}
        
        # Mock LLM to return proper LLMConversation object
        async def mock_generate_response(conversation, session_id, stage_execution_id=None):
            updated_conversation = LLMConversation(messages=conversation.messages.copy())
            updated_conversation.append_assistant_message("Final Answer: Comprehensive analysis")
            return updated_conversation
        
        mock_llm.generate_response = AsyncMock(side_effect=mock_generate_response)
        
        # Mock agent methods for iteration
        agent.analyze_alert = AsyncMock(return_value="Multi-iteration analysis")
        
        # Mock MCP registry
        mock_config = Mock()
        mock_config.server_id = "kubernetes-server"
        mock_config.server_type = "kubernetes"
        mock_config.instructions = "Use kubectl tools for analysis"
        agent.mcp_registry.get_server_configs.return_value = [mock_config]
        
        pod_crash_alert = Alert(
            alert_type="kubernetes",
            runbook="https://runbooks.company.com/k8s-pod-crash",
            timestamp=now_us(),
            data={
                "severity": "critical",
                "alert": "PodCrashLoopBackOff",
                "environment": "production",
                "cluster": "prod-cluster",
                "namespace": "production",
                "pod": "app-pod-123",
                "message": "Pod restart count: 15, exit code: 1"
            }
        )
        
        from tarsy.models.processing_context import ChainContext
        processing_alert = ProcessingAlert(
            alert_type=pod_crash_alert.alert_type,
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data=pod_crash_alert.data
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="analysis"
        )
        chain_context.runbook_content = "runbook"
        result = await agent.process_alert(chain_context)
        
        assert result.status.value == "completed"
        assert result.result_summary is not None  # Analysis result may vary based on iteration strategy


@pytest.mark.unit
class TestKubernetesAgentSummarization:
    """Test KubernetesAgent summarization integration (EP-0015)."""
    
    @pytest.fixture
    def kubernetes_agent_with_summarization(self):
        """Create KubernetesAgent with summarization-capable MCP client."""
        # Use the existing fixtures from the file
        mock_llm_client = Mock(spec=LLMClient)
        mock_llm_client.generate_response = AsyncMock(return_value="Test analysis result")
        
        mock_mcp_client = Mock(spec=MCPClient)
        mock_mcp_client.list_tools = AsyncMock(return_value={"kubernetes-server": []})
        mock_mcp_client.call_tool = AsyncMock()
        
        mock_mcp_registry = Mock(spec=MCPServerRegistry)
        server_config = MCPServerConfigModel(
            server_id="kubernetes-server",
            server_type="kubernetes",
            enabled=True,
            transport={"type": "stdio", "command": "npx", "args": ["-y", "kubernetes-mcp-server@latest"]},
            instructions="Kubernetes server instructions"
        )
        mock_mcp_registry.get_server_configs.return_value = [server_config]
        
        agent = KubernetesAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)
        return agent, mock_llm_client, mock_mcp_client, mock_mcp_registry
    
    @pytest.mark.asyncio
    async def test_execute_mcp_tools_with_summarization_context(self, kubernetes_agent_with_summarization):
        """Test KubernetesAgent execute_mcp_tools passes investigation conversation for summarization."""
        agent, mock_llm, mock_mcp, mock_registry = kubernetes_agent_with_summarization
        agent._configured_servers = ["kubernetes-server"]
        
        # Mock large result from MCP client that would trigger summarization
        mock_mcp.call_tool = AsyncMock(return_value={
            "result": "SUMMARY: Critical namespace issue - 25 pods stuck in Terminating state due to finalizers on worker-node-03",
            "_summarized": {
                "original_tokens": 4500,
                "threshold": 2000,
                "summarized_at": 1704110400000000
            }
        })
        
        # Create Kubernetes-specific investigation conversation
        investigation_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="""You are a Kubernetes expert investigating cluster issues.

DOMAIN KNOWLEDGE:
- Production cluster with 50+ microservices
- Known issues with finalizer cleanup in production namespace  
- Escalation required for namespace stuck >30min
- Critical services: payment, auth, notifications"""),
            LLMMessage(role=MessageRole.USER, content="Namespace 'production' stuck in Terminating state for 45 minutes"),
            LLMMessage(role=MessageRole.ASSISTANT, content="I need to investigate the namespace status and identify blocking resources")
        ])
        
        tools_to_call = [
            {
                "server": "kubernetes-server",
                "tool": "kubectl_describe",
                "parameters": {"resource": "namespace", "name": "production"},
                "reason": "Analyze namespace termination blocking issue"
            }
        ]
        
        # Act
        result = await agent.execute_mcp_tools(
            tools_to_call,
            session_id="test-k8s-summarization", 
            investigation_conversation=investigation_conversation
        )
        
        # Assert
        assert "kubernetes-server" in result
        assert len(result["kubernetes-server"]) == 1
        
        tool_result = result["kubernetes-server"][0]
        assert tool_result["tool"] == "kubectl_describe"
        assert "SUMMARY:" in str(tool_result["result"])
        assert "_summarized" in tool_result["result"]  # Should contain summarization metadata
        
        # Verify MCP client was called with Kubernetes investigation conversation
        mock_mcp.call_tool.assert_called_once_with(
            "kubernetes-server",
            "kubectl_describe", 
            {"resource": "namespace", "name": "production"},
            "test-k8s-summarization",
            None,
            investigation_conversation,  # Investigation conversation should be passed
            None,
            ["kubernetes-server"]
        )

    @pytest.mark.asyncio
    async def test_configure_mcp_client_injects_kubernetes_summarizer(self, kubernetes_agent_with_summarization):
        """Test that configure_mcp_client creates and injects summarizer for KubernetesAgent."""
        agent, mock_llm, mock_mcp, mock_registry = kubernetes_agent_with_summarization
        
        # Ensure agent has required attributes for summarizer creation
        agent.llm_client = mock_llm
        
        # Mock the prompt builder that should exist
        with patch.object(agent, '_prompt_builder') as mock_prompt_builder:
            # Act
            await agent._configure_mcp_client()
        
        # Assert
        assert agent._configured_servers == ["kubernetes-server"]
        
        # Verify summarizer was injected into MCP client
        assert hasattr(agent.mcp_client, 'summarizer')
        assert agent.mcp_client.summarizer is not None 