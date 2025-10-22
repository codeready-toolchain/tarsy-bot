"""
Unit tests for HealthEndpointFilter logging filter.
"""

import logging
from unittest.mock import MagicMock

from tarsy.utils.logger import HealthEndpointFilter


class TestHealthEndpointFilter:
    """Test suite for HealthEndpointFilter."""

    def test_filter_suppresses_successful_health_endpoint_requests(self) -> None:
        """Test that successful health endpoint requests are filtered out."""
        filter_instance = HealthEndpointFilter()
        
        # Mock a uvicorn access log record for successful health check
        # Format: (client, method, path, http_version, status_code)
        record = MagicMock(spec=logging.LogRecord)
        record.args = ("127.0.0.1:12345", "GET", "/health", "HTTP/1.1", 200)
        
        # Should return False to suppress the log
        assert filter_instance.filter(record) is False

    def test_filter_allows_health_endpoint_errors(self) -> None:
        """Test that health endpoint errors are logged (not suppressed)."""
        filter_instance = HealthEndpointFilter()
        
        # Mock a uvicorn access log record for failed health check (503)
        record = MagicMock(spec=logging.LogRecord)
        record.args = ("127.0.0.1:12345", "GET", "/health", "HTTP/1.1", 503)
        
        # Should return True to allow the log
        assert filter_instance.filter(record) is True

    def test_filter_allows_health_endpoint_client_errors(self) -> None:
        """Test that health endpoint client errors (4xx) are logged."""
        filter_instance = HealthEndpointFilter()
        
        # Mock a uvicorn access log record for client error (404)
        record = MagicMock(spec=logging.LogRecord)
        record.args = ("127.0.0.1:12345", "GET", "/health", "HTTP/1.1", 404)
        
        # Should return True to allow the log
        assert filter_instance.filter(record) is True

    def test_filter_allows_health_endpoint_redirects(self) -> None:
        """Test that health endpoint redirects (3xx) are logged."""
        filter_instance = HealthEndpointFilter()
        
        # Mock a uvicorn access log record for redirect (301)
        record = MagicMock(spec=logging.LogRecord)
        record.args = ("127.0.0.1:12345", "GET", "/health", "HTTP/1.1", 301)
        
        # Should return True to allow the log
        assert filter_instance.filter(record) is True

    def test_filter_allows_other_endpoint_requests(self) -> None:
        """Test that requests to other endpoints are not filtered."""
        filter_instance = HealthEndpointFilter()
        
        # Mock a uvicorn access log record for API endpoint
        record = MagicMock(spec=logging.LogRecord)
        record.args = ("127.0.0.1:12345", "GET", "/api/v1/alerts", "HTTP/1.1", 200)
        
        # Should return True to allow the log
        assert filter_instance.filter(record) is True

    def test_filter_allows_non_get_health_requests(self) -> None:
        """Test that non-GET requests to health endpoint are logged."""
        filter_instance = HealthEndpointFilter()
        
        # Mock a uvicorn access log record for POST to health (unusual but should log)
        record = MagicMock(spec=logging.LogRecord)
        record.args = ("127.0.0.1:12345", "POST", "/health", "HTTP/1.1", 200)
        
        # Should return True to allow the log
        assert filter_instance.filter(record) is True

    def test_filter_handles_malformed_log_records(self) -> None:
        """Test that filter handles malformed log records gracefully."""
        filter_instance = HealthEndpointFilter()
        
        # Mock a log record with insufficient args
        record = MagicMock(spec=logging.LogRecord)
        record.args = ("127.0.0.1", "GET")  # Only 2 args instead of 5
        
        # Should return True (allow) to be safe
        assert filter_instance.filter(record) is True

    def test_filter_handles_records_without_args(self) -> None:
        """Test that filter handles records without args attribute."""
        filter_instance = HealthEndpointFilter()
        
        # Mock a log record without args
        record = MagicMock(spec=logging.LogRecord)
        del record.args  # Remove args attribute
        
        # Should return True (allow) to be safe
        assert filter_instance.filter(record) is True

    def test_filter_handles_records_with_none_args(self) -> None:
        """Test that filter handles records with None args."""
        filter_instance = HealthEndpointFilter()
        
        # Mock a log record with None args
        record = MagicMock(spec=logging.LogRecord)
        record.args = None
        
        # Should return True (allow) to be safe
        assert filter_instance.filter(record) is True

    def test_filter_handles_non_integer_status_codes(self) -> None:
        """Test that filter handles non-integer status codes gracefully."""
        filter_instance = HealthEndpointFilter()
        
        # Mock a log record with string status code
        record = MagicMock(spec=logging.LogRecord)
        record.args = ("127.0.0.1:12345", "GET", "/health", "HTTP/1.1", "200")
        
        # Should return True (allow) to be safe
        assert filter_instance.filter(record) is True

    def test_filter_suppresses_all_2xx_status_codes(self) -> None:
        """Test that all 2xx status codes for health endpoint are suppressed."""
        filter_instance = HealthEndpointFilter()
        
        # Test various 2xx status codes
        for status_code in [200, 201, 202, 204, 206]:
            record = MagicMock(spec=logging.LogRecord)
            record.args = ("127.0.0.1:12345", "GET", "/health", "HTTP/1.1", status_code)
            
            # All 2xx should be suppressed
            assert filter_instance.filter(record) is False, f"Status {status_code} should be suppressed"

    def test_filter_suppresses_successful_warnings_endpoint_requests(self) -> None:
        """Test that successful warnings endpoint requests are filtered out."""
        filter_instance = HealthEndpointFilter()
        
        # Mock a uvicorn access log record for successful warnings check
        record = MagicMock(spec=logging.LogRecord)
        record.args = ("127.0.0.1:12345", "GET", "/api/v1/system/warnings", "HTTP/1.1", 200)
        
        # Should return False to suppress the log (prevents noise from dashboard polling)
        assert filter_instance.filter(record) is False

    def test_filter_allows_warnings_endpoint_errors(self) -> None:
        """Test that warnings endpoint errors are logged (not suppressed)."""
        filter_instance = HealthEndpointFilter()
        
        # Mock a uvicorn access log record for failed warnings check (500)
        record = MagicMock(spec=logging.LogRecord)
        record.args = ("127.0.0.1:12345", "GET", "/api/v1/system/warnings", "HTTP/1.1", 500)
        
        # Should return True to allow the log (errors should be visible)
        assert filter_instance.filter(record) is True

    def test_filter_allows_non_get_warnings_requests(self) -> None:
        """Test that non-GET requests to warnings endpoint are logged."""
        filter_instance = HealthEndpointFilter()
        
        # Mock a uvicorn access log record for POST to warnings (unusual but should log)
        record = MagicMock(spec=logging.LogRecord)
        record.args = ("127.0.0.1:12345", "POST", "/api/v1/system/warnings", "HTTP/1.1", 200)
        
        # Should return True to allow the log (non-GET methods are noteworthy)
        assert filter_instance.filter(record) is True

    def test_filter_suppresses_both_monitoring_endpoints(self) -> None:
        """Test that both health and warnings monitoring endpoints are suppressed."""
        filter_instance = HealthEndpointFilter()
        
        # Test that both frequently-polled endpoints are suppressed with 200 OK
        endpoints = ["/health", "/api/v1/system/warnings"]
        
        for endpoint in endpoints:
            record = MagicMock(spec=logging.LogRecord)
            record.args = ("127.0.0.1:12345", "GET", endpoint, "HTTP/1.1", 200)
            
            assert filter_instance.filter(record) is False, f"Endpoint {endpoint} should be suppressed"

