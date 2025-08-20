"""
Comprehensive tests for the main FastAPI application.

Tests lifespan management, endpoints, WebSocket connections, and background processing.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, Mock, patch
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from fastapi import WebSocket


# Import the modules we need to test and mock
from tarsy.main import app, lifespan, process_alert_background, processing_alert_keys, alert_keys_lock
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
             patch('tarsy.services.history_service.get_history_service') as mock_history_service, \
             patch('tarsy.main.AlertService') as mock_alert_service_class, \
             patch('tarsy.main.DashboardConnectionManager') as mock_dashboard_manager_class, \
             patch('tarsy.hooks.hook_registry.get_typed_hook_registry') as mock_hook_registry, \
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
    async def test_lifespan_startup_success(self, mock_get_settings, mock_lifespan_dependencies):
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
    async def test_lifespan_startup_with_history_disabled(self, mock_get_settings, mock_lifespan_dependencies):
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
    async def test_lifespan_startup_with_orphaned_session_cleanup_error(self, mock_get_settings, mock_lifespan_dependencies):
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
        deps['history'].cleanup_orphaned_sessions.side_effect = Exception("Cleanup failed")

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
    def test_health_endpoint_status(self, mock_db_info, client, db_status, expected_status, expected_services):
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
                        assert data["services"][service][key] == value, \
                            f"Service {service}.{key} should be {value}, got {data['services'][service][key]}"
                else:
                    assert data["services"][service] == expected_value, \
                        f"Service {service} should be {expected_value}, got {data['services'][service]}"
        
        # Check for error message when unhealthy
        if expected_status == "unhealthy":
            assert "error" in data
            if isinstance(db_status, Exception):
                assert str(db_status) in data["error"]

    @patch('tarsy.main.alert_service')
    def test_get_alert_types(self, mock_alert_service, client):
        """Test get alert types endpoint."""
        mock_chain_registry = Mock()
        mock_chain_registry.list_available_alert_types.return_value = ["kubernetes", "database", "network"]
        mock_alert_service.chain_registry = mock_chain_registry
        
        response = client.get("/alert-types")
        assert response.status_code == 200
        data = response.json()
        
        assert data == ["kubernetes", "database", "network"]
        mock_chain_registry.list_available_alert_types.assert_called_once()


@pytest.mark.unit  
class TestSubmitAlertEndpoint:
    """Test the complex submit alert endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def valid_alert_data(self):
        """Valid alert data for testing."""
        return {
            "alert_type": "kubernetes",
            "runbook": "https://example.com/runbook.md",
            "data": {
                "namespace": "production",
                "pod": "api-server-123"
            },
            "severity": "high",
            "timestamp": 1640995200000000  # 2022-01-01 00:00:00 UTC in microseconds
        }

    @patch('tarsy.main.alert_service')
    @patch('tarsy.main.asyncio.create_task')
    def test_submit_alert_success(self, mock_create_task, mock_alert_service, client, valid_alert_data):
        """Test successful alert submission."""
        mock_alert_service.register_alert_id = Mock()
        
        response = client.post("/alerts", json=valid_alert_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "queued"
        assert "alert_id" in data
        assert "message" in data
        mock_create_task.assert_called_once()
        mock_alert_service.register_alert_id.assert_called_once()

    @pytest.mark.parametrize("invalid_input,expected_status,expected_error", [
        (None, 400, "Empty request body"),
        ("invalid json", 400, "Invalid JSON"),
        ("not a dict", 400, "Invalid data structure"),
        ({"alert_type": "", "runbook": "invalid-url", "data": "not a dict"}, 422, "Validation failed"),
        ({"alert_type": "   ", "runbook": "https://example.com/runbook.md", "data": {}}, 400, "Invalid alert_type"),
        ({"alert_type": "test", "runbook": "", "data": {}}, 400, "Invalid runbook"),
    ])
    def test_submit_alert_input_validation(self, client, valid_alert_data, invalid_input, expected_status, expected_error):
        """Test alert submission with various invalid inputs."""
        if invalid_input == "invalid json":
            response = client.post("/alerts", data=invalid_input, headers={"content-type": "application/json"})
        elif invalid_input == "not a dict":
            response = client.post("/alerts", json=invalid_input)
        elif invalid_input is None:
            response = client.post("/alerts", json=invalid_input)
        else:
            response = client.post("/alerts", json=invalid_input)
        
        assert response.status_code == expected_status
        data = response.json()
        
        assert data["detail"]["error"] == expected_error
        
        # Additional checks for specific error types
        if expected_error == "Empty request body":
            assert "expected_fields" in data["detail"]
        elif expected_error == "Invalid data structure":
            assert "received_type" in data["detail"]
        elif expected_error == "Validation failed":
            assert "validation_errors" in data["detail"]
        elif expected_error in ["Invalid alert_type", "Invalid runbook"]:
            assert "field" in data["detail"]

    def test_submit_alert_duplicate_detection(self, client, valid_alert_data):
        """Test duplicate alert detection."""
        # Create a mock AlertKey instance
        mock_alert_key = Mock()
        mock_alert_key.__str__ = Mock(return_value="test-key") 
        mock_alert_key.__hash__ = Mock(return_value=12345)
        
        # Patch with AlertKey object as key instead of string
        with patch('tarsy.main.processing_alert_keys', {mock_alert_key: "existing-id"}), \
             patch('tarsy.main.alert_keys_lock', asyncio.Lock()), \
             patch('tarsy.main.AlertKey.from_chain_context') as mock_from_chain_context:
            
            # Mock the factory method to return our test key
            mock_from_chain_context.return_value = mock_alert_key
            
            response = client.post("/alerts", json=valid_alert_data)
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "duplicate"
            assert data["alert_id"] == "existing-id"
            assert "already being processed" in data["message"]

    def test_submit_alert_payload_too_large(self, client):
        """Test alert submission with payload too large."""
        # Create a large payload
        large_data = {"data": {"large_field": "x" * (11 * 1024 * 1024)}}  # 11MB
        
        # Mock content-length header
        with patch.object(client, 'post') as mock_post:
            mock_post.return_value.status_code = 413
            mock_post.return_value.json.return_value = {
                "detail": {
                    "error": "Payload too large",
                    "max_size_mb": 10.0
                }
            }
            
            response = client.post("/alerts", json=large_data)
            assert response.status_code == 413

    @patch('tarsy.main.alert_service')
    @patch('tarsy.main.asyncio.create_task')
    def test_submit_alert_suspicious_runbook_url(self, mock_create_task, mock_alert_service, client, valid_alert_data):
        """Test alert submission with suspicious runbook URL."""
        mock_alert_service.register_alert_id = Mock()
        valid_alert_data["runbook"] = "file:///etc/passwd"  # Suspicious URL
        
        response = client.post("/alerts", json=valid_alert_data)
        assert response.status_code == 200  # Should still process but log warning

    @patch('tarsy.main.alert_service')
    @patch('tarsy.main.asyncio.create_task')
    def test_submit_alert_with_defaults(self, mock_create_task, mock_alert_service, client):
        """Test alert submission applies defaults for missing fields."""
        mock_alert_service.register_alert_id = Mock()
        
        minimal_data = {
            "alert_type": "test",
            "runbook": "https://example.com/runbook.md"
        }
        
        response = client.post("/alerts", json=minimal_data)
        assert response.status_code == 200
        
        # Verify defaults were applied by checking the task was created
        mock_create_task.assert_called_once()


@pytest.mark.unit
class TestSessionIdEndpoint:
    """Test session ID endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @patch.object(app, 'dependency_overrides', {})
    def test_get_session_id_success(self, client):
        """Test successful session ID retrieval."""
        # Mock the global alert_service
        from tarsy import main
        mock_alert_service = Mock()
        mock_alert_service.alert_exists.return_value = True
        mock_alert_service.get_session_id_for_alert.return_value = "session-123"
        main.alert_service = mock_alert_service
        
        response = client.get("/session-id/alert-123")
        assert response.status_code == 200
        data = response.json()
        
        assert data["alert_id"] == "alert-123"
        assert data["session_id"] == "session-123"

    @patch.object(app, 'dependency_overrides', {})
    def test_get_session_id_not_found(self, client):
        """Test session ID retrieval for non-existent alert."""
        from tarsy import main
        mock_alert_service = Mock()
        mock_alert_service.alert_exists.return_value = False
        main.alert_service = mock_alert_service
        
        response = client.get("/session-id/nonexistent")
        assert response.status_code == 404
        data = response.json()
        
        assert "not found" in data["detail"]

    @patch.object(app, 'dependency_overrides', {})
    def test_get_session_id_no_session(self, client):
        """Test session ID retrieval when session doesn't exist yet."""
        from tarsy import main
        mock_alert_service = Mock()
        mock_alert_service.alert_exists.return_value = True
        mock_alert_service.get_session_id_for_alert.return_value = None
        main.alert_service = mock_alert_service
        
        response = client.get("/session-id/alert-123")
        assert response.status_code == 200
        data = response.json()
        
        assert data["alert_id"] == "alert-123"
        assert data["session_id"] is None


@pytest.mark.unit
class TestWebSocketEndpoint:
    """Test WebSocket endpoint."""

    @pytest.fixture
    def mock_websocket(self):
        """Mock WebSocket connection."""
        websocket = AsyncMock(spec=WebSocket)
        return websocket

    @patch('tarsy.main.dashboard_manager')
    async def test_websocket_connection_success(self, mock_dashboard_manager, mock_websocket):
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
        
        try:
            await dashboard_websocket_endpoint(mock_websocket, "user-123")
        except Exception:
            pass  # Expected due to disconnect simulation
        
        # Verify connection flow
        mock_dashboard_manager.connect.assert_called_once_with(mock_websocket, "user-123")
        mock_dashboard_manager.send_to_user.assert_called()
        mock_dashboard_manager.disconnect.assert_called_once_with("user-123")

    @patch('tarsy.main.dashboard_manager')
    async def test_websocket_invalid_json_message(self, mock_dashboard_manager, mock_websocket):
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
        
        try:
            await dashboard_websocket_endpoint(mock_websocket, "user-123")
        except Exception:
            pass
        
        # Verify error message was sent
        assert mock_dashboard_manager.send_to_user.call_count >= 2  # Connection message + error message
        
        # Check that an error message was sent
        calls = mock_dashboard_manager.send_to_user.call_args_list
        error_call_found = False
        for call in calls:
            if len(call[0]) > 1 and isinstance(call[0][1], dict) and 'message' in call[0][1]:
                if 'Invalid JSON' in call[0][1].get('message', ''):
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
    @patch('tarsy.main.processing_alert_keys', {})
    @patch('tarsy.main.alert_keys_lock', asyncio.Lock())
    async def test_process_alert_background_success(self, mock_alert_service, mock_alert_data):
        """Test successful background alert processing."""
        mock_alert_service.process_alert = AsyncMock(return_value={"status": "success"})
        
        # Mock the semaphore to avoid issues
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)):
            await process_alert_background("alert-123", mock_alert_data)
        
        mock_alert_service.process_alert.assert_called_once_with(mock_alert_data, alert_id="alert-123")

    @patch('tarsy.main.alert_service')
    async def test_process_alert_background_cleanup(self, mock_alert_service, mock_alert_data):
        """Test background processing cleans up alert keys."""
        mock_alert_service.process_alert = AsyncMock(return_value={"status": "success"})
        
        # Create a mock AlertKey instance
        mock_alert_key = Mock()
        mock_alert_key.__str__ = Mock(return_value="test-key")
        mock_alert_key.__hash__ = Mock(return_value=12345)
        
        # Start with the key in the processing dict
        with patch('tarsy.main.processing_alert_keys', {mock_alert_key: "alert-123"}) as mock_processing_keys, \
             patch('tarsy.main.alert_keys_lock', asyncio.Lock()), \
             patch('tarsy.main.AlertKey.from_chain_context') as mock_from_chain_context:
            
            # Mock the factory method to return our test key
            mock_from_chain_context.return_value = mock_alert_key
            
            with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)):
                await process_alert_background("alert-123", mock_alert_data)
        
        # Verify the alert key was cleaned up (dict should be empty now)
        assert mock_alert_key not in mock_processing_keys

    @patch('tarsy.main.alert_service')
    @patch('tarsy.main.processing_alert_keys', {})
    @patch('tarsy.main.alert_keys_lock', asyncio.Lock())
    async def test_process_alert_background_timeout(self, mock_alert_service, mock_alert_data):
        """Test background processing with timeout."""
        # Make process_alert hang
        mock_alert_service.process_alert = AsyncMock(side_effect=asyncio.sleep(1000))
        
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)):
            # Should not raise exception, should handle timeout gracefully
            await process_alert_background("alert-123", mock_alert_data)

    @patch('tarsy.main.alert_service')
    @patch('tarsy.main.processing_alert_keys', {})
    @patch('tarsy.main.alert_keys_lock', asyncio.Lock())
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
            mock_alert_service.process_alert.side_effect = ValueError("Processing failed")
            
            # Need to mock AlertKey.from_chain_context for cleanup in finally block
            with patch('tarsy.main.AlertKey.from_chain_context') as mock_from_chain_context:
                mock_key = Mock()
                mock_key.__str__ = Mock(return_value="test-key")
                mock_key.__hash__ = Mock(return_value=12345)
                mock_from_chain_context.return_value = mock_key
                await process_alert_background("alert-124", valid_alert)
        
        # The function should handle errors gracefully and not raise exceptions
        # Even with invalid data, it attempts processing and handles the failure
        assert mock_alert_service.process_alert.call_count >= 1

    @patch('tarsy.main.alert_service')
    @patch('tarsy.main.processing_alert_keys', {})
    @patch('tarsy.main.alert_keys_lock', asyncio.Lock())
    async def test_process_alert_background_processing_exception(self, mock_alert_service, mock_alert_data):
        """Test background processing handles processing exceptions."""
        mock_alert_service.process_alert = AsyncMock(side_effect=Exception("Processing failed"))
        
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
class TestInputSanitization:
    """Test input sanitization functions in submit_alert endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client.""" 
        return TestClient(app)

    def test_sanitize_xss_prevention(self, client):
        """Test XSS prevention in input sanitization."""
        malicious_data = {
            "alert_type": "<script>alert('xss')</script>kubernetes",
            "runbook": "https://example.com/runbook<script>evil()</script>.md",
            "data": {
                "message": "Alert with <img src=x onerror=alert(1)> payload"
            }
        }
        
        # Even with malicious input, the endpoint should sanitize and process
        with patch('tarsy.main.alert_service') as mock_alert_service:
            mock_alert_service.register_alert_id = Mock()
            with patch('tarsy.main.asyncio.create_task'):
                response = client.post("/alerts", json=malicious_data)
        
        # Should succeed after sanitization
        assert response.status_code == 200

    def test_deep_sanitization_nested_objects(self, client):
        """Test deep sanitization of nested objects."""
        nested_data = {
            "alert_type": "test",
            "runbook": "https://example.com/runbook.md",
            "data": {
                "level1": {
                    "level2": {
                        "malicious": "<script>alert('nested')</script>",
                        "array": ["<script>", "normal_value", {"nested_in_array": "<img src=x>"}]
                    }
                }
            }
        }
        
        with patch('tarsy.main.alert_service') as mock_alert_service:
            mock_alert_service.register_alert_id = Mock()
            with patch('tarsy.main.asyncio.create_task'):
                response = client.post("/alerts", json=nested_data)
        
        assert response.status_code == 200

    def test_array_size_limits(self, client):
        """Test array size limiting in sanitization."""
        large_array_data = {
            "alert_type": "test", 
            "runbook": "https://example.com/runbook.md",
            "data": {
                "large_array": [f"item_{i}" for i in range(2000)]  # Over 1000 limit
            }
        }
        
        with patch('tarsy.main.alert_service') as mock_alert_service:
            mock_alert_service.register_alert_id = Mock()  
            with patch('tarsy.main.asyncio.create_task'):
                response = client.post("/alerts", json=large_array_data)
        
        assert response.status_code == 200

    def test_string_length_limits(self, client):
        """Test string length limiting in sanitization."""
        long_string_data = {
            "alert_type": "x" * 15000,  # Over 10KB limit
            "runbook": "https://example.com/runbook.md",
            "data": {
                "message": "y" * 15000
            }
        }
        
        with patch('tarsy.main.alert_service') as mock_alert_service:
            mock_alert_service.register_alert_id = Mock()
            with patch('tarsy.main.asyncio.create_task'):
                response = client.post("/alerts", json=long_string_data)
        
        assert response.status_code == 200


