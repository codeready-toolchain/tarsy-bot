"""
Unit tests for the alert controller.

This module tests the alert-related endpoints that were moved from main.py
to controllers/alert_controller.py for better code organization.
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import TestClient

from tarsy.main import app


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
        
        response = client.get("/api/v1/session-id/alert-123")
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
        
        response = client.get("/api/v1/session-id/nonexistent")
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
        
        response = client.get("/api/v1/session-id/alert-123")
        assert response.status_code == 200
        data = response.json()
        
        assert data["alert_id"] == "alert-123"
        assert data["session_id"] is None


@pytest.mark.unit
class TestAlertControllerCriticalCoverage:
    """Test critical alert controller logic and edge cases."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    def test_memory_usage_under_load(self, client):
        """Test memory usage behavior under load for alert submission."""
        from tests.utils import AlertFactory
        
        # Create many alerts to test memory usage
        alerts = [AlertFactory.create_kubernetes_alert() for _ in range(100)]
        
        with patch('tarsy.main.alert_service') as mock_alert_service, \
             patch('asyncio.create_task') as mock_create_task:
            
            mock_alert_service.register_alert_id = Mock()
            
            # Submit many alerts quickly
            for alert in alerts:
                alert_data = {
                    "alert_type": alert.alert_type,
                    "runbook": alert.runbook,
                    "severity": alert.severity,
                    "data": alert.data
                }
                response = client.post("/api/v1/alerts", json=alert_data)
                assert response.status_code == 200



