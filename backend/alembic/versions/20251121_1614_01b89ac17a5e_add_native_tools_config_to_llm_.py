"""add_native_tools_config_to_llm_interactions

Revision ID: 01b89ac17a5e
Revises: 921cbd5111ad
Create Date: 2025-11-21 16:14:26.152426

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '01b89ac17a5e'
down_revision: Union[str, Sequence[str], None] = '921cbd5111ad'
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
    if 'native_tools_config' not in columns:
        with op.batch_alter_table('llm_interactions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('native_tools_config', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Check if column exists before trying to drop it
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('llm_interactions')]
    
    # Only drop column if it exists
    if 'native_tools_config' in columns:
        with op.batch_alter_table('llm_interactions', schema=None) as batch_op:
            batch_op.drop_column('native_tools_config')
