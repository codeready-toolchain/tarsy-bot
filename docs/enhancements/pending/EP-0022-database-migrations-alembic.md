# EP-0022: Database Migration System with Alembic

## Problem Statement

TARSy currently uses `SQLModel.metadata.create_all()` for database initialization, which has critical limitations:

1. **No version tracking**: Cannot determine current schema version
2. **No migration support**: Schema changes require manual DB updates or recreation
3. **No rollback capability**: Cannot revert schema changes
4. **Production risk**: Upgrading TARSy in production requires manual database coordination
5. **Data migration gap**: Cannot transform existing data during schema changes

This creates operational friction and risk when evolving the database schema.

## Design

### Architecture Overview

```
Startup Flow:
  main.py
    └─> initialize_database()
          ├─> run_migrations()
          │     └─> alembic upgrade head
          │           ├─> Fresh DB: Runs all migrations 001→N
          │           ├─> Existing DB: Runs pending migrations only
          │           └─> Up-to-date: No-op
          └─> test_database_connection()
```

### Core Components

#### 1. Alembic Configuration

**File: `backend/alembic.ini`**
- Database URL from settings (template-based)
- Migration script location: `backend/alembic/versions/`
- Logging configuration

**File: `backend/alembic/env.py`**
- Load TARSy settings
- Import all SQLModel table definitions
- Configure target metadata from SQLModel
- Support both online (PostgreSQL) and offline (SQLite) migrations

#### 2. Migration Runner

**Location: `backend/tarsy/database/migrations.py`** (new file)

```python
from alembic import command
from alembic.config import Config
from pathlib import Path

def run_migrations(database_url: str) -> bool:
    """
    Run all pending Alembic migrations to latest version.
    
    Args:
        database_url: Database connection string
        
    Returns:
        True if migrations successful, False otherwise
    """
    # Create Alembic config programmatically
    # Set sqlalchemy.url from parameter
    # Execute: command.upgrade(config, "head")
    # Handle PostgreSQL vs SQLite differences
```

#### 3. Integration Point

**Modified: `backend/tarsy/database/init_db.py`**

```python
def initialize_database() -> bool:
    settings = get_settings()
    
    if not settings.history_enabled:
        return True
    
    # Run migrations (handles both fresh and existing databases)
    success = run_migrations(settings.database_url)
    if not success:
        logger.error("Database migrations failed")
        return False
    
    return test_database_connection()
```

#### 4. Migration File Structure

```
backend/
  alembic/
    versions/
      001_initial_schema.py       # Baseline from current schema
      002_add_column_example.py   # Future migrations
    env.py                         # Alembic environment config
    script.py.mako                 # Migration template
  alembic.ini                      # Alembic configuration
```

### Migration Generation Workflow

#### Adding a New Column (Example)

**Step 1: Modify the SQLModel**
```python
# backend/tarsy/models/db_models.py
class AlertSession(SQLModel, table=True):
    # ... existing fields ...
    
    # NEW: Add your field
    resolution_notes: Optional[str] = Field(
        default=None,
        description="Notes about how the alert was resolved"
    )
```

**Step 2: Generate Migration**
```bash
make migration msg="Add resolution_notes to AlertSession"
```

This creates: `backend/alembic/versions/003_add_resolution_notes_to_alertsession.py`

**Step 3: Review Generated Migration**
```python
# backend/alembic/versions/003_add_resolution_notes_to_alertsession.py
def upgrade() -> None:
    op.add_column('alert_sessions', 
        sa.Column('resolution_notes', sa.String(), nullable=True))

def downgrade() -> None:
    op.drop_column('alert_sessions', 'resolution_notes')
```

Verify:
- ✓ Column name correct
- ✓ Type correct (String, Integer, etc.)
- ✓ Nullable/default correct
- ✓ Downgrade reverses the change

