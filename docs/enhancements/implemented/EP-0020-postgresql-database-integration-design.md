# EP-0020: PostgreSQL Database Integration - Design Document

**Status:** Approved  
**Created:** 2025-09-17  
**Phase:** Design Complete
**Requirements Document:** N/A (Self-contained design proposal)
**Depends On:** EP-0019 (Docker Deployment Infrastructure)
**Next Phase:** Implementation

---

## Design Overview

This enhancement introduces PostgreSQL database support for Tarsy's history service while maintaining SQLite as the default option. The design provides flexible database configuration allowing users to choose between SQLite (default) and PostgreSQL (optional) based on their specific needs. This EP extends the container deployment infrastructure from EP-0019 to support PostgreSQL in containerized environments.

### Architecture Summary

The dual database support provides:
1. **Default SQLite**: Simple, file-based database requiring no additional infrastructure
2. **Optional PostgreSQL**: Advanced database with connection pooling and optimization features
3. **Configuration-Driven Selection**: Database type determined by connection string format
4. **Environment Agnostic**: Both options work in any environment (dev, testing, production)

### Key Design Principles

- **SQLite by Default**: Zero-configuration database that works out of the box
- **PostgreSQL When Needed**: Optional upgrade for advanced features and scale
- **Production Recommendation**: PostgreSQL is recommended for production deployments
- **Database Agnostic Models**: Leverage SQLModel's cross-database compatibility
- **Configuration Simplicity**: Minimal configuration required for common use cases
- **Performance Options**: Optimized configurations available for each database type
- **Container Integration**: Extends EP-0019 Docker infrastructure for PostgreSQL container deployment

## System Architecture

### Database Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Tarsy Database Layer                     │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Application Layer                      │    │
│  │  ┌─────────────────┐    ┌─────────────────┐         │    │
│  │  │   History       │    │   Dashboard     │         │    │
│  │  │   Service       │    │   Service       │         │    │
│  │  └─────────────────┘    └─────────────────┘         │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Database Abstraction Layer             │    │
│  │  ┌─────────────────┐    ┌─────────────────┐         │    │
│  │  │   SQLModel      │    │   SQLAlchemy    │         │    │
│  │  │   (ORM)         │    │   (Engine)      │         │    │
│  │  └─────────────────┘    └─────────────────┘         │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Database Configuration                 │    │
│  │  ┌─────────────────┐                                │    │
│  │  │   Connection    │  ┌─────────┐ ┌─────────────┐   │    │
│  │  │   String        │──│ SQLite  │ │ PostgreSQL  │   │    │
│  │  │   Parser        │  │ Default │ │ Optional    │   │    │
│  │  └─────────────────┘  └─────────┘ └─────────────┘   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                Database Storage Options                │ │
│  │                                                        │ │
│  │  ┌──────────────────────────────────────────────────┐  │ │
│  │  │              Default Option                      │  │ │
│  │  │  ┌─────────────┐  ┌─────────────────────────────┐│  │ │
│  │  │  │ SQLite File │  │ In-Memory (Testing)         ││  │ │
│  │  │  │ Default     │  │ sqlite:///:memory:          ││  │ │
│  │  │  │ history.db  │  │ pytest runs                 ││  │ │
│  │  │  └─────────────┘  └─────────────────────────────┘│  │ │
│  │  └──────────────────────────────────────────────────┘  │ │
│  │                                                        │ │
│  │  ┌─────────────────────────────────────────────────┐   │ │
│  │  │              Optional Upgrade                   │   │ │
│  │  │  ┌─────────────────────────────────────────────┐│   │ │
│  │  │  │ PostgreSQL (Advanced Features)              ││   │ │
│  │  │  │ postgresql://user:pass@host:port/database   ││   │ │
│  │  │  │ - Connection pooling                        ││   │ │
│  │  │  │ - Advanced indexing                         ││   │ │
│  │  │  │ - High concurrency                          ││   │ │
│  │  │  └─────────────────────────────────────────────┘│   │ │
│  │  └─────────────────────────────────────────────────┘   │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Component Architecture

