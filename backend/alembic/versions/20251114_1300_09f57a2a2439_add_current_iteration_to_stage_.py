"""Add current_iteration to stage_execution for pause resume

Revision ID: 09f57a2a2439
Revises: 11b500f06df2
Create Date: 2025-11-14 13:00:57.160248

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '09f57a2a2439'
down_revision: Union[str, Sequence[str], None] = '11b500f06df2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Check if column already exists (defensive for test scenarios)
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('stage_executions')]
    
    # Only add column if it doesn't exist
    if 'current_iteration' not in columns:
        with op.batch_alter_table('stage_executions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('current_iteration', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Check if column exists before trying to drop it
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('stage_executions')]
    
    # Only drop column if it exists
    if 'current_iteration' in columns:
        with op.batch_alter_table('stage_executions', schema=None) as batch_op:
            batch_op.drop_column('current_iteration')
