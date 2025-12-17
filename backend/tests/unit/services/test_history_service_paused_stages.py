"""
Unit tests for HistoryService paused stages methods.

Tests get_paused_stages() and cancel_all_paused_stages() methods.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.models.constants import StageStatus
from tarsy.models.db_models import StageExecution
from tarsy.services.history_service import HistoryService
from tarsy.utils.timestamp import now_us


def create_mock_stage_execution(
    execution_id: str = "stage-exec-1",
    session_id: str = "session-123",
    status: str = StageStatus.PAUSED.value,
    agent: str = "TestAgent",
    paused_at_us: int | None = None,
    started_at_us: int | None = None,
) -> StageExecution:
    """Create a StageExecution instance for testing."""
    current_time = now_us()
    return StageExecution(
        execution_id=execution_id,
        session_id=session_id,
        stage_id="stage-1",
        stage_index=0,
        stage_name="test-stage",
        agent=agent,
        status=status,
        started_at_us=started_at_us or (current_time - 5000000),
        paused_at_us=paused_at_us or current_time,
        completed_at_us=None,
        duration_ms=None,
        error_message=None,
    )


@pytest.mark.unit
class TestGetPausedStages:
    """Test suite for HistoryService.get_paused_stages()."""

    @pytest.fixture
    def mock_settings(self, isolated_test_settings):
        """Create mock settings for testing."""
        return isolated_test_settings

    @pytest.fixture
    def history_service(self, mock_settings):
        """Create HistoryService instance with mocked dependencies."""
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            service._initialization_attempted = True
            service._is_healthy = True
            return service

    @pytest.mark.asyncio
    async def test_get_paused_stages_returns_only_paused(
        self, history_service: HistoryService
    ) -> None:
        """Test that get_paused_stages returns only stages with PAUSED status."""
        session_id = "test-session-123"
        
        paused_stage = create_mock_stage_execution(
            execution_id="paused-1",
            session_id=session_id,
            status=StageStatus.PAUSED.value
        )
        completed_stage = create_mock_stage_execution(
            execution_id="completed-1",
            session_id=session_id,
            status=StageStatus.COMPLETED.value
        )
        failed_stage = create_mock_stage_execution(
            execution_id="failed-1",
            session_id=session_id,
            status=StageStatus.FAILED.value
        )
        
        mock_repo = Mock()
        mock_repo.get_stage_executions_for_session.return_value = [
            paused_stage, completed_stage, failed_stage
        ]
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo
            
            result = await history_service.get_paused_stages(session_id)
        
        assert len(result) == 1
        assert result[0].execution_id == "paused-1"
        assert result[0].status == StageStatus.PAUSED.value

    @pytest.mark.asyncio
    async def test_get_paused_stages_returns_empty_when_none_paused(
        self, history_service: HistoryService
    ) -> None:
        """Test that get_paused_stages returns empty list when no paused stages."""
        session_id = "test-session-123"
        
        completed_stage = create_mock_stage_execution(
            execution_id="completed-1",
            status=StageStatus.COMPLETED.value
        )
        failed_stage = create_mock_stage_execution(
            execution_id="failed-1",
            status=StageStatus.FAILED.value
        )
        
        mock_repo = Mock()
        mock_repo.get_stage_executions_for_session.return_value = [
            completed_stage, failed_stage
        ]
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo
            
            result = await history_service.get_paused_stages(session_id)
        
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_paused_stages_returns_multiple_paused(
        self, history_service: HistoryService
    ) -> None:
        """Test that get_paused_stages returns all paused stages."""
        session_id = "test-session-123"
        
        paused_stage1 = create_mock_stage_execution(
            execution_id="paused-1",
            status=StageStatus.PAUSED.value
        )
        paused_stage2 = create_mock_stage_execution(
            execution_id="paused-2",
            status=StageStatus.PAUSED.value
        )
        completed_stage = create_mock_stage_execution(
            execution_id="completed-1",
            status=StageStatus.COMPLETED.value
        )
        
        mock_repo = Mock()
        mock_repo.get_stage_executions_for_session.return_value = [
            paused_stage1, paused_stage2, completed_stage
        ]
        
        with patch.object(history_service, 'get_repository') as mock_get_repo:
            mock_get_repo.return_value.__enter__.return_value = mock_repo
            
            result = await history_service.get_paused_stages(session_id)
        
        assert len(result) == 2
        assert all(s.status == StageStatus.PAUSED.value for s in result)


@pytest.mark.unit
class TestCancelAllPausedStages:
    """Test suite for HistoryService.cancel_all_paused_stages()."""

    @pytest.fixture
    def mock_settings(self, isolated_test_settings):
        """Create mock settings for testing."""
        return isolated_test_settings

    @pytest.fixture
    def history_service(self, mock_settings):
        """Create HistoryService instance with mocked dependencies."""
        with patch('tarsy.services.history_service.get_settings', return_value=mock_settings):
            service = HistoryService()
            service._initialization_attempted = True
            service._is_healthy = True
            return service

    @pytest.mark.asyncio
    async def test_cancel_all_paused_stages_updates_status_to_cancelled(
        self, history_service: HistoryService
    ) -> None:
        """Test that cancel_all_paused_stages updates status to CANCELLED."""
        session_id = "test-session-123"
        
        paused_stage = create_mock_stage_execution(
            execution_id="paused-1",
            session_id=session_id,
            status=StageStatus.PAUSED.value
        )
        
        # Mock get_paused_stages to return our paused stage
        history_service.get_paused_stages = AsyncMock(return_value=[paused_stage])
        history_service.update_stage_execution = AsyncMock()
        
        count = await history_service.cancel_all_paused_stages(session_id)
        
        assert count == 1
        assert paused_stage.status == StageStatus.CANCELLED.value
        assert paused_stage.error_message == "Cancelled by user"
        history_service.update_stage_execution.assert_called_once_with(paused_stage)

    @pytest.mark.asyncio
    async def test_cancel_all_paused_stages_uses_paused_at_us_for_completed_at(
        self, history_service: HistoryService
    ) -> None:
        """Test that cancel_all_paused_stages uses paused_at_us as completed_at_us."""
        session_id = "test-session-123"
        paused_timestamp = now_us() - 10000000  # 10 seconds ago
        
        paused_stage = create_mock_stage_execution(
            execution_id="paused-1",
            session_id=session_id,
            status=StageStatus.PAUSED.value,
            paused_at_us=paused_timestamp
        )
        
        history_service.get_paused_stages = AsyncMock(return_value=[paused_stage])
        history_service.update_stage_execution = AsyncMock()
        
        await history_service.cancel_all_paused_stages(session_id)
        
        assert paused_stage.completed_at_us == paused_timestamp

    @pytest.mark.asyncio
    async def test_cancel_all_paused_stages_calculates_duration(
        self, history_service: HistoryService
    ) -> None:
        """Test that cancel_all_paused_stages calculates duration correctly."""
        session_id = "test-session-123"
        started_at = now_us() - 5000000  # 5 seconds ago
        paused_at = now_us() - 1000000   # 1 second ago
        expected_duration_ms = (paused_at - started_at) // 1000
        
        paused_stage = create_mock_stage_execution(
            execution_id="paused-1",
            session_id=session_id,
            status=StageStatus.PAUSED.value,
            started_at_us=started_at,
            paused_at_us=paused_at
        )
        
        history_service.get_paused_stages = AsyncMock(return_value=[paused_stage])
        history_service.update_stage_execution = AsyncMock()
        
        await history_service.cancel_all_paused_stages(session_id)
        
        assert paused_stage.duration_ms == expected_duration_ms

    @pytest.mark.asyncio
    async def test_cancel_all_paused_stages_returns_count(
        self, history_service: HistoryService
    ) -> None:
        """Test that cancel_all_paused_stages returns correct count."""
        session_id = "test-session-123"
        
        paused_stages = [
            create_mock_stage_execution(
                execution_id=f"paused-{i}",
                session_id=session_id,
                status=StageStatus.PAUSED.value
            )
            for i in range(3)
        ]
        
        history_service.get_paused_stages = AsyncMock(return_value=paused_stages)
        history_service.update_stage_execution = AsyncMock()
        
        count = await history_service.cancel_all_paused_stages(session_id)
        
        assert count == 3
        assert history_service.update_stage_execution.call_count == 3

    @pytest.mark.asyncio
    async def test_cancel_all_paused_stages_returns_zero_when_no_paused(
        self, history_service: HistoryService
    ) -> None:
        """Test that cancel_all_paused_stages returns 0 when no paused stages."""
        session_id = "test-session-123"
        
        history_service.get_paused_stages = AsyncMock(return_value=[])
        history_service.update_stage_execution = AsyncMock()
        
        count = await history_service.cancel_all_paused_stages(session_id)
        
        assert count == 0
        history_service.update_stage_execution.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_all_paused_stages_fallback_when_paused_at_us_is_none(
        self, history_service: HistoryService
    ) -> None:
        """Test that cancel_all_paused_stages uses current time when paused_at_us is None."""
        session_id = "test-session-123"
        
        paused_stage = create_mock_stage_execution(
            execution_id="paused-1",
            session_id=session_id,
            status=StageStatus.PAUSED.value,
        )
        paused_stage.paused_at_us = None  # Explicitly set to None
        
        history_service.get_paused_stages = AsyncMock(return_value=[paused_stage])
        history_service.update_stage_execution = AsyncMock()
        
        before_cancel = now_us()
        await history_service.cancel_all_paused_stages(session_id)
        after_cancel = now_us()
        
        # Should use a recent timestamp as fallback
        assert paused_stage.completed_at_us is not None
        assert before_cancel <= paused_stage.completed_at_us <= after_cancel

