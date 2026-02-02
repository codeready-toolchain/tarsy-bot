"""
Repository for session scoring database operations.

Provides database access layer for session scoring with SQLModel,
supporting async status tracking and duplicate prevention.
"""

from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, and_, select

from tarsy.models.constants import ScoringStatus
from tarsy.models.db_models import SessionScore
from tarsy.repositories.base_repository import BaseRepository
from tarsy.utils.logger import get_logger

logger = get_logger(__name__)


class SessionScoreRepository:
    """Repository for session scoring data operations."""

    def __init__(self, session: Session) -> None:
        """
        Initialize session score repository with database session.

        Args:
            session: SQLModel database session
        """
        self.session = session
        self.base_repo = BaseRepository(session, SessionScore)

    def create_session_score(self, score: SessionScore) -> SessionScore:
        """
        Create a new session scoring record.

        Prevents duplicate in-progress scores for the same session via
        partial unique constraint enforced at the database level.

        Args:
            score: SessionScore instance to create

        Returns:
            Created SessionScore

        Raises:
            ValueError: If attempting to create duplicate active scoring
        """
        try:
            return self.base_repo.create(score)
        except IntegrityError as e:
            # Partial unique constraint violation (both PostgreSQL and SQLite)
            self.session.rollback()
            raise ValueError(
                f"Cannot create active scoring for session {score.session_id} due to constraint violation: {str(e)}"
            ) from e

    def get_score_by_id(self, score_id: str) -> Optional[SessionScore]:
        """Retrieve a session score by ID."""
        return self.base_repo.get_by_id(score_id)

    def get_scores_for_session(
        self,
        session_id: str,
        status: Optional[ScoringStatus] = None
    ) -> List[SessionScore]:
        """Get all scoring attempts for a session, ordered by scored_at_us descending."""
        statement = select(SessionScore).where(
            SessionScore.session_id == session_id
        )

        if status:
            statement = statement.where(SessionScore.status == status)

        statement = statement.order_by(SessionScore.scored_at_us.desc())

        return list(self.session.exec(statement).all())

    def get_latest_score_for_session(self, session_id: str) -> Optional[SessionScore]:
        """Get the most recent scoring attempt for a session."""
        scores = self.get_scores_for_session(session_id)
        return scores[0] if scores else None

    def get_active_score_for_session(self, session_id: str) -> Optional[SessionScore]:
        """Get active (pending/in_progress) scoring for a session."""
        statement = select(SessionScore).where(
            and_(
                SessionScore.session_id == session_id,
                SessionScore.status.in_(ScoringStatus.active_values())
            )
        )

        return self.session.exec(statement).first()

    def update_score(self, score: SessionScore) -> SessionScore:
        """Update an existing session score."""
        return self.base_repo.update(score)

    def update_score_status(
        self,
        score_id: str,
        status: ScoringStatus,
        completed_at_us: Optional[int] = None,
        error_message: Optional[str] = None,
        total_score: Optional[int] = None,
        score_analysis: Optional[str] = None,
        missing_tools_analysis: Optional[str] = None
    ) -> Optional[SessionScore]:
        """
        Update scoring status and related fields.

        Convenience method for status transitions with automatic field updates.
        """
        score = self.get_score_by_id(score_id)
        if not score:
            logger.error(f"Score {score_id} not found for status update")
            return None

        score.status = status

        if completed_at_us:
            score.completed_at_us = completed_at_us

        if error_message:
            score.error_message = error_message

        if total_score is not None:
            score.total_score = total_score

        if score_analysis:
            score.score_analysis = score_analysis

        if missing_tools_analysis:
            score.missing_tools_analysis = missing_tools_analysis

        return self.update_score(score)
