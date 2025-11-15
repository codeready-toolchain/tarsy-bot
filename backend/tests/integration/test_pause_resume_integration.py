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
            session_channel = f"session:{session_id}"
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
            session_channel = f"session:{session_id}"
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
                select(StageExecution).where(StageExecution.session_id == session_id)
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

