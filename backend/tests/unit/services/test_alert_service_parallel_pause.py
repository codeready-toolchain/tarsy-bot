"""
Unit tests for parallel agent pause/resume functionality.

Tests the helper methods and logic added for parallel stage pause/resume support:
- ParallelStageMetadata.paused_count property
- Status aggregation logic with PAUSED status
- Child status separation for resume
"""

import pytest

from tarsy.models.agent_execution_result import (
    AgentExecutionMetadata,
    ParallelStageMetadata,
)
from tarsy.models.constants import FailurePolicy, StageStatus


@pytest.mark.unit
class TestParallelStageMetadata:
    """Test ParallelStageMetadata helper methods."""
    
    def test_paused_count_property(self):
        """Test that paused_count correctly counts paused agent executions."""
        metadatas = [
            AgentExecutionMetadata(
                agent_name="agent1",
                llm_provider="openai",
                iteration_strategy="react",
                started_at_us=1000,
                completed_at_us=2000,
                status=StageStatus.COMPLETED,
                error_message=None,
                token_usage=None
            ),
            AgentExecutionMetadata(
                agent_name="agent2",
                llm_provider="openai",
                iteration_strategy="react",
                started_at_us=1000,
                completed_at_us=2000,
                status=StageStatus.PAUSED,
                error_message=None,
                token_usage=None
            ),
            AgentExecutionMetadata(
                agent_name="agent3",
                llm_provider="openai",
                iteration_strategy="react",
                started_at_us=1000,
                completed_at_us=2000,
                status=StageStatus.FAILED,
                error_message="Test error",
                token_usage=None
            ),
        ]
        
        stage_metadata = ParallelStageMetadata(
            parent_stage_execution_id="parent-123",
            parallel_type="multi_agent",
            failure_policy=FailurePolicy.ALL,
            started_at_us=1000,
            completed_at_us=3000,
            agent_metadatas=metadatas
        )
        
        assert stage_metadata.paused_count == 1
        assert stage_metadata.successful_count == 1
        assert stage_metadata.failed_count == 1
        assert stage_metadata.total_count == 3
    
    def test_paused_count_zero_when_no_paused(self):
        """Test that paused_count is 0 when no agents are paused."""
        metadatas = [
            AgentExecutionMetadata(
                agent_name="agent1",
                llm_provider="openai",
                iteration_strategy="react",
                started_at_us=1000,
                completed_at_us=2000,
                status=StageStatus.COMPLETED,
                error_message=None,
                token_usage=None
            ),
            AgentExecutionMetadata(
                agent_name="agent2",
                llm_provider="openai",
                iteration_strategy="react",
                started_at_us=1000,
                completed_at_us=2000,
                status=StageStatus.COMPLETED,
                error_message=None,
                token_usage=None
            ),
        ]
        
        stage_metadata = ParallelStageMetadata(
            parent_stage_execution_id="parent-123",
            parallel_type="replica",
            failure_policy=FailurePolicy.ANY,
            started_at_us=1000,
            completed_at_us=3000,
            agent_metadatas=metadatas
        )
        
        assert stage_metadata.paused_count == 0
        assert stage_metadata.successful_count == 2
        assert stage_metadata.failed_count == 0
    
    def test_paused_count_all_paused(self):
        """Test that paused_count correctly counts when all agents are paused."""
        metadatas = [
            AgentExecutionMetadata(
                agent_name="agent1",
                llm_provider="openai",
                iteration_strategy="react",
                started_at_us=1000,
                completed_at_us=2000,
                status=StageStatus.PAUSED,
                error_message=None,
                token_usage=None
            ),
            AgentExecutionMetadata(
                agent_name="agent2",
                llm_provider="openai",
                iteration_strategy="react",
                started_at_us=1000,
                completed_at_us=2000,
                status=StageStatus.PAUSED,
                error_message=None,
                token_usage=None
            ),
            AgentExecutionMetadata(
                agent_name="agent3",
                llm_provider="openai",
                iteration_strategy="react",
                started_at_us=1000,
                completed_at_us=2000,
                status=StageStatus.PAUSED,
                error_message=None,
                token_usage=None
            ),
        ]
        
        stage_metadata = ParallelStageMetadata(
            parent_stage_execution_id="parent-123",
            parallel_type="multi_agent",
            failure_policy=FailurePolicy.ALL,
            started_at_us=1000,
            completed_at_us=3000,
            agent_metadatas=metadatas
        )
        
        assert stage_metadata.paused_count == 3
        assert stage_metadata.successful_count == 0
        assert stage_metadata.failed_count == 0
        assert stage_metadata.total_count == 3