**Step 4: Test Migration Locally**
```bash
# Apply migration
make migration-upgrade

# Verify in database
# PostgreSQL: \d alert_sessions
# SQLite: .schema alert_sessions

# Test rollback
make migration-downgrade

# Re-apply
make migration-upgrade
```

**Step 5: Test Application**
```bash
# Start TARSy - migration runs automatically
make dev

# Verify:
# - Application starts successfully
# - New field accessible in code
# - No errors in logs
```

**Step 6: Commit**
```bash
git add backend/tarsy/models/db_models.py
git add backend/alembic/versions/003_*.py
git commit -m "Add resolution_notes field to AlertSession"
```

**Step 7: Deploy**
```bash
# On deployment/restart, TARSy automatically:
# 1. Detects pending migration (002 → 003)
# 2. Runs: alembic upgrade head
# 3. Applies the new column
# 4. Starts normally
```

#### Manual Migration (Data Transformation)

For complex changes requiring data manipulation:

**Step 1: Create Empty Migration**
```bash
make migration-manual msg="Migrate alert_type values to new format"
```

**Step 2: Edit Migration Manually**
```python
def upgrade() -> None:
    # Change schema
    op.add_column('alert_sessions', sa.Column('alert_category', sa.String()))
    
    # Transform data
    connection = op.get_bind()
    connection.execute(text("""
        UPDATE alert_sessions 
        SET alert_category = CASE
            WHEN alert_type LIKE 'k8s_%' THEN 'kubernetes'
            WHEN alert_type LIKE 'argocd_%' THEN 'argocd'
            ELSE 'general'
        END
    """))
    
    # Remove old column
    op.drop_column('alert_sessions', 'alert_type')

def downgrade() -> None:
    # Reverse the process
    op.add_column('alert_sessions', sa.Column('alert_type', sa.String()))
    # ... reverse data transformation ...
    op.drop_column('alert_sessions', 'alert_category')
```

**Step 3: Test thoroughly** (same as above)

### Database Support

**PostgreSQL:**
- Full support for all Alembic features
- Online migrations (with active connections)
- Concurrent index creation support

**SQLite:**
- Batch mode for ALTER TABLE limitations (automatic)
- Special handling for column renames/drops (automatic)
- Same automatic migration execution as PostgreSQL

### Version Tracking

Alembic creates `alembic_version` table automatically:
```sql
CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);
```

Stores current schema version (e.g., `"002_add_column_example"`).

## Implementation Plan

### Phase 1: Setup & Configuration
1. Ensure virtual environment exists:
   ```bash
   cd backend
   make install  # Creates .venv if needed via 'uv sync'
   ```
2. Add Alembic to dependencies:
   ```bash
   uv add alembic
   ```
   This updates `pyproject.toml` and `uv.lock` automatically
3. Initialize Alembic:
   ```bash
   source .venv/bin/activate  # Activate venv
   alembic init alembic       # Initialize Alembic structure
   ```
4. Configure `alembic.ini`:
   - Set `sqlalchemy.url` placeholder
   - Configure logging integration
5. Configure `alembic/env.py`:
   - Import `tarsy.config.settings.get_settings()`
   - Import all models: `from tarsy.models.db_models import *`
   - Import unified models: `from tarsy.models.unified_interactions import *`
   - Set `target_metadata = SQLModel.metadata`
   - Handle PostgreSQL vs SQLite in `run_migrations_online()`

### Phase 2: Makefile Integration
1. Create `make/db.mk` with migration targets:
   ```makefile
   migration:          # Generate migration from model changes
   migration-manual:   # Create empty migration for manual changes
   migration-upgrade:  # Apply pending migrations
   migration-downgrade:# Rollback last migration
   migration-status:   # Show current version
   migration-history:  # Show migration history
   ```
2. Add to root `Makefile`:
   ```makefile
   include make/db.mk
   ```
3. Test targets:
   ```bash
   make migration msg="Test migration"
   make migration-status
   ```