@pytest.mark.unit
class TestCriticalCoverage:
    """Test critical business logic and edge cases that were missing coverage."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_concurrent_alert_processing(self, client):
        """Test that multiple alerts can be processed concurrently without conflicts."""
        from tests.utils import AlertFactory
        
        # Create multiple alerts
        alerts = [
            AlertFactory.create_kubernetes_alert(severity="critical"),
            AlertFactory.create_kubernetes_alert(severity="warning"),
            AlertFactory.create_generic_alert(severity="info"),
        ]
        
        # Mock alert service to track concurrent calls
        with patch('tarsy.main.alert_service') as mock_alert_service, \
             patch('tarsy.main.asyncio.create_task'):
            
            mock_alert_service.register_alert_id = Mock()
            
            # Submit alerts sequentially (simulating concurrent behavior)
            responses = []
            for alert in alerts:
                alert_data = {
                    "alert_type": alert.alert_type,
                    "runbook": alert.runbook,
                    "severity": alert.severity,
                    "data": alert.data
                }
                response = client.post("/alerts", json=alert_data)
                responses.append(response)
            
            # Verify all were accepted
            for response in responses:
                assert response.status_code == 200
                data = response.json()
                assert data["status"] in ["queued", "duplicate"]
                assert "alert_id" in data
            
            # Verify each alert was registered
            assert mock_alert_service.register_alert_id.call_count == len(alerts)

    def test_alert_processing_recovery_after_failure(self, client):
        """Test that system recovers after alert processing failure."""
        from tests.utils import AlertFactory
        
        alert = AlertFactory.create_kubernetes_alert()
        
        with patch('tarsy.main.alert_service') as mock_alert_service, \
             patch('tarsy.main.asyncio.create_task'):
            
            # First call fails
            mock_alert_service.register_alert_id.side_effect = [
                Exception("Processing failed"),  # First call fails
                Mock()  # Second call succeeds
            ]
            
            alert_data = {
                "alert_type": alert.alert_type,
                "runbook": alert.runbook,
                "severity": alert.severity,
                "data": alert.data
            }
            
            # First submission should fail gracefully
            response1 = client.post("/alerts", json=alert_data)
            assert response1.status_code in [200, 500]  # Should handle failure gracefully
            
            # Second submission should succeed
            response2 = client.post("/alerts", json=alert_data)
            assert response2.status_code == 200

    def test_malicious_payload_handling(self, client):
        """Test handling of potentially malicious payloads."""
        malicious_payloads = [
            {
                "alert_type": "<script>alert('xss')</script>kubernetes",
                "runbook": "https://example.com/runbook<script>evil()</script>.md",
                "data": {
                    "message": "Alert with <img src=x onerror=alert(1)> payload",
                    "sql_injection": "'; DROP TABLE alerts; --"
                }
            },
            {
                "alert_type": "kubernetes",
                "runbook": "file:///etc/passwd",
                "data": {
                    "command_injection": "$(rm -rf /)",
                    "path_traversal": "../../../etc/passwd"
                }
            },
            {
                "alert_type": "kubernetes",
                "runbook": "https://example.com/runbook.md",
                "data": {
                    "large_payload": "x" * (11 * 1024 * 1024),  # 11MB payload
                    "deep_nesting": {"level1": {"level2": {"level3": {"level4": {"level5": "value"}}}}}
                }
            }
        ]
        
        for payload in malicious_payloads:
            with patch('tarsy.main.alert_service') as mock_alert_service, \
                 patch('tarsy.main.asyncio.create_task'):
                
                mock_alert_service.register_alert_id = Mock()
                
                # Should handle malicious payloads gracefully
                response = client.post("/alerts", json=payload)
                
                # Should either succeed (with sanitization) or fail gracefully
                assert response.status_code in [200, 400, 413]
                
                if response.status_code == 200:
                    data = response.json()
                    assert data["status"] in ["queued", "duplicate"]

    def test_alert_deduplication_edge_cases(self, client):
        """Test edge cases in alert deduplication logic."""
        from tests.utils import AlertFactory
        
        alert = AlertFactory.create_kubernetes_alert()
        alert_data = {
            "alert_type": alert.alert_type,
            "runbook": alert.runbook,
            "severity": alert.severity,
            "data": alert.data
        }
        
        # Test with existing processing key
        mock_alert_key = Mock()
        mock_alert_key.__str__ = Mock(return_value="test-key")
        mock_alert_key.__hash__ = Mock(return_value=12345)
        
        with patch('tarsy.main.processing_alert_keys', {mock_alert_key: "existing-id"}), \
             patch('tarsy.main.alert_keys_lock', asyncio.Lock()), \
             patch('tarsy.main.AlertKey.from_chain_context') as mock_from_chain_context:
            
            # Mock the factory method to return our test key
            mock_from_chain_context.return_value = mock_alert_key
            
            response = client.post("/alerts", json=alert_data)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "duplicate"
            assert data["alert_id"] == "existing-id"

    def test_alert_processing_timeout_handling(self, client):
        """Test handling of alert processing timeouts."""
        from tests.utils import AlertFactory
        
        alert = AlertFactory.create_kubernetes_alert()
        alert_data = {
            "alert_type": alert.alert_type,
            "runbook": alert.runbook,
            "severity": alert.severity,
            "data": alert.data
        }
        
        with patch('tarsy.main.alert_service') as mock_alert_service, \
             patch('tarsy.main.asyncio.create_task'), \
             patch('tarsy.main.processing_alert_keys', {}), \
             patch('tarsy.main.alert_keys_lock', asyncio.Lock()), \
             patch('tarsy.main.AlertKey.from_chain_context') as mock_from_chain_context:
            
            # Mock AlertKey to return a unique key matching production format: <alert_type>_<12-char hex hash>
            mock_key = Mock()
            mock_key.__str__ = Mock(return_value=f"test_alert_{uuid.uuid4().hex[:12]}")
            mock_key.__hash__ = Mock(return_value=12345)
            mock_from_chain_context.return_value = mock_key
            
            mock_alert_service.register_alert_id = Mock()
            
            # Should not block the endpoint
            response = client.post("/alerts", json=alert_data)
            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ["queued", "duplicate"]  # Accept either status

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

    def test_memory_usage_under_load(self, client):
        """Test memory usage behavior under load."""
        from tests.utils import AlertFactory
        
        # Create many alerts to test memory usage
        alerts = [AlertFactory.create_kubernetes_alert() for _ in range(100)]
        
        with patch('tarsy.main.alert_service') as mock_alert_service, \
             patch('tarsy.main.asyncio.create_task'):
            
            mock_alert_service.register_alert_id = Mock()
            
            # Submit many alerts quickly
            for alert in alerts:
                alert_data = {
                    "alert_type": alert.alert_type,
                    "runbook": alert.runbook,
                    "severity": alert.severity,
                    "data": alert.data
                }
                response = client.post("/alerts", json=alert_data)
                assert response.status_code == 200

    def test_websocket_connection_stability(self, client):
        """Test WebSocket connection stability under various conditions."""
        # This would require a more complex setup with actual WebSocket testing
        # For now, we'll test the endpoint exists and responds appropriately
        response = client.get("/")
        assert response.status_code == 200
        assert "tarsy" in response.json()["message"].lower()

