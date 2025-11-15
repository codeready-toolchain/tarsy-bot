"""
Integration tests for pause/resume functionality with real database.

Tests the complete pause/resume flow including database operations,
event publishing, and state persistence.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tarsy.models.constants import AlertSessionStatus, StageStatus
from tarsy.models.db_models import AlertSession, StageExecution, SQLModel
from tarsy.repositories.event_repository import EventRepository
from tarsy.services.events.channels import EventChannel
from tarsy.services.events.event_helpers import publish_session_paused, publish_session_resumed
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
    async def test_pause_metadata_preserved_on_resume(
        self, async_test_session_factory
    ) -> None:
        """Test that pause_metadata is preserved when session transitions from PAUSED to IN_PROGRESS (audit trail)."""
        session_id = "preserved-metadata-test"
        
        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        from sqlmodel import select
        
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
        
        # Step 2: Update status to IN_PROGRESS (simulating resume) - pause_metadata should be preserved
        async with async_test_session_factory() as session:
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            alert_session.status = AlertSessionStatus.IN_PROGRESS.value
            # PRESERVE pause_metadata for audit trail (don't set to None)
            # The history_service.update_session_status logic preserves pause_metadata for audit trail
            session.add(alert_session)
            await session.commit()
        
        # Step 3: Verify pause_metadata is preserved for audit trail
        async with async_test_session_factory() as session:
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            assert alert_session.status == AlertSessionStatus.IN_PROGRESS.value
            assert alert_session.pause_metadata is not None, \
                "pause_metadata should be preserved when transitioning from PAUSED to IN_PROGRESS for audit trail"
            assert alert_session.pause_metadata["reason"] == "max_iterations_reached"
    
    @pytest.mark.asyncio
    async def test_pause_metadata_preserved_on_completion(
        self, async_test_session_factory
    ) -> None:
        """Test that pause_metadata is preserved when session completes after being paused (audit trail)."""
        session_id = "preserved-on-complete-test"
        
        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        from sqlmodel import select
        
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
        
        # Update status to COMPLETED - pause_metadata should be preserved for audit trail
        async with async_test_session_factory() as session:
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            alert_session.status = AlertSessionStatus.COMPLETED.value
            alert_session.final_analysis = "Analysis completed successfully"
            # PRESERVE pause_metadata for audit trail (don't set to None)
            # The history_service.update_session_status logic preserves pause_metadata for audit trail
            alert_session.completed_at_us = now_us()
            session.add(alert_session)
            await session.commit()
        
        # Verify pause_metadata is preserved for audit trail
        async with async_test_session_factory() as session:
            result = await session.execute(
                select(AlertSession).where(AlertSession.session_id == session_id)
            )
            alert_session = result.scalar_one()
            assert alert_session.status == AlertSessionStatus.COMPLETED.value
            assert alert_session.pause_metadata is not None, \
                "pause_metadata should be preserved when transitioning from PAUSED to COMPLETED for audit trail"
            assert alert_session.pause_metadata["reason"] == "max_iterations_reached"
            assert alert_session.final_analysis == "Analysis completed successfully"
    
    @pytest.mark.integration
    def test_history_service_preserves_pause_metadata_on_resume(
        self, history_service_with_test_db
    ) -> None:
        """Test that history_service.update_session_status preserves pause_metadata on resume (audit trail).
        
        This test exercises the actual service layer logic (not just ORM) to ensure
        the production code path for preserving pause_metadata works correctly.
        """
        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        from tarsy.models.constants import AlertSessionStatus
        
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
        
        # Verify pause_metadata was preserved by the service for audit trail
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.IN_PROGRESS.value
        assert retrieved_session.pause_metadata is not None, \
            "history_service.update_session_status should preserve pause_metadata on resume for audit trail"
        assert retrieved_session.pause_metadata["reason"] == "max_iterations_reached"
    
    @pytest.mark.integration
    def test_history_service_preserves_pause_metadata_on_completion(
        self, history_service_with_test_db
    ) -> None:
        """Test that history_service.update_session_status preserves pause_metadata on completion (audit trail).
        
        This test exercises the actual service layer logic (not just ORM) to ensure
        the production code path for preserving pause_metadata works correctly.
        """
        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        from tarsy.models.constants import AlertSessionStatus
        
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
        
        # Verify pause_metadata was preserved by the service for audit trail
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.COMPLETED.value
        assert retrieved_session.pause_metadata is not None, \
            "history_service.update_session_status should preserve pause_metadata on completion for audit trail"
        assert retrieved_session.pause_metadata["reason"] == "max_iterations_reached"
        assert retrieved_session.final_analysis == "Test completed successfully"
        assert retrieved_session.completed_at_us is not None
    
    @pytest.mark.integration
    def test_history_service_sets_pause_metadata_when_pausing(
        self, history_service_with_test_db
    ) -> None:
        """Test that history_service.update_session_status sets pause_metadata when pausing.
        
        This test verifies the complete pause/resume cycle through the service layer.
        """
        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        from tarsy.models.constants import AlertSessionStatus
        
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
        
        # Verify pause_metadata was preserved on resume for audit trail
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.IN_PROGRESS.value
        assert retrieved_session.pause_metadata is not None, \
            "pause_metadata should be preserved when resuming through service for audit trail"
        assert retrieved_session.pause_metadata["reason"] == "max_iterations_reached"
        assert retrieved_session.pause_metadata["current_iteration"] == 30
    
    @pytest.mark.integration
    def test_multiple_pause_resume_cycles(
        self, history_service_with_test_db
    ) -> None:
        """Test that multiple pause/resume cycles work correctly and preserve last pause metadata.
        
        Scenario:
        1. Session starts in progress
        2. Pause at iteration 5
        3. Resume to in progress
        4. Pause again at iteration 10
        5. Resume to in progress
        6. Complete
        
        Verifies:
        - All state transitions work correctly
        - pause_metadata shows LAST pause (iteration 10)
        - Session completes successfully after multiple cycles
        """
        from tarsy.models.pause_metadata import PauseMetadata, PauseReason
        from tarsy.models.constants import AlertSessionStatus
        
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
        
        # Verify first resume - pause_metadata preserved
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.IN_PROGRESS.value
        assert retrieved_session.pause_metadata is not None, \
            "pause_metadata should be preserved after resume for audit trail"
        assert retrieved_session.pause_metadata["current_iteration"] == 5
        
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
        
        # Verify second pause - metadata updated to iteration 10
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.PAUSED.value
        assert retrieved_session.pause_metadata is not None
        assert retrieved_session.pause_metadata["current_iteration"] == 10, \
            "Second pause should overwrite first pause metadata"
        assert retrieved_session.pause_metadata["message"] == "Second pause at iteration 10"
        
        # Step 5: Second resume
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.IN_PROGRESS.value
        )
        assert success is True
        
        # Verify second resume - still has pause_metadata from second pause
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.IN_PROGRESS.value
        assert retrieved_session.pause_metadata is not None
        assert retrieved_session.pause_metadata["current_iteration"] == 10, \
            "pause_metadata should show last pause (iteration 10)"
        
        # Step 6: Complete
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.COMPLETED.value,
            final_analysis="Analysis completed after multiple pause/resume cycles"
        )
        assert success is True
        
        # Verify completion - pause_metadata still preserved with LAST pause info
        retrieved_session = history_service.get_session(session_id)
        assert retrieved_session is not None
        assert retrieved_session.status == AlertSessionStatus.COMPLETED.value
        assert retrieved_session.pause_metadata is not None, \
            "pause_metadata should be preserved after completion for audit trail"
        assert retrieved_session.pause_metadata["current_iteration"] == 10, \
            "Final pause_metadata should show last pause (iteration 10), not first (iteration 5)"
        assert retrieved_session.pause_metadata["reason"] == "max_iterations_reached"
        assert retrieved_session.final_analysis == "Analysis completed after multiple pause/resume cycles"
        assert retrieved_session.completed_at_us is not None

