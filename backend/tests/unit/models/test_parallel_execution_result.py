"""Unit tests for parallel execution result models."""

import pytest

from tarsy.models.agent_execution_result import (
    AgentExecutionMetadata,
    AgentExecutionResult,
    ParallelStageMetadata,
    ParallelStageResult,
)
from tarsy.models.constants import FailurePolicy, StageStatus
from tarsy.utils.timestamp import now_us


@pytest.mark.unit
class TestAgentExecutionMetadata:
    """Test cases for AgentExecutionMetadata model."""

    def test_valid_agent_execution_metadata(self) -> None:
        """Test creating valid agent execution metadata."""
        start_time = now_us()
        end_time = start_time + 5_000_000
        
        metadata = AgentExecutionMetadata(
            agent_name="KubernetesAgent-1",
            llm_provider="openai",
            iteration_strategy="react",
            started_at_us=start_time,
            completed_at_us=end_time,
            status=StageStatus.COMPLETED
        )
        
        assert metadata.agent_name == "KubernetesAgent-1"
        assert metadata.llm_provider == "openai"
        assert metadata.iteration_strategy == "react"
        assert metadata.status == StageStatus.COMPLETED
        assert metadata.error_message is None
        assert metadata.token_usage is None

    def test_agent_execution_metadata_duration_calculation(self) -> None:
        """Test duration_ms property calculation."""
        start_time = now_us()
        end_time = start_time + 5_234_567
        
        metadata = AgentExecutionMetadata(
            agent_name="TestAgent",
            llm_provider="gemini",
            iteration_strategy="react",
            started_at_us=start_time,
            completed_at_us=end_time,
            status=StageStatus.COMPLETED
        )
        
        assert metadata.duration_ms == 5234

    def test_agent_execution_metadata_with_error(self) -> None:
        """Test agent execution metadata with error information."""
        metadata = AgentExecutionMetadata(
            agent_name="FailedAgent",
            llm_provider="anthropic",
            iteration_strategy="native-thinking",
            started_at_us=now_us(),
            completed_at_us=now_us() + 1_000_000,
            status=StageStatus.FAILED,
            error_message="Connection timeout"
        )
        
        assert metadata.status == StageStatus.FAILED
        assert metadata.error_message == "Connection timeout"

    def test_agent_execution_metadata_with_token_usage(self) -> None:
        """Test agent execution metadata with token usage statistics."""
        metadata = AgentExecutionMetadata(
            agent_name="TestAgent",
            llm_provider="openai",
            iteration_strategy="react",
            started_at_us=now_us(),
            completed_at_us=now_us() + 1_000_000,
            status=StageStatus.COMPLETED,
            token_usage={
                "input_tokens": 1500,
                "output_tokens": 800,
                "total_tokens": 2300
            }
        )
        
        assert metadata.token_usage["input_tokens"] == 1500
        assert metadata.token_usage["output_tokens"] == 800
        assert metadata.token_usage["total_tokens"] == 2300

    @pytest.mark.parametrize(
        "agent_name,provider,strategy",
        [
            ("KubernetesAgent", "openai", "react"),
            ("KubernetesAgent-1", "anthropic", "react-stage"),
            ("KubernetesAgent-2", "gemini", "native-thinking"),
            ("VMAgent", "xai", "react"),
            ("ConfigurableAgent:custom", "openai", "react-stage"),
        ],
    )
    def test_agent_execution_metadata_various_configs(
        self, agent_name: str, provider: str, strategy: str
    ) -> None:
        """Test agent execution metadata with various agent configurations."""
        metadata = AgentExecutionMetadata(
            agent_name=agent_name,
            llm_provider=provider,
            iteration_strategy=strategy,
            started_at_us=now_us(),
            completed_at_us=now_us() + 1_000_000,
            status=StageStatus.COMPLETED
        )
        
        assert metadata.agent_name == agent_name
        assert metadata.llm_provider == provider
        assert metadata.iteration_strategy == strategy


