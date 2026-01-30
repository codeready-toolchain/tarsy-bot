"""
E2E tests for runbooks functionality.

Tests the complete runbooks flow from API endpoint through service layer
to GitHub API integration.
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from github import GithubException

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
        # Mock PyGithub file objects
        mock_file1 = Mock()
        mock_file1.type = "file"
        mock_file1.name = "namespace-terminating.md"
        mock_file1.path = "runbooks/ai/namespace-terminating.md"

        mock_file2 = Mock()
        mock_file2.type = "file"
        mock_file2.name = "pod-crashloop.md"
        mock_file2.path = "runbooks/ai/pod-crashloop.md"

        mock_dir = Mock()
        mock_dir.type = "dir"
        mock_dir.name = "subdirectory"
        mock_dir.path = "runbooks/ai/subdirectory"

        mock_subfile = Mock()
        mock_subfile.type = "file"
        mock_subfile.name = "advanced-debugging.md"
        mock_subfile.path = "runbooks/ai/subdirectory/advanced-debugging.md"

        # Mock GitHub repository
        def mock_get_contents(path: str, ref: str) -> list[Mock]:
            """Mock get_contents to return different results based on path."""
            if "subdirectory" in path:
                return [mock_subfile]
            return [mock_file1, mock_file2, mock_dir]

        mock_repo = Mock()
        mock_repo.get_contents = mock_get_contents

        # Mock Github client
        mock_github = Mock()
        mock_github.get_repo = Mock(return_value=mock_repo)

        # Mock settings for this test
        with patch("tarsy.config.settings.get_settings") as mock_get_settings:
            test_settings = Mock()
            test_settings.github_token = "test_e2e_token"
            test_settings.runbooks_repo_url = (
                "https://github.com/codeready-toolchain/sandbox-sre/tree/master/runbooks/ai"
            )
            mock_get_settings.return_value = test_settings

            with patch("tarsy.services.runbooks_service.Github") as mock_github_class:
                with patch("tarsy.services.runbooks_service.Auth"):
                    mock_github_class.return_value = mock_github

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
        # Mock GitHub repository that raises 401 error
        mock_repo = Mock()
        error_data = {"message": "Bad credentials"}
        mock_repo.get_contents = Mock(
            side_effect=GithubException(401, error_data, headers={})
        )

        # Mock Github client
        mock_github = Mock()
        mock_github.get_repo = Mock(return_value=mock_repo)

        with patch("tarsy.config.settings.get_settings") as mock_get_settings:
            test_settings = Mock()
            test_settings.github_token = "invalid_token"
            test_settings.runbooks_repo_url = (
                "https://github.com/private-org/private-repo/tree/master/runbooks"
            )
            mock_get_settings.return_value = test_settings

            with patch("tarsy.services.runbooks_service.Github") as mock_github_class:
                with patch("tarsy.services.runbooks_service.Auth"):
                    mock_github_class.return_value = mock_github

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
        # Mock GitHub repository that raises 404 error
        mock_repo = Mock()
        error_data = {"message": "Not Found"}
        mock_repo.get_contents = Mock(
            side_effect=GithubException(404, error_data, headers={})
        )

        # Mock Github client
        mock_github = Mock()
        mock_github.get_repo = Mock(return_value=mock_repo)

        with patch("tarsy.config.settings.get_settings") as mock_get_settings:
            test_settings = Mock()
            test_settings.github_token = "valid_token"
            test_settings.runbooks_repo_url = (
                "https://github.com/org/repo/tree/master/nonexistent-path"
            )
            mock_get_settings.return_value = test_settings

            with patch("tarsy.services.runbooks_service.Github") as mock_github_class:
                with patch("tarsy.services.runbooks_service.Auth"):
                    mock_github_class.return_value = mock_github

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
        # Mock PyGithub file objects
        mock_md1 = Mock()
        mock_md1.type = "file"
        mock_md1.name = "runbook.md"
        mock_md1.path = "runbooks/runbook.md"

        mock_txt = Mock()
        mock_txt.type = "file"
        mock_txt.name = "README.txt"
        mock_txt.path = "runbooks/README.txt"

        mock_yaml = Mock()
        mock_yaml.type = "file"
        mock_yaml.name = "config.yaml"
        mock_yaml.path = "runbooks/config.yaml"

        mock_sh = Mock()
        mock_sh.type = "file"
        mock_sh.name = "script.sh"
        mock_sh.path = "runbooks/script.sh"

        mock_md2 = Mock()
        mock_md2.type = "file"
        mock_md2.name = "guide.md"
        mock_md2.path = "runbooks/guide.md"

        # Mock GitHub repository
        mock_repo = Mock()
        mock_repo.get_contents = Mock(
            return_value=[mock_md1, mock_txt, mock_yaml, mock_sh, mock_md2]
        )

        # Mock Github client
        mock_github = Mock()
        mock_github.get_repo = Mock(return_value=mock_repo)

        with patch("tarsy.config.settings.get_settings") as mock_get_settings:
            test_settings = Mock()
            test_settings.github_token = "test_token"
            test_settings.slack_bot_token = None
            test_settings.slack_channel = None
            test_settings.runbooks_repo_url = (
                "https://github.com/org/repo/tree/master/runbooks"
            )
            mock_get_settings.return_value = test_settings

            with patch("tarsy.services.runbooks_service.Github") as mock_github_class:
                with patch("tarsy.services.runbooks_service.Auth"):
                    mock_github_class.return_value = mock_github

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
        # Mock GitHub repository that raises timeout error
        mock_repo = Mock()
        mock_repo.get_contents = Mock(side_effect=Exception("Network timeout"))

        # Mock Github client
        mock_github = Mock()
        mock_github.get_repo = Mock(return_value=mock_repo)

        with patch("tarsy.config.settings.get_settings") as mock_get_settings:
            test_settings = Mock()
            test_settings.github_token = "test_token"
            test_settings.slack_bot_token = None
            test_settings.slack_channel = None
            test_settings.runbooks_repo_url = (
                "https://github.com/org/repo/tree/master/runbooks"
            )
            mock_get_settings.return_value = test_settings

            with patch("tarsy.services.runbooks_service.Github") as mock_github_class:
                with patch("tarsy.services.runbooks_service.Auth"):
                    mock_github_class.return_value = mock_github

                    response = client.get("/api/v1/runbooks")

        # Should handle timeout gracefully and return empty list
        assert response.status_code == 200
        runbooks = response.json()
        assert runbooks == []

    @pytest.mark.e2e
    def test_complete_flow_with_empty_repository(self, client: TestClient) -> None:
        """Test complete flow when repository contains no markdown files."""
        # Mock PyGithub file objects (no markdown files)
        mock_txt = Mock()
        mock_txt.type = "file"
        mock_txt.name = "README.txt"
        mock_txt.path = "runbooks/README.txt"

        mock_dir = Mock()
        mock_dir.type = "dir"
        mock_dir.name = "config"
        mock_dir.path = "runbooks/config"

        # Mock GitHub repository
        mock_repo = Mock()
        mock_repo.get_contents = Mock(return_value=[mock_txt, mock_dir])

        # Mock Github client
        mock_github = Mock()
        mock_github.get_repo = Mock(return_value=mock_repo)

        with patch("tarsy.config.settings.get_settings") as mock_get_settings:
            test_settings = Mock()
            test_settings.github_token = "test_token"
            test_settings.slack_bot_token = None
            test_settings.slack_channel = None
            test_settings.runbooks_repo_url = (
                "https://github.com/org/repo/tree/master/runbooks"
            )
            mock_get_settings.return_value = test_settings

            with patch("tarsy.services.runbooks_service.Github") as mock_github_class:
                with patch("tarsy.services.runbooks_service.Auth"):
                    mock_github_class.return_value = mock_github

                    response = client.get("/api/v1/runbooks")

        assert response.status_code == 200
        runbooks = response.json()
        assert runbooks == []

