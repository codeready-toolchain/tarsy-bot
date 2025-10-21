"""add_mcp_event_id_to_llm_interactions

Revision ID: 8bc629164789
Revises: 3717971cb125
Create Date: 2025-10-20 20:15:29.215996

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '8bc629164789'
down_revision: Union[str, Sequence[str], None] = '3717971cb125'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add mcp_event_id to link summarization interactions to their tool calls
    with op.batch_alter_table('llm_interactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('mcp_event_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove mcp_event_id column
    with op.batch_alter_table('llm_interactions', schema=None) as batch_op:
        batch_op.drop_column('mcp_event_id')
