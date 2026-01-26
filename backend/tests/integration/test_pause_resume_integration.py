"""
Integration tests for pause/resume functionality with real database.

Tests the complete pause/resume flow including database operations,
event publishing, and state persistence.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tarsy.models.constants import AlertSessionStatus, StageStatus
from tarsy.models.db_models import AlertSession, SQLModel, StageExecution
from tarsy.repositories.event_repository import EventRepository
from tarsy.services.events.channels import EventChannel
from tarsy.services.events.event_helpers import (
    publish_session_paused,
    publish_session_resumed,
)
from tarsy.utils.timestamp import now_us


@pytest_asyncio.fixture
async def async_test_engine():
    """Create an in-memory async database engine for testing."""
    from tarsy import database
    
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    database.init_db._async_engine = engine
    database.init_db._async_session_factory = session_factory
    
    yield engine
    
    # Cleanup
    database.init_db._async_engine = None
    database.init_db._async_session_factory = None
    await engine.dispose()


@pytest_asyncio.fixture
async def async_test_session_factory(async_test_engine):
    """Create an async session factory for testing."""
    _ = async_test_engine  # ensure fixture dependency, avoid ARG001
    from tarsy import database
    return database.init_db._async_session_factory


@pytest_asyncio.fixture
async def test_paused_session_in_db(async_test_session_factory):
    """Create a test paused session with stage execution in the database."""
    session_id = "integration-test-paused-session"
    execution_id = "integration-test-execution"
    
    async with async_test_session_factory() as session:
        # Create paused session
        test_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.PAUSED.value,
            started_at_us=now_us(),
            chain_id="test-chain-1",
            alert_data={"severity": "warning", "message": "Test alert"}
        )
        session.add(test_session)
        
        # Create paused stage execution
        test_stage = StageExecution(
            execution_id=execution_id,
            session_id=session_id,
            stage_id="initial-analysis",
            stage_index=0,
            stage_name="Initial Analysis",
            agent="KubernetesAgent",
            status=StageStatus.PAUSED.value,
            started_at_us=now_us(),
            current_iteration=30
        )
        session.add(test_stage)
        await session.commit()
    
    return session_id, execution_id


@pytest_asyncio.fixture
async def test_in_progress_session_in_db(async_test_session_factory):
    """Create a test in-progress session in the database."""
    session_id = "integration-test-in-progress-session"
    
    async with async_test_session_factory() as session:
        test_session = AlertSession(
            session_id=session_id,
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.IN_PROGRESS.value,
            started_at_us=now_us(),
            chain_id="test-chain-1"
        )
        session.add(test_session)
        await session.commit()
    
    return session_id


@pytest.mark.integration
class TestPauseResumeIntegration:
    """Integration tests for pause/resume with real database."""
    
    @pytest.mark.asyncio
    async def test_paused_event_published_to_sessions_channel(
        self, async_test_session_factory, test_in_progress_session_in_db
    ) -> None:
        """Test that paused event is published to sessions channel with metadata."""
        session_id = test_in_progress_session_in_db
        pause_metadata = {
            "reason": "max_iterations_reached",
            "current_iteration": 30,
            "message": "Paused after 30 iterations - resume to continue",
            "paused_at_us": 1234567890
        }
        
        # Publish paused event
        await publish_session_paused(session_id, pause_metadata)
        
        # Verify event was published to sessions channel
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            events = await repo.get_events_after(EventChannel.SESSIONS, after_id=0, limit=10)
            
            assert len(events) > 0
            latest_event = events[-1]
            assert latest_event.payload["type"] == "session.paused"
            assert latest_event.payload["session_id"] == session_id
            assert latest_event.payload["status"] == "paused"
            assert latest_event.payload["pause_metadata"] == pause_metadata
            assert latest_event.payload["pause_metadata"]["reason"] == "max_iterations_reached"
            assert latest_event.payload["pause_metadata"]["current_iteration"] == 30
    
    @pytest.mark.asyncio
    async def test_paused_event_published_to_session_specific_channel(
        self, async_test_session_factory, test_in_progress_session_in_db
    ) -> None:
        """Test that paused event is published to session-specific channel."""
        session_id = test_in_progress_session_in_db
        
        # Publish paused event
        await publish_session_paused(session_id)
        
        # Verify event was published to session-specific channel
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            session_channel = EventChannel.session_details(session_id)
            events = await repo.get_events_after(session_channel, after_id=0, limit=10)
            
            assert len(events) > 0
            latest_event = events[-1]
            assert latest_event.payload["type"] == "session.paused"
            assert latest_event.payload["session_id"] == session_id
    
    @pytest.mark.asyncio
    async def test_resumed_event_published_to_sessions_channel(
        self, async_test_session_factory, test_paused_session_in_db
    ) -> None:
        """Test that resumed event is published to sessions channel."""
        session_id, _ = test_paused_session_in_db
        
        # Publish resumed event
        await publish_session_resumed(session_id)
        
        # Verify event was published to sessions channel
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            events = await repo.get_events_after(EventChannel.SESSIONS, after_id=0, limit=10)
            
            assert len(events) > 0
            latest_event = events[-1]
            assert latest_event.payload["type"] == "session.resumed"
            assert latest_event.payload["session_id"] == session_id
            assert latest_event.payload["status"] == "in_progress"
    
    @pytest.mark.asyncio
    async def test_resumed_event_published_to_session_specific_channel(
        self, async_test_session_factory, test_paused_session_in_db
    ) -> None:
        """Test that resumed event is published to session-specific channel."""
        session_id, _ = test_paused_session_in_db
        
        # Publish resumed event
        await publish_session_resumed(session_id)
        
        # Verify event was published to session-specific channel
        async with async_test_session_factory() as session:
            repo = EventRepository(session)
            session_channel = EventChannel.session_details(session_id)
            events = await repo.get_events_after(session_channel, after_id=0, limit=10)
            
            assert len(events) > 0
            latest_event = events[-1]
            assert latest_event.payload["type"] == "session.resumed"
            assert latest_event.payload["session_id"] == session_id
    
    @pytest.mark.asyncio
    async def test_pause_state_persisted_in_database(
        self, async_test_session_factory, test_paused_session_in_db
    ) -> None:
        """Test that paused state is correctly persisted in database."""
        session_id, execution_id = test_paused_session_in_db
        
        # Verify session status
        async with async_test_session_factory() as session:
            from sqlmodel import select
            
            # Check session status
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            assert alert_session.status == AlertSessionStatus.PAUSED.value
            
            # Check stage execution status and iteration
            result = await session.execute(
                select(StageExecution).where(StageExecution.execution_id == execution_id)
            )
            stage_execution = result.scalar_one()
            assert stage_execution.status == StageStatus.PAUSED.value
            assert stage_execution.current_iteration == 30
    
    @pytest.mark.asyncio
    async def test_current_iteration_persisted_in_stage_execution(
        self, async_test_session_factory, test_paused_session_in_db
    ) -> None:
        """Test that current_iteration field is correctly persisted."""
        session_id, execution_id = test_paused_session_in_db
        
        async with async_test_session_factory() as session:
            from sqlmodel import select
            
            result = await session.execute(
                select(StageExecution).where(StageExecution.execution_id == execution_id)
            )
            stage_execution = result.scalar_one()
            
            # Verify current_iteration is stored
            assert stage_execution.current_iteration is not None
            assert stage_execution.current_iteration == 30
    
    @pytest.mark.asyncio
    async def test_pause_resume_state_transitions(
        self, async_test_session_factory, test_in_progress_session_in_db
    ) -> None:
        """Test complete state transition: in_progress -> paused -> in_progress."""
        session_id = test_in_progress_session_in_db
        
        # Initial state verification
        async with async_test_session_factory() as session:
            from sqlmodel import select
            
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            assert alert_session.status == AlertSessionStatus.IN_PROGRESS.value
        
        # Transition to PAUSED
        async with async_test_session_factory() as session:
            from sqlmodel import select
            
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            alert_session.status = AlertSessionStatus.PAUSED.value
            session.add(alert_session)
            await session.commit()
        
        # Verify paused state
        async with async_test_session_factory() as session:
            from sqlmodel import select
            
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            assert alert_session.status == AlertSessionStatus.PAUSED.value
        
        # Transition back to IN_PROGRESS (resume)
        async with async_test_session_factory() as session:
            from sqlmodel import select
            
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            alert_session.status = AlertSessionStatus.IN_PROGRESS.value
            session.add(alert_session)
            await session.commit()
        
        # Verify resumed state
        async with async_test_session_factory() as session:
            from sqlmodel import select
            
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            assert alert_session.status == AlertSessionStatus.IN_PROGRESS.value
    
    @pytest.mark.asyncio
    async def test_multiple_stages_pause_at_correct_stage(
        self, async_test_session_factory
    ) -> None:
        """Test that only the correct stage is marked as paused in multi-stage chains."""
        session_id = "multi-stage-pause-test"
        
        async with async_test_session_factory() as session:
            # Create session
            test_session = AlertSession(
                session_id=session_id,
                alert_type="kubernetes",
                agent_type="KubernetesAgent",
                status=AlertSessionStatus.PAUSED.value,
                started_at_us=now_us(),
                chain_id="multi-stage-chain"
            )
            session.add(test_session)
            
            # Create multiple stages
            stage1 = StageExecution(
                execution_id="stage1",
                session_id=session_id,
                stage_id="data-collection",
                stage_index=0,
                stage_name="Data Collection",
                agent="KubernetesAgent",
                status=StageStatus.COMPLETED.value,
                started_at_us=now_us(),
                completed_at_us=now_us()
            )
            
            stage2 = StageExecution(
                execution_id="stage2",
                session_id=session_id,
                stage_id="initial-analysis",
                stage_index=1,
                stage_name="Initial Analysis",
                agent="KubernetesAgent",
                status=StageStatus.PAUSED.value,
                started_at_us=now_us(),
                current_iteration=30
            )
            
            stage3 = StageExecution(
                execution_id="stage3",
                session_id=session_id,
                stage_id="final-report",
                stage_index=2,
                stage_name="Final Report",
                agent="KubernetesAgent",
                status=StageStatus.PENDING.value
            )
            
            session.add(stage1)
            session.add(stage2)
            session.add(stage3)
            await session.commit()
        
        # Verify only stage 2 is paused
        async with async_test_session_factory() as session:
            from sqlmodel import select
            
            result = await session.execute(
                select(StageExecution)
                .where(StageExecution.session_id == session_id)
                .order_by(StageExecution.stage_index)
            )
            stages = result.scalars().all()
            
            assert len(stages) == 3
            assert stages[0].status == StageStatus.COMPLETED.value
            assert stages[1].status == StageStatus.PAUSED.value
            assert stages[1].current_iteration == 30
            assert stages[2].status == StageStatus.PENDING.value
    
    @pytest.mark.asyncio
    async def test_pause_metadata_persisted_to_database(
        self, async_test_session_factory
    ) -> None:
        """Test that pause_metadata is correctly stored in database."""
        session_id = "metadata-test-session"
        
        pause_metadata = {
            "reason": "max_iterations_reached",
            "current_iteration": 30,
            "message": "Paused after 30 iterations - resume to continue",
            "paused_at_us": 1234567890
        }
        
        async with async_test_session_factory() as session:
            # Create paused session with metadata
            test_session = AlertSession(
                session_id=session_id,
                alert_type="kubernetes",
                agent_type="KubernetesAgent",
                status=AlertSessionStatus.PAUSED.value,
                started_at_us=now_us(),
                chain_id="test-chain",
                pause_metadata=pause_metadata
            )
            session.add(test_session)
            await session.commit()
        
        # Verify metadata persisted correctly
        async with async_test_session_factory() as session:
            from sqlmodel import select
            
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            
            assert alert_session.pause_metadata is not None
            assert alert_session.pause_metadata["reason"] == "max_iterations_reached"
            assert alert_session.pause_metadata["current_iteration"] == 30
            assert alert_session.pause_metadata["message"] == "Paused after 30 iterations - resume to continue"
            assert alert_session.pause_metadata["paused_at_us"] == 1234567890
    
    @pytest.mark.asyncio
    async def test_pause_metadata_survives_roundtrip(
        self, async_test_session_factory
    ) -> None:
        """Test that pause_metadata survives database roundtrip correctly."""
        session_id = "roundtrip-test"
        
        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        
        # Create PauseMetadata model
        pause_meta = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=30,
            message="Test pause",
            paused_at_us=1234567890
        )
        
        # Serialize to dict (JSON mode for database storage)
        pause_meta_dict = pause_meta.model_dump(mode='json')
        
        # Store in database
        async with async_test_session_factory() as session:
            test_session = AlertSession(
                session_id=session_id,
                alert_type="kubernetes",
                agent_type="KubernetesAgent",
                status=AlertSessionStatus.PAUSED.value,
                started_at_us=now_us(),
                chain_id="test-chain",
                pause_metadata=pause_meta_dict
            )
            session.add(test_session)
            await session.commit()
        
        # Read from database
        async with async_test_session_factory() as session:
            from sqlmodel import select
            
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            
            # Deserialize back to PauseMetadata model
            restored_meta = PauseMetadata.model_validate(alert_session.pause_metadata)
            
            assert restored_meta.reason == PauseReason.MAX_ITERATIONS_REACHED
            assert restored_meta.current_iteration == 30
            assert restored_meta.message == "Test pause"
            assert restored_meta.paused_at_us == 1234567890
    
    @pytest.mark.asyncio
    async def test_pause_metadata_optional_in_database(
        self, async_test_session_factory
    ) -> None:
        """Test that sessions can exist without pause_metadata."""
        session_id = "no-metadata-session"
        
        async with async_test_session_factory() as session:
            # Create session without pause_metadata
            test_session = AlertSession(
                session_id=session_id,
                alert_type="kubernetes",
                agent_type="KubernetesAgent",
                status=AlertSessionStatus.COMPLETED.value,
                started_at_us=now_us(),
                chain_id="test-chain",
                pause_metadata=None
            )
            session.add(test_session)
            await session.commit()
        
        # Verify it stored correctly
        async with async_test_session_factory() as session:
            from sqlmodel import select
            
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            
            assert alert_session.pause_metadata is None
    
    @pytest.mark.asyncio
    async def test_pause_metadata_cleared_on_resume(
        self, async_test_session_factory
    ) -> None:
        """Test that pause_metadata is cleared when session transitions from PAUSED to IN_PROGRESS."""
        session_id = "cleared-metadata-test"
        
        from sqlmodel import select

        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        
        # Step 1: Create session with PAUSED status and pause_metadata
        pause_meta = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=30,
            message="Paused at iteration 30",
            paused_at_us=1234567890
        )
        
        async with async_test_session_factory() as session:
            test_session = AlertSession(
                session_id=session_id,
                alert_type="kubernetes",
                agent_type="chain:test-chain",
                status=AlertSessionStatus.PAUSED.value,
                started_at_us=now_us(),
                chain_id="test-chain",
                pause_metadata=pause_meta.model_dump(mode='json')
            )
            session.add(test_session)
            await session.commit()
        
        # Verify pause_metadata is set
        async with async_test_session_factory() as session:
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            assert alert_session.pause_metadata is not None
            assert alert_session.pause_metadata["reason"] == "max_iterations_reached"
        
        # Step 2: Update status to IN_PROGRESS (simulating resume) - pause_metadata should be cleared
        async with async_test_session_factory() as session:
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            alert_session.status = AlertSessionStatus.IN_PROGRESS.value
            # Clear pause_metadata when not paused (keep it clean)
            alert_session.pause_metadata = None
            session.add(alert_session)
            await session.commit()
        
        # Step 3: Verify pause_metadata is cleared
        async with async_test_session_factory() as session:
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            assert alert_session.status == AlertSessionStatus.IN_PROGRESS.value
            assert alert_session.pause_metadata is None, \
                "pause_metadata should be cleared when transitioning from PAUSED to IN_PROGRESS"
    
    @pytest.mark.asyncio
    async def test_pause_metadata_cleared_on_completion(
        self, async_test_session_factory
    ) -> None:
        """Test that pause_metadata is cleared when session completes after being paused."""
        session_id = "cleared-on-complete-test"
        
        from sqlmodel import select

        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        
        # Create session with PAUSED status and pause_metadata
        pause_meta = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=30,
            message="Paused at iteration 30",
            paused_at_us=1234567890
        )
        
        async with async_test_session_factory() as session:
            test_session = AlertSession(
                session_id=session_id,
                alert_type="kubernetes",
                agent_type="chain:test-chain",
                status=AlertSessionStatus.PAUSED.value,
                started_at_us=now_us(),
                chain_id="test-chain",
                pause_metadata=pause_meta.model_dump(mode='json')
            )
            session.add(test_session)
            await session.commit()
        
        # Update status to COMPLETED - pause_metadata should be cleared
        async with async_test_session_factory() as session:
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            alert_session.status = AlertSessionStatus.COMPLETED.value
            alert_session.final_analysis = "Analysis completed successfully"
            # Clear pause_metadata when not paused (keep it clean)
            alert_session.pause_metadata = None
            alert_session.completed_at_us = now_us()
            session.add(alert_session)
            await session.commit()
        
        # Verify pause_metadata is cleared
        async with async_test_session_factory() as session:
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            assert alert_session.status == AlertSessionStatus.COMPLETED.value
            assert alert_session.pause_metadata is None, \
                "pause_metadata should be cleared when transitioning from PAUSED to COMPLETED"
            assert alert_session.final_analysis == "Analysis completed successfully"
    
    @pytest.mark.integration
    def test_history_service_clears_pause_metadata_on_resume(
        self, history_service_with_test_db
    ) -> None:
        """Test that history_service.update_session_status clears pause_metadata on resume.
        
        This test exercises the actual service layer logic (not just ORM) to ensure
        the production code path for clearing pause_metadata works correctly.
        """
        from tarsy.models.constants import AlertSessionStatus
        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        
        history_service = history_service_with_test_db
        session_id = "service-test-resume"
        
        # Create a paused session with pause_metadata
        pause_meta = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=30,
            message="Paused for service test",
            paused_at_us=now_us()
        )
        
        with history_service.get_repository() as repo:
            session = AlertSession(
                session_id=session_id,
                alert_type="kubernetes",
                agent_type="chain:test-chain",
                status=AlertSessionStatus.PAUSED.value,
                started_at_us=now_us(),
                chain_id="test-chain",
                pause_metadata=pause_meta.model_dump(mode='json')
            )
            repo.create_alert_session(session)
        
        # Verify initial state
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.pause_metadata is not None
        assert retrieved_session.pause_metadata["reason"] == "max_iterations_reached"
        
        # Resume via history_service.update_session_status
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.IN_PROGRESS.value
        )
        assert success is True
        
        # Verify pause_metadata was cleared by the service
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.IN_PROGRESS.value
        assert retrieved_session.pause_metadata is None, \
            "history_service.update_session_status should clear pause_metadata on resume"
    
    @pytest.mark.integration
    def test_history_service_clears_pause_metadata_on_completion(
        self, history_service_with_test_db
    ) -> None:
        """Test that history_service.update_session_status clears pause_metadata on completion.
        
        This test exercises the actual service layer logic (not just ORM) to ensure
        the production code path for clearing pause_metadata works correctly.
        """
        from tarsy.models.constants import AlertSessionStatus
        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        
        history_service = history_service_with_test_db
        session_id = "service-test-complete"
        
        # Create a paused session with pause_metadata
        pause_meta = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=30,
            message="Paused for service test",
            paused_at_us=now_us()
        )
        
        with history_service.get_repository() as repo:
            session = AlertSession(
                session_id=session_id,
                alert_type="kubernetes",
                agent_type="chain:test-chain",
                status=AlertSessionStatus.PAUSED.value,
                started_at_us=now_us(),
                chain_id="test-chain",
                pause_metadata=pause_meta.model_dump(mode='json')
            )
            repo.create_alert_session(session)
        
        # Verify initial state
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.pause_metadata is not None
        
        # Complete via history_service.update_session_status
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.COMPLETED.value,
            final_analysis="Test completed successfully"
        )
        assert success is True
        
        # Verify pause_metadata was cleared by the service
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.COMPLETED.value
        assert retrieved_session.pause_metadata is None, \
            "history_service.update_session_status should clear pause_metadata on completion"
        assert retrieved_session.final_analysis == "Test completed successfully"
        assert retrieved_session.completed_at_us is not None
    
    @pytest.mark.integration
    def test_history_service_sets_pause_metadata_when_pausing(
        self, history_service_with_test_db
    ) -> None:
        """Test that history_service.update_session_status sets pause_metadata when pausing.
        
        This test verifies the complete pause/resume cycle through the service layer.
        """
        from tarsy.models.constants import AlertSessionStatus
        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        
        history_service = history_service_with_test_db
        session_id = "service-test-pause-cycle"
        
        # Create an in-progress session
        with history_service.get_repository() as repo:
            session = AlertSession(
                session_id=session_id,
                alert_type="kubernetes",
                agent_type="chain:test-chain",
                status=AlertSessionStatus.IN_PROGRESS.value,
                started_at_us=now_us(),
                chain_id="test-chain"
            )
            repo.create_alert_session(session)
        
        # Verify initial state (no pause_metadata)
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.pause_metadata is None
        
        # Pause via history_service with metadata
        pause_meta = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=30,
            message="Service test pause",
            paused_at_us=now_us()
        )
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.PAUSED.value,
            pause_metadata=pause_meta.model_dump(mode='json')
        )
        assert success is True
        
        # Verify pause_metadata was set
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.PAUSED.value
        assert retrieved_session.pause_metadata is not None
        assert retrieved_session.pause_metadata["reason"] == "max_iterations_reached"
        assert retrieved_session.pause_metadata["current_iteration"] == 30
        
        # Resume via history_service
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.IN_PROGRESS.value
        )
        assert success is True
        
        # Verify pause_metadata was cleared on resume
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.IN_PROGRESS.value
        assert retrieved_session.pause_metadata is None, \
            "pause_metadata should be cleared when resuming through service"
    
    @pytest.mark.integration
    def test_multiple_pause_resume_cycles(
        self, history_service_with_test_db
    ) -> None:
        """Test that multiple pause/resume cycles work correctly and clear pause metadata.
        
        Scenario:
        1. Session starts in progress
        2. Pause at iteration 5
        3. Resume to in progress (pause_metadata cleared)
        4. Pause again at iteration 10
        5. Resume to in progress (pause_metadata cleared)
        6. Complete
        
        Verifies:
        - All state transitions work correctly
        - pause_metadata is cleared when not paused
        - Session completes successfully after multiple cycles
        """
        from tarsy.models.constants import AlertSessionStatus
        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        
        history_service = history_service_with_test_db
        session_id = "multi-cycle-test"
        
        # Step 1: Create an in-progress session
        with history_service.get_repository() as repo:
            session = AlertSession(
                session_id=session_id,
                alert_type="kubernetes",
                agent_type="chain:test-chain",
                status=AlertSessionStatus.IN_PROGRESS.value,
                started_at_us=now_us(),
                chain_id="test-chain"
            )
            repo.create_alert_session(session)
        
        # Verify initial state
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.IN_PROGRESS.value
        assert retrieved_session.pause_metadata is None
        
        # Step 2: First pause at iteration 5
        first_pause_meta = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=5,
            message="First pause at iteration 5",
            paused_at_us=now_us()
        )
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.PAUSED.value,
            pause_metadata=first_pause_meta.model_dump(mode='json')
        )
        assert success is True
        
        # Verify first pause
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.PAUSED.value
        assert retrieved_session.pause_metadata is not None
        assert retrieved_session.pause_metadata["current_iteration"] == 5
        
        # Step 3: First resume
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.IN_PROGRESS.value
        )
        assert success is True
        
        # Verify first resume - pause_metadata cleared
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.IN_PROGRESS.value
        assert retrieved_session.pause_metadata is None, \
            "pause_metadata should be cleared after resume"
        
        # Step 4: Second pause at iteration 10 (overwrites first pause metadata)
        second_pause_meta = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=10,
            message="Second pause at iteration 10",
            paused_at_us=now_us()
        )
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.PAUSED.value,
            pause_metadata=second_pause_meta.model_dump(mode='json')
        )
        assert success is True
        
        # Verify second pause - metadata set to iteration 10
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.PAUSED.value
        assert retrieved_session.pause_metadata is not None
        assert retrieved_session.pause_metadata["current_iteration"] == 10, \
            "Second pause should set new pause metadata"
        assert retrieved_session.pause_metadata["message"] == "Second pause at iteration 10"
        
        # Step 5: Second resume
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.IN_PROGRESS.value
        )
        assert success is True
        
        # Verify second resume - pause_metadata cleared
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.IN_PROGRESS.value
        assert retrieved_session.pause_metadata is None, \
            "pause_metadata should be cleared after second resume"
        
        # Step 6: Complete
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.COMPLETED.value,
            final_analysis="Analysis completed after multiple pause/resume cycles"
        )
        assert success is True
        
        # Verify completion - pause_metadata cleared
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.COMPLETED.value
        assert retrieved_session.pause_metadata is None, \
            "pause_metadata should be cleared after completion"
        assert retrieved_session.final_analysis == "Analysis completed after multiple pause/resume cycles"
        assert retrieved_session.completed_at_us is not None
    
    @pytest.mark.integration
    def test_resumed_chain_timeout_persists_error_message(
        self, history_service_with_test_db
    ) -> None:
        """Test that when a resumed chain times out, error message is persisted to database.
        
        This test verifies the fix for the resume path handling of ChainStatus.TIMED_OUT,
        ensuring error messages are consistently persisted in both initial execution and
        resume execution paths.
        
        Scenario:
        1. Session is paused
        2. Resume happens (update to IN_PROGRESS)
        3. Chain execution times out (update to TIMED_OUT with error_message)
        4. Verify error_message is persisted in the database
        """
        from tarsy.models.constants import AlertSessionStatus
        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        
        history_service = history_service_with_test_db
        session_id = "resume-timeout-test"
        
        # Step 1: Create a paused session
        pause_meta = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=30,
            message="Paused at max iterations",
            paused_at_us=now_us()
        )
        
        with history_service.get_repository() as repo:
            session = AlertSession(
                session_id=session_id,
                alert_type="kubernetes",
                agent_type="chain:test-chain",
                status=AlertSessionStatus.PAUSED.value,
                started_at_us=now_us(),
                chain_id="test-chain",
                pause_metadata=pause_meta.model_dump(mode='json')
            )
            repo.create_alert_session(session)
        
        # Verify initial paused state
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.PAUSED.value
        assert retrieved_session.pause_metadata is not None
        assert retrieved_session.error_message is None
        
        # Step 2: Simulate resume (update to IN_PROGRESS, clear pause_metadata)
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.IN_PROGRESS.value
        )
        assert success is True
        
        # Verify resumed state
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.IN_PROGRESS.value
        assert retrieved_session.pause_metadata is None
        
        # Step 3: Chain times out during resumed execution - update to TIMED_OUT with error_message
        timeout_error_message = "Chain execution timed out after resume"
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.TIMED_OUT.value,
            error_message=timeout_error_message
        )
        assert success is True
        
        # Step 4: Verify error_message is persisted in database
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.TIMED_OUT.value
        assert retrieved_session.error_message == timeout_error_message, \
            "Error message should be persisted when chain times out after resume"
        assert retrieved_session.completed_at_us is not None, \
            "Session should be marked as completed when timed out"