#### New Components

- **Database Type Detection**: Automatic detection of database type from connection string
- **PostgreSQL Connection Validation**: Enhanced connection testing for PostgreSQL-specific features

#### Modified Components

- **Settings Configuration**: Extended to support PostgreSQL connection parameters and pooling options
- **Database Initialization**: Enhanced to handle PostgreSQL-specific setup requirements
- **Connection Management**: Improved error handling and validation for different database types

#### Component Interactions

1. Application starts and loads settings configuration
2. Database type is detected from connection string format
3. Appropriate database engine is created with type-specific optimizations
4. Schema creation uses SQLModel's cross-database compatibility
5. Connection validation ensures database is accessible and properly configured
6. Application services use the same SQLModel interface regardless of underlying database

## Configuration Design

### Configuration Options

```bash
# Default SQLite (works in any environment)
HISTORY_DATABASE_URL=""  # Empty = use default SQLite (history.db)

# Explicit SQLite configuration
HISTORY_DATABASE_URL="sqlite:///history.db"
HISTORY_DATABASE_URL="sqlite:///./data/tarsy_history.db"  # Custom path

# Testing with in-memory SQLite
HISTORY_DATABASE_URL="sqlite:///:memory:"  # RAM-only, no file persistence

# Optional PostgreSQL upgrade
HISTORY_DATABASE_URL="postgresql://username:password@localhost:5432/tarsy_history"
HISTORY_DATABASE_URL="postgresql+psycopg2://user:pass@localhost/tarsy"

# PostgreSQL with advanced features
HISTORY_DATABASE_URL="postgresql://user:pass@localhost/tarsy?pool_size=10&max_overflow=20"
HISTORY_DATABASE_URL="postgresql://user:pass@localhost/tarsy?sslmode=require"
```

#### Settings.py Configuration

```python
class Settings(BaseSettings):
    # History Service Configuration
    history_database_url: str = Field(
        default="",
        description="Database connection string for alert processing history"
    )
    history_enabled: bool = Field(
        default=True,
        description="Enable/disable history capture for alert processing"
    )
    history_retention_days: int = Field(
        default=90,
        description="Number of days to retain alert processing history data"
    )
    
    # NEW: PostgreSQL-specific configuration
    postgres_pool_size: int = Field(
        default=5,
        description="PostgreSQL connection pool size"
    )
    postgres_max_overflow: int = Field(
        default=10,
        description="PostgreSQL connection pool max overflow"
    )
    postgres_pool_timeout: int = Field(
        default=30,
        description="PostgreSQL connection pool timeout in seconds"
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set default database URL if not explicitly provided
        if not self.history_database_url:
            if is_testing():
                # Use in-memory database for tests by default
                self.history_database_url = "sqlite:///:memory:"
            else:
                # Use SQLite file database by default (works everywhere)
                self.history_database_url = "sqlite:///history.db"
```

### Configuration Examples

#### Default SQLite Setup (.env)

```bash
# Minimal setup (uses SQLite by default)
HISTORY_ENABLED=true
# No HISTORY_DATABASE_URL needed - defaults to SQLite

# Custom SQLite configuration
HISTORY_DATABASE_URL="sqlite:///./data/tarsy_history.db"
HISTORY_RETENTION_DAYS=90
```

#### Optional PostgreSQL Setup (.env)

```bash
# PostgreSQL configuration (when advanced features needed)
HISTORY_DATABASE_URL="postgresql://tarsy_user:secure_password@postgres-server:5432/tarsy_history"
HISTORY_ENABLED=true
HISTORY_RETENTION_DAYS=90

# PostgreSQL optimization settings
POSTGRES_POOL_SIZE=10
POSTGRES_MAX_OVERFLOW=20
POSTGRES_POOL_TIMEOUT=30
```

## Data Design

### Database Schema Compatibility

The existing SQLModel schema is already compatible with both SQLite and PostgreSQL:

