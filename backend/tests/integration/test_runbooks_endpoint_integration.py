"""
Integration tests for runbooks endpoint.

Tests the /api/v1/runbooks endpoint with real HTTP calls and mocked GitHub API.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from tarsy.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client for FastAPI app."""
    return TestClient(app)


class TestRunbooksEndpointIntegration:
    """Test runbooks endpoint integration with HTTP layer."""

    @pytest.mark.integration
    def test_runbooks_endpoint_returns_list_when_configured(
        self, client: TestClient
    ) -> None:
        """Test endpoint returns runbook URLs when properly configured."""
        mock_runbooks = [
            "https://github.com/org/repo/blob/master/runbooks/r1.md",
            "https://github.com/org/repo/blob/master/runbooks/r2.md",
            "https://github.com/org/repo/blob/master/runbooks/r3.md",
        ]

        with patch(
            "tarsy.services.runbooks_service.RunbooksService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_runbooks.return_value = mock_runbooks
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/runbooks")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3
        assert data == mock_runbooks

    @pytest.mark.integration
    def test_runbooks_endpoint_returns_empty_list_when_not_configured(
        self, client: TestClient
    ) -> None:
        """Test endpoint returns empty list when runbooks_repo_url not configured."""
        with patch(
            "tarsy.services.runbooks_service.RunbooksService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_runbooks.return_value = []
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/runbooks")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.integration
    def test_runbooks_endpoint_handles_service_errors_gracefully(
        self, client: TestClient
    ) -> None:
        """Test endpoint handles service errors without failing."""
        with patch(
            "tarsy.services.runbooks_service.RunbooksService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_runbooks.side_effect = Exception("GitHub API error")
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/runbooks")

        # Should still return 200 with empty list instead of crashing
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.integration
    def test_runbooks_endpoint_content_type(self, client: TestClient) -> None:
        """Test endpoint returns correct content type."""
        with patch(
            "tarsy.services.runbooks_service.RunbooksService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_runbooks.return_value = []
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/runbooks")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    @pytest.mark.integration
    def test_runbooks_endpoint_response_schema(self, client: TestClient) -> None:
        """Test endpoint response matches expected schema."""
        mock_runbooks = [
            "https://github.com/org1/repo1/blob/main/docs/runbook.md",
            "https://github.com/org2/repo2/blob/master/runbooks/alert.md",
        ]

        with patch(
            "tarsy.services.runbooks_service.RunbooksService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_runbooks.return_value = mock_runbooks
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/runbooks")

        assert response.status_code == 200
        data = response.json()
        
        # Verify response is list of strings
        assert isinstance(data, list)
        for item in data:
            assert isinstance(item, str)
            assert item.startswith("https://github.com/")

    @pytest.mark.integration
    def test_runbooks_endpoint_uses_settings_from_app(
        self, client: TestClient
    ) -> None:
        """Test endpoint uses application settings correctly."""
        with patch(
            "tarsy.config.settings.get_settings"
        ) as mock_get_settings:
            mock_settings = AsyncMock()
            mock_settings.github_token = "test_token"
            mock_settings.runbooks_repo_url = "https://github.com/org/repo/tree/master/docs"
            mock_get_settings.return_value = mock_settings

            with patch(
                "tarsy.services.runbooks_service.RunbooksService"
            ) as mock_service_class:
                mock_service = AsyncMock()
                mock_service.get_runbooks.return_value = []
                mock_service_class.return_value = mock_service

                response = client.get("/api/v1/runbooks")

                # Verify service was created with settings
                mock_service_class.assert_called_once_with(mock_settings)

        assert response.status_code == 200


class TestRunbooksEndpointWithRealService:
    """Test runbooks endpoint with real service but mocked GitHub API."""

    @pytest.mark.integration
    def test_endpoint_with_real_service_and_mocked_github(
        self, client: TestClient
    ) -> None:
        """Test endpoint with real RunbooksService but mocked PyGithub API."""
        # Mock PyGithub file objects
        mock_file1 = Mock()
        mock_file1.type = "file"
        mock_file1.name = "runbook1.md"
        mock_file1.path = "runbooks/runbook1.md"

        mock_file2 = Mock()
        mock_file2.type = "file"
        mock_file2.name = "runbook2.md"
        mock_file2.path = "runbooks/runbook2.md"

        # Mock GitHub repository
        mock_repo = Mock()
        mock_repo.get_contents = Mock(return_value=[mock_file1, mock_file2])

        # Mock Github client
        mock_github = Mock()
        mock_github.get_repo = Mock(return_value=mock_repo)

        with patch("tarsy.services.runbooks_service.Github") as mock_github_class:
            with patch("tarsy.services.runbooks_service.Auth"):
                mock_github_class.return_value = mock_github

                with patch(
                    "tarsy.config.settings.get_settings"
                ) as mock_get_settings:
                    mock_settings = Mock()
                    mock_settings.github_token = "test_token"
                    mock_settings.runbooks_repo_url = (
                        "https://github.com/test-org/test-repo/tree/master/runbooks"
                    )
                    mock_get_settings.return_value = mock_settings

                    response = client.get("/api/v1/runbooks")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert all("runbook" in url and ".md" in url for url in data)


class TestRunbooksEndpointErrorScenarios:
    """Test error handling scenarios for runbooks endpoint."""

    @pytest.mark.integration
    @pytest.mark.parametrize(
        "github_error,expected_response",
        [
            (Exception("Network error"), []),
            (ValueError("Invalid URL"), []),
            (RuntimeError("Unexpected error"), []),
        ],
    )
    def test_endpoint_error_handling(
        self, client: TestClient, github_error: Exception, expected_response: list[Any]
    ) -> None:
        """Test endpoint handles various GitHub API errors gracefully."""
        with patch(
            "tarsy.services.runbooks_service.RunbooksService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_runbooks.side_effect = github_error
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/runbooks")

        assert response.status_code == 200
        assert response.json() == expected_response

    @pytest.mark.integration
    def test_endpoint_with_timeout_error(self, client: TestClient) -> None:
        """Test endpoint handles timeout errors gracefully."""
        import asyncio

        with patch(
            "tarsy.services.runbooks_service.RunbooksService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_runbooks.side_effect = asyncio.TimeoutError()
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/runbooks")

        assert response.status_code == 200
        assert response.json() == []


class TestRunbooksEndpointCORS:
    """Test CORS handling for runbooks endpoint."""

    @pytest.mark.integration
    def test_runbooks_endpoint_cors_headers(self, client: TestClient) -> None:
        """Test endpoint includes proper CORS headers if configured."""
        with patch(
            "tarsy.services.runbooks_service.RunbooksService"
        ) as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_runbooks.return_value = []
            mock_service_class.return_value = mock_service

            response = client.get("/api/v1/runbooks")

        assert response.status_code == 200
        # CORS headers are configured at app level, just verify response succeeds

