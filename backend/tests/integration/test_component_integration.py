"""
Component integration tests for tarsy services.

This module tests the integration between specific components of the system,
focusing on service boundaries and interactions rather than full end-to-end flows.
"""


import pytest

from tarsy.agents.kubernetes_agent import KubernetesAgent
from tarsy.integrations.llm.client import LLMManager
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.constants import StageStatus
from tarsy.services.agent_factory import AgentFactory
from tarsy.services.agent_registry import AgentRegistry
from tarsy.services.mcp_server_registry import MCPServerRegistry


@pytest.mark.asyncio
@pytest.mark.integration
class TestAgentRegistryIntegration:
    """Test agent registry component and its interactions."""

    def test_agent_registry_default_mappings(self):
        """Test agent registry with default mappings."""
        # Act
        registry = AgentRegistry()
        
        # Assert
        supported_types = registry.get_supported_alert_types()
        assert "NamespaceTerminating" in supported_types
        
        agent_class = registry.get_agent_for_alert_type("NamespaceTerminating")
        assert agent_class == "KubernetesAgent"

    def test_agent_registry_custom_mappings(self):
        """Test agent registry with custom configuration."""
        # Arrange
        custom_config = {
            "Custom Alert Type": "CustomAgent",
            "Test Alert": "TestAgent"
        }
        
        # Act
        registry = AgentRegistry(config=custom_config)
        
        # Assert
        supported_types = registry.get_supported_alert_types()
        assert "Custom Alert Type" in supported_types
        assert "Test Alert" in supported_types
        
        agent_class = registry.get_agent_for_alert_type("Custom Alert Type")
        assert agent_class == "CustomAgent"

    def test_agent_registry_unknown_alert_type(self):
        """Test agent registry behavior with unknown alert types."""
        # Act & Assert
        registry = AgentRegistry()
        with pytest.raises(ValueError, match="No agent for alert type 'Unknown Alert Type'"):
            registry.get_agent_for_alert_type("Unknown Alert Type")


