"""
Unit tests for unified execution configuration resolver.

Tests the ExecutionConfigResolver that consolidates all configuration
resolution (iteration, MCP servers, LLM provider, iteration strategy).
"""

import pytest
from unittest.mock import Mock

from tarsy.config.settings import Settings
from tarsy.models.agent_config import (
    AgentConfigModel,
    ChainConfigModel,
    ChainStageConfigModel,
    IterationStrategy,
    ParallelAgentConfig,
)
from tarsy.models.agent_execution_config import AgentExecutionConfig
from tarsy.services.execution_config_resolver import ExecutionConfigResolver


@pytest.mark.unit
class TestExecutionConfigResolver:
    """Test suite for ExecutionConfigResolver."""
    
    @pytest.fixture
    def settings(self):
        """Create mock settings."""
        settings = Mock(spec=Settings)
        settings.max_llm_mcp_iterations = 30
        settings.force_conclusion_at_max_iterations = False
        return settings
    
    def test_resolve_config_system_defaults_only(self, settings):
        """Test resolution with only system defaults."""
        config = ExecutionConfigResolver.resolve_config(system_settings=settings)
        
        assert isinstance(config, AgentExecutionConfig)
        assert config.max_iterations == 30
        assert config.force_conclusion is False
        assert config.llm_provider is None
        assert config.iteration_strategy is None
        assert config.mcp_servers is None
    
    def test_resolve_config_with_agent_level(self, settings):
        """Test resolution with agent-level configuration."""
        agent_config = AgentConfigModel(
            mcp_servers=["agent-server"],
            custom_instructions="test",
            iteration_strategy=IterationStrategy.REACT,
            max_iterations=20,
            force_conclusion_at_max_iterations=True
        )
        
        config = ExecutionConfigResolver.resolve_config(
            system_settings=settings,
            agent_config=agent_config
        )
        
        assert config.max_iterations == 20
        assert config.force_conclusion is True
        assert config.iteration_strategy == "react"
        assert config.mcp_servers == ["agent-server"]
        assert config.llm_provider is None  # Agent level doesn't have llm_provider
    
    def test_resolve_config_with_chain_level_overrides(self, settings):
        """Test resolution with chain-level overrides."""
        agent_config = AgentConfigModel(
            mcp_servers=["agent-server"],
            custom_instructions="test",
            max_iterations=20
        )
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[ChainStageConfigModel(name="dummy-stage", agent="TestAgent")],
            mcp_servers=["chain-server"],
            llm_provider="chain-provider",
            max_iterations=25
        )
        
        config = ExecutionConfigResolver.resolve_config(
            system_settings=settings,
            agent_config=agent_config,
            chain_config=chain_config
        )
        
        assert config.max_iterations == 25  # Chain overrides agent
        assert config.mcp_servers == ["chain-server"]  # Chain overrides agent
        assert config.llm_provider == "chain-provider"
    
    def test_resolve_config_with_stage_level_overrides(self, settings):
        """Test resolution with stage-level overrides."""
        agent_config = AgentConfigModel(
            mcp_servers=["agent-server"],
            custom_instructions="test",
            iteration_strategy=IterationStrategy.REACT
        )
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[ChainStageConfigModel(name="dummy-stage", agent="TestAgent")],
            mcp_servers=["chain-server"],
            llm_provider="chain-provider"
        )
        stage_config = ChainStageConfigModel(
            name="test-stage",
            agent="TestAgent",
            mcp_servers=["stage-server"],
            llm_provider="stage-provider",
            iteration_strategy=IterationStrategy.NATIVE_THINKING,
            max_iterations=15
        )
        
        config = ExecutionConfigResolver.resolve_config(
            system_settings=settings,
            agent_config=agent_config,
            chain_config=chain_config,
            stage_config=stage_config
        )
        
        assert config.max_iterations == 15  # Stage overrides chain
        assert config.mcp_servers == ["stage-server"]  # Stage overrides chain
        assert config.llm_provider == "stage-provider"  # Stage overrides chain
        assert config.iteration_strategy == "native-thinking"  # Stage overrides agent
    
    def test_resolve_config_with_parallel_agent_highest_priority(self, settings):
        """Test resolution with parallel-agent level (highest priority)."""
        agent_config = AgentConfigModel(
            mcp_servers=["agent-server"],
            custom_instructions="test",
            iteration_strategy=IterationStrategy.REACT
        )
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["test"],
            stages=[ChainStageConfigModel(name="dummy-stage", agent="TestAgent")],
            mcp_servers=["chain-server"]
        )
        stage_config = ChainStageConfigModel(
            name="test-stage",
            agent="TestAgent",
            mcp_servers=["stage-server"],
            iteration_strategy=IterationStrategy.NATIVE_THINKING
        )
        parallel_agent_config = ParallelAgentConfig(
            name="ParallelAgent",
            mcp_servers=["parallel-server"],
            llm_provider="parallel-provider",
            iteration_strategy=IterationStrategy.REACT_STAGE,
            max_iterations=10,
            force_conclusion_at_max_iterations=True
        )
        
        config = ExecutionConfigResolver.resolve_config(
            system_settings=settings,
            agent_config=agent_config,
            chain_config=chain_config,
            stage_config=stage_config,
            parallel_agent_config=parallel_agent_config
        )
        
        # Parallel-agent has highest priority for all fields
        assert config.max_iterations == 10
        assert config.force_conclusion is True
        assert config.mcp_servers == ["parallel-server"]
        assert config.llm_provider == "parallel-provider"
        assert config.iteration_strategy == "react-stage"
    
    def test_normalize_iteration_strategy_enum(self):
        """Test normalization of IterationStrategy enum to string."""
        result = ExecutionConfigResolver._normalize_iteration_strategy(
            IterationStrategy.NATIVE_THINKING
        )
        assert result == "native-thinking"
    
    def test_normalize_iteration_strategy_string(self):
        """Test normalization of string strategy (pass-through)."""
        result = ExecutionConfigResolver._normalize_iteration_strategy("react")
        assert result == "react"
    
    def test_normalize_iteration_strategy_none(self):
        """Test normalization of None strategy."""
        result = ExecutionConfigResolver._normalize_iteration_strategy(None)
        assert result is None
    
    def test_resolve_config_preserves_none_when_not_set(self, settings):
        """Test that None is preserved when config levels don't specify values."""
        config = ExecutionConfigResolver.resolve_config(
            system_settings=settings
        )
        
        # These should be None when not specified at any level
        assert config.llm_provider is None
        assert config.iteration_strategy is None
        assert config.mcp_servers is None
        
        # These come from system settings
        assert config.max_iterations == 30
        assert config.force_conclusion is False