```python
class AlertSession(SQLModel, table=True):
    """
    Cross-database compatible model using SQLModel.
    Works with both SQLite and PostgreSQL without modifications.
    """
    __tablename__ = "alert_sessions"
    
    # Database-agnostic indexes
    __table_args__ = (
        # Standard indexes work on both databases
        Index('ix_alert_sessions_status', 'status'),
        Index('ix_alert_sessions_agent_type', 'agent_type'), 
        Index('ix_alert_sessions_alert_type', 'alert_type'),
        Index('ix_alert_sessions_status_started_at', 'status', 'started_at_us'),
        
        # PostgreSQL-specific optimizations (ignored by SQLite)
        # Can be added conditionally based on database type
    )
    
    session_id: str = Field(primary_key=True)
    alert_id: str = Field(unique=True, index=True)
    alert_data: dict = Field(default_factory=dict, sa_column=Column(JSON))
    # ... rest of fields remain unchanged
```

### Database Compatibility

The existing indexes are designed to work optimally with both SQLite and PostgreSQL without modification. No additional PostgreSQL-specific indexes are needed - the current schema provides good performance for typical alert history queries on both database systems.

#### Connection Pool Configuration

```python
def create_database_engine(database_url: str, settings: Settings):
    """Create database engine with appropriate configuration for database type."""
    
    if database_url.startswith('postgresql'):
        # PostgreSQL-specific configuration
        return create_engine(
            database_url,
            echo=False,
            pool_size=settings.postgres_pool_size,
            max_overflow=settings.postgres_max_overflow,
            pool_timeout=settings.postgres_pool_timeout,
            pool_pre_ping=True,  # Validate connections before use
            # PostgreSQL-specific optimizations
            connect_args={
                "application_name": "tarsy",
                "options": "-c timezone=UTC"
            }
        )
    else:
        # SQLite configuration (existing)
        return create_engine(
            database_url,
            echo=False,
            # SQLite-specific settings
            connect_args={"check_same_thread": False} if "sqlite" in database_url else {}
        )
```

## Implementation Design

### Database Initialization Updates

```python
# Enhanced init_db.py
import logging
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlmodel import Session, SQLModel, create_engine, text

def detect_database_type(database_url: str) -> str:
    """Detect database type from connection URL."""
    parsed = urlparse(database_url)
    scheme = parsed.scheme.lower()
    
    if scheme.startswith('postgresql'):
        return 'postgresql'
    elif scheme.startswith('sqlite'):
        return 'sqlite'
    else:
        raise ValueError(f"Unsupported database scheme: {scheme}")

def create_database_engine(database_url: str, settings: Settings):
    """Create database engine with type-specific configuration."""
    db_type = detect_database_type(database_url)
    
    if db_type == 'postgresql':
        return create_engine(
            database_url,
            echo=False,
            pool_size=settings.postgres_pool_size,
            max_overflow=settings.postgres_max_overflow,
            pool_timeout=settings.postgres_pool_timeout,
            pool_pre_ping=True,
            connect_args={
                "application_name": "tarsy",
                "options": "-c timezone=UTC"
            }
        )
    else:  # SQLite
        return create_engine(
            database_url,
            echo=False,
            connect_args={"check_same_thread": False}
        )

def create_database_tables(database_url: str, settings: Settings) -> bool:
    """Create database tables with type-specific optimizations."""
    try:
        engine = create_database_engine(database_url, settings)
        db_type = detect_database_type(database_url)
        
        # Create base tables (works for both databases)
        SQLModel.metadata.create_all(engine)
        
        # Test connection
        with Session(engine) as session:
            session.exec(text("SELECT 1")).first()
        
        logger.info(f"Database tables created successfully for {db_type}: {database_url.split('/')[-1]}")
        return True
        
    except Exception as e:
        logger.error(f"Database table creation failed: {str(e)}")
        return False

```


## Testing Strategy

### Unit Testing

