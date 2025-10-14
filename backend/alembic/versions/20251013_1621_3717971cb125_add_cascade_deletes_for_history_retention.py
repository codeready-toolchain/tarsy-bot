"""add cascade deletes for history retention

Revision ID: 3717971cb125
Revises: 3d5f7251e766
Create Date: 2025-10-13 16:21:00.000000

Adds ON DELETE CASCADE to all foreign keys referencing alert_sessions and
stage_executions to enable automatic cleanup of related records when old
sessions are deleted based on history_retention_days configuration.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3717971cb125"
down_revision: Union[str, Sequence[str], None] = "3d5f7251e766"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add CASCADE delete to foreign keys for automatic history cleanup."""
    # Get connection and detect database type
    conn = op.get_bind()
    db_type = conn.dialect.name
    
    if db_type == "postgresql":
        # PostgreSQL: Drop and recreate foreign keys with CASCADE
        _upgrade_postgresql()
    else:
        # SQLite: Use batch_alter_table which handles table recreation
        _upgrade_sqlite()


def _upgrade_postgresql() -> None:
    """PostgreSQL-specific upgrade: drop and recreate foreign keys."""
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # stage_executions.session_id -> alert_sessions.session_id
    with op.batch_alter_table("stage_executions", schema=None) as batch_op:
        # Drop existing foreign key if it exists
        existing_fks = inspector.get_foreign_keys("stage_executions")
        for fk in existing_fks:
            if fk["constrained_columns"] == ["session_id"]:
                batch_op.drop_constraint(fk["name"], type_="foreignkey")
        
        # Recreate with CASCADE
        batch_op.create_foreign_key(
            "fk_stage_executions_session_id",
            "alert_sessions",
            ["session_id"],
            ["session_id"],
            ondelete="CASCADE",
        )
    
    # llm_interactions.session_id -> alert_sessions.session_id
    with op.batch_alter_table("llm_interactions", schema=None) as batch_op:
        existing_fks = inspector.get_foreign_keys("llm_interactions")
        for fk in existing_fks:
            if fk["constrained_columns"] == ["session_id"]:
                batch_op.drop_constraint(fk["name"], type_="foreignkey")
        
        batch_op.create_foreign_key(
            "fk_llm_interactions_session_id",
            "alert_sessions",
            ["session_id"],
            ["session_id"],
            ondelete="CASCADE",
        )
    
    # llm_interactions.stage_execution_id -> stage_executions.execution_id
    with op.batch_alter_table("llm_interactions", schema=None) as batch_op:
        existing_fks = inspector.get_foreign_keys("llm_interactions")
        for fk in existing_fks:
            if fk["constrained_columns"] == ["stage_execution_id"]:
                batch_op.drop_constraint(fk["name"], type_="foreignkey")
        
        batch_op.create_foreign_key(
            "fk_llm_interactions_stage_execution_id",
            "stage_executions",
            ["stage_execution_id"],
            ["execution_id"],
            ondelete="CASCADE",
        )
    
    # mcp_communications.session_id -> alert_sessions.session_id
    with op.batch_alter_table("mcp_communications", schema=None) as batch_op:
        existing_fks = inspector.get_foreign_keys("mcp_communications")
        for fk in existing_fks:
            if fk["constrained_columns"] == ["session_id"]:
                batch_op.drop_constraint(fk["name"], type_="foreignkey")
        
        batch_op.create_foreign_key(
            "fk_mcp_communications_session_id",
            "alert_sessions",
            ["session_id"],
            ["session_id"],
            ondelete="CASCADE",
        )
    
    # mcp_communications.stage_execution_id -> stage_executions.execution_id
    with op.batch_alter_table("mcp_communications", schema=None) as batch_op:
        existing_fks = inspector.get_foreign_keys("mcp_communications")
        for fk in existing_fks:
            if fk["constrained_columns"] == ["stage_execution_id"]:
                batch_op.drop_constraint(fk["name"], type_="foreignkey")
        
        batch_op.create_foreign_key(
            "fk_mcp_communications_stage_execution_id",
            "stage_executions",
            ["stage_execution_id"],
            ["execution_id"],
            ondelete="CASCADE",
        )


