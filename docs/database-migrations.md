# Database Migrations with Alembic

This document describes TARSy's database migration system, which uses Alembic for automatic schema version control and updates.

## Overview

TARSy uses **Alembic** for database migrations to:
- Track database schema versions
- Apply schema changes automatically on startup
- Support both PostgreSQL and SQLite
- Enable rollback if needed
- Maintain data integrity during schema changes

### Architecture

```
Startup Flow:
  main.py
    └─> initialize_database()
          └─> run_migrations(database_url)
                ├─> Get current DB version
                ├─> Check for pending migrations
                ├─> Apply any pending migrations
                └─> Verify final version

Migration Files:
  backend/
    ├── alembic.ini              # Alembic configuration
    ├── alembic/
    │   ├── env.py               # Migration environment
    │   └── versions/            # Migration scripts
    │       ├── ae85467a75d2_initial_schema_baseline.py
    │       └── <future migrations>.py
    └── tarsy/database/
        └── migrations.py        # Programmatic migration runner
```

## Creating Migrations

### 1. Modify Your Models

Edit the SQLModel classes in `tarsy/models/`:

```python
# backend/tarsy/models/db_models.py
class AlertSession(SQLModel, table=True):
    # ... existing fields ...
    
    # Add new field
    resolution_notes: Optional[str] = Field(
        default=None,
        description="Notes about how the alert was resolved"
    )
```

### 2. Generate Migration

```bash
# From project root:
make migration msg="Add resolution_notes to AlertSession"

# Or from backend directory:
cd backend
uv run alembic revision --autogenerate -m "Add resolution_notes to AlertSession"
```

This creates a new file: `backend/alembic/versions/<revision>_add_resolution_notes_to_alertsession.py`

### 3. Review the Generated Migration

**IMPORTANT:** Always review auto-generated migrations before applying them!

```python
# backend/alembic/versions/<revision>_add_resolution_notes_to_alertsession.py

def upgrade() -> None:
    """Upgrade schema."""
    # Review these operations:
    op.add_column('alert_sessions', 
        sa.Column('resolution_notes', sa.String(), nullable=True))

def downgrade() -> None:
    """Downgrade schema."""
    # Review rollback operations:
    op.drop_column('alert_sessions', 'resolution_notes')
```

**Check for:**
- Correct table and column names
- Appropriate data types
- Nullable vs NOT NULL constraints
- Default values
- Any data transformations needed

### 4. Test the Migration Locally

```bash
# Apply migration
make migration-upgrade

# Verify it worked
make migration-status

# Test rollback
make migration-downgrade

# Re-apply
make migration-upgrade
```

### 5. Commit the Migration

```bash
git add backend/tarsy/models/db_models.py
git add backend/alembic/versions/<revision>_add_resolution_notes_to_alertsession.py
git commit -m "Add resolution_notes field to AlertSession"
```

## Manual Migrations (Data Transformations)

For complex changes that require data transformation:

### 1. Create Empty Migration

```bash
make migration-manual msg="Migrate alert_type values to new format"
```

### 2. Edit the Migration

```python
# backend/alembic/versions/<revision>_migrate_alert_type_values_to_new_format.py

def upgrade() -> None:
    """Transform alert_type data."""
    # Use Alembic's op object for raw SQL
    from sqlalchemy import text
    
    connection = op.get_bind()
    
    # Update existing data
    connection.execute(text("""
        UPDATE alert_sessions
        SET alert_type = 'namespace_terminating'
        WHERE alert_type = 'NamespaceTerminating'
    """))
    
    connection.execute(text("""
        UPDATE alert_sessions
        SET alert_type = 'out_of_sync_application'
        WHERE alert_type = 'OutOfSyncApplication'
    """))

def downgrade() -> None:
    """Reverse the transformation."""
    from sqlalchemy import text
    
    connection = op.get_bind()
    
    # Reverse the changes
    connection.execute(text("""
        UPDATE alert_sessions
        SET alert_type = 'NamespaceTerminating'
        WHERE alert_type = 'namespace_terminating'
    """))
    
    connection.execute(text("""
        UPDATE alert_sessions
        SET alert_type = 'OutOfSyncApplication'
        WHERE alert_type = 'out_of_sync_application'
    """))
```

### 3. Test Data Migration

