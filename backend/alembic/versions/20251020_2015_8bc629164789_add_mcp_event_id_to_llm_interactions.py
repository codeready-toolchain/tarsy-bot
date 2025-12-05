"""add_mcp_event_id_to_llm_interactions

Revision ID: 8bc629164789
Revises: 3717971cb125
Create Date: 2025-10-20 20:15:29.215996

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8bc629164789'
down_revision: Union[str, Sequence[str], None] = '3717971cb125'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add mcp_event_id to llm_interactions (idempotent)."""
    # Check if column already exists (for databases created from baseline with updated model)
    connection = op.get_bind()
    inspector = inspect(connection)
    columns = [col["name"] for col in inspector.get_columns("llm_interactions")]
    
    # Add mcp_event_id to link summarization interactions to their tool calls
    if "mcp_event_id" not in columns:
        with op.batch_alter_table('llm_interactions', schema=None) as batch_op:
            batch_op.add_column(sa.Column('mcp_event_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema - remove mcp_event_id from llm_interactions (idempotent)."""
    # Check if column exists before removing it
    connection = op.get_bind()
    inspector = inspect(connection)
    columns = [col["name"] for col in inspector.get_columns("llm_interactions")]
    
    # Remove mcp_event_id column
    if "mcp_event_id" in columns:
        with op.batch_alter_table('llm_interactions', schema=None) as batch_op:
            batch_op.drop_column('mcp_event_id')
