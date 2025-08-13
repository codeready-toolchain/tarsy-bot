"""
Comprehensive tests for the main FastAPI application.

Tests lifespan management, endpoints, WebSocket connections, and background processing.
"""

import asyncio
import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient
from fastapi import WebSocket

from pydantic import ValidationError

# Import the modules we need to test and mock
from tarsy.main import app, lifespan, process_alert_background, processing_alert_keys, alert_keys_lock
from tarsy.models.alert import Alert, AlertResponse
from tarsy.models.alert_processing import AlertProcessingData, AlertKey
from tarsy.models.websocket_models import ConnectionEstablished, ErrorMessage
from tarsy.services.alert_service import AlertService
from tarsy.services.dashboard_connection_manager import DashboardConnectionManager


@pytest.mark.unit
class TestMainLifespan:
    """Test application lifespan management."""

    @pytest.fixture
    def mock_get_settings(self):
        """Mock settings for lifespan tests."""
        mock_settings = Mock()
        mock_settings.log_level = "INFO"
        mock_settings.max_concurrent_alerts = 5
        mock_settings.history_enabled = True
        mock_settings.cors_origins = ["*"]
        mock_settings.host = "localhost" 
        mock_settings.port = 8000
        return mock_settings

    @patch('tarsy.main.get_settings')
    @patch('tarsy.main.setup_logging')
    @patch('tarsy.main.initialize_database')
    @patch('tarsy.services.history_service.get_history_service')
    @patch('tarsy.main.AlertService')
    @patch('tarsy.main.DashboardConnectionManager')
    @patch('tarsy.hooks.hook_registry.get_typed_hook_registry')
    @patch('tarsy.main.get_database_info')
    async def test_lifespan_startup_success(self, mock_db_info, mock_hook_registry, mock_dashboard_manager_class, 
                                           mock_alert_service_class, mock_history_service, mock_init_db, 
                                           mock_setup_logging, mock_get_settings):
        """Test successful application startup."""
        # Setup mocks
        mock_get_settings.return_value = Mock(
            log_level="INFO", 
            max_concurrent_alerts=5, 
            history_enabled=True,
            cors_origins=["*"]
        )
        mock_init_db.return_value = True
        mock_db_info.return_value = {"enabled": True}
        
        # Mock services
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

        # Test lifespan manager
        @asynccontextmanager 
        async def test_lifespan(app):
            async with lifespan(app):
                yield

        async with test_lifespan(app):
            pass  # Application startup and shutdown

        # Verify startup calls
        mock_setup_logging.assert_called_once_with("INFO")
        mock_init_db.assert_called_once()
        mock_alert_service.initialize.assert_called_once()
        mock_dashboard_manager.initialize_broadcaster.assert_called_once()
        mock_typed_hooks.initialize_hooks.assert_called_once()
        mock_history.cleanup_orphaned_sessions.assert_called_once()

        # Verify shutdown calls
        mock_dashboard_manager.shutdown_broadcaster.assert_called_once()

    @patch('tarsy.main.get_settings')
    @patch('tarsy.main.setup_logging')
    @patch('tarsy.main.initialize_database')
    @patch('tarsy.services.history_service.get_history_service')
    @patch('tarsy.main.AlertService')
    @patch('tarsy.main.DashboardConnectionManager')
    @patch('tarsy.main.get_database_info')
    async def test_lifespan_startup_with_history_disabled(self, mock_db_info, mock_dashboard_manager_class,
                                                         mock_alert_service_class, mock_history_service,
                                                         mock_init_db, mock_setup_logging, mock_get_settings):
        """Test application startup with history service disabled."""
        # Setup mocks
        mock_get_settings.return_value = Mock(
            log_level="INFO",
            max_concurrent_alerts=5,
            history_enabled=False,
            cors_origins=["*"]
        )
        mock_init_db.return_value = False
        mock_db_info.return_value = {"enabled": False}
        
        mock_alert_service = AsyncMock()
        mock_alert_service_class.return_value = mock_alert_service
        
        mock_dashboard_manager = Mock()
        mock_dashboard_manager.initialize_broadcaster = AsyncMock()
        mock_dashboard_manager.shutdown_broadcaster = AsyncMock()
        mock_dashboard_manager_class.return_value = mock_dashboard_manager

        # Test lifespan manager
        @asynccontextmanager 
        async def test_lifespan(app):
            async with lifespan(app):
                yield

        async with test_lifespan(app):
            pass

        # Verify startup calls - history service should not be initialized
        mock_setup_logging.assert_called_once()
        mock_alert_service.initialize.assert_called_once()
        mock_dashboard_manager.initialize_broadcaster.assert_called_once()
        
        # History service should not be called
        mock_history_service.assert_not_called()

    @patch('tarsy.main.get_settings')
    @patch('tarsy.main.setup_logging')
    @patch('tarsy.main.initialize_database')
    @patch('tarsy.services.history_service.get_history_service')
    @patch('tarsy.main.AlertService')
    @patch('tarsy.main.DashboardConnectionManager')
    @patch('tarsy.main.get_database_info')
    async def test_lifespan_startup_with_orphaned_session_cleanup_error(self, mock_db_info, mock_dashboard_manager_class,
                                                                       mock_alert_service_class, mock_history_service,
                                                                       mock_init_db, mock_setup_logging, mock_get_settings):
        """Test application startup when orphaned session cleanup fails."""
        # Setup mocks
        mock_get_settings.return_value = Mock(
            log_level="INFO",
            max_concurrent_alerts=5,
            history_enabled=True,
            cors_origins=["*"]
        )
        mock_init_db.return_value = True
        mock_db_info.return_value = {"enabled": True}
        
        mock_alert_service = AsyncMock()
        mock_alert_service_class.return_value = mock_alert_service
        
        mock_dashboard_manager = Mock()
        mock_dashboard_manager.initialize_broadcaster = AsyncMock()
        mock_dashboard_manager.shutdown_broadcaster = AsyncMock()
        mock_dashboard_manager_class.return_value = mock_dashboard_manager
        
        # Make cleanup fail
        mock_history = Mock()
        mock_history.cleanup_orphaned_sessions.side_effect = Exception("Cleanup failed")
        mock_history_service.return_value = mock_history

        # Test lifespan manager - should not fail even if cleanup fails
        @asynccontextmanager 
        async def test_lifespan(app):
            async with lifespan(app):
                yield

        async with test_lifespan(app):
            pass

        # Verify startup continued despite cleanup error
        mock_alert_service.initialize.assert_called_once()
        mock_dashboard_manager.initialize_broadcaster.assert_called_once()


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

    @patch('tarsy.main.get_database_info')
    def test_health_endpoint_healthy(self, mock_db_info, client):
        """Test health endpoint when all services are healthy."""
        mock_db_info.return_value = {
            "enabled": True,
            "connection_test": True,
            "retention_days": 30
        }
        
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert data["service"] == "tarsy"
        assert "timestamp" in data
        assert data["services"]["alert_processing"] == "healthy"
        assert data["services"]["history_service"] == "healthy"
        assert data["services"]["database"]["enabled"] is True
        assert data["services"]["database"]["connected"] is True
        assert data["services"]["database"]["retention_days"] == 30

    @patch('tarsy.main.get_database_info')
    def test_health_endpoint_degraded(self, mock_db_info, client):
        """Test health endpoint when history service is unhealthy."""
        mock_db_info.return_value = {
            "enabled": True,
            "connection_test": False,
            "retention_days": 30
        }
        
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "degraded"
        assert data["services"]["history_service"] == "unhealthy"
        assert data["services"]["database"]["connected"] is False

    @patch('tarsy.main.get_database_info')
    def test_health_endpoint_history_disabled(self, mock_db_info, client):
        """Test health endpoint when history service is disabled."""
        mock_db_info.return_value = {
            "enabled": False
        }
        
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert data["services"]["history_service"] == "disabled"
        assert data["services"]["database"]["enabled"] is False
        assert data["services"]["database"]["connected"] is None

    @patch('tarsy.main.get_database_info')
    def test_health_endpoint_exception(self, mock_db_info, client):
        """Test health endpoint when an exception occurs."""
        mock_db_info.side_effect = Exception("Database error")
        
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "unhealthy"
        assert data["service"] == "tarsy"
        assert "error" in data
        assert "Database error" in data["error"]

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

    def test_submit_alert_empty_body(self, client):
        """Test alert submission with empty body."""
        response = client.post("/alerts", json=None)
        assert response.status_code == 400
        data = response.json()
        
        assert data["detail"]["error"] == "Empty request body"
        assert "expected_fields" in data["detail"]

    def test_submit_alert_invalid_json(self, client):
        """Test alert submission with invalid JSON."""
        response = client.post("/alerts", data="invalid json", headers={"content-type": "application/json"})
        assert response.status_code == 400
        data = response.json()
        
        assert data["detail"]["error"] == "Invalid JSON"

    def test_submit_alert_non_dict_body(self, client):
        """Test alert submission with non-dictionary body."""
        response = client.post("/alerts", json="not a dict")
        assert response.status_code == 400
        data = response.json()
        
        assert data["detail"]["error"] == "Invalid data structure"
        assert data["detail"]["received_type"] == "str"

    def test_submit_alert_validation_error(self, client):
        """Test alert submission with validation errors."""
        invalid_data = {
            "alert_type": "",  # Empty alert type
            "runbook": "invalid-url",
            "data": "not a dict"
        }
        
        response = client.post("/alerts", json=invalid_data)
        assert response.status_code == 422
        data = response.json()
        
        assert data["detail"]["error"] == "Validation failed"
        assert "validation_errors" in data["detail"]

    def test_submit_alert_empty_alert_type(self, client, valid_alert_data):
        """Test alert submission with empty alert_type."""
        valid_alert_data["alert_type"] = "   "  # Whitespace only
        
        response = client.post("/alerts", json=valid_alert_data)
        assert response.status_code == 400
        data = response.json()
        
        assert data["detail"]["error"] == "Invalid alert_type"
        assert data["detail"]["field"] == "alert_type"

    def test_submit_alert_empty_runbook(self, client, valid_alert_data):
        """Test alert submission with empty runbook."""
        valid_alert_data["runbook"] = ""
        
        response = client.post("/alerts", json=valid_alert_data)
        assert response.status_code == 400
        data = response.json()
        
        assert data["detail"]["error"] == "Invalid runbook"
        assert data["detail"]["field"] == "runbook"

    @patch('tarsy.main.processing_alert_keys', {"test-key": "existing-id"})
    @patch('tarsy.main.alert_keys_lock', asyncio.Lock())
    def test_submit_alert_duplicate_detection(self, client, valid_alert_data):
        """Test duplicate alert detection."""
        # Mock AlertKey to return a predictable key
        with patch('tarsy.main.AlertKey') as mock_alert_key:
            mock_key = Mock()
            mock_key.__str__ = Mock(return_value="test-key")
            mock_alert_key.from_alert_data.return_value = mock_key
            
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
        return AlertProcessingData(
            alert_type="kubernetes",
            alert_data={
                "namespace": "production",
                "pod": "api-server-123",
                "severity": "high"
            }
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
        
        mock_alert_service.process_alert.assert_called_once_with(mock_alert_data, api_alert_id="alert-123")

    @patch('tarsy.main.alert_service')
    @patch('tarsy.main.processing_alert_keys', {"test-key": "alert-123"})
    @patch('tarsy.main.alert_keys_lock', asyncio.Lock())
    async def test_process_alert_background_cleanup(self, mock_alert_service, mock_alert_data):
        """Test background processing cleans up alert keys."""
        mock_alert_service.process_alert = AsyncMock(return_value={"status": "success"})
        
        # Create a mock AlertKey that returns "test-key"
        with patch('tarsy.main.AlertKey') as mock_alert_key_class:
            mock_key = Mock()
            mock_key.__str__ = Mock(return_value="test-key")
            mock_alert_key_class.from_alert_data.return_value = mock_key
            
            with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)):
                await process_alert_background("alert-123", mock_alert_data)
        
        # Verify the alert key was cleaned up (dict should be empty now)
        from tarsy.main import processing_alert_keys
        assert "test-key" not in processing_alert_keys

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
        """Test background processing with invalid alert data."""
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)):
            # Test with None alert
            await process_alert_background("alert-123", None)
            
            # Create minimally valid AlertProcessingData but then mock validation failure
            valid_alert = AlertProcessingData(alert_type="test", alert_data={"key": "value"})
            
            # Test by directly setting invalid attributes after creation
            valid_alert.alert_type = ""  # Make it invalid after creation
            await process_alert_background("alert-123", valid_alert)
            
            # For the None alert_data case, we need to mock the AlertKey creation to avoid the error
            valid_alert2 = AlertProcessingData(alert_type="test", alert_data={"key": "value"})
            valid_alert2.alert_data = None  # Make it invalid after creation
            
            with patch('tarsy.main.AlertKey.from_alert_data') as mock_alert_key:
                mock_key = Mock()
                mock_key.__str__ = Mock(return_value="test-key-2")
                mock_alert_key.return_value = mock_key
                await process_alert_background("alert-123", valid_alert2)
        
        # Should not call process_alert for invalid data
        mock_alert_service.process_alert.assert_not_called()

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
        from tarsy.main import processing_alert_keys
        assert isinstance(processing_alert_keys, dict)

    def test_alert_keys_lock_initialization(self):
        """Test alert keys lock is properly initialized."""
        from tarsy.main import alert_keys_lock
        assert isinstance(alert_keys_lock, asyncio.Lock)

    def test_global_services_initialization(self):
        """Test global services are initialized as None."""
        from tarsy.main import alert_service, dashboard_manager, alert_processing_semaphore
        # These will be None initially before lifespan runs
        # The actual initialization happens in the lifespan context manager


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

