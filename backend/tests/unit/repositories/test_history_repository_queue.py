"""
Unit tests for HistoryRepository queue methods
"""

import pytest
from sqlmodel import Session

from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession
from tarsy.repositories.history_repository import HistoryRepository
from tarsy.utils.timestamp import now_us

pytestmark = pytest.mark.unit


@pytest.fixture
def history_repository(test_database_session: Session):
    """Create a HistoryRepository with test database session."""
    return HistoryRepository(test_database_session)


@pytest.fixture
def create_pending_session(test_database_session: Session):
    """Helper to create a pending session."""
    def _create(session_id: str, alert_type: str = "test-alert") -> AlertSession:
        session = AlertSession(
            session_id=session_id,
            alert_type=alert_type,
            agent_type="test-agent",
            status=AlertSessionStatus.PENDING.value,
            started_at_us=now_us(),
            alert_data={"test": "data"},
            chain_id="test-chain-1"
        )
        test_database_session.add(session)
        test_database_session.commit()
        test_database_session.refresh(session)
        return session
    return _create


@pytest.fixture
def create_in_progress_session(test_database_session: Session):
    """Helper to create an in-progress session."""
    def _create(session_id: str, pod_id: str = "test-pod") -> AlertSession:
        session = AlertSession(
            session_id=session_id,
            alert_type="test-alert",
            agent_type="test-agent",
            status=AlertSessionStatus.IN_PROGRESS.value,
            pod_id=pod_id,
            started_at_us=now_us(),
            alert_data={"test": "data"},
            chain_id="test-chain-1"
        )
        test_database_session.add(session)
        test_database_session.commit()
        test_database_session.refresh(session)
        return session
    return _create


def test_count_pending_sessions_empty(history_repository: HistoryRepository):
    """Test counting pending sessions when none exist."""
    count = history_repository.count_pending_sessions()
    assert count == 0


def test_count_pending_sessions_with_data(
    history_repository: HistoryRepository,
    create_pending_session,
    create_in_progress_session
):
    """Test counting pending sessions with mixed data."""
    # Create 3 pending sessions
    create_pending_session("session-1")
    create_pending_session("session-2")
    create_pending_session("session-3")
    
    # Create 2 in-progress sessions (should not be counted)
    create_in_progress_session("session-4")
    create_in_progress_session("session-5")
    
    count = history_repository.count_pending_sessions()
    assert count == 3


def test_count_sessions_by_status(
    history_repository: HistoryRepository,
    create_pending_session,
    create_in_progress_session
):
    """Test counting sessions by status."""
    create_pending_session("session-1")
    create_pending_session("session-2")
    create_in_progress_session("session-3")
    create_in_progress_session("session-4")
    create_in_progress_session("session-5")
    
    pending_count = history_repository.count_sessions_by_status(AlertSessionStatus.PENDING.value)
    assert pending_count == 2
    
    in_progress_count = history_repository.count_sessions_by_status(AlertSessionStatus.IN_PROGRESS.value)
    assert in_progress_count == 3


def test_claim_next_pending_session_fifo(
    history_repository: HistoryRepository,
    create_pending_session
):
    """Test claiming returns oldest pending session first (FIFO)."""
    import time
    
    # Create sessions with small delays to ensure different timestamps
    session1 = create_pending_session("session-1")
    time.sleep(0.01)
    session2 = create_pending_session("session-2")
    time.sleep(0.01)
    session3 = create_pending_session("session-3")
    
    # Claim should return session-1 (oldest)
    claimed = history_repository.claim_next_pending_session("pod-1")
    
    assert claimed is not None
    assert claimed.session_id == "session-1"
    assert claimed.status == AlertSessionStatus.IN_PROGRESS.value
    assert claimed.pod_id == "pod-1"


def test_claim_next_pending_session_none_available(history_repository: HistoryRepository):
    """Test claiming when no pending sessions available."""
    claimed = history_repository.claim_next_pending_session("pod-1")
    assert claimed is None


def test_claim_next_pending_session_updates_status(
    history_repository: HistoryRepository,
    create_pending_session,
    test_database_session: Session
):
    """Test claiming updates session status and pod_id."""
    session = create_pending_session("session-1")
    
    claimed = history_repository.claim_next_pending_session("pod-1")
    
    assert claimed is not None
    assert claimed.session_id == "session-1"
    assert claimed.status == AlertSessionStatus.IN_PROGRESS.value
    assert claimed.pod_id == "pod-1"
    assert claimed.last_interaction_at is not None
    
    # Verify in database
    test_database_session.refresh(session)
    assert session.status == AlertSessionStatus.IN_PROGRESS.value
    assert session.pod_id == "pod-1"


def test_claim_next_pending_session_skips_in_progress(
    history_repository: HistoryRepository,
    create_pending_session,
    create_in_progress_session
):
    """Test claiming skips sessions already in progress."""
    import time
    
    # Create in-progress first
    create_in_progress_session("session-1")
    time.sleep(0.01)
    
    # Then pending
    create_pending_session("session-2")
    time.sleep(0.01)
    create_pending_session("session-3")
    
    # Should claim session-2 (oldest pending)
    claimed = history_repository.claim_next_pending_session("pod-1")
    
    assert claimed is not None
    assert claimed.session_id == "session-2"


def test_claim_next_pending_session_multiple_pods(
    history_repository: HistoryRepository,
    create_pending_session,
    test_database_session: Session
):
    """Test multiple pods claiming different sessions."""
    import time
    
    # Create 3 pending sessions
    create_pending_session("session-1")
    time.sleep(0.01)
    create_pending_session("session-2")
    time.sleep(0.01)
    create_pending_session("session-3")
    
    # Pod 1 claims
    claimed1 = history_repository.claim_next_pending_session("pod-1")
    assert claimed1.session_id == "session-1"
    assert claimed1.pod_id == "pod-1"
    
    # Pod 2 claims
    claimed2 = history_repository.claim_next_pending_session("pod-2")
    assert claimed2.session_id == "session-2"
    assert claimed2.pod_id == "pod-2"
    
    # Pod 3 claims
    claimed3 = history_repository.claim_next_pending_session("pod-3")
    assert claimed3.session_id == "session-3"
    assert claimed3.pod_id == "pod-3"
    
    # No more pending
    claimed4 = history_repository.claim_next_pending_session("pod-4")
    assert claimed4 is None


@pytest.mark.parametrize("dialect", ["sqlite", "postgresql"])
def test_claim_next_pending_session_dialect_specific(
    history_repository: HistoryRepository,
    create_pending_session,
    dialect
):
    """Test claiming works for both SQLite and PostgreSQL."""
    # Mock the dialect
    history_repository.session.bind.dialect.name = dialect
    
    create_pending_session("session-1")
    
    claimed = history_repository.claim_next_pending_session("pod-1")
    
    assert claimed is not None
    assert claimed.session_id == "session-1"
    assert claimed.pod_id == "pod-1"