```python
# Enhanced database testing
import pytest
from tarsy.database.init_db import detect_database_type, create_database_engine

def test_database_type_detection():
    """Test database type detection from URLs."""
    assert detect_database_type("sqlite:///test.db") == "sqlite"
    assert detect_database_type("sqlite:///:memory:") == "sqlite"
    assert detect_database_type("postgresql://user:pass@localhost/db") == "postgresql"
    assert detect_database_type("postgresql+psycopg2://user:pass@localhost/db") == "postgresql"

def test_sqlite_engine_creation(test_settings):
    """Test SQLite engine creation."""
    engine = create_database_engine("sqlite:///:memory:", test_settings)
    assert engine is not None
    assert "sqlite" in str(engine.url)

@pytest.mark.skipif(not os.getenv("TEST_POSTGRESQL_URL"), reason="PostgreSQL not available")
def test_postgresql_engine_creation(test_settings):
    """Test PostgreSQL engine creation (only if PostgreSQL available)."""
    postgres_url = os.getenv("TEST_POSTGRESQL_URL")
    engine = create_database_engine(postgres_url, test_settings)
    assert engine is not None
    assert "postgresql" in str(engine.url)
```

### Integration Testing

```python
@pytest.fixture(scope="session") 
def postgres_test_database():
    """Create temporary PostgreSQL database for testing."""
    if not os.getenv("TEST_POSTGRESQL_URL"):
        pytest.skip("PostgreSQL not available for testing")
    
    yield os.getenv("TEST_POSTGRESQL_URL")

def test_cross_database_compatibility(sqlite_session, postgres_session):
    """Test that same operations work on both databases."""
    for session in [sqlite_session, postgres_session]:
        # Test CRUD operations
        alert_session = AlertSession(
            session_id="test-session",
            alert_id="test-alert",
            alert_data={"severity": "high"},
            agent_type="kubernetes",
            status="completed"
        )
        
        session.add(alert_session)
        session.commit()
        
        # Test retrieval
        retrieved = session.get(AlertSession, "test-session")
        assert retrieved is not None
        assert retrieved.alert_data["severity"] == "high"
```

## Error Handling & Resilience

### Error Handling Strategy

Database errors should preserve the original exception details for debugging purposes. The application will log the full error details and surface meaningful error information without masking the underlying technical details.

```python
def initialize_database() -> bool:
    """Initialize database with proper error handling and logging."""
    try:
        settings = get_settings()
        
        if not settings.history_enabled:
            logger.info("History service disabled - skipping database initialization")
            return True
        
        success = create_database_tables(settings.history_database_url, settings)
        
        if not success:
            # Log the actual error details for debugging
            logger.error("Database initialization failed - check logs for details")
            
        return success
        
    except Exception as e:
        # Preserve original error for debugging
        logger.error(f"Database initialization error: {type(e).__name__}: {str(e)}")
        raise  # Re-raise to preserve stack trace
```

### Connection Recovery

```python
class DatabaseHealthChecker:
    """Monitor database health and handle reconnection."""
    
    def __init__(self, database_url: str, settings: Settings):
        self.database_url = database_url
        self.settings = settings
        self.db_type = detect_database_type(database_url)
    
    async def check_connection(self) -> bool:
        """Check database connection health."""
        try:
            engine = create_database_engine(self.database_url, self.settings)
            with Session(engine) as session:
                session.exec(text("SELECT 1")).first()
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    async def wait_for_database(self, max_retries: int = 30) -> bool:
        """Wait for database to become available (useful for container startup)."""
        for attempt in range(max_retries):
            if await self.check_connection():
                return True
            
            wait_time = min(2 ** attempt, 30)  # Exponential backoff, max 30s
            logger.info(f"Database not ready, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait_time)
        
        return False
```

## Docker Integration

For containerized PostgreSQL testing and deployment, this design integrates with the Docker deployment infrastructure defined in **EP-0019: Docker Deployment Infrastructure**.

### PostgreSQL Container Configuration

EP-0019 provides the base container deployment infrastructure. To add PostgreSQL support:

