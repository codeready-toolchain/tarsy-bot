"""add mcp_selection to alert_sessions

Revision ID: da4300b74d0e
Revises: 9f8e7d6c5b4a
Create Date: 2025-11-03 22:57:17.531702

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'da4300b74d0e'
down_revision: Union[str, Sequence[str], None] = '9f8e7d6c5b4a'
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
    if 'mcp_selection' not in columns:
        with op.batch_alter_table('alert_sessions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('mcp_selection', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Check if column exists before trying to drop it
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('alert_sessions')]
    
    # Only drop column if it exists
    if 'mcp_selection' in columns:
        with op.batch_alter_table('alert_sessions', schema=None) as batch_op:
            batch_op.drop_column('mcp_selection')
