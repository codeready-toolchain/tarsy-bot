"""
Unit tests for AlertService._aggregate_stage_errors method.

Tests the error aggregation logic for both regular and parallel stage failures.
"""

import pytest

from tarsy.models.agent_execution_result import (
    AgentExecutionResult,
    AgentExecutionMetadata,
    ParallelStageMetadata,
    ParallelStageResult,
)
from tarsy.models.constants import StageStatus
from tarsy.models.processing_context import ChainContext
from tarsy.services.alert_service import AlertService
from tarsy.utils.timestamp import now_us


@pytest.fixture
def alert_service():
    """Create a minimal AlertService for testing error aggregation."""
    # We only need the _aggregate_stage_errors method, which is a pure function
    # that doesn't require any dependencies
    from unittest.mock import Mock
    service = Mock(spec=AlertService)
    # Bind the actual method to our mock instance
    service._aggregate_stage_errors = AlertService._aggregate_stage_errors.__get__(service, AlertService)
    return service


@pytest.fixture
def chain_context():
    """Create a minimal ChainContext for testing."""
    from tarsy.models.alert import ProcessingAlert
    
    processing_alert = ProcessingAlert(
        alert_type="test",
        timestamp=now_us(),
        alert_data={"test": "data"}
    )
    return ChainContext(
        processing_alert=processing_alert,
        session_id="test-session-123",
        current_stage_name="test-stage"
    )


@pytest.mark.unit
class TestAgentExecutionResultErrorAggregation:
    """Tests for regular AgentExecutionResult error aggregation."""
    
    def test_single_failed_stage_with_error_message(self, alert_service, chain_context):
        """Test aggregation with a single failed stage that has an error message."""
        # Create a failed agent result
        failed_result = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="TestAgent",
            stage_name="test-stage",
            timestamp_us=now_us(),
            result_summary="Test failed",
            error_message="Connection timeout after 30 seconds"
        )
        
        # Add to chain context
        chain_context.add_stage_result("stage-exec-1", failed_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify error message contains stage info and error details
        assert "Chain processing failed" in error_msg
        assert "test-stage" in error_msg
        assert "TestAgent" in error_msg
        assert "Connection timeout after 30 seconds" in error_msg
    
    def test_single_failed_stage_without_error_message(self, alert_service, chain_context):
        """Test aggregation with a single failed stage that has no error message."""
        # Create a failed agent result without error_message
        failed_result = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="TestAgent",
            stage_name="test-stage",
            timestamp_us=now_us(),
            result_summary="Test failed",
            error_message=None
        )
        
        # Add to chain context
        chain_context.add_stage_result("stage-exec-1", failed_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify error message contains fallback text
        assert "Chain processing failed" in error_msg
        assert "test-stage" in error_msg
        assert "TestAgent" in error_msg
        assert "Failed with no error message" in error_msg
    
    def test_multiple_failed_stages(self, alert_service, chain_context):
        """Test aggregation with multiple failed stages."""
        # Create multiple failed results
        failed_result_1 = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="Agent1",
            stage_name="stage-1",
            timestamp_us=now_us(),
            result_summary="Test failed",
            error_message="Error in stage 1"
        )
        
        failed_result_2 = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="Agent2",
            stage_name="stage-2",
            timestamp_us=now_us(),
            result_summary="Test failed",
            error_message="Error in stage 2"
        )
        
        # Add to chain context
        chain_context.add_stage_result("stage-exec-1", failed_result_1)
        chain_context.add_stage_result("stage-exec-2", failed_result_2)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify both errors are included
        assert "2 stage failures" in error_msg
        assert "stage-1" in error_msg
        assert "Agent1" in error_msg
        assert "Error in stage 1" in error_msg
        assert "stage-2" in error_msg
        assert "Agent2" in error_msg
        assert "Error in stage 2" in error_msg


