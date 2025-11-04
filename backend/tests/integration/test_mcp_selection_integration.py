"""
Integration tests for MCP server/tool selection feature.

Tests the integration of MCP selection through alert submission and processing,
validating that user-provided server/tool selections override defaults correctly.
"""

import pytest
from unittest.mock import AsyncMock, Mock
from mcp.types import Tool

from tarsy.models.alert import Alert
from tarsy.models.mcp_selection_models import MCPSelectionConfig, MCPServerSelection
from tarsy.models.processing_context import ChainContext
from tarsy.models.alert import ProcessingAlert
from tarsy.services.alert_service import AlertService
from tarsy.services.agent_factory import AgentFactory
from tarsy.agents.kubernetes_agent import KubernetesAgent


@pytest.mark.asyncio
@pytest.mark.integration
class TestMCPSelectionAlertSubmission:
    """Test alert submission with MCP selection configuration."""
    
    def test_alert_with_mcp_selection_validation(self):
        """Test that Alert model validates MCP selection correctly."""
        # Valid alert with server selection
        alert = Alert(
            alert_type="kubernetes",
            data={"test": "data"},
            mcp=MCPSelectionConfig(
                servers=[
                    MCPServerSelection(name="kubernetes-server")
                ]
            )
        )
        
        assert alert.mcp is not None
        assert len(alert.mcp.servers) == 1
        assert alert.mcp.servers[0].name == "kubernetes-server"
        assert alert.mcp.servers[0].tools is None
    
    def test_alert_with_tool_selection_validation(self):
        """Test that Alert model validates tool selection correctly."""
        alert = Alert(
            alert_type="kubernetes",
            data={"test": "data"},
            mcp=MCPSelectionConfig(
                servers=[
                    MCPServerSelection(
                        name="kubernetes-server",
                        tools=["kubectl-get", "kubectl-describe"]
                    )
                ]
            )
        )
        
        assert alert.mcp is not None
        assert alert.mcp.servers[0].tools == ["kubectl-get", "kubectl-describe"]
    
    def test_alert_without_mcp_selection(self):
        """Test that Alert without MCP selection works normally."""
        alert = Alert(
            alert_type="kubernetes",
            data={"test": "data"}
        )
        
        assert alert.mcp is None
    
    def test_processing_alert_preserves_mcp_selection(self):
        """Test that ProcessingAlert preserves MCP selection from API alert."""
        api_alert = Alert(
            alert_type="kubernetes",
            data={"test": "data"},
            mcp=MCPSelectionConfig(
                servers=[
                    MCPServerSelection(name="kubernetes-server")
                ]
            )
        )
        
        processing_alert = ProcessingAlert.from_api_alert(api_alert)
        
        assert processing_alert.mcp is not None
        assert processing_alert.mcp.servers[0].name == "kubernetes-server"
    
    def test_chain_context_preserves_mcp_selection(self):
        """Test that ChainContext preserves MCP selection from ProcessingAlert."""
        api_alert = Alert(
            alert_type="kubernetes",
            data={"test": "data"},
            mcp=MCPSelectionConfig(
                servers=[
                    MCPServerSelection(
                        name="kubernetes-server",
                        tools=["kubectl-get"]
                    )
                ]
            )
        )
        
        processing_alert = ProcessingAlert.from_api_alert(api_alert)
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="analysis"
        )
        
        assert chain_context.mcp is not None
        assert chain_context.mcp.servers[0].name == "kubernetes-server"
        assert chain_context.mcp.servers[0].tools == ["kubectl-get"]


