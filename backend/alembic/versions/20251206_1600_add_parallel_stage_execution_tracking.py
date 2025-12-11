"""add_parallel_stage_execution_tracking

Revision ID: d7e8f9a0b1c2
Revises: c2f1e3d4a5b6
Create Date: 2025-12-06 16:00:00.000000

Adds parallel execution tracking to stage_executions table:
- parent_stage_execution_id: Foreign key to parent stage for parallel execution grouping
- parallel_index: Position in parallel group (0 for single/parent, 1-N for children)
- parallel_type: Execution type (ParallelType: SINGLE, MULTI_AGENT, REPLICA)
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, Sequence[str], None] = 'c2f1e3d4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add parallel execution tracking columns."""
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('stage_executions')]
    
    # Add columns if they don't exist
    with op.batch_alter_table('stage_executions', schema=None) as batch_op:
        if 'parent_stage_execution_id' not in columns:
            batch_op.add_column(
                sa.Column('parent_stage_execution_id', sa.String(), nullable=True)
            )
        
        if 'parallel_index' not in columns:
            batch_op.add_column(
                sa.Column('parallel_index', sa.Integer(), nullable=False, server_default='0')
            )
        
        if 'parallel_type' not in columns:
            batch_op.add_column(
                sa.Column('parallel_type', sa.String(), nullable=False, server_default='single')
            )
    
    # Add foreign key constraint (separate from batch operation for SQLite compatibility)
    # Note: SQLite doesn't support adding foreign keys to existing tables in batch mode
    # This will work in PostgreSQL; for SQLite in tests, foreign key is enforced at application level
    try:
        with op.batch_alter_table('stage_executions', schema=None) as batch_op:
            batch_op.create_foreign_key(
                'fk_stage_executions_parent',
                'stage_executions',
                ['parent_stage_execution_id'],
                ['execution_id']
            )
    except Exception as e:
        # Foreign key creation may fail in SQLite; that's OK for dev/test
        # Log for visibility in case this fails unexpectedly in PostgreSQL
        import logging
        logging.getLogger('alembic.migration').debug(
            f"Foreign key creation skipped (expected for SQLite): {e}"
        )
    
    # Add indexes for efficient queries
    with op.batch_alter_table('stage_executions', schema=None) as batch_op:
        # Index on parent_stage_execution_id for parent-child queries
        batch_op.create_index(
            'ix_stage_executions_parent_stage_execution_id',
            ['parent_stage_execution_id'],
            unique=False
        )
        
        # Composite index for hierarchical queries
        batch_op.create_index(
            'ix_stage_executions_session_parent',
            ['session_id', 'parent_stage_execution_id'],
            unique=False
        )


def downgrade() -> None:
    """Downgrade schema - remove parallel execution tracking columns."""
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Drop indexes first
    indexes = [idx['name'] for idx in inspector.get_indexes('stage_executions')]
    
    with op.batch_alter_table('stage_executions', schema=None) as batch_op:
        if 'ix_stage_executions_parent_stage_execution_id' in indexes:
            batch_op.drop_index('ix_stage_executions_parent_stage_execution_id')
        
        if 'ix_stage_executions_session_parent' in indexes:
            batch_op.drop_index('ix_stage_executions_session_parent')
    
    # Drop foreign key constraint if it exists
    try:
        with op.batch_alter_table('stage_executions', schema=None) as batch_op:
            batch_op.drop_constraint('fk_stage_executions_parent', type_='foreignkey')
    except Exception as e:
        # Constraint may not exist; that's OK
        # Log for visibility in case this fails unexpectedly
        import logging
        logging.getLogger('alembic.migration').debug(
            f"Foreign key constraint drop skipped (may not exist): {e}"
        )
    
    # Drop columns
    columns = [col['name'] for col in inspector.get_columns('stage_executions')]
    
    with op.batch_alter_table('stage_executions', schema=None) as batch_op:
        if 'parallel_type' in columns:
            batch_op.drop_column('parallel_type')
        
        if 'parallel_index' in columns:
            batch_op.drop_column('parallel_index')
        
        if 'parent_stage_execution_id' in columns:
            batch_op.drop_column('parent_stage_execution_id')

