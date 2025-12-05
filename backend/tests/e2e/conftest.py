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
from typing import Any, Optional
from unittest.mock import patch

import pytest

logger = logging.getLogger(__name__)


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
            "KUBECONFIG", "DATABASE_URL", "HISTORY_ENABLED",
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
        """Clean up all resources when exiting the context manager."""
        from contextlib import suppress
        
        # Clean up resources as normal
        
        # 2. Stop all patches
        for patcher in reversed(self.patches):  # Reverse order to undo patches properly
            try:
                patcher.stop()
            except Exception as e:
                logger.warning(f"Error stopping patch during cleanup: {e}")
        
        # 3. Restore original environment variables
        for key, original_value in self.original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
        
        # 4. Clean up temporary files
        for temp_file in self.temp_files:
            try:
                Path(temp_file).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Error removing temp file {temp_file}: {e}")
        
        # 5. Clean up temporary directory
        if self.temp_dir:
            try:
                shutil.rmtree(self.temp_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Error removing temp directory {self.temp_dir}: {e}")
        
        # 6. Restore logging state
        self._restore_logging_state()
        
        # 7. Clear tracking lists
        self.temp_files.clear()
        self.patches.clear()
        self.original_env.clear()
        
        # 8. CRITICAL: Reset global history service singleton to prevent contamination
        with suppress(Exception):
            import tarsy.services.history_service
            tarsy.services.history_service._history_service = None
    
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
    e2e_isolation.set_isolated_env("DATABASE_URL", test_db_url)
    e2e_isolation.set_isolated_env("HISTORY_ENABLED", "true")
    e2e_isolation.set_isolated_env("AGENT_CONFIG_PATH", str(test_agents_path))
    e2e_isolation.set_isolated_env("OPENAI_API_KEY", "test-key-123")
    e2e_isolation.set_isolated_env("LLM_PROVIDER", "openai-default")
    e2e_isolation.set_isolated_env("KUBECONFIG", kubeconfig_path)
    
    # Create real Settings object with isolated environment
    settings = Settings()
    
    # Override specific values after creation to ensure they're isolated
    settings.database_url = test_db_url
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
        "TESTING", "KUBECONFIG", "DATABASE_URL", "HISTORY_ENABLED",
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
    # Ensure settings cache is cleared before importing app
    # This ensures the app is created with the test configuration
    from contextlib import suppress
    from unittest.mock import patch

    from fastapi.testclient import TestClient
    with suppress(Exception):
        import tarsy.config.settings
        tarsy.config.settings.get_settings.cache_clear()

    # CRITICAL FIX: Mock MCPClient.initialize() to prevent it from trying to start
    # real MCP server subprocesses during app lifespan startup
    # Individual tests can override with more specific mocks as needed
    async def mock_mcp_initialize(self):
        """Mock MCP initialization - tests will provide their own mocks."""
        self._initialized = True
        self.sessions = {}
        logger.info("E2E: Skipping real MCP server initialization (will be mocked in test)")
    
    with patch('tarsy.integrations.mcp.client.MCPClient.initialize', mock_mcp_initialize):
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
        "severity": "warning",  # Top-level field in Alert model
        # Note: timestamp will be generated if not provided
        "data": {  # User-provided data fields
            "namespace": "test-namespace",
            "description": "Namespace stuck in Terminating state",
            "cluster": "test-cluster",
            "contact": "admin@example.com",  # Email to test masking
            "labels": {
                "env": "test",
                "team": "platform"
            },
            "annotations": {
                "finalizers": "kubernetes.io/pv-protection"
            }
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
            "KUBECONFIG", "DATABASE_URL", "HISTORY_ENABLED",
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


# Shared test helpers for mocking LLM streaming responses


class MockChunk:
    """Mock chunk for streaming responses."""

    def __init__(self, content: str = "", usage_metadata: Optional[dict] = None):
        self.content = content
        self.usage_metadata = usage_metadata

    def __add__(self, other):
        """Support chunk aggregation like LangChain does."""
        if not isinstance(other, MockChunk):
            return NotImplemented
        # Aggregate content and usage_metadata
        new_content = self.content + other.content
        # For usage metadata, the last one wins (simulating LangChain behavior)
        new_usage = other.usage_metadata or self.usage_metadata
        return MockChunk(new_content, new_usage)

    def __radd__(self, other):
        """Support reverse addition."""
        if other is None:
            return self
        return self.__add__(other)


async def create_mock_stream(content: str, usage_metadata: Optional[dict] = None):
    """
    Create an async generator that yields mock chunks with usage metadata in final chunk.

    Args:
        content: The content to stream, yielded character by character
        usage_metadata: Optional usage metadata to attach to the final chunk
    """
    # Yield content character by character
    for i, char in enumerate(content):
        # Add usage_metadata only to the final chunk
        is_final = (i == len(content) - 1)
        yield MockChunk(char, usage_metadata=usage_metadata if is_final else None)


# =============================================================================
# Native Thinking Mock Helpers (for Gemini SDK tests)
# =============================================================================


class MockUsageMetadata:
    """Mock usage metadata for Gemini API responses."""
    
    def __init__(self, prompt_token_count: int, candidates_token_count: int, total_token_count: int):
        self.prompt_token_count = prompt_token_count
        self.candidates_token_count = candidates_token_count
        self.total_token_count = total_token_count


class MockPart:
    """Mock Part object for Gemini API responses."""
    
    def __init__(
        self,
        text: Optional[str] = None,
        thought: bool = False,
        thought_signature: Optional[bytes] = None,
        function_call: Optional[Any] = None
    ):
        self.text = text
        self.thought = thought
        self.thought_signature = thought_signature
        self.function_call = function_call


class MockFunctionCall:
    """Mock function call from Gemini API."""
    
    def __init__(self, name: str, args: dict):
        self.name = name
        self.args = args


class MockContent:
    """Mock Content object for Gemini API responses."""
    
    def __init__(self, parts: list):
        self.parts = parts


class MockCandidate:
    """Mock Candidate object for Gemini API responses."""
    
    def __init__(self, content: MockContent):
        self.content = content


class MockGeminiResponse:
    """Mock response from Gemini API generate_content."""
    
    def __init__(
        self,
        text_content: str = "",
        thinking_content: Optional[str] = None,
        function_calls: Optional[list] = None,
        thought_signature: Optional[bytes] = None,
        usage_metadata: Optional[MockUsageMetadata] = None
    ):
        parts = []
        
        # Add thinking content if present
        if thinking_content:
            parts.append(MockPart(text=thinking_content, thought=True))
        
        # Add regular text content if present
        if text_content:
            parts.append(MockPart(text=text_content, thought=False, thought_signature=thought_signature))
        
        # Build candidates
        content = MockContent(parts=parts)
        self.candidates = [MockCandidate(content=content)]
        
        # Function calls are stored directly on response
        self.function_calls = []
        if function_calls:
            for fc in function_calls:
                self.function_calls.append(MockFunctionCall(name=fc["name"], args=fc.get("args", {})))
        
        self.usage_metadata = usage_metadata


def create_native_thinking_response(
    text_content: str = "",
    thinking_content: Optional[str] = None,
    function_calls: Optional[list] = None,
    thought_signature: Optional[bytes] = None,
    input_tokens: int = 100,
    output_tokens: int = 50,
    total_tokens: int = 150
) -> MockGeminiResponse:
    """
    Create a mock Gemini native thinking response.
    
    Args:
        text_content: The main text response
        thinking_content: Optional thinking/reasoning content
        function_calls: Optional list of function calls [{"name": "server__tool", "args": {...}}]
        thought_signature: Optional thought signature for multi-turn continuity
        input_tokens: Input token count
        output_tokens: Output token count
        total_tokens: Total token count
        
    Returns:
        MockGeminiResponse object
    """
    usage = MockUsageMetadata(
        prompt_token_count=input_tokens,
        candidates_token_count=output_tokens,
        total_token_count=total_tokens
    )
    
    return MockGeminiResponse(
        text_content=text_content,
        thinking_content=thinking_content,
        function_calls=function_calls,
        thought_signature=thought_signature,
        usage_metadata=usage
    )


class MockGeminiModels:
    """Mock for google.genai.Client.aio.models."""
    
    def __init__(self, response_generator):
        self._response_generator = response_generator
        self._call_count = 0
    
    async def generate_content(self, model: str, contents: list, config: Any = None):
        """Mock generate_content that returns responses from the generator."""
        self._call_count += 1
        return self._response_generator(self._call_count, model, contents, config)
    
    async def generate_content_stream(self, model: str, contents: list, config: Any = None):
        """Mock generate_content_stream that returns an async generator yielding the response."""
        self._call_count += 1
        response = self._response_generator(self._call_count, model, contents, config)
        
        # Return an async generator that yields the complete response as a single chunk
        async def stream_response():
            yield response
        
        return stream_response()


class MockGeminiAio:
    """Mock for google.genai.Client.aio."""
    
    def __init__(self, response_generator):
        self.models = MockGeminiModels(response_generator)


class MockGeminiClient:
    """Mock for google.genai.Client."""
    
    def __init__(self, response_generator, api_key: str = "test-api-key"):
        self.api_key = api_key
        self.aio = MockGeminiAio(response_generator)


def create_gemini_client_mock(response_map: dict):
    """
    Create a mock Gemini client factory.
    
    Args:
        response_map: Dictionary mapping interaction number (1-based) to response data:
            {
                1: {
                    "text_content": "...",
                    "thinking_content": "...",  # optional
                    "function_calls": [...],    # optional
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150
                },
                ...
            }
    
    Returns:
        A function that creates MockGeminiClient instances
    """
    def response_generator(call_num: int, model: str, contents: list, config: Any):
        """Generate response based on call number."""
        response_data = response_map.get(call_num, {
            "text_content": "",
            "thinking_content": None,
            "function_calls": None,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0
        })
        
        return create_native_thinking_response(
            text_content=response_data.get("text_content", ""),
            thinking_content=response_data.get("thinking_content"),
            function_calls=response_data.get("function_calls"),
            thought_signature=response_data.get("thought_signature"),
            input_tokens=response_data.get("input_tokens", 100),
            output_tokens=response_data.get("output_tokens", 50),
            total_tokens=response_data.get("total_tokens", 150)
        )
    
    def client_factory(api_key: str = "test-api-key"):
        return MockGeminiClient(response_generator, api_key)
    
    return client_factory


@pytest.fixture
def e2e_native_thinking_alert():
    """Alert specifically for native thinking E2E tests."""
    return {
        "alert_type": "test-native-thinking",
        "runbook": "https://runbooks.example.com/k8s-namespace-stuck",
        "severity": "warning",
        "data": {
            "namespace": "test-namespace",
            "description": "Namespace stuck in Terminating state",
            "cluster": "test-cluster",
            "contact": "admin@example.com",
            "labels": {
                "env": "test",
                "team": "platform"
            },
            "annotations": {
                "finalizers": "kubernetes.io/pv-protection"
            }
        }
    }


@pytest.fixture
def isolated_native_thinking_settings(e2e_isolation):
    """Create isolated test settings for native thinking e2e tests."""
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
    
    # Create absolute path to native thinking test agents config
    current_dir = Path(__file__).parent
    test_agents_path = current_dir / "test_native_thinking_agents.yaml"
    
    # Set isolated environment variables
    e2e_isolation.set_isolated_env("DATABASE_URL", test_db_url)
    e2e_isolation.set_isolated_env("HISTORY_ENABLED", "true")
    e2e_isolation.set_isolated_env("AGENT_CONFIG_PATH", str(test_agents_path))
    e2e_isolation.set_isolated_env("GOOGLE_API_KEY", "test-google-key-123")
    e2e_isolation.set_isolated_env("LLM_PROVIDER", "google-default")  # Use builtin Google provider
    e2e_isolation.set_isolated_env("KUBECONFIG", kubeconfig_path)
    
    # Create real Settings object with isolated environment
    settings = Settings()
    
    # Override specific values after creation to ensure they're isolated
    settings.database_url = test_db_url
    settings.history_enabled = True
    settings.agent_config_path = str(test_agents_path)
    settings.google_api_key = "test-google-key-123"
    settings.llm_provider = "google-default"  # Use builtin Google provider
    
    # Patch global settings
    e2e_isolation.patch_settings(settings)
    
    return settings


@pytest.fixture
def e2e_native_thinking_test_client(isolated_native_thinking_settings):
    """Create an isolated FastAPI test client for native thinking e2e tests."""
    # Ensure settings cache is cleared before importing app
    from contextlib import suppress
    from unittest.mock import patch

    from fastapi.testclient import TestClient
    with suppress(Exception):
        import tarsy.config.settings
        tarsy.config.settings.get_settings.cache_clear()

    # Mock MCPClient.initialize() to prevent real server startup
    async def mock_mcp_initialize(self):
        """Mock MCP initialization - tests will provide their own mocks."""
        self._initialized = True
        self.sessions = {}
        logger.info("E2E Native Thinking: Skipping real MCP server initialization")
    
    with patch('tarsy.integrations.mcp.client.MCPClient.initialize', mock_mcp_initialize):
        from tarsy.main import app
        
        with TestClient(app) as client:
            yield client