```bash
# Apply with real data
make migration-upgrade

# Verify data was transformed correctly
# (Use database tool to inspect)

# Test rollback
make migration-downgrade

# Verify data was restored
```

## Makefile Commands

TARSy provides convenient Makefile targets for migration management:

```bash
# Generate migration from model changes
make migration msg="Your migration description"

# Create empty migration for manual changes
make migration-manual msg="Your migration description"

# Apply all pending migrations
make migration-upgrade

# Rollback last migration
make migration-downgrade

# Show current database version
make migration-status

# Show full migration history
make migration-history
```

## Deployment

### Automatic Migration on Startup

Migrations are applied **automatically** when TARSy starts:

```python
# This happens on every startup:
initialize_database()
  └─> run_migrations(database_url)
        └─> Applies any pending migrations
```

**What happens:**
1. TARSy starts
2. Checks current database version
3. Detects any pending migrations
4. Applies them in order
5. Verifies success
6. Continues startup

**If migration fails:**
- TARSy will **not start**
- Error logged with full traceback
- Database may be in inconsistent state
- Manual intervention required

### Zero-Downtime Deployments

For production zero-downtime deployments:

1. **Ensure migrations are backward-compatible** with the old code
2. **Deploy in two phases:**
   - Phase 1: Add new column (nullable), deploy new code
   - Phase 2: Make column required (if needed)

**Example:**

```python
# Migration 001: Add new field (nullable)
def upgrade():
    op.add_column('alert_sessions', 
        sa.Column('resolution_notes', sa.String(), nullable=True))

# Deploy new code (can handle both old and new schema)

# Migration 002: Make field required (optional)
def upgrade():
    op.alter_column('alert_sessions', 'resolution_notes',
        nullable=False, server_default='')
```

## Rollback Procedures

### Development/Staging

```bash
# Rollback last migration
make migration-downgrade

# Rollback multiple migrations
cd backend
uv run alembic downgrade -2  # Go back 2 versions

# Rollback to specific version
uv run alembic downgrade <revision_id>

# Rollback to beginning (DANGEROUS!)
uv run alembic downgrade base
```

### Production Rollback

**IMPORTANT:** In production, prefer **forward-fixing migrations** over rollback.

If you must rollback:

1. **Stop the application**
2. **Backup the database first**
   ```bash
   # PostgreSQL
   pg_dump mydb > backup_before_rollback.sql
   
   # SQLite
   cp history.db history.db.backup
   ```

3. **Run rollback**
   ```bash
   cd backend
   uv run alembic downgrade -1
   ```

4. **Verify database state**
5. **Deploy old application version**
6. **Test thoroughly**

### Why Forward-Fixing is Better

Instead of rolling back, create a new migration that fixes the issue:

```bash
# Instead of: alembic downgrade -1
# Do: make migration msg="Revert problematic change"

# This:
# - Keeps migration history clean
# - Works with continuous deployment
# - No need to stop the application
# - Safer for production
```

## Best Practices

### DO:
- ✅ Always review auto-generated migrations
- ✅ Test migrations locally before committing
- ✅ Test both upgrade and downgrade
- ✅ Use descriptive migration messages
- ✅ Keep migrations small and focused
- ✅ Add comments for complex transformations
- ✅ Test with production-like data volumes
- ✅ Backup before production migrations

### DON'T:
- ❌ Modify existing migration files after they're committed
- ❌ Skip testing downgrade() functions
- ❌ Create migrations that can't be rolled back
- ❌ Include unrelated changes in one migration
- ❌ Assume auto-generated migrations are always correct
- ❌ Roll back in production without a backup
- ❌ Manually modify the database without creating a migration

## Migration File Structure

```python
"""Migration description

Revision ID: ae85467a75d2
Revises: 
Create Date: 2025-10-02 20:33:15.353864

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = 'ae85467a75d2'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Operations to apply the migration
    pass


def downgrade() -> None:
    """Downgrade schema."""
    # Operations to reverse the migration
    pass
```

## References

- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLModel Documentation](https://sqlmodel.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [EP-0022: Database Migration System](./enhancements/pending/EP-0022-database-migrations-alembic.md)

## Getting Help

If you encounter issues not covered in this guide:

1. Check the logs: `backend/logs/tarsy.log`
2. View migration history: `make migration-history`
3. Check database version: `make migration-status`
4. Review EP-0022 for implementation details
5. Check Alembic documentation for advanced scenarios

