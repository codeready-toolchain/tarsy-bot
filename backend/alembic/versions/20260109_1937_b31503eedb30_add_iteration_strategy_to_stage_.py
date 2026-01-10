"""Add iteration_strategy to stage_executions

Revision ID: b31503eedb30
Revises: a1b2c3d4e5f6
Create Date: 2026-01-09 19:37:41.149468

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b31503eedb30"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add iteration_strategy column to stage_executions table.
    
    This field tracks the iteration strategy used for a stage execution
    (e.g., 'native-thinking', 'react'), enabling the frontend to properly
    display and handle different types of LLM interactions.
    """
    # Check if column already exists (defensive for test scenarios)
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('stage_executions')]
    
    # Only add column if it doesn't exist
    if 'iteration_strategy' not in columns:
        with op.batch_alter_table('stage_executions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('iteration_strategy', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove iteration_strategy column from stage_executions table."""
    # Check if column exists before trying to drop it
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('stage_executions')]
    
    # Only drop column if it exists
    if 'iteration_strategy' in columns:
        with op.batch_alter_table('stage_executions', schema=None) as batch_op:
            batch_op.drop_column('iteration_strategy')
