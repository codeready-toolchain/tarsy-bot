"""Unit tests for parallel agent configuration models."""

import pytest
from pydantic import ValidationError

from tarsy.models.agent_config import (
    ChainStageConfigModel,
    ParallelAgentConfig,
)
from tarsy.models.constants import FailurePolicy


@pytest.mark.unit
class TestParallelAgentConfig:
    """Test cases for ParallelAgentConfig validation."""

    def test_valid_parallel_agent_config(self) -> None:
        """Test valid parallel agent configuration."""
        config = ParallelAgentConfig(
            name="KubernetesAgent",
            llm_provider="openai",
            iteration_strategy="react"
        )
        
        assert config.name == "KubernetesAgent"
        assert config.llm_provider == "openai"
        assert config.iteration_strategy == "react"

    def test_minimal_parallel_agent_config(self) -> None:
        """Test minimal parallel agent configuration with only required fields."""
        config = ParallelAgentConfig(name="KubernetesAgent")
        
        assert config.name == "KubernetesAgent"
        assert config.llm_provider is None
        assert config.iteration_strategy is None

    def test_parallel_agent_config_with_configurable_agent(self) -> None:
        """Test parallel agent config with ConfigurableAgent reference."""
        config = ParallelAgentConfig(
            name="custom-agent",
            llm_provider="anthropic",
            iteration_strategy="native-thinking"
        )
        
        assert config.name == "custom-agent"
        assert config.llm_provider == "anthropic"
        assert config.iteration_strategy == "native-thinking"

    def test_parallel_agent_config_empty_name_fails(self) -> None:
        """Test that empty agent name fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ParallelAgentConfig(name="")
        
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    def test_parallel_agent_config_whitespace_name_trimmed(self) -> None:
        """Test that whitespace in agent name is trimmed."""
        config = ParallelAgentConfig(name="  KubernetesAgent  ")
        assert config.name == "KubernetesAgent"

    @pytest.mark.parametrize("provider", ["openai", "anthropic", "gemini", "xai"])
    def test_parallel_agent_config_valid_providers(self, provider: str) -> None:
        """Test parallel agent config with various LLM providers."""
        config = ParallelAgentConfig(name="TestAgent", llm_provider=provider)
        assert config.llm_provider == provider

    @pytest.mark.parametrize("strategy", ["react", "react-stage", "native-thinking"])
    def test_parallel_agent_config_valid_strategies(self, strategy: str) -> None:
        """Test parallel agent config with various iteration strategies."""
        config = ParallelAgentConfig(name="TestAgent", iteration_strategy=strategy)
        assert config.iteration_strategy == strategy


@pytest.mark.unit
class TestChainStageConfigModelParallelValidation:
    """Test cases for ChainStageConfigModel parallel execution validation."""

    def test_stage_with_single_agent(self) -> None:
        """Test stage configuration with single agent (non-parallel)."""
        stage = ChainStageConfigModel(
            name="analysis",
            agent="KubernetesAgent"
        )
        
        assert stage.name == "analysis"
        assert stage.agent == "KubernetesAgent"
        assert stage.agents is None
        assert stage.replicas == 1
        assert stage.failure_policy == FailurePolicy.ALL

    def test_stage_with_multi_agent_parallel(self) -> None:
        """Test stage configuration with multiple agents (parallel)."""
        stage = ChainStageConfigModel(
            name="investigation",
            agents=[
                ParallelAgentConfig(name="KubernetesAgent", llm_provider="openai"),
                ParallelAgentConfig(name="VMAgent", llm_provider="anthropic")
            ]
        )
        
        assert stage.name == "investigation"
        assert stage.agent is None
        assert len(stage.agents) == 2
        assert stage.agents[0].name == "KubernetesAgent"
        assert stage.agents[1].name == "VMAgent"

    def test_stage_with_replicas(self) -> None:
        """Test stage configuration with replicas (simple redundancy)."""
        stage = ChainStageConfigModel(
            name="analysis",
            agent="KubernetesAgent",
            replicas=3,
            llm_provider="openai"
        )
        
        assert stage.name == "analysis"
        assert stage.agent == "KubernetesAgent"
        assert stage.replicas == 3
        assert stage.llm_provider == "openai"

    def test_stage_with_failure_policy_any(self) -> None:
        """Test stage with 'any' failure policy (partial success allowed)."""
        stage = ChainStageConfigModel(
            name="investigation",
            agents=[
                ParallelAgentConfig(name="KubernetesAgent"),
                ParallelAgentConfig(name="VMAgent")
            ],
            failure_policy=FailurePolicy.ANY
        )
        
        assert stage.failure_policy == FailurePolicy.ANY

    def test_stage_missing_agent_and_agents_fails(self) -> None:
        """Test that stage without agent or agents field fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ChainStageConfigModel(name="invalid-stage")
        
        errors = exc_info.value.errors()
        assert any("Either 'agent' or 'agents' must be specified" in str(e["ctx"]) for e in errors)

    def test_stage_with_both_agent_and_agents_fails(self) -> None:
        """Test that stage with both agent and agents fields fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ChainStageConfigModel(
                name="invalid-stage",
                agent="KubernetesAgent",
                agents=[ParallelAgentConfig(name="VMAgent")]
            )
        
        errors = exc_info.value.errors()
        assert any("Cannot specify both 'agent' and 'agents'" in str(e["ctx"]) for e in errors)

    def test_stage_with_agents_list_and_replicas_fails(self) -> None:
        """Test that agents list with replicas > 1 fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ChainStageConfigModel(
                name="invalid-stage",
                agents=[
                    ParallelAgentConfig(name="KubernetesAgent"),
                    ParallelAgentConfig(name="VMAgent")
                ],
                replicas=3
            )
        
        errors = exc_info.value.errors()
        assert any("Cannot use 'agents' list with replicas > 1" in str(e["ctx"]) for e in errors)

    def test_stage_with_single_agent_in_agents_list_fails(self) -> None:
        """Test that agents list with only one agent fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ChainStageConfigModel(
                name="invalid-stage",
                agents=[ParallelAgentConfig(name="KubernetesAgent")]
            )
        
        errors = exc_info.value.errors()
        assert any("must contain at least 2 agents" in str(e["ctx"]) for e in errors)

    @pytest.mark.parametrize(
        "agents,expected_count",
        [
            ([ParallelAgentConfig(name="Agent1"), ParallelAgentConfig(name="Agent2")], 2),
            ([ParallelAgentConfig(name="Agent1"), ParallelAgentConfig(name="Agent2"), ParallelAgentConfig(name="Agent3")], 3),
            (
                [
                    ParallelAgentConfig(name="KubernetesAgent", llm_provider="openai"),
                    ParallelAgentConfig(name="KubernetesAgent", llm_provider="anthropic"),
                    ParallelAgentConfig(name="KubernetesAgent", llm_provider="gemini")
                ],
                3
            ),
        ],
    )
    def test_stage_with_multiple_parallel_agents(self, agents: list, expected_count: int) -> None:
        """Test stage with various multi-agent parallel configurations."""
        stage = ChainStageConfigModel(name="parallel-stage", agents=agents)
        
        assert len(stage.agents) == expected_count

    def test_stage_with_same_agent_different_configs(self) -> None:
        """Test stage with same agent but different LLM/strategy configs (A/B testing)."""
        stage = ChainStageConfigModel(
            name="comparison",
            agents=[
                ParallelAgentConfig(name="KubernetesAgent", llm_provider="openai", iteration_strategy="react"),
                ParallelAgentConfig(name="KubernetesAgent", llm_provider="anthropic", iteration_strategy="react-stage"),
                ParallelAgentConfig(name="KubernetesAgent", llm_provider="gemini", iteration_strategy="native-thinking")
            ]
        )
        
        assert len(stage.agents) == 3
        assert all(agent.name == "KubernetesAgent" for agent in stage.agents)
        assert stage.agents[0].llm_provider == "openai"
        assert stage.agents[1].llm_provider == "anthropic"
        assert stage.agents[2].llm_provider == "gemini"

    @pytest.mark.parametrize("replicas", [1, 2, 3, 5, 10])
    def test_stage_with_valid_replica_counts(self, replicas: int) -> None:
        """Test stage with various valid replica counts."""
        stage = ChainStageConfigModel(
            name="replicated-stage",
            agent="KubernetesAgent",
            replicas=replicas
        )
        
        assert stage.replicas == replicas

    def test_stage_with_zero_replicas_fails(self) -> None:
        """Test that replicas = 0 fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ChainStageConfigModel(
                name="invalid-stage",
                agent="KubernetesAgent",
                replicas=0
            )
        
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("replicas",) for e in errors)

    def test_stage_with_negative_replicas_fails(self) -> None:
        """Test that negative replicas fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ChainStageConfigModel(
                name="invalid-stage",
                agent="KubernetesAgent",
                replicas=-1
            )
        
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("replicas",) for e in errors)

    def test_stage_per_agent_overrides(self) -> None:
        """Test stage with per-agent LLM provider and iteration strategy overrides."""
        stage = ChainStageConfigModel(
            name="multi-config",
            agents=[
                ParallelAgentConfig(name="Agent1", llm_provider="openai"),
                ParallelAgentConfig(name="Agent2", iteration_strategy="react-stage"),
                ParallelAgentConfig(name="Agent3", llm_provider="anthropic", iteration_strategy="native-thinking")
            ]
        )
        
        assert stage.agents[0].llm_provider == "openai"
        assert stage.agents[0].iteration_strategy is None
        assert stage.agents[1].llm_provider is None
        assert stage.agents[1].iteration_strategy == "react-stage"
        assert stage.agents[2].llm_provider == "anthropic"
        assert stage.agents[2].iteration_strategy == "native-thinking"

    def test_stage_level_overrides_for_replicas(self) -> None:
        """Test stage-level LLM provider and iteration strategy for replicas."""
        stage = ChainStageConfigModel(
            name="replicated",
            agent="KubernetesAgent",
            replicas=3,
            llm_provider="openai",
            iteration_strategy="react"
        )
        
        assert stage.replicas == 3
        assert stage.llm_provider == "openai"
        assert stage.iteration_strategy == "react"

    @pytest.mark.parametrize("policy", [FailurePolicy.ALL, FailurePolicy.ANY])
    def test_stage_failure_policies(self, policy: FailurePolicy) -> None:
        """Test stage with different failure policies."""
        stage = ChainStageConfigModel(
            name="policy-test",
            agents=[
                ParallelAgentConfig(name="Agent1"),
                ParallelAgentConfig(name="Agent2")
            ],
            failure_policy=policy
        )
        
        assert stage.failure_policy == policy

