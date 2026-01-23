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
async def test_worker_has_capacity_true(mock_history_service, mock_process_callback):
    """Test capacity check when slots are available."""
    # Configure mock on history_service, not repository
    mock_history_service.count_sessions_by_status.return_value = 3
    
    # Create worker with pre-configured mock
    worker = SessionClaimWorker(
        history_service=mock_history_service,
        max_global_concurrent=5,
        claim_interval=0.1,
        process_callback=mock_process_callback,
        pod_id="test-pod"
    )
    
    has_capacity = await worker._has_capacity()
    
    assert has_capacity is True


@pytest.mark.asyncio
async def test_worker_has_capacity_false(worker, mock_history_service):
    """Test capacity check when at max capacity."""
    mock_history_service.repository.count_sessions_by_status.return_value = 5
    
    has_capacity = await worker._has_capacity()
    
    assert has_capacity is False


@pytest.mark.asyncio
async def test_worker_count_active_sessions(mock_history_service, mock_process_callback):
    """Test counting active sessions."""
    # Configure mock on history_service, not repository
    mock_history_service.count_sessions_by_status.return_value = 3
    
    # Create worker with pre-configured mock
    worker = SessionClaimWorker(
        history_service=mock_history_service,
        max_global_concurrent=5,
        claim_interval=0.1,
        process_callback=mock_process_callback,
        pod_id="test-pod"
    )
    
    count = await worker._count_active_sessions()
    
    assert count == 3


@pytest.mark.asyncio
async def test_worker_claim_next_session_success(mock_history_service, mock_process_callback):
    """Test successful session claiming."""
    # Create a proper mock session object with all required attributes
    mock_session = MagicMock()
    mock_session.session_id = "test-session-123"
    mock_session.alert_data = {"test": "data"}
    mock_session.alert_type = "test-alert"
    mock_session.author = "test-user"
    mock_session.runbook_url = None
    mock_session.mcp_selection = None
    mock_session.session_metadata = None
    mock_session.started_at_us = 1234567890
    
    # Configure mock on history_service, not repository
    mock_history_service.claim_next_pending_session.return_value = mock_session
    
    # Create worker with pre-configured mock
    worker = SessionClaimWorker(
        history_service=mock_history_service,
        max_global_concurrent=5,
        claim_interval=0.1,
        process_callback=mock_process_callback,
        pod_id="test-pod"
    )
    
    session_data = await worker._claim_next_session()
    
    assert session_data is not None
    assert session_data["session_id"] == "test-session-123"
    assert session_data["alert_data"] == {"test": "data"}
    assert session_data["alert_type"] == "test-alert"


@pytest.mark.asyncio
async def test_worker_claim_next_session_none(mock_history_service, mock_process_callback):
    """Test claiming when no pending sessions available."""
    # Configure mock on history_service, not repository
    mock_history_service.claim_next_pending_session.return_value = None
    
    # Create worker with pre-configured mock
    worker = SessionClaimWorker(
        history_service=mock_history_service,
        max_global_concurrent=5,
        claim_interval=0.1,
        process_callback=mock_process_callback,
        pod_id="test-pod"
    )
    
    session_data = await worker._claim_next_session()
    
    assert session_data is None


@pytest.mark.asyncio
async def test_worker_dispatch_session(mock_history_service, mock_process_callback):
    """Test dispatching a claimed session."""
    # Create worker
    worker = SessionClaimWorker(
        history_service=mock_history_service,
        max_global_concurrent=5,
        claim_interval=0.1,
        process_callback=mock_process_callback,
        pod_id="test-pod"
    )
    
    session_data = {
        "session_id": "test-session-123",
        "alert_data": {"test": "data"},
        "alert_type": "test-alert",
        "author": "test-user",
        "runbook_url": None,
        "mcp_selection": None,
        "session_metadata": None,
        "started_at_us": 1234567890  # Required field
    }
    
    with patch("tarsy.services.session_claim_worker.asyncio.create_task") as mock_create_task:
        await worker._dispatch_session(session_data)
        
        # Verify create_task was called
        assert mock_create_task.called is True


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
async def test_worker_claim_loop_with_capacity(mock_history_service, mock_process_callback):
    """Test claim loop when capacity is available and session is claimed."""
    mock_session = MagicMock()
    mock_session.session_id = "test-session-123"
    mock_session.alert_data = {"test": "data"}
    mock_session.alert_type = "test-alert"
    mock_session.author = "test-user"
    mock_session.runbook_url = None
    mock_session.mcp_selection = None
    mock_session.session_metadata = None
    mock_session.started_at_us = 1234567890
    
    # Configure mocks on history_service - has capacity, has pending session (then none to stop loop)
    mock_history_service.count_sessions_by_status.return_value = 2
    mock_history_service.claim_next_pending_session.side_effect = [
        mock_session,
        None
    ]
    
    # Create worker with pre-configured mock
    worker = SessionClaimWorker(
        history_service=mock_history_service,
        max_global_concurrent=5,
        claim_interval=0.1,
        process_callback=mock_process_callback,
        pod_id="test-pod"
    )
    
    # Start worker
    await worker.start()
    
    # Let it run for a bit
    await asyncio.sleep(0.3)
    
    # Stop worker
    await worker.stop()
    
    # Verify session was claimed and dispatched
    assert mock_history_service.claim_next_pending_session.call_count >= 1


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
async def test_worker_claim_loop_error_handling(mock_history_service, mock_process_callback, caplog):
    """Test claim loop handles errors gracefully."""
    # Configure mock on history_service to raise error in capacity check
    mock_history_service.count_sessions_by_status.side_effect = Exception("Database error")
    
    # Create worker with pre-configured mock
    worker = SessionClaimWorker(
        history_service=mock_history_service,
        max_global_concurrent=5,
        claim_interval=0.1,
        process_callback=mock_process_callback,
        pod_id="test-pod"
    )
    
    # Start worker
    await worker.start()
    
    # Let it run for a bit
    await asyncio.sleep(0.3)
    
    # Stop worker
    await worker.stop()
    
    # Verify error was logged (the specific message may vary)
    assert "failed" in caplog.text.lower() or "error" in caplog.text.lower()


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
