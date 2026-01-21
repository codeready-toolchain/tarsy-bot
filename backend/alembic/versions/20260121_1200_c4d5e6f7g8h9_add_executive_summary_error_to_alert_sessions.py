"""Add executive_summary_error field to AlertSession

Revision ID: c4d5e6f7g8h9
Revises: b31503eedb30
Create Date: 2026-01-21 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7g8h9"
down_revision: Union[str, Sequence[str], None] = "b31503eedb30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Check if column already exists (defensive for test scenarios)
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("alert_sessions")]

    # Only add column if it doesn't exist
    if "executive_summary_error" not in columns:
        with op.batch_alter_table("alert_sessions", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "executive_summary_error",
                    sqlmodel.sql.sqltypes.AutoString(),
                    nullable=True,
                )
            )


def downgrade() -> None:
    """Downgrade schema."""
    # Check if column exists before trying to drop it
    from sqlalchemy import inspect

    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col["name"] for col in inspector.get_columns("alert_sessions")]

    # Only drop column if it exists
    if "executive_summary_error" in columns:
        with op.batch_alter_table("alert_sessions", schema=None) as batch_op:
            batch_op.drop_column("executive_summary_error")