@pytest.mark.unit
class TestParallelStageMetadata:
    """Test cases for ParallelStageMetadata model."""

    def test_valid_parallel_stage_metadata(self) -> None:
        """Test creating valid parallel stage metadata."""
        start_time = now_us()
        end_time = start_time + 10_000_000
        
        agent_metas = [
            AgentExecutionMetadata(
                agent_name="Agent1",
                llm_provider="openai",
                iteration_strategy="react",
                started_at_us=start_time,
                completed_at_us=start_time + 5_000_000,
                status=StageStatus.COMPLETED
            ),
            AgentExecutionMetadata(
                agent_name="Agent2",
                llm_provider="anthropic",
                iteration_strategy="react-stage",
                started_at_us=start_time,
                completed_at_us=start_time + 7_000_000,
                status=StageStatus.COMPLETED
            )
        ]
        
        metadata = ParallelStageMetadata(
            parent_stage_execution_id="exec-123",
            parallel_type="multi_agent",
            failure_policy=FailurePolicy.ALL,
            started_at_us=start_time,
            completed_at_us=end_time,
            agent_metadatas=agent_metas
        )
        
        assert metadata.parent_stage_execution_id == "exec-123"
        assert metadata.parallel_type == "multi_agent"
        assert metadata.failure_policy == FailurePolicy.ALL
        assert len(metadata.agent_metadatas) == 2

    def test_parallel_stage_metadata_duration_calculation(self) -> None:
        """Test duration_ms property calculation."""
        start_time = now_us()
        end_time = start_time + 12_500_000
        
        metadata = ParallelStageMetadata(
            parent_stage_execution_id="exec-456",
            parallel_type="replica",
            failure_policy=FailurePolicy.ANY,
            started_at_us=start_time,
            completed_at_us=end_time,
            agent_metadatas=[]
        )
        
        assert metadata.duration_ms == 12500

    def test_parallel_stage_metadata_count_properties(self) -> None:
        """Test successful_count, failed_count, and total_count properties."""
        agent_metas = [
            AgentExecutionMetadata(
                agent_name="Agent1",
                llm_provider="openai",
                iteration_strategy="react",
                started_at_us=now_us(),
                completed_at_us=now_us() + 1_000_000,
                status=StageStatus.COMPLETED
            ),
            AgentExecutionMetadata(
                agent_name="Agent2",
                llm_provider="anthropic",
                iteration_strategy="react",
                started_at_us=now_us(),
                completed_at_us=now_us() + 1_000_000,
                status=StageStatus.COMPLETED
            ),
            AgentExecutionMetadata(
                agent_name="Agent3",
                llm_provider="gemini",
                iteration_strategy="react",
                started_at_us=now_us(),
                completed_at_us=now_us() + 1_000_000,
                status=StageStatus.FAILED,
                error_message="Timeout"
            )
        ]
        
        metadata = ParallelStageMetadata(
            parent_stage_execution_id="exec-789",
            parallel_type="multi_agent",
            failure_policy=FailurePolicy.ANY,
            started_at_us=now_us(),
            completed_at_us=now_us() + 5_000_000,
            agent_metadatas=agent_metas
        )
        
        assert metadata.total_count == 3
        assert metadata.successful_count == 2
        assert metadata.failed_count == 1

    @pytest.mark.parametrize(
        "parallel_type,failure_policy",
        [
            ("multi_agent", FailurePolicy.ALL),
            ("multi_agent", FailurePolicy.ANY),
            ("replica", FailurePolicy.ALL),
            ("replica", FailurePolicy.ANY),
        ],
    )
    def test_parallel_stage_metadata_type_combinations(
        self, parallel_type: str, failure_policy: FailurePolicy
    ) -> None:
        """Test parallel stage metadata with different type and policy combinations."""
        metadata = ParallelStageMetadata(
            parent_stage_execution_id="exec-combo",
            parallel_type=parallel_type,
            failure_policy=failure_policy,
            started_at_us=now_us(),
            completed_at_us=now_us() + 5_000_000,
            agent_metadatas=[]
        )
        
        assert metadata.parallel_type == parallel_type
        assert metadata.failure_policy == failure_policy


