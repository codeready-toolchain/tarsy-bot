"""add_thinking_content_to_llm_interactions

Revision ID: c2f1e3d4a5b6
Revises: 01b89ac17a5e
Create Date: 2025-12-04 15:00:00.000000

Adds thinking_content column to llm_interactions table for storing
internal reasoning from native thinking models (Gemini).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2f1e3d4a5b6'
down_revision: Union[str, Sequence[str], None] = '01b89ac17a5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add thinking_content column."""
    # Check if column already exists (defensive for test scenarios)
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('llm_interactions')]
    
    # Only add column if it doesn't exist
    if 'thinking_content' not in columns:
        with op.batch_alter_table('llm_interactions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('thinking_content', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema - remove thinking_content column."""
    # Check if column exists before trying to drop it
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('llm_interactions')]
    
    # Only drop column if it exists
    if 'thinking_content' in columns:
        with op.batch_alter_table('llm_interactions', schema=None) as batch_op:
            batch_op.drop_column('thinking_content')

