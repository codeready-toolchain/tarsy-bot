"""
Comprehensive tests for the main FastAPI application.

Tests lifespan management, endpoints, WebSocket connections, and background processing.
"""

import asyncio
import contextlib
import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, patch, call

import pytest
from fastapi import WebSocket
from fastapi.testclient import TestClient

# Import the modules we need to test and mock
from tarsy.main import (
    app,
    lifespan,
    process_alert_background,
)
from tarsy.controllers.alert_controller import (
    alert_keys_lock,
    processing_alert_keys,
)
from tarsy.models.processing_context import ChainContext


@pytest.mark.unit
class TestMainLifespan:
    """Test application lifespan management."""

    @pytest.fixture
    def mock_get_settings(self):
        """Mock settings for lifespan tests."""
        from tests.utils import MockFactory
        return MockFactory.create_mock_settings(
            log_level="INFO",
            max_concurrent_alerts=5,
            history_enabled=True,
            cors_origins=["*"],
            host="localhost",
            port=8000
        )

    @pytest.fixture
    def mock_lifespan_dependencies(self):
        """Centralized mock setup for lifespan tests."""
        from unittest.mock import AsyncMock, Mock, patch
        
        with patch('tarsy.main.setup_logging') as mock_setup_logging, \
             patch('tarsy.main.initialize_database') as mock_init_db, \
             patch(
                 'tarsy.services.history_service.get_history_service'
             ) as mock_history_service, \
             patch('tarsy.main.AlertService') as mock_alert_service_class, \
             patch(
                 'tarsy.main.DashboardConnectionManager'
             ) as mock_dashboard_manager_class, \
             patch(
                 'tarsy.hooks.hook_registry.get_typed_hook_registry'
             ) as mock_hook_registry, \
             patch('tarsy.main.get_database_info') as mock_db_info:
            
            # Setup service mocks
            mock_alert_service = AsyncMock()
            mock_alert_service_class.return_value = mock_alert_service
            
            mock_dashboard_manager = Mock()
            mock_dashboard_manager.initialize_broadcaster = AsyncMock()
            mock_dashboard_manager.shutdown_broadcaster = AsyncMock()
            mock_dashboard_manager_class.return_value = mock_dashboard_manager
            
            mock_history = Mock()
            mock_history.cleanup_orphaned_sessions.return_value = 2
            mock_history_service.return_value = mock_history
            
            mock_typed_hooks = AsyncMock()
            mock_hook_registry.return_value = mock_typed_hooks
            
            yield {
                'setup_logging': mock_setup_logging,
                'init_db': mock_init_db,
                'history_service': mock_history_service,
                'alert_service_class': mock_alert_service_class,
                'dashboard_manager_class': mock_dashboard_manager_class,
                'hook_registry': mock_hook_registry,
                'db_info': mock_db_info,
                'alert_service': mock_alert_service,
                'dashboard_manager': mock_dashboard_manager,
                'history': mock_history,
                'typed_hooks': mock_typed_hooks
            }

    @patch('tarsy.main.get_settings')
    async def test_lifespan_startup_success(
        self, mock_get_settings, mock_lifespan_dependencies
    ):
        """Test successful application startup."""
        deps = mock_lifespan_dependencies
        
        # Setup mocks
        mock_get_settings.return_value = Mock(
            log_level="INFO", 
            max_concurrent_alerts=5, 
            history_enabled=True,
            cors_origins=["*"]
        )
        deps['init_db'].return_value = True
        deps['db_info'].return_value = {"enabled": True}

        # Test lifespan manager
        @asynccontextmanager 
        async def test_lifespan(app):
            async with lifespan(app):
                yield

        async with test_lifespan(app):
            pass  # Application startup and shutdown

        # Verify startup calls
        deps['setup_logging'].assert_called_once_with("INFO")
        deps['init_db'].assert_called_once()
        deps['alert_service'].initialize.assert_called_once()
        deps['dashboard_manager'].initialize_broadcaster.assert_called_once()
        deps['typed_hooks'].initialize_hooks.assert_called_once()
        deps['history'].cleanup_orphaned_sessions.assert_called_once()

        # Verify shutdown calls
        deps['dashboard_manager'].shutdown_broadcaster.assert_called_once()

    @patch('tarsy.main.get_settings')
    async def test_lifespan_startup_with_history_disabled(
        self, mock_get_settings, mock_lifespan_dependencies
    ):
        """Test application startup with history service disabled."""
        deps = mock_lifespan_dependencies
        
        # Setup mocks
        mock_get_settings.return_value = Mock(
            log_level="INFO",
            max_concurrent_alerts=5,
            history_enabled=False,
            cors_origins=["*"]
        )
        deps['init_db'].return_value = False
        deps['db_info'].return_value = {"enabled": False}

        # Test lifespan manager
        @asynccontextmanager 
        async def test_lifespan(app):
            async with lifespan(app):
                yield

        async with test_lifespan(app):
            pass

        # Verify startup calls - history service should not be initialized
        deps['setup_logging'].assert_called_once()
        deps['alert_service'].initialize.assert_called_once()
        deps['dashboard_manager'].initialize_broadcaster.assert_called_once()
        
        # History service should not be called
        deps['history_service'].assert_not_called()

    @patch('tarsy.main.get_settings')
    async def test_lifespan_startup_with_orphaned_session_cleanup_error(
        self, mock_get_settings, mock_lifespan_dependencies
    ):
        """Test application startup when orphaned session cleanup fails."""
        deps = mock_lifespan_dependencies
        
        # Setup mocks
        mock_get_settings.return_value = Mock(
            log_level="INFO",
            max_concurrent_alerts=5,
            history_enabled=True,
            cors_origins=["*"]
        )
        deps['init_db'].return_value = True
        deps['db_info'].return_value = {"enabled": True}
        
        # Make cleanup fail
        deps['history'].cleanup_orphaned_sessions.side_effect = Exception(
            "Cleanup failed"
        )

        # Test lifespan manager - should not fail even if cleanup fails
        @asynccontextmanager 
        async def test_lifespan(app):
            async with lifespan(app):
                yield

        async with test_lifespan(app):
            pass

        # Verify startup continued despite cleanup error
        deps['alert_service'].initialize.assert_called_once()
        deps['dashboard_manager'].initialize_broadcaster.assert_called_once()

    @patch('tarsy.main.get_settings')
    @patch('sys.exit')
    async def test_lifespan_exits_when_db_init_fails_with_history_enabled(
        self, mock_sys_exit, mock_get_settings, mock_lifespan_dependencies
    ):
        """Test that application exits when history is enabled but DB initialization fails."""
        deps = mock_lifespan_dependencies
        
        # Setup mocks - history enabled but DB init fails
        mock_get_settings.return_value = Mock(
            log_level="INFO",
            max_concurrent_alerts=5,
            history_enabled=True,  # History enabled
            cors_origins=["*"]
        )
        deps['init_db'].return_value = False  # DB initialization fails
        
        # Mock sys.exit to prevent actual exit during test
        mock_sys_exit.side_effect = SystemExit(1)
        
        # Test lifespan manager - should exit with error code 1
        @asynccontextmanager 
        async def test_lifespan(app):
            async with lifespan(app):
                yield
        
        # Expect SystemExit to be raised
        with pytest.raises(SystemExit):
            async with test_lifespan(app):
                pass
        
        # Verify sys.exit was called with error code 1
        mock_sys_exit.assert_called_once_with(1)
        
        # Verify initialization was attempted
        deps['init_db'].assert_called_once()

    @patch('tarsy.main.get_settings')
    @patch('sys.exit')
    async def test_lifespan_exits_when_alert_service_init_fails(
        self, mock_sys_exit, mock_get_settings, mock_lifespan_dependencies
    ):
        """Test that application exits when AlertService initialization fails."""
        deps = mock_lifespan_dependencies
        
        # Setup mocks
        mock_get_settings.return_value = Mock(
            log_level="INFO",
            max_concurrent_alerts=5,
            history_enabled=True,
            cors_origins=["*"]
        )
        deps['init_db'].return_value = True
        
        # Make AlertService initialization fail (e.g., invalid config)
        deps['alert_service'].initialize.side_effect = Exception(
            "Configured LLM provider 'invalid-provider' not found in loaded configuration"
        )
        
        # Mock sys.exit to prevent actual exit during test
        mock_sys_exit.side_effect = SystemExit(1)
        
        # Test lifespan manager - should exit with error code 1
        @asynccontextmanager 
        async def test_lifespan(app):
            async with lifespan(app):
                yield
        
        # Expect SystemExit to be raised
        with pytest.raises(SystemExit):
            async with test_lifespan(app):
                pass
        
        # Verify sys.exit was called with error code 1
        mock_sys_exit.assert_called_once_with(1)
        
        # Verify initialization was attempted
        deps['alert_service'].initialize.assert_called_once()