@pytest.mark.asyncio
@pytest.mark.integration
class TestAgentFactoryIntegration:
    """Test agent factory component and its interactions."""

    def test_agent_factory_initialization(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry
    ):
        """Test agent factory initialization."""
        # Act
        factory = AgentFactory(
            llm_client=mock_llm_manager,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        # Assert
        assert factory is not None
        assert factory.llm_client == mock_llm_manager
        assert factory.mcp_client == mock_mcp_client
        assert factory.mcp_registry == mock_mcp_server_registry
        assert len(factory.static_agent_classes) > 0
        assert "KubernetesAgent" in factory.static_agent_classes

    def test_agent_factory_kubernetes_agent_creation(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry
    ):
        """Test creation of KubernetesAgent through factory."""
        # Arrange
        factory = AgentFactory(
            llm_client=mock_llm_manager,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        # Act
        agent = factory.create_agent("KubernetesAgent")
        
        # Assert
        assert isinstance(agent, KubernetesAgent)
        assert agent.llm_client == mock_llm_manager
        assert agent.mcp_client == mock_mcp_client
        assert agent.mcp_registry == mock_mcp_server_registry

    def test_agent_factory_unknown_agent_error(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry
    ):
        """Test agent factory error handling for unknown agents."""
        # Arrange
        factory = AgentFactory(
            llm_client=mock_llm_manager,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        # Act & Assert
        with pytest.raises(ValueError, match="Unknown agent 'UnknownAgent'"):
            factory.create_agent("UnknownAgent")


@pytest.mark.asyncio
@pytest.mark.integration
class TestMCPServerRegistryIntegration:
    """Test MCP server registry component."""

    def test_mcp_server_registry_default_configuration(self):
        """Test MCP server registry with default configuration."""
        # Act
        registry = MCPServerRegistry()
        
        # Assert
        server_ids = registry.get_all_server_ids()
        assert "kubernetes-server" in server_ids
        
        config = registry.get_server_config("kubernetes-server")
        assert config is not None
        assert config.server_id == "kubernetes-server"
        assert config.server_type == "kubernetes"
        assert config.enabled is True

    def test_mcp_server_registry_server_configs_retrieval(self):
        """Test retrieving multiple server configurations."""
        # Arrange
        registry = MCPServerRegistry()
        
        # Act
        configs = registry.get_server_configs(["kubernetes-server"])
        
        # Assert
        assert len(configs) == 1
        assert configs[0].server_id == "kubernetes-server"

    def test_mcp_server_registry_custom_configuration(self):
        """Test MCP server registry with custom configuration."""
        # Arrange
        custom_config = {
            "test-server": {
                "server_id": "test-server",
                "server_type": "test",
                "enabled": True,
                "connection_params": {"command": "test"},
                "instructions": "Test instructions"
            }
        }
        
        # Act
        registry = MCPServerRegistry(config=custom_config)
        
        # Assert
        server_ids = registry.get_all_server_ids()
        assert "test-server" in server_ids
        
        config = registry.get_server_config("test-server")
        assert config.server_type == "test"
        assert config.instructions == "Test instructions"


@pytest.mark.asyncio
@pytest.mark.integration
class TestKubernetesAgentIntegration:
    """Test KubernetesAgent component in isolation."""

    def test_kubernetes_agent_mcp_servers(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry
    ):
        """Test KubernetesAgent MCP server assignment."""
        # Arrange & Act
        agent = KubernetesAgent(
            llm_client=mock_llm_manager.get_client(),
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        # Assert
        servers = agent.mcp_servers()
        assert servers == ["kubernetes-server"]

    def test_kubernetes_agent_custom_instructions(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry
    ):
        """Test KubernetesAgent custom instructions."""
        # Arrange & Act
        agent = KubernetesAgent(
            llm_client=mock_llm_manager.get_client(),
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        # Assert
        instructions = agent.custom_instructions()
        assert isinstance(instructions, str)  # May be empty but should be string

    # EP-0012 Clean Implementation: create_prompt_context method removed
    # Context creation now handled by StageContext in the clean architecture
    # This functionality is tested through the full processing pipeline tests


@pytest.mark.asyncio
@pytest.mark.integration
class TestLLMManagerIntegration:
    """Test LLM manager component integration."""

    def test_llm_manager_availability_checking(self, mock_settings):
        """Test LLM manager availability checking."""
        # Arrange - Create real LLM manager with mock settings
        manager = LLMManager(mock_settings)
        
        # Act
        is_available = manager.is_available()
        available_providers = manager.list_available_providers()
        status = manager.get_availability_status()
        
        # Assert
        assert isinstance(is_available, bool)
        assert isinstance(available_providers, list)
        assert isinstance(status, dict)

    def test_llm_manager_client_retrieval(self, mock_settings):
        """Test LLM manager client retrieval."""
        # Arrange
        manager = LLMManager(mock_settings)
        
        # Act
        client = manager.get_client()
        
        # Assert - Should return some client (may be mock or None based on availability)
        # The exact behavior depends on settings and availability
        assert client is not None or not manager.is_available()


@pytest.mark.asyncio
@pytest.mark.integration
class TestMCPClientIntegration:
    """Test MCP client component integration."""

    async def test_mcp_client_initialization(
        self, 
        mock_settings, 
        mock_mcp_server_registry
    ):
        """Test MCP client initialization with registry."""
        # Arrange & Act
        client = MCPClient(mock_settings, mock_mcp_server_registry)
        await client.initialize()
        
        # Assert
        assert client._initialized is True
        assert client.mcp_registry == mock_mcp_server_registry

    async def test_mcp_client_tool_listing_integration(
        self, 
        mock_settings, 
        mock_mcp_server_registry,
        mock_mcp_client
    ):
        """Test MCP client tool listing with real-like registry interaction."""
        # Arrange - Use the provided mock_mcp_client fixture which already returns 2 tools
        client = mock_mcp_client
        
        # Act - Fix: list_tools requires session_id as first parameter
        tools = await client.list_tools("test-session-123", server_name="kubernetes-server")
        
        # Assert
        assert "kubernetes-server" in tools
        assert len(tools["kubernetes-server"]) == 2
        tool_names = [tool["name"] for tool in tools["kubernetes-server"]]
        assert "kubectl_get_namespace" in tool_names
        assert "kubectl_get_pods" in tool_names


@pytest.mark.asyncio
@pytest.mark.integration
class TestServiceInteractionPatterns:
    """Test common interaction patterns between services."""

    async def test_agent_registry_factory_integration(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry
    ):
        """Test integration between agent registry and factory."""
        # Arrange
        registry = AgentRegistry()
        factory = AgentFactory(
            llm_client=mock_llm_manager,
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        alert_type = "NamespaceTerminating"
        
        # Act
        agent_class_name = registry.get_agent_for_alert_type(alert_type)
        agent = factory.create_agent(agent_class_name)
        
        # Assert
        assert agent_class_name == "KubernetesAgent"
        assert isinstance(agent, KubernetesAgent)

    async def test_agent_mcp_registry_integration(
        self, 
        mock_llm_manager, 
        mock_mcp_client
    ):
        """Test integration between agents and MCP server registry."""
        # Arrange
        registry = MCPServerRegistry()
        agent = KubernetesAgent(
            llm_client=mock_llm_manager.get_client(),
            mcp_client=mock_mcp_client,
            mcp_registry=registry
        )
        
        # Act
        required_servers = agent.mcp_servers()
        server_configs = registry.get_server_configs(required_servers)
        
        # Assert
        assert required_servers == ["kubernetes-server"]
        assert len(server_configs) == 1
        assert server_configs[0].server_id == "kubernetes-server"

    async def test_agent_llm_integration(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry,
        sample_alert,
        sample_runbook_content
    ):
        """Test integration between agents and LLM manager."""
        # Arrange
        agent = KubernetesAgent(
            llm_client=mock_llm_manager.get_client(),
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        # Create ChainContext for the new architecture
        from tarsy.models.processing_context import ChainContext
        chain_context = ChainContext(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.data,
            session_id="test-session-integration",
            current_stage_name="analysis",
            runbook_content=sample_runbook_content
        )
        
        # Act
        result = await agent.process_alert(chain_context)
        
        # Assert - With our new failure detection logic, this correctly fails when all LLM interactions fail
        from tarsy.models.agent_execution_result import AgentExecutionResult
        assert isinstance(result, AgentExecutionResult)
        assert result.result_summary
        assert len(result.result_summary) > 0
        assert result.status == StageStatus.FAILED  # New failure detection: max iterations + failed interactions = FAILED
        assert "reached maximum iterations" in result.error_message
        mock_llm_manager.get_client().generate_response.assert_called()

@pytest.mark.asyncio
@pytest.mark.integration
class TestErrorPropagationBetweenComponents:
    """Test error propagation and handling between components."""

    async def test_mcp_client_error_to_agent(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry,
        sample_alert,
        sample_runbook_content
    ):
        """Test error propagation from MCP client to agent."""
        # Arrange
        mock_mcp_client.call_tool.side_effect = Exception("MCP connection failed")
        
        agent = KubernetesAgent(
            llm_client=mock_llm_manager.get_client(),
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        # Act
        from tarsy.models.processing_context import ChainContext
        chain_context = ChainContext(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.data,
            session_id="test-session-integration",
            current_stage_name="analysis",
            runbook_content=sample_runbook_content
        )
        result = await agent.process_alert(chain_context)
        
        # Assert - Agent should handle MCP errors gracefully
        assert result is not None
        assert result.status in [StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.PARTIAL]

    async def test_llm_error_to_agent(
        self, 
        mock_llm_manager, 
        mock_mcp_client, 
        mock_mcp_server_registry,
        sample_alert,
        sample_runbook_content
    ):
        """Test error propagation from LLM to agent."""
        # Arrange
        mock_llm_manager.get_client().generate_response.side_effect = Exception("LLM API failed")
        
        agent = KubernetesAgent(
            llm_client=mock_llm_manager.get_client(),
            mcp_client=mock_mcp_client,
            mcp_registry=mock_mcp_server_registry
        )
        
        # Act
        from tarsy.models.processing_context import ChainContext
        chain_context = ChainContext(
            alert_type=sample_alert.alert_type,
            alert_data=sample_alert.data,
            session_id="test-session-integration",
            current_stage_name="analysis",
            runbook_content=sample_runbook_content
        )
        result = await agent.process_alert(chain_context)
        
        # Assert - Agent should handle LLM errors gracefully and now correctly fails with our new logic
        assert result is not None
        from tarsy.models.agent_execution_result import AgentExecutionResult
        assert isinstance(result, AgentExecutionResult)
        assert result.status == StageStatus.FAILED  # New behavior: persistent LLM errors now correctly fail the stage
        # Check that the result summary or final analysis indicates the issues
        analysis_text = result.final_analysis or result.result_summary
        assert "incomplete" in analysis_text or "failed" in analysis_text or "LLM API failed" in analysis_text

    def test_registry_misconfiguration_error(
        self, 
        mock_llm_manager, 
        mock_mcp_client
    ):
        """Test error handling for registry misconfiguration."""
        # Arrange - Create registry with truly empty configuration
        # Note: MCPServerRegistry({}) falls back to defaults, so we override static_servers
        empty_registry = MCPServerRegistry(config={})
        empty_registry.static_servers = {}  # Force empty registry for testing
        
        # Act & Assert
        agent = KubernetesAgent(
            llm_client=mock_llm_manager.get_client(),
            mcp_client=mock_mcp_client,
            mcp_registry=empty_registry
        )
        
        # The agent should be created but fail during configuration
        required_servers = agent.mcp_servers()
        server_configs = empty_registry.get_server_configs(required_servers)
        
        # Should return empty list for missing servers
        assert len(server_configs) == 0 