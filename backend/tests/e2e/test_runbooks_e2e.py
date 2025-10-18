"""
E2E tests for runbooks functionality.

Tests the complete runbooks flow from API endpoint through service layer
to GitHub API integration.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from tarsy.main import app


@pytest.fixture
def client() -> TestClient:
    """Create test client for FastAPI app."""
    return TestClient(app)


class TestRunbooksE2E:
    """End-to-end tests for runbooks functionality."""

    @pytest.mark.e2e
    def test_complete_runbooks_flow_with_valid_configuration(
        self, client: TestClient
    ) -> None:
        """Test complete flow from API call to GitHub and back with valid config."""
        # Mock GitHub API response
        mock_github_contents = [
            {
                "name": "namespace-terminating.md",
                "type": "file",
                "path": "runbooks/ai/namespace-terminating.md",
            },
            {
                "name": "pod-crashloop.md",
                "type": "file",
                "path": "runbooks/ai/pod-crashloop.md",
            },
            {
                "name": "subdirectory",
                "type": "dir",
                "path": "runbooks/ai/subdirectory",
            },
        ]

        mock_github_subdir_contents = [
            {
                "name": "advanced-debugging.md",
                "type": "file",
                "path": "runbooks/ai/subdirectory/advanced-debugging.md",
            },
        ]

        async def mock_github_get(url: str, **kwargs: Any) -> Mock:
            """Mock GitHub API GET requests."""
            response = Mock()
            if "subdirectory" in url:
                response.json = lambda: mock_github_subdir_contents
            else:
                response.json = lambda: mock_github_contents
            response.raise_for_status = lambda: None
            return response

        # Mock settings for this test
        with patch("tarsy.config.settings.get_settings") as mock_get_settings:
            test_settings = Mock()
            test_settings.github_token = "test_e2e_token"
            test_settings.runbooks_repo_url = (
                "https://github.com/codeready-toolchain/sandbox-sre/tree/master/runbooks/ai"
            )
            mock_get_settings.return_value = test_settings

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.get = mock_github_get
                mock_client_class.return_value = mock_client

                # Make API call
                response = client.get("/api/v1/runbooks")

        # Verify response
        assert response.status_code == 200
        runbooks = response.json()
        
        assert isinstance(runbooks, list)
        assert len(runbooks) == 3
        
        # Verify expected URLs are present
        expected_urls = [
            "https://github.com/codeready-toolchain/sandbox-sre/blob/master/runbooks/ai/namespace-terminating.md",
            "https://github.com/codeready-toolchain/sandbox-sre/blob/master/runbooks/ai/pod-crashloop.md",
            "https://github.com/codeready-toolchain/sandbox-sre/blob/master/runbooks/ai/subdirectory/advanced-debugging.md",
        ]
        
        for expected_url in expected_urls:
            assert expected_url in runbooks

    @pytest.mark.e2e
    def test_complete_flow_without_configuration(self, client: TestClient) -> None:
        """Test complete flow when runbooks_repo_url is not configured."""
        with patch("tarsy.config.settings.get_settings") as mock_get_settings:
            test_settings = Mock()
            test_settings.github_token = None
            test_settings.runbooks_repo_url = None
            mock_get_settings.return_value = test_settings

            response = client.get("/api/v1/runbooks")

        assert response.status_code == 200
        runbooks = response.json()
        assert runbooks == []

    @pytest.mark.e2e
    def test_complete_flow_with_github_authentication_failure(
        self, client: TestClient
    ) -> None:
        """Test complete flow when GitHub authentication fails."""
        with patch("tarsy.config.settings.get_settings") as mock_get_settings:
            test_settings = Mock()
            test_settings.github_token = "invalid_token"
            test_settings.runbooks_repo_url = (
                "https://github.com/private-org/private-repo/tree/master/runbooks"
            )
            mock_get_settings.return_value = test_settings

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                
                # Simulate 401 authentication error
                mock_response = Mock()
                mock_response.status_code = 401
                mock_response.text = "Unauthorized"
                error = httpx.HTTPStatusError(
                    "Unauthorized",
                    request=Mock(),
                    response=mock_response
                )
                mock_client.get = AsyncMock(side_effect=error)
                mock_client_class.return_value = mock_client

                response = client.get("/api/v1/runbooks")

        # Should return empty list gracefully
        assert response.status_code == 200
        runbooks = response.json()
        assert runbooks == []

    @pytest.mark.e2e
    def test_complete_flow_with_github_not_found_error(
        self, client: TestClient
    ) -> None:
        """Test complete flow when GitHub repository or path is not found."""
        with patch("tarsy.config.settings.get_settings") as mock_get_settings:
            test_settings = Mock()
            test_settings.github_token = "valid_token"
            test_settings.runbooks_repo_url = (
                "https://github.com/org/repo/tree/master/nonexistent-path"
            )
            mock_get_settings.return_value = test_settings

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                
                # Simulate 404 not found error
                mock_response = Mock()
                mock_response.status_code = 404
                mock_response.text = "Not Found"
                error = httpx.HTTPStatusError(
                    "Not Found",
                    request=Mock(),
                    response=mock_response
                )
                mock_client.get = AsyncMock(side_effect=error)
                mock_client_class.return_value = mock_client

                response = client.get("/api/v1/runbooks")

        # Should return empty list gracefully
        assert response.status_code == 200
        runbooks = response.json()
        assert runbooks == []

    @pytest.mark.e2e
    def test_complete_flow_filters_non_markdown_files(
        self, client: TestClient
    ) -> None:
        """Test that only markdown files are returned in complete flow."""
        mock_github_contents = [
            {"name": "runbook.md", "type": "file", "path": "runbooks/runbook.md"},
            {"name": "README.txt", "type": "file", "path": "runbooks/README.txt"},
            {"name": "config.yaml", "type": "file", "path": "runbooks/config.yaml"},
            {"name": "script.sh", "type": "file", "path": "runbooks/script.sh"},
            {"name": "guide.md", "type": "file", "path": "runbooks/guide.md"},
        ]

        with patch("tarsy.config.settings.get_settings") as mock_get_settings:
            test_settings = Mock()
            test_settings.github_token = "test_token"
            test_settings.runbooks_repo_url = (
                "https://github.com/org/repo/tree/master/runbooks"
            )
            mock_get_settings.return_value = test_settings

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_response = Mock()
                mock_response.json = lambda: mock_github_contents
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                response = client.get("/api/v1/runbooks")

        assert response.status_code == 200
        runbooks = response.json()
        
        # Only .md files should be returned
        assert len(runbooks) == 2
        assert all(url.endswith(".md") for url in runbooks)
        assert any("runbook.md" in url for url in runbooks)
        assert any("guide.md" in url for url in runbooks)

    @pytest.mark.e2e
    def test_complete_flow_with_network_timeout(self, client: TestClient) -> None:
        """Test complete flow handles network timeouts gracefully."""
        import asyncio

        with patch("tarsy.config.settings.get_settings") as mock_get_settings:
            test_settings = Mock()
            test_settings.github_token = "test_token"
            test_settings.runbooks_repo_url = (
                "https://github.com/org/repo/tree/master/runbooks"
            )
            mock_get_settings.return_value = test_settings

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.get = AsyncMock(side_effect=asyncio.TimeoutError())
                mock_client_class.return_value = mock_client

                response = client.get("/api/v1/runbooks")

        # Should handle timeout gracefully and return empty list
        assert response.status_code == 200
        runbooks = response.json()
        assert runbooks == []

    @pytest.mark.e2e
    def test_complete_flow_with_empty_repository(self, client: TestClient) -> None:
        """Test complete flow when repository contains no markdown files."""
        mock_github_contents = [
            {"name": "README.txt", "type": "file", "path": "runbooks/README.txt"},
            {"name": "config", "type": "dir", "path": "runbooks/config"},
        ]

        with patch("tarsy.config.settings.get_settings") as mock_get_settings:
            test_settings = Mock()
            test_settings.github_token = "test_token"
            test_settings.runbooks_repo_url = (
                "https://github.com/org/repo/tree/master/runbooks"
            )
            mock_get_settings.return_value = test_settings

            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_response = Mock()
                mock_response.json = lambda: mock_github_contents
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_class.return_value = mock_client

                response = client.get("/api/v1/runbooks")

        assert response.status_code == 200
        runbooks = response.json()
        assert runbooks == []