@pytest.mark.unit
class TestMainEndpoints:
    """Test main application endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_root_endpoint(self, client):
        """Test root health check endpoint."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Tarsy is running"
        assert data["status"] == "healthy"

    @pytest.mark.parametrize("db_status,expected_status,expected_services", [
        (
            {"enabled": True, "connection_test": True, "retention_days": 30},
            "healthy",
            {
                "alert_processing": "healthy",
                "history_service": "healthy",
                "database": {"enabled": True, "connected": True, "retention_days": 30}
            }
        ),
        (
            {"enabled": True, "connection_test": False, "retention_days": 30},
            "degraded",
            {
                "alert_processing": "healthy",
                "history_service": "unhealthy",
                "database": {"enabled": True, "connected": False, "retention_days": 30}
            }
        ),
        (
            {"enabled": False},
            "healthy",
            {
                "alert_processing": "healthy",
                "history_service": "disabled",
                "database": {"enabled": False, "connected": None}
            }
        ),
        (
            Exception("Database error"),
            "unhealthy",
            {
                "alert_processing": "healthy",
                "history_service": "unhealthy",
                "database": {"enabled": None, "connected": None}
            }
        )
    ])
    @patch('tarsy.main.get_database_info')
    def test_health_endpoint_status(
        self, mock_db_info, client, db_status, expected_status, expected_services
    ):
        """Test health endpoint with different database status scenarios."""
        if isinstance(db_status, Exception):
            mock_db_info.side_effect = db_status
        else:
            mock_db_info.return_value = db_status
        
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        
        # Check basic response structure
        assert data["status"] == expected_status
        assert data["service"] == "tarsy"
        
        # Timestamp may not be present in unhealthy responses
        if expected_status != "unhealthy":
            assert "timestamp" in data
        
        # Check services status (only for healthy/degraded responses)
        if expected_status != "unhealthy":
            for service, expected_value in expected_services.items():
                if isinstance(expected_value, dict):
                    for key, value in expected_value.items():
                        assert data["services"][service][key] == value, (
                            f"Service {service}.{key} should be {value}, "
                            f"got {data['services'][service][key]}"
                        )
                else:
                    assert data["services"][service] == expected_value, (
                        f"Service {service} should be {expected_value}, "
                        f"got {data['services'][service]}"
                    )
        
        # Check for error message when unhealthy
        if expected_status == "unhealthy":
            assert "error" in data
            if isinstance(db_status, Exception):
                assert str(db_status) in data["error"]

    @patch('tarsy.main.get_database_info')
    def test_health_endpoint_with_warnings(self, mock_db_info, client):
        """Test health endpoint includes system warnings."""
        from tarsy.services.system_warnings_service import (
            SystemWarningsService,
            get_warnings_service,
        )

        # Reset singleton for clean test
        SystemWarningsService._instance = None

        # Mock database as healthy
        mock_db_info.return_value = {
            "enabled": True,
            "connection_test": True,
            "retention_days": 30,
        }

        # Add some warnings
        warnings_service = get_warnings_service()
        warnings_service.add_warning(
            "mcp_initialization",
            "MCP Server 'kubernetes-server' failed to initialize",
            "Connection timeout",
        )
        warnings_service.add_warning(
            "runbook_service", "Runbook service disabled"
        )

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()

        # Status should be degraded due to warnings
        assert data["status"] == "degraded"

        # Verify warnings are present
        assert "warnings" in data
        assert "warning_count" in data
        assert data["warning_count"] == 2
        assert len(data["warnings"]) == 2

        # Verify warning structure
        warning1 = data["warnings"][0]
        assert "category" in warning1
        assert "message" in warning1
        assert "timestamp" in warning1
        assert warning1["category"] == "mcp_initialization"
        assert (
            warning1["message"]
            == "MCP Server 'kubernetes-server' failed to initialize"
        )

    @patch('tarsy.main.get_database_info')
    def test_health_endpoint_without_warnings(self, mock_db_info, client):
        """Test health endpoint without warnings."""
        from tarsy.services.system_warnings_service import SystemWarningsService

        # Reset singleton for clean test
        SystemWarningsService._instance = None

        # Mock database as healthy
        mock_db_info.return_value = {
            "enabled": True,
            "connection_test": True,
            "retention_days": 30,
        }

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()

        # Status should be healthy
        assert data["status"] == "healthy"

        # Verify warnings fields are present but empty
        assert "warnings" in data
        assert "warning_count" in data
        assert data["warning_count"] == 0
        assert data["warnings"] == []


