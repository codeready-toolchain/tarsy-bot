"""add_runbook_url_to_alert_sessions

Revision ID: 9f8e7d6c5b4a
Revises: ab12cd34ef56
Create Date: 2025-10-24 22:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f8e7d6c5b4a"
down_revision: Union[str, Sequence[str], None] = "ab12cd34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add runbook_url column to alert_sessions (idempotent)."""
    # Check if column already exists (for databases created from baseline with updated model)
    connection = op.get_bind()
    inspector = inspect(connection)
    columns = [col["name"] for col in inspector.get_columns("alert_sessions")]

    # Add runbook_url field to track the runbook URL used for processing
    if "runbook_url" not in columns:
        with op.batch_alter_table("alert_sessions", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "runbook_url",
                    sqlmodel.sql.sqltypes.AutoString(),
                    nullable=True,
                )
            )


def downgrade() -> None:
    """Downgrade schema - remove runbook_url column from alert_sessions (idempotent)."""
    # Check if column exists before removing it
    connection = op.get_bind()
    inspector = inspect(connection)
    columns = [col["name"] for col in inspector.get_columns("alert_sessions")]

    # Remove runbook_url column
    if "runbook_url" in columns:
        with op.batch_alter_table("alert_sessions", schema=None) as batch_op:
            batch_op.drop_column("runbook_url")

