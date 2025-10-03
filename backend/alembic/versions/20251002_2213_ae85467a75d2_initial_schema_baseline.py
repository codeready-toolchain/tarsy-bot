"""Initial schema baseline

This is the baseline migration that creates the initial database schema.
For existing databases, tables already exist so operations are skipped (idempotent).
For fresh databases, tables are created from SQLModel metadata.

This migration serves to:
1. Establish version ae85467a75d2 as the baseline in the alembic_version table
2. Create initial schema (AlertSession, StageExecution, LLMInteraction, MCPInteraction)
3. Provide a starting point for future schema changes

Revision ID: ae85467a75d2
Revises:
Create Date: 2025-10-02 20:33:15.353864

"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "ae85467a75d2"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - create tables if they don't exist."""
    # Get connection and check if tables already exist
    connection = op.get_bind()
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    
    # Only create tables if they don't exist (idempotent for existing databases)
    if "llm_interactions" not in existing_tables:
        # Import and create all tables from SQLModel metadata
        from sqlmodel import SQLModel
        
        # Create all tables defined in metadata
        SQLModel.metadata.create_all(connection)


def downgrade() -> None:
    """Downgrade schema - this is a baseline, so downgrade does nothing."""
    # Baseline migration - no downgrade path
    pass