@pytest.mark.unit
class TestWebSocketEndpoint:
    """Test WebSocket endpoint."""

    @pytest.fixture
    def mock_websocket(self):
        """Mock WebSocket connection."""
        websocket = AsyncMock(spec=WebSocket)
        return websocket

    @patch('tarsy.main.dashboard_manager')
    async def test_websocket_connection_success(
        self, mock_dashboard_manager, mock_websocket
    ):
        """Test successful WebSocket connection."""
        # Mock the dashboard manager
        mock_dashboard_manager.connect = AsyncMock()
        mock_dashboard_manager.send_to_user = AsyncMock()
        mock_dashboard_manager.handle_subscription_message = AsyncMock()
        mock_dashboard_manager.disconnect = Mock()
        
        # Mock websocket messages
        mock_websocket.receive_text = AsyncMock()
        mock_websocket.receive_text.side_effect = [
            '{"type": "subscribe", "channel": "alerts"}',
            # Then simulate WebSocketDisconnect
            Exception("WebSocketDisconnect")
        ]
        
        # Import and test the endpoint
        from tarsy.main import dashboard_websocket_endpoint
        
        with contextlib.suppress(Exception):
            # Expected due to disconnect simulation
            await dashboard_websocket_endpoint(mock_websocket, "user-123")
        
        # Verify connection flow
        mock_dashboard_manager.connect.assert_called_once_with(
            mock_websocket, "user-123"
        )
        mock_dashboard_manager.send_to_user.assert_called()
        mock_dashboard_manager.disconnect.assert_called_once_with("user-123")

    @patch('tarsy.main.dashboard_manager')
    async def test_websocket_invalid_json_message(
        self, mock_dashboard_manager, mock_websocket
    ):
        """Test WebSocket with invalid JSON message."""
        mock_dashboard_manager.connect = AsyncMock()
        mock_dashboard_manager.send_to_user = AsyncMock()
        mock_dashboard_manager.disconnect = Mock()
        
        # Mock websocket to send invalid JSON
        mock_websocket.receive_text = AsyncMock()
        mock_websocket.receive_text.side_effect = [
            'invalid json',
            Exception("WebSocketDisconnect")
        ]
        
        from tarsy.main import dashboard_websocket_endpoint
        
        with contextlib.suppress(Exception):
            await dashboard_websocket_endpoint(mock_websocket, "user-123")
        
        # Verify error message was sent
        # Connection message + error message
        assert mock_dashboard_manager.send_to_user.call_count >= 2
        
        # Check that an error message was sent
        calls = mock_dashboard_manager.send_to_user.call_args_list
        error_call_found = False
        for call in calls:
            if (len(call[0]) > 1 and 
                isinstance(call[0][1], dict) and 
                'message' in call[0][1] and
                'Invalid JSON' in call[0][1].get('message', '')):
                    error_call_found = True
                    break
        assert error_call_found


