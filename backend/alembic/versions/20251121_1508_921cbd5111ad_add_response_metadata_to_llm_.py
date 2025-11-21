"""add_response_metadata_to_llm_interactions

Revision ID: 921cbd5111ad
Revises: 88f7a5fba343
Create Date: 2025-11-21 15:08:19.980919

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '921cbd5111ad'
down_revision: Union[str, Sequence[str], None] = '88f7a5fba343'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Check if column already exists (defensive for test scenarios)
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('llm_interactions')]
    
    # Only add column if it doesn't exist
    if 'response_metadata' not in columns:
        with op.batch_alter_table('llm_interactions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('response_metadata', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Check if column exists before trying to drop it
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('llm_interactions')]
    
    # Only drop column if it exists
    if 'response_metadata' in columns:
        with op.batch_alter_table('llm_interactions', schema=None) as batch_op:
            batch_op.drop_column('response_metadata')