### Phase 3: Baseline Migration
1. Create initial migration from current schema:
   ```bash
   make migration msg="Initial schema baseline"
   ```
2. Review generated migration in `alembic/versions/001_*.py`
3. Test migration on clean database:
   ```bash
   make migration-upgrade   # SQLite test
   make migration-downgrade
   make migration-upgrade   # PostgreSQL test
   ```
4. Verify schema matches current `create_all()` output

### Phase 4: Migration Runner
1. Create `backend/tarsy/database/migrations.py`:
   ```python
   def get_alembic_config(database_url: str) -> Config
   def run_migrations(database_url: str) -> bool
   def get_current_version(database_url: str) -> Optional[str]
   def get_pending_migrations(database_url: str) -> list[str]
   ```
2. Implement programmatic Alembic execution
3. Add error handling and logging
4. Support both PostgreSQL and SQLite

### Phase 5: Integration
1. Modify `backend/tarsy/database/init_db.py`:
   - Import `from tarsy.database.migrations import run_migrations`
   - Replace `create_database_tables()` logic with `run_migrations()`
2. Add startup logging:
   ```
   INFO: Running database migrations...
   INFO: Current version: 001_initial_schema
   INFO: Applying migration: 002_add_field_x
   INFO: Database migrations completed successfully
   ```
3. Test startup with:
   - Fresh database (no tables) - runs all migrations from scratch
   - Existing database (current schema) - no migrations needed
   - Database with pending migrations - runs only pending migrations

### Phase 6: Documentation & Testing
1. Create `backend/docs/database-migrations.md`:
   - How to create migrations
   - How to test migrations
   - Rollback procedures
   - Troubleshooting
2. Add unit tests:
   - `tests/unit/database/test_migrations.py`
   - Test migration runner functions
   - Test error handling
3. Add integration test:
   - `tests/integration/test_database_migrations.py`
   - Test full migration cycle
   - Test upgrade/downgrade
4. Update `backend/README.md` with migration workflow

### Phase 7: Production Preparation
1. Add migration health check to `/system/info` endpoint:
   ```json
   {
     "database": {
       "schema_version": "002_add_field_x",
       "pending_migrations": []
     }
   }
   ```
2. Create migration testing procedure for staging environment
3. Document rollback procedure:
   ```bash
   # Rollback one migration
   alembic downgrade -1
   
   # Rollback to specific version
   alembic downgrade <revision>
   ```
4. Add migration pre-check to deployment process
5. Add validation that ensures migrations are up-to-date
6. Consider adding pre-deployment migration check in CI/CD

## Technical Notes

### Model Import Requirements
All SQLModel tables must be imported in `alembic/env.py`:
```python
from tarsy.models.db_models import AlertSession, StageExecution
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
```

### Configuration Template
`alembic.ini` uses placeholder for database URL:
```ini
sqlalchemy.url = driver://user:pass@localhost/dbname
```

Runtime override in `env.py`:
```python
config.set_main_option('sqlalchemy.url', get_settings().database_url)
```

### SQLite Batch Mode (Automatic)
Alembic automatically handles SQLite's ALTER TABLE limitations using batch mode.

When you run `make migration msg="..."`, Alembic auto-generates the correct code:
```python
# For SQLite, Alembic automatically wraps in batch mode:
with op.batch_alter_table('alert_sessions') as batch_op:
    batch_op.add_column(sa.Column('new_field', sa.String()))
    
# This works transparently - no manual intervention needed
```

Behind the scenes:
1. Creates temporary table with new schema
2. Copies all existing data
3. Drops old table
4. Renames temp table

**You don't need to do anything special** - batch mode is automatic for SQLite.

### Concurrent Migrations
Alembic uses database locks to prevent concurrent migrations. Safe for multi-instance deployments.

### Testing Strategy
1. Unit tests: Migration runner logic
2. Integration tests: Full upgrade/downgrade cycles
3. E2E tests: Application startup with migrations
4. Manual testing: Production-like scenario in staging

