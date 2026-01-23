"""
Unit tests for author field in alert controller.

Tests the extraction of author information from oauth2-proxy headers
(X-Forwarded-User and X-Forwarded-Email) and the default fallback to "api-client"
when headers are not present.
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from tarsy.main import app


@pytest.mark.unit
class TestAuthorFieldHeaderExtraction:
    """Test author field extraction from oauth2-proxy headers."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture(autouse=True)
    def mock_alert_service(self):
        """Mock alert_service with chain_registry for default alert type."""
        with patch('tarsy.main.alert_service') as mock_service:
            mock_chain_registry = Mock()
            mock_chain_registry.get_default_alert_type.return_value = "kubernetes"
            mock_service.chain_registry = mock_chain_registry
            
            # Mock session manager to capture session creation
            mock_session_manager = Mock()
            mock_session_manager.create_chain_history_session.return_value = True
            mock_service.session_manager = mock_session_manager
            
            yield mock_service

    @pytest.fixture
    def valid_alert_data(self):
        """Valid alert data for testing."""
        return {
            "alert_type": "test_alert",
            "runbook": "https://example.com/runbook.md",
            "data": {
                "namespace": "test-namespace",
                "message": "Test alert for author field"
            }
        }

    @pytest.mark.parametrize(
        "forwarded_user,forwarded_email,expected_author",
        [
            # OAuth user with username
            ("github-user", "user@example.com", "github-user"),
            # OAuth user without username (only email)
            (None, "user@example.com", "user@example.com"),
            # API client (no headers)
            (None, None, "api-client"),
            # Empty string headers should use default
            ("", "", "api-client"),
            # Whitespace-only headers should use default
            ("   ", "   ", "api-client"),
        ],
    )
    def test_author_extraction_from_headers(
        self, client, valid_alert_data, mock_alert_service, forwarded_user, forwarded_email, expected_author
    ):
        """Test that author is correctly extracted from oauth2-proxy headers."""
        # Build headers
        headers = {"Content-Type": "application/json"}
        if forwarded_user:
            headers["X-Forwarded-User"] = forwarded_user
        if forwarded_email:
            headers["X-Forwarded-Email"] = forwarded_email

        # Submit alert
        response = client.post("/api/v1/alerts", json=valid_alert_data, headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "queued"
        assert "session_id" in data
        
        # Verify author was passed correctly to session creation
        mock_alert_service.session_manager.create_chain_history_session.assert_called_once()
        call_args = mock_alert_service.session_manager.create_chain_history_session.call_args
        chain_context = call_args[0][0]
        assert chain_context.author == expected_author

    def test_author_prioritizes_username_over_email(
        self, client, valid_alert_data, mock_alert_service
    ):
        """Test that X-Forwarded-User is prioritized over X-Forwarded-Email."""
        headers = {
            "Content-Type": "application/json",
            "X-Forwarded-User": "github-username",
            "X-Forwarded-Email": "different@email.com"
        }

        response = client.post("/api/v1/alerts", json=valid_alert_data, headers=headers)

        assert response.status_code == 200
        
        # Verify author passed to session creation - should use username, not email
        mock_alert_service.session_manager.create_chain_history_session.assert_called_once()
        call_args = mock_alert_service.session_manager.create_chain_history_session.call_args
        chain_context = call_args[0][0]
        assert chain_context.author == "github-username"

    def test_author_with_special_characters_in_username(
        self, client, valid_alert_data, mock_alert_service
    ):
        """Test author field handles special characters in usernames."""
        special_usernames = [
            "user-name",
            "user.name",
            "user_name",
            "user123",
            "user@org",
        ]

        for username in special_usernames:
            # Reset mock call count for each iteration
            mock_alert_service.session_manager.create_chain_history_session.reset_mock()
            
            headers = {
                "Content-Type": "application/json",
                "X-Forwarded-User": username
            }

            response = client.post("/api/v1/alerts", json=valid_alert_data, headers=headers)

            assert response.status_code == 200
            
            # Verify author passed to session creation
            mock_alert_service.session_manager.create_chain_history_session.assert_called_once()
            call_args = mock_alert_service.session_manager.create_chain_history_session.call_args
            chain_context = call_args[0][0]
            assert chain_context.author == username

    def test_author_with_long_username(
        self, client, valid_alert_data, mock_alert_service
    ):
        """Test author field handles long usernames (up to 255 chars)."""
        long_username = "user" * 60  # 240 characters
        
        headers = {
            "Content-Type": "application/json",
            "X-Forwarded-User": long_username
        }

        response = client.post("/api/v1/alerts", json=valid_alert_data, headers=headers)

        assert response.status_code == 200
        
        # Verify author passed to session creation
        mock_alert_service.session_manager.create_chain_history_session.assert_called_once()
        call_args = mock_alert_service.session_manager.create_chain_history_session.call_args
        chain_context = call_args[0][0]
        assert chain_context.author == long_username

    def test_author_without_oauth_headers_uses_default(
        self, client, valid_alert_data, mock_alert_service
    ):
        """Test that API clients without oauth headers get 'api-client' as author."""
        # No oauth2-proxy headers at all
        response = client.post("/api/v1/alerts", json=valid_alert_data)

        assert response.status_code == 200
        
        # Verify author passed to session creation
        mock_alert_service.session_manager.create_chain_history_session.assert_called_once()
        call_args = mock_alert_service.session_manager.create_chain_history_session.call_args
        chain_context = call_args[0][0]
        assert chain_context.author == "api-client"

    def test_author_with_only_empty_headers(
        self, client, valid_alert_data, mock_alert_service
    ):
        """Test that empty header values result in default author."""
        headers = {
            "Content-Type": "application/json",
            "X-Forwarded-User": "",
            "X-Forwarded-Email": ""
        }

        response = client.post("/api/v1/alerts", json=valid_alert_data, headers=headers)

        assert response.status_code == 200
        
        # Verify author passed to session creation - empty strings should result in default
        mock_alert_service.session_manager.create_chain_history_session.assert_called_once()
        call_args = mock_alert_service.session_manager.create_chain_history_session.call_args
        chain_context = call_args[0][0]
        assert chain_context.author == "api-client"

