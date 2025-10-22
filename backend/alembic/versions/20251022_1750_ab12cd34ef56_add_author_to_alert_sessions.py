"""add_author_to_alert_sessions

Revision ID: ab12cd34ef56
Revises: 8bc629164789
Create Date: 2025-10-22 17:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = 'ab12cd34ef56'
down_revision: Union[str, Sequence[str], None] = '8bc629164789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add author column to alert_sessions (idempotent)."""
    # Check if column already exists (for databases created from baseline with updated model)
    connection = op.get_bind()
    inspector = inspect(connection)
    columns = [col["name"] for col in inspector.get_columns("alert_sessions")]
    
    # Add author field to track who submitted the alert
    if "author" not in columns:
        with op.batch_alter_table('alert_sessions', schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('author', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True)
            )


def downgrade() -> None:
    """Downgrade schema - remove author column from alert_sessions (idempotent)."""
    # Check if column exists before removing it
    connection = op.get_bind()
    inspector = inspect(connection)
    columns = [col["name"] for col in inspector.get_columns("alert_sessions")]
    
    # Remove author column
    if "author" in columns:
        with op.batch_alter_table('alert_sessions', schema=None) as batch_op:
            batch_op.drop_column('author')

