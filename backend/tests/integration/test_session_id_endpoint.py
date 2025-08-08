"""
Integration tests for the /session-id/{alert_id} endpoint.

Tests the complete functionality including 404 error handling for non-existent alert IDs,
successful responses for valid alerts, and interaction with the alert processing workflow.
"""

import uuid
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from tarsy.main import app


@pytest.mark.integration
class TestSessionIdEndpoint:
    """Integration tests for the /session-id/{alert_id} endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client for FastAPI app."""
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def setup_clean_state(self):
        """Ensure clean state before each test."""
        # Import here to avoid circular imports
        import tarsy.main
        
        # Store original alert_service
        original_alert_service = getattr(tarsy.main, 'alert_service', None)
        
        yield
        
        # Restore original alert_service after test
        if original_alert_service is not None:
            tarsy.main.alert_service = original_alert_service

    @pytest.fixture
    def sample_alert_data(self):
        """Sample alert data for testing."""
        return {
            "alert_type": "kubernetes",
            "title": "Pod Restart Loop",
            "message": "Pod my-app-123 is in a restart loop",
            "source": "prometheus",
            "severity": "high",
            "environment": "production",
            "namespace": "default",
            "pod_name": "my-app-123"
        }

    def test_get_session_id_for_non_existent_alert(self, client):
        """Test that non-existent alert IDs return 404."""
        with patch('tarsy.main.alert_service') as mock_alert_service:
            # Mock alert service to simulate non-existent alert
            non_existent_alert_id = str(uuid.uuid4())
            
            # Ensure mock methods return regular values, not coroutines
            mock_alert_service.alert_exists = Mock(return_value=False)
            mock_alert_service.get_session_id_for_alert = Mock(return_value=None)
            
            response = client.get(f"/session-id/{non_existent_alert_id}")
            
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()
            assert non_existent_alert_id in response.json()["detail"]
            
            # Verify service method was called
            mock_alert_service.alert_exists.assert_called_once_with(non_existent_alert_id)

    def test_get_session_id_with_empty_string(self, client):
        """Test endpoint behavior with empty alert ID."""
        with patch('tarsy.main.alert_service') as mock_alert_service:
            # FastAPI should handle this at the path level, but let's test
            response = client.get("/session-id/")
            
            # Should return 404 or method not allowed, not 500
            assert response.status_code in [404, 405]

    def test_get_session_id_for_valid_alert_no_session(self, client, sample_alert_data):
        """Test that valid alert with no session returns null session_id."""
        with patch('tarsy.main.alert_service') as mock_alert_service:
            # Mock alert service to simulate registered alert with no session
            alert_id = str(uuid.uuid4())
            
            # Ensure mock methods return regular values, not coroutines
            mock_alert_service.alert_exists = Mock(return_value=True)
            mock_alert_service.get_session_id_for_alert = Mock(return_value=None)
            
            response = client.get(f"/session-id/{alert_id}")
            
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["alert_id"] == alert_id
            assert response_data["session_id"] is None
            
            # Verify service methods were called
            mock_alert_service.alert_exists.assert_called_once_with(alert_id)
            mock_alert_service.get_session_id_for_alert.assert_called_once_with(alert_id)

    def test_get_session_id_for_valid_alert_with_session(self, client, sample_alert_data):
        """Test that valid alert with session returns the session_id."""
        with patch('tarsy.main.alert_service') as mock_alert_service:
            # Mock alert service to simulate registered alert with session
            alert_id = str(uuid.uuid4())
            session_id = "session-" + str(uuid.uuid4())
            
            # Ensure mock methods return regular values, not coroutines
            mock_alert_service.alert_exists = Mock(return_value=True)
            mock_alert_service.get_session_id_for_alert = Mock(return_value=session_id)
            
            response = client.get(f"/session-id/{alert_id}")
            
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["alert_id"] == alert_id
            assert response_data["session_id"] == session_id
            
            # Verify service methods were called
            mock_alert_service.alert_exists.assert_called_once_with(alert_id)
            mock_alert_service.get_session_id_for_alert.assert_called_once_with(alert_id)

    def test_get_session_id_workflow_simulation(self, client, sample_alert_data):
        """Test session ID workflow: register alert, then check session ID."""
        with patch('tarsy.main.alert_service') as mock_alert_service:
            alert_id = str(uuid.uuid4())
            session_id = "session-" + str(uuid.uuid4())
            
            # Simulate workflow: first call returns no session, second call has session
            call_count = 0
            def mock_get_session_with_progression(alert_id_param):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return None  # No session initially
                else:
                    return session_id  # Session created later
            
            # Ensure mock methods return regular values, not coroutines
            mock_alert_service.alert_exists = Mock(return_value=True)
            mock_alert_service.get_session_id_for_alert = Mock(side_effect=mock_get_session_with_progression)
            
            # First request - no session yet
            response = client.get(f"/session-id/{alert_id}")
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["alert_id"] == alert_id
            assert response_data["session_id"] is None
            
            # Second request - session now exists
            response = client.get(f"/session-id/{alert_id}")
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["alert_id"] == alert_id
            assert response_data["session_id"] == session_id

    def test_multiple_alerts_session_id_isolation(self, client, sample_alert_data):
        """Test that multiple alerts have isolated session ID lookups."""
        with patch('tarsy.main.alert_service') as mock_alert_service:
            alert_id_1 = str(uuid.uuid4())
            alert_id_2 = str(uuid.uuid4())
            session_id_1 = "session-1"
            session_id_2 = "session-2"
            
            # Mock different responses for different alerts
            def mock_alert_exists(alert_id):
                return alert_id in [alert_id_1, alert_id_2]
            
            def mock_get_session(alert_id):
                if alert_id == alert_id_1:
                    return session_id_1
                elif alert_id == alert_id_2:
                    return session_id_2
                return None
            
            # Ensure mock methods return regular values, not coroutines
            mock_alert_service.alert_exists = Mock(side_effect=mock_alert_exists)
            mock_alert_service.get_session_id_for_alert = Mock(side_effect=mock_get_session)
            
            # Test first alert
            response = client.get(f"/session-id/{alert_id_1}")
            assert response.status_code == 200
            assert response.json()["session_id"] == session_id_1
            
            # Test second alert
            response = client.get(f"/session-id/{alert_id_2}")
            assert response.status_code == 200
            assert response.json()["session_id"] == session_id_2
            
            # Test non-existent alert
            non_existent_id = str(uuid.uuid4())
            response = client.get(f"/session-id/{non_existent_id}")
            assert response.status_code == 404

    def test_session_id_endpoint_error_response_format(self, client):
        """Test that 404 error response has correct format."""
        with patch('tarsy.main.alert_service') as mock_alert_service:
            non_existent_id = "definitely-not-an-alert-id"
            
            # Ensure mock methods return regular values, not coroutines
            mock_alert_service.alert_exists = Mock(return_value=False)
            mock_alert_service.get_session_id_for_alert = Mock(return_value=None)
            
            response = client.get(f"/session-id/{non_existent_id}")
            
            assert response.status_code == 404
            assert "detail" in response.json()
            
            detail = response.json()["detail"]
            assert isinstance(detail, str)
            assert "not found" in detail.lower()
            assert non_existent_id in detail

    def test_session_id_endpoint_with_special_characters(self, client):
        """Test endpoint with special characters in alert ID."""
        with patch('tarsy.main.alert_service') as mock_alert_service:
            # Test with URL-encoded characters (common UUIDs with dashes)
            alert_id = "alert-123-456-789"
            
            # Ensure mock methods return regular values, not coroutines
            mock_alert_service.alert_exists = Mock(return_value=True)
            mock_alert_service.get_session_id_for_alert = Mock(return_value="session-123")
            
            response = client.get(f"/session-id/{alert_id}")
            assert response.status_code == 200
            assert response.json()["alert_id"] == alert_id

    def test_session_id_endpoint_performance(self, client):
        """Test endpoint performance with multiple requests."""
        with patch('tarsy.main.alert_service') as mock_alert_service:
            alert_id = str(uuid.uuid4())
            
            # Ensure mock methods return regular values, not coroutines
            mock_alert_service.alert_exists = Mock(return_value=True)
            mock_alert_service.get_session_id_for_alert = Mock(return_value="session-123")
            
            # Make multiple requests to ensure consistent behavior
            for i in range(10):
                response = client.get(f"/session-id/{alert_id}")
                assert response.status_code == 200
                assert response.json()["alert_id"] == alert_id
                assert response.json()["session_id"] == "session-123"
            
            # Verify caching doesn't cause issues
            assert mock_alert_service.alert_exists.call_count == 10
            assert mock_alert_service.get_session_id_for_alert.call_count == 10

    def test_endpoint_maintains_backward_compatibility(self, client):
        """Test that the endpoint maintains backward compatibility."""
        with patch('tarsy.main.alert_service') as mock_alert_service:
            alert_id = str(uuid.uuid4())
            
            # Test scenario where alert exists but history is disabled
            # Ensure mock methods return regular values, not coroutines
            mock_alert_service.alert_exists = Mock(return_value=True)
            mock_alert_service.get_session_id_for_alert = Mock(return_value=None)
            
            response = client.get(f"/session-id/{alert_id}")
            
            # Should still return 200 with null session_id (backward compatible)
            assert response.status_code == 200
            response_data = response.json()
            assert response_data["alert_id"] == alert_id
            assert response_data["session_id"] is None