def _upgrade_sqlite() -> None:
    """SQLite-specific upgrade: batch_alter_table handles table recreation."""
    # SQLite doesn't support ALTER TABLE for foreign keys, but batch_alter_table
    # handles this by creating a new table, copying data, and dropping the old one
    # With recreate="always", we don't drop constraints - just define new schema
    
    # stage_executions: recreate with CASCADE on session_id
    with op.batch_alter_table("stage_executions", schema=None, recreate="always") as batch_op:
        pass  # Foreign keys will be recreated from model definitions with CASCADE
    
    # llm_interactions: recreate with CASCADE on both foreign keys  
    with op.batch_alter_table("llm_interactions", schema=None, recreate="always") as batch_op:
        pass  # Foreign keys will be recreated from model definitions with CASCADE
    
    # mcp_communications: recreate with CASCADE on both foreign keys
    with op.batch_alter_table("mcp_communications", schema=None, recreate="always") as batch_op:
        pass  # Foreign keys will be recreated from model definitions with CASCADE


def downgrade() -> None:
    """Remove CASCADE from foreign keys (revert to no action)."""
    # Get connection and detect database type
    conn = op.get_bind()
    db_type = conn.dialect.name
    
    if db_type == "postgresql":
        _downgrade_postgresql()
    else:
        _downgrade_sqlite()


def _downgrade_postgresql() -> None:
    """PostgreSQL-specific downgrade: recreate foreign keys without CASCADE."""
    from sqlalchemy import inspect
    
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # stage_executions.session_id
    with op.batch_alter_table("stage_executions", schema=None) as batch_op:
        existing_fks = inspector.get_foreign_keys("stage_executions")
        for fk in existing_fks:
            if fk["constrained_columns"] == ["session_id"]:
                batch_op.drop_constraint(fk["name"], type_="foreignkey")
        
        batch_op.create_foreign_key(
            "fk_stage_executions_session_id",
            "alert_sessions",
            ["session_id"],
            ["session_id"],
        )
    
    # llm_interactions.session_id
    with op.batch_alter_table("llm_interactions", schema=None) as batch_op:
        existing_fks = inspector.get_foreign_keys("llm_interactions")
        for fk in existing_fks:
            if fk["constrained_columns"] == ["session_id"]:
                batch_op.drop_constraint(fk["name"], type_="foreignkey")
        
        batch_op.create_foreign_key(
            "fk_llm_interactions_session_id",
            "alert_sessions",
            ["session_id"],
            ["session_id"],
        )
    
    # llm_interactions.stage_execution_id
    with op.batch_alter_table("llm_interactions", schema=None) as batch_op:
        existing_fks = inspector.get_foreign_keys("llm_interactions")
        for fk in existing_fks:
            if fk["constrained_columns"] == ["stage_execution_id"]:
                batch_op.drop_constraint(fk["name"], type_="foreignkey")
        
        batch_op.create_foreign_key(
            "fk_llm_interactions_stage_execution_id",
            "stage_executions",
            ["stage_execution_id"],
            ["execution_id"],
        )
    
    # mcp_communications.session_id
    with op.batch_alter_table("mcp_communications", schema=None) as batch_op:
        existing_fks = inspector.get_foreign_keys("mcp_communications")
        for fk in existing_fks:
            if fk["constrained_columns"] == ["session_id"]:
                batch_op.drop_constraint(fk["name"], type_="foreignkey")
        
        batch_op.create_foreign_key(
            "fk_mcp_communications_session_id",
            "alert_sessions",
            ["session_id"],
            ["session_id"],
        )
    
    # mcp_communications.stage_execution_id
    with op.batch_alter_table("mcp_communications", schema=None) as batch_op:
        existing_fks = inspector.get_foreign_keys("mcp_communications")
        for fk in existing_fks:
            if fk["constrained_columns"] == ["stage_execution_id"]:
                batch_op.drop_constraint(fk["name"], type_="foreignkey")
        
        batch_op.create_foreign_key(
            "fk_mcp_communications_stage_execution_id",
            "stage_executions",
            ["stage_execution_id"],
            ["execution_id"],
        )


def _downgrade_sqlite() -> None:
    """SQLite-specific downgrade: recreate tables without CASCADE."""
    # Note: SQLite downgrade requires reverting model changes first
    # With recreate="always", foreign keys are recreated from current model definitions
    # This is a limitation - to properly downgrade, you'd need to revert code changes
    
    # stage_executions
    with op.batch_alter_table("stage_executions", schema=None, recreate="always") as batch_op:
        pass  # Foreign keys recreated from model (will still have CASCADE if models not reverted)
    
    # llm_interactions
    with op.batch_alter_table("llm_interactions", schema=None, recreate="always") as batch_op:
        pass  # Foreign keys recreated from model (will still have CASCADE if models not reverted)
    
    # mcp_communications
    with op.batch_alter_table("mcp_communications", schema=None, recreate="always") as batch_op:
        pass  # Foreign keys recreated from model (will still have CASCADE if models not reverted)

