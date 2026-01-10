"""
Integration tests for iteration_strategy persistence and retrieval.

Tests that iteration_strategy is correctly persisted to the database
and returned in API responses for session history.
"""

import pytest
from sqlmodel import select

from tarsy.models.constants import AlertSessionStatus, StageStatus
from tarsy.models.db_models import AlertSession, StageExecution
from tarsy.repositories.history_repository import HistoryRepository


@pytest.mark.integration
class TestIterationStrategyPersistence:
    """Test iteration_strategy field persistence and retrieval."""

    def test_iteration_strategy_persisted_in_stage_execution(
        self, test_database_session
    ) -> None:
        """Test that iteration_strategy is correctly saved to and retrieved from database."""
        # Create an alert session
        session = AlertSession(
            session_id="test-session-1",
            alert_type="kubernetes",
            agent_type="kubernetes",
            chain_id="test-chain",
            status=AlertSessionStatus.COMPLETED.value,
        )
        test_database_session.add(session)
        test_database_session.commit()

        # Create stage execution with iteration_strategy
        stage_exec = StageExecution(
            execution_id="exec-1",
            session_id="test-session-1",
            stage_id="test-stage-1",
            stage_index=0,
            stage_name="Test Stage",
            agent="TestAgent",
            status=StageStatus.COMPLETED.value,
            iteration_strategy="native-thinking",
        )
        test_database_session.add(stage_exec)
        test_database_session.commit()

        # Retrieve from database
        result = test_database_session.exec(
            select(StageExecution).where(StageExecution.execution_id == "exec-1")
        )
        retrieved_exec = result.one()

        # Verify iteration_strategy was persisted
        assert retrieved_exec.iteration_strategy == "native-thinking"

    def test_iteration_strategy_returned_in_detailed_stage(
        self, test_database_session
    ) -> None:
        """Test that iteration_strategy is included in DetailedStage response."""
        # Create an alert session
        session = AlertSession(
            session_id="test-session-2",
            alert_type="kubernetes",
            agent_type="kubernetes",
            chain_id="test-chain",
            status=AlertSessionStatus.COMPLETED.value,
        )
        test_database_session.add(session)
        test_database_session.commit()

        # Create stage executions with different iteration strategies
        stage_exec_react = StageExecution(
            execution_id="exec-react",
            session_id="test-session-2",
            stage_id="react-stage",
            stage_index=0,
            stage_name="React Stage",
            agent="ReactAgent",
            status=StageStatus.COMPLETED.value,
            iteration_strategy="react",
        )
        stage_exec_native = StageExecution(
            execution_id="exec-native",
            session_id="test-session-2",
            stage_id="native-stage",
            stage_index=1,
            stage_name="Native Thinking Stage",
            agent="NativeAgent",
            status=StageStatus.COMPLETED.value,
            iteration_strategy="native-thinking",
        )
        test_database_session.add(stage_exec_react)
        test_database_session.add(stage_exec_native)
        test_database_session.commit()

        # Use HistoryRepository to get detailed session (as API would)
        repo = HistoryRepository(session=test_database_session)
        detailed_session = repo.get_session_details("test-session-2")

        # Verify iteration_strategy is present in DetailedStage
        assert len(detailed_session.stages) == 2
        
        react_stage = detailed_session.stages[0]
        assert react_stage.iteration_strategy == "react"
        assert react_stage.stage_name == "React Stage"
        
        native_stage = detailed_session.stages[1]
        assert native_stage.iteration_strategy == "native-thinking"
        assert native_stage.stage_name == "Native Thinking Stage"

    def test_iteration_strategy_nullable_for_legacy_data(
        self, test_database_session
    ) -> None:
        """Test that iteration_strategy can be NULL for backward compatibility with legacy data."""
        # Create an alert session
        session = AlertSession(
            session_id="test-session-3",
            alert_type="kubernetes",
            agent_type="kubernetes",
            chain_id="test-chain",
            status=AlertSessionStatus.COMPLETED.value,
        )
        test_database_session.add(session)
        test_database_session.commit()

        # Create stage execution WITHOUT iteration_strategy (legacy data)
        stage_exec = StageExecution(
            execution_id="exec-legacy",
            session_id="test-session-3",
            stage_id="legacy-stage",
            stage_index=0,
            stage_name="Legacy Stage",
            agent="LegacyAgent",
            status=StageStatus.COMPLETED.value,
            # iteration_strategy=None (default)
        )
        test_database_session.add(stage_exec)
        test_database_session.commit()

        # Retrieve from database
        result = test_database_session.exec(
            select(StageExecution).where(StageExecution.execution_id == "exec-legacy")
        )
        retrieved_exec = result.one()

        # Verify NULL is handled correctly
        assert retrieved_exec.iteration_strategy is None

        # Verify HistoryRepository handles NULL iteration_strategy
        repo = HistoryRepository(session=test_database_session)
        detailed_session = repo.get_session_details("test-session-3")

        assert len(detailed_session.stages) == 1
        legacy_stage = detailed_session.stages[0]
        assert legacy_stage.iteration_strategy is None