@pytest.mark.unit
class TestParallelStageResultErrorAggregation:
    """Tests for ParallelStageResult error aggregation."""
    
    def test_parallel_stage_single_failed_agent(self, alert_service, chain_context):
        """Test aggregation with a parallel stage where one agent failed."""
        # Create a failed agent result
        failed_agent_result = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="KubernetesAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="LLM request failed",
            error_message="Anthropic API error: rate limit exceeded"
        )
        
        # Create parallel stage result
        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[failed_agent_result],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="parent-exec-1",
                parallel_type="multi_agent",
                success_policy="any",
                started_at_us=now_us(),
                completed_at_us=now_us(),
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="KubernetesAgent",
                        llm_provider="anthropic",
                        iteration_strategy="react",
                        started_at_us=now_us(),
                        completed_at_us=now_us(),
                        status=StageStatus.FAILED,
                        error_message="Anthropic API error: rate limit exceeded",
                        token_usage=None
                    )
                ]
            ),
            status=StageStatus.FAILED,
            timestamp_us=now_us()
        )
        
        # Add to chain context
        chain_context.add_stage_result("parent-exec-1", parallel_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify error message contains parallel stage info and agent error
        assert "Chain processing failed" in error_msg
        assert "Parallel stage 'investigation' failed" in error_msg
        assert "KubernetesAgent" in error_msg
        assert "Anthropic API error: rate limit exceeded" in error_msg
    
    def test_parallel_stage_multiple_failed_agents(self, alert_service, chain_context):
        """Test aggregation with a parallel stage where multiple agents failed."""
        # Create multiple failed agent results
        failed_agent_1 = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="KubernetesAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="LLM request failed",
            error_message="Gemini API error: 503 Service Unavailable"
        )
        
        failed_agent_2 = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="LogAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="LLM request failed",
            error_message="OpenAI API error: Connection timeout"
        )
        
        # Create parallel stage result
        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[failed_agent_1, failed_agent_2],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="parent-exec-1",
                parallel_type="multi_agent",
                success_policy="all",
                started_at_us=now_us(),
                completed_at_us=now_us(),
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="KubernetesAgent",
                        llm_provider="gemini",
                        iteration_strategy="native-thinking",
                        started_at_us=now_us(),
                        completed_at_us=now_us(),
                        status=StageStatus.FAILED,
                        error_message="Gemini API error: 503 Service Unavailable",
                        token_usage=None
                    ),
                    AgentExecutionMetadata(
                        agent_name="LogAgent",
                        llm_provider="openai",
                        iteration_strategy="react",
                        started_at_us=now_us(),
                        completed_at_us=now_us(),
                        status=StageStatus.FAILED,
                        error_message="OpenAI API error: Connection timeout",
                        token_usage=None
                    )
                ]
            ),
            status=StageStatus.FAILED,
            timestamp_us=now_us()
        )
        
        # Add to chain context
        chain_context.add_stage_result("parent-exec-1", parallel_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify error message contains all agent errors
        assert "Chain processing failed" in error_msg
        assert "Parallel stage 'investigation' failed" in error_msg
        assert "2 agents" in error_msg
        assert "KubernetesAgent" in error_msg
        assert "Gemini API error: 503 Service Unavailable" in error_msg
        assert "LogAgent" in error_msg
        assert "OpenAI API error: Connection timeout" in error_msg
    
    def test_parallel_stage_with_mixed_status(self, alert_service, chain_context):
        """Test aggregation with a parallel stage where some agents failed and some succeeded."""
        # Create mixed results
        failed_agent = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="KubernetesAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="LLM request failed",
            error_message="LLM request failed - no response received"
        )
        
        successful_agent = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="LogAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="Analysis completed",
            error_message=None
        )
        
        # Create parallel stage result (overall status is FAILED due to success_policy)
        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[failed_agent, successful_agent],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="parent-exec-1",
                parallel_type="multi_agent",
                success_policy="all",
                started_at_us=now_us(),
                completed_at_us=now_us(),
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="KubernetesAgent",
                        llm_provider="gemini",
                        iteration_strategy="native-thinking",
                        started_at_us=now_us(),
                        completed_at_us=now_us(),
                        status=StageStatus.FAILED,
                        error_message="LLM request failed - no response received",
                        token_usage=None
                    ),
                    AgentExecutionMetadata(
                        agent_name="LogAgent",
                        llm_provider="openai",
                        iteration_strategy="react",
                        started_at_us=now_us(),
                        completed_at_us=now_us(),
                        status=StageStatus.COMPLETED,
                        error_message=None,
                        token_usage={"input_tokens": 100, "output_tokens": 200, "total_tokens": 300}
                    )
                ]
            ),
            status=StageStatus.FAILED,
            timestamp_us=now_us()
        )
        
        # Add to chain context
        chain_context.add_stage_result("parent-exec-1", parallel_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify error message only includes failed agents
        assert "Chain processing failed" in error_msg
        assert "Parallel stage 'investigation' failed" in error_msg
        assert "KubernetesAgent" in error_msg
        assert "LLM request failed - no response received" in error_msg
        # Successful agent should not be in error message
        assert "LogAgent" not in error_msg or "LogAgent:" not in error_msg
    
    def test_parallel_stage_without_error_messages(self, alert_service, chain_context):
        """Test aggregation with a parallel stage where agents failed without error messages."""
        # Create a failed agent result without error message
        failed_agent = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="TestAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="Failed",
            error_message=None
        )
        
        # Create parallel stage result
        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[failed_agent],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="parent-exec-1",
                parallel_type="replica",
                success_policy="any",
                started_at_us=now_us(),
                completed_at_us=now_us(),
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="TestAgent",
                        llm_provider="openai",
                        iteration_strategy="react",
                        started_at_us=now_us(),
                        completed_at_us=now_us(),
                        status=StageStatus.FAILED,
                        error_message=None,
                        token_usage=None
                    )
                ]
            ),
            status=StageStatus.FAILED,
            timestamp_us=now_us()
        )
        
        # Add to chain context
        chain_context.add_stage_result("parent-exec-1", parallel_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify error message includes fallback for missing error message
        assert "Chain processing failed" in error_msg
        assert "Parallel stage 'investigation' failed" in error_msg
        assert "TestAgent" in error_msg
        assert "No error message" in error_msg


@pytest.mark.unit
class TestCancelledAgentErrorAggregation:
    """Tests for cancelled agent error aggregation in parallel stages."""
    
    def test_parallel_stage_with_cancelled_agent(self, alert_service, chain_context):
        """Test aggregation with a parallel stage where one agent was cancelled."""
        # Create a cancelled agent result (e.g., due to timeout or user cancellation)
        cancelled_agent = AgentExecutionResult(
            status=StageStatus.CANCELLED,
            agent_name="TimeoutAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="Agent cancelled",
            error_message="Operation timed out after 900 seconds"
        )
        
        # Create parallel stage result (overall status is FAILED because all agents cancelled)
        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[cancelled_agent],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="parent-exec-1",
                parallel_type="multi_agent",
                success_policy="any",
                started_at_us=now_us(),
                completed_at_us=now_us(),
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="TimeoutAgent",
                        llm_provider="gemini",
                        iteration_strategy="react",
                        started_at_us=now_us(),
                        completed_at_us=now_us(),
                        status=StageStatus.CANCELLED,
                        error_message="Operation timed out after 900 seconds",
                        token_usage=None
                    )
                ]
            ),
            status=StageStatus.FAILED,
            timestamp_us=now_us()
        )
        
        # Add to chain context
        chain_context.add_stage_result("parent-exec-1", parallel_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify error message includes cancelled agent with label
        assert "Chain processing failed" in error_msg
        assert "Parallel stage 'investigation' failed" in error_msg
        assert "TimeoutAgent (cancelled)" in error_msg
        assert "Operation timed out after 900 seconds" in error_msg
    
    def test_parallel_stage_with_mixed_failed_and_cancelled(self, alert_service, chain_context):
        """Test aggregation with a parallel stage with both failed and cancelled agents."""
        # Failed agent
        failed_agent = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="FailedAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="Agent failed",
            error_message="LLM API error"
        )
        
        # Cancelled agent
        cancelled_agent = AgentExecutionResult(
            status=StageStatus.CANCELLED,
            agent_name="CancelledAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="Agent cancelled",
            error_message="User cancelled the operation"
        )
        
        # Create parallel stage result (status FAILED - all agents failed/cancelled)
        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[failed_agent, cancelled_agent],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="parent-exec-1",
                parallel_type="multi_agent",
                success_policy="any",
                started_at_us=now_us(),
                completed_at_us=now_us(),
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="FailedAgent",
                        llm_provider="gemini",
                        iteration_strategy="react",
                        started_at_us=now_us(),
                        completed_at_us=now_us(),
                        status=StageStatus.FAILED,
                        error_message="LLM API error",
                        token_usage=None
                    ),
                    AgentExecutionMetadata(
                        agent_name="CancelledAgent",
                        llm_provider="openai",
                        iteration_strategy="react",
                        started_at_us=now_us(),
                        completed_at_us=now_us(),
                        status=StageStatus.CANCELLED,
                        error_message="User cancelled the operation",
                        token_usage=None
                    )
                ]
            ),
            status=StageStatus.FAILED,
            timestamp_us=now_us()
        )
        
        # Add to chain context
        chain_context.add_stage_result("parent-exec-1", parallel_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify both agents are in error message with proper labels
        assert "Chain processing failed" in error_msg
        assert "Parallel stage 'investigation' failed" in error_msg
        assert "2 agents" in error_msg
        assert "FailedAgent (failed): LLM API error" in error_msg
        assert "CancelledAgent (cancelled): User cancelled the operation" in error_msg


@pytest.mark.unit
class TestTimedOutStageErrorAggregation:
    """Tests for timed out stage error aggregation."""
    
    def test_single_timed_out_stage(self, alert_service, chain_context):
        """Test aggregation with a single timed out stage."""
        # Create a timed out agent result
        timed_out_result = AgentExecutionResult(
            status=StageStatus.TIMED_OUT,
            agent_name="SlowAgent",
            stage_name="analysis",
            timestamp_us=now_us(),
            result_summary="Operation timed out",
            error_message="Agent processing timed out after 300 seconds"
        )
        
        # Add to chain context
        chain_context.add_stage_result("stage-exec-1", timed_out_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify error message includes timed out stage
        assert "Chain processing failed" in error_msg
        assert "analysis" in error_msg
        assert "SlowAgent" in error_msg
        assert "Agent processing timed out after 300 seconds" in error_msg
    
    def test_parallel_stage_timed_out_status(self, alert_service, chain_context):
        """Test aggregation with a parallel stage that has TIMED_OUT status."""
        # Create a timed out agent result
        timed_out_agent = AgentExecutionResult(
            status=StageStatus.TIMED_OUT,
            agent_name="NativeThinkingAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="Agent timed out",
            error_message="Native thinking timed out after 180 seconds"
        )
        
        # Create parallel stage result with TIMED_OUT status (all agents timed out)
        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[timed_out_agent],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="parent-exec-1",
                parallel_type="replica",
                success_policy="any",
                started_at_us=now_us(),
                completed_at_us=now_us(),
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="NativeThinkingAgent",
                        llm_provider="gemini",
                        iteration_strategy="native-thinking",
                        started_at_us=now_us(),
                        completed_at_us=now_us(),
                        status=StageStatus.TIMED_OUT,
                        error_message="Native thinking timed out after 180 seconds",
                        token_usage=None
                    )
                ]
            ),
            status=StageStatus.TIMED_OUT,
            timestamp_us=now_us()
        )
        
        # Add to chain context
        chain_context.add_stage_result("parent-exec-1", parallel_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify error message includes timed out agent with label
        assert "Chain processing failed" in error_msg
        assert "Parallel stage 'investigation' failed" in error_msg
        assert "NativeThinkingAgent (timed_out)" in error_msg
        assert "Native thinking timed out after 180 seconds" in error_msg


@pytest.mark.unit
class TestCancelledStageErrorAggregation:
    """Tests for cancelled stage error aggregation."""
    
    def test_single_cancelled_stage(self, alert_service, chain_context):
        """Test aggregation with a single cancelled stage."""
        # Create a cancelled agent result
        cancelled_result = AgentExecutionResult(
            status=StageStatus.CANCELLED,
            agent_name="UserCancelledAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="User cancelled",
            error_message="User cancelled the operation"
        )
        
        # Add to chain context
        chain_context.add_stage_result("stage-exec-1", cancelled_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify error message includes cancelled stage
        assert "Chain processing failed" in error_msg
        assert "investigation" in error_msg
        assert "UserCancelledAgent" in error_msg
        assert "User cancelled the operation" in error_msg
    
    def test_parallel_stage_cancelled_status(self, alert_service, chain_context):
        """Test aggregation with a parallel stage that has CANCELLED status."""
        # Create cancelled agent results
        cancelled_agent_1 = AgentExecutionResult(
            status=StageStatus.CANCELLED,
            agent_name="KubernetesAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="Agent cancelled",
            error_message="User requested cancellation"
        )
        
        cancelled_agent_2 = AgentExecutionResult(
            status=StageStatus.CANCELLED,
            agent_name="LogAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="Agent cancelled",
            error_message="User requested cancellation"
        )
        
        # Create parallel stage result with CANCELLED status (all agents cancelled)
        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[cancelled_agent_1, cancelled_agent_2],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="parent-exec-1",
                parallel_type="multi_agent",
                success_policy="any",
                started_at_us=now_us(),
                completed_at_us=now_us(),
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="KubernetesAgent",
                        llm_provider="gemini",
                        iteration_strategy="react",
                        started_at_us=now_us(),
                        completed_at_us=now_us(),
                        status=StageStatus.CANCELLED,
                        error_message="User requested cancellation",
                        token_usage=None
                    ),
                    AgentExecutionMetadata(
                        agent_name="LogAgent",
                        llm_provider="openai",
                        iteration_strategy="react",
                        started_at_us=now_us(),
                        completed_at_us=now_us(),
                        status=StageStatus.CANCELLED,
                        error_message="User requested cancellation",
                        token_usage=None
                    )
                ]
            ),
            status=StageStatus.CANCELLED,
            timestamp_us=now_us()
        )
        
        # Add to chain context
        chain_context.add_stage_result("parent-exec-1", parallel_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify error message includes both cancelled agents with labels
        assert "Chain processing failed" in error_msg
        assert "Parallel stage 'investigation' failed" in error_msg
        assert "2 agents" in error_msg
        assert "KubernetesAgent (cancelled)" in error_msg
        assert "LogAgent (cancelled)" in error_msg
        assert "User requested cancellation" in error_msg


@pytest.mark.unit
class TestMixedErrorAggregation:
    """Tests for mixed regular and parallel stage error aggregation."""
    
    def test_regular_and_parallel_stage_failures(self, alert_service, chain_context):
        """Test aggregation with both regular and parallel stage failures."""
        # Create a regular failed stage
        regular_failed = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="PreprocessAgent",
            stage_name="preprocessing",
            timestamp_us=now_us(),
            result_summary="Preprocessing failed",
            error_message="Invalid alert format"
        )
        
        # Create a parallel stage with failed agent
        parallel_failed_agent = AgentExecutionResult(
            status=StageStatus.FAILED,
            agent_name="KubernetesAgent",
            stage_name="investigation",
            timestamp_us=now_us(),
            result_summary="Investigation failed",
            error_message="MCP server connection failed"
        )
        
        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[parallel_failed_agent],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="parent-exec-2",
                parallel_type="multi_agent",
                success_policy="any",
                started_at_us=now_us(),
                completed_at_us=now_us(),
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="KubernetesAgent",
                        llm_provider="gemini",
                        iteration_strategy="native-thinking",
                        started_at_us=now_us(),
                        completed_at_us=now_us(),
                        status=StageStatus.FAILED,
                        error_message="MCP server connection failed",
                        token_usage=None
                    )
                ]
            ),
            status=StageStatus.FAILED,
            timestamp_us=now_us()
        )
        
        # Add both to chain context
        chain_context.add_stage_result("stage-exec-1", regular_failed)
        chain_context.add_stage_result("parent-exec-2", parallel_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify both errors are included with proper formatting
        assert "2 stage failures" in error_msg
        assert "preprocessing" in error_msg
        assert "PreprocessAgent" in error_msg
        assert "Invalid alert format" in error_msg
        assert "Parallel stage 'investigation' failed" in error_msg
        assert "KubernetesAgent" in error_msg
        assert "MCP server connection failed" in error_msg
    
    def test_no_failed_stages(self, alert_service, chain_context):
        """Test aggregation when there are no failed stages."""
        # Create a successful stage
        successful_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="TestAgent",
            stage_name="test-stage",
            timestamp_us=now_us(),
            result_summary="Test completed",
            error_message=None
        )
        
        # Add to chain context
        chain_context.add_stage_result("stage-exec-1", successful_result)
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify fallback message is returned
        assert "Chain processing failed: One or more stages failed without detailed error messages" == error_msg
    
    def test_empty_chain_context(self, alert_service, chain_context):
        """Test aggregation when chain context has no stage outputs."""
        # Don't add any stage results
        
        # Aggregate errors
        error_msg = alert_service._aggregate_stage_errors(chain_context)
        
        # Verify fallback message is returned
        assert "Chain processing failed: One or more stages failed without detailed error messages" == error_msg
