"""add_session_scores_table

Revision ID: 776dca9d9a2f
Revises: b67c135119d7
Create Date: 2026-01-13 17:21:32.869647

Adds session_scores table for alert session scoring API (EP-0028):
- Tracks scoring attempts for alert sessions
- Stores prompt hash for detecting stale scores
- Async status tracking (pending -> in_progress -> completed/failed)
- Partial unique constraint prevents duplicate concurrent scoring attempts
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "776dca9d9a2f"
down_revision: Union[str, Sequence[str], None] = "b67c135119d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create session_scores table with indexes and constraints."""
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if "session_scores" not in existing_tables:
        # Create table
        op.create_table(
            "session_scores",
            sa.Column("score_id", sa.String(), nullable=False),
            sa.Column("session_id", sa.String(), nullable=False),
            sa.Column("prompt_hash", sa.String(length=64), nullable=False),
            sa.Column("total_score", sa.Integer(), nullable=True),
            sa.Column("score_analysis", sa.Text(), nullable=True),
            sa.Column("missing_tools_analysis", sa.Text(), nullable=True),
            sa.Column("score_triggered_by", sa.String(length=255), nullable=False),
            sa.Column("scored_at_us", sa.BIGINT(), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("started_at_us", sa.BIGINT(), nullable=False),
            sa.Column("completed_at_us", sa.BIGINT(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["session_id"],
                ["alert_sessions.session_id"],
                name="fk_session_scores_session",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("score_id"),
        )

        # Create indexes
        op.create_index(
            "ix_session_scores_session_id", "session_scores", ["session_id"]
        )
        op.create_index(
            "ix_session_scores_prompt_hash", "session_scores", ["prompt_hash"]
        )
        op.create_index(
            "ix_session_scores_total_score", "session_scores", ["total_score"]
        )
        op.create_index("ix_session_scores_status", "session_scores", ["status"])
        op.create_index(
            "ix_session_scores_session_status",
            "session_scores",
            ["session_id", "status"],
        )
        op.create_index(
            "ix_session_scores_status_started",
            "session_scores",
            ["status", "started_at_us"],
        )

        # Create partial unique index (prevents duplicate active scorings)
        op.execute("""
            CREATE UNIQUE INDEX ix_session_scores_unique_active
            ON session_scores(session_id)
            WHERE status IN ('pending', 'in_progress')
        """)


def downgrade() -> None:
    """Drop session_scores table."""
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if "session_scores" in existing_tables:
        # Drop partial unique index
        op.execute("DROP INDEX IF EXISTS ix_session_scores_unique_active")

        # Drop table (indexes drop automatically)
        op.drop_table("session_scores")
