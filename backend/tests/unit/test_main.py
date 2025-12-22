"""
Comprehensive tests for the main FastAPI application.

Tests lifespan management, endpoints, WebSocket connections, and background processing.
"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock, call, patch

import pytest
from fastapi.testclient import TestClient

# Import the modules we need to test and mock
from tarsy.main import (
    app,
    lifespan,
    process_alert_background,
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
                 'tarsy.hooks.hook_registry.get_hook_registry'
             ) as mock_hook_registry, \
             patch('tarsy.main.get_database_info') as mock_db_info, \
             patch(
                 'tarsy.repositories.base_repository.DatabaseManager'
             ) as mock_db_manager_class, \
             patch(
                 'tarsy.services.history_cleanup_service.HistoryCleanupService'
             ) as mock_cleanup_service_class:
            
            # Setup service mocks
            mock_alert_service = AsyncMock()
            mock_alert_service_class.return_value = mock_alert_service
            
            mock_history = Mock()
            mock_history.cleanup_orphaned_sessions.return_value = 2
            mock_history_service.return_value = mock_history
            
            mock_typed_hooks = AsyncMock()
            mock_hook_registry.return_value = mock_typed_hooks
            
            # Setup DatabaseManager mock
            mock_db_manager = Mock()
            mock_db_manager.get_session = Mock()
            mock_db_manager_class.return_value = mock_db_manager
            
            # Setup HistoryCleanupService mock
            mock_cleanup_service = AsyncMock()
            mock_cleanup_service.start = AsyncMock()
            mock_cleanup_service.stop = AsyncMock()
            mock_cleanup_service_class.return_value = mock_cleanup_service
            
            yield {
                'setup_logging': mock_setup_logging,
                'init_db': mock_init_db,
                'history_service': mock_history_service,
                'alert_service_class': mock_alert_service_class,
                'hook_registry': mock_hook_registry,
                'db_info': mock_db_info,
                'alert_service': mock_alert_service,
                'history': mock_history,
                'typed_hooks': mock_typed_hooks,
                'db_manager_class': mock_db_manager_class,
                'db_manager': mock_db_manager,
                'cleanup_service_class': mock_cleanup_service_class,
                'cleanup_service': mock_cleanup_service
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
            cors_origins=["*"],
            database_url="sqlite:///test.db",
            history_retention_days=90,
            history_cleanup_interval_hours=12
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
        deps['typed_hooks'].initialize_hooks.assert_called_once()
        deps['history'].cleanup_orphaned_sessions.assert_called_once()

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
            cors_origins=["*"],
            database_url="sqlite:///test.db",
            history_retention_days=90,
            history_cleanup_interval_hours=12
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
            database_url="sqlite:///test.db",
            history_retention_days=90,
            history_cleanup_interval_hours=12,
            max_concurrent_alerts=5,
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
            cors_origins=["*"],
            database_url="sqlite:///test.db",
            history_retention_days=90,
            history_cleanup_interval_hours=12
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
    
    @patch('tarsy.main.get_settings')
    @patch('sys.exit')
    async def test_lifespan_exits_when_history_cleanup_service_init_fails(
        self, mock_sys_exit, mock_get_settings, mock_lifespan_dependencies
    ):
        """Test that application exits when HistoryCleanupService initialization fails."""
        deps = mock_lifespan_dependencies
        
        # Setup mocks
        mock_get_settings.return_value = Mock(
            log_level="INFO",
            max_concurrent_alerts=5,
            cors_origins=["*"],
            database_url="sqlite:///test.db",
            history_retention_days=90,
            history_cleanup_interval_hours=12
        )
        deps['init_db'].return_value = True
        deps['db_info'].return_value = {"enabled": True}
        
        # Make DatabaseManager initialization fail
        deps['db_manager'].initialize.side_effect = Exception("Database connection failed")
        
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

    @pytest.mark.parametrize("db_status,expected_status,expected_http_code,expected_services", [
        (
            {"enabled": True, "connection_test": True, "retention_days": 30},
            "healthy",
            200,
            {
                "alert_processing": "healthy",
                "history_service": "healthy",
                "database": {"enabled": True, "connected": True, "retention_days": 30}
            }
        ),
        (
            {"enabled": True, "connection_test": False, "retention_days": 30},
            "degraded",
            503,
            {
                "alert_processing": "healthy",
                "history_service": "unhealthy",
                "database": {"enabled": True, "connected": False, "retention_days": 30}
            }
        ),
        (
            {"enabled": False},
            "healthy",
            200,
            {
                "alert_processing": "healthy",
                "history_service": "disabled",
                "database": {"enabled": False, "connected": None}
            }
        ),
        (
            Exception("Database error"),
            "unhealthy",
            503,
            {
                "alert_processing": "healthy",
                "history_service": "unhealthy",
                "database": {"enabled": None, "connected": None}
            }
        )
    ])
    @patch('tarsy.main.get_database_info')
    def test_health_endpoint_status(
        self, mock_db_info, client, db_status, expected_status, expected_http_code, expected_services
    ):
        """Test health endpoint with different database status scenarios."""
        if isinstance(db_status, Exception):
            mock_db_info.side_effect = db_status
        else:
            mock_db_info.return_value = db_status
        
        # Mock shutdown flag as False to test normal health check behavior
        with patch('tarsy.main.shutdown_in_progress', False), \
             patch('tarsy.services.events.manager.get_event_system') as mock_get_event_system:
            mock_event_system = Mock()
            mock_listener = Mock()
            mock_listener.running = True
            mock_event_system.get_listener.return_value = mock_listener
            mock_get_event_system.return_value = mock_event_system
            
            response = client.get("/health")
            assert response.status_code == expected_http_code
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

    @patch('tarsy.main.shutdown_in_progress', True)
    def test_health_endpoint_during_shutdown(self, client):
        """Test health endpoint returns 503 when shutdown is in progress."""
        response = client.get("/health")
        
        # Assert HTTP 503 status code
        assert response.status_code == 503
        
        # Parse response JSON
        data = response.json()
        
        # Assert status is "shutting_down"
        assert data["status"] == "shutting_down"
        
        # Assert message contains "shutting down" (case-insensitive)
        assert "shutting down" in data["message"].lower()

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

        # Mock shutdown flag and event system as healthy for this test
        with patch('tarsy.main.shutdown_in_progress', False), \
             patch('tarsy.services.events.manager.get_event_system') as mock_get_event_system:
            mock_event_system = Mock()
            mock_listener = Mock()
            mock_listener.running = True
            mock_event_system.get_listener.return_value = mock_listener
            mock_get_event_system.return_value = mock_event_system
            
            response = client.get("/health")
            assert response.status_code == 200  # Warnings don't cause 503 - service is still healthy
            data = response.json()

        # Status should remain healthy despite warnings (warnings are non-critical)
        assert data["status"] == "healthy"

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

        # Mock shutdown flag and event system as healthy for this test
        with patch('tarsy.main.shutdown_in_progress', False), \
             patch('tarsy.services.events.manager.get_event_system') as mock_get_event_system:
            mock_event_system = Mock()
            mock_listener = Mock()
            mock_listener.running = True
            mock_event_system.get_listener.return_value = mock_listener
            mock_get_event_system.return_value = mock_event_system
            
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

    @patch('tarsy.main.get_database_info')
    def test_health_endpoint_includes_migration_version(self, mock_db_info, client):
        """Test health endpoint includes database migration version."""
        # Mock database with migration version
        mock_db_info.return_value = {
            "enabled": True,
            "connection_test": True,
            "retention_days": 90,
            "migration_version": "3717971cb125"
        }

        # Mock shutdown flag and event system as healthy
        with patch('tarsy.main.shutdown_in_progress', False), \
             patch('tarsy.services.events.manager.get_event_system') as mock_get_event_system:
            mock_event_system = Mock()
            mock_listener = Mock()
            mock_listener.running = True
            mock_event_system.get_listener.return_value = mock_listener
            mock_get_event_system.return_value = mock_event_system
            
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()

        # Verify migration_version is included in database section
        assert "database" in data["services"]
        assert "migration_version" in data["services"]["database"]
        assert data["services"]["database"]["migration_version"] == "3717971cb125"

    @patch('tarsy.main.get_database_info')
    def test_health_endpoint_migration_version_special_values(self, mock_db_info, client):
        """Test health endpoint handles special migration version values."""
        # Test with "not_initialized" value
        mock_db_info.return_value = {
            "enabled": True,
            "connection_test": True,
            "retention_days": 90,
            "migration_version": "not_initialized"
        }

        # Mock shutdown flag and event system as healthy
        with patch('tarsy.main.shutdown_in_progress', False), \
             patch('tarsy.services.events.manager.get_event_system') as mock_get_event_system:
            mock_event_system = Mock()
            mock_listener = Mock()
            mock_listener.running = True
            mock_event_system.get_listener.return_value = mock_listener
            mock_get_event_system.return_value = mock_event_system
            
            response = client.get("/health")
            data = response.json()

        assert data["services"]["database"]["migration_version"] == "not_initialized"

    @patch('tarsy.main.get_database_info')
    def test_health_endpoint_includes_version(self, mock_db_info, client):
        """Test health endpoint includes application version."""
        mock_db_info.return_value = {
            "enabled": True,
            "connection_test": True,
            "retention_days": 90,
        }

        # Mock shutdown flag and event system as healthy
        with patch('tarsy.main.shutdown_in_progress', False), \
             patch('tarsy.services.events.manager.get_event_system') as mock_get_event_system:
            mock_event_system = Mock()
            mock_listener = Mock()
            mock_listener.running = True
            mock_event_system.get_listener.return_value = mock_listener
            mock_get_event_system.return_value = mock_event_system
            
            response = client.get("/health")
            assert response.status_code == 200
            data = response.json()

        # Verify version field is present in top-level response
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0  # Should have some value (dev, commit SHA, etc.)


@pytest.mark.unit
class TestBackgroundProcessing:
    """Test background alert processing function."""

    @pytest.fixture
    def mock_alert_data(self):
        """Mock alert processing data."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="kubernetes",
            severity="high",
            timestamp=now_us(),
            environment="production",
            alert_data={
                "namespace": "production",
                "pod": "api-server-123",
                "severity": "high"
            }
        )
        return ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="test-stage"
        )

    @patch('tarsy.main.alert_service')
    async def test_process_alert_background_success(
        self, mock_alert_service, mock_alert_data
    ):
        """Test successful background alert processing."""
        mock_alert_service.process_alert = AsyncMock(return_value={"status": "success"})
        
        # Mock the semaphore and locks to avoid issues
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)), \
             patch('tarsy.main.active_tasks_lock', asyncio.Lock()), \
             patch('tarsy.main.active_tasks', {}):
            await process_alert_background("test-session-123", mock_alert_data)
        
        mock_alert_service.process_alert.assert_called_once_with(mock_alert_data)


    @patch('tarsy.main.alert_service')
    async def test_process_alert_background_timeout(
        self, mock_alert_service, mock_alert_data
    ):
        """Test background processing with timeout."""
        # Make process_alert hang
        mock_alert_service.process_alert = AsyncMock(side_effect=asyncio.sleep(1000))
        mock_session_manager = Mock()
        mock_session_manager.update_session_error = Mock()
        mock_alert_service.session_manager = mock_session_manager
        
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)), \
             patch('tarsy.main.asyncio.wait_for', side_effect=asyncio.TimeoutError()), \
             patch('tarsy.main.active_tasks_lock', asyncio.Lock()), \
             patch('tarsy.main.active_tasks', {}), \
             patch('tarsy.services.events.event_helpers.publish_session_failed', new_callable=AsyncMock):
            # Should not raise exception, should handle timeout gracefully
            await process_alert_background("test-session-123", mock_alert_data)
        
        # Verify session was marked as failed
        mock_session_manager.update_session_error.assert_called_once()
        call_args = mock_session_manager.update_session_error.call_args
        assert call_args[0][0] == mock_alert_data.session_id
        assert "timeout" in call_args[0][1].lower()

    @patch('tarsy.main.alert_service')
    async def test_process_alert_background_invalid_alert(self, mock_alert_service):
        """Test background processing handles invalid alert data gracefully."""
        # Mock process_alert to track if it's called
        mock_alert_service.process_alert = AsyncMock()
        
        # Test with valid ChainContext but process_alert fails
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"key": "value"}
        )
        valid_alert = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session",
            current_stage_name="test-stage"
        )
        
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)), \
             patch('tarsy.main.active_tasks_lock', asyncio.Lock()), \
             patch('tarsy.main.active_tasks', {}), \
             patch('tarsy.services.events.event_helpers.publish_session_failed', new_callable=AsyncMock):
            # Test with None alert - should fail early during logging
            await process_alert_background("test-session-123", None)
            
            # Make process_alert fail to simulate processing errors
            mock_alert_service.process_alert.side_effect = ValueError(
                "Processing failed"
            )
            await process_alert_background("test-session-124", valid_alert)
        
        # The function should handle errors gracefully and not raise exceptions
        # Even with invalid data, it attempts processing and handles the failure
        assert mock_alert_service.process_alert.call_count >= 1

    @patch('tarsy.main.alert_service')
    async def test_process_alert_background_processing_exception(
        self, mock_alert_service, mock_alert_data
    ):
        """Test background processing handles processing exceptions."""
        mock_alert_service.process_alert = AsyncMock(
            side_effect=Exception("Processing failed")
        )
        mock_session_manager = Mock()
        mock_session_manager.update_session_error = Mock()
        mock_alert_service.session_manager = mock_session_manager
        
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)), \
             patch('tarsy.main.active_tasks_lock', asyncio.Lock()), \
             patch('tarsy.main.active_tasks', {}), \
             patch('tarsy.services.events.event_helpers.publish_session_failed', new_callable=AsyncMock):
            # Should not raise exception, should handle gracefully
            await process_alert_background("test-session-123", mock_alert_data)
        
        mock_alert_service.process_alert.assert_called_once()
        
        # Verify session was marked as failed
        mock_session_manager.update_session_error.assert_called_once()
        call_args = mock_session_manager.update_session_error.call_args
        assert call_args[0][0] == mock_alert_data.session_id
        assert "processing error" in call_args[0][1].lower()

    @patch('tarsy.main.alert_service')
    async def test_process_alert_background_user_cancellation(
        self, mock_alert_service, mock_alert_data
    ):
        """Test user-requested cancellation does not mark session as FAILED."""
        from tarsy.models.constants import AlertSessionStatus
        from tarsy.models.db_models import AlertSession
        from tarsy.utils.timestamp import now_us
        
        # Make process_alert raise CancelledError (simulating user cancellation)
        mock_alert_service.process_alert = AsyncMock(
            side_effect=asyncio.CancelledError()
        )
        mock_session_manager = Mock()
        mock_session_manager.update_session_error = Mock()
        mock_alert_service.session_manager = mock_session_manager
        
        # Mock session in CANCELING status (user-requested)
        mock_session = AlertSession(
            session_id="test-session-123",
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.CANCELING.value,
            started_at_us=now_us(),
            chain_id="chain-1"
        )
        
        mock_history_service = Mock()
        mock_history_service.get_session.return_value = mock_session
        mock_history_service.cancel_all_paused_stages = AsyncMock(return_value=0)
        mock_history_service.update_session_status = AsyncMock()
        
        # Create lock in async context (Python 3.13+ requirement)
        test_lock = asyncio.Lock()
        
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)), \
             patch('tarsy.services.history_service.get_history_service', return_value=mock_history_service), \
             patch('tarsy.main.active_tasks_lock', test_lock), \
             patch('tarsy.main.active_tasks', {}), \
             patch('tarsy.services.events.event_helpers.publish_session_cancelled', new_callable=AsyncMock):
            
            # Should not raise exception and should exit gracefully
            await process_alert_background("test-session-123", mock_alert_data)
        
        # Verify session was NOT marked as failed (user cancellation handled gracefully)
        mock_session_manager.update_session_error.assert_not_called()

    @patch('tarsy.main.alert_service')
    async def test_process_alert_background_non_user_cancellation(
        self, mock_alert_service, mock_alert_data
    ):
        """Test non-user cancellation (e.g., timeout) marks session as FAILED."""
        from tarsy.models.constants import AlertSessionStatus
        from tarsy.models.db_models import AlertSession
        from tarsy.utils.timestamp import now_us
        
        # Make process_alert raise CancelledError (simulating non-user cancellation)
        mock_alert_service.process_alert = AsyncMock(
            side_effect=asyncio.CancelledError()
        )
        mock_session_manager = Mock()
        mock_session_manager.update_session_error = Mock()
        mock_alert_service.session_manager = mock_session_manager
        
        # Mock session in IN_PROGRESS status (not user-requested cancellation)
        mock_session = AlertSession(
            session_id="test-session-123",
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.IN_PROGRESS.value,
            started_at_us=now_us(),
            chain_id="chain-1"
        )
        
        mock_history_service = Mock()
        mock_history_service.get_session.return_value = mock_session
        
        # Create lock in async context (Python 3.13+ requirement)
        test_lock = asyncio.Lock()
        
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)), \
             patch('tarsy.services.history_service.get_history_service', return_value=mock_history_service), \
             patch('tarsy.main.active_tasks_lock', test_lock), \
             patch('tarsy.main.active_tasks', {}), \
             patch('tarsy.services.events.event_helpers.publish_session_failed', new_callable=AsyncMock):
            
            # Should not raise exception and should handle gracefully
            await process_alert_background("test-session-123", mock_alert_data)
        
        # Verify session was marked as failed (non-user cancellation)
        mock_session_manager.update_session_error.assert_called_once()
        call_args = mock_session_manager.update_session_error.call_args
        assert call_args[0][0] == mock_alert_data.session_id
        assert "cancelled" in call_args[0][1].lower()

    @patch('tarsy.main.alert_service')
    async def test_process_alert_background_user_cancellation_already_cancelled_status(
        self, mock_alert_service, mock_alert_data
    ):
        """Test user-requested cancellation when status is already CANCELLED.
        
        This tests the scenario where the inner handler has already updated
        the status to CANCELLED before the outer handler checks it.
        """
        from tarsy.models.constants import AlertSessionStatus
        from tarsy.models.db_models import AlertSession
        from tarsy.utils.timestamp import now_us
        
        # Make process_alert raise CancelledError (simulating user cancellation)
        mock_alert_service.process_alert = AsyncMock(
            side_effect=asyncio.CancelledError()
        )
        mock_session_manager = Mock()
        mock_session_manager.update_session_error = Mock()
        mock_alert_service.session_manager = mock_session_manager
        
        # Mock session in CANCELLED status (already processed by inner handler)
        mock_session = AlertSession(
            session_id="test-session-123",
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            status=AlertSessionStatus.CANCELLED.value,  # Already CANCELLED
            started_at_us=now_us(),
            chain_id="chain-1"
        )
        
        mock_history_service = Mock()
        mock_history_service.get_session.return_value = mock_session
        
        # Create lock in async context (Python 3.13+ requirement)
        test_lock = asyncio.Lock()
        
        with patch('tarsy.main.alert_processing_semaphore', asyncio.Semaphore(1)), \
             patch('tarsy.services.history_service.get_history_service', return_value=mock_history_service), \
             patch('tarsy.main.active_tasks_lock', test_lock), \
             patch('tarsy.main.active_tasks', {}):
            
            # Should not raise exception and should exit gracefully
            await process_alert_background("test-session-123", mock_alert_data)
        
        # Verify session was NOT marked as failed (user cancellation handled gracefully)
        mock_session_manager.update_session_error.assert_not_called()


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
        with patch('tarsy.main.shutdown_in_progress', False), \
             patch('tarsy.main.get_database_info') as mock_db_info:
            mock_db_info.side_effect = Exception("Database connection failed")
            
            # Health endpoint should handle database failures gracefully and return 503
            response = client.get("/health")
            assert response.status_code == 503  # Unhealthy status returns 503
            data = response.json()
            assert data["status"] == "unhealthy"
            assert "error" in data

    @patch('tarsy.main.get_database_info')
    def test_health_endpoint_event_system_not_initialized(self, mock_db_info, client):
        """Test health endpoint marks status as degraded when event system fails to initialize."""
        # Mock database as healthy
        mock_db_info.return_value = {
            "enabled": True,
            "connection_test": True,
            "retention_days": 30,
        }
        
        # Mock shutdown flag and get_event_system to raise RuntimeError (event system not initialized)
        with patch('tarsy.main.shutdown_in_progress', False), \
             patch('tarsy.services.events.manager.get_event_system') as mock_get_event_system:
            mock_get_event_system.side_effect = RuntimeError("Event system not initialized")
            
            response = client.get("/health")
            
            # Should return 503 (degraded status)
            assert response.status_code == 503
            data = response.json()
            
            # Overall status should be degraded (critical for multi-replica support)
            assert data["status"] == "degraded"
            
            # Event system status should be "not_initialized"
            assert data["services"]["event_system"]["status"] == "not_initialized"

    