"""
Global pytest configuration and fixtures for all tests.

This module provides common fixtures and configuration for both unit and integration tests,
ensuring proper test isolation and database handling.
"""

import os
import types
from pathlib import Path
from typing import Generator
from unittest.mock import Mock, patch, AsyncMock

import pytest
from sqlmodel import Session, SQLModel, create_engine

# Set testing environment variable as early as possible
os.environ["TESTING"] = "true"

# JWT service mocking for unit/integration tests only (NOT E2E tests)
# E2E tests need real JWT validation with dev keys
import sys
from unittest.mock import Mock

# Create a mock JWT service module to replace the real one (unit tests only)
mock_jwt_service = Mock()
mock_jwt_service.verify_jwt_token = Mock(return_value={
    "sub": "test_user_123",
    "username": "test-user",
    "email": "test@example.com",
    "avatar_url": "https://github.com/test.png",
    "iss": "tarsy-test",
    "iat": 1234567890,
    "exp": 1234567890 + 3600
})
mock_jwt_service.create_user_jwt_token = Mock(return_value="mock_jwt_token")
mock_jwt_service.create_service_account_jwt_token = Mock(return_value="mock_service_jwt_token")

# Mock the JWTService class to return our mock instance (unit tests only)
class MockJWTService:
    def __init__(self, *args, **kwargs):
        pass
    
    def verify_jwt_token(self, token):
        return {
            "sub": "test_user_123",
            "username": "test-user",
            "email": "test@example.com",
            "avatar_url": "https://github.com/test.png",
            "iss": "tarsy-test",
            "iat": 1234567890,
            "exp": 1234567890 + 3600
        }
    
    def create_user_jwt_token(self, *args, **kwargs):
        return "mock_jwt_token"
    
    def create_service_account_jwt_token(self, *args, **kwargs):
        return "mock_service_jwt_token"

# Apply JWT mocking at module level for unit/integration tests
# E2E tests will override this in their conftest.py to use real JWT validation
mock_jwt_module = types.ModuleType('tarsy.services.jwt_service')
mock_jwt_module.JWTService = MockJWTService
sys.modules['tarsy.services.jwt_service'] = mock_jwt_module

# Mock PyGithub to avoid import issues in tests
mock_github = Mock()
mock_github_user = Mock()
mock_github_user.id = 123
mock_github_user.login = "test-user"
mock_github_user.email = "test@example.com"
mock_github_user.avatar_url = "https://github.com/test.png"

mock_github_class = Mock()
mock_github_class.return_value.get_user.return_value = mock_github_user

sys.modules['github'] = mock_github
sys.modules['github'].Github = mock_github_class
sys.modules['github'].GithubException = Exception
sys.modules['github'].UnknownObjectException = Exception

# Create module-like objects for direct exception imports
# Production code uses: from github.GithubException import GithubException
github_exception_module = types.ModuleType('github.GithubException')
github_exception_module.GithubException = Exception
sys.modules['github.GithubException'] = github_exception_module

# Handle UnknownObjectException for potential future use
unknown_object_exception_module = types.ModuleType('github.UnknownObjectException')
unknown_object_exception_module.UnknownObjectException = Exception
sys.modules['github.UnknownObjectException'] = unknown_object_exception_module

# Mock the GitHub service as well
mock_github_service = Mock()
mock_github_service.validate_github_membership = Mock()
sys.modules['tarsy.services.github_service'] = mock_github_service

