"""Tests for session scoring models."""

import pytest
from tarsy.models.constants import ScoringStatus
from tarsy.models.db_models import SessionScore
from tarsy.models.api_models import SessionScoreResponse
from tarsy.utils.timestamp import now_us
from tarsy.agents.prompts.judges import CURRENT_PROMPT_HASH


class TestScoringStatusEnum:
    """Test ScoringStatus enum."""

    def test_active_values(self):
        """Test active_values() returns pending and in_progress."""
        active = ScoringStatus.active_values()
        assert "pending" in active
        assert "in_progress" in active
        assert len(active) == 2

    def test_values(self):
        """Test values() returns all status strings."""
        all_values = ScoringStatus.values()
        assert len(all_values) == 4
        assert "pending" in all_values
        assert "in_progress" in all_values
        assert "completed" in all_values
        assert "failed" in all_values


class TestSessionScore:
    """Test SessionScore model validation."""

    def test_create_session_score_with_required_fields(self):
        """Test creating SessionScoreDB with minimum required fields."""
        score = SessionScore(
            session_id="test-session-123",
            prompt_hash="abc123",
            score_triggered_by="user:test",
            status=ScoringStatus.PENDING.value,
        )

        assert score.session_id == "test-session-123"
        assert score.prompt_hash == "abc123"
        assert score.score_triggered_by == "user:test"
        assert score.status == "pending"
        assert score.score_id is not None  # Auto-generated
        assert score.started_at_us is not None  # Auto-generated
        assert score.scored_at_us is not None  # Auto-generated

    def test_score_id_auto_generation(self):
        """Test that score_id is auto-generated as UUID."""
        score1 = SessionScore(
            session_id="test-session-123",
            prompt_hash="abc123",
            score_triggered_by="user:test",
            status=ScoringStatus.PENDING.value,
        )
        score2 = SessionScore(
            session_id="test-session-456",
            prompt_hash="abc123",
            score_triggered_by="user:test",
            status=ScoringStatus.PENDING.value,
        )

        assert score1.score_id != score2.score_id
        assert len(score1.score_id) == 36  # UUID format


class TestSessionScoreResponse:
    """Test SessionScoreResponse."""

    def test_db_to_api_model_conversion(self):
        """Test converting SessionScore to SessionScoreResponse."""
        timestamp = now_us()
        db_score = SessionScore(
            score_id="score-123",
            session_id="session-456",
            prompt_hash="hash789",
            total_score=75,
            score_analysis="Good investigation",
            missing_tools_analysis="No missing tools",
            score_triggered_by="user:alice",
            scored_at_us=timestamp,
            status=ScoringStatus.COMPLETED.value,
            started_at_us=timestamp,
            completed_at_us=timestamp,
        )

        # Manually convert DB model to API model
        api_score = SessionScoreResponse(
            score_id=db_score.score_id,
            session_id=db_score.session_id,
            prompt_hash=db_score.prompt_hash,
            total_score=db_score.total_score,
            score_analysis=db_score.score_analysis,
            missing_tools_analysis=db_score.missing_tools_analysis,
            score_triggered_by=db_score.score_triggered_by,
            scored_at_us=db_score.scored_at_us,
            status=db_score.status,
            started_at_us=db_score.started_at_us,
            completed_at_us=db_score.completed_at_us,
            error_message=db_score.error_message,
        )

        assert api_score.score_id == "score-123"
        assert api_score.session_id == "session-456"
        assert api_score.prompt_hash == "hash789"
        assert api_score.total_score == 75
        assert api_score.score_analysis == "Good investigation"
        assert api_score.status == "completed"

    def test_current_prompt_used_with_matching_hash(self):
        """Test that current_prompt_used returns True when hash matches."""
        db_score = SessionScore(
            session_id="session-456",
            prompt_hash=CURRENT_PROMPT_HASH,  # Use current hash
            score_triggered_by="user:alice",
            status=ScoringStatus.COMPLETED.value,
        )

        api_score = SessionScoreResponse(
            score_id=db_score.score_id,
            session_id=db_score.session_id,
            prompt_hash=db_score.prompt_hash,
            score_triggered_by=db_score.score_triggered_by,
            scored_at_us=db_score.scored_at_us,
            status=db_score.status,
            started_at_us=db_score.started_at_us,
        )

        # Should return True since hash matches current
        assert api_score.current_prompt_used is True

    def test_current_prompt_used_with_obsolete_hash(self):
        """Test that current_prompt_used returns False for obsolete hash."""
        db_score = SessionScore(
            session_id="session-456",
            prompt_hash="obsolete_hash_from_old_criteria",
            score_triggered_by="user:alice",
            status=ScoringStatus.COMPLETED.value,
        )

        api_score = SessionScoreResponse(
            score_id=db_score.score_id,
            session_id=db_score.session_id,
            prompt_hash=db_score.prompt_hash,
            score_triggered_by=db_score.score_triggered_by,
            scored_at_us=db_score.scored_at_us,
            status=db_score.status,
            started_at_us=db_score.started_at_us,
        )

        # Should return False since hash doesn't match current
        assert api_score.current_prompt_used is False

    def test_current_prompt_used_is_computed_field(self):
        """Test that current_prompt_used is computed, not stored."""
        # Create with one hash
        api_score = SessionScoreResponse(
            score_id="score-123",
            session_id="session-456",
            prompt_hash="old_hash",
            score_triggered_by="user:alice",
            scored_at_us=now_us(),
            status=ScoringStatus.COMPLETED.value,
            started_at_us=now_us(),
        )

        # Should be False for old hash
        assert api_score.current_prompt_used is False

        # Update prompt_hash to current
        api_score.prompt_hash = CURRENT_PROMPT_HASH

        # Should now be True (computed dynamically)
        assert api_score.current_prompt_used is True
