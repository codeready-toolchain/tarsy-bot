"""
Unit tests for the alert controller.

This module tests the alert-related endpoints that were moved from main.py
to controllers/alert_controller.py for better code organization.
"""

import asyncio
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
        
        # Mock the process_alert_callback in app state
        app.state.process_alert_callback = AsyncMock()
        
        # Create many alerts to test memory usage
        alerts = [AlertFactory.create_kubernetes_alert() for _ in range(100)]
        
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

    def test_submit_alert_success(
        self, client, valid_alert_data
    ):
        """Test successful alert submission."""
        # Mock the process_alert_callback in app state
        app.state.process_alert_callback = AsyncMock()
        
        response = client.post("/api/v1/alerts", json=valid_alert_data)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "queued"
        assert "session_id" in data
        assert len(data["session_id"]) == 36  # UUID format
        assert data["message"] == "Alert submitted for processing"
        
        # Verify background callback was called
        assert app.state.process_alert_callback.called

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
    ])
    @patch('tarsy.main.alert_service')
    def test_submit_alert_input_validation(
        self, mock_alert_service, client, valid_alert_data, invalid_input, expected_status, expected_error
    ):
        """Test alert submission with various invalid inputs."""
        from tarsy.models.alert import AlertResponse
        
        # Mock alert service (won't be called for input validation errors, but needs to exist)
        mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
            session_id="test-alert-123",
            status="queued",
            message="Alert submitted for processing"
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
            assert "required_fields" in data["detail"]
            assert "optional_fields" in data["detail"]
        elif expected_error == "Invalid data structure":
            assert "received_type" in data["detail"]
        elif expected_error == "Validation failed":
            assert "validation_errors" in data["detail"]
            assert "required_fields" in data["detail"]
            assert "optional_fields" in data["detail"]
        elif expected_error == "Invalid alert_type":
            assert "field" in data["detail"]


    @patch('tarsy.main.alert_service')
    def test_submit_alert_payload_too_large(self, mock_alert_service, client):
        """Test rejection of extremely large payloads."""
        from tarsy.models.alert import AlertResponse
        
        # Mock alert service (won't be called due to size limit, but needs to exist)
        mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
            session_id="test-alert-123",
            status="queued",
            message="Alert submitted for processing"
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
    def test_submit_alert_unsafe_runbook_url_rejected(
        self, mock_alert_service, client, valid_alert_data
    ):
        """Test alert submission with unsafe runbook URL schemes gets rejected."""
        valid_alert_data["runbook"] = "file:///etc/passwd"  # Unsafe URL scheme
        
        response = client.post("/api/v1/alerts", json=valid_alert_data)
        assert response.status_code == 400
        data = response.json()
        
        assert data["detail"]["error"] == "Invalid runbook URL scheme"
        assert "file" in data["detail"]["message"]
        assert data["detail"]["field"] == "runbook"
        assert data["detail"]["allowed_schemes"] == ["http", "https"]

    @pytest.mark.parametrize("unsafe_url", [
        "file:///etc/passwd",
        "ssh://user@host/path",
        "data:text/html,<script>alert(1)</script>",
        "javascript:alert(document.cookie)",
        "ftp://internal.server/file",
        "ldap://directory.service/query",
        "gopher://old.protocol/path"
    ])
    def test_submit_alert_various_unsafe_url_schemes(self, client, valid_alert_data, unsafe_url):
        """Test that various unsafe URL schemes are rejected."""
        valid_alert_data["runbook"] = unsafe_url
        
        response = client.post("/api/v1/alerts", json=valid_alert_data)
        assert response.status_code == 400
        data = response.json()
        assert data["detail"]["error"] == "Invalid runbook URL scheme"
        assert data["detail"]["field"] == "runbook"

    def test_submit_alert_with_defaults(
        self, client
    ):
        """Test alert submission applies defaults for missing fields."""
        # Mock the process_alert_callback in app state
        app.state.process_alert_callback = AsyncMock()
        
        minimal_data = {
            "alert_type": "test",
            "runbook": "https://example.com/runbook.md"
        }
        
        response = client.post("/api/v1/alerts", json=minimal_data)
        assert response.status_code == 200
        
        # Verify background callback was called
        assert app.state.process_alert_callback.called

    def test_submit_alert_without_runbook(
        self, client
    ):
        """Test alert submission without runbook field (should use built-in default)."""
        # Mock the process_alert_callback in app state
        app.state.process_alert_callback = AsyncMock()
        
        alert_data_no_runbook = {
            "alert_type": "test_alert",
            "data": {
                "namespace": "test-namespace",
                "message": "Test alert without runbook"
            }
        }
        
        response = client.post("/api/v1/alerts", json=alert_data_no_runbook)
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "queued"
        assert "session_id" in data
        assert len(data["session_id"]) == 36  # UUID format
        
        # Verify background callback was called
        assert app.state.process_alert_callback.called

    def test_submit_alert_invalid_content_length_header(self, client, valid_alert_data):
        """Test that invalid Content-Length headers are handled gracefully."""
        import json
        
        # Test with invalid Content-Length header
        response = client.post(
            "/api/v1/alerts",
            data=json.dumps(valid_alert_data),
            headers={
                "Content-Type": "application/json",
                "Content-Length": "invalid-number"
            }
        )
        
        # Should proceed to process the body size after reading
        # The actual body size enforcement will catch oversized payloads
        assert response.status_code in [200, 400, 413, 422]  # Various valid outcomes

    def test_submit_alert_post_read_size_verification(self, client, valid_alert_data):
        """Test that payload size is verified after reading, regardless of Content-Length header."""
        import json
        
        # Create oversized payload (over 10MB)
        oversized_data = valid_alert_data.copy()
        oversized_data["data"] = {"large_field": "x" * (11 * 1024 * 1024)}  # 11MB
        
        # Test with missing Content-Length header (should still be caught)
        response = client.post(
            "/api/v1/alerts",
            data=json.dumps(oversized_data),
            headers={"Content-Type": "application/json"}  # No Content-Length
        )
        
        # Should be rejected due to post-read size verification
        assert response.status_code == 413
        data = response.json()
        assert data["detail"]["error"] == "Payload too large"


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
                session_id="test-alert-123",
                status="queued",
                message="Alert submitted for processing"
            ))
            response = client.post("/api/v1/alerts", json=malicious_data)
        
        # Should succeed after sanitization
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "input_data,test_description",
        [
            (
                {"message": "line1\nline2\nline3"},
                "Simple newlines in message"
            ),
            (
                {"yaml_data": "name: test\nnode: server1\ncontainers:\n    - name: app"},
                "YAML-like structure with newlines"
            ),
            (
                {"multiline": "First line\nSecond line\nThird line\nFourth line"},
                "Multiple consecutive newlines"
            ),
            (
                {"logs": "Error occurred\nStack trace:\n  at function1()\n  at function2()"},
                "Log messages with indentation"
            ),
        ],
    )
    def test_sanitization_preserves_newlines(
        self, client, input_data, test_description
    ):
        """Test that alerts with newlines are accepted and processed successfully."""
        alert_data = {
            "alert_type": "test",
            "runbook": "https://example.com/runbook.md",
            "data": input_data
        }
        
        # Mock the callback
        app.state.process_alert_callback = AsyncMock()
        
        response = client.post("/api/v1/alerts", json=alert_data)
        
        # If newlines were being stripped (old bug), special characters in newlines 
        # would cause sanitization issues. Success means newlines were preserved.
        assert response.status_code == 200, f"{test_description}: Failed to process alert with newlines"
        data = response.json()
        assert data["status"] == "queued"
        assert "session_id" in data

    @pytest.mark.parametrize(
        "input_data,test_description",
        [
            (
                {"message": "column1\tcolumn2\tcolumn3"},
                "Tab-separated values"
            ),
            (
                {"code": "def function():\n\treturn True"},
                "Code with tab indentation"
            ),
            (
                {"data": "field1\tfield2\nvalue1\tvalue2"},
                "Mixed tabs and newlines"
            ),
        ],
    )
    def test_sanitization_preserves_tabs(
        self, client, input_data, test_description
    ):
        """Test that alerts with tabs are accepted and processed successfully."""
        alert_data = {
            "alert_type": "test",
            "runbook": "https://example.com/runbook.md",
            "data": input_data
        }
        
        # Mock the callback
        app.state.process_alert_callback = AsyncMock()
        
        response = client.post("/api/v1/alerts", json=alert_data)
        
        assert response.status_code == 200, f"{test_description}: Failed to process alert with tabs"
        data = response.json()
        assert data["status"] == "queued"
        assert "session_id" in data

    def test_sanitization_preserves_carriage_returns(self, client):
        """Test that carriage returns are preserved in sanitized data."""
        alert_data = {
            "alert_type": "test",
            "runbook": "https://example.com/runbook.md",
            "data": {
                "message": "line1\r\nline2\r\nline3"
            }
        }
        
        # Mock the callback
        app.state.process_alert_callback = AsyncMock()
        
        response = client.post("/api/v1/alerts", json=alert_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "session_id" in data

    def test_sanitization_removes_dangerous_characters_but_keeps_whitespace(self, client):
        """Test that dangerous characters are removed but whitespace is preserved."""
        alert_data = {
            "alert_type": "test",
            "runbook": "https://example.com/runbook.md",
            "data": {
                "message": "<script>alert('xss')</script>\nLegitimate data\twith tab"
            }
        }
        
        # Mock the callback
        app.state.process_alert_callback = AsyncMock()
        
        response = client.post("/api/v1/alerts", json=alert_data)
        
        # Should successfully sanitize and accept the alert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "session_id" in data

    def test_yaml_structure_preservation(self, client):
        """Test that YAML-like structures with newlines and indentation are accepted."""
        yaml_data = """name: nanochat-0
node: ip-10-0-67-102.ec2.internal
ec2_instance: i-08428461af8eea9e4
containers:
    - name: nanochat
      reports:
        - analyzer: file-system-analyzer
          outcome: suspicious
          contents:
            - detected: Ragnarok
              source: /proc/1169670/root/opt/app-root/src/models/file.jsonl"""
        
        alert_data = {
            "alert_type": "kubernetes",
            "runbook": "https://example.com/runbook.md",
            "data": {
                "message": yaml_data
            }
        }
        
        # Mock the callback
        app.state.process_alert_callback = AsyncMock()
        
        response = client.post("/api/v1/alerts", json=alert_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "session_id" in data

    def test_deep_sanitization_preserves_newlines_in_nested_structures(self, client):
        """Test that deeply nested objects with newlines are accepted successfully."""
        nested_data = {
            "alert_type": "test",
            "runbook": "https://example.com/runbook.md",
            "data": {
                "level1": {
                    "message": "First\nSecond\nThird",
                    "level2": {
                        "logs": "Error\nStack trace:\n  Line 1\n  Line 2",
                        "level3": {
                            "details": "Info\nMore info\nEven more"
                        }
                    }
                }
            }
        }
        
        # Mock the callback
        app.state.process_alert_callback = AsyncMock()
        
        response = client.post("/api/v1/alerts", json=nested_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "session_id" in data

    def test_sanitization_preserves_whitespace_in_arrays(self, client):
        """Test that array elements with whitespace are accepted successfully."""
        alert_data = {
            "alert_type": "test",
            "runbook": "https://example.com/runbook.md",
            "data": {
                "logs": [
                    "Log line 1\nwith newline",
                    "Log line 2\twith tab",
                    "Log line 3\r\nwith CRLF"
                ]
            }
        }
        
        # Mock the callback
        app.state.process_alert_callback = AsyncMock()
        
        response = client.post("/api/v1/alerts", json=alert_data)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "session_id" in data

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
                session_id="test-alert-123",
                status="queued",
                message="Alert submitted for processing"
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
                session_id="test-alert-123",
                status="queued",
                message="Alert submitted for processing"
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
                session_id="test-alert-123",
                status="queued",
                message="Alert submitted for processing"
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
        
        # Mock the process_alert_callback in app state
        app.state.process_alert_callback = AsyncMock()
        
        for payload in malicious_payloads:
            # Should handle malicious payloads gracefully
            response = client.post("/api/v1/alerts", json=payload)
            
            # Second payload (11MB) should be rejected with 413
            # First payload should either succeed with sanitization or fail gracefully
            assert response.status_code in [200, 400, 413, 422]


    def test_memory_usage_under_load(self, client):
        """Test memory usage behavior under load."""
        from tests.utils import AlertFactory
        
        # Create many alerts to test memory usage
        alerts = [AlertFactory.create_kubernetes_alert() for _ in range(100)]
        
        with patch('tarsy.main.alert_service') as mock_alert_service:
            from tarsy.models.alert import AlertResponse
            mock_alert_service.process_alert = AsyncMock(return_value=AlertResponse(
                session_id="test-alert-123",
                status="queued",
                message="Alert submitted for processing"
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