# Mock async operations that can hang in tests
@pytest.fixture(autouse=True) 
def mock_async_operations(request):
    """Mock async operations that can cause hangs in tests."""
    
    # Skip this fixture for E2E tests (they need real services)
    if "e2e" in request.node.nodeid:
        yield
        return
    
    # Create a no-op async context manager for lifespan
    from contextlib import asynccontextmanager
    
    @asynccontextmanager
    async def mock_lifespan(app):
        # Do minimal setup for tests
        import asyncio
        from tarsy import main
        
        # Mock alert service with chain registry using AsyncMock for async methods
        mock_alert_service = Mock()
        mock_alert_service.process_alert = AsyncMock()  # Make process_alert awaitable
        mock_chain_registry = Mock()
        mock_chain_registry.list_available_alert_types.return_value = ["kubernetes", "database", "network"]
        mock_alert_service.chain_registry = mock_chain_registry
        mock_alert_service.register_alert_id = Mock()
        
        # Set up global state in the main module
        main.alert_service = mock_alert_service
        main.dashboard_manager = Mock()
        main.alert_processing_semaphore = asyncio.Semaphore(10)
        
        yield
    
    # Also patch the app's lifespan directly
    import tarsy.main
    original_lifespan = tarsy.main.app.router.lifespan_context
    
    try:
        tarsy.main.app.router.lifespan_context = mock_lifespan
        
        with patch('tarsy.main.lifespan', mock_lifespan), \
             patch('tarsy.database.init_db.initialize_database', return_value=True), \
             patch('tarsy.services.alert_service.AlertService.initialize', new_callable=AsyncMock), \
             patch('tarsy.services.dashboard_connection_manager.DashboardConnectionManager.initialize_broadcaster', new_callable=AsyncMock), \
             patch('tarsy.services.history_service.get_history_service') as mock_history:
            
            # Mock history service methods that could hang
            mock_history_service = Mock()
            mock_history_service.cleanup_orphaned_sessions = Mock(return_value=0)
            mock_history.return_value = mock_history_service
            
            yield
    finally:
        # Restore original lifespan
        tarsy.main.app.router.lifespan_context = original_lifespan

# Import Alert model for fixtures
# Import all database models to ensure they're registered with SQLModel.metadata
import tarsy.models.db_models  # noqa: F401
import tarsy.models.unified_interactions  # noqa: F401
from tarsy.models.alert import Alert
from tarsy.models.llm_models import LLMProviderConfig
from tarsy.models.processing_context import ChainContext
from tarsy.utils.timestamp import now_us


# Optional JWT authentication mocking - use when you don't want real JWT validation
@pytest.fixture
def mock_jwt_authentication():
    """
    Mock JWT authentication for tests that don't need real JWT validation.
    
    Use this fixture explicitly in tests that need to bypass JWT authentication.
    Most tests should use real JWT tokens via auth_fixtures instead.
    """
    mock_user_payload = {
        "sub": "test_user_123",
        "username": "test-user",
        "email": "test@example.com",
        "avatar_url": "https://github.com/test.png",
        "iss": "tarsy-test",
        "iat": 1234567890,
        "exp": 1234567890 + 3600
    }
    
    # Create a mock JWT service that doesn't require key files
    mock_jwt_service = Mock()
    mock_jwt_service.verify_jwt_token.return_value = mock_user_payload
    mock_jwt_service.create_user_jwt_token.return_value = "mock_jwt_token"
    mock_jwt_service.create_service_account_jwt_token.return_value = "mock_service_jwt_token"
    
    # Mock the dependency functions and JWT service creation
    # Note: get_jwt_service is cached with @lru_cache for performance.
    # If your test modifies JWT settings, call clear_jwt_service_cache() 
    # from tarsy.auth.dependencies to ensure fresh configuration.
    with patch('tarsy.auth.dependencies.get_jwt_service', return_value=mock_jwt_service), \
         patch('tarsy.auth.dependencies.verify_jwt_token', new_callable=AsyncMock, return_value=mock_user_payload), \
         patch('tarsy.auth.dependencies.verify_jwt_token_websocket', new_callable=AsyncMock, return_value=mock_user_payload):
        yield