#### Extended Podman Compose Configuration
```yaml
# podman-compose.postgres.yml (extends EP-0019 base configuration)
version: '3.8'
services:
  tarsy-backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - HISTORY_DATABASE_URL=postgresql://tarsy:dev_password@postgres:5432/tarsy
      - POSTGRES_POOL_SIZE=5
      - POSTGRES_MAX_OVERFLOW=10
    depends_on:
      postgres:
        condition: service_healthy
    
  tarsy-frontend:
    build:
      context: ./dashboard
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    depends_on:
      - tarsy-backend
      
  postgres:
    image: mirror.gcr.io/library/postgres:15-alpine
    environment:
      - POSTGRES_DB=tarsy
      - POSTGRES_USER=tarsy
      - POSTGRES_PASSWORD=dev_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_dev_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tarsy -d tarsy"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_dev_data:
```

### Extended Make Targets

Extend the EP-0019 make targets with PostgreSQL-specific commands:

```makefile
# PostgreSQL deployment targets (extends EP-0019)
deploy-postgres: build-images ## Deploy with PostgreSQL for testing using podman-compose
	@echo "$(GREEN)Deploying Tarsy with PostgreSQL...$(NC)"
	podman-compose -f podman-compose.postgres.yml up -d
	@echo "$(YELLOW)Waiting for PostgreSQL to be ready...$(NC)"
	@sleep 10
	@echo "$(BLUE)Tarsy frontend: http://localhost:3000$(NC)"
	@echo "$(BLUE)Backend API: http://localhost:8000$(NC)"
	@echo "$(BLUE)PostgreSQL: localhost:5432$(NC)"

container-logs-postgres: ## Show PostgreSQL container logs
	@echo "$(GREEN)PostgreSQL container logs:$(NC)"
	-podman-compose -f podman-compose.postgres.yml logs postgres --tail=50 2>/dev/null || echo "PostgreSQL container not running"
```

### PostgreSQL Testing Workflow

Using the EP-0019 infrastructure with PostgreSQL extensions:

```bash
# Test PostgreSQL Integration
make deploy-postgres

# Check PostgreSQL connectivity (wait for container to be ready)
sleep 15
podman exec -it $(podman ps -q --filter ancestor=mirror.gcr.io/library/postgres:15-alpine) psql -U tarsy -d tarsy -c "\dt"

# Check PostgreSQL specific logs
make container-logs-postgres

# Stop and clean up
make clean-containers
```

## Documentation Requirements

### Configuration Documentation

- Environment variable reference with examples
- PostgreSQL connection string formats and options
- Performance tuning recommendations for PostgreSQL
- Migration guide for switching from SQLite to PostgreSQL

---

## Implementation Checklist

### Phase 1: Core PostgreSQL Support
- [ ] Enhanced database type detection
- [ ] PostgreSQL-specific engine configuration
- [ ] Connection pool settings
- [ ] Updated initialization logic
- [ ] Cross-database testing suite

### Phase 2: Container Integration (Extends EP-0019)
- [ ] PostgreSQL container configuration
- [ ] Extended podman-compose.postgres.yml
- [ ] PostgreSQL-specific make targets
- [ ] Container health checks and initialization
- [ ] Integration testing with EP-0019 infrastructure

### Phase 3: Production Features
- [ ] Database health checking
- [ ] Enhanced error handling
- [ ] Performance monitoring integration
- [ ] PostgreSQL-specific optimizations

---

## Next Steps

After design approval:
1. **Prerequisite**: Ensure EP-0019 (Docker Deployment Infrastructure) is implemented
2. Create Implementation Plan: `docs/enhancements/pending/EP-0020-implementation.md`
3. Update backend dependencies to include PostgreSQL drivers
4. Enhance testing suite for cross-database compatibility
5. Extend EP-0019 container configurations with PostgreSQL support

**AI Prompt for Next Phase:**
```
Create an implementation plan using the template at docs/templates/ep-implementation-template.md for EP-0020 based on the approved design in this document, ensuring integration with EP-0019 Docker infrastructure.
```