@pytest.mark.unit
class TestParallelStageResult:
    """Test cases for ParallelStageResult model."""

    def test_valid_parallel_stage_result(self) -> None:
        """Test creating valid parallel stage result."""
        timestamp = now_us()
        
        results = [
            AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="Agent1",
                timestamp_us=timestamp,
                result_summary="Agent1 completed successfully"
            ),
            AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="Agent2",
                timestamp_us=timestamp,
                result_summary="Agent2 completed successfully"
            )
        ]
        
        metadata = ParallelStageMetadata(
            parent_stage_execution_id="exec-result-1",
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
        
        assert len(parallel_result.results) == 2
        assert parallel_result.status == StageStatus.COMPLETED
        assert parallel_result.timestamp_us == timestamp
        assert parallel_result.metadata.parallel_type == "multi_agent"

    def test_parallel_stage_result_with_partial_success(self) -> None:
        """Test parallel stage result with partial success (ANY policy)."""
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
            parent_stage_execution_id="exec-partial",
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

    def test_parallel_stage_result_with_replicas(self) -> None:
        """Test parallel stage result with replica parallelism."""
        timestamp = now_us()
        
        results = [
            AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="KubernetesAgent-1",
                timestamp_us=timestamp,
                result_summary="Replica 1"
            ),
            AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="KubernetesAgent-2",
                timestamp_us=timestamp,
                result_summary="Replica 2"
            ),
            AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="KubernetesAgent-3",
                timestamp_us=timestamp,
                result_summary="Replica 3"
            )
        ]
        
        metadata = ParallelStageMetadata(
            parent_stage_execution_id="exec-replicas",
            parallel_type="replica",
            failure_policy=FailurePolicy.ALL,
            started_at_us=timestamp - 10_000_000,
            completed_at_us=timestamp,
            agent_metadatas=[
                AgentExecutionMetadata(
                    agent_name=f"KubernetesAgent-{i}",
                    llm_provider="openai",
                    iteration_strategy="react",
                    started_at_us=timestamp - 10_000_000,
                    completed_at_us=timestamp,
                    status=StageStatus.COMPLETED
                )
                for i in range(1, 4)
            ]
        )
        
        parallel_result = ParallelStageResult(
            results=results,
            metadata=metadata,
            status=StageStatus.COMPLETED,
            timestamp_us=timestamp
        )
        
        assert len(parallel_result.results) == 3
        assert parallel_result.metadata.parallel_type == "replica"
        assert metadata.successful_count == 3
        assert metadata.failed_count == 0

    def test_parallel_stage_result_all_failures(self) -> None:
        """Test parallel stage result with all agents failing."""
        timestamp = now_us()
        
        results = [
            AgentExecutionResult(
                status=StageStatus.FAILED,
                agent_name="Agent1",
                timestamp_us=timestamp,
                result_summary="",
                error_message="Error 1"
            ),
            AgentExecutionResult(
                status=StageStatus.FAILED,
                agent_name="Agent2",
                timestamp_us=timestamp,
                result_summary="",
                error_message="Error 2"
            )
        ]
        
        metadata = ParallelStageMetadata(
            parent_stage_execution_id="exec-all-fail",
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
                    status=StageStatus.FAILED,
                    error_message="Error 1"
                ),
                AgentExecutionMetadata(
                    agent_name="Agent2",
                    llm_provider="anthropic",
                    iteration_strategy="react",
                    started_at_us=timestamp - 5_000_000,
                    completed_at_us=timestamp,
                    status=StageStatus.FAILED,
                    error_message="Error 2"
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
        assert metadata.successful_count == 0
        assert metadata.failed_count == 2

    def test_parallel_stage_result_with_token_usage(self) -> None:
        """Test parallel stage result with token usage in metadata."""
        timestamp = now_us()
        
        results = [
            AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="Agent1",
                timestamp_us=timestamp,
                result_summary="Success"
            )
        ]
        
        metadata = ParallelStageMetadata(
            parent_stage_execution_id="exec-tokens",
            parallel_type="replica",
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
                    status=StageStatus.COMPLETED,
                    token_usage={
                        "input_tokens": 2000,
                        "output_tokens": 1500,
                        "total_tokens": 3500
                    }
                )
            ]
        )
        
        parallel_result = ParallelStageResult(
            results=results,
            metadata=metadata,
            status=StageStatus.COMPLETED,
            timestamp_us=timestamp
        )
        
        assert parallel_result.metadata.agent_metadatas[0].token_usage["total_tokens"] == 3500

