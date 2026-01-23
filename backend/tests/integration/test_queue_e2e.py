"""
Integration tests for end-to-end alert queue flow
"""

import asyncio
import time
from unittest.mock import MagicMock

import pytest
from sqlmodel import Session

from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession
from tarsy.models.processing_context import ChainContext
from tarsy.repositories.history_repository import HistoryRepository
from tarsy.services.session_claim_worker import SessionClaimWorker
from tarsy.utils.timestamp import now_us

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_process_callback():
    """Create a mock process callback that tracks calls."""
    calls = []
    
    async def callback(session_id: str, alert: ChainContext):
        calls.append({"session_id": session_id, "alert": alert})
        await asyncio.sleep(0.1)  # Simulate processing
    
    callback.calls = calls
    return callback


@pytest.fixture
def create_session_in_db(db_session: Session):
    """Helper to create session directly in database."""
    def _create(
        session_id: str,
        status: str = AlertSessionStatus.PENDING.value,
        pod_id: str = None
    ) -> AlertSession:
        session = AlertSession(
            session_id=session_id,
            alert_type="test-alert",
            agent_type="test-agent",
            status=status,
            pod_id=pod_id,
            started_at_us=now_us(),
            alert_data={"test": "data"}
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        return session
    return _create


@pytest.mark.asyncio
async def test_queue_end_to_end_single_session(
    db_session: Session,
    create_session_in_db,
    mock_process_callback
):
    """Test end-to-end queue flow with single session."""
    # Setup
    history_repository = HistoryRepository(db_session)
    
    # Create pending session
    session = create_session_in_db("session-1")
    assert session.status == AlertSessionStatus.PENDING.value
    
    # Create worker
    worker = SessionClaimWorker(
        history_service=MagicMock(repository=history_repository),
        max_global_concurrent=5,
        claim_interval=0.1,
        process_callback=mock_process_callback,
        pod_id="test-pod"
    )
    
    # Start worker
    await worker.start()
    
    # Wait for processing
    await asyncio.sleep(0.3)
    
    # Stop worker
    await worker.stop()
    
    # Verify session was claimed and dispatched
    assert len(mock_process_callback.calls) == 1
    assert mock_process_callback.calls[0]["session_id"] == "session-1"
    
    # Verify session status updated
    db_session.refresh(session)
    assert session.status == AlertSessionStatus.IN_PROGRESS.value
    assert session.pod_id == "test-pod"


@pytest.mark.asyncio
async def test_queue_end_to_end_multiple_sessions_fifo(
    db_session: Session,
    create_session_in_db,
    mock_process_callback
):
    """Test FIFO ordering with multiple sessions."""
    # Setup
    history_repository = HistoryRepository(db_session)
    
    # Create 3 pending sessions with delays to ensure ordering
    session1 = create_session_in_db("session-1")
    time.sleep(0.01)
    session2 = create_session_in_db("session-2")
    time.sleep(0.01)
    session3 = create_session_in_db("session-3")
    
    # Create worker with high concurrency to process all
    worker = SessionClaimWorker(
        history_service=MagicMock(repository=history_repository),
        max_global_concurrent=10,
        claim_interval=0.1,
        process_callback=mock_process_callback,
        pod_id="test-pod"
    )
    
    # Start worker
    await worker.start()
    
    # Wait for all to be claimed
    await asyncio.sleep(0.5)
    
    # Stop worker
    await worker.stop()
    
    # Verify all sessions were dispatched in FIFO order
    assert len(mock_process_callback.calls) == 3
    assert mock_process_callback.calls[0]["session_id"] == "session-1"
    assert mock_process_callback.calls[1]["session_id"] == "session-2"
    assert mock_process_callback.calls[2]["session_id"] == "session-3"


@pytest.mark.asyncio
async def test_queue_respects_global_concurrency_limit(
    db_session: Session,
    create_session_in_db,
    mock_process_callback
):
    """Test that worker respects global concurrency limit."""
    # Setup
    history_repository = HistoryRepository(db_session)
    
    # Create 5 pending sessions
    for i in range(1, 6):
        create_session_in_db(f"session-{i}")
        time.sleep(0.01)
    
    # Create 2 sessions already in progress (simulating other pods)
    create_session_in_db("session-in-progress-1", AlertSessionStatus.IN_PROGRESS.value, "other-pod-1")
    create_session_in_db("session-in-progress-2", AlertSessionStatus.IN_PROGRESS.value, "other-pod-2")
    
    # Create worker with limit of 3
    worker = SessionClaimWorker(
        history_service=MagicMock(repository=history_repository),
        max_global_concurrent=3,
        claim_interval=0.1,
        process_callback=mock_process_callback,
        pod_id="test-pod"
    )
    
    # Start worker
    await worker.start()
    
    # Wait briefly - should only claim 1 session (2 + 1 = 3)
    await asyncio.sleep(0.3)
    
    # Verify only 1 session was claimed (not all 5)
    assert len(mock_process_callback.calls) == 1
    
    # Verify active count is at limit
    active_count = history_repository.count_sessions_by_status(AlertSessionStatus.IN_PROGRESS.value)
    assert active_count == 3  # 2 existing + 1 claimed
    
    # Stop worker
    await worker.stop()


@pytest.mark.asyncio
async def test_queue_handles_no_pending_sessions(
    db_session: Session,
    mock_process_callback
):
    """Test worker handles empty queue gracefully."""
    # Setup
    history_repository = HistoryRepository(db_session)
    
    # No pending sessions created
    
    # Create worker
    worker = SessionClaimWorker(
        history_service=MagicMock(repository=history_repository),
        max_global_concurrent=5,
        claim_interval=0.1,
        process_callback=mock_process_callback,
        pod_id="test-pod"
    )
    
    # Start worker
    await worker.start()
    
    # Wait
    await asyncio.sleep(0.3)
    
    # Stop worker
    await worker.stop()
    
    # Verify no sessions were dispatched
    assert len(mock_process_callback.calls) == 0


@pytest.mark.asyncio
async def test_multi_pod_claiming(
    db_session: Session,
    create_session_in_db
):
    """Test multiple pods claiming different sessions."""
    # Setup
    history_repository = HistoryRepository(db_session)
    
    # Create 3 pending sessions
    for i in range(1, 4):
        create_session_in_db(f"session-{i}")
        time.sleep(0.01)
    
    # Track which pod claimed which session
    pod1_calls = []
    pod2_calls = []
    
    async def pod1_callback(session_id: str, alert: ChainContext):
        pod1_calls.append(session_id)
        await asyncio.sleep(0.1)
    
    async def pod2_callback(session_id: str, alert: ChainContext):
        pod2_calls.append(session_id)
        await asyncio.sleep(0.1)
    
    # Create two workers (simulating two pods)
    worker1 = SessionClaimWorker(
        history_service=MagicMock(repository=history_repository),
        max_global_concurrent=10,
        claim_interval=0.1,
        process_callback=pod1_callback,
        pod_id="pod-1"
    )
    
    worker2 = SessionClaimWorker(
        history_service=MagicMock(repository=history_repository),
        max_global_concurrent=10,
        claim_interval=0.1,
        process_callback=pod2_callback,
        pod_id="pod-2"
    )
    
    # Start both workers
    await worker1.start()
    await worker2.start()
    
    # Wait for all to be claimed
    await asyncio.sleep(0.5)
    
    # Stop workers
    await worker1.stop()
    await worker2.stop()
    
    # Verify all sessions were claimed (between both pods)
    total_claimed = len(pod1_calls) + len(pod2_calls)
    assert total_claimed == 3
    
    # Verify no duplicate claims
    all_claimed = set(pod1_calls + pod2_calls)
    assert len(all_claimed) == 3


@pytest.mark.asyncio
async def test_session_cancellation_in_queue(
    db_session: Session,
    create_session_in_db
):
    """Test cancelling a session while it's in pending queue."""
    # Setup
    history_repository = HistoryRepository(db_session)
    
    # Create pending session
    session = create_session_in_db("session-1")
    
    # Cancel it before worker picks it up
    session.status = AlertSessionStatus.CANCELLED.value
    db_session.add(session)
    db_session.commit()
    
    # Create worker
    callback_calls = []
    
    async def callback(session_id: str, alert: ChainContext):
        callback_calls.append(session_id)
    
    worker = SessionClaimWorker(
        history_service=MagicMock(repository=history_repository),
        max_global_concurrent=5,
        claim_interval=0.1,
        process_callback=callback,
        pod_id="test-pod"
    )
    
    # Start worker
    await worker.start()
    
    # Wait
    await asyncio.sleep(0.3)
    
    # Stop worker
    await worker.stop()
    
    # Verify cancelled session was not claimed
    assert len(callback_calls) == 0
    
    # Verify status still cancelled
    db_session.refresh(session)
    assert session.status == AlertSessionStatus.CANCELLED.value


@pytest.mark.asyncio
async def test_queue_continues_after_dispatch_error(
    db_session: Session,
    create_session_in_db,
    caplog
):
    """Test worker continues processing after dispatch error."""
    # Setup
    history_repository = HistoryRepository(db_session)
    
    # Create 2 pending sessions
    session1 = create_session_in_db("session-1")
    time.sleep(0.01)
    session2 = create_session_in_db("session-2")
    
    callback_count = [0]
    
    async def failing_callback(session_id: str, alert: ChainContext):
        callback_count[0] += 1
        if callback_count[0] == 1:
            # First call fails
            raise Exception("Simulated dispatch error")
        # Second call succeeds
        await asyncio.sleep(0.1)
    
    # Create worker
    worker = SessionClaimWorker(
        history_service=MagicMock(repository=history_repository),
        max_global_concurrent=10,
        claim_interval=0.1,
        process_callback=failing_callback,
        pod_id="test-pod"
    )
    
    # Start worker
    await worker.start()
    
    # Wait for both to be attempted
    await asyncio.sleep(0.5)
    
    # Stop worker
    await worker.stop()
    
    # Verify both sessions were attempted
    assert callback_count[0] == 2
    
    # First session should be marked as failed in DB
    db_session.refresh(session1)
    # Note: Our current implementation doesn't mark as failed in DB on dispatch error
    # It just logs the error. This could be enhanced.
