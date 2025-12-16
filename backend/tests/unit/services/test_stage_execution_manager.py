"""
Unit tests for StageExecutionManager.

Tests the stage execution lifecycle management including creation,
status transitions, and hook triggering.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.constants import ParallelType, StageStatus
from tarsy.services.stage_execution_manager import StageExecutionManager
from tarsy.utils.timestamp import now_us


@pytest.mark.unit
class TestStageExecutionManagerInitialization:
    """Test StageExecutionManager initialization."""
    
    def test_initialization_with_history_service(self):
        """Test that StageExecutionManager initializes with history service."""
        history_service = Mock()
        
        manager = StageExecutionManager(history_service=history_service)
        
        assert manager.history_service == history_service


@pytest.mark.unit
class TestCreateStageExecution:
    """Test stage execution creation."""
    
    @pytest.mark.asyncio
    async def test_create_stage_execution_success(self):
        """Test creating a stage execution record successfully."""
        history_service = Mock()
        # Mock get_stage_execution to return a stage execution object for verification
        history_service.get_stage_execution = AsyncMock(
            return_value=Mock(execution_id="exec-123")
        )
        
        manager = StageExecutionManager(history_service=history_service)
        
        stage = SimpleNamespace(name="test-stage", agent="TestAgent")
        
        with patch('tarsy.hooks.hook_context.stage_execution_context') as mock_context:
            # Mock the context manager to set execution_id on the model
            async def mock_aenter(self):
                return Mock()
            
            async def mock_aexit(self, exc_type, exc_val, exc_tb):
                return None
            
            def mock_context_fn(stage_execution):
                stage_execution.execution_id = "exec-123"
                mock_cm = Mock()
                mock_cm.__aenter__ = mock_aenter
                mock_cm.__aexit__ = mock_aexit
                return mock_cm
            
            mock_context.side_effect = mock_context_fn
            
            execution_id = await manager.create_stage_execution(
                session_id="session-1",
                stage=stage,
                stage_index=0
            )
            
            assert execution_id == "exec-123"
    
    @pytest.mark.asyncio
    async def test_create_stage_execution_with_parallel_params(self):
        """Test creating a child stage execution with parallel parameters."""
        history_service = Mock()
        # Mock get_stage_execution to return a stage execution object for verification
        history_service.get_stage_execution = AsyncMock(
            return_value=Mock(execution_id="child-exec-1")
        )
        
        manager = StageExecutionManager(history_service=history_service)
        
        stage = SimpleNamespace(name="child-stage", agent="TestAgent")
        
        with patch('tarsy.hooks.hook_context.stage_execution_context') as mock_context:
            async def mock_aenter(self):
                return Mock()
            
            async def mock_aexit(self, exc_type, exc_val, exc_tb):
                return None
            
            def mock_context_fn(stage_execution):
                stage_execution.execution_id = "child-exec-1"
                # Verify parallel parameters were set correctly
                assert stage_execution.parent_stage_execution_id == "parent-exec-1"
                assert stage_execution.parallel_index == 2
                assert stage_execution.parallel_type == ParallelType.MULTI_AGENT.value
                mock_cm = Mock()
                mock_cm.__aenter__ = mock_aenter
                mock_cm.__aexit__ = mock_aexit
                return mock_cm
            
            mock_context.side_effect = mock_context_fn
            
            execution_id = await manager.create_stage_execution(
                session_id="session-1",
                stage=stage,
                stage_index=1,
                parent_stage_execution_id="parent-exec-1",
                parallel_index=2,
                parallel_type=ParallelType.MULTI_AGENT.value
            )
            
            assert execution_id == "child-exec-1"
    
    @pytest.mark.asyncio
    async def test_create_stage_execution_fails_when_history_disabled(self):
        """Test that creating stage execution fails when history is disabled."""
        history_service = Mock()
        
        manager = StageExecutionManager(history_service=history_service)
        
        stage = SimpleNamespace(name="test-stage", agent="TestAgent")
        
        with pytest.raises(RuntimeError, match="History service is unavailable"):
            await manager.create_stage_execution(
                session_id="session-1",
                stage=stage,
                stage_index=0
            )


@pytest.mark.unit
class TestUpdateStageExecutionStarted:
    """Test updating stage execution to started status."""
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_started(self):
        """Test transitioning stage to ACTIVE status."""
        history_service = Mock()
        history_service.get_stage_execution = AsyncMock(
            return_value=SimpleNamespace(
                session_id="session-1",
                stage_index=0,
                stage_id="stage-id",
                status=StageStatus.PENDING.value,
                started_at_us=None
            )
        )
        
        manager = StageExecutionManager(history_service=history_service)
        
        with patch('tarsy.hooks.hook_context.stage_execution_context') as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock()
            mock_context.return_value.__aexit__ = AsyncMock()
            
            await manager.update_stage_execution_started("exec-123")
            
            # Verify stage execution was fetched
            history_service.get_stage_execution.assert_called_once_with("exec-123")
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_started_clears_iteration(self):
        """Test that starting a stage clears current_iteration."""
        stage_exec = SimpleNamespace(
            session_id="session-1",
            stage_index=0,
            stage_id="stage-id",
            status=StageStatus.PAUSED.value,
            started_at_us=None,
            current_iteration=5
        )
        
        history_service = Mock()
        history_service.get_stage_execution = AsyncMock(return_value=stage_exec)
        
        manager = StageExecutionManager(history_service=history_service)
        
        with patch('tarsy.hooks.hook_context.stage_execution_context') as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock()
            mock_context.return_value.__aexit__ = AsyncMock()
            
            await manager.update_stage_execution_started("exec-123")
            
            # Verify current_iteration was cleared
            assert stage_exec.current_iteration is None
            assert stage_exec.status == StageStatus.ACTIVE.value
            # started_at_us should be set since it was None
            assert stage_exec.started_at_us is not None
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_started_preserves_start_time_on_resume(self):
        """Test that resuming a paused stage preserves original started_at_us."""
        original_start_time = 1000000
        stage_exec = SimpleNamespace(
            session_id="session-1",
            stage_index=0,
            stage_id="stage-id",
            status=StageStatus.PAUSED.value,
            started_at_us=original_start_time,
            current_iteration=5
        )
        
        history_service = Mock()
        history_service.get_stage_execution = AsyncMock(return_value=stage_exec)
        
        manager = StageExecutionManager(history_service=history_service)
        
        with patch('tarsy.hooks.hook_context.stage_execution_context') as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock()
            mock_context.return_value.__aexit__ = AsyncMock()
            
            await manager.update_stage_execution_started("exec-123")
            
            # Verify started_at_us was preserved (not overwritten)
            assert stage_exec.started_at_us == original_start_time
            assert stage_exec.status == StageStatus.ACTIVE.value
            assert stage_exec.current_iteration is None
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_started_sets_start_time_for_pending(self):
        """Test that starting a pending stage sets started_at_us."""
        stage_exec = SimpleNamespace(
            session_id="session-1",
            stage_index=0,
            stage_id="stage-id",
            status=StageStatus.PENDING.value,
            started_at_us=None,
            current_iteration=None
        )
        
        history_service = Mock()
        history_service.get_stage_execution = AsyncMock(return_value=stage_exec)
        
        manager = StageExecutionManager(history_service=history_service)
        
        with patch('tarsy.hooks.hook_context.stage_execution_context') as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock()
            mock_context.return_value.__aexit__ = AsyncMock()
            
            await manager.update_stage_execution_started("exec-123")
            
            # Verify started_at_us was set for new stage
            assert stage_exec.started_at_us is not None
            assert stage_exec.status == StageStatus.ACTIVE.value
            assert stage_exec.current_iteration is None
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_started_fails_when_history_disabled(self):
        """Test that update fails when history service is disabled."""
        history_service = None
        
        manager = StageExecutionManager(history_service=history_service)
        
        with pytest.raises(RuntimeError, match="History service is unavailable"):
            await manager.update_stage_execution_started("exec-123")
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_started_fails_when_not_found(self):
        """Test that update fails when stage execution is not found."""
        history_service = Mock()
        history_service.get_stage_execution = AsyncMock(return_value=None)
        
        manager = StageExecutionManager(history_service=history_service)
        
        with pytest.raises(RuntimeError, match="not found in database"):
            await manager.update_stage_execution_started("exec-123")


@pytest.mark.unit
class TestUpdateStageExecutionCompleted:
    """Test updating stage execution to completed status."""
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_completed(self):
        """Test marking stage as completed with result."""
        stage_exec = SimpleNamespace(
            session_id="session-1",
            stage_index=0,
            stage_id="stage-id",
            status=StageStatus.ACTIVE.value,
            started_at_us=1000000,
            completed_at_us=None,
            duration_ms=None
        )
        
        history_service = Mock()
        history_service.get_stage_execution = AsyncMock(return_value=stage_exec)
        
        manager = StageExecutionManager(history_service=history_service)
        
        result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="TestAgent",
            stage_name="test-stage",
            timestamp_us=2000000,
            result_summary="Test completed",
            error_message=None
        )
        
        with patch('tarsy.hooks.hook_context.stage_execution_context') as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock()
            mock_context.return_value.__aexit__ = AsyncMock()
            
            await manager.update_stage_execution_completed("exec-123", result)
            
            # Verify stage was updated correctly
            assert stage_exec.status == StageStatus.COMPLETED.value
            assert stage_exec.completed_at_us == result.timestamp_us
            assert stage_exec.error_message is None
            assert stage_exec.duration_ms == 1000  # (2000000 - 1000000) / 1000
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_completed_fails_when_history_disabled(self):
        """Test that update fails when history service is disabled."""
        history_service = None
        
        manager = StageExecutionManager(history_service=history_service)
        
        result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="TestAgent",
            stage_name="test-stage",
            timestamp_us=2000000,
            result_summary="Test completed",
            error_message=None
        )
        
        with pytest.raises(RuntimeError, match="History service is unavailable"):
            await manager.update_stage_execution_completed("exec-123", result)
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_completed_fails_when_not_found(self):
        """Test that update fails when stage execution is not found."""
        history_service = Mock()
        history_service.get_stage_execution = AsyncMock(return_value=None)
        
        manager = StageExecutionManager(history_service=history_service)
        
        result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="TestAgent",
            stage_name="test-stage",
            timestamp_us=2000000,
            result_summary="Test completed",
            error_message=None
        )
        
        with pytest.raises(RuntimeError, match="not found in database"):
            await manager.update_stage_execution_completed("exec-123", result)


@pytest.mark.unit
class TestUpdateStageExecutionFailed:
    """Test updating stage execution to failed status."""
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_failed(self):
        """Test marking stage as failed with error message."""
        stage_exec = SimpleNamespace(
            session_id="session-1",
            stage_index=0,
            stage_id="stage-id",
            status=StageStatus.ACTIVE.value,
            started_at_us=1000000,
            completed_at_us=None,
            duration_ms=None
        )
        
        history_service = Mock()
        history_service.get_stage_execution = AsyncMock(return_value=stage_exec)
        
        manager = StageExecutionManager(history_service=history_service)
        
        with patch('tarsy.hooks.hook_context.stage_execution_context') as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock()
            mock_context.return_value.__aexit__ = AsyncMock()
            
            await manager.update_stage_execution_failed("exec-123", "Test error")
            
            # Verify stage was marked as failed
            assert stage_exec.status == StageStatus.FAILED.value
            assert stage_exec.error_message == "Test error"
            assert stage_exec.stage_output is None
            assert stage_exec.completed_at_us is not None
            assert stage_exec.duration_ms is not None
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_failed_fails_when_history_disabled(self):
        """Test that update fails when history service is disabled."""
        history_service = None
        
        manager = StageExecutionManager(history_service=history_service)
        
        with pytest.raises(RuntimeError, match="History service is unavailable"):
            await manager.update_stage_execution_failed("exec-123", "Test error")
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_failed_fails_when_not_found(self):
        """Test that update fails when stage execution is not found."""
        history_service = Mock()
        history_service.get_stage_execution = AsyncMock(return_value=None)
        
        manager = StageExecutionManager(history_service=history_service)
        
        with pytest.raises(RuntimeError, match="not found in database"):
            await manager.update_stage_execution_failed("exec-123", "Test error")


@pytest.mark.unit
class TestUpdateStageExecutionPaused:
    """Test updating stage execution to paused status."""
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_paused(self):
        """Test marking stage as paused with iteration count."""
        stage_exec = SimpleNamespace(
            session_id="session-1",
            stage_index=0,
            stage_id="stage-id",
            stage_name="test-stage",
            status=StageStatus.ACTIVE.value,
            started_at_us=1000000,
            completed_at_us=None,
            current_iteration=None
        )
        
        history_service = Mock()
        history_service.get_stage_execution = AsyncMock(return_value=stage_exec)
        
        manager = StageExecutionManager(history_service=history_service)
        
        paused_result = AgentExecutionResult(
            status=StageStatus.PAUSED,
            agent_name="TestAgent",
            stage_name="test-stage",
            timestamp_us=now_us(),
            result_summary="Paused at iteration 5",
            paused_conversation_state={"messages": []},
            error_message=None
        )
        
        with patch('tarsy.hooks.hook_context.stage_execution_context') as mock_context:
            mock_context.return_value.__aenter__ = AsyncMock()
            mock_context.return_value.__aexit__ = AsyncMock()
            
            await manager.update_stage_execution_paused("exec-123", 5, paused_result)
            
            # Verify stage was marked as paused
            assert stage_exec.status == StageStatus.PAUSED.value
            assert stage_exec.current_iteration == 5
            assert stage_exec.stage_output is not None
            assert stage_exec.completed_at_us is None  # Not completed yet
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_paused_fails_when_history_disabled(self):
        """Test that update fails when history service is disabled."""
        history_service = None
        
        manager = StageExecutionManager(history_service=history_service)
        
        paused_result = AgentExecutionResult(
            status=StageStatus.PAUSED,
            agent_name="TestAgent",
            stage_name="test-stage",
            timestamp_us=now_us(),
            result_summary="Paused at iteration 5",
            paused_conversation_state={"messages": []},
            error_message=None
        )
        
        with pytest.raises(RuntimeError, match="History service is unavailable"):
            await manager.update_stage_execution_paused("exec-123", 5, paused_result)
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_paused_fails_when_not_found(self):
        """Test that update fails when stage execution is not found."""
        history_service = Mock()
        history_service.get_stage_execution = AsyncMock(return_value=None)
        
        manager = StageExecutionManager(history_service=history_service)
        
        paused_result = AgentExecutionResult(
            status=StageStatus.PAUSED,
            agent_name="TestAgent",
            stage_name="test-stage",
            timestamp_us=now_us(),
            result_summary="Paused at iteration 5",
            paused_conversation_state={"messages": []},
            error_message=None
        )
        
        with pytest.raises(RuntimeError, match="not found in database"):
            await manager.update_stage_execution_paused("exec-123", 5, paused_result)


@pytest.mark.unit
class TestUpdateSessionCurrentStage:
    """Test updating session's current stage."""
    
    @pytest.mark.asyncio
    async def test_update_session_current_stage(self):
        """Test updating current stage information for a session."""
        history_service = Mock()
        history_service.update_session_current_stage = AsyncMock()
        
        manager = StageExecutionManager(history_service=history_service)
        
        await manager.update_session_current_stage("session-1", 2, "exec-456")
        
        history_service.update_session_current_stage.assert_called_once_with(
            session_id="session-1",
            current_stage_index=2,
            current_stage_id="exec-456"
        )
    
    @pytest.mark.asyncio
    async def test_update_session_current_stage_disabled_history(self):
        """Test that update fails when history is disabled."""
        history_service = Mock()
        
        manager = StageExecutionManager(history_service=history_service)
        
        # Should raise RuntimeError when history is disabled
        with pytest.raises(RuntimeError, match="History service is unavailable"):
            await manager.update_session_current_stage("session-1", 2, "exec-456")