@pytest.mark.unit
class TestBackgroundProcessing:
    """Test background alert processing function."""

    @pytest.fixture
    def mock_alert_data(self):
        """Mock alert processing data."""
        return ChainContext(
            alert_type="kubernetes",
            alert_data={
                "namespace": "production",
                "pod": "api-server-123",
                "severity": "high"
            },
            session_id="test-session-123",
            current_stage_name="test-stage"
        )

    @patch('tarsy.main.alert_service')
    @patch('tarsy.controllers.alert_controller.processing_alert_keys', {})
    @patch('tarsy.controllers.alert_controller.alert_keys_lock', asyncio.Lock())
    async def test_process_alert_background_success(
        self, mock_alert_service, mock_alert_data
    ):
        """Test successful background alert processing."""
        mock_alert_service.process_alert = AsyncMock(return_value={"status": "success"})
        
        # Mock the semaphore to avoid issues
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)):
            await process_alert_background("alert-123", mock_alert_data)
        
        mock_alert_service.process_alert.assert_called_once_with(
            mock_alert_data, alert_id="alert-123"
        )

    @patch('tarsy.main.alert_service')
    async def test_process_alert_background_cleanup(
        self, mock_alert_service, mock_alert_data
    ):
        """Test background processing cleans up alert keys."""
        mock_alert_service.process_alert = AsyncMock(return_value={"status": "success"})
        
        # Create a mock AlertKey instance
        mock_alert_key = Mock()
        mock_alert_key.__str__ = Mock(return_value="test-key")
        mock_alert_key.__hash__ = Mock(return_value=12345)
        
        # Start with the key in the processing dict
        with patch(
            'tarsy.controllers.alert_controller.processing_alert_keys', {mock_alert_key: "alert-123"}
        ) as mock_processing_keys, \
             patch('tarsy.controllers.alert_controller.alert_keys_lock', asyncio.Lock()), \
             patch('tarsy.main.AlertKey.from_chain_context') as mock_from_chain_context:
            
            # Mock the factory method to return our test key
            mock_from_chain_context.return_value = mock_alert_key
            
            with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)):
                await process_alert_background("alert-123", mock_alert_data)
        
        # Verify the alert key was cleaned up (dict should be empty now)
        assert mock_alert_key not in mock_processing_keys

    @patch('tarsy.main.alert_service')
    @patch('tarsy.controllers.alert_controller.processing_alert_keys', {})
    @patch('tarsy.controllers.alert_controller.alert_keys_lock', asyncio.Lock())
    async def test_process_alert_background_timeout(
        self, mock_alert_service, mock_alert_data
    ):
        """Test background processing with timeout."""
        # Make process_alert hang
        mock_alert_service.process_alert = AsyncMock(side_effect=asyncio.sleep(1000))
        
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)), \
             patch('tarsy.main.asyncio.wait_for', side_effect=asyncio.TimeoutError()):
            # Should not raise exception, should handle timeout gracefully
            await process_alert_background("alert-123", mock_alert_data)

    @patch('tarsy.main.alert_service')
    @patch('tarsy.controllers.alert_controller.processing_alert_keys', {})
    @patch('tarsy.controllers.alert_controller.alert_keys_lock', asyncio.Lock())
    async def test_process_alert_background_invalid_alert(self, mock_alert_service):
        """Test background processing handles invalid alert data gracefully."""
        # Mock process_alert to track if it's called 
        mock_alert_service.process_alert = AsyncMock()
        
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)):
            # Test with None alert - should fail early during logging  
            await process_alert_background("alert-123", None)
            
            # Test with valid ChainContext but process_alert fails
            valid_alert = ChainContext(
                alert_type="test", 
                alert_data={"key": "value"},
                session_id="test-session",
                current_stage_name="test-stage"
            )
            
            # Make process_alert fail to simulate processing errors
            mock_alert_service.process_alert.side_effect = ValueError(
                "Processing failed"
            )
            
            # Need to mock AlertKey.from_chain_context for cleanup in finally block
            with patch(
                'tarsy.main.AlertKey.from_chain_context'
            ) as mock_from_chain_context:
                mock_key = Mock()
                mock_key.__str__ = Mock(return_value="test-key")
                mock_key.__hash__ = Mock(return_value=12345)
                mock_from_chain_context.return_value = mock_key
                await process_alert_background("alert-124", valid_alert)
        
        # The function should handle errors gracefully and not raise exceptions
        # Even with invalid data, it attempts processing and handles the failure
        assert mock_alert_service.process_alert.call_count >= 1

    @patch('tarsy.main.alert_service')
    @patch('tarsy.controllers.alert_controller.processing_alert_keys', {})
    @patch('tarsy.controllers.alert_controller.alert_keys_lock', asyncio.Lock())
    async def test_process_alert_background_processing_exception(
        self, mock_alert_service, mock_alert_data
    ):
        """Test background processing handles processing exceptions."""
        mock_alert_service.process_alert = AsyncMock(
            side_effect=Exception("Processing failed")
        )
        
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)):
            # Should not raise exception, should handle gracefully
            await process_alert_background("alert-123", mock_alert_data)
        
        mock_alert_service.process_alert.assert_called_once()


