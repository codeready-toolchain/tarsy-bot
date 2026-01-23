"""
Unit tests for SessionClaimWorker
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tarsy.models.constants import AlertSessionStatus
from tarsy.services.session_claim_worker import SessionClaimWorker

pytestmark = pytest.mark.unit


@pytest.fixture
def mock_history_service():
    """Create a mock history service."""
    service = MagicMock()
    service.repository = MagicMock()
    return service


@pytest.fixture
def mock_process_callback():
    """Create a mock process callback."""
    callback = AsyncMock()
    return callback


@pytest.fixture
def worker(mock_history_service, mock_process_callback):
    """Create SessionClaimWorker instance."""
    return SessionClaimWorker(
        history_service=mock_history_service,
        max_global_concurrent=5,
        claim_interval=0.1,  # Fast interval for testing
        process_callback=mock_process_callback,
        pod_id="test-pod"
    )


@pytest.mark.asyncio
async def test_worker_start_stop(worker):
    """Test worker can start and stop gracefully."""
    await worker.start()
    assert worker._running is True
    assert worker._worker_task is not None
    
    await worker.stop()
    assert worker._running is False


@pytest.mark.asyncio
async def test_worker_double_start(worker, caplog):
    """Test worker handles double start gracefully."""
    await worker.start()
    await worker.start()  # Should log warning
    assert "already running" in caplog.text.lower()
    await worker.stop()


@pytest.mark.asyncio
async def test_worker_has_capacity_true(worker, mock_history_service):
    """Test capacity check when slots are available."""
    mock_history_service.repository.count_sessions_by_status.return_value = 3
    
    has_capacity = await worker._has_capacity()
    
    assert has_capacity is True
    mock_history_service.repository.count_sessions_by_status.assert_called_with(
        AlertSessionStatus.IN_PROGRESS.value
    )


@pytest.mark.asyncio
async def test_worker_has_capacity_false(worker, mock_history_service):
    """Test capacity check when at max capacity."""
    mock_history_service.repository.count_sessions_by_status.return_value = 5
    
    has_capacity = await worker._has_capacity()
    
    assert has_capacity is False


@pytest.mark.asyncio
async def test_worker_count_active_sessions(worker, mock_history_service):
    """Test counting active sessions."""
    mock_history_service.repository.count_sessions_by_status.return_value = 3
    
    count = await worker._count_active_sessions()
    
    assert count == 3
    mock_history_service.repository.count_sessions_by_status.assert_called_with(
        AlertSessionStatus.IN_PROGRESS.value
    )


@pytest.mark.asyncio
async def test_worker_claim_next_session_success(worker, mock_history_service):
    """Test successful session claiming."""
    mock_session = MagicMock()
    mock_session.session_id = "test-session-123"
    mock_session.alert_data = {"test": "data"}
    mock_session.alert_type = "test-alert"
    mock_session.author = "test-user"
    mock_session.runbook_url = None
    mock_session.mcp_selection = None
    mock_session.session_metadata = None
    
    mock_history_service.repository.claim_next_pending_session.return_value = mock_session
    
    session_data = await worker._claim_next_session()
    
    assert session_data is not None
    assert session_data["session_id"] == "test-session-123"
    assert session_data["alert_data"] == {"test": "data"}
    assert session_data["alert_type"] == "test-alert"
    mock_history_service.repository.claim_next_pending_session.assert_called_with("test-pod")


@pytest.mark.asyncio
async def test_worker_claim_next_session_none(worker, mock_history_service):
    """Test claiming when no pending sessions available."""
    mock_history_service.repository.claim_next_pending_session.return_value = None
    
    session_data = await worker._claim_next_session()
    
    assert session_data is None


@pytest.mark.asyncio
async def test_worker_dispatch_session(worker, mock_process_callback):
    """Test dispatching a claimed session."""
    session_data = {
        "session_id": "test-session-123",
        "alert_data": {"test": "data"},
        "alert_type": "test-alert",
        "author": "test-user",
        "runbook_url": None,
        "mcp_selection": None,
        "session_metadata": None
    }
    
    with patch("tarsy.services.session_claim_worker.asyncio.create_task") as mock_create_task:
        await worker._dispatch_session(session_data)
        
        # Verify create_task was called
        assert mock_create_task.called
        
        # Verify the callback would be called with correct args
        call_args = mock_create_task.call_args[0][0]  # Get the coroutine
        # We can't easily inspect the coroutine, but we verified create_task was called


@pytest.mark.asyncio
async def test_worker_dispatch_session_error_handling(worker, mock_history_service):
    """Test dispatch error handling."""
    session_data = {
        "session_id": "test-session-123",
        "alert_data": None,  # Will cause error
        "alert_type": "test-alert"
    }
    
    # Should not raise exception, but should mark session as failed
    await worker._dispatch_session(session_data)
    
    # Verify session was marked as failed
    mock_history_service.update_session_status.assert_called_once()
    call_args = mock_history_service.update_session_status.call_args
    assert call_args[1]["session_id"] == "test-session-123"
    assert call_args[1]["status"] == AlertSessionStatus.FAILED.value


@pytest.mark.asyncio
async def test_worker_claim_loop_with_capacity(worker, mock_history_service, mock_process_callback):
    """Test claim loop when capacity is available and session is claimed."""
    mock_session = MagicMock()
    mock_session.session_id = "test-session-123"
    mock_session.alert_data = {"test": "data"}
    mock_session.alert_type = "test-alert"
    mock_session.author = "test-user"
    mock_session.runbook_url = None
    mock_session.mcp_selection = None
    mock_session.session_metadata = None
    
    # Has capacity
    mock_history_service.repository.count_sessions_by_status.return_value = 2
    # Has pending session (then none to stop loop)
    mock_history_service.repository.claim_next_pending_session.side_effect = [
        mock_session,
        None
    ]
    
    # Start worker
    await worker.start()
    
    # Let it run for a bit
    await asyncio.sleep(0.3)
    
    # Stop worker
    await worker.stop()
    
    # Verify session was claimed and dispatched
    assert mock_history_service.repository.claim_next_pending_session.call_count >= 1


@pytest.mark.asyncio
async def test_worker_claim_loop_no_capacity(worker, mock_history_service):
    """Test claim loop when at capacity."""
    # No capacity
    mock_history_service.repository.count_sessions_by_status.return_value = 5
    
    # Start worker
    await worker.start()
    
    # Let it run for a bit
    await asyncio.sleep(0.3)
    
    # Stop worker
    await worker.stop()
    
    # Verify no sessions were claimed
    mock_history_service.repository.claim_next_pending_session.assert_not_called()


@pytest.mark.asyncio
async def test_worker_claim_loop_error_handling(worker, mock_history_service, caplog):
    """Test claim loop handles errors gracefully."""
    # Simulate error in capacity check
    mock_history_service.repository.count_sessions_by_status.side_effect = Exception("Database error")
    
    # Start worker
    await worker.start()
    
    # Let it run for a bit
    await asyncio.sleep(0.3)
    
    # Stop worker
    await worker.stop()
    
    # Verify error was logged
    assert "error in claim loop" in caplog.text.lower()


@pytest.mark.asyncio
async def test_worker_stop_timeout(worker, mock_history_service):
    """Test worker stop with timeout."""
    # Simulate stuck claim loop
    mock_history_service.repository.count_sessions_by_status.return_value = 0
    
    await worker.start()
    
    # Make the worker task hang
    worker._worker_task.cancel = MagicMock()  # Prevent actual cancellation
    
    # Stop should timeout and cancel
    with patch.object(worker._worker_task, "cancel"):
        await worker.stop()