@pytest.mark.asyncio
@pytest.mark.integration
class TestMCPSelectionAgentExecution:
    """Test agent execution with MCP selection override."""
    
    async def test_agent_uses_default_servers_without_selection(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry
    ):
        """Test that agent uses default configured servers when no MCP selection provided."""
        # Mock the registry to return kubernetes-server
        mock_mcp_server_registry.get_all_server_ids.return_value = ["kubernetes-server", "argocd-server"]
        
        # Note: mock_mcp_client fixture already has list_tools configured
        # It returns kubectl_get_namespace and kubectl_get_pods for kubernetes-server
        
        # Create agent
        agent = KubernetesAgent(
            llm_client=mock_llm_manager,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        await agent._configure_mcp_client()
        
        # Get tools without MCP selection (should use default kubernetes-server)
        available_tools = await agent._get_available_tools("test-session")
        
        # Verify default servers were used
        assert len(available_tools.tools) == 2
        assert all(tool.server == "kubernetes-server" for tool in available_tools.tools)
        tool_names = {tool.tool.name for tool in available_tools.tools}
        assert tool_names == {"kubectl_get_namespace", "kubectl_get_pods"}
    
    async def test_agent_uses_selected_servers_with_mcp_selection(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry
    ):
        """Test that agent uses user-selected servers instead of defaults."""
        # Mock the registry
        mock_mcp_server_registry.get_all_server_ids.return_value = [
            "kubernetes-server", 
            "argocd-server", 
            "custom-server"
        ]
        
        # Mock list_tools for different servers
        async def mock_list_tools(session_id, server_name, stage_execution_id=None):
            if server_name == "argocd-server":
                return {
                    "argocd-server": [
                        Tool(name="get-application", description="Get app", inputSchema={})
                    ]
                }
            elif server_name == "custom-server":
                return {
                    "custom-server": [
                        Tool(name="custom-tool", description="Custom", inputSchema={})
                    ]
                }
            return {}
        
        mock_mcp_client.list_tools.side_effect = mock_list_tools
        
        # Create agent
        agent = KubernetesAgent(
            llm_client=mock_llm_manager,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        await agent._configure_mcp_client()
        
        # Create MCP selection (not including kubernetes-server)
        mcp_selection = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="argocd-server"),
                MCPServerSelection(name="custom-server")
            ]
        )
        
        # Get tools with MCP selection
        available_tools = await agent._get_available_tools("test-session", mcp_selection=mcp_selection)
        
        # Verify user-selected servers were used instead of defaults
        assert len(available_tools.tools) == 2
        servers = {tool.server for tool in available_tools.tools}
        assert servers == {"argocd-server", "custom-server"}
        assert "kubernetes-server" not in servers
    
    async def test_agent_filters_tools_with_tool_selection(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry
    ):
        """Test that agent filters to only requested tools."""
        # Mock the registry
        mock_mcp_server_registry.get_all_server_ids.return_value = ["kubernetes-server"]
        
        # Note: mock_mcp_client fixture already returns kubectl_get_namespace and kubectl_get_pods
        # We'll use these actual tool names for the test
        
        # Create agent
        agent = KubernetesAgent(
            llm_client=mock_llm_manager,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        await agent._configure_mcp_client()
        
        # Create MCP selection with specific tools (using actual tool names from fixture)
        mcp_selection = MCPSelectionConfig(
            servers=[
                MCPServerSelection(
                    name="kubernetes-server",
                    tools=["kubectl_get_namespace"]  # Only request one tool
                )
            ]
        )
        
        # Get tools with selection
        available_tools = await agent._get_available_tools("test-session", mcp_selection=mcp_selection)
        
        # Verify only requested tools were returned
        assert len(available_tools.tools) == 1
        tool_names = {tool.tool.name for tool in available_tools.tools}
        assert tool_names == {"kubectl_get_namespace"}


@pytest.mark.asyncio
@pytest.mark.integration
class TestMCPSelectionErrorHandling:
    """Test error handling for invalid MCP selections."""
    
    async def test_invalid_server_selection_raises_error(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry
    ):
        """Test that selecting non-existent server raises MCPServerSelectionError."""
        from tarsy.agents.exceptions import MCPServerSelectionError
        
        # Mock the registry with limited servers
        mock_mcp_server_registry.get_all_server_ids.return_value = ["kubernetes-server"]
        
        # Create agent
        agent = KubernetesAgent(
            llm_client=mock_llm_manager,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        await agent._configure_mcp_client()
        
        # Try to select non-existent server
        mcp_selection = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="non-existent-server")
            ]
        )
        
        with pytest.raises(MCPServerSelectionError) as exc_info:
            await agent._get_available_tools("test-session", mcp_selection=mcp_selection)
        
        # Verify error details
        error = exc_info.value
        assert "non-existent-server" in str(error)
        assert error.requested_servers == ["non-existent-server"]
        assert "kubernetes-server" in error.available_servers
    
    async def test_invalid_tool_selection_raises_error(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry
    ):
        """Test that selecting non-existent tool raises MCPToolSelectionError."""
        from tarsy.agents.exceptions import MCPToolSelectionError
        
        # Mock the registry
        mock_mcp_server_registry.get_all_server_ids.return_value = ["kubernetes-server"]
        
        # Note: mock_mcp_client fixture already returns kubectl_get_namespace and kubectl_get_pods
        
        # Create agent
        agent = KubernetesAgent(
            llm_client=mock_llm_manager,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        await agent._configure_mcp_client()
        
        # Try to select non-existent tool
        mcp_selection = MCPSelectionConfig(
            servers=[
                MCPServerSelection(
                    name="kubernetes-server",
                    tools=["non-existent-tool"]
                )
            ]
        )
        
        with pytest.raises(MCPToolSelectionError) as exc_info:
            await agent._get_available_tools("test-session", mcp_selection=mcp_selection)
        
        # Verify error details
        error = exc_info.value
        assert error.server_name == "kubernetes-server"
        assert "non-existent-tool" in error.requested_tools
        # Verify the available tools match what the fixture returns
        assert set(error.available_tools) == {"kubectl_get_namespace", "kubectl_get_pods"}


@pytest.mark.asyncio
@pytest.mark.integration
class TestMCPSelectionEndToEnd:
    """Test MCP selection through the full alert processing flow."""
    
    async def test_alert_with_mcp_selection_flows_through_processing(
        self,
        mock_llm_manager,
        mock_mcp_client,
        mock_mcp_server_registry
    ):
        """Test that MCP selection flows correctly through the entire processing pipeline."""
        # Mock registry
        mock_mcp_server_registry.get_all_server_ids.return_value = [
            "kubernetes-server",
            "argocd-server"
        ]
        
        # Mock list_tools
        async def mock_list_tools(session_id, server_name, stage_execution_id=None):
            if server_name == "argocd-server":
                return {
                    "argocd-server": [
                        Tool(name="get-application", description="Get app", inputSchema={})
                    ]
                }
            return {}
        
        mock_mcp_client.list_tools.side_effect = mock_list_tools
        
        # Create alert with MCP selection
        alert = Alert(
            alert_type="kubernetes",
            data={"namespace": "test"},
            mcp=MCPSelectionConfig(
                servers=[
                    MCPServerSelection(name="argocd-server")
                ]
            )
        )
        
        # Convert to processing alert
        processing_alert = ProcessingAlert.from_api_alert(alert)
        
        # Create chain context
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="analysis"
        )
        
        # Verify MCP selection propagated correctly
        assert chain_context.mcp is not None
        assert chain_context.mcp.servers[0].name == "argocd-server"
        
        # Create agent and verify it uses the selection
        agent = KubernetesAgent(
            llm_client=mock_llm_manager,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        await agent._configure_mcp_client()
        
        # Get tools using the chain context's MCP selection
        available_tools = await agent._get_available_tools(
            "test-session",
            mcp_selection=chain_context.mcp
        )
        
        # Verify only selected server tools are available
        assert len(available_tools.tools) == 1
        assert available_tools.tools[0].server == "argocd-server"
        assert available_tools.tools[0].tool.name == "get-application"


@pytest.mark.asyncio
@pytest.mark.integration
class TestMCPSelectionPersistence:
    """Test MCP selection persistence in database and retrieval via API."""
    
    def test_mcp_selection_serialization_roundtrip(self):
        """Test that MCP selection can be serialized and deserialized correctly."""
        from tarsy.models.mcp_selection_models import MCPSelectionConfig, MCPServerSelection
        
        # Create MCP selection
        original = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="kubernetes-server", tools=["list_pods", "get_pod"]),
                MCPServerSelection(name="argocd-server")
            ]
        )
        
        # Serialize to dict (as stored in database)
        serialized = original.model_dump()
        
        # Deserialize back (as returned from API)
        deserialized = MCPSelectionConfig(**serialized)
        
        # Verify roundtrip preserves data
        assert len(deserialized.servers) == 2
        assert deserialized.servers[0].name == "kubernetes-server"
        assert deserialized.servers[0].tools == ["list_pods", "get_pod"]
        assert deserialized.servers[1].name == "argocd-server"
        assert deserialized.servers[1].tools is None
    
    def test_mcp_selection_flows_through_alert_models(self):
        """Test that MCP selection flows correctly through alert processing models."""
        from tarsy.models.alert import Alert, ProcessingAlert
        from tarsy.models.mcp_selection_models import MCPSelectionConfig, MCPServerSelection
        from tarsy.models.processing_context import ChainContext
        
        # Create alert with MCP selection
        api_alert = Alert(
            alert_type="kubernetes",
            data={"namespace": "test"},
            mcp=MCPSelectionConfig(
                servers=[
                    MCPServerSelection(name="kubernetes-server", tools=["list_pods"])
                ]
            )
        )
        
        # Flow through ProcessingAlert
        processing_alert = ProcessingAlert.from_api_alert(api_alert)
        assert processing_alert.mcp is not None
        assert processing_alert.mcp.servers[0].name == "kubernetes-server"
        assert processing_alert.mcp.servers[0].tools == ["list_pods"]
        
        # Flow through ChainContext
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-flow",
            current_stage_name="analysis"
        )
        assert chain_context.mcp is not None
        assert chain_context.mcp.servers[0].name == "kubernetes-server"
        assert chain_context.mcp.servers[0].tools == ["list_pods"]
    
    def test_history_models_support_mcp_selection(self):
        """Test that history models can represent MCP selection."""
        from tarsy.models.history_models import DetailedSession, SessionOverview
        from tarsy.models.mcp_selection_models import MCPSelectionConfig, MCPServerSelection
        from tarsy.models.constants import AlertSessionStatus
        from tarsy.utils.timestamp import now_us
        
        mcp_selection = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="kubernetes-server", tools=["list_pods"])
            ]
        )
        
        # Test SessionOverview
        overview = SessionOverview(
            session_id="test-overview",
            alert_type="kubernetes",
            agent_type="chain:k8s",
            status=AlertSessionStatus.COMPLETED,
            started_at_us=now_us(),
            chain_id="test-chain",
            mcp_selection=mcp_selection
        )
        assert overview.mcp_selection is not None
        assert isinstance(overview.mcp_selection, MCPSelectionConfig)
        
        # Test DetailedSession
        detailed = DetailedSession(
            session_id="test-detailed",
            alert_type="kubernetes",
            agent_type="chain:k8s",
            status=AlertSessionStatus.COMPLETED,
            started_at_us=now_us(),
            alert_data={"test": "data"},
            chain_id="test-chain",
            chain_definition={},
            mcp_selection=mcp_selection
        )
        assert detailed.mcp_selection is not None
        assert isinstance(detailed.mcp_selection, MCPSelectionConfig)
        
        # Test serialization for API response
        response_data = detailed.model_dump()
        assert "mcp_selection" in response_data
        assert response_data["mcp_selection"]["servers"][0]["name"] == "kubernetes-server"

