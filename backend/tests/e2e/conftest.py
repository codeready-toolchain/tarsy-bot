"""
E2E Test Configuration with Complete Isolation.

This module provides isolated fixtures for e2e tests that don't affect 
unit or integration tests. All environment variables, database files,
and global state are properly isolated and cleaned up.
"""

import logging
import os
import shutil
import sys
import tempfile
import uuid
from contextlib import suppress
from pathlib import Path
from unittest.mock import patch

import pytest


class E2ETestIsolation:
    """Context manager for complete e2e test isolation."""
    
    def __init__(self):
        self.original_env = {}
        self.temp_dir = None
        self.temp_files = []
        self.patches = []
        self.original_logging_state = {}
        self.original_sys_modules = {}
    
    def __enter__(self):
        # CRITICAL: Reset global singletons and caches BEFORE e2e test setup
        # This prevents contamination from other tests that ran in the same pytest session
        with suppress(Exception):
            import tarsy.services.history_service
            tarsy.services.history_service._history_service = None
            
        # Clear cached settings to ensure environment changes take effect
        with suppress(Exception):
            import tarsy.config.settings
            tarsy.config.settings.get_settings.cache_clear()
        
        # Create isolated temporary directory for this test
        self.temp_dir = Path(tempfile.mkdtemp(prefix="tarsy_e2e_test_"))
        
        # Store original environment variables we'll modify
        env_vars_to_isolate = [
            "KUBECONFIG", "HISTORY_DATABASE_URL", "HISTORY_ENABLED",
            "AGENT_CONFIG_PATH", "LLM_CONFIG_PATH",
            "GOOGLE_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY", "ANTHROPIC_API_KEY",
            "LLM_PROVIDER",
            "TESTING"
        ]
        
        for var in env_vars_to_isolate:
            self.original_env[var] = os.environ.get(var)
        
        # Capture logging state before e2e test modifications
        self._capture_logging_state()
        
        # Set isolated testing environment
        os.environ["TESTING"] = "true"
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        
        # CRITICAL: Reset global history service singleton to prevent contamination
        with suppress(Exception):
            import tarsy.services.history_service
            tarsy.services.history_service._history_service = None
        
        # Restore logging state
        self._restore_logging_state()
        
        # Restore original environment variables
        for var, original_value in self.original_env.items():
            if original_value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = original_value
        
        # Clean up all temporary files
        for temp_file in self.temp_files:
            with suppress(OSError, IOError):
                if os.path.exists(temp_file):
                    os.remove(temp_file)
        
        # Clean up temporary directory
        if self.temp_dir and self.temp_dir.exists():
            with suppress(OSError, IOError):
                shutil.rmtree(self.temp_dir)
        
        # Clean up patches
        for patcher in reversed(self.patches):
            with suppress(RuntimeError):
                patcher.stop()
    
    def create_temp_database(self) -> str:
        """Create an isolated temporary database file."""
        if not self.temp_dir:
            raise RuntimeError("E2E isolation not properly initialized")
        
        db_file = self.temp_dir / f"e2e_test_{uuid.uuid4().hex[:8]}.db"
        self.temp_files.append(str(db_file))
        return f"sqlite:///{db_file}"
    
    def create_temp_file(self, suffix: str = "", content: str = "") -> str:
        """Create an isolated temporary file."""
        if not self.temp_dir:
            raise RuntimeError("E2E isolation not properly initialized")
        
        temp_file = self.temp_dir / f"temp_{uuid.uuid4().hex[:8]}{suffix}"
        
        if content:
            temp_file.write_text(content)
        
        self.temp_files.append(str(temp_file))
        return str(temp_file)
    
    def set_isolated_env(self, key: str, value: str):
        """Set an environment variable in isolation."""
        if key not in self.original_env:
            self.original_env[key] = os.environ.get(key)
        os.environ[key] = value
    
    def patch_settings(self, settings_override):
        """Patch global settings in isolation."""
        patcher = patch('tarsy.config.settings.get_settings', return_value=settings_override)
        self.patches.append(patcher)
        patcher.start()
        return patcher
    
    def _capture_logging_state(self):
        """Capture current logging configuration."""
        with suppress(Exception):
            # Store root logger state
            root_logger = logging.getLogger()
            self.original_logging_state['root_level'] = root_logger.level
            self.original_logging_state['root_handlers'] = root_logger.handlers.copy()
            
            # Store specific loggers that might be affected
            for logger_name in ['tarsy', 'tarsy.services', 'tarsy.agents']:
                logger = logging.getLogger(logger_name)
                self.original_logging_state[logger_name] = {
                    'level': logger.level,
                    'handlers': logger.handlers.copy(),
                    'propagate': logger.propagate
                }
    
    def _restore_logging_state(self):
        """Restore original logging configuration."""
        with suppress(Exception):
            # Restore root logger
            root_logger = logging.getLogger()
            if 'root_level' in self.original_logging_state:
                root_logger.setLevel(self.original_logging_state['root_level'])
            if 'root_handlers' in self.original_logging_state:
                root_logger.handlers = self.original_logging_state['root_handlers']
            
            # Restore specific loggers
            for logger_name, state in self.original_logging_state.items():
                if logger_name.startswith('root_'):
                    continue
                logger = logging.getLogger(logger_name)
                if isinstance(state, dict):
                    logger.setLevel(state['level'])
                    logger.handlers = state['handlers']
                    logger.propagate = state['propagate']
    
