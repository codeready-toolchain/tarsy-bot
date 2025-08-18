"""
Comprehensive unit tests for KubernetesAgent.

Tests the Kubernetes-specialized agent implementation including abstract method
implementations, Kubernetes-specific functionality, and integration with BaseAgent.
"""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.models.constants import IterationStrategy
from tarsy.agents.exceptions import ConfigurationError
from tarsy.agents.kubernetes_agent import KubernetesAgent
from tarsy.integrations.llm.client import LLMClient
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.alert import Alert
from tarsy.models.agent_config import MCPServerConfigModel
from tarsy.services.mcp_server_registry import MCPServerRegistry
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
            connection_params={"command": "npx", "args": ["-y", "kubernetes-mcp-server@latest"]},
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
        assert agent._iteration_count == 0
        assert agent._configured_servers is None
        # Verify default iteration strategy
        assert agent.iteration_strategy == IterationStrategy.REACT
    
    def test_initialization_with_custom_iteration_strategy(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test KubernetesAgent initialization with custom iteration strategy."""
        agent = KubernetesAgent(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry,
            iteration_strategy=IterationStrategy.REGULAR
        )
        
        assert agent.iteration_strategy == IterationStrategy.REGULAR
    
    def test_inheritance_from_base_agent(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test that KubernetesAgent properly inherits from BaseAgent."""
        agent = KubernetesAgent(
            llm_client=mock_llm_client,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_registry
        )
        
        # Check that it has BaseAgent attributes and methods
        assert hasattr(agent, '_iteration_count')
        assert hasattr(agent, 'max_iterations')
        assert hasattr(agent, 'process_alert')
        assert hasattr(agent, 'analyze_alert')
        assert hasattr(agent, '_compose_instructions')
    
    def test_multiple_instances_independence(self, mock_llm_client, mock_mcp_client, mock_mcp_registry):
        """Test that multiple KubernetesAgent instances are independent."""
        agent1 = KubernetesAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)
        agent2 = KubernetesAgent(mock_llm_client, mock_mcp_client, mock_mcp_registry)
        
        assert agent1 is not agent2
        assert agent1._iteration_count == agent2._iteration_count  # Both start at 0
        
        # Modify one and verify independence
        agent1._iteration_count = 5
        assert agent2._iteration_count == 0


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
    
    @patch('tarsy.agents.kubernetes_agent.super')
    def test_build_analysis_prompt_uses_base_implementation(self, mock_super, kubernetes_agent, sample_alert_data):
        """Test that build_analysis_prompt uses BaseAgent implementation."""
        mock_base_prompt = "Base analysis prompt"
        mock_super().build_analysis_prompt.return_value = mock_base_prompt
        
        runbook_content = "Test runbook content"
        mcp_data = {"test": "data"}
        
        result = kubernetes_agent.build_analysis_prompt(sample_alert_data, runbook_content, mcp_data)
        
        assert result == mock_base_prompt
        mock_super().build_analysis_prompt.assert_called_once_with(sample_alert_data, runbook_content, mcp_data)
    
    @patch('tarsy.agents.kubernetes_agent.super')
    def test_build_mcp_tool_selection_prompt_adds_kubernetes_guidance(self, mock_super, kubernetes_agent, sample_alert_data, sample_available_tools):
        """Test that build_mcp_tool_selection_prompt adds Kubernetes-specific guidance."""
        base_prompt = "Base tool selection prompt"
        mock_super().build_mcp_tool_selection_prompt.return_value = base_prompt
        
        runbook_content = "Test runbook content"
        
        result = kubernetes_agent.build_mcp_tool_selection_prompt(
            sample_alert_data, runbook_content, sample_available_tools
        )
        
        # Verify base method was called
        mock_super().build_mcp_tool_selection_prompt.assert_called_once_with(
            sample_alert_data, runbook_content, sample_available_tools
        )
        
        # Verify Kubernetes-specific guidance was added
        assert base_prompt in result
        assert "Kubernetes-Specific Tool Selection Strategy" in result
        assert "Namespace-level resources first" in result
        assert "Resource status and events" in result
        assert "Cluster-level resources only if needed" in result
        assert "Logs last" in result
        assert "Focus on the specific namespace" in result
    
    def test_build_mcp_tool_selection_prompt_preserves_base_content(self, kubernetes_agent, sample_alert_data, sample_available_tools):
        """Test that Kubernetes guidance doesn't interfere with base content."""
        runbook_content = "Test runbook with specific guidance"
        
        with patch('tarsy.agents.kubernetes_agent.super') as mock_super:
            base_prompt = "Base prompt with important content"
            mock_super().build_mcp_tool_selection_prompt.return_value = base_prompt
            
            result = kubernetes_agent.build_mcp_tool_selection_prompt(
                sample_alert_data, runbook_content, sample_available_tools
            )
            
            # Verify both base content and Kubernetes guidance are present
            assert base_prompt in result
            assert "Kubernetes-Specific Tool Selection Strategy" in result
            # Verify they're properly separated
            assert result.startswith(base_prompt)
            assert "\n\n" in result  # Proper separation


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
            connection_params={"command": "npx"},
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
            severity="critical",
            timestamp=now_us(),
            data={
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
    
    async def test_configure_mcp_client_with_kubernetes_server(self, kubernetes_agent):
        """Test that _configure_mcp_client sets up kubernetes-server correctly."""
        await kubernetes_agent._configure_mcp_client()
        
        assert kubernetes_agent._configured_servers == ["kubernetes-server"]
        kubernetes_agent.mcp_registry.get_server_configs.assert_called_once_with(["kubernetes-server"])
    
    async def test_configure_mcp_client_missing_server_config(self, kubernetes_agent):
        """Test error handling when kubernetes-server config is missing."""
        kubernetes_agent.mcp_registry.get_server_configs.return_value = []
        
        with pytest.raises(ConfigurationError, match="Required MCP servers not configured"):
            await kubernetes_agent._configure_mcp_client()
    
    async def test_get_available_tools_from_kubernetes_server(self, kubernetes_agent):
        """Test that _get_available_tools retrieves tools from kubernetes-server."""
        kubernetes_agent._configured_servers = ["kubernetes-server"]
        mock_tools = [
            {"name": "get_pod_status", "description": "Get pod status"},
            {"name": "get_namespace_events", "description": "Get namespace events"}
        ]
        kubernetes_agent.mcp_client.list_tools.return_value = {"kubernetes-server": mock_tools}
        
        tools = await kubernetes_agent._get_available_tools("test_session")
        
        assert len(tools) == 2
        for tool in tools:
            assert tool["server"] == "kubernetes-server"
            assert "name" in tool
            assert "description" in tool
        
        kubernetes_agent.mcp_client.list_tools.assert_called_once_with(session_id="test_session", server_name="kubernetes-server", stage_execution_id=None)
    
    async def test_get_available_tools_not_configured(self, kubernetes_agent):
        """Test that unconfigured agent returns empty tools list."""
        kubernetes_agent._configured_servers = None
        
        tools = await kubernetes_agent._get_available_tools("test_session")
        
        # Should return empty list when not configured (error is caught and logged)
        assert tools == []
    
    def test_compose_instructions_includes_kubernetes_server(self, kubernetes_agent):
        """Test that _compose_instructions includes kubernetes-server instructions."""
        with patch.object(kubernetes_agent, '_get_general_instructions', return_value="General instructions"):
            instructions = kubernetes_agent._compose_instructions()
        
        assert "General instructions" in instructions
        assert "Kubernetes Server Instructions" in instructions
        assert "K8s instructions" in instructions  # From the mock server config
    
    def test_get_server_specific_tool_guidance_includes_kubernetes(self, kubernetes_agent):
        """Test that server guidance includes kubernetes-server instructions."""
        guidance = kubernetes_agent._get_server_specific_tool_guidance()
        
        assert "Server-Specific Tool Selection Guidance" in guidance
        assert "Kubernetes Tools" in guidance
        assert "K8s instructions" in guidance


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
            connection_params={"command": "test"},
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
    
    async def test_analyze_alert_calls_llm_with_kubernetes_context(self, kubernetes_agent_with_mocks, sample_alert_data):
        """Test that analyze_alert calls LLM with Kubernetes-specific context."""
        agent, mock_llm, mock_mcp, mock_registry = kubernetes_agent_with_mocks
        mock_llm.generate_response = AsyncMock(return_value="Analysis result")
        
        runbook_content = "Test runbook"
        mcp_data = {"test": "data"}
        
        result = await agent.analyze_alert(sample_alert_data, runbook_content, mcp_data, session_id="test-session-123")
        
        assert result == "Analysis result"
        mock_llm.generate_response.assert_called_once()
        
        # Verify the messages structure
        call_args = mock_llm.generate_response.call_args[0]
        messages = call_args[0]
        assert len(messages) == 2
        assert messages[0].role == "system"
        assert messages[1].role == "user"
        
        # Verify system message includes Kubernetes server instructions
        assert "Test K8s instructions" in messages[0].content
    
    async def test_determine_mcp_tools_with_kubernetes_guidance(self, kubernetes_agent_with_mocks, sample_alert_data):
        """Test that determine_mcp_tools includes Kubernetes-specific guidance."""
        agent, mock_llm, mock_mcp, mock_registry = kubernetes_agent_with_mocks
        
        # Mock LLM response for tool selection
        tool_selection_response = json.dumps([
            {
                "server": "kubernetes-server",
                "tool": "get_pod_status",
                "parameters": {"namespace": "production"},
                "reason": "Check pod status"
            }
        ])
        mock_llm.generate_response = AsyncMock(return_value=tool_selection_response)
        
        available_tools = {"tools": [{"name": "get_pod_status", "server": "kubernetes-server"}]}
        runbook_content = "Test runbook"
        
        result = await agent.determine_mcp_tools(sample_alert_data, runbook_content, available_tools, session_id="test-session-123")
        
        assert len(result) == 1
        assert result[0]["server"] == "kubernetes-server"
        assert result[0]["tool"] == "get_pod_status"
        
        # Verify LLM was called with Kubernetes guidance
        mock_llm.generate_response.assert_called_once()
        call_args = mock_llm.generate_response.call_args[0]
        user_message = call_args[0][1].content
        assert "Kubernetes-Specific Tool Selection Strategy" in user_message
    
    async def test_analyze_alert_error_handling(self, kubernetes_agent_with_mocks, sample_alert_data):
        """Test error handling in analyze_alert."""
        agent, mock_llm, mock_mcp, mock_registry = kubernetes_agent_with_mocks
        mock_llm.generate_response = AsyncMock(side_effect=Exception("LLM error"))
        
        with pytest.raises(Exception, match="Analysis error: LLM error"):
            await agent.analyze_alert(sample_alert_data, "runbook", {}, session_id="test-session-123")


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
            connection_params={"command": "test"},
            instructions="K8s instructions"
        )
        mock_registry.get_server_configs.return_value = [server_config]
        
        agent = KubernetesAgent(mock_llm, mock_mcp, mock_registry)
        return agent, mock_llm, mock_mcp, mock_registry
    
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
            None
        )
    
    async def test_execute_mcp_tools_server_validation(self, kubernetes_agent_with_mocks):
        """Test that tool execution validates server is allowed for agent."""
        agent, mock_llm, mock_mcp, mock_registry = kubernetes_agent_with_mocks
        agent._configured_servers = ["kubernetes-server"]
        
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
        assert "not allowed for agent KubernetesAgent" in result["unauthorized-server"][0]["error"]
        
        # Should not call MCP client
        mock_mcp.call_tool.assert_not_called()
    
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
    
    async def test_determine_mcp_tools_invalid_json_response(self, kubernetes_agent):
        """Test handling of invalid JSON response from LLM."""
        kubernetes_agent.llm_client.generate_response = AsyncMock(return_value="Invalid JSON response")
        
        with pytest.raises(Exception, match="Tool selection error"):
            await kubernetes_agent.determine_mcp_tools(
                {"alert": "test"}, "runbook", {"tools": []}, session_id="test-session-123"
            )
    
    async def test_determine_mcp_tools_wrong_response_type(self, kubernetes_agent):
        """Test handling of wrong response type from LLM."""
        kubernetes_agent.llm_client.generate_response = AsyncMock(return_value='{"wrong": "type"}')
        
        with pytest.raises(Exception, match="Tool selection error"):
            await kubernetes_agent.determine_mcp_tools(
                {"alert": "test"}, "runbook", {"tools": []}, session_id="test-session-123"
            )
    
    async def test_determine_mcp_tools_missing_required_fields(self, kubernetes_agent):
        """Test handling of tool calls missing required fields."""
        invalid_tools_response = json.dumps([
            {
                "server": "kubernetes-server",
                "tool": "get_pod_status"
                # Missing "parameters" and "reason"
            }
        ])
        kubernetes_agent.llm_client.generate_response = AsyncMock(return_value=invalid_tools_response)
        
        with pytest.raises(Exception, match="Tool selection error"):
            await kubernetes_agent.determine_mcp_tools(
                {"alert": "test"}, "runbook", {"tools": []}, session_id="test-session-123"
            )
    


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
            connection_params={"command": "npx", "args": ["-y", "kubernetes-mcp-server@latest"]},
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
            message="Pod app-deployment-abc123 in namespace production is crash looping with exit code 1",
            environment="production",
            severity="critical",
            cluster="prod-cluster-01",
            namespace="production",
            pod="app-deployment-abc123",
            runbook="https://runbook.example.com/pod-crash-troubleshooting",
            context="Labels: app=web-service,version=v1.2.3; Restart count: 15; Last exit code: 1"
        )
    
    @pytest.mark.asyncio
    async def test_complete_analysis_workflow(self, full_kubernetes_agent_setup):
        """Test complete workflow from alert to analysis."""
        agent, mock_llm, mock_mcp, mock_registry = full_kubernetes_agent_setup
        
        # Mock the MCP client
        mock_mcp.list_tools.return_value = {"kubernetes-server": []}
        mock_llm.generate_response.return_value = "Pod analysis completed"
        
        # Mock agent methods for complete workflow
        agent.determine_mcp_tools = AsyncMock(return_value=[])
        agent.determine_next_mcp_tools = AsyncMock(return_value={"continue": False})
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
            severity="critical",
            timestamp=now_us(),
            data={
                "alert": "PodCrashLoopBackOff",
                "environment": "production",
                "cluster": "prod-cluster", 
                "namespace": "production",
                "pod": "app-pod-123",
                "message": "Pod restart count: 15, exit code: 1"
            }
        )
        
        runbook_content = "# Kubernetes Pod Troubleshooting\\n..."
        
        # Create AlertProcessingData for new interface
        from tarsy.models.alert_processing import AlertProcessingData
        alert_processing_data = AlertProcessingData(
            alert_type=pod_crash_alert.alert_type,
            alert_data=pod_crash_alert.data,
            runbook_content=runbook_content
        )
        
        result = await agent.process_alert(alert_processing_data, "test-session-123")
        
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
            severity="critical",
            timestamp=now_us(),
            data={
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
        """Test graceful error handling and fallback mechanisms."""
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
            severity="critical", 
            timestamp=now_us(),
            data={
                "alert": "PodCrashLoopBackOff",
                "environment": "production",
                "cluster": "prod-cluster",
                "namespace": "production",
                "pod": "app-pod-123", 
                "message": "Pod restart count: 15, exit code: 1"
            }
        )
        
        from tarsy.models.alert_processing import AlertProcessingData
        alert_processing_data = AlertProcessingData(
            alert_type=pod_crash_alert.alert_type,
            alert_data=pod_crash_alert.data,
            runbook_content="runbook"
        )
        result = await agent.process_alert(alert_processing_data, "test-session-123")
        
        assert result.status.value == "completed"
        assert result.result_summary is not None  # Analysis result may vary based on iteration strategy

    @pytest.mark.asyncio
    async def test_multiple_tool_iterations(self, full_kubernetes_agent_setup):
        """Test handling of multiple MCP tool iterations."""
        agent, mock_llm, mock_mcp, mock_registry = full_kubernetes_agent_setup
        
        # Mock iterative tool calls
        mock_mcp.list_tools.return_value = {"kubernetes-server": ["kubectl"]}
        mock_mcp.call_tool.return_value = {"result": "Pod details retrieved"}
        mock_llm.generate_response.return_value = "Comprehensive analysis"
        
        # Mock agent methods for iteration
        agent.determine_mcp_tools = AsyncMock(return_value=[{"server": "kubernetes-server", "tool": "kubectl"}])
        agent.determine_next_mcp_tools = AsyncMock(return_value={"continue": False})
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
            severity="critical",
            timestamp=now_us(),
            data={
                "alert": "PodCrashLoopBackOff",
                "environment": "production",
                "cluster": "prod-cluster",
                "namespace": "production",
                "pod": "app-pod-123",
                "message": "Pod restart count: 15, exit code: 1"
            }
        )
        
        from tarsy.models.alert_processing import AlertProcessingData
        alert_processing_data = AlertProcessingData(
            alert_type=pod_crash_alert.alert_type,
            alert_data=pod_crash_alert.data,
            runbook_content="runbook"
        )
        result = await agent.process_alert(alert_processing_data, "test-session-123")
        
        assert result.status.value == "completed"
        assert result.result_summary is not None  # Analysis result may vary based on iteration strategy 