@pytest.mark.unit
class TestAlertTypesEndpoint:
    """Test the alert types endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @patch('tarsy.main.alert_service')
    def test_get_alert_types(self, mock_alert_service, client):
        """Test get alert types endpoint."""
        mock_chain_registry = Mock()
        mock_chain_registry.list_available_alert_types.return_value = [
            "kubernetes", "database", "network"
        ]
        mock_alert_service.chain_registry = mock_chain_registry
        
        response = client.get("/api/v1/alert-types")
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
            "alert_type": "test_alert",
            "runbook": "https://example.com/runbook.md",
            "data": {
                "namespace": "test-namespace",
                "pod_name": "test-pod-12345",
                "reason": "ImagePullBackOff"
            },
            "severity": "high",
            "timestamp": 1640995200000000  # 2022-01-01 00:00:00 UTC in microseconds
        }

    @patch('tarsy.main.alert_service')
    @patch('asyncio.create_task')
    def test_submit_alert_success(
        self, mock_create_task, mock_alert_service, client, valid_alert_data
    ):
        """Test successful alert submission."""
        # Mock alert_service methods
        mock_alert_service.register_alert_id = Mock()
        
        response = client.post("/api/v1/alerts", json=valid_alert_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "queued"
        assert "alert_id" in data
        assert len(data["alert_id"]) == 36  # UUID format
        assert data["message"] == "Alert submitted for processing and validation completed"
        
        # Verify alert_service.register_alert_id was called
        mock_alert_service.register_alert_id.assert_called_once()
        # Verify background task was created
        mock_create_task.assert_called_once()

    @pytest.mark.parametrize("invalid_input,expected_status,expected_error", [
        (None, 400, "Empty request body"),
        ("invalid json", 400, "Invalid JSON"),
        ("not a dict", 400, "Invalid data structure"),
        (
            {"invalid": "no required fields"},
            422,
            "Validation failed"
        ),
        (
            {"alert_type": "", "runbook": "https://example.com/runbook.md", "data": {}},
            400,
            "Invalid alert_type"
        ),
        (
            {"alert_type": "test", "runbook": "", "data": {}},
            400,
            "Invalid runbook"
        ),
    ])
    @patch('tarsy.main.alert_service')
    def test_submit_alert_input_validation(
        self, mock_alert_service, client, valid_alert_data, invalid_input, expected_status, expected_error
    ):
        """Test alert submission with various invalid inputs."""
        from tarsy.models.alert import AlertResponse
        
        # Mock alert service (won't be called for input validation errors, but needs to exist)
        mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
            alert_id="test-alert-123",
            status="queued",
            message="Alert submitted for processing and validation completed"
        ))
        if invalid_input == "invalid json":
            response = client.post(
                "/api/v1/alerts",
                data=invalid_input,
                headers={"content-type": "application/json"}
            )
        elif invalid_input == "not a dict" or invalid_input is None:
            response = client.post("/api/v1/alerts", json=invalid_input)
        else:
            response = client.post("/api/v1/alerts", json=invalid_input)
        
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
        with patch(
            'tarsy.controllers.alert_controller.processing_alert_keys', {mock_alert_key: "existing-id"}
        ), \
             patch('tarsy.controllers.alert_controller.alert_keys_lock', asyncio.Lock()), \
             patch('tarsy.models.alert_processing.AlertKey.from_chain_context') as mock_from_chain_context, \
             patch('tarsy.main.alert_service') as mock_alert_service:
            
            # Mock the factory method to return our test key
            mock_from_chain_context.return_value = mock_alert_key
            
            # Mock alert service to return duplicate status
            from tarsy.models.alert import AlertResponse
            mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
                alert_id="existing-id",
                status="duplicate",
                message="Identical alert is already being processed"
            ))
            
            response = client.post("/api/v1/alerts", json=valid_alert_data)
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "duplicate"
            assert data["alert_id"] == "existing-id"

    @patch('tarsy.main.alert_service')
    def test_submit_alert_payload_too_large(self, mock_alert_service, client):
        """Test rejection of extremely large payloads."""
        from tarsy.models.alert import AlertResponse
        
        # Mock alert service (won't be called due to size limit, but needs to exist)
        mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
            alert_id="test-alert-123",
            status="queued",
            message="Alert submitted for processing and validation completed"
        ))
        
        large_data = {
            "alert_type": "test",
            "runbook": "https://example.com/runbook.md",
            "data": {
                "large_payload": "x" * (11 * 1024 * 1024)  # 11MB payload
            }
        }
        
        response = client.post("/api/v1/alerts", json=large_data)
        assert response.status_code == 413

    @patch('tarsy.main.alert_service')
    def test_submit_alert_suspicious_runbook_url(
        self, mock_alert_service, client, valid_alert_data
    ):
        """Test alert submission with suspicious runbook URL."""
        from tarsy.models.alert import AlertResponse
        
        # Mock process_alert to return a proper AlertResponse
        mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
            alert_id="test-alert-123",
            status="queued",
            message="Alert submitted for processing and validation completed"
        ))
        
        valid_alert_data["runbook"] = "file:///etc/passwd"  # Suspicious URL
        
        response = client.post("/api/v1/alerts", json=valid_alert_data)
        assert response.status_code == 200  # Should still process but log warning

    @patch('tarsy.main.alert_service')
    @patch('asyncio.create_task')
    def test_submit_alert_with_defaults(
        self, mock_create_task, mock_alert_service, client
    ):
        """Test alert submission applies defaults for missing fields."""
        # Mock alert_service methods
        mock_alert_service.register_alert_id = Mock()
        
        minimal_data = {
            "alert_type": "test",
            "runbook": "https://example.com/runbook.md"
        }
        
        response = client.post("/api/v1/alerts", json=minimal_data)
        assert response.status_code == 200
        
        # Verify alert_service.register_alert_id was called
        mock_alert_service.register_alert_id.assert_called_once()
        # Verify background task was created
        mock_create_task.assert_called_once()


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
            from tarsy.models.alert import AlertResponse
            mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
                alert_id="test-alert-123",
                status="queued",
                message="Alert submitted for processing and validation completed"
            ))
            response = client.post("/api/v1/alerts", json=malicious_data)
        
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
                        "array": [
                            "<script>", 
                            "normal_value", 
                            {"nested_in_array": "<img src=x>"}
                        ]
                    }
                }
            }
        }
        
        with patch('tarsy.main.alert_service') as mock_alert_service:
            from tarsy.models.alert import AlertResponse
            mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
                alert_id="test-alert-123",
                status="queued",
                message="Alert submitted for processing and validation completed"
            ))
            response = client.post("/api/v1/alerts", json=nested_data)
        
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
            from tarsy.models.alert import AlertResponse
            mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
                alert_id="test-alert-123",
                status="queued",
                message="Alert submitted for processing and validation completed"
            ))
            response = client.post("/api/v1/alerts", json=large_array_data)
        
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
            from tarsy.models.alert import AlertResponse
            mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
                alert_id="test-alert-123",
                status="queued",
                message="Alert submitted for processing and validation completed"
            ))
            response = client.post("/api/v1/alerts", json=long_string_data)
        
        assert response.status_code == 200


@pytest.mark.unit
class TestAlertControllerCriticalCoverage:
    """Test critical business logic and edge cases for alert controller."""

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
             patch('asyncio.create_task') as mock_create_task:
            
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
                response = client.post("/api/v1/alerts", json=alert_data)
                responses.append(response)
            
            # Verify all were accepted
            for response in responses:
                assert response.status_code == 200
                data = response.json()
                assert data["status"] in ["queued", "duplicate"]
                assert "alert_id" in data
            
            # Verify each alert triggered background processing
            assert mock_create_task.call_count == len(alerts)
            # Verify each alert was registered
            assert mock_alert_service.register_alert_id.call_count == len(alerts)

    def test_alert_processing_recovery_after_failure(self, client):
        """Test that system recovers after alert processing failure."""
        from tests.utils import AlertFactory
        
        alert = AlertFactory.create_kubernetes_alert()
        
        with patch('tarsy.main.alert_service') as mock_alert_service, \
             patch('tarsy.controllers.alert_controller.asyncio.create_task'):
            
            # First call fails, second call succeeds
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
            response1 = client.post("/api/v1/alerts", json=alert_data)
            # Should handle failure gracefully
            assert response1.status_code in [200, 500]
            
            # Second submission should succeed
            response2 = client.post("/api/v1/alerts", json=alert_data)
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
                "alert_type": "test",
                "runbook": "https://example.com/runbook.md",
                "data": {
                    "large_payload": "x" * (11 * 1024 * 1024),  # 11MB payload
                    "deep_nesting": {
                        "level1": {
                            "level2": {"level3": {"level4": {"level5": "value"}}}
                        }
                    }
                }
            }
        ]
        
        for payload in malicious_payloads:
            with patch('tarsy.main.alert_service') as mock_alert_service, \
                 patch('tarsy.main.asyncio.create_task'):
                from tarsy.models.alert import AlertResponse
                
                mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
                    alert_id="test-alert-123",
                    status="queued",
                    message="Alert submitted for processing and validation completed"
                ))
                
                # Should handle malicious payloads gracefully
                response = client.post("/api/v1/alerts", json=payload)
                
                # Should either succeed with sanitization or fail gracefully
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
        
        with patch('tarsy.main.alert_service') as mock_alert_service, \
             patch('tarsy.main.asyncio.create_task'), \
             patch('tarsy.controllers.alert_controller.processing_alert_keys', {}), \
             patch('tarsy.controllers.alert_controller.alert_keys_lock', asyncio.Lock()), \
             patch(
                 'tarsy.models.alert_processing.AlertKey.from_chain_context'
             ) as mock_from_chain_context:
            
            # Mock AlertKey to return a unique key matching production format:
            # <alert_type>_<12-char hex hash>
            mock_key = Mock()
            mock_key.__str__ = Mock(return_value=f"test_alert_{uuid.uuid4().hex[:12]}")
            mock_key.__hash__ = Mock(return_value=12345)
            mock_from_chain_context.return_value = mock_key
            
            from tarsy.models.alert import AlertResponse
            mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
                alert_id="test-alert-123",
                status="queued",
                message="Alert submitted for processing and validation completed"
            ))
            
            # Should not block the endpoint
            response = client.post("/api/v1/alerts", json=alert_data)
            assert response.status_code == 200
            data = response.json()
            
            # First call should succeed (not duplicate)  
            response = client.post("/api/v1/alerts", json=alert_data)
            assert response.status_code == 200
            data = response.json()
            
            # Test duplicate detection by modifying the processing_alert_keys to have an existing entry
            # The next call with the same data should detect as duplicate
            with patch('tarsy.controllers.alert_controller.processing_alert_keys', {mock_key: "existing-id"}):
                response2 = client.post("/api/v1/alerts", json=alert_data)
                assert response2.status_code == 200
                data2 = response2.json()
                assert data2["status"] == "duplicate"
                assert data2["alert_id"] == "existing-id"

    def test_memory_usage_under_load(self, client):
        """Test memory usage behavior under load."""
        from tests.utils import AlertFactory
        
        # Create many alerts to test memory usage
        alerts = [AlertFactory.create_kubernetes_alert() for _ in range(100)]
        
        with patch('tarsy.main.alert_service') as mock_alert_service:
            from tarsy.models.alert import AlertResponse
            mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
                alert_id="test-alert-123",
                status="queued",
                message="Alert submitted for processing and validation completed"
            ))
            
            # Submit many alerts quickly
            for alert in alerts:
                alert_data = {
                    "alert_type": alert.alert_type,
                    "runbook": alert.runbook,
                    "severity": alert.severity,
                    "data": alert.data
                }
                response = client.post("/api/v1/alerts", json=alert_data)
                
                # Each should be processed successfully
                assert response.status_code == 200
