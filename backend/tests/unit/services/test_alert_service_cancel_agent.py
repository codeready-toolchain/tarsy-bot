"""
Unit tests for AlertService.cancel_agent() method.

Tests the per-agent cancellation logic including validation, status aggregation,
session state updates, and event publishing.
"""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tarsy.models.constants import AlertSessionStatus, StageStatus
from tarsy.models.db_models import AlertSession, StageExecution
from tarsy.services.alert_service import AlertService
from tarsy.utils.timestamp import now_us


@asynccontextmanager
async def mock_stage_execution_context(*args, **kwargs):
    """Mock async context manager for stage_execution_context."""
    yield MagicMock()


def create_mock_stage_execution(
    execution_id: str = "stage-exec-1",
    session_id: str = "session-123",
    status: str = StageStatus.PAUSED.value,
    agent: str = "TestAgent",
    parent_stage_execution_id: str | None = "parent-exec-1",
    paused_at_us: int | None = None,
    started_at_us: int | None = None,
    stage_output: dict | None = None,
) -> MagicMock:
    """Create a mock StageExecution object."""
    mock = MagicMock(spec=StageExecution)
    mock.execution_id = execution_id
    mock.session_id = session_id
    mock.status = status
    mock.agent = agent
    mock.parent_stage_execution_id = parent_stage_execution_id
    mock.paused_at_us = paused_at_us or now_us()
    mock.started_at_us = started_at_us or (mock.paused_at_us - 5000000)
    mock.completed_at_us = None
    mock.duration_ms = None
    mock.error_message = None
    mock.stage_name = "test-stage"
    mock.stage_index = 0
    mock.stage_output = stage_output
    return mock


def create_mock_session(
    session_id: str = "session-123",
    status: str = AlertSessionStatus.PAUSED.value,
) -> MagicMock:
    """Create a mock AlertSession object."""
    mock = MagicMock(spec=AlertSession)
    mock.session_id = session_id
    mock.status = status
    mock.completed_at_us = None
    mock.error_message = None
    return mock


