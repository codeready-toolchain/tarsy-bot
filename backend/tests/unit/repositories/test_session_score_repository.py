"""Tests for SessionScoreRepository."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine

from tarsy.models.constants import ScoringStatus
from tarsy.models.db_models import SessionScore, AlertSession
from tarsy.repositories.session_score_repository import SessionScoreRepository
from tarsy.utils.timestamp import now_us


@pytest.mark.unit
class TestSessionScoreRepository:
    """Test SessionScoreRepository CRUD operations."""

    @pytest.fixture
    def repository(self, test_database_session):
        """Create repository instance."""
        return SessionScoreRepository(test_database_session)

    @pytest.fixture
    def sample_alert_session(self, test_database_session):
        """Create sample AlertSession for FK constraint."""
        session = AlertSession(
            session_id="test-session-123",
            alert_data={},
            agent_type="KubernetesAgent",
            status="completed",
            started_at_us=now_us(),
            chain_id="test-chain-123",
        )
        test_database_session.add(session)
        test_database_session.commit()
        return session

    def test_create_session_score_success(self, repository, sample_alert_session):
        """Test successful score creation."""
        score = SessionScore(
            session_id=sample_alert_session.session_id,
            prompt_hash="abc123",
            score_triggered_by="user:test",
            status=ScoringStatus.PENDING,
        )

        created = repository.create_session_score(score)

        assert created is not None
        assert created.score_id is not None
        assert created.session_id == sample_alert_session.session_id
        assert created.status == ScoringStatus.PENDING

    def test_create_duplicate_active_score_raises_error(
        self, repository, sample_alert_session
    ):
        """Test that creating duplicate active score raises ValueError."""
        score1 = SessionScore(
            session_id=sample_alert_session.session_id,
            prompt_hash="abc123",
            score_triggered_by="user:test",
            status=ScoringStatus.PENDING,
        )
        repository.create_session_score(score1)

        # Attempt duplicate
        score2 = SessionScore(
            session_id=sample_alert_session.session_id,
            prompt_hash="abc123",
            score_triggered_by="user:test",
            status=ScoringStatus.IN_PROGRESS,
        )

        with pytest.raises(ValueError, match="due to constraint violation"):
            repository.create_session_score(score2)

    def test_create_allows_new_score_after_previous_completed(
        self, repository, sample_alert_session
    ):
        """Test that new score can be created after previous completes."""
        # Create and complete first score
        score1 = SessionScore(
            session_id=sample_alert_session.session_id,
            prompt_hash="abc123",
            score_triggered_by="user:test",
            status=ScoringStatus.COMPLETED,
            completed_at_us=now_us(),
        )
        repository.create_session_score(score1)

        # Create new score - should succeed
        score2 = SessionScore(
            session_id=sample_alert_session.session_id,
            prompt_hash="def456",
            score_triggered_by="user:test",
            status=ScoringStatus.PENDING,
        )
        created = repository.create_session_score(score2)

        assert created is not None
        assert created.score_id != score1.score_id

    def test_get_score_by_id_found(self, repository, sample_alert_session):
        """Test retrieving score by ID."""
        score = SessionScore(
            session_id=sample_alert_session.session_id,
            prompt_hash="abc123",
            score_triggered_by="user:test",
            status=ScoringStatus.PENDING,
        )
        created = repository.create_session_score(score)

        retrieved = repository.get_score_by_id(created.score_id)

        assert retrieved is not None
        assert retrieved.score_id == created.score_id

    def test_get_score_by_id_not_found(self, repository):
        """Test that non-existent score returns None."""
        retrieved = repository.get_score_by_id("nonexistent-id")
        assert retrieved is None

    def test_get_latest_score_for_session(self, repository, sample_alert_session):
        """Test getting most recent score."""
        # Create two scores
        score1 = SessionScore(
            session_id=sample_alert_session.session_id,
            prompt_hash="abc123",
            score_triggered_by="user:test",
            status=ScoringStatus.COMPLETED,
            scored_at_us=now_us() - 1000000,  # Earlier
        )
        score2 = SessionScore(
            session_id=sample_alert_session.session_id,
            prompt_hash="def456",
            score_triggered_by="user:test",
            status=ScoringStatus.PENDING,
            scored_at_us=now_us(),  # Later
        )
        repository.create_session_score(score1)
        repository.create_session_score(score2)

        latest = repository.get_latest_score_for_session(
            sample_alert_session.session_id
        )

        assert latest is not None
        assert latest.prompt_hash == "def456"  # Most recent

    def test_get_active_score_for_session(self, repository, sample_alert_session):
        """Test getting active score (pending/in_progress)."""
        # Create completed score
        score1 = SessionScore(
            session_id=sample_alert_session.session_id,
            prompt_hash="abc123",
            score_triggered_by="user:test",
            status=ScoringStatus.COMPLETED,
        )
        repository.create_session_score(score1)

        # Should return None (no active)
        active = repository.get_active_score_for_session(
            sample_alert_session.session_id
        )
        assert active is None

        # Create pending score
        score2 = SessionScore(
            session_id=sample_alert_session.session_id,
            prompt_hash="def456",
            score_triggered_by="user:test",
            status=ScoringStatus.PENDING,
        )
        repository.create_session_score(score2)

        # Should return the pending score
        active = repository.get_active_score_for_session(
            sample_alert_session.session_id
        )
        assert active is not None
        assert active.status == ScoringStatus.PENDING

    def test_update_score_status_to_completed(self, repository, sample_alert_session):
        """Test updating score status to completed with results."""
        score = SessionScore(
            session_id=sample_alert_session.session_id,
            prompt_hash="abc123",
            score_triggered_by="user:test",
            status=ScoringStatus.PENDING,
        )
        created = repository.create_session_score(score)

        # Update to completed
        updated = repository.update_score_status(
            score_id=created.score_id,
            status=ScoringStatus.COMPLETED,
            completed_at_us=now_us(),
            total_score=85,
            score_analysis="Excellent investigation",
            missing_tools_analysis="No tools missing",
        )

        assert updated is not None
        assert updated.status == ScoringStatus.COMPLETED
        assert updated.total_score == 85
        assert updated.completed_at_us is not None

    def test_update_score_status_to_failed(self, repository, sample_alert_session):
        """Test updating score status to failed with error message."""
        score = SessionScore(
            session_id=sample_alert_session.session_id,
            prompt_hash="abc123",
            score_triggered_by="user:test",
            status=ScoringStatus.IN_PROGRESS,
        )
        created = repository.create_session_score(score)

        # Update to failed
        updated = repository.update_score_status(
            score_id=created.score_id,
            status=ScoringStatus.FAILED,
            completed_at_us=now_us(),
            error_message="LLM API timeout",
        )

        assert updated is not None
        assert updated.status == ScoringStatus.FAILED
        assert updated.error_message == "LLM API timeout"
        assert updated.completed_at_us is not None
