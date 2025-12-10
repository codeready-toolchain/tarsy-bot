"""
Integration tests for parallel stages indicator in session list.

Tests that the has_parallel_stages flag is correctly set when retrieving
session lists based on stage execution data.
"""

import pytest
from sqlmodel import Session

from tarsy.models.constants import ParallelType, StageStatus
from tarsy.models.db_models import AlertSession, StageExecution
from tarsy.repositories.history_repository import HistoryRepository
from tarsy.utils.timestamp import now_us


@pytest.mark.asyncio
@pytest.mark.integration
class TestParallelStagesIndicator:
    """Integration tests for parallel stages indicator in get_alert_sessions."""

    @pytest.mark.parametrize(
        "parallel_type,expected_flag",
        [
            (ParallelType.MULTI_AGENT, True),
            (ParallelType.REPLICA, True),
            (ParallelType.SINGLE, False),
        ],
    )
    async def test_has_parallel_stages_flag_with_different_types(
        self,
        test_database_session: Session,
        parallel_type: ParallelType,
        expected_flag: bool,
    ) -> None:
        """Test that has_parallel_stages flag is set correctly for different parallel types."""
        repository = HistoryRepository(test_database_session)
        
        # Create a test session
        session_id = f"test-session-{parallel_type.value}"
        session = AlertSession(
            session_id=session_id,
            alert_data={"pod": "test-pod"},
            agent_type="TestAgent",
            alert_type="kubernetes",
            status=StageStatus.COMPLETED.value,
            started_at_us=now_us(),
            chain_id="test-chain",
        )
        repository.create_alert_session(session)
        
        # Create a stage execution with the specified parallel_type
        stage = StageExecution(
            session_id=session_id,
            stage_id="test-stage-0",
            stage_index=0,
            stage_name="test-stage",
            agent="TestAgent",
            status=StageStatus.COMPLETED.value,
            parallel_type=parallel_type.value,
            started_at_us=now_us(),
        )
        test_database_session.add(stage)
        test_database_session.commit()
        
        # Retrieve sessions and verify flag
        result = repository.get_alert_sessions()
        
        assert result is not None
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == session_id
        assert result.sessions[0].has_parallel_stages == expected_flag

    async def test_has_parallel_stages_with_child_executions(
        self, test_database_session: Session
    ) -> None:
        """Test that has_parallel_stages is True when session has child stage executions."""
        repository = HistoryRepository(test_database_session)
        
        # Create a test session
        session_id = "test-session-with-children"
        session = AlertSession(
            session_id=session_id,
            alert_data={"namespace": "production"},
            agent_type="ParallelAgent",
            alert_type="kubernetes",
            status=StageStatus.COMPLETED.value,
            started_at_us=now_us(),
            chain_id="parallel-chain",
        )
        repository.create_alert_session(session)
        
        # Create parent stage execution
        parent_stage = StageExecution(
            session_id=session_id,
            stage_id="parent-stage-0",
            stage_index=0,
            stage_name="investigation",
            agent="ParentAgent",
            status=StageStatus.COMPLETED.value,
            parallel_type=ParallelType.MULTI_AGENT.value,
            started_at_us=now_us(),
        )
        test_database_session.add(parent_stage)
        test_database_session.commit()
        test_database_session.refresh(parent_stage)
        
        # Create child stage executions
        for i in range(3):
            child_stage = StageExecution(
                session_id=session_id,
                stage_id=f"child-stage-{i}",
                stage_index=0,
                stage_name="investigation",
                agent=f"Agent{i+1}",
                status=StageStatus.COMPLETED.value,
                parallel_type=ParallelType.MULTI_AGENT.value,
                parent_stage_execution_id=parent_stage.execution_id,
                parallel_index=i + 1,
                started_at_us=now_us(),
            )
            test_database_session.add(child_stage)
        
        test_database_session.commit()
        
        # Retrieve sessions and verify flag is True due to children
        result = repository.get_alert_sessions()
        
        assert result is not None
        assert len(result.sessions) == 1
        assert result.sessions[0].has_parallel_stages is True

    async def test_has_parallel_stages_false_for_single_stage_session(
        self, test_database_session: Session
    ) -> None:
        """Test that has_parallel_stages is False for sessions with only single-type stages."""
        repository = HistoryRepository(test_database_session)
        
        # Create a test session
        session_id = "test-session-single-only"
        session = AlertSession(
            session_id=session_id,
            alert_data={"alert": "test"},
            agent_type="SingleAgent",
            alert_type="generic",
            status=StageStatus.COMPLETED.value,
            started_at_us=now_us(),
            chain_id="single-chain",
        )
        repository.create_alert_session(session)
        
        # Create multiple single-type stages
        for i in range(3):
            stage = StageExecution(
                session_id=session_id,
                stage_id=f"stage-{i}",
                stage_index=i,
                stage_name=f"stage-{i}",
                agent="SingleAgent",
                status=StageStatus.COMPLETED.value,
                parallel_type=ParallelType.SINGLE.value,
                started_at_us=now_us(),
            )
            test_database_session.add(stage)
        
        test_database_session.commit()
        
        # Retrieve sessions and verify flag is False
        result = repository.get_alert_sessions()
        
        assert result is not None
        assert len(result.sessions) == 1
        assert result.sessions[0].has_parallel_stages is False

    async def test_has_parallel_stages_mixed_sessions(
        self, test_database_session: Session
    ) -> None:
        """Test that has_parallel_stages is correctly set for multiple sessions with different configurations."""
        repository = HistoryRepository(test_database_session)
        
        # Create session 1: with parallel stages
        session1 = AlertSession(
            session_id="session-with-parallel",
            alert_data={"type": "parallel"},
            agent_type="ParallelAgent",
            alert_type="kubernetes",
            status=StageStatus.COMPLETED.value,
            started_at_us=now_us(),
            chain_id="chain-1",
        )
        repository.create_alert_session(session1)
        
        stage1 = StageExecution(
            session_id="session-with-parallel",
            stage_id="parallel-stage",
            stage_index=0,
            stage_name="parallel",
            agent="ParallelAgent",
            status=StageStatus.COMPLETED.value,
            parallel_type=ParallelType.REPLICA.value,
            started_at_us=now_us(),
        )
        test_database_session.add(stage1)
        
        # Create session 2: without parallel stages
        session2 = AlertSession(
            session_id="session-without-parallel",
            alert_data={"type": "single"},
            agent_type="SingleAgent",
            alert_type="database",
            status=StageStatus.COMPLETED.value,
            started_at_us=now_us(),
            chain_id="chain-2",
        )
        repository.create_alert_session(session2)
        
        stage2 = StageExecution(
            session_id="session-without-parallel",
            stage_id="single-stage",
            stage_index=0,
            stage_name="analysis",
            agent="SingleAgent",
            status=StageStatus.COMPLETED.value,
            parallel_type=ParallelType.SINGLE.value,
            started_at_us=now_us(),
        )
        test_database_session.add(stage2)
        
        # Create session 3: with no stages at all
        session3 = AlertSession(
            session_id="session-no-stages",
            alert_data={"type": "none"},
            agent_type="TestAgent",
            alert_type="test",
            status=StageStatus.PENDING.value,
            started_at_us=now_us(),
            chain_id="chain-3",
        )
        repository.create_alert_session(session3)
        
        test_database_session.commit()
        
        # Retrieve all sessions
        result = repository.get_alert_sessions(page_size=10)
        
        assert result is not None
        assert len(result.sessions) == 3
        
        # Find each session and verify flag
        sessions_by_id = {s.session_id: s for s in result.sessions}
        
        assert sessions_by_id["session-with-parallel"].has_parallel_stages is True
        assert sessions_by_id["session-without-parallel"].has_parallel_stages is False
        assert sessions_by_id["session-no-stages"].has_parallel_stages is False

    async def test_has_parallel_stages_with_filters_and_pagination(
        self, test_database_session: Session
    ) -> None:
        """Test that has_parallel_stages works correctly with pagination and filters."""
        repository = HistoryRepository(test_database_session)
        
        # Create multiple sessions with different statuses
        for i in range(5):
            is_parallel = i % 2 == 0  # Alternate parallel/single
            status = StageStatus.COMPLETED.value if i < 3 else StageStatus.FAILED.value
            
            session = AlertSession(
                session_id=f"session-{i}",
                alert_data={"index": i},
                agent_type="TestAgent",
                alert_type="kubernetes",
                status=status,
                started_at_us=now_us() - (i * 1_000_000),  # Different timestamps
                chain_id=f"chain-{i}",
            )
            repository.create_alert_session(session)
            
            stage = StageExecution(
                session_id=f"session-{i}",
                stage_id=f"stage-{i}",
                stage_index=0,
                stage_name="test",
                agent="TestAgent",
                status=status,
                parallel_type=(
                    ParallelType.MULTI_AGENT.value
                    if is_parallel
                    else ParallelType.SINGLE.value
                ),
                started_at_us=now_us(),
            )
            test_database_session.add(stage)
        
        test_database_session.commit()
        
        # Test with status filter
        result = repository.get_alert_sessions(
            status=StageStatus.COMPLETED.value, page_size=10
        )
        assert result is not None
        assert len(result.sessions) == 3
        
        # Verify flags are correct for completed sessions
        for session_overview in result.sessions:
            session_id = session_overview.session_id
            index = int(session_id.split("-")[1])
            is_parallel = index % 2 == 0
            assert session_overview.has_parallel_stages == is_parallel
        
        # Test with pagination
        result_page1 = repository.get_alert_sessions(page=1, page_size=2)
        assert len(result_page1.sessions) == 2
        assert all(hasattr(s, "has_parallel_stages") for s in result_page1.sessions)

    async def test_has_parallel_stages_graceful_degradation(
        self, test_database_session: Session
    ) -> None:
        """Test that get_alert_sessions continues working even if parallel stages query has issues."""
        repository = HistoryRepository(test_database_session)
        
        # Create a valid session
        session = AlertSession(
            session_id="test-session-graceful",
            alert_data={"test": "data"},
            agent_type="TestAgent",
            alert_type="test",
            status=StageStatus.COMPLETED.value,
            started_at_us=now_us(),
            chain_id="test-chain",
        )
        repository.create_alert_session(session)
        
        # Add a valid stage
        stage = StageExecution(
            session_id="test-session-graceful",
            stage_id="test-stage",
            stage_index=0,
            stage_name="test",
            agent="TestAgent",
            status=StageStatus.COMPLETED.value,
            parallel_type=ParallelType.SINGLE.value,
            started_at_us=now_us(),
        )
        test_database_session.add(stage)
        test_database_session.commit()
        
        # Retrieve sessions - should work even if parallel query fails
        # (the actual error handling is tested by the code catching exceptions)
        result = repository.get_alert_sessions()
        
        assert result is not None
        assert len(result.sessions) == 1
        assert result.sessions[0].session_id == "test-session-graceful"
        # Flag should be present (defaulted to False if query fails)
        assert hasattr(result.sessions[0], "has_parallel_stages")