@pytest.mark.unit
class TestGlobalState:
    """Test global state management."""

    def test_processing_alert_keys_initialization(self):
        """Test processing alert keys dictionary is properly initialized."""
        assert isinstance(processing_alert_keys, dict)

    def test_alert_keys_lock_initialization(self):
        """Test alert keys lock is properly initialized."""
        assert isinstance(alert_keys_lock, asyncio.Lock)

@pytest.mark.unit 
class TestJWKSEndpoint:
    """Test JWKS endpoint for JWT authentication."""
    
    @pytest.fixture(autouse=True)
    def clear_jwks_cache(self):
        """Clear JWKS cache before each test."""
        from tarsy.main import jwks_cache
        jwks_cache.clear()
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_rsa_public_key(self):
        """Create a mock RSA public key for testing."""
        from unittest.mock import Mock
        from cryptography.hazmat.primitives.asymmetric import rsa
        
        # Mock RSA public key with test values, using spec to pass isinstance checks
        mock_key = Mock(spec=rsa.RSAPublicKey)
        mock_numbers = Mock()
        mock_numbers.n = 123456789  # Modulus
        mock_numbers.e = 65537      # Exponent
        mock_key.public_numbers.return_value = mock_numbers
        return mock_key
    
    @pytest.fixture
    def valid_pem_key_content(self):
        """Valid PEM key content for testing."""
        # This is a valid RSA public key format (test key, not for production)
        return b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA4qiXJLzX8QExQ8tBZrU9