@pytest.fixture
def e2e_isolation():
    """Provide complete e2e test isolation."""
    with E2ETestIsolation() as isolation:
        yield isolation


@pytest.fixture
def isolated_e2e_settings(e2e_isolation):
    """Create isolated test settings for e2e tests."""
    from tarsy.config.settings import Settings
    
    # Create isolated database
    test_db_url = e2e_isolation.create_temp_database()
    
    # Create isolated kubeconfig
    kubeconfig_content = """
apiVersion: v1
kind: Config
clusters:
- name: test-cluster
  cluster:
    server: https://test-k8s-api.example.com
contexts:
- name: test-context
  context:
    cluster: test-cluster
current-context: test-context
"""
    kubeconfig_path = e2e_isolation.create_temp_file(".yaml", kubeconfig_content)
    
    # Create absolute path to test agents config
    current_dir = Path(__file__).parent
    test_agents_path = current_dir / "test_agents.yaml"
    
    # Set isolated environment variables
    e2e_isolation.set_isolated_env("HISTORY_DATABASE_URL", test_db_url)
    e2e_isolation.set_isolated_env("HISTORY_ENABLED", "true")
    e2e_isolation.set_isolated_env("AGENT_CONFIG_PATH", str(test_agents_path))
    e2e_isolation.set_isolated_env("OPENAI_API_KEY", "test-key-123")
    e2e_isolation.set_isolated_env("LLM_PROVIDER", "openai-default")
    e2e_isolation.set_isolated_env("KUBECONFIG", kubeconfig_path)
    
    # Create real Settings object with isolated environment
    settings = Settings()
    
    # Override specific values after creation to ensure they're isolated
    settings.history_database_url = test_db_url
    settings.history_enabled = True
    settings.agent_config_path = str(test_agents_path)
    settings.openai_api_key = "test-key-123"
    settings.llm_provider = "openai-default"
    
    # Patch global settings
    e2e_isolation.patch_settings(settings)
    
    return settings

@pytest.fixture(autouse=True, scope="function")
def ensure_e2e_isolation(request):
    """Automatically ensure e2e tests are properly isolated."""
    # Only apply to e2e tests
    if "e2e" not in request.node.nodeid:
        yield
        return
    
    # Set testing mode for EVERY e2e test
    os.environ["TESTING"] = "true"
    
    # CRITICAL: Reset global singletons and caches at the START of each e2e test
    # This ensures e2e tests get fresh instances even when running with other tests
    with suppress(Exception):
        import tarsy.services.history_service
        tarsy.services.history_service._history_service = None
        
    # Clear cached settings to ensure environment changes take effect
    with suppress(Exception):
        import tarsy.config.settings
        tarsy.config.settings.get_settings.cache_clear()
    
    # Store original environment for e2e tests
    original_env = {}
    e2e_env_vars = [
        "TESTING", "KUBECONFIG", "HISTORY_DATABASE_URL", "HISTORY_ENABLED",
        "AGENT_CONFIG_PATH", "LLM_CONFIG_PATH",
        "GOOGLE_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY", "ANTHROPIC_API_KEY",
        "LLM_PROVIDER"
    ]
    
    for var in e2e_env_vars:
        original_env[var] = os.environ.get(var)
    
    yield
        
    # Restore original environment completely
    for var, original_value in original_env.items():
        if original_value is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = original_value
    
    # Clean up any stray test database files that might have been created
    cleanup_patterns = [
        "test_db_*.db*",
        "history_test.db*", 
        "test_history.db*",
        "/tmp/test_db_*.db*",
        "/tmp/e2e_test_*.db*"
    ]
    
    import glob
    for pattern in cleanup_patterns:
        for file_path in glob.glob(pattern):
            with suppress(OSError, IOError):
                os.remove(file_path)


