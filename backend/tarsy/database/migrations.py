"""
Database Migration Module

Handles programmatic Alembic migration execution for automatic database schema
updates on application startup. Supports both PostgreSQL and SQLite databases.
"""

import logging
from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


def get_alembic_config(database_url: str) -> Config:
    """
    Create Alembic configuration programmatically.

    Args:
        database_url: Database connection string

    Returns:
        Configured Alembic Config object

    Raises:
        FileNotFoundError: If alembic.ini not found
    """
    # Find alembic.ini relative to this module
    backend_dir = Path(__file__).parent.parent.parent
    alembic_ini = backend_dir / "alembic.ini"

    if not alembic_ini.exists():
        raise FileNotFoundError(f"Alembic configuration not found: {alembic_ini}")

    # Create config and override database URL
    config = Config(str(alembic_ini))
    
    # ConfigParser treats % as interpolation character (like %(variable)s)
    # We need to escape % in URL-encoded passwords by doubling them: % -> %%
    # This allows URL-encoded passwords like p%40ssw0rd to work as p%%40ssw0rd
    escaped_url = database_url.replace('%', '%%')
    config.set_main_option("sqlalchemy.url", escaped_url)

    return config


def get_current_version(database_url: str) -> Optional[str]:
    """
    Get the current database migration version.

    Args:
        database_url: Database connection string

    Returns:
        Current migration revision ID, or None if no migrations applied yet

    Raises:
        SQLAlchemyError: If database connection fails
    """
    try:
        engine = create_engine(database_url)

        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_rev = context.get_current_revision()

        return current_rev

    except SQLAlchemyError as e:
        logger.error(f"Failed to get current migration version: {e}")
        raise


def get_pending_migrations(database_url: str) -> list[str]:
    """
    Get list of pending migrations that haven't been applied yet.

    Args:
        database_url: Database connection string

    Returns:
        List of pending migration revision IDs

    Raises:
        SQLAlchemyError: If database connection fails
    """
    try:
        config = get_alembic_config(database_url)
        script = ScriptDirectory.from_config(config)

        # Get current database version
        current_rev = get_current_version(database_url)

        # Get all revisions from current to head
        if current_rev is None:
            # No migrations applied yet - all migrations are pending
            pending = [rev.revision for rev in script.walk_revisions()]
            # Reverse to get chronological order (oldest first)
            pending.reverse()
        else:
            # Get revisions between current and head
            pending = []
            for rev in script.iterate_revisions(current_rev, "head"):
                if rev.revision != current_rev:
                    pending.append(rev.revision)
            # Reverse to get chronological order
            pending.reverse()

        return pending

    except Exception as e:
        logger.error(f"Failed to get pending migrations: {e}")
        raise


def run_migrations(database_url: str) -> bool:
    """
    Run all pending Alembic migrations to latest version.

    This function is idempotent and safe to call on every application startup.
    It will:
    - Create alembic_version table if it doesn't exist
    - Apply all pending migrations in order
    - Skip if database is already up-to-date

    Args:
        database_url: Database connection string

    Returns:
        True if migrations successful (or no migrations needed)

    Raises:
        FileNotFoundError: If alembic.ini or migration files not found
        SQLAlchemyError: If database connection or query fails
        RuntimeError: If migration verification fails
        Exception: For unexpected errors during migration
    """
    try:
        # Get current version before migration
        try:
            current_version = get_current_version(database_url)
            version_desc = current_version if current_version else "<none>"
        except Exception:
            # Database might not have alembic_version table yet
            current_version = None
            version_desc = "<not initialized>"

        logger.info(f"Current database version: {version_desc}")

        # Get pending migrations
        try:
            pending = get_pending_migrations(database_url)
            if pending:
                logger.info(f"Found {len(pending)} pending migration(s): {', '.join(pending)}")
            else:
                logger.info("Database is up-to-date, no migrations needed")
                return True
        except Exception:
            # If we can't get pending migrations, assume we need to run upgrade
            logger.info("Unable to determine pending migrations, running upgrade...")
            pending = []

        # Run migrations
        logger.info("Running database migrations...")
        config = get_alembic_config(database_url)

        # Use upgrade command to apply all pending migrations
        try:
            command.upgrade(config, "head")
        except Exception as cmd_error:
            logger.error(f"Alembic upgrade command failed: {cmd_error}")
            raise

        # Verify migration success by checking new version
        # If we can't verify, raise exception - better safe than sorry
        new_version = get_current_version(database_url)
        if not new_version:
            raise RuntimeError(
                "Migration command succeeded but database has no version - "
                "alembic_version table may not have been created"
            )
        
        logger.info(f"Database migrations completed successfully. New version: {new_version}")
        return True

    except FileNotFoundError as e:
        logger.error(f"Migration configuration error: {e}", exc_info=True)
        raise

    except SQLAlchemyError as e:
        logger.error(f"Database error during migration: {e}", exc_info=True)
        logger.error("Migration failed - database may be in inconsistent state")
        raise

    except Exception as e:
        logger.error(f"Unexpected error during migration: {e}", exc_info=True)
        logger.error("Migration failed - database may be in inconsistent state")
        raise


def rollback_migration(database_url: str, steps: int = 1) -> bool:
    """
    Rollback the last N migrations.

    WARNING: This should only be used for development/testing or emergency rollback.
    In production, prefer creating forward-fixing migrations instead.

    Args:
        database_url: Database connection string
        steps: Number of migrations to roll back (default: 1)

    Returns:
        True if rollback successful (or nothing to rollback)

    Raises:
        SQLAlchemyError: If database connection or query fails
        Exception: For unexpected errors during rollback
    """
    current_version = get_current_version(database_url)
    if not current_version:
        logger.warning("No migrations to roll back")
        return True

    logger.warning(f"Rolling back {steps} migration(s) from version: {current_version}")

    try:
        config = get_alembic_config(database_url)
        command.downgrade(config, f"-{steps}")

        new_version = get_current_version(database_url)
        new_desc = new_version if new_version else "<none>"
        logger.info(f"Rollback completed. New version: {new_desc}")

        return True

    except Exception as e:
        logger.error(f"Rollback failed: {e}", exc_info=True)
        raise

