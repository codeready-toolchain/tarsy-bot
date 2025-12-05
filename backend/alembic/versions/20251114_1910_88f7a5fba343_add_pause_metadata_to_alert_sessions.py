"""add pause_metadata to alert_sessions

Revision ID: 88f7a5fba343
Revises: 09f57a2a2439
Create Date: 2025-11-14 19:10:21.946869

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '88f7a5fba343'
down_revision: Union[str, Sequence[str], None] = '09f57a2a2439'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Check if column already exists (defensive for test scenarios)
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('alert_sessions')]
    
    # Only add column if it doesn't exist
    if 'pause_metadata' not in columns:
        with op.batch_alter_table('alert_sessions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('pause_metadata', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Check if column exists before trying to drop it
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('alert_sessions')]
    
    # Only drop column if it exists
    if 'pause_metadata' in columns:
        with op.batch_alter_table('alert_sessions', schema=None) as batch_op:
            batch_op.drop_column('pause_metadata')
