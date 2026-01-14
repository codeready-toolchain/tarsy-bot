"""
Unit tests for IterationConfigResolver.

Tests the hierarchical configuration resolution logic for max_iterations
and force_conclusion_at_max_iterations settings.
"""

import pytest

from tarsy.config.settings import Settings
from tarsy.models.agent_config import (
    AgentConfigModel,
    ChainConfigModel,
    ChainStageConfigModel,
    ParallelAgentConfig,
)
from tarsy.services.iteration_config_resolver import IterationConfigResolver


@pytest.mark.unit
class TestIterationConfigResolver:
    """Test suite for IterationConfigResolver."""

    def test_system_defaults_only(self):
        """Test resolution with only system defaults."""
        settings = Settings(
            max_llm_mcp_iterations=30,
            force_conclusion_at_max_iterations=False
        )
        
        max_iter, force_conclude = IterationConfigResolver.resolve_iteration_config(
            system_settings=settings
        )
        
        assert max_iter == 30
        assert force_conclude is False

    def test_agent_level_override(self):
        """Test agent-level configuration overrides system defaults."""
        settings = Settings(
            max_llm_mcp_iterations=30,
            force_conclusion_at_max_iterations=False
        )
        
        agent_config = AgentConfigModel(
            mcp_servers=["test-server"],
            max_iterations=35,
            force_conclusion_at_max_iterations=True
        )
        
        max_iter, force_conclude = IterationConfigResolver.resolve_iteration_config(
            system_settings=settings,
            agent_config=agent_config
        )
        
        assert max_iter == 35
        assert force_conclude is True

    def test_chain_level_override(self):
        """Test chain-level configuration overrides agent and system."""
        settings = Settings(
            max_llm_mcp_iterations=30,
            force_conclusion_at_max_iterations=False
        )
        
        agent_config = AgentConfigModel(
            mcp_servers=["test-server"],
            max_iterations=35,
            force_conclusion_at_max_iterations=True
        )
        
        # Create a minimal stage for validation
        stage = ChainStageConfigModel(name="test", agent="TestAgent")
        
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[stage],
            max_iterations=25,
            force_conclusion_at_max_iterations=False
        )
        
        max_iter, force_conclude = IterationConfigResolver.resolve_iteration_config(
            system_settings=settings,
            agent_config=agent_config,
            chain_config=chain_config
        )
        
        assert max_iter == 25
        assert force_conclude is False

    def test_stage_level_override(self):
        """Test stage-level configuration overrides chain, agent, and system."""
        settings = Settings(
            max_llm_mcp_iterations=30,
            force_conclusion_at_max_iterations=False
        )
        
        agent_config = AgentConfigModel(
            mcp_servers=["test-server"],
            max_iterations=35
        )
        
        # Create a minimal stage for validation
        stage = ChainStageConfigModel(name="test", agent="TestAgent")
        
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[stage],
            max_iterations=25
        )
        
        stage_config = ChainStageConfigModel(
            name="test-stage",
            agent="TestAgent",
            max_iterations=20,
            force_conclusion_at_max_iterations=True
        )
        
        max_iter, force_conclude = IterationConfigResolver.resolve_iteration_config(
            system_settings=settings,
            agent_config=agent_config,
            chain_config=chain_config,
            stage_config=stage_config
        )
        
        assert max_iter == 20
        assert force_conclude is True

    def test_parallel_agent_override(self):
        """Test parallel agent configuration has highest precedence."""
        settings = Settings(
            max_llm_mcp_iterations=30,
            force_conclusion_at_max_iterations=False
        )
        
        agent_config = AgentConfigModel(
            mcp_servers=["test-server"],
            max_iterations=35
        )
        
        # Create a minimal stage for validation
        stage = ChainStageConfigModel(name="test", agent="TestAgent")
        
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[stage],
            max_iterations=25
        )
        
        stage_config = ChainStageConfigModel(
            name="test-stage",
            agent="TestAgent",
            max_iterations=20
        )
        
        parallel_agent_config = ParallelAgentConfig(
            name="TestAgent",
            max_iterations=15,
            force_conclusion_at_max_iterations=True
        )
        
        max_iter, force_conclude = IterationConfigResolver.resolve_iteration_config(
            system_settings=settings,
            agent_config=agent_config,
            chain_config=chain_config,
            stage_config=stage_config,
            parallel_agent_config=parallel_agent_config
        )
        
        assert max_iter == 15
        assert force_conclude is True

    def test_partial_overrides(self):
        """Test that only specified values are overridden."""
        settings = Settings(
            max_llm_mcp_iterations=30,
            force_conclusion_at_max_iterations=False
        )
        
        # Agent only overrides max_iterations
        agent_config = AgentConfigModel(
            mcp_servers=["test-server"],
            max_iterations=35
            # force_conclusion_at_max_iterations not set (None)
        )
        
        # Chain only overrides force_conclusion
        # Create a minimal stage for validation
        stage = ChainStageConfigModel(name="test", agent="TestAgent")
        
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[stage],
            force_conclusion_at_max_iterations=True
            # max_iterations not set (None)
        )
        
        max_iter, force_conclude = IterationConfigResolver.resolve_iteration_config(
            system_settings=settings,
            agent_config=agent_config,
            chain_config=chain_config
        )
        
        # max_iterations from agent (35), force_conclusion from chain (True)
        assert max_iter == 35
        assert force_conclude is True

    def test_none_values_fallthrough(self):
        """Test that None values fall through to lower levels."""
        settings = Settings(
            max_llm_mcp_iterations=30,
            force_conclusion_at_max_iterations=False
        )
        
        # All configs have None values
        agent_config = AgentConfigModel(
            mcp_servers=["test-server"]
            # Both iteration settings None
        )
        
        # Create a minimal stage for validation
        stage = ChainStageConfigModel(name="test", agent="TestAgent")
        
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[stage]
            # Both iteration settings None
        )
        
        stage_config = ChainStageConfigModel(
            name="test-stage",
            agent="TestAgent"
            # Both iteration settings None
        )
        
        max_iter, force_conclude = IterationConfigResolver.resolve_iteration_config(
            system_settings=settings,
            agent_config=agent_config,
            chain_config=chain_config,
            stage_config=stage_config
        )
        
        # Should use system defaults
        assert max_iter == 30
        assert force_conclude is False

    def test_mixed_hierarchy(self):
        """Test complex scenario with mixed overrides at different levels."""
        settings = Settings(
            max_llm_mcp_iterations=30,
            force_conclusion_at_max_iterations=False
        )
        
        # Agent sets both
        agent_config = AgentConfigModel(
            mcp_servers=["test-server"],
            max_iterations=35,
            force_conclusion_at_max_iterations=True
        )
        
        # Chain only sets max_iterations
        # Create a minimal stage for validation
        stage = ChainStageConfigModel(name="test", agent="TestAgent")
        
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[stage],
            max_iterations=25
        )
        
        # Stage only sets force_conclusion
        stage_config = ChainStageConfigModel(
            name="test-stage",
            agent="TestAgent",
            force_conclusion_at_max_iterations=False
        )
        
        max_iter, force_conclude = IterationConfigResolver.resolve_iteration_config(
            system_settings=settings,
            agent_config=agent_config,
            chain_config=chain_config,
            stage_config=stage_config
        )
        
        # max_iterations from chain (25), force_conclusion from stage (False)
        assert max_iter == 25
        assert force_conclude is False