@pytest.mark.unit
class TestCancelAgentValidation:
    """Test cancel_agent validation scenarios."""

    @pytest.fixture
    def alert_service(self) -> AlertService:
        """Create AlertService instance with mocked dependencies."""
        mock_settings = MagicMock()
        mock_settings.agent_config_path = None
        mock_settings.slack_bot_token = None
        mock_settings.slack_channel = None
        
        with patch('tarsy.services.alert_service.RunbookService'):
            service = AlertService(settings=mock_settings)
        service.history_service = MagicMock()
        service.session_manager = MagicMock()
        service.parallel_executor = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_cancel_agent_history_service_unavailable(
        self, alert_service: AlertService
    ) -> None:
        """Test cancel_agent raises error when history service unavailable."""
        alert_service.history_service = None

        with pytest.raises(ValueError, match="History service not available"):
            await alert_service.cancel_agent("session-123", "stage-exec-1")

    @pytest.mark.asyncio
    async def test_cancel_agent_session_not_found(
        self, alert_service: AlertService
    ) -> None:
        """Test cancel_agent raises error when session doesn't exist."""
        alert_service.history_service.get_session.return_value = None

        with pytest.raises(ValueError, match="Session .* not found"):
            await alert_service.cancel_agent("nonexistent-session", "stage-exec-1")

    @pytest.mark.asyncio
    async def test_cancel_agent_session_not_paused(
        self, alert_service: AlertService
    ) -> None:
        """Test cancel_agent raises error when session is not paused."""
        mock_session = create_mock_session(status=AlertSessionStatus.IN_PROGRESS.value)
        alert_service.history_service.get_session.return_value = mock_session

        with pytest.raises(ValueError, match="is not paused"):
            await alert_service.cancel_agent("session-123", "stage-exec-1")

    @pytest.mark.asyncio
    async def test_cancel_agent_stage_not_found(
        self, alert_service: AlertService
    ) -> None:
        """Test cancel_agent raises error when stage execution doesn't exist."""
        mock_session = create_mock_session()
        alert_service.history_service.get_session.return_value = mock_session
        alert_service.history_service.get_stage_execution = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="Stage execution .* not found"):
            await alert_service.cancel_agent("session-123", "nonexistent-stage")

    @pytest.mark.asyncio
    async def test_cancel_agent_stage_wrong_session(
        self, alert_service: AlertService
    ) -> None:
        """Test cancel_agent raises error when stage belongs to different session."""
        mock_session = create_mock_session(session_id="session-123")
        alert_service.history_service.get_session.return_value = mock_session

        mock_stage = create_mock_stage_execution(
            execution_id="stage-exec-1",
            session_id="other-session"
        )
        alert_service.history_service.get_stage_execution = AsyncMock(return_value=mock_stage)

        with pytest.raises(ValueError, match="does not belong to session"):
            await alert_service.cancel_agent("session-123", "stage-exec-1")

    @pytest.mark.asyncio
    async def test_cancel_agent_stage_not_child(
        self, alert_service: AlertService
    ) -> None:
        """Test cancel_agent raises error when stage is not a child stage."""
        mock_session = create_mock_session()
        alert_service.history_service.get_session.return_value = mock_session

        mock_stage = create_mock_stage_execution(
            parent_stage_execution_id=None  # Not a child stage
        )
        alert_service.history_service.get_stage_execution = AsyncMock(return_value=mock_stage)

        with pytest.raises(ValueError, match="is not a child stage"):
            await alert_service.cancel_agent("session-123", "stage-exec-1")

    @pytest.mark.asyncio
    async def test_cancel_agent_stage_not_paused(
        self, alert_service: AlertService
    ) -> None:
        """Test cancel_agent raises error when stage is not paused."""
        mock_session = create_mock_session()
        alert_service.history_service.get_session.return_value = mock_session

        mock_stage = create_mock_stage_execution(
            status=StageStatus.COMPLETED.value
        )
        alert_service.history_service.get_stage_execution = AsyncMock(return_value=mock_stage)

        with pytest.raises(ValueError, match="is not paused"):
            await alert_service.cancel_agent("session-123", "stage-exec-1")


