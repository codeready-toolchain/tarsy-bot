"""add_paused_at_us_to_stage_executions

Revision ID: a1b2c3d4e5f6
Revises: f0dd17b71ce2
Create Date: 2025-12-16 20:41:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f0dd17b71ce2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add paused_at_us column to stage_executions table.
    
    This field tracks when a stage was paused, enabling accurate duration
    calculation that excludes pause/wait time when the stage is cancelled.
    """
    # Check if column already exists (defensive for test scenarios)
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('stage_executions')]
    
    # Only add column if it doesn't exist
    if 'paused_at_us' not in columns:
        with op.batch_alter_table('stage_executions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('paused_at_us', sa.BIGINT(), nullable=True))


def downgrade() -> None:
    """Remove paused_at_us column from stage_executions table."""
    # Check if column exists before trying to drop it
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('stage_executions')]
    
    # Only drop column if it exists
    if 'paused_at_us' in columns:
        with op.batch_alter_table('stage_executions', schema=None) as batch_op:
            batch_op.drop_column('paused_at_us')