def alert_to_api_format(alert: Alert) -> ChainContext:
    """
    Convert an Alert object to the ChainContext format that AlertService expects.
    
    This matches the format created in main.py lines 350-353.
    """
    # Create normalized_data that matches what the API layer does
    normalized_data = alert.data.copy() if alert.data else {}
    
    # Add core fields (matching API logic)
    normalized_data["runbook"] = alert.runbook
    normalized_data["severity"] = alert.severity or "warning"
    normalized_data["timestamp"] = alert.timestamp or now_us()
    
    # Add default environment if not present
    if "environment" not in normalized_data:
        normalized_data["environment"] = "production"
    
    # Return ChainContext instance that AlertService expects
    return ChainContext(
        alert_type=alert.alert_type,
        alert_data=normalized_data,
        session_id=f"test-session-{hash(str(alert.data))}",  # EP-0012: Generate test session ID from alert data
        current_stage_name="initial"  # Default stage for tests
    )


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Automatically set up test environment for all tests."""
    # Ensure we're in testing mode
    os.environ["TESTING"] = "true"
    
    # Set up any other global test configuration
    yield
    
    # Cleanup after all tests
    if "TESTING" in os.environ:
        del os.environ["TESTING"]


@pytest.fixture
def test_database_url() -> str:
    """Provide a unique in-memory database URL for each test."""
    return "sqlite:///:memory:"


@pytest.fixture
def test_database_engine(test_database_url):
    """Create a test database engine with all tables."""
    engine = create_engine(test_database_url, echo=False)
    # Import all models to ensure they're registered with SQLModel.metadata
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def test_database_session(test_database_engine) -> Generator[Session, None, None]:
    """Create a database session for testing."""
    with Session(test_database_engine) as session:
        yield session


@pytest.fixture
def isolated_test_settings():
    """Create isolated test settings that don't affect the production database."""
    from tarsy.config.settings import Settings
    
    # Create a mock settings object that behaves like Settings but allows modification
    settings = Mock(spec=Settings)
    settings.history_database_url = "sqlite:///:memory:"
    settings.history_enabled = True
    settings.history_retention_days = 90
    settings.google_api_key = "test-google-key"
    settings.openai_api_key = "test-openai-key"
    settings.xai_api_key = "test-xai-key"
    settings.github_token = "test-github-token"
    settings.default_llm_provider = "gemini"
    settings.max_llm_mcp_iterations = 3
    settings.log_level = "INFO"
    
    # LLM providers configuration that LLMManager expects
    settings.llm_providers = {
        "gemini": {
            "model": "gemini-2.5-pro",
            "api_key_env": "GEMINI_API_KEY",
            "type": "gemini"
        },
        "openai": {
            "model": "gpt-4-1106-preview",
            "api_key_env": "OPENAI_API_KEY", 
            "type": "openai"
        },
        "grok": {
            "model": "grok-3",
            "api_key_env": "GROK_API_KEY",
            "type": "grok"
        }
    }
    
    # Mock the get_llm_config method
    def mock_get_llm_config(provider: str) -> LLMProviderConfig:
        if provider not in settings.llm_providers:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        base = settings.llm_providers[provider]
        if provider == "gemini":
            api_key = settings.google_api_key
        elif provider == "openai":
            api_key = settings.openai_api_key
        elif provider == "grok":
            api_key = settings.xai_api_key
        else:
            api_key = ""
        
        return LLMProviderConfig(
            model=base["model"],
            type=base["type"],
            api_key=api_key,
        )
    
    settings.get_llm_config = mock_get_llm_config
    return settings


@pytest.fixture
def patch_settings_for_tests(isolated_test_settings):
    """Patch the get_settings function to return isolated test settings."""
    with patch('tarsy.config.settings.get_settings', return_value=isolated_test_settings):
        yield isolated_test_settings


@pytest.fixture(autouse=True)
def cleanup_test_database_files():
    """Automatically clean up any test database files after each test."""
    yield
    
    # Clean up any test database files that might have been created
    test_db_patterns = [
        "test_history.db",
        "test_history.db-shm", 
        "test_history.db-wal",
        "history_test.db",
        "history_test.db-shm",
        "history_test.db-wal"
    ]
    
    for pattern in test_db_patterns:
        test_file = Path(pattern)
        if test_file.exists():
            try:
                test_file.unlink()
            except OSError:
                pass  # File might be in use, ignore 


@pytest.fixture
def sample_kubernetes_alert():
    """Create a sample Kubernetes alert using the new flexible model."""
    return Alert(
        alert_type="kubernetes",
        runbook="https://github.com/company/runbooks/blob/main/k8s.md",
        severity="critical",
        timestamp=now_us(),
        data={
            "environment": "production",
            "cluster": "main-cluster", 
            "namespace": "test-namespace",
            "message": "Namespace is terminating",
            "alert": "NamespaceTerminating"
        }
    )


@pytest.fixture
def sample_generic_alert():
    """Create a sample generic alert using the new flexible model."""
    return Alert(
        alert_type="generic",
        runbook="https://example.com/runbook",
        severity="warning",
        timestamp=now_us(),
        data={
            "environment": "production",
            "message": "Generic alert message",
            "source": "monitoring-system"
        }
    )


@pytest.fixture
def minimal_alert():
    """Create a minimal alert with only required fields."""
    return Alert(
        alert_type="test",
        runbook="https://example.com/minimal-runbook",
        data={}
    ) 