@pytest.mark.unit
class TestCancelAgentStatusUpdate:
    """Test cancel_agent status update behavior."""

    @pytest.fixture
    def alert_service(self) -> AlertService:
        """Create AlertService instance with mocked dependencies."""
        mock_settings = MagicMock()
        mock_settings.agent_config_path = None
        mock_settings.slack_bot_token = None
        mock_settings.slack_channel = None
        
        with patch('tarsy.services.alert_service.RunbookService'):
            service = AlertService(settings=mock_settings)
        service.history_service = MagicMock()
        service.session_manager = MagicMock()
        service.parallel_executor = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_cancel_agent_sets_cancelled_status(
        self, alert_service: AlertService
    ) -> None:
        """Test that cancelled agent has CANCELLED status set."""
        # Setup
        mock_session = create_mock_session()
        alert_service.history_service.get_session.return_value = mock_session

        child_stage = create_mock_stage_execution()
        parent_stage = create_mock_stage_execution(
            execution_id="parent-exec-1",
            parent_stage_execution_id=None,
            status=StageStatus.PAUSED.value,
            stage_output={"metadata": {"success_policy": "any"}}
        )

        alert_service.history_service.get_stage_execution = AsyncMock(
            side_effect=[child_stage, parent_stage]
        )
        alert_service.history_service.get_parallel_stage_children = AsyncMock(
            return_value=[child_stage]
        )
        alert_service.history_service.update_stage_execution = AsyncMock()

        # Mock aggregation to return FAILED (all cancelled = failed with ANY policy)
        alert_service.parallel_executor.aggregate_status.return_value = StageStatus.FAILED

        with patch('tarsy.hooks.hook_context.stage_execution_context', mock_stage_execution_context), \
             patch('tarsy.services.events.event_helpers.publish_session_cancelled', new=AsyncMock()), \
             patch('tarsy.services.events.event_helpers.publish_agent_cancelled', new=AsyncMock()):
            await alert_service.cancel_agent("session-123", "stage-exec-1")

        # Verify child stage was updated to CANCELLED
        assert child_stage.status == StageStatus.CANCELLED.value
        assert child_stage.error_message == "Cancelled by user"

    @pytest.mark.asyncio
    async def test_cancel_agent_uses_paused_at_us_for_completed_at(
        self, alert_service: AlertService
    ) -> None:
        """Test that paused_at_us is used as completed_at_us."""
        mock_session = create_mock_session()
        alert_service.history_service.get_session.return_value = mock_session

        paused_timestamp = now_us() - 10000000  # 10 seconds ago
        child_stage = create_mock_stage_execution(paused_at_us=paused_timestamp)
        parent_stage = create_mock_stage_execution(
            execution_id="parent-exec-1",
            parent_stage_execution_id=None,
            stage_output={"metadata": {"success_policy": "any"}}
        )

        alert_service.history_service.get_stage_execution = AsyncMock(
            side_effect=[child_stage, parent_stage]
        )
        alert_service.history_service.get_parallel_stage_children = AsyncMock(
            return_value=[child_stage]
        )
        alert_service.history_service.update_stage_execution = AsyncMock()
        alert_service.parallel_executor.aggregate_status.return_value = StageStatus.FAILED

        with patch('tarsy.hooks.hook_context.stage_execution_context', mock_stage_execution_context), \
             patch('tarsy.services.events.event_helpers.publish_session_cancelled', new=AsyncMock()), \
             patch('tarsy.services.events.event_helpers.publish_agent_cancelled', new=AsyncMock()):
            await alert_service.cancel_agent("session-123", "stage-exec-1")

        # Verify completed_at_us matches paused_at_us
        assert child_stage.completed_at_us == paused_timestamp

    @pytest.mark.asyncio
    async def test_cancel_agent_fallback_when_paused_at_us_is_none(
        self, alert_service: AlertService
    ) -> None:
        """Test that now_us() is used when paused_at_us is None."""
        mock_session = create_mock_session()
        alert_service.history_service.get_session.return_value = mock_session

        child_stage = create_mock_stage_execution(paused_at_us=None)
        parent_stage = create_mock_stage_execution(
            execution_id="parent-exec-1",
            parent_stage_execution_id=None,
            stage_output={"metadata": {"success_policy": "any"}}
        )

        alert_service.history_service.get_stage_execution = AsyncMock(
            side_effect=[child_stage, parent_stage]
        )
        alert_service.history_service.get_parallel_stage_children = AsyncMock(
            return_value=[child_stage]
        )
        alert_service.history_service.update_stage_execution = AsyncMock()
        alert_service.parallel_executor.aggregate_status.return_value = StageStatus.FAILED

        with patch('tarsy.hooks.hook_context.stage_execution_context', mock_stage_execution_context), \
             patch('tarsy.services.events.event_helpers.publish_session_cancelled', new=AsyncMock()), \
             patch('tarsy.services.events.event_helpers.publish_agent_cancelled', new=AsyncMock()):
            await alert_service.cancel_agent("session-123", "stage-exec-1")

        # Verify completed_at_us is set (fallback to now_us() since paused_at_us was None)
        assert child_stage.completed_at_us is not None
        # The completed_at_us should be a recent timestamp (within last second)
        current_time = now_us()
        assert current_time - child_stage.completed_at_us < 1000000  # Within 1 second

    @pytest.mark.asyncio
    async def test_cancel_agent_calculates_duration_correctly(
        self, alert_service: AlertService
    ) -> None:
        """Test that duration is calculated from started_at_us to completed_at_us."""
        mock_session = create_mock_session()
        alert_service.history_service.get_session.return_value = mock_session

        started_at = now_us() - 5000000  # 5 seconds ago
        paused_at = now_us() - 1000000   # 1 second ago
        expected_duration_ms = (paused_at - started_at) // 1000

        child_stage = create_mock_stage_execution(
            started_at_us=started_at,
            paused_at_us=paused_at
        )
        parent_stage = create_mock_stage_execution(
            execution_id="parent-exec-1",
            parent_stage_execution_id=None,
            stage_output={"metadata": {"success_policy": "any"}}
        )

        alert_service.history_service.get_stage_execution = AsyncMock(
            side_effect=[child_stage, parent_stage]
        )
        alert_service.history_service.get_parallel_stage_children = AsyncMock(
            return_value=[child_stage]
        )
        alert_service.history_service.update_stage_execution = AsyncMock()
        alert_service.parallel_executor.aggregate_status.return_value = StageStatus.FAILED

        with patch('tarsy.hooks.hook_context.stage_execution_context', mock_stage_execution_context), \
             patch('tarsy.services.events.event_helpers.publish_session_cancelled', new=AsyncMock()), \
             patch('tarsy.services.events.event_helpers.publish_agent_cancelled', new=AsyncMock()):
            await alert_service.cancel_agent("session-123", "stage-exec-1")

        # Verify duration is calculated correctly
        assert child_stage.duration_ms == expected_duration_ms


