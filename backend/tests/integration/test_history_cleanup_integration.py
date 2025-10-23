"""Integration tests for HistoryCleanupService with real database."""

import pytest

from tarsy.models.db_models import AlertSession, StageExecution
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.models.constants import AlertSessionStatus, StageStatus
from tarsy.services.history_cleanup_service import HistoryCleanupService
from tarsy.repositories.history_repository import HistoryRepository
from tarsy.utils.timestamp import now_us


@pytest.mark.integration
class TestHistoryCleanupServiceIntegration:
    """Integration tests for HistoryCleanupService with real database."""

    def _create_test_session(
        self,
        session,
        session_id: str,
        started_at_us: int,
        status: str = AlertSessionStatus.COMPLETED.value,
    ) -> AlertSession:
        """Helper to create a test session."""
        alert_session = AlertSession(
            session_id=session_id,
            alert_data={"test": "data"},
            agent_type="test-agent",
            alert_type="test-alert",
            status=status,
            started_at_us=started_at_us,
            completed_at_us=started_at_us + 1_000_000,  # 1 second later
            chain_id="test-chain",
        )
        session.add(alert_session)
        return alert_session

    def _create_test_stage(
        self, session, session_id: str, execution_id: str
    ) -> StageExecution:
        """Helper to create a test stage execution."""
        stage = StageExecution(
            execution_id=execution_id,
            session_id=session_id,
            stage_id="test-stage",
            stage_index=0,
            stage_name="Test Stage",
            agent="test-agent",
            status=StageStatus.COMPLETED.value,
        )
        session.add(stage)
        return stage

    def _create_test_llm_interaction(
        self, session, session_id: str, stage_execution_id: str
    ) -> LLMInteraction:
        """Helper to create a test LLM interaction."""
        interaction = LLMInteraction(
            session_id=session_id,
            stage_execution_id=stage_execution_id,
            model_name="test-model",
            provider="test-provider",
        )
        session.add(interaction)
        return interaction

    def _create_test_mcp_interaction(
        self, session, session_id: str, stage_execution_id: str
    ) -> MCPInteraction:
        """Helper to create a test MCP interaction."""
        interaction = MCPInteraction(
            session_id=session_id,
            stage_execution_id=stage_execution_id,
            step_description="Test MCP call",
            server_name="test-server",
            communication_type="tool_call",
            tool_name="test-tool",
        )
        session.add(interaction)
        return interaction

    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_sessions(self, test_session_factory):
        """Test that cleanup deletes sessions older than retention period."""
        # Create old session (100 days ago)
        old_timestamp = now_us() - (100 * 24 * 3600 * 1_000_000)

        with test_session_factory() as session:
            self._create_test_session(session, "old-session-1", old_timestamp)
            session.commit()

        # Create recent session (30 days ago)
        recent_timestamp = now_us() - (30 * 24 * 3600 * 1_000_000)

        with test_session_factory() as session:
            self._create_test_session(session, "recent-session-1", recent_timestamp)
            session.commit()

        # Run cleanup with 90 day retention
        service = HistoryCleanupService(
            test_session_factory, retention_days=90, retention_cleanup_interval_hours=12
        )
        await service._cleanup_old_history()

        # Verify old session was deleted, recent session remains
        with test_session_factory() as session:
            repo = HistoryRepository(session)
            remaining_session = repo.get_alert_session("old-session-1")
            assert remaining_session is None

            recent_still_exists = repo.get_alert_session("recent-session-1")
            assert recent_still_exists is not None

    @pytest.mark.asyncio
    async def test_cleanup_respects_retention_period(self, test_session_factory):
        """Test cleanup respects custom retention period."""
        # Create session 40 days ago
        timestamp_40d = now_us() - (40 * 24 * 3600 * 1_000_000)

        with test_session_factory() as session:
            self._create_test_session(session, "session-40d", timestamp_40d)
            session.commit()

        # Create session 20 days ago
        timestamp_20d = now_us() - (20 * 24 * 3600 * 1_000_000)

        with test_session_factory() as session:
            self._create_test_session(session, "session-20d", timestamp_20d)
            session.commit()

        # Run cleanup with 30 day retention
        service = HistoryCleanupService(
            test_session_factory, retention_days=30, retention_cleanup_interval_hours=12
        )
        await service._cleanup_old_history()

        # Verify 40-day-old session deleted, 20-day-old remains
        with test_session_factory() as session:
            repo = HistoryRepository(session)
            session_40d_result = repo.get_alert_session("session-40d")
            assert session_40d_result is None

            session_20d_result = repo.get_alert_session("session-20d")
            assert session_20d_result is not None

    @pytest.mark.asyncio
    async def test_cleanup_deletes_all_statuses(self, test_session_factory):
        """Test cleanup deletes sessions regardless of status."""
        old_timestamp = now_us() - (100 * 24 * 3600 * 1_000_000)

        # Create sessions with different statuses
        with test_session_factory() as session:
            self._create_test_session(
                session, "completed-old", old_timestamp, AlertSessionStatus.COMPLETED.value
            )
            self._create_test_session(
                session, "failed-old", old_timestamp, AlertSessionStatus.FAILED.value
            )
            self._create_test_session(
                session,
                "in-progress-old",
                old_timestamp,
                AlertSessionStatus.IN_PROGRESS.value,
            )
            self._create_test_session(
                session, "pending-old", old_timestamp, AlertSessionStatus.PENDING.value
            )
            session.commit()

        # Run cleanup
        service = HistoryCleanupService(
            test_session_factory, retention_days=90, retention_cleanup_interval_hours=12
        )
        await service._cleanup_old_history()

        # Verify all old sessions were deleted regardless of status
        with test_session_factory() as session:
            repo = HistoryRepository(session)
            assert repo.get_alert_session("completed-old") is None
            assert repo.get_alert_session("failed-old") is None
            assert repo.get_alert_session("in-progress-old") is None
            assert repo.get_alert_session("pending-old") is None

    @pytest.mark.asyncio
    async def test_cascade_deletes_related_records(self, test_session_factory):
        """Test that CASCADE deletes remove related stages and interactions."""
        old_timestamp = now_us() - (100 * 24 * 3600 * 1_000_000)

        # Create session with related records
        with test_session_factory() as session:
            self._create_test_session(session, "cascade-test-session", old_timestamp)
            self._create_test_stage(session, "cascade-test-session", "cascade-test-stage")
            llm_interaction = self._create_test_llm_interaction(
                session, "cascade-test-session", "cascade-test-stage"
            )
            mcp_interaction = self._create_test_mcp_interaction(
                session, "cascade-test-session", "cascade-test-stage"
            )
            session.commit()

            # Get IDs for verification
            llm_interaction_id = llm_interaction.interaction_id
            mcp_interaction_id = mcp_interaction.communication_id

        # Run cleanup
        service = HistoryCleanupService(
            test_session_factory, retention_days=90, retention_cleanup_interval_hours=12
        )
        await service._cleanup_old_history()

        # Verify session and all related records were deleted
        with test_session_factory() as session:
            repo = HistoryRepository(session)

            # Check session deleted
            assert repo.get_alert_session("cascade-test-session") is None

            # Check stage deleted
            assert repo.get_stage_execution("cascade-test-stage") is None

            # Check LLM interaction deleted
            from sqlmodel import select

            llm_stmt = select(LLMInteraction).where(
                LLMInteraction.interaction_id == llm_interaction_id
            )
            llm_result = session.exec(llm_stmt).first()
            assert llm_result is None

            # Check MCP interaction deleted
            mcp_stmt = select(MCPInteraction).where(
                MCPInteraction.communication_id == mcp_interaction_id
            )
            mcp_result = session.exec(mcp_stmt).first()
            assert mcp_result is None

    @pytest.mark.asyncio
    async def test_cleanup_with_no_old_sessions(self, test_session_factory):
        """Test cleanup when no sessions need to be deleted."""
        # Create only recent sessions
        recent_timestamp = now_us() - (10 * 24 * 3600 * 1_000_000)

        with test_session_factory() as session:
            self._create_test_session(session, "recent-1", recent_timestamp)
            self._create_test_session(session, "recent-2", recent_timestamp)
            session.commit()

        # Run cleanup
        service = HistoryCleanupService(
            test_session_factory, retention_days=90, retention_cleanup_interval_hours=12
        )
        deleted_count = await service._cleanup_old_history()

        # Verify no sessions were deleted
        assert deleted_count == 0

        with test_session_factory() as session:
            repo = HistoryRepository(session)
            assert repo.get_alert_session("recent-1") is not None
            assert repo.get_alert_session("recent-2") is not None

    @pytest.mark.asyncio
    async def test_cleanup_returns_correct_count(self, test_session_factory):
        """Test cleanup returns accurate count of deleted sessions."""
        old_timestamp = now_us() - (100 * 24 * 3600 * 1_000_000)

        # Create 3 old sessions
        with test_session_factory() as session:
            for i in range(3):
                self._create_test_session(session, f"old-session-{i}", old_timestamp)
            session.commit()

        # Create 2 recent sessions
        recent_timestamp = now_us() - (10 * 24 * 3600 * 1_000_000)

        with test_session_factory() as session:
            for i in range(2):
                self._create_test_session(
                    session, f"recent-session-{i}", recent_timestamp
                )
            session.commit()

        # Run cleanup
        service = HistoryCleanupService(
            test_session_factory, retention_days=90, retention_cleanup_interval_hours=12
        )
        deleted_count = await service._cleanup_old_history()

        # Verify correct count returned
        assert deleted_count == 3

    @pytest.mark.asyncio
    async def test_cleanup_service_start_and_stop(self, test_session_factory):
        """Test that cleanup service can start and stop cleanly."""
        service = HistoryCleanupService(
            test_session_factory, retention_days=90, retention_cleanup_interval_hours=12
        )

        # Start service
        await service.start()
        assert service.running is True
        assert service.cleanup_task is not None

        # Stop service
        await service.stop()
        assert service.running is False
        assert service.cleanup_task.done()

    @pytest.mark.asyncio
    async def test_dual_cleanup_methods_exist_and_callable(self, test_session_factory):
        """Test that dual-cleanup methods exist and can be called."""
        # Create service with both cleanup configurations
        service = HistoryCleanupService(
            test_session_factory,
            retention_days=90,
            retention_cleanup_interval_hours=12,
            orphaned_timeout_minutes=30,
            orphaned_check_interval_minutes=10,
        )

        # Verify the service has the new attributes
        assert hasattr(service, "orphaned_timeout_minutes")
        assert hasattr(service, "orphaned_check_interval_minutes")
        assert hasattr(service, "last_retention_cleanup_time")
        
        # Verify methods exist
        assert hasattr(service, "_cleanup_orphaned_sessions")
        assert hasattr(service, "_should_run_retention_cleanup")
        assert hasattr(service, "_update_last_retention_cleanup")

        # Verify initial state
        assert service.orphaned_timeout_minutes == 30
        assert service.orphaned_check_interval_minutes == 10
        assert service.last_retention_cleanup_time == 0.0

    def test_retention_cleanup_timing_integration(self, test_session_factory):
        """Test retention cleanup timing logic with real time values."""
        import time
        
        service = HistoryCleanupService(
            test_session_factory,
            retention_cleanup_interval_hours=1,  # 1 hour for faster testing
        )

        # Initially should run (time = 0)
        assert service._should_run_retention_cleanup()

        # Update time
        service._update_last_retention_cleanup()
        first_time = service.last_retention_cleanup_time
        assert first_time > 0

        # Immediately after, should NOT run (less than 1 hour)
        assert not service._should_run_retention_cleanup()

        # Simulate time passage (set to 2 hours ago)
        service.last_retention_cleanup_time = time.time() - (2 * 3600)
        
        # Now should run again
        assert service._should_run_retention_cleanup()

    @pytest.mark.asyncio
    async def test_service_initialization_with_dual_cleanup_config(self, test_session_factory):
        """Test service can be initialized with full dual-cleanup configuration."""
        service = HistoryCleanupService(
            test_session_factory,
            retention_days=30,
            retention_cleanup_interval_hours=6,
            orphaned_timeout_minutes=15,
            orphaned_check_interval_minutes=5,
        )

        # Verify all parameters were set correctly
        assert service.retention_days == 30
        assert service.retention_cleanup_interval_hours == 6
        assert service.orphaned_timeout_minutes == 15
        assert service.orphaned_check_interval_minutes == 5

        # Start and stop to verify lifecycle
        await service.start()
        assert service.running
        await service.stop()
        assert not service.running

