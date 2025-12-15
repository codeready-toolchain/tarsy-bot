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
            stage_name="stage1",  # Required for get_previous_stages_results()
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
            stage_name="investigation",
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
        base_chain_context.add_stage_result("parallel-stage-exec-id", sample_parallel_stage_result)
        
        results = base_chain_context.get_previous_stage_results()
        
        assert len(results) == 1
        assert results[0][0] == "investigation"  # Extracted from result.stage_name
        assert isinstance(results[0][1], ParallelStageResult)
        assert len(results[0][1].results) == 2

    def test_get_previous_stage_results_mixed_stages(
        self,
        base_chain_context: ChainContext,
        sample_single_agent_result: AgentExecutionResult,
        sample_parallel_stage_result: ParallelStageResult
    ) -> None:
        """Test get_previous_stage_results with both single and parallel stages."""
        base_chain_context.add_stage_result("stage1-exec-id", sample_single_agent_result)
        base_chain_context.add_stage_result("parallel-stage-exec-id", sample_parallel_stage_result)
        
        results = base_chain_context.get_previous_stage_results()
        
        assert len(results) == 2
        assert results[0][0] == "stage1"  # Extracted from result.stage_name
        assert isinstance(results[0][1], AgentExecutionResult)
        assert results[1][0] == "investigation"  # Extracted from result.stage_name
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
        base_chain_context.add_stage_result("parallel-stage-exec-id", sample_parallel_stage_result)
        
        # Check by stage_name (extracted from result), not by key
        assert base_chain_context.is_parallel_stage("investigation") is True

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
            stage_name="completed-stage",
            timestamp_us=now_us(),
            result_summary="Completed"
        )
        
        failed_result = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="FailedAgent",
            stage_name="failed-stage",
            timestamp_us=now_us(),
            result_summary="",
            error_message="Failed"
        )
        
        base_chain_context.add_stage_result("completed-stage-id", completed_result)
        base_chain_context.add_stage_result("failed-stage-id", failed_result)
        
        results = base_chain_context.get_previous_stage_results()
        
        assert len(results) == 1
        assert results[0][0] == "completed-stage"

    def test_get_previous_stage_results_parallel_with_partial_failure(
        self, base_chain_context: ChainContext
    ) -> None:
        """Test get_previous_stage_results with parallel stage that has partial success."""
        timestamp = now_us()
        
        parallel_result = ParallelStageResult(
            stage_name="parallel-stage",
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
        assert results[0][0] == "parallel-stage"  # Extracted from result.stage_name
        assert results[0][1].status == StageStatus.COMPLETED


@pytest.mark.unit
class TestChainContextFormattingParallel:
    """Test StageContext format_previous_stages_context with parallel results."""

    @pytest.fixture
    def base_chain_context(self) -> ChainContext:
        """Create a base ChainContext for testing."""
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="critical",
            timestamp=now_us(),
            environment="production",
            runbook_url=None,
            alert_data={"pod": "failing-pod", "namespace": "prod"}
        )
        return ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="command"
        )

    @pytest.fixture
    def available_tools(self):
        """Create test AvailableTools."""
        from tarsy.models.processing_context import AvailableTools
        return AvailableTools(tools=[])

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent."""
        from unittest.mock import Mock
        agent = Mock()
        agent.__class__.__name__ = "TestAgent"
        agent.mcp_servers.return_value = []
        return agent

    def test_format_previous_stages_context_empty(
        self, base_chain_context: ChainContext, available_tools, mock_agent
    ) -> None:
        """Test formatting with no previous stages."""
        from tarsy.models.processing_context import StageContext
        
        stage_context = StageContext(
            chain_context=base_chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
        
        formatted = stage_context.format_previous_stages_context()
        assert formatted == "No previous stage context available."

    def test_format_previous_stages_context_single_agent(
        self, base_chain_context: ChainContext, available_tools, mock_agent
    ) -> None:
        """Test formatting with single agent result."""
        from tarsy.models.processing_context import StageContext
        
        result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="KubernetesAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="Pod analysis complete",
            complete_conversation_history="## Analysis\nPod is failing due to memory limit"
        )
        base_chain_context.add_stage_result("investigation-exec-id", result)
        
        stage_context = StageContext(
            chain_context=base_chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
        
        formatted = stage_context.format_previous_stages_context()
        
        assert "### Results from 'investigation' stage:" in formatted
        assert "Pod is failing due to memory limit" in formatted
        assert "<!-- Analysis Result START -->" in formatted
        assert "<!-- Analysis Result END -->" in formatted

    def test_format_previous_stages_context_parallel_multi_agent(
        self, base_chain_context: ChainContext, available_tools, mock_agent
    ) -> None:
        """Test formatting with parallel multi-agent result."""
        from tarsy.models.processing_context import StageContext
        
        timestamp = now_us()
        
        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[
                AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="KubernetesAgent",
                    timestamp_us=timestamp,
                    result_summary="K8s investigation",
                    complete_conversation_history="Found pod OOMKilled"
                ),
                AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="VMAgent",
                    timestamp_us=timestamp,
                    result_summary="VM investigation",
                    complete_conversation_history="Node has high memory pressure"
                )
            ],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="exec-123",
                parallel_type="multi_agent",
                failure_policy=FailurePolicy.ALL,
                started_at_us=timestamp - 5_000_000,
                completed_at_us=timestamp,
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="KubernetesAgent",
                        llm_provider="openai",
                        iteration_strategy="react",
                        started_at_us=timestamp - 5_000_000,
                        completed_at_us=timestamp,
                        status=StageStatus.COMPLETED
                    ),
                    AgentExecutionMetadata(
                        agent_name="VMAgent",
                        llm_provider="anthropic",
                        iteration_strategy="native-thinking",
                        started_at_us=timestamp - 5_000_000,
                        completed_at_us=timestamp,
                        status=StageStatus.COMPLETED
                    )
                ]
            ),
            status=StageStatus.COMPLETED,
            timestamp_us=timestamp
        )
        
        base_chain_context.add_stage_result("investigation", parallel_result)
        
        stage_context = StageContext(
            chain_context=base_chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
        
        formatted = stage_context.format_previous_stages_context()
        
        # Check parallel stage header
        assert "### Results from parallel stage 'investigation':" in formatted
        assert "**Parallel Execution Summary**: 2/2 agents succeeded" in formatted
        
        # Check individual agent results are formatted
        assert "#### Agent 1: KubernetesAgent (openai, react)" in formatted
        assert "**Status**: completed" in formatted
        assert "Found pod OOMKilled" in formatted
        
        assert "#### Agent 2: VMAgent (anthropic, native-thinking)" in formatted
        assert "Node has high memory pressure" in formatted
        
        # Check HTML comment boundaries are present
        assert formatted.count("<!-- Analysis Result START -->") == 2
        assert formatted.count("<!-- Analysis Result END -->") == 2

    def test_format_previous_stages_context_parallel_with_failure(
        self, base_chain_context: ChainContext, available_tools, mock_agent
    ) -> None:
        """Test formatting parallel result with partial failure."""
        from tarsy.models.processing_context import StageContext
        
        timestamp = now_us()
        
        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[
                AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="Agent1",
                    timestamp_us=timestamp,
                    result_summary="Success",
                    complete_conversation_history="Agent1 analysis completed"
                ),
                AgentExecutionResult(
                    status=StageStatus.FAILED,
                    agent_name="Agent2",
                    timestamp_us=timestamp,
                    result_summary="",
                    error_message="Connection timeout"
                )
            ],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="exec-456",
                parallel_type="multi_agent",
                failure_policy=FailurePolicy.ANY,
                started_at_us=timestamp - 3_000_000,
                completed_at_us=timestamp,
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="Agent1",
                        llm_provider="openai",
                        iteration_strategy="react",
                        started_at_us=timestamp - 3_000_000,
                        completed_at_us=timestamp,
                        status=StageStatus.COMPLETED
                    ),
                    AgentExecutionMetadata(
                        agent_name="Agent2",
                        llm_provider="gemini",
                        iteration_strategy="react",
                        started_at_us=timestamp - 3_000_000,
                        completed_at_us=timestamp,
                        status=StageStatus.FAILED,
                        error_message="Connection timeout"
                    )
                ]
            ),
            status=StageStatus.COMPLETED,
            timestamp_us=timestamp
        )
        
        base_chain_context.add_stage_result("parallel-stage", parallel_result)
        
        stage_context = StageContext(
            chain_context=base_chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
        
        formatted = stage_context.format_previous_stages_context()
        
        # Check summary shows partial success
        assert "**Parallel Execution Summary**: 1/2 agents succeeded" in formatted
        
        # Check successful agent is formatted
        assert "Agent1 analysis completed" in formatted
        
        # Check failed agent shows error
        assert "**Status**: failed" in formatted
        assert "**Error**: Connection timeout" in formatted

    def test_format_previous_stages_context_mixed_stages(
        self, base_chain_context: ChainContext, available_tools, mock_agent
    ) -> None:
        """Test formatting with both single and parallel stages."""
        from tarsy.models.processing_context import StageContext
        
        timestamp = now_us()
        
        # Add single agent stage
        single_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="AnalysisAgent",
            stage_name="analysis",
            timestamp_us=timestamp,
            result_summary="Initial analysis",
            complete_conversation_history="Alert requires deeper investigation"
        )
        base_chain_context.add_stage_result("analysis-exec-id", single_result)
        
        # Add parallel stage
        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[
                AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="Agent1",
                    timestamp_us=timestamp + 1000,
                    result_summary="Deep dive 1",
                    complete_conversation_history="Found root cause in logs"
                ),
                AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="Agent2",
                    timestamp_us=timestamp + 1000,
                    result_summary="Deep dive 2",
                    complete_conversation_history="Metrics confirm the issue"
                )
            ],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="exec-789",
                parallel_type="multi_agent",
                failure_policy=FailurePolicy.ALL,
                started_at_us=timestamp,
                completed_at_us=timestamp + 1000,
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="Agent1",
                        llm_provider="openai",
                        iteration_strategy="react",
                        started_at_us=timestamp,
                        completed_at_us=timestamp + 1000,
                        status=StageStatus.COMPLETED
                    ),
                    AgentExecutionMetadata(
                        agent_name="Agent2",
                        llm_provider="anthropic",
                        iteration_strategy="react",
                        started_at_us=timestamp,
                        completed_at_us=timestamp + 1000,
                        status=StageStatus.COMPLETED
                    )
                ]
            ),
            status=StageStatus.COMPLETED,
            timestamp_us=timestamp + 1000
        )
        base_chain_context.add_stage_result("investigation", parallel_result)
        
        stage_context = StageContext(
            chain_context=base_chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
        
        formatted = stage_context.format_previous_stages_context()
        
        # Check both stages are present
        assert "### Results from 'analysis' stage:" in formatted
        assert "Alert requires deeper investigation" in formatted
        
        assert "### Results from parallel stage 'investigation':" in formatted
        assert "Found root cause in logs" in formatted
        assert "Metrics confirm the issue" in formatted

    def test_format_previous_stages_context_escapes_html_comments(
        self, base_chain_context: ChainContext, available_tools, mock_agent
    ) -> None:
        """Test that HTML comments in content are properly escaped."""
        from tarsy.models.processing_context import StageContext
        
        result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="TestAgent",
            timestamp_us=now_us(),
            result_summary="Test",
            complete_conversation_history="<!-- This is a comment --> and --> another"
        )
        base_chain_context.add_stage_result("test-stage", result)
        
        stage_context = StageContext(
            chain_context=base_chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
        
        formatted = stage_context.format_previous_stages_context()
        
        # Check that HTML comments are escaped
        assert "&lt;!--" in formatted
        assert "--&gt;" in formatted
        # Original should not be present unescaped
        assert formatted.count("<!-- This is a comment -->") == 0

    def test_format_previous_stages_context_handles_empty_content(
        self, base_chain_context: ChainContext, available_tools, mock_agent
    ) -> None:
        """Test formatting with empty result_summary and conversation_history."""
        from tarsy.models.processing_context import StageContext
        
        result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="EmptyAgent",
            stage_name="empty-stage",
            timestamp_us=now_us(),
            result_summary=""
        )
        base_chain_context.add_stage_result("empty-stage-exec-id", result)
        
        stage_context = StageContext(
            chain_context=base_chain_context,
            available_tools=available_tools,
            agent=mock_agent
        )
        
        formatted = stage_context.format_previous_stages_context()
        
        # Should still have structure even with empty content
        assert "### Results from 'empty-stage' stage:" in formatted
        assert "<!-- Analysis Result START -->" in formatted
        assert "<!-- Analysis Result END -->" in formatted