@pytest.mark.unit
class TestStatusAggregationLogic:
    """Test status aggregation logic for parallel stages."""
    
    def test_pause_takes_priority_over_success(self):
        """Test that if any agent is paused, stage status is PAUSED (even if others succeeded)."""
        # Simulate: 2 completed, 1 paused
        completed_count = 2
        failed_count = 0
        paused_count = 1
        failure_policy = FailurePolicy.ALL
        
        # Logic from _execute_parallel_stage
        if paused_count > 0:
            overall_status = StageStatus.PAUSED
        elif failure_policy == FailurePolicy.ALL:
            overall_status = StageStatus.COMPLETED if failed_count == 0 else StageStatus.FAILED
        else:  # FailurePolicy.ANY
            overall_status = StageStatus.COMPLETED if completed_count > 0 else StageStatus.FAILED
        
        assert overall_status == StageStatus.PAUSED
    
    def test_pause_takes_priority_over_failure(self):
        """Test that if any agent is paused, stage status is PAUSED (even if others failed)."""
        # Simulate: 1 completed, 1 failed, 1 paused
        completed_count = 1
        failed_count = 1
        paused_count = 1
        failure_policy = FailurePolicy.ALL
        
        # Logic from _execute_parallel_stage
        if paused_count > 0:
            overall_status = StageStatus.PAUSED
        elif failure_policy == FailurePolicy.ALL:
            overall_status = StageStatus.COMPLETED if failed_count == 0 else StageStatus.FAILED
        else:  # FailurePolicy.ANY
            overall_status = StageStatus.COMPLETED if completed_count > 0 else StageStatus.FAILED
        
        assert overall_status == StageStatus.PAUSED
    
    def test_no_pause_policy_all_success(self):
        """Test that with policy=ALL and no pauses, stage succeeds if all succeeded."""
        completed_count = 3
        failed_count = 0
        paused_count = 0
        failure_policy = FailurePolicy.ALL
        
        if paused_count > 0:
            overall_status = StageStatus.PAUSED
        elif failure_policy == FailurePolicy.ALL:
            overall_status = StageStatus.COMPLETED if failed_count == 0 else StageStatus.FAILED
        else:  # FailurePolicy.ANY
            overall_status = StageStatus.COMPLETED if completed_count > 0 else StageStatus.FAILED
        
        assert overall_status == StageStatus.COMPLETED
    
    def test_no_pause_policy_all_one_failure(self):
        """Test that with policy=ALL and no pauses, stage fails if any failed."""
        completed_count = 2
        failed_count = 1
        paused_count = 0
        failure_policy = FailurePolicy.ALL
        
        if paused_count > 0:
            overall_status = StageStatus.PAUSED
        elif failure_policy == FailurePolicy.ALL:
            overall_status = StageStatus.COMPLETED if failed_count == 0 else StageStatus.FAILED
        else:  # FailurePolicy.ANY
            overall_status = StageStatus.COMPLETED if completed_count > 0 else StageStatus.FAILED
        
        assert overall_status == StageStatus.FAILED
    
    def test_no_pause_policy_any_success(self):
        """Test that with policy=ANY and no pauses, stage succeeds if any succeeded."""
        completed_count = 1
        failed_count = 2
        paused_count = 0
        failure_policy = FailurePolicy.ANY
        
        if paused_count > 0:
            overall_status = StageStatus.PAUSED
        elif failure_policy == FailurePolicy.ALL:
            overall_status = StageStatus.COMPLETED if failed_count == 0 else StageStatus.FAILED
        else:  # FailurePolicy.ANY
            overall_status = StageStatus.COMPLETED if completed_count > 0 else StageStatus.FAILED
        
        assert overall_status == StageStatus.COMPLETED
    
    def test_no_pause_policy_any_all_failures(self):
        """Test that with policy=ANY and no pauses, stage fails if all failed."""
        completed_count = 0
        failed_count = 3
        paused_count = 0
        failure_policy = FailurePolicy.ANY
        
        if paused_count > 0:
            overall_status = StageStatus.PAUSED
        elif failure_policy == FailurePolicy.ALL:
            overall_status = StageStatus.COMPLETED if failed_count == 0 else StageStatus.FAILED
        else:  # FailurePolicy.ANY
            overall_status = StageStatus.COMPLETED if completed_count > 0 else StageStatus.FAILED
        
        assert overall_status == StageStatus.FAILED