@pytest.mark.unit
class TestCancelAgentPolicyEvaluation:
    """Test cancel_agent with different success policies."""

    @pytest.fixture
    def alert_service(self) -> AlertService:
        """Create AlertService instance with mocked dependencies."""
        mock_settings = MagicMock()
        mock_settings.agent_config_path = None
        mock_settings.slack_bot_token = None
        mock_settings.slack_channel = None
        
        with patch('tarsy.services.alert_service.RunbookService'):
            service = AlertService(settings=mock_settings)
        service.history_service = MagicMock()
        service.session_manager = MagicMock()
        service.parallel_executor = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_cancel_agent_with_policy_any_one_completed_triggers_continuation(
        self, alert_service: AlertService
    ) -> None:
        """Test that with policy=ANY and one completed, chain continuation is triggered."""
        mock_session = create_mock_session()
        alert_service.history_service.get_session.return_value = mock_session

        child_stage = create_mock_stage_execution(
            execution_id="stage-exec-1",
            status=StageStatus.PAUSED.value
        )
        completed_sibling = create_mock_stage_execution(
            execution_id="stage-exec-2",
            status=StageStatus.COMPLETED.value
        )
        parent_stage = create_mock_stage_execution(
            execution_id="parent-exec-1",
            parent_stage_execution_id=None,
            status=StageStatus.PAUSED.value,
            stage_output={"metadata": {"success_policy": "any"}}
        )

        alert_service.history_service.get_stage_execution = AsyncMock(
            side_effect=[child_stage, parent_stage]
        )
        alert_service.history_service.get_parallel_stage_children = AsyncMock(
            return_value=[child_stage, completed_sibling]
        )
        alert_service.history_service.update_stage_execution = AsyncMock()

        # With one completed and one cancelled, ANY policy = COMPLETED
        alert_service.parallel_executor.aggregate_status.return_value = StageStatus.COMPLETED

        with patch('tarsy.hooks.hook_context.stage_execution_context', mock_stage_execution_context), \
             patch('tarsy.services.events.event_helpers.publish_session_resumed', new=AsyncMock()) as mock_resumed, \
             patch.object(alert_service, '_continue_after_parallel_completion', new=AsyncMock()):
            result = await alert_service.cancel_agent("session-123", "stage-exec-1")

        # Verify session status changed to IN_PROGRESS
        alert_service.session_manager.update_session_status.assert_called_with(
            "session-123", AlertSessionStatus.IN_PROGRESS.value
        )
        mock_resumed.assert_called_once_with("session-123")

        # Verify response
        assert result.success is True
        assert result.session_status == AlertSessionStatus.IN_PROGRESS.value
        assert result.stage_status == StageStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_cancel_agent_with_policy_any_all_cancelled_results_in_session_cancelled(
        self, alert_service: AlertService
    ) -> None:
        """Test that with policy=ANY and all cancelled, session is CANCELLED."""
        mock_session = create_mock_session()
        alert_service.history_service.get_session.return_value = mock_session

        child_stage = create_mock_stage_execution(
            execution_id="stage-exec-1",
            status=StageStatus.PAUSED.value
        )
        # After cancel, both will be CANCELLED
        cancelled_sibling = create_mock_stage_execution(
            execution_id="stage-exec-2",
            status=StageStatus.CANCELLED.value
        )
        parent_stage = create_mock_stage_execution(
            execution_id="parent-exec-1",
            parent_stage_execution_id=None,
            stage_output={"metadata": {"success_policy": "any"}}
        )

        alert_service.history_service.get_stage_execution = AsyncMock(
            side_effect=[child_stage, parent_stage]
        )
        # Return children with the child_stage status changed to CANCELLED
        alert_service.history_service.get_parallel_stage_children = AsyncMock(
            return_value=[child_stage, cancelled_sibling]
        )
        alert_service.history_service.update_stage_execution = AsyncMock()

        # All cancelled = FAILED
        alert_service.parallel_executor.aggregate_status.return_value = StageStatus.FAILED

        with patch('tarsy.hooks.hook_context.stage_execution_context', mock_stage_execution_context), \
             patch('tarsy.services.events.event_helpers.publish_session_cancelled', new=AsyncMock()) as mock_cancelled, \
             patch('tarsy.services.events.event_helpers.publish_agent_cancelled', new=AsyncMock()):
            result = await alert_service.cancel_agent("session-123", "stage-exec-1")

        # Verify session status is CANCELLED (not FAILED since only cancellations)
        mock_cancelled.assert_called_once_with("session-123")
        assert result.success is True
        assert result.session_status == AlertSessionStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_cancel_agent_with_policy_all_one_cancelled_results_in_session_cancelled(
        self, alert_service: AlertService
    ) -> None:
        """Test that with policy=ALL and cancelled agents (no failures), session is CANCELLED."""
        mock_session = create_mock_session()
        alert_service.history_service.get_session.return_value = mock_session

        child_stage = create_mock_stage_execution(
            execution_id="stage-exec-1",
            status=StageStatus.PAUSED.value
        )
        completed_sibling = create_mock_stage_execution(
            execution_id="stage-exec-2",
            status=StageStatus.COMPLETED.value
        )
        parent_stage = create_mock_stage_execution(
            execution_id="parent-exec-1",
            parent_stage_execution_id=None,
            stage_output={"metadata": {"success_policy": "all"}}
        )

        alert_service.history_service.get_stage_execution = AsyncMock(
            side_effect=[child_stage, parent_stage]
        )
        alert_service.history_service.get_parallel_stage_children = AsyncMock(
            return_value=[child_stage, completed_sibling]
        )
        alert_service.history_service.update_stage_execution = AsyncMock()

        # With ALL policy and one cancelled = FAILED (aggregated status)
        # But session status is CANCELLED since no actual failures, only cancellations
        alert_service.parallel_executor.aggregate_status.return_value = StageStatus.FAILED

        with patch('tarsy.hooks.hook_context.stage_execution_context', mock_stage_execution_context), \
             patch('tarsy.services.events.event_helpers.publish_session_cancelled', new=AsyncMock()) as mock_cancelled, \
             patch('tarsy.services.events.event_helpers.publish_agent_cancelled', new=AsyncMock()):
            result = await alert_service.cancel_agent("session-123", "stage-exec-1")

        # Verify session status is CANCELLED (not FAILED since only cancellations, no actual failures)
        mock_cancelled.assert_called_once_with("session-123")
        assert result.success is True
        assert result.session_status == AlertSessionStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_cancel_agent_with_multiple_paused_stays_paused(
        self, alert_service: AlertService
    ) -> None:
        """Test that with other agents still paused, session stays PAUSED."""
        mock_session = create_mock_session()
        alert_service.history_service.get_session.return_value = mock_session

        child_stage = create_mock_stage_execution(
            execution_id="stage-exec-1",
            status=StageStatus.PAUSED.value
        )
        paused_sibling = create_mock_stage_execution(
            execution_id="stage-exec-2",
            status=StageStatus.PAUSED.value
        )
        parent_stage = create_mock_stage_execution(
            execution_id="parent-exec-1",
            parent_stage_execution_id=None,
            stage_output={"metadata": {"success_policy": "any"}}
        )

        alert_service.history_service.get_stage_execution = AsyncMock(
            side_effect=[child_stage, parent_stage]
        )
        alert_service.history_service.get_parallel_stage_children = AsyncMock(
            return_value=[child_stage, paused_sibling]
        )
        alert_service.history_service.update_stage_execution = AsyncMock()

        # One cancelled, one still paused = PAUSED
        alert_service.parallel_executor.aggregate_status.return_value = StageStatus.PAUSED

        with patch('tarsy.hooks.hook_context.stage_execution_context', mock_stage_execution_context), \
             patch('tarsy.services.events.event_helpers.publish_agent_cancelled', new=AsyncMock()) as mock_agent_cancelled:
            result = await alert_service.cancel_agent("session-123", "stage-exec-1")

        # Verify session status stays PAUSED
        assert result.success is True
        assert result.session_status == AlertSessionStatus.PAUSED.value
        assert result.stage_status == StageStatus.PAUSED.value

        # Verify agent cancelled event was still published
        mock_agent_cancelled.assert_called_once()


