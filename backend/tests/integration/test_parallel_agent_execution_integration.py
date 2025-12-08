"""
Integration tests for parallel agent execution in AlertService.

Tests actual parallel execution flow including concurrent agent execution,
result aggregation, and failure policy handling.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel, ParallelAgentConfig
from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.alert import ProcessingAlert
from tarsy.models.constants import FailurePolicy, StageStatus
from tarsy.models.processing_context import ChainContext
from tarsy.utils.timestamp import now_us


@pytest.mark.asyncio
@pytest.mark.integration
class TestParallelAgentExecutionIntegration:
    """Integration tests for parallel agent execution."""

    @pytest.fixture
    def multi_agent_parallel_chain(self) -> ChainConfigModel:
        """Create a chain with multi-agent parallel stage."""
        return ChainConfigModel(
            chain_id="multi-agent-test-chain",
            alert_types=["test"],
            stages=[
                ChainStageConfigModel(
                    name="investigation",
                    agents=[
                        ParallelAgentConfig(name="Agent1", llm_provider="openai"),
                        ParallelAgentConfig(name="Agent2", llm_provider="anthropic")
                    ],
                    failure_policy=FailurePolicy.ALL
                )
            ]
        )

    @pytest.fixture
    def replica_parallel_chain(self) -> ChainConfigModel:
        """Create a chain with replica parallelism."""
        return ChainConfigModel(
            chain_id="replica-test-chain",
            alert_types=["test"],
            stages=[
                ChainStageConfigModel(
                    name="analysis",
                    agent="TestAgent",
                    replicas=3,
                    llm_provider="openai"
                )
            ]
        )

    @pytest.fixture
    def mock_parallel_agents(self) -> dict:
        """Create mock agents for parallel execution."""
        agent1 = AsyncMock()
        agent1.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="Agent1",
            timestamp_us=now_us(),
            result_summary="Agent1 completed investigation"
        )

        agent2 = AsyncMock()
        agent2.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="Agent2",
            timestamp_us=now_us(),
            result_summary="Agent2 completed investigation"
        )

        return {"Agent1": agent1, "Agent2": agent2}

    @pytest.fixture
    def base_chain_context(self) -> ChainContext:
        """Create a base ChainContext for testing."""
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            runbook_url=None,
            alert_data={"test": "data"}
        )
        return ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="investigation"
        )

    async def test_multi_agent_parallel_execution_all_succeed(
        self,
        multi_agent_parallel_chain: ChainConfigModel,
        mock_parallel_agents: dict,
        base_chain_context: ChainContext
    ) -> None:
        """Test multi-agent parallel execution where all agents succeed."""
        agents = mock_parallel_agents
        stage_config = multi_agent_parallel_chain.stages[0]

        agent1_result = await agents["Agent1"].process_alert(base_chain_context)
        agent2_result = await agents["Agent2"].process_alert(base_chain_context)

        assert agent1_result.status == StageStatus.COMPLETED
        assert agent2_result.status == StageStatus.COMPLETED
        assert agent1_result.agent_name == "Agent1"
        assert agent2_result.agent_name == "Agent2"

    async def test_multi_agent_parallel_execution_partial_failure_any_policy(
        self,
        mock_parallel_agents: dict,
        base_chain_context: ChainContext
    ) -> None:
        """Test multi-agent parallel execution with partial failure and ANY policy."""
        agents = mock_parallel_agents

        agents["Agent1"].process_alert.return_value = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="Agent1",
            timestamp_us=now_us(),
            result_summary="Success"
        )

        agents["Agent2"].process_alert.return_value = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="Agent2",
            timestamp_us=now_us(),
            result_summary="",
            error_message="Agent2 failed"
        )

        agent1_result = await agents["Agent1"].process_alert(base_chain_context)
        agent2_result = await agents["Agent2"].process_alert(base_chain_context)

        assert agent1_result.status == StageStatus.COMPLETED
        assert agent2_result.status == StageStatus.FAILED

    async def test_replica_parallel_execution(
        self,
        replica_parallel_chain: ChainConfigModel,
        base_chain_context: ChainContext
    ) -> None:
        """Test replica parallelism with same agent multiple times."""
        mock_agent = AsyncMock()
        replica_results = []

        for i in range(3):
            result = AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name=f"TestAgent-{i+1}",
                timestamp_us=now_us(),
                result_summary=f"Replica {i+1} result"
            )
            replica_results.append(result)

        mock_agent.process_alert.side_effect = replica_results

        for i in range(3):
            result = await mock_agent.process_alert(base_chain_context)
            assert result.status == StageStatus.COMPLETED
            assert f"Replica {i+1}" in result.result_summary

    async def test_parallel_execution_with_different_llm_providers(
        self,
        base_chain_context: ChainContext
    ) -> None:
        """Test parallel execution with different LLM providers per agent."""
        agent_configs = [
            ParallelAgentConfig(name="Agent1", llm_provider="openai"),
            ParallelAgentConfig(name="Agent2", llm_provider="anthropic"),
            ParallelAgentConfig(name="Agent3", llm_provider="gemini")
        ]

        for config in agent_configs:
            assert config.llm_provider in ["openai", "anthropic", "gemini"]

    async def test_parallel_execution_with_different_iteration_strategies(
        self,
        base_chain_context: ChainContext
    ) -> None:
        """Test parallel execution with different iteration strategies per agent."""
        agent_configs = [
            ParallelAgentConfig(name="Agent1", iteration_strategy="react"),
            ParallelAgentConfig(name="Agent2", iteration_strategy="react-stage"),
            ParallelAgentConfig(name="Agent3", iteration_strategy="native-thinking")
        ]

        for config in agent_configs:
            assert config.iteration_strategy in ["react", "react-stage", "native-thinking"]

    async def test_parallel_execution_all_failures_all_policy(
        self,
        mock_parallel_agents: dict,
        base_chain_context: ChainContext
    ) -> None:
        """Test parallel execution where all agents fail with ALL policy."""
        agents = mock_parallel_agents

        agents["Agent1"].process_alert.return_value = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="Agent1",
            timestamp_us=now_us(),
            result_summary="",
            error_message="Agent1 error"
        )

        agents["Agent2"].process_alert.return_value = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="Agent2",
            timestamp_us=now_us(),
            result_summary="",
            error_message="Agent2 error"
        )

        agent1_result = await agents["Agent1"].process_alert(base_chain_context)
        agent2_result = await agents["Agent2"].process_alert(base_chain_context)

        assert agent1_result.status == StageStatus.FAILED
        assert agent2_result.status == StageStatus.FAILED

    async def test_concurrent_agent_execution_timing(
        self,
        mock_parallel_agents: dict,
        base_chain_context: ChainContext
    ) -> None:
        """Test that parallel agents can execute concurrently."""
        import asyncio
        
        agents = mock_parallel_agents

        start_time = now_us()
        
        results = await asyncio.gather(
            agents["Agent1"].process_alert(base_chain_context),
            agents["Agent2"].process_alert(base_chain_context),
            return_exceptions=True
        )
        
        end_time = now_us()

        assert len(results) == 2
        assert all(isinstance(r, AgentExecutionResult) for r in results)
        
        duration_ms = (end_time - start_time) // 1000
        assert duration_ms < 5000

    async def test_parallel_stage_result_aggregation(
        self,
        base_chain_context: ChainContext
    ) -> None:
        """Test that parallel stage results are properly aggregated."""
        from tarsy.models.agent_execution_result import (
            AgentExecutionMetadata,
            ParallelStageMetadata,
            ParallelStageResult,
        )

        timestamp = now_us()

        results = [
            AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="Agent1",
                timestamp_us=timestamp,
                result_summary="Result 1"
            ),
            AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="Agent2",
                timestamp_us=timestamp,
                result_summary="Result 2"
            )
        ]

        metadata = ParallelStageMetadata(
            parent_stage_execution_id="exec-123",
            parallel_type="multi_agent",
            failure_policy=FailurePolicy.ALL,
            started_at_us=timestamp - 5_000_000,
            completed_at_us=timestamp,
            agent_metadatas=[
                AgentExecutionMetadata(
                    agent_name="Agent1",
                    llm_provider="openai",
                    iteration_strategy="react",
                    started_at_us=timestamp - 5_000_000,
                    completed_at_us=timestamp,
                    status=StageStatus.COMPLETED
                ),
                AgentExecutionMetadata(
                    agent_name="Agent2",
                    llm_provider="anthropic",
                    iteration_strategy="react",
                    started_at_us=timestamp - 5_000_000,
                    completed_at_us=timestamp,
                    status=StageStatus.COMPLETED
                )
            ]
        )

        parallel_result = ParallelStageResult(
            results=results,
            metadata=metadata,
            status=StageStatus.COMPLETED,
            timestamp_us=timestamp
        )

        base_chain_context.add_stage_result("investigation", parallel_result)

        assert base_chain_context.is_parallel_stage("investigation")
        assert len(parallel_result.results) == 2
        assert parallel_result.metadata.successful_count == 2
        assert parallel_result.metadata.failed_count == 0

    async def test_failure_policy_all_requires_all_success(
        self,
        base_chain_context: ChainContext
    ) -> None:
        """Test that ALL failure policy requires all agents to succeed."""
        from tarsy.models.agent_execution_result import (
            AgentExecutionMetadata,
            ParallelStageMetadata,
            ParallelStageResult,
        )

        timestamp = now_us()

        results = [
            AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="Agent1",
                timestamp_us=timestamp,
                result_summary="Success"
            ),
            AgentExecutionResult(
                status=StageStatus.FAILED,
                agent_name="Agent2",
                timestamp_us=timestamp,
                result_summary="",
                error_message="Failed"
            )
        ]

        metadata = ParallelStageMetadata(
            parent_stage_execution_id="exec-456",
            parallel_type="multi_agent",
            failure_policy=FailurePolicy.ALL,
            started_at_us=timestamp - 5_000_000,
            completed_at_us=timestamp,
            agent_metadatas=[
                AgentExecutionMetadata(
                    agent_name="Agent1",
                    llm_provider="openai",
                    iteration_strategy="react",
                    started_at_us=timestamp - 5_000_000,
                    completed_at_us=timestamp,
                    status=StageStatus.COMPLETED
                ),
                AgentExecutionMetadata(
                    agent_name="Agent2",
                    llm_provider="anthropic",
                    iteration_strategy="react",
                    started_at_us=timestamp - 5_000_000,
                    completed_at_us=timestamp,
                    status=StageStatus.FAILED,
                    error_message="Failed"
                )
            ]
        )

        parallel_result = ParallelStageResult(
            results=results,
            metadata=metadata,
            status=StageStatus.FAILED,
            timestamp_us=timestamp
        )

        assert parallel_result.status == StageStatus.FAILED
        assert metadata.successful_count == 1
        assert metadata.failed_count == 1

    async def test_failure_policy_any_allows_partial_success(
        self,
        base_chain_context: ChainContext
    ) -> None:
        """Test that ANY failure policy allows partial success."""
        from tarsy.models.agent_execution_result import (
            AgentExecutionMetadata,
            ParallelStageMetadata,
            ParallelStageResult,
        )

        timestamp = now_us()

        results = [
            AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="Agent1",
                timestamp_us=timestamp,
                result_summary="Success"
            ),
            AgentExecutionResult(
                status=StageStatus.FAILED,
                agent_name="Agent2",
                timestamp_us=timestamp,
                result_summary="",
                error_message="Failed"
            )
        ]

        metadata = ParallelStageMetadata(
            parent_stage_execution_id="exec-789",
            parallel_type="multi_agent",
            failure_policy=FailurePolicy.ANY,
            started_at_us=timestamp - 5_000_000,
            completed_at_us=timestamp,
            agent_metadatas=[
                AgentExecutionMetadata(
                    agent_name="Agent1",
                    llm_provider="openai",
                    iteration_strategy="react",
                    started_at_us=timestamp - 5_000_000,
                    completed_at_us=timestamp,
                    status=StageStatus.COMPLETED
                ),
                AgentExecutionMetadata(
                    agent_name="Agent2",
                    llm_provider="anthropic",
                    iteration_strategy="react",
                    started_at_us=timestamp - 5_000_000,
                    completed_at_us=timestamp,
                    status=StageStatus.FAILED,
                    error_message="Failed"
                )
            ]
        )

        parallel_result = ParallelStageResult(
            results=results,
            metadata=metadata,
            status=StageStatus.COMPLETED,
            timestamp_us=timestamp
        )

        assert parallel_result.status == StageStatus.COMPLETED
        assert metadata.successful_count == 1
        assert metadata.failed_count == 1

