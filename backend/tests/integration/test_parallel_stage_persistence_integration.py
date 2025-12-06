"""
Integration tests for parallel stage execution persistence.

Tests actual database operations for parallel stage executions including
parent-child relationships, nested queries, and data integrity.
"""

import pytest
from sqlmodel import Session, select

from tarsy.models.constants import AlertSessionStatus, ParallelType, StageStatus
from tarsy.models.db_models import AlertSession, StageExecution
from tarsy.repositories.history_repository import HistoryRepository


@pytest.mark.integration
class TestParallelStagePersistence:
    """Integration tests for parallel stage persistence."""
    
    @pytest.fixture
    def test_session(self, test_db_session: Session) -> AlertSession:
        """Create a test alert session."""
        session = AlertSession(
            session_id="test-parallel-session",
            alert_data={"test": "data"},
            agent_type="chain:test",
            alert_type="TestAlert",
            status=AlertSessionStatus.IN_PROGRESS.value,
            chain_id="test-chain"
        )
        test_db_session.add(session)
        test_db_session.commit()
        return session
    
    def test_create_parent_stage_with_parallel_type(self, test_db_session: Session, test_session: AlertSession):
        """Test creating a parent stage execution with parallel_type."""
        parent_stage = StageExecution(
            session_id=test_session.session_id,
            stage_id="parallel-stage",
            stage_index=0,
            stage_name="Parallel Investigation",
            agent="ParentAgent",
            status=StageStatus.ACTIVE.value,
            parent_stage_execution_id=None,
            parallel_index=0,
            parallel_type=ParallelType.MULTI_AGENT.value
        )
        
        test_db_session.add(parent_stage)
        test_db_session.commit()
        test_db_session.refresh(parent_stage)
        
        # Verify saved correctly
        assert parent_stage.execution_id is not None
        assert parent_stage.parallel_type == "multi_agent"
        assert parent_stage.parallel_index == 0
        assert parent_stage.parent_stage_execution_id is None
    
    def test_create_child_stages_with_parent_reference(self, test_db_session: Session, test_session: AlertSession):
        """Test creating child stage executions with parent reference."""
        # Create parent
        parent_stage = StageExecution(
            session_id=test_session.session_id,
            stage_id="parallel-stage",
            stage_index=0,
            stage_name="Parallel Stage",
            agent="ParentAgent",
            status=StageStatus.ACTIVE.value,
            parallel_type=ParallelType.MULTI_AGENT.value
        )
        test_db_session.add(parent_stage)
        test_db_session.commit()
        test_db_session.refresh(parent_stage)
        
        # Create children
        child1 = StageExecution(
            session_id=test_session.session_id,
            stage_id="parallel-stage-child",
            stage_index=0,
            stage_name="Child 1",
            agent="Agent1",
            status=StageStatus.COMPLETED.value,
            parent_stage_execution_id=parent_stage.execution_id,
            parallel_index=1,
            parallel_type=ParallelType.MULTI_AGENT.value
        )
        
        child2 = StageExecution(
            session_id=test_session.session_id,
            stage_id="parallel-stage-child",
            stage_index=0,
            stage_name="Child 2",
            agent="Agent2",
            status=StageStatus.COMPLETED.value,
            parent_stage_execution_id=parent_stage.execution_id,
            parallel_index=2,
            parallel_type=ParallelType.MULTI_AGENT.value
        )
        
        test_db_session.add(child1)
        test_db_session.add(child2)
        test_db_session.commit()
        
        # Query children
        stmt = select(StageExecution).where(
            StageExecution.parent_stage_execution_id == parent_stage.execution_id
        ).order_by(StageExecution.parallel_index)
        
        children = test_db_session.exec(stmt).all()
        
        assert len(children) == 2
        assert children[0].parallel_index == 1
        assert children[0].agent == "Agent1"
        assert children[1].parallel_index == 2
        assert children[1].agent == "Agent2"
    
    def test_repository_get_parallel_stage_children(self, test_db_session: Session, test_session: AlertSession):
        """Test repository method for retrieving child stages."""
        repo = HistoryRepository(test_db_session)
        
        # Create parent and children
        parent_stage = StageExecution(
            session_id=test_session.session_id,
            stage_id="parallel-stage",
            stage_index=0,
            stage_name="Parallel Stage",
            agent="ParentAgent",
            status=StageStatus.COMPLETED.value,
            parallel_type=ParallelType.REPLICA.value
        )
        test_db_session.add(parent_stage)
        test_db_session.commit()
        test_db_session.refresh(parent_stage)
        
        for i in range(3):
            child = StageExecution(
                session_id=test_session.session_id,
                stage_id="parallel-stage-child",
                stage_index=0,
                stage_name=f"Replica {i+1}",
                agent=f"Agent-{i+1}",
                status=StageStatus.COMPLETED.value,
                parent_stage_execution_id=parent_stage.execution_id,
                parallel_index=i+1,
                parallel_type=ParallelType.REPLICA.value
            )
            test_db_session.add(child)
        
        test_db_session.commit()
        
        # Use repository method
        children = repo.get_parallel_stage_children(parent_stage.execution_id)
        
        assert len(children) == 3
        assert all(c.parent_stage_execution_id == parent_stage.execution_id for c in children)
        assert [c.parallel_index for c in children] == [1, 2, 3]
    
    def test_repository_get_stage_executions_nested_structure(self, test_db_session: Session, test_session: AlertSession):
        """Test that get_stage_executions_for_session returns nested structure."""
        repo = HistoryRepository(test_db_session)
        
        # Create a regular stage
        regular_stage = StageExecution(
            session_id=test_session.session_id,
            stage_id="regular-stage",
            stage_index=0,
            stage_name="Regular Stage",
            agent="RegularAgent",
            status=StageStatus.COMPLETED.value,
            parallel_type=ParallelType.SINGLE.value
        )
        test_db_session.add(regular_stage)
        
        # Create a parallel parent stage
        parent_stage = StageExecution(
            session_id=test_session.session_id,
            stage_id="parallel-stage",
            stage_index=1,
            stage_name="Parallel Stage",
            agent="ParentAgent",
            status=StageStatus.COMPLETED.value,
            parallel_type=ParallelType.MULTI_AGENT.value
        )
        test_db_session.add(parent_stage)
        test_db_session.commit()
        test_db_session.refresh(parent_stage)
        
        # Create child stages
        child1 = StageExecution(
            session_id=test_session.session_id,
            stage_id="parallel-stage-child",
            stage_index=1,
            stage_name="Child 1",
            agent="Agent1",
            status=StageStatus.COMPLETED.value,
            parent_stage_execution_id=parent_stage.execution_id,
            parallel_index=1,
            parallel_type=ParallelType.MULTI_AGENT.value
        )
        child2 = StageExecution(
            session_id=test_session.session_id,
            stage_id="parallel-stage-child",
            stage_index=1,
            stage_name="Child 2",
            agent="Agent2",
            status=StageStatus.COMPLETED.value,
            parent_stage_execution_id=parent_stage.execution_id,
            parallel_index=2,
            parallel_type=ParallelType.MULTI_AGENT.value
        )
        test_db_session.add(child1)
        test_db_session.add(child2)
        test_db_session.commit()
        
        # Get stages with nested structure
        stages = repo.get_stage_executions_for_session(test_session.session_id)
        
        # Should only return top-level stages
        assert len(stages) == 2
        
        # First should be regular stage
        assert stages[0].stage_index == 0
        assert stages[0].parallel_type == "single"
        assert not hasattr(stages[0], 'parallel_executions') or stages[0].parallel_executions is None
        
        # Second should be parallel parent with children
        assert stages[1].stage_index == 1
        assert stages[1].parallel_type == "multi_agent"
        assert hasattr(stages[1], 'parallel_executions')
        assert stages[1].parallel_executions is not None
        assert len(stages[1].parallel_executions) == 2
        assert stages[1].parallel_executions[0].parallel_index == 1
        assert stages[1].parallel_executions[1].parallel_index == 2
    
    def test_parallel_type_values(self, test_db_session: Session, test_session: AlertSession):
        """Test all parallel_type values persist correctly."""
        parallel_types = ParallelType.values()
        
        for idx, ptype in enumerate(parallel_types):
            stage = StageExecution(
                session_id=test_session.session_id,
                stage_id=f"stage-{ptype}",
                stage_index=idx,
                stage_name=f"Stage {ptype}",
                agent="TestAgent",
                status=StageStatus.COMPLETED.value,
                parallel_type=ptype
            )
            test_db_session.add(stage)
        
        test_db_session.commit()
        
        # Query back
        stmt = select(StageExecution).where(
            StageExecution.session_id == test_session.session_id
        ).order_by(StageExecution.stage_index)
        
        stages = test_db_session.exec(stmt).all()
        
        assert len(stages) == 3
        assert [s.parallel_type for s in stages] == parallel_types