@pytest.mark.unit
class TestCancelAgentMixedStatuses:
    """Test cancel_agent with mixed agent statuses."""

    @pytest.fixture
    def alert_service(self) -> AlertService:
        """Create AlertService instance with mocked dependencies."""
        mock_settings = MagicMock()
        mock_settings.agent_config_path = None
        mock_settings.slack_bot_token = None
        mock_settings.slack_channel = None
        
        with patch('tarsy.services.alert_service.RunbookService'):
            service = AlertService(settings=mock_settings)
        service.history_service = MagicMock()
        service.session_manager = MagicMock()
        service.parallel_executor = MagicMock()
        return service

    @pytest.mark.asyncio
    async def test_cancel_agent_mixed_failed_cancelled_results_in_session_failed(
        self, alert_service: AlertService
    ) -> None:
        """Test that mixed failed+cancelled agents results in FAILED session."""
        mock_session = create_mock_session()
        alert_service.history_service.get_session.return_value = mock_session

        child_stage = create_mock_stage_execution(
            execution_id="stage-exec-1",
            status=StageStatus.PAUSED.value
        )
        failed_sibling = create_mock_stage_execution(
            execution_id="stage-exec-2",
            status=StageStatus.FAILED.value
        )
        parent_stage = create_mock_stage_execution(
            execution_id="parent-exec-1",
            parent_stage_execution_id=None,
            stage_output={"metadata": {"success_policy": "any"}}
        )

        alert_service.history_service.get_stage_execution = AsyncMock(
            side_effect=[child_stage, parent_stage]
        )
        alert_service.history_service.get_parallel_stage_children = AsyncMock(
            return_value=[child_stage, failed_sibling]
        )
        alert_service.history_service.update_stage_execution = AsyncMock()

        # All failed/cancelled = FAILED
        alert_service.parallel_executor.aggregate_status.return_value = StageStatus.FAILED

        with patch('tarsy.hooks.hook_context.stage_execution_context', mock_stage_execution_context), \
             patch('tarsy.services.events.event_helpers.publish_session_failed', new=AsyncMock()) as mock_failed, \
             patch('tarsy.services.events.event_helpers.publish_agent_cancelled', new=AsyncMock()):
            result = await alert_service.cancel_agent("session-123", "stage-exec-1")

        # Session should be FAILED (not CANCELLED because there are actual failures)
        mock_failed.assert_called_once_with("session-123")
        assert result.session_status == AlertSessionStatus.FAILED.value

