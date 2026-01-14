"""
Integration tests for hierarchical iteration configuration.

Tests that agents properly respect iteration configuration from different hierarchy levels.
"""

import pytest
from tarsy.config.settings import Settings
from tarsy.models.agent_config import (
    AgentConfigModel,
    ChainConfigModel,
    ChainStageConfigModel,
    ParallelAgentConfig,
)
from tarsy.services.agent_factory import AgentFactory
from tarsy.services.iteration_config_resolver import IterationConfigResolver
from tarsy.services.mcp_server_registry import MCPServerRegistry


@pytest.mark.asyncio
@pytest.mark.integration
class TestHierarchicalIterationConfig:
    """Integration tests for hierarchical iteration configuration."""

    @pytest.fixture
    def settings(self):
        """Create test settings with known defaults."""
        return Settings(
            max_llm_mcp_iterations=30,
            force_conclusion_at_max_iterations=False
        )

    @pytest.fixture
    def mcp_registry(self):
        """Create minimal MCP registry."""
        return MCPServerRegistry(config={}, configured_servers={})

    @pytest.fixture
    def agent_factory(self, mock_llm_manager, mcp_registry):
        """Create agent factory with test dependencies."""
        return AgentFactory(
            llm_manager=mock_llm_manager,
            mcp_registry=mcp_registry,
            agent_configs={}
        )

    def test_agent_respects_max_iterations_override(
        self, agent_factory, mock_mcp_client, settings
    ):
        """Test that agent instance respects max_iterations override."""
        # Create agent with default settings
        agent = agent_factory.get_agent(
            agent_identifier="KubernetesAgent",
            mcp_client=mock_mcp_client
        )
        
        # Should have system default
        assert agent.max_iterations == 30
        
        # Override with higher value
        agent_with_override = agent_factory.get_agent(
            agent_identifier="KubernetesAgent",
            mcp_client=mock_mcp_client,
            max_iterations=50
        )
        
        assert agent_with_override.max_iterations == 50

    def test_agent_respects_force_conclusion_override(
        self, agent_factory, mock_mcp_client, settings
    ):
        """Test that agent instance respects force_conclusion override."""
        # Create agent with default settings
        agent = agent_factory.get_agent(
            agent_identifier="KubernetesAgent",
            mcp_client=mock_mcp_client
        )
        
        # Should have system default
        assert agent.get_force_conclusion() is False
        
        # Override with True
        agent_with_override = agent_factory.get_agent(
            agent_identifier="KubernetesAgent",
            mcp_client=mock_mcp_client,
            force_conclusion=True
        )
        
        assert agent_with_override.get_force_conclusion() is True

    def test_hierarchy_resolution_integration(self, settings):
        """Test full hierarchy resolution with all levels."""
        # System: 30, False
        # Agent: 35, True
        agent_config = AgentConfigModel(
            mcp_servers=["test-server"],
            max_iterations=35,
            force_conclusion_at_max_iterations=True
        )
        
        # Chain: 25, None (inherits from agent)
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[],
            max_iterations=25
        )
        
        # Stage: 20, False
        stage_config = ChainStageConfigModel(
            name="test-stage",
            agent="TestAgent",
            max_iterations=20,
            force_conclusion_at_max_iterations=False
        )
        
        # Parallel: 15, True (highest precedence)
        parallel_config = ParallelAgentConfig(
            name="TestAgent",
            max_iterations=15,
            force_conclusion_at_max_iterations=True
        )
        
        max_iter, force_conclude = IterationConfigResolver.resolve_iteration_config(
            system_settings=settings,
            agent_config=agent_config,
            chain_config=chain_config,
            stage_config=stage_config,
            parallel_agent_config=parallel_config
        )
        
        # Should use parallel agent values (highest precedence)
        assert max_iter == 15
        assert force_conclude is True

    def test_agent_setter_methods(self, agent_factory, mock_mcp_client):
        """Test that agent setter methods work correctly."""
        agent = agent_factory.get_agent(
            agent_identifier="KubernetesAgent",
            mcp_client=mock_mcp_client
        )
        
        # Test set_max_iterations
        agent.set_max_iterations(100)
        assert agent.max_iterations == 100
        
        # Test set_force_conclusion
        agent.set_force_conclusion(True)
        assert agent.get_force_conclusion() is True
        
        # Test validation
        with pytest.raises(ValueError, match="max_iterations must be >= 1"):
            agent.set_max_iterations(0)

    def test_multiple_agents_independent_config(
        self, agent_factory, mock_mcp_client
    ):
        """Test that multiple agent instances have independent configurations."""
        agent1 = agent_factory.get_agent(
            agent_identifier="KubernetesAgent",
            mcp_client=mock_mcp_client,
            max_iterations=10,
            force_conclusion=True
        )
        
        agent2 = agent_factory.get_agent(
            agent_identifier="KubernetesAgent",
            mcp_client=mock_mcp_client,
            max_iterations=50,
            force_conclusion=False
        )
        
        # Each agent should have its own configuration
        assert agent1.max_iterations == 10
        assert agent1.get_force_conclusion() is True
        
        assert agent2.max_iterations == 50
        assert agent2.get_force_conclusion() is False
