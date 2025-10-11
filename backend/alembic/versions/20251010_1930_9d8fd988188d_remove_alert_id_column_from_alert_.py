"""remove_alert_id_column_from_alert_sessions

Revision ID: 9d8fd988188d
Revises: 3eafea61046d
Create Date: 2025-10-10 19:30:03.755933

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d8fd988188d'
down_revision: Union[str, Sequence[str], None] = '3eafea61046d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Check if column exists before trying to drop it
    # (handles fresh databases where alert_id was never added)
    from sqlalchemy import inspect
    connection = op.get_bind()
    inspector = inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('alert_sessions')]
    
    if 'alert_id' in columns:
        with op.batch_alter_table('alert_sessions', schema=None) as batch_op:
            try:
                batch_op.drop_index(batch_op.f('ix_alert_sessions_alert_id'))
            except Exception:
                # Index might not exist, that's OK
                pass
            batch_op.drop_column('alert_id')


def downgrade() -> None:
    """Downgrade schema."""
    # Check if column exists before trying to add it back
    from sqlalchemy import inspect
    connection = op.get_bind()
    inspector = inspect(connection)
    columns = [col['name'] for col in inspector.get_columns('alert_sessions')]
    
    if 'alert_id' not in columns:
        with op.batch_alter_table('alert_sessions', schema=None) as batch_op:
            # Add column as nullable first
            batch_op.add_column(sa.Column('alert_id', sa.VARCHAR(), nullable=True))
            batch_op.create_index(batch_op.f('ix_alert_sessions_alert_id'), ['alert_id'], unique=True)
