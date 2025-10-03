"""Integration tests for the Alembic database migration system.

These tests verify the full migration lifecycle using a real SQLite database.
"""

import tempfile
from pathlib import Path
from typing import Generator

import pytest
from sqlalchemy import inspect, text
from sqlmodel import Session, create_engine

from tarsy.database.migrations import (
    get_current_version,
    get_pending_migrations,
    rollback_migration,
    run_migrations,
)


@pytest.fixture
def temp_database() -> Generator[str, None, None]:
    """
    Create a temporary database for testing.
    
    Yields:
        Database URL for the temporary database
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
        db_path = Path(tmp_file.name)
        database_url = f"sqlite:///{db_path}"
        
        yield database_url
        
        # Cleanup
        try:
            db_path.unlink(missing_ok=True)
        except Exception:
            pass


@pytest.mark.integration
class TestMigrationLifecycle:
    """Test the complete migration lifecycle with a real database."""

    def test_fresh_database_initialization(self, temp_database: str) -> None:
        """Test that migrations work correctly on a fresh database."""
        # Fresh database should have no version
        current_version = get_current_version(temp_database)
        assert current_version is None, "Fresh database should have no version"

        # Should have pending migrations
        pending = get_pending_migrations(temp_database)
        assert len(pending) > 0, "Fresh database should have pending migrations"

        # Run migrations
        success = run_migrations(temp_database)
        assert success, "Migration should succeed"

        # Should now have a version
        current_version = get_current_version(temp_database)
        assert current_version is not None, "Database should have version after migration"

        # No more pending migrations
        pending = get_pending_migrations(temp_database)
        assert len(pending) == 0, "Should have no pending migrations after upgrade"

        # Verify alembic_version table exists
        engine = create_engine(temp_database)
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "alembic_version" in tables, "alembic_version table should exist"

    def test_idempotent_migrations(self, temp_database: str) -> None:
        """Test that running migrations multiple times is safe."""
        # First migration
        success = run_migrations(temp_database)
        assert success

        version1 = get_current_version(temp_database)

        # Second migration (should be no-op)
        success = run_migrations(temp_database)
        assert success

        version2 = get_current_version(temp_database)
        assert version1 == version2, "Version should not change on second migration"

    def test_rollback_migration(self, temp_database: str) -> None:
        """Test that rollback works correctly."""
        # Apply migrations
        success = run_migrations(temp_database)
        assert success

        initial_version = get_current_version(temp_database)
        assert initial_version is not None

        # Rollback one step
        success = rollback_migration(temp_database, steps=1)
        assert success

        # Version should have changed (or be None if at base)
        new_version = get_current_version(temp_database)
        # If we're at base, version will be None
        # Otherwise, it should be different from initial
        if new_version is not None:
            assert new_version != initial_version, "Version should change after rollback"

    def test_migration_creates_expected_tables(self, temp_database: str) -> None:
        """Test that migrations create the expected database schema."""
        # Run migrations
        success = run_migrations(temp_database)
        assert success

        # Verify expected tables exist
        engine = create_engine(temp_database)
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        # alembic_version should always exist after migration
        assert "alembic_version" in tables, "alembic_version table should exist"
        
        # NOTE: The baseline migration (ae85467a75d2) is empty because it was
        # generated when the database already had all tables. Future migrations
        # will add the actual schema. This test verifies the migration system
        # works, not the specific schema content.

    def test_database_integrity_after_migration(self, temp_database: str) -> None:
        """Test that the database is functional after migration."""
        # Run migrations
        success = run_migrations(temp_database)
        assert success

        # Try to execute a simple query to verify integrity
        engine = create_engine(temp_database)
        with Session(engine) as session:
            result = session.exec(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).all()
            assert len(result) > 0, "Should be able to query database structure"

            # Verify we can query the version table
            result = session.exec(text("SELECT version_num FROM alembic_version")).all()
            assert len(result) == 1, "Should have exactly one version record"


@pytest.mark.integration
class TestMigrationErrorCases:
    """Test error handling in migration scenarios."""

    def test_migration_with_invalid_database_url(self) -> None:
        """Test that invalid database URLs are handled properly."""
        invalid_url = "invalid://not/a/real/database"

        with pytest.raises(Exception):
            run_migrations(invalid_url)

    def test_get_version_with_nonexistent_database(self) -> None:
        """Test getting version from a non-existent SQLite database.
        
        NOTE: SQLite creates an empty database file if it doesn't exist,
        so this returns None (no version) rather than raising an exception.
        This is expected SQLite behavior.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=True) as tmp_file:
            nonexistent_url = f"sqlite:///{tmp_file.name}_nonexistent"
            
            # SQLite will create the DB, so this returns None (no version yet)
            version = get_current_version(nonexistent_url)
            assert version is None, "Non-existent DB should have no version"

    def test_rollback_on_fresh_database(self, temp_database: str) -> None:
        """Test that rollback on a fresh database is safe."""
        # Try to rollback before any migrations
        success = rollback_migration(temp_database, steps=1)
        # This should succeed but do nothing (logged as warning)
        assert success


@pytest.mark.integration
class TestMigrationVersioning:
    """Test migration version tracking and management."""

    def test_version_progression(self, temp_database: str) -> None:
        """Test that version progresses correctly through migration lifecycle."""
        # Track version changes
        versions: list[str | None] = []

        # Initial state
        versions.append(get_current_version(temp_database))
        assert versions[-1] is None, "Fresh database should have no version"

        # After migration
        run_migrations(temp_database)
        versions.append(get_current_version(temp_database))
        assert versions[-1] is not None, "Should have version after migration"

        # Re-running migration (should not change version)
        run_migrations(temp_database)
        versions.append(get_current_version(temp_database))
        assert versions[-1] == versions[-2], "Re-running should not change version"

    def test_pending_migrations_tracking(self, temp_database: str) -> None:
        """Test that pending migrations are tracked correctly."""
        # Fresh database should have pending migrations
        initial_pending = get_pending_migrations(temp_database)
        assert len(initial_pending) > 0, "Should have pending migrations initially"

        # After migration, should have none
        run_migrations(temp_database)
        after_pending = get_pending_migrations(temp_database)
        assert len(after_pending) == 0, "Should have no pending migrations after upgrade"

