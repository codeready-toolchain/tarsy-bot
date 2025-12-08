"""Unit tests for ChainContext helpers for parallel stages."""

import pytest

from tarsy.models.agent_execution_result import (
    AgentExecutionMetadata,
    AgentExecutionResult,
    ParallelStageMetadata,
    ParallelStageResult,
)
from tarsy.models.alert import ProcessingAlert
from tarsy.models.constants import FailurePolicy, StageStatus
from tarsy.models.processing_context import ChainContext
from tarsy.utils.timestamp import now_us


@pytest.mark.unit
class TestChainContextParallelHelpers:
    """Test ChainContext helper methods for parallel stages."""

    @pytest.fixture
    def base_chain_context(self) -> ChainContext:
        """Create a base ChainContext for testing."""
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            runbook_url=None,
            alert_data={"pod": "test-pod", "namespace": "default"}
        )
        return ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="test-stage"
        )

    @pytest.fixture
    def sample_single_agent_result(self) -> AgentExecutionResult:
        """Create a sample single agent execution result."""
        return AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="KubernetesAgent",
            timestamp_us=now_us(),
            result_summary="Single agent completed successfully"
        )

    @pytest.fixture
    def sample_parallel_stage_result(self) -> ParallelStageResult:
        """Create a sample parallel stage result."""
        timestamp = now_us()
        
        results = [
            AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="Agent1",
                timestamp_us=timestamp,
                result_summary="Agent1 result"
            ),
            AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="Agent2",
                timestamp_us=timestamp,
                result_summary="Agent2 result"
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
        
        return ParallelStageResult(
            results=results,
            metadata=metadata,
            status=StageStatus.COMPLETED,
            timestamp_us=timestamp
        )

    def test_get_previous_stage_results_empty(self, base_chain_context: ChainContext) -> None:
        """Test get_previous_stage_results with no previous stages."""
        results = base_chain_context.get_previous_stage_results()
        assert results == []

    def test_get_previous_stage_results_with_single_agent(
        self, base_chain_context: ChainContext, sample_single_agent_result: AgentExecutionResult
    ) -> None:
        """Test get_previous_stage_results with single agent result."""
        base_chain_context.add_stage_result("stage1", sample_single_agent_result)
        
        results = base_chain_context.get_previous_stage_results()
        
        assert len(results) == 1
        assert results[0][0] == "stage1"
        assert isinstance(results[0][1], AgentExecutionResult)
        assert results[0][1].agent_name == "KubernetesAgent"

    def test_get_previous_stage_results_with_parallel_stage(
        self, base_chain_context: ChainContext, sample_parallel_stage_result: ParallelStageResult
    ) -> None:
        """Test get_previous_stage_results with parallel stage result."""
        base_chain_context.add_stage_result("parallel-stage", sample_parallel_stage_result)
        
        results = base_chain_context.get_previous_stage_results()
        
        assert len(results) == 1
        assert results[0][0] == "parallel-stage"
        assert isinstance(results[0][1], ParallelStageResult)
        assert len(results[0][1].results) == 2

    def test_get_previous_stage_results_mixed_stages(
        self,
        base_chain_context: ChainContext,
        sample_single_agent_result: AgentExecutionResult,
        sample_parallel_stage_result: ParallelStageResult
    ) -> None:
        """Test get_previous_stage_results with both single and parallel stages."""
        base_chain_context.add_stage_result("stage1", sample_single_agent_result)
        base_chain_context.add_stage_result("parallel-stage", sample_parallel_stage_result)
        
        results = base_chain_context.get_previous_stage_results()
        
        assert len(results) == 2
        assert results[0][0] == "stage1"
        assert isinstance(results[0][1], AgentExecutionResult)
        assert results[1][0] == "parallel-stage"
        assert isinstance(results[1][1], ParallelStageResult)

    def test_get_previous_stages_results_alias(self, base_chain_context: ChainContext) -> None:
        """Test that get_previous_stages_results is an alias for get_previous_stage_results."""
        results1 = base_chain_context.get_previous_stage_results()
        results2 = base_chain_context.get_previous_stages_results()
        
        assert results1 == results2

    def test_is_parallel_stage_returns_false_for_nonexistent(self, base_chain_context: ChainContext) -> None:
        """Test is_parallel_stage returns False for nonexistent stage."""
        assert base_chain_context.is_parallel_stage("nonexistent") is False

    def test_is_parallel_stage_returns_false_for_single_agent(
        self, base_chain_context: ChainContext, sample_single_agent_result: AgentExecutionResult
    ) -> None:
        """Test is_parallel_stage returns False for single agent stage."""
        base_chain_context.add_stage_result("single-stage", sample_single_agent_result)
        
        assert base_chain_context.is_parallel_stage("single-stage") is False

    def test_is_parallel_stage_returns_true_for_parallel_stage(
        self, base_chain_context: ChainContext, sample_parallel_stage_result: ParallelStageResult
    ) -> None:
        """Test is_parallel_stage returns True for parallel stage."""
        base_chain_context.add_stage_result("parallel-stage", sample_parallel_stage_result)
        
        assert base_chain_context.is_parallel_stage("parallel-stage") is True

    def test_get_last_stage_result_with_no_stages(self, base_chain_context: ChainContext) -> None:
        """Test get_last_stage_result returns None when no stages completed."""
        result = base_chain_context.get_last_stage_result()
        assert result is None

    def test_get_last_stage_result_with_single_stage(
        self, base_chain_context: ChainContext, sample_single_agent_result: AgentExecutionResult
    ) -> None:
        """Test get_last_stage_result returns the only stage result."""
        base_chain_context.add_stage_result("stage1", sample_single_agent_result)
        
        result = base_chain_context.get_last_stage_result()
        
        assert result is not None
        assert isinstance(result, AgentExecutionResult)
        assert result.agent_name == "KubernetesAgent"

    def test_get_last_stage_result_with_multiple_stages(
        self,
        base_chain_context: ChainContext,
        sample_single_agent_result: AgentExecutionResult,
        sample_parallel_stage_result: ParallelStageResult
    ) -> None:
        """Test get_last_stage_result returns the most recent stage result."""
        base_chain_context.add_stage_result("stage1", sample_single_agent_result)
        base_chain_context.add_stage_result("stage2", sample_parallel_stage_result)
        
        result = base_chain_context.get_last_stage_result()
        
        assert result is not None
        assert isinstance(result, ParallelStageResult)
        assert result.metadata.parallel_type == "multi_agent"

    def test_get_last_stage_result_insertion_order_preserved(
        self, base_chain_context: ChainContext
    ) -> None:
        """Test that get_last_stage_result respects insertion order."""
        results_by_timestamp = []
        
        for i in range(3):
            result = AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name=f"Agent{i}",
                timestamp_us=now_us() + i * 1000,
                result_summary=f"Result {i}"
            )
            stage_name = f"stage{i}"
            base_chain_context.add_stage_result(stage_name, result)
            results_by_timestamp.append((stage_name, result))
        
        last_result = base_chain_context.get_last_stage_result()
        
        assert last_result is not None
        assert last_result.agent_name == "Agent2"

    def test_add_stage_result_single_agent(
        self, base_chain_context: ChainContext, sample_single_agent_result: AgentExecutionResult
    ) -> None:
        """Test adding a single agent execution result."""
        base_chain_context.add_stage_result("analysis", sample_single_agent_result)
        
        assert "analysis" in base_chain_context.stage_outputs
        assert isinstance(base_chain_context.stage_outputs["analysis"], AgentExecutionResult)

    def test_add_stage_result_parallel_stage(
        self, base_chain_context: ChainContext, sample_parallel_stage_result: ParallelStageResult
    ) -> None:
        """Test adding a parallel stage result."""
        base_chain_context.add_stage_result("investigation", sample_parallel_stage_result)
        
        assert "investigation" in base_chain_context.stage_outputs
        assert isinstance(base_chain_context.stage_outputs["investigation"], ParallelStageResult)

    def test_stage_outputs_type_union(
        self,
        base_chain_context: ChainContext,
        sample_single_agent_result: AgentExecutionResult,
        sample_parallel_stage_result: ParallelStageResult
    ) -> None:
        """Test that stage_outputs can hold both AgentExecutionResult and ParallelStageResult."""
        base_chain_context.add_stage_result("single", sample_single_agent_result)
        base_chain_context.add_stage_result("parallel", sample_parallel_stage_result)
        
        assert len(base_chain_context.stage_outputs) == 2
        assert isinstance(base_chain_context.stage_outputs["single"], AgentExecutionResult)
        assert isinstance(base_chain_context.stage_outputs["parallel"], ParallelStageResult)

    def test_get_previous_stage_results_excludes_failed_stages(
        self, base_chain_context: ChainContext
    ) -> None:
        """Test that get_previous_stage_results only includes completed stages."""
        completed_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="CompletedAgent",
            timestamp_us=now_us(),
            result_summary="Completed"
        )
        
        failed_result = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="FailedAgent",
            timestamp_us=now_us(),
            result_summary="",
            error_message="Failed"
        )
        
        base_chain_context.add_stage_result("completed-stage", completed_result)
        base_chain_context.add_stage_result("failed-stage", failed_result)
        
        results = base_chain_context.get_previous_stage_results()
        
        assert len(results) == 1
        assert results[0][0] == "completed-stage"

    def test_get_previous_stage_results_parallel_with_partial_failure(
        self, base_chain_context: ChainContext
    ) -> None:
        """Test get_previous_stage_results with parallel stage that has partial success."""
        timestamp = now_us()
        
        parallel_result = ParallelStageResult(
            results=[
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
            ],
            metadata=ParallelStageMetadata(
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
            ),
            status=StageStatus.COMPLETED,
            timestamp_us=timestamp
        )
        
        base_chain_context.add_stage_result("partial-parallel", parallel_result)
        
        results = base_chain_context.get_previous_stage_results()
        
        assert len(results) == 1
        assert results[0][0] == "partial-parallel"
        assert results[0][1].status == StageStatus.COMPLETED

