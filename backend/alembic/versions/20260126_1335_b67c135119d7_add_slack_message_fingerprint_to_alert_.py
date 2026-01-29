"""add slack_message_fingerprint to alert_sessions

Revision ID: b67c135119d7
Revises: c4d5e6f7g8h9
Create Date: 2026-01-26 13:35:56.151465

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b67c135119d7"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7g8h9"
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
    if "slack_message_fingerprint" not in columns:
        with op.batch_alter_table("alert_sessions", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "slack_message_fingerprint",
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
    if "slack_message_fingerprint" in columns:
        with op.batch_alter_table("alert_sessions", schema=None) as batch_op:
            batch_op.drop_column("slack_message_fingerprint")