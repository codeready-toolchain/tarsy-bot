"""
Unit tests for RunbooksService.

Tests GitHub repository runbook listing functionality including URL parsing,
API interactions, error handling, and authentication.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from tarsy.config.settings import Settings
from tarsy.services.runbooks_service import RunbooksService


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    settings = Mock(spec=Settings)
    settings.github_token = "test_token_123"
    settings.runbooks_repo_url = "https://github.com/test-org/test-repo/tree/master/runbooks"
    return settings


@pytest.fixture
def runbooks_service(mock_settings: Settings) -> RunbooksService:
    """Create RunbooksService instance for testing."""
    return RunbooksService(mock_settings)


class TestRunbooksServiceInitialization:
    """Test RunbooksService initialization scenarios."""

    @pytest.mark.unit
    def test_initialization_with_all_settings(self) -> None:
        """Test service initializes correctly with all settings provided."""
        settings = Mock(spec=Settings)
        settings.github_token = "token123"
        settings.runbooks_repo_url = "https://github.com/org/repo/tree/main/docs"

        service = RunbooksService(settings)

        assert service.settings == settings
        assert service.github_token == "token123"
        assert service.runbooks_repo_url == "https://github.com/org/repo/tree/main/docs"

    @pytest.mark.unit
    def test_initialization_without_token(self) -> None:
        """Test service initializes correctly without GitHub token."""
        settings = Mock(spec=Settings)
        settings.github_token = None
        settings.runbooks_repo_url = "https://github.com/org/repo/tree/main/docs"

        service = RunbooksService(settings)

        assert service.github_token is None
        assert service.runbooks_repo_url is not None

    @pytest.mark.unit
    def test_initialization_without_repo_url(self) -> None:
        """Test service initializes correctly without runbooks repo URL."""
        settings = Mock(spec=Settings)
        settings.github_token = "token123"
        settings.runbooks_repo_url = None

        service = RunbooksService(settings)

        assert service.github_token is not None
        assert service.runbooks_repo_url is None


class TestURLParsing:
    """Test GitHub URL parsing functionality."""

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "url,expected_org,expected_repo,expected_ref,expected_path",
        [
            (
                "https://github.com/org/repo/tree/master/path",
                "org",
                "repo",
                "master",
                "path",
            ),
            (
                "https://github.com/org/repo/tree/main/docs/runbooks",
                "org",
                "repo",
                "main",
                "docs/runbooks",
            ),
            (
                "https://github.com/codeready-toolchain/sandbox-sre/tree/master/runbooks/ai",
                "codeready-toolchain",
                "sandbox-sre",
                "master",
                "runbooks/ai",
            ),
            (
                "https://github.com/org/repo/tree/feature-branch/path/to/docs",
                "org",
                "repo",
                "feature-branch",
                "path/to/docs",
            ),
            (
                "https://github.com/org/repo/tree/v1.0.0/runbooks",
                "org",
                "repo",
                "v1.0.0",
                "runbooks",
            ),
            # No path after ref
            ("https://github.com/org/repo/tree/master", "org", "repo", "master", ""),
            ("https://github.com/org/repo/tree/main/", "org", "repo", "main", ""),
        ],
    )
    def test_parse_valid_github_urls(
        self,
        runbooks_service: RunbooksService,
        url: str,
        expected_org: str,
        expected_repo: str,
        expected_ref: str,
        expected_path: str,
    ) -> None:
        """Test parsing valid GitHub repository URLs."""
        result = runbooks_service._parse_github_url(url)

        assert result is not None
        assert result["org"] == expected_org
        assert result["repo"] == expected_repo
        assert result["ref"] == expected_ref
        assert result["path"] == expected_path

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "invalid_url",
        [
            "https://github.com/org",  # Incomplete URL
            "https://github.com/org/repo",  # No tree segment
            "https://github.com/org/repo/tree",  # No ref
            "https://gitlab.com/org/repo/tree/master/path",  # Wrong host
            "not-a-url",  # Invalid URL format
            "",  # Empty string
        ],
    )
    def test_parse_invalid_github_urls_returns_none(
        self, runbooks_service: RunbooksService, invalid_url: str
    ) -> None:
        """Test parsing invalid GitHub URLs returns None."""
        result = runbooks_service._parse_github_url(invalid_url)
        assert result is None

    @pytest.mark.unit
    def test_parse_github_url_with_blob_instead_of_tree(
        self, runbooks_service: RunbooksService
    ) -> None:
        """Test parsing URL with 'blob' (file) instead of 'tree' (directory)."""
        url = "https://github.com/org/repo/blob/master/docs/runbook.md"
        result = runbooks_service._parse_github_url(url)

        assert result is not None
        assert result["org"] == "org"
        assert result["repo"] == "repo"
        assert result["ref"] == "master"
        assert result["path"] == "docs/runbook.md"


class TestGitHubAPIInteractions:
    """Test GitHub API interaction functionality."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fetch_github_contents_success(
        self, runbooks_service: RunbooksService
    ) -> None:
        """Test successful GitHub API content fetching."""
        mock_response = [
            {"name": "runbook1.md", "type": "file", "path": "runbooks/runbook1.md"},
            {"name": "runbook2.md", "type": "file", "path": "runbooks/runbook2.md"},
            {"name": "subdir", "type": "dir", "path": "runbooks/subdir"},
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(return_value=Mock(json=lambda: mock_response))
            mock_client_class.return_value = mock_client

            result = await runbooks_service._fetch_github_contents(
                "test-org", "test-repo", "runbooks", "master"
            )

        assert len(result) == 3
        assert result[0]["name"] == "runbook1.md"
        assert result[1]["name"] == "runbook2.md"
        assert result[2]["type"] == "dir"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fetch_github_contents_with_authentication(
        self, runbooks_service: RunbooksService
    ) -> None:
        """Test GitHub API calls include authentication header."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_get = AsyncMock(return_value=Mock(json=lambda: []))
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            await runbooks_service._fetch_github_contents(
                "org", "repo", "path", "master"
            )

            # Verify authentication header was included
            call_args = mock_get.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer test_token_123"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fetch_github_contents_without_token(
        self, mock_settings: Settings
    ) -> None:
        """Test GitHub API calls work without authentication token."""
        mock_settings.github_token = None
        service = RunbooksService(mock_settings)

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_get = AsyncMock(return_value=Mock(json=lambda: []))
            mock_client.get = mock_get
            mock_client_class.return_value = mock_client

            await service._fetch_github_contents("org", "repo", "path", "master")

            # Verify no Authorization header when token is None
            call_args = mock_get.call_args
            headers = call_args.kwargs.get("headers", {})
            assert "Authorization" not in headers

    @pytest.mark.unit
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status_code,expected_log",
        [
            (404, "not found"),
            (401, "authentication failed"),
            (403, "forbidden"),
            (500, "API error"),
        ],
    )
    async def test_fetch_github_contents_error_handling(
        self, runbooks_service: RunbooksService, status_code: int, expected_log: str
    ) -> None:
        """Test GitHub API error handling for various HTTP status codes."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            
            # Create proper HTTPStatusError
            mock_response = Mock()
            mock_response.status_code = status_code
            mock_response.text = f"Error {status_code}"
            error = httpx.HTTPStatusError(
                f"HTTP {status_code}", request=Mock(), response=mock_response
            )
            mock_client.get = AsyncMock(side_effect=error)
            mock_client_class.return_value = mock_client

            result = await runbooks_service._fetch_github_contents(
                "org", "repo", "path", "master"
            )

            assert result == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_fetch_github_contents_network_error(
        self, runbooks_service: RunbooksService
    ) -> None:
        """Test GitHub API handles network errors gracefully."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get = AsyncMock(side_effect=httpx.NetworkError("Connection failed"))
            mock_client_class.return_value = mock_client

            result = await runbooks_service._fetch_github_contents(
                "org", "repo", "path", "master"
            )

            assert result == []


class TestMarkdownFileCollection:
    """Test recursive markdown file collection."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_collect_markdown_files_from_flat_directory(
        self, runbooks_service: RunbooksService
    ) -> None:
        """Test collecting markdown files from a flat directory structure."""
        mock_contents = [
            {"name": "runbook1.md", "type": "file", "path": "runbooks/runbook1.md"},
            {"name": "runbook2.md", "type": "file", "path": "runbooks/runbook2.md"},
            {"name": "README.txt", "type": "file", "path": "runbooks/README.txt"},
        ]

        with patch.object(
            runbooks_service, "_fetch_github_contents", return_value=mock_contents
        ):
            result = await runbooks_service._collect_markdown_files(
                "org", "repo", "runbooks", "master"
            )

        assert len(result) == 2
        assert "https://github.com/org/repo/blob/master/runbooks/runbook1.md" in result
        assert "https://github.com/org/repo/blob/master/runbooks/runbook2.md" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_collect_markdown_files_recursively(
        self, runbooks_service: RunbooksService
    ) -> None:
        """Test recursive collection of markdown files from nested directories."""
        # Mock first level
        first_level = [
            {"name": "root.md", "type": "file", "path": "runbooks/root.md"},
            {"name": "subdir", "type": "dir", "path": "runbooks/subdir"},
        ]
        # Mock subdirectory
        second_level = [
            {"name": "nested.md", "type": "file", "path": "runbooks/subdir/nested.md"},
        ]

        async def mock_fetch(org: str, repo: str, path: str, ref: str) -> list[dict[str, Any]]:
            if path == "runbooks":
                return first_level
            elif path == "runbooks/subdir":
                return second_level
            return []

        with patch.object(runbooks_service, "_fetch_github_contents", side_effect=mock_fetch):
            result = await runbooks_service._collect_markdown_files(
                "org", "repo", "runbooks", "master"
            )

        assert len(result) == 2
        assert "https://github.com/org/repo/blob/master/runbooks/root.md" in result
        assert (
            "https://github.com/org/repo/blob/master/runbooks/subdir/nested.md"
            in result
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_collect_markdown_files_filters_non_markdown(
        self, runbooks_service: RunbooksService
    ) -> None:
        """Test that only .md files are collected."""
        mock_contents = [
            {"name": "valid.md", "type": "file", "path": "runbooks/valid.md"},
            {"name": "README.txt", "type": "file", "path": "runbooks/README.txt"},
            {"name": "config.yaml", "type": "file", "path": "runbooks/config.yaml"},
            {"name": "script.sh", "type": "file", "path": "runbooks/script.sh"},
            {"name": "another.MD", "type": "file", "path": "runbooks/another.MD"},  # Different case
        ]

        with patch.object(
            runbooks_service, "_fetch_github_contents", return_value=mock_contents
        ):
            result = await runbooks_service._collect_markdown_files(
                "org", "repo", "runbooks", "master"
            )

        # Should only include files ending with .md (lowercase)
        assert len(result) == 1
        assert "https://github.com/org/repo/blob/master/runbooks/valid.md" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_collect_markdown_files_empty_directory(
        self, runbooks_service: RunbooksService
    ) -> None:
        """Test collecting from empty directory returns empty list."""
        with patch.object(runbooks_service, "_fetch_github_contents", return_value=[]):
            result = await runbooks_service._collect_markdown_files(
                "org", "repo", "empty", "master"
            )

        assert result == []


class TestGetRunbooks:
    """Test the main get_runbooks public method."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_runbooks_success(self, mock_settings: Settings) -> None:
        """Test successful runbook retrieval."""
        service = RunbooksService(mock_settings)
        
        mock_files = [
            "https://github.com/test-org/test-repo/blob/master/runbooks/r1.md",
            "https://github.com/test-org/test-repo/blob/master/runbooks/r2.md",
        ]

        with patch.object(service, "_collect_markdown_files", return_value=mock_files):
            result = await service.get_runbooks()

        assert len(result) == 2
        assert result == mock_files

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_runbooks_without_repo_url_configured(
        self, mock_settings: Settings
    ) -> None:
        """Test get_runbooks returns empty list when repo URL not configured."""
        mock_settings.runbooks_repo_url = None
        service = RunbooksService(mock_settings)

        result = await service.get_runbooks()

        assert result == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_runbooks_with_invalid_url_format(
        self, mock_settings: Settings
    ) -> None:
        """Test get_runbooks handles invalid URL format gracefully."""
        mock_settings.runbooks_repo_url = "not-a-valid-url"
        service = RunbooksService(mock_settings)

        result = await service.get_runbooks()

        assert result == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_runbooks_handles_github_api_failure(
        self, mock_settings: Settings
    ) -> None:
        """Test get_runbooks handles GitHub API failures gracefully."""
        service = RunbooksService(mock_settings)

        with patch.object(
            service,
            "_collect_markdown_files",
            side_effect=Exception("API Error"),
        ):
            result = await service.get_runbooks()

        assert result == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_runbooks_parses_url_correctly(
        self, mock_settings: Settings
    ) -> None:
        """Test that get_runbooks correctly parses the GitHub URL."""
        service = RunbooksService(mock_settings)

        with patch.object(
            service, "_collect_markdown_files", return_value=[]
        ) as mock_collect:
            await service.get_runbooks()

            # Verify correct parsing
            mock_collect.assert_called_once_with(
                org="test-org", repo="test-repo", path="runbooks", ref="master"
            )