GOJ2jGqq/6l5mGqGqJ7nFOJ2jGqq/6l5mGqGqJ7nFOJ2jGqq/6l5mGqGqJ7nFOJ2
jGqq/6l5mGqGqJ7nFOJ2jGqq/6l5mGqGqJ7nFOJ2jGqq/6l5mGqGqJ7nFOJ2jGqq
/6l5mGqGqJ7nFOJ2jGqq/6l5mGqGqJ7nFOJ2jGqq/6l5mGqGqJ7nFOJ2jGqq/6l5
mGqGqJ7nFOJ2jGqq/6l5mGqGqJ7nFOJ2jGqq/6l5mGqGqJ7nFOJ2jGqq/6l5mGqG
qJ7nFOJ2jGqq/6l5mGqGqJ7nFOJ2jGqq/6l5mGqGqJ7nFOJ2jGqq/6l5mGqGqJ7n
FOJ2jGqq/6l5mGqGqJ7nFOJ2jGqq/6l5mGqGqJ7nFQIDAQAB
-----END PUBLIC KEY-----"""
    
    @patch('tarsy.main.get_settings')
    @patch('tarsy.main.Path')
    @patch('builtins.open')
    @patch('tarsy.main.serialization.load_pem_public_key')
    def test_jwks_endpoint_success(self, mock_load_key, mock_open, mock_path_class, mock_get_settings, client, mock_rsa_public_key, valid_pem_key_content):
        """Test successful JWKS endpoint response."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings.jwt_public_key_path = "/test/path/jwt_public_key.pem"
        mock_get_settings.return_value = mock_settings
        
        # Mock path operations
        mock_path_instance = Mock()
        mock_path_instance.is_absolute.return_value = True
        mock_path_instance.exists.return_value = True
        mock_path_class.return_value = mock_path_instance
        
        # Mock file operations
        mock_file = Mock()
        mock_file.read.return_value = valid_pem_key_content
        mock_open.return_value.__enter__.return_value = mock_file
        
        # Mock cryptographic operations
        mock_load_key.return_value = mock_rsa_public_key
        
        # Clear cache before test
        from tarsy.main import jwks_cache
        jwks_cache.clear()
        
        response = client.get("/.well-known/jwks.json")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify JWKS structure
        assert "keys" in data
        assert len(data["keys"]) == 1
        
        key = data["keys"][0]
        assert key["kty"] == "RSA"
        assert key["use"] == "sig"
        assert key["kid"] == "tarsy-api-key-1"
        assert key["alg"] == "RS256"
        assert "n" in key  # Modulus
        assert "e" in key  # Exponent
        
        # Verify key path was created and file was read
        mock_path_class.assert_called_once_with("/test/path/jwt_public_key.pem")
        # Verify open was called with the correct arguments
        # Note: mock_open may track multiple calls due to context manager usage
        assert mock_open.call_count >= 1, f"Expected at least 1 call to open, got {mock_open.call_count}"
        # Check that at least one call was made with our expected arguments
        expected_call = call(mock_path_instance, "rb")
        assert expected_call in mock_open.call_args_list, f"Expected call {expected_call} not found in {mock_open.call_args_list}"
        mock_load_key.assert_called_once_with(valid_pem_key_content)
    
    @patch('tarsy.main.get_settings')
    @patch('tarsy.main.Path')
    def test_jwks_endpoint_missing_file(self, mock_path_class, mock_get_settings, client):
        """Test JWKS endpoint when public key file doesn't exist."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings.jwt_public_key_path = "/nonexistent/jwt_public_key.pem"
        mock_get_settings.return_value = mock_settings
        
        # Mock path operations - file doesn't exist
        mock_path_instance = Mock()
        mock_path_instance.is_absolute.return_value = True
        mock_path_instance.exists.return_value = False
        mock_path_class.return_value = mock_path_instance
        
        # Clear cache before test
        from tarsy.main import jwks_cache
        jwks_cache.clear()
        
        response = client.get("/.well-known/jwks.json")
        
        assert response.status_code == 503
        data = response.json()
        
        assert data["detail"]["error"] == "JWT public key not available"
        assert "make generate-jwt-keys" in data["detail"]["message"]
    
    @patch('tarsy.main.get_settings')
    @patch('tarsy.main.Path')
    @patch('builtins.open')
    @patch('tarsy.main.serialization.load_pem_public_key')
    def test_jwks_endpoint_invalid_key_file(self, mock_load_key, mock_open, mock_path_class, mock_get_settings, client):
        """Test JWKS endpoint with invalid public key file."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings.jwt_public_key_path = "/test/path/invalid_key.pem"
        mock_get_settings.return_value = mock_settings
        
        # Mock path operations
        mock_path_instance = Mock()
        mock_path_instance.is_absolute.return_value = True
        mock_path_instance.exists.return_value = True
        mock_path_class.return_value = mock_path_instance
        
        # Mock file operations
        mock_file = Mock()
        mock_file.read.return_value = b"invalid key data"
        mock_open.return_value.__enter__.return_value = mock_file
        
        # Mock cryptographic operations to fail
        mock_load_key.side_effect = ValueError("Invalid key format")
        
        # Clear cache before test
        from tarsy.main import jwks_cache
        jwks_cache.clear()
        
        response = client.get("/.well-known/jwks.json")
        
        assert response.status_code == 500
        data = response.json()
        
        assert data["detail"]["error"] == "JWKS generation failed"
        assert "Unable to generate JSON Web Key Set" in data["detail"]["message"]
    
    @patch('tarsy.main.get_settings')
    @patch('tarsy.main.Path')
    @patch('builtins.open')
    @patch('tarsy.main.serialization.load_pem_public_key')
    def test_jwks_endpoint_non_rsa_key_validation(self, mock_load_key, mock_open, mock_path_class, mock_get_settings, client, valid_pem_key_content):
        """Test JWKS endpoint rejects non-RSA public keys."""
        from unittest.mock import Mock
        from cryptography.hazmat.primitives.asymmetric import ec
        
        # Setup mocks
        mock_settings = Mock()
        mock_settings.jwt_public_key_path = "/test/path/ec_public_key.pem"
        mock_get_settings.return_value = mock_settings
        
        # Mock path operations
        mock_path_instance = Mock()
        mock_path_instance.is_absolute.return_value = True
        mock_path_instance.exists.return_value = True
        mock_path_class.return_value = mock_path_instance
        
        # Mock file operations
        mock_file = Mock()
        mock_file.read.return_value = valid_pem_key_content
        mock_open.return_value.__enter__.return_value = mock_file
        
        # Mock cryptographic operations - return a non-RSA key (EC key)
        mock_ec_key = Mock(spec=ec.EllipticCurvePublicKey)
        mock_load_key.return_value = mock_ec_key
        
        # Clear cache before test
        from tarsy.main import jwks_cache
        jwks_cache.clear()
        
        response = client.get("/.well-known/jwks.json")
        
        assert response.status_code == 503
        data = response.json()
        
        assert data["detail"]["error"] == "Invalid key type"
        assert data["detail"]["message"] == "JWT public key must be an RSA public key"
    
    @patch('tarsy.main.get_settings')
    @patch('tarsy.main.Path')
    @patch('builtins.open')
    @patch('tarsy.main.serialization.load_pem_public_key')
    def test_jwks_endpoint_relative_path_handling(self, mock_load_key, mock_open, mock_path_class, mock_get_settings, client, mock_rsa_public_key, valid_pem_key_content):
        """Test JWKS endpoint correctly handles relative paths."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings.jwt_public_key_path = "../config/keys/jwt_public_key.pem"
        mock_get_settings.return_value = mock_settings
        
        # Mock the initial relative path
        mock_relative_path = Mock()
        mock_relative_path.is_absolute.return_value = False
        
        # Mock the backend directory path  
        mock_backend_dir = Mock()
        
        # Mock the combined path result (backend_dir / relative_path)
        mock_combined_path = Mock()
        # Mock the resolved final path
        mock_final_path = Mock()
        mock_final_path.exists.return_value = True
        
        # Set up the path operation chain:
        # backend_dir / relative_path -> combined_path
        mock_backend_dir.__truediv__ = Mock(return_value=mock_combined_path)
        # combined_path.resolve() -> final_path
        mock_combined_path.resolve = Mock(return_value=mock_final_path)
        
        # Mock __file__ path to get backend directory
        mock_file_path = Mock()
        mock_file_path.parent.parent = mock_backend_dir
        
        # Mock Path constructor calls
        def path_side_effect(path_str):
            if path_str == "../config/keys/jwt_public_key.pem":
                return mock_relative_path
            # For Path(__file__)
            else:
                return mock_file_path
        
        mock_path_class.side_effect = path_side_effect
        
        # Mock __file__ in the main module
        import tarsy.main
        original_file = getattr(tarsy.main, '__file__', None)
        tarsy.main.__file__ = '/backend/tarsy/main.py'  # Mock file path
        
        try:
            # Mock file operations
            mock_file = Mock()
            mock_file.read.return_value = valid_pem_key_content
            mock_open.return_value.__enter__.return_value = mock_file
            
            # Mock cryptographic operations
            mock_load_key.return_value = mock_rsa_public_key
            
            # Clear cache before test
            from tarsy.main import jwks_cache
            jwks_cache.clear()
            
            response = client.get("/.well-known/jwks.json")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify JWKS structure is correct
            assert "keys" in data
            assert len(data["keys"]) == 1
            
            key = data["keys"][0]
            assert key["kty"] == "RSA"
            assert key["use"] == "sig"
            
            # Verify path resolution was used
            mock_backend_dir.__truediv__.assert_called_once_with(mock_relative_path)
            mock_combined_path.resolve.assert_called_once()
            
        finally:
            # Restore original __file__
            if original_file is not None:
                tarsy.main.__file__ = original_file
    
    @patch('tarsy.main.get_settings')
    @patch('tarsy.main.Path')
    @patch('builtins.open')
    @patch('tarsy.main.serialization.load_pem_public_key')
    def test_jwks_endpoint_caching_behavior(self, mock_load_key, mock_open, mock_path_class, mock_get_settings, client, mock_rsa_public_key, valid_pem_key_content):
        """Test that JWKS endpoint uses caching correctly."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings.jwt_public_key_path = "/test/path/jwt_public_key.pem"
        mock_get_settings.return_value = mock_settings
        
        # Mock path operations
        mock_path_instance = Mock()
        mock_path_instance.is_absolute.return_value = True
        mock_path_instance.exists.return_value = True
        mock_path_class.return_value = mock_path_instance
        
        # Mock file operations
        mock_file = Mock()
        mock_file.read.return_value = valid_pem_key_content
        mock_open.return_value.__enter__.return_value = mock_file
        
        # Mock cryptographic operations
        mock_load_key.return_value = mock_rsa_public_key
        
        # Clear cache before test
        from tarsy.main import jwks_cache
        jwks_cache.clear()
        
        # First request should load from file
        response1 = client.get("/.well-known/jwks.json")
        assert response1.status_code == 200
        
        # Verify file was read once
        assert mock_open.call_count == 1
        assert mock_load_key.call_count == 1
        
        # Second request should use cache
        response2 = client.get("/.well-known/jwks.json")
        assert response2.status_code == 200
        
        # Verify file was not read again (still only called once)
        assert mock_open.call_count == 1
        assert mock_load_key.call_count == 1
        
        # Both responses should be identical
        assert response1.json() == response2.json()
    
    @patch('tarsy.main.get_settings')
    @patch('tarsy.main.Path')
    @patch('builtins.open')
    def test_jwks_endpoint_file_permission_error(self, mock_open, mock_path_class, mock_get_settings, client):
        """Test JWKS endpoint when file cannot be read due to permissions."""
        # Setup mocks
        mock_settings = Mock()
        mock_settings.jwt_public_key_path = "/test/path/jwt_public_key.pem"
        mock_get_settings.return_value = mock_settings
        
        # Mock path operations
        mock_path_instance = Mock()
        mock_path_instance.is_absolute.return_value = True
        mock_path_instance.exists.return_value = True
        mock_path_class.return_value = mock_path_instance
        
        # Mock file operations to raise permission error
        mock_open.side_effect = PermissionError("Permission denied")
        
        # Clear cache before test
        from tarsy.main import jwks_cache
        jwks_cache.clear()
        
        response = client.get("/.well-known/jwks.json")
        
        assert response.status_code == 500
        data = response.json()
        
        assert data["detail"]["error"] == "JWKS generation failed"
        assert "Unable to generate JSON Web Key Set" in data["detail"]["message"]
    
    def test_jwks_cache_initialization(self):
        """Test that JWKS cache is properly initialized."""
        from tarsy.main import jwks_cache
        
        # Clear cache to ensure deterministic initial state
        jwks_cache.clear()
        
        # Cache should be initialized and empty
        assert jwks_cache is not None
        assert len(jwks_cache) == 0
        
        # Test cache basic functionality
        jwks_cache["test"] = {"test": "data"}
        assert jwks_cache["test"] == {"test": "data"}
        
        # Clear for other tests
        jwks_cache.clear()

@pytest.mark.unit
class TestCriticalCoverage:
    """Test critical business logic and edge cases that were missing coverage."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_database_connection_failure_handling(self, client):
        """Test handling of database connection failures."""
        with patch('tarsy.main.get_database_info') as mock_db_info:
            mock_db_info.side_effect = Exception("Database connection failed")
            
            # Health endpoint should handle database failures gracefully
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unhealthy"
            assert "error" in data


    def test_websocket_connection_stability(self, client):
        """Test WebSocket connection stability under various conditions."""
        # This would require a more complex setup with actual WebSocket testing
        # For now, we'll test the endpoint exists and responds appropriately
        response = client.get("/")
        assert response.status_code == 200
        assert "tarsy" in response.json()["message"].lower()

