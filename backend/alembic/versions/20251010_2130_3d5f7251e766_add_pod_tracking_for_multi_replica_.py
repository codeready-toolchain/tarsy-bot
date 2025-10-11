"""add pod tracking for multi-replica support

Revision ID: 3d5f7251e766
Revises: 9d8fd988188d
Create Date: 2025-10-10 21:30:21.592898

Adds pod_id and last_interaction_at fields to support multi-replica
Kubernetes deployments with session cleanup and orphan detection (EP-0024).
"""
from datetime import datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '3d5f7251e766'
down_revision: Union[str, Sequence[str], None] = '9d8fd988188d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add pod tracking columns for multi-replica support."""
    from sqlalchemy import inspect
    
    # Get connection and inspector
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # Get existing columns
    existing_columns = {col['name'] for col in inspector.get_columns('alert_sessions')}
    
    # Add new columns only if they don't exist (idempotent migration)
    with op.batch_alter_table('alert_sessions', schema=None) as batch_op:
        if 'pod_id' not in existing_columns:
            batch_op.add_column(sa.Column('pod_id', sa.String(255), nullable=True))
        if 'last_interaction_at' not in existing_columns:
            batch_op.add_column(sa.Column('last_interaction_at', sa.BIGINT(), nullable=True))
        
        # Check if index exists before creating
        existing_indexes = {idx['name'] for idx in inspector.get_indexes('alert_sessions')}
        if 'ix_alert_sessions_status_last_interaction' not in existing_indexes:
            batch_op.create_index(
                'ix_alert_sessions_status_last_interaction',
                ['status', 'last_interaction_at'],
                unique=False
            )
    
    # Backfill pod_id for existing rows (historical sessions get "unknown")
    op.execute("UPDATE alert_sessions SET pod_id = 'unknown' WHERE pod_id IS NULL")
    
    # Backfill last_interaction_at for existing rows (use started_at_us as fallback)
    # Only proceed if started_at_us column exists
    if 'started_at_us' in existing_columns:
        # Use COALESCE to handle NULL values; if started_at_us is NULL, use current timestamp
        # Database-agnostic: calculate timestamp in Python instead of database-specific SQL
        current_ts_us = int(datetime.now().timestamp() * 1_000_000)
        conn.execute(
            text("UPDATE alert_sessions "
                 "SET last_interaction_at = COALESCE(started_at_us, :current_ts) "
                 "WHERE last_interaction_at IS NULL"),
            {"current_ts": current_ts_us}
        )
    else:
        # If started_at_us doesn't exist, backfill with current timestamp
        # Database-agnostic: calculate timestamp in Python
        current_ts_us = int(datetime.now().timestamp() * 1_000_000)
        conn.execute(
            text("UPDATE alert_sessions "
                 "SET last_interaction_at = :current_ts "
                 "WHERE last_interaction_at IS NULL"),
            {"current_ts": current_ts_us}
        )


def downgrade() -> None:
    """Downgrade schema."""
    from sqlalchemy import inspect
    
    # Get connection and inspector for idempotent checks
    conn = op.get_bind()
    inspector = inspect(conn)
    
    with op.batch_alter_table('alert_sessions', schema=None) as batch_op:
        # Check and drop index if exists
        existing_indexes = {idx['name'] for idx in inspector.get_indexes('alert_sessions')}
        if 'ix_alert_sessions_status_last_interaction' in existing_indexes:
            batch_op.drop_index('ix_alert_sessions_status_last_interaction')
        
        # Check and drop columns if exist
        existing_columns = {col['name'] for col in inspector.get_columns('alert_sessions')}
        if 'last_interaction_at' in existing_columns:
            batch_op.drop_column('last_interaction_at')
        if 'pod_id' in existing_columns:
            batch_op.drop_column('pod_id')