# E2E specific fixtures that don't interfere with other tests
@pytest.fixture
def e2e_test_client(isolated_e2e_settings):
    """Create an isolated FastAPI test client for e2e tests."""
    from fastapi.testclient import TestClient

    # Ensure settings cache is cleared before importing app
    # This ensures the app is created with the test configuration
    from contextlib import suppress
    with suppress(Exception):
        import tarsy.config.settings
        tarsy.config.settings.get_settings.cache_clear()

    from tarsy.main import app
    
    # The isolated settings are already patched globally
    with TestClient(app) as client:
        yield client


@pytest.fixture
def e2e_realistic_kubernetes_alert():
    """Realistic Kubernetes alert for e2e testing."""
    return {
        "alert_type": "test-kubernetes", 
        "runbook": "https://runbooks.example.com/k8s-namespace-stuck",
        "alert_data": {
            "namespace": "test-namespace",
            "severity": "warning", 
            "description": "Namespace stuck in Terminating state",
            "cluster": "test-cluster",
            "labels": {
                "env": "test",
                "team": "platform"
            },
            "annotations": {
                "finalizers": "kubernetes.io/pv-protection"
            },
            "timestamp": "2024-01-15T10:30:00Z"
        }
    }


# Module-level cleanup for any global state that might leak
def pytest_runtest_teardown(item):
    """Clean up after each e2e test to prevent state leakage.""" 
    if "e2e" in item.nodeid:
        # Note: Patch cleanup is now handled by the individual E2ETestIsolation instances
        # through their self.patches list, so no global cleanup is needed here
        
        # Clean up environment variables that might have been modified
        test_env_vars = [
            "KUBECONFIG", "HISTORY_DATABASE_URL", "HISTORY_ENABLED",
            "AGENT_CONFIG_PATH", "LLM_CONFIG_PATH",
            "GOOGLE_API_KEY", "OPENAI_API_KEY", "XAI_API_KEY", "ANTHROPIC_API_KEY",
            "LLM_PROVIDER"
        ]
        
        for var in test_env_vars:
            # Only remove test-specific values, preserve original production values
            current_value = os.environ.get(var)
            if current_value and ("test-" in current_value or "tmp" in current_value or "/tmp/" in current_value):
                os.environ.pop(var, None)
        
        # CRITICAL: Reset global history service singleton to prevent contamination of other tests
        with suppress(Exception):
            import tarsy.services.history_service
            tarsy.services.history_service._history_service = None
            
        # Force clear any cached modules that might have been modified
        modules_to_clear = [
            'tarsy.config.settings',
            'tarsy.repositories.base_repository',
            'tarsy.database.init_db'
        ]
        
        for module_name in modules_to_clear:
            if module_name in sys.modules:
                # Don't actually remove the module, but clear any cached data
                with suppress(Exception):
                    module = sys.modules[module_name]
                    # Clear module-level caches if they exist
                    if hasattr(module, '_cached_settings'):
                        delattr(module, '_cached_settings')
                    if hasattr(module, '_db_manager'):
                        delattr(module, '_db_manager')


def pytest_configure(config):
    """Configure pytest for e2e tests."""
    # Ensure the e2e marker is registered
    config.addinivalue_line(
        "markers", "e2e: mark test as end-to-end test requiring full isolation"
    )