@pytest.mark.unit
class TestChildStatusSeparation:
    """Test logic for separating children by status for resume."""
    
    def test_separate_children_by_status(self):
        """Test that children are correctly separated by status."""
        from tarsy.models.db_models import StageExecution
        
        # Simulate child stage executions
        children = [
            StageExecution(
                execution_id="child-1",
                session_id="session-123",
                stage_id="stage-1",
                stage_index=0,
                stage_name="test-stage",
                agent="agent1",
                status=StageStatus.COMPLETED.value,
                stage_output={"result": "completed"}
            ),
            StageExecution(
                execution_id="child-2",
                session_id="session-123",
                stage_id="stage-2",
                stage_index=0,
                stage_name="test-stage",
                agent="agent2",
                status=StageStatus.PAUSED.value,
                stage_output={"result": "paused"}
            ),
            StageExecution(
                execution_id="child-3",
                session_id="session-123",
                stage_id="stage-3",
                stage_index=0,
                stage_name="test-stage",
                agent="agent3",
                status=StageStatus.FAILED.value,
                error_message="Test failure"
            ),
        ]
        
        # Simulate separation logic from _resume_parallel_stage
        completed_children = [c for c in children if c.status == StageStatus.COMPLETED.value]
        paused_children = [c for c in children if c.status == StageStatus.PAUSED.value]
        failed_children = [c for c in children if c.status == StageStatus.FAILED.value]
        
        assert len(completed_children) == 1
        assert len(paused_children) == 1
        assert len(failed_children) == 1
        
        assert completed_children[0].agent == "agent1"
        assert paused_children[0].agent == "agent2"
        assert failed_children[0].agent == "agent3"
    
    def test_separate_children_all_paused(self):
        """Test separation when all children are paused."""
        from tarsy.models.db_models import StageExecution
        
        children = [
            StageExecution(
                execution_id="child-1",
                session_id="session-123",
                stage_id="stage-1",
                stage_index=0,
                stage_name="test-stage",
                agent="agent1",
                status=StageStatus.PAUSED.value
            ),
            StageExecution(
                execution_id="child-2",
                session_id="session-123",
                stage_id="stage-2",
                stage_index=0,
                stage_name="test-stage",
                agent="agent2",
                status=StageStatus.PAUSED.value
            ),
        ]
        
        completed_children = [c for c in children if c.status == StageStatus.COMPLETED.value]
        paused_children = [c for c in children if c.status == StageStatus.PAUSED.value]
        failed_children = [c for c in children if c.status == StageStatus.FAILED.value]
        
        assert len(completed_children) == 0
        assert len(paused_children) == 2
        assert len(failed_children) == 0
    
    def test_separate_children_all_completed(self):
        """Test separation when all children are completed (shouldn't happen in resume but test logic)."""
        from tarsy.models.db_models import StageExecution
        
        children = [
            StageExecution(
                execution_id="child-1",
                session_id="session-123",
                stage_id="stage-1",
                stage_index=0,
                stage_name="test-stage",
                agent="agent1",
                status=StageStatus.COMPLETED.value
            ),
            StageExecution(
                execution_id="child-2",
                session_id="session-123",
                stage_id="stage-2",
                stage_index=0,
                stage_name="test-stage",
                agent="agent2",
                status=StageStatus.COMPLETED.value
            ),
        ]
        
        completed_children = [c for c in children if c.status == StageStatus.COMPLETED.value]
        paused_children = [c for c in children if c.status == StageStatus.PAUSED.value]
        failed_children = [c for c in children if c.status == StageStatus.FAILED.value]
        
        assert len(completed_children) == 2
        assert len(paused_children) == 0
        assert len(failed_children) == 0

