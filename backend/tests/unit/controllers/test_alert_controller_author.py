"""
Unit tests for author field in alert controller.

Tests the extraction of author information from oauth2-proxy headers
(X-Forwarded-User and X-Forwarded-Email) and the default fallback to "api-client"
when headers are not present.
"""

import pytest
from unittest.mock import Mock, patch
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
        self, client, valid_alert_data, forwarded_user, forwarded_email, expected_author
    ):
        """Test that author is correctly extracted from oauth2-proxy headers."""
        # Mock the process_alert_callback in app state to capture the context
        captured_context = []

        async def mock_callback(session_id, context):
            captured_context.append(context)

        app.state.process_alert_callback = mock_callback

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

        # Verify author was set correctly in the context
        assert len(captured_context) == 1
        context = captured_context[0]
        assert context.author == expected_author

    def test_author_prioritizes_username_over_email(
        self, client, valid_alert_data
    ):
        """Test that X-Forwarded-User is prioritized over X-Forwarded-Email."""
        captured_context = []

        async def mock_callback(session_id, context):
            captured_context.append(context)

        app.state.process_alert_callback = mock_callback

        headers = {
            "Content-Type": "application/json",
            "X-Forwarded-User": "github-username",
            "X-Forwarded-Email": "different@email.com"
        }

        response = client.post("/api/v1/alerts", json=valid_alert_data, headers=headers)

        assert response.status_code == 200
        assert len(captured_context) == 1
        # Should use username, not email
        assert captured_context[0].author == "github-username"

    def test_author_with_special_characters_in_username(
        self, client, valid_alert_data
    ):
        """Test author field handles special characters in usernames."""
        captured_context = []

        async def mock_callback(session_id, context):
            captured_context.append(context)

        app.state.process_alert_callback = mock_callback

        special_usernames = [
            "user-name",
            "user.name",
            "user_name",
            "user123",
            "user@org",
        ]

        for username in special_usernames:
            captured_context.clear()
            
            headers = {
                "Content-Type": "application/json",
                "X-Forwarded-User": username
            }

            response = client.post("/api/v1/alerts", json=valid_alert_data, headers=headers)

            assert response.status_code == 200
            assert len(captured_context) == 1
            assert captured_context[0].author == username

    def test_author_with_long_username(
        self, client, valid_alert_data
    ):
        """Test author field handles long usernames (up to 255 chars)."""
        captured_context = []

        async def mock_callback(session_id, context):
            captured_context.append(context)

        app.state.process_alert_callback = mock_callback

        long_username = "user" * 60  # 240 characters
        
        headers = {
            "Content-Type": "application/json",
            "X-Forwarded-User": long_username
        }

        response = client.post("/api/v1/alerts", json=valid_alert_data, headers=headers)

        assert response.status_code == 200
        assert len(captured_context) == 1
        assert captured_context[0].author == long_username

    def test_author_without_oauth_headers_uses_default(
        self, client, valid_alert_data
    ):
        """Test that API clients without oauth headers get 'api-client' as author."""
        captured_context = []

        async def mock_callback(session_id, context):
            captured_context.append(context)

        app.state.process_alert_callback = mock_callback

        # No oauth2-proxy headers at all
        response = client.post("/api/v1/alerts", json=valid_alert_data)

        assert response.status_code == 200
        assert len(captured_context) == 1
        assert captured_context[0].author == "api-client"

    def test_author_with_only_empty_headers(
        self, client, valid_alert_data
    ):
        """Test that empty header values result in default author."""
        captured_context = []

        async def mock_callback(session_id, context):
            captured_context.append(context)

        app.state.process_alert_callback = mock_callback

        headers = {
            "Content-Type": "application/json",
            "X-Forwarded-User": "",
            "X-Forwarded-Email": ""
        }

        response = client.post("/api/v1/alerts", json=valid_alert_data, headers=headers)

        assert response.status_code == 200
        assert len(captured_context) == 1
        # Empty strings should result in default
        assert captured_context[0].author == "api-client"

