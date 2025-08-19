"""
Global pytest configuration and fixtures for all tests.

This module provides common fixtures and configuration for both unit and integration tests,
ensuring proper test isolation and database handling.
"""

import os
from pathlib import Path
from typing import Generator
from unittest.mock import Mock, patch

import pytest
from sqlmodel import Session, SQLModel, create_engine

# Set testing environment variable as early as possible
os.environ["TESTING"] = "true"

# Import Alert model for fixtures
from tarsy.models.alert import Alert
from tarsy.models.processing_context import ChainContext
from tarsy.utils.timestamp import now_us

# Import all database models to ensure they're registered with SQLModel.metadata
import tarsy.models.db_models  # noqa: F401
import tarsy.models.unified_interactions  # noqa: F401


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
        session_id=f"test-session-{alert.id}",  # Generate test session ID
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
    settings.gemini_api_key = "test-gemini-key"
    settings.openai_api_key = "test-openai-key"
    settings.grok_api_key = "test-grok-key"
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
    def mock_get_llm_config(provider: str):
        if provider not in settings.llm_providers:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        config = settings.llm_providers[provider].copy()
        if provider == "gemini":
            config["api_key"] = settings.gemini_api_key
        elif provider == "openai":
            config["api_key"] = settings.openai_api_key
        elif provider == "grok":
            config["api_key"] = settings.grok_api_key
        return config
    
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