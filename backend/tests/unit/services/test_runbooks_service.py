"""
Unit tests for RunbooksService.

Tests GitHub repository runbook listing functionality including URL parsing,
API interactions, error handling, and authentication.
"""

from typing import Any
from unittest.mock import Mock, patch

import pytest
from github import GithubException

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
    with patch("tarsy.services.runbooks_service.Github"):
        return RunbooksService(mock_settings)


class TestRunbooksServiceInitialization:
    """Test RunbooksService initialization scenarios."""

    @pytest.mark.unit
    def test_initialization_with_all_settings(self) -> None:
        """Test service initializes correctly with all settings provided."""
        settings = Mock(spec=Settings)
        settings.github_token = "token123"
        settings.runbooks_repo_url = "https://github.com/org/repo/tree/main/docs"

        with patch("tarsy.services.runbooks_service.Github") as mock_github:
            with patch("tarsy.services.runbooks_service.Auth") as mock_auth:
                service = RunbooksService(settings)

                assert service.settings == settings
                assert service.github_token == "token123"
                assert service.runbooks_repo_url == "https://github.com/org/repo/tree/main/docs"
                # Verify Auth.Token was called with token
                mock_auth.Token.assert_called_once_with("token123")
                # Verify Github was initialized with auth
                mock_github.assert_called_once()

    @pytest.mark.unit
    def test_initialization_without_token(self) -> None:
        """Test service initializes correctly without GitHub token."""
        settings = Mock(spec=Settings)
        settings.github_token = None
        settings.runbooks_repo_url = "https://github.com/org/repo/tree/main/docs"

        with patch("tarsy.services.runbooks_service.Github") as mock_github:
            service = RunbooksService(settings)

            assert service.github_token is None
            assert service.runbooks_repo_url is not None
            # Verify Github was initialized without auth
            mock_github.assert_called_once_with()

    @pytest.mark.unit
    def test_initialization_without_repo_url(self) -> None:
        """Test service initializes correctly without runbooks repo URL."""
        settings = Mock(spec=Settings)
        settings.github_token = "token123"
        settings.runbooks_repo_url = None

        with patch("tarsy.services.runbooks_service.Github"):
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
            # Refs with slashes - PyGithub handles these natively
            (
                "https://github.com/org/repo/tree/feature/foo/path",
                "org",
                "repo",
                "feature",
                "foo/path",
            ),
            (
                "https://github.com/org/repo/tree/release/v1.0/docs",
                "org",
                "repo",
                "release",
                "v1.0/docs",
            ),
            # No path after ref
            ("https://github.com/org/repo/tree/master", "org", "repo", "master", ""),
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
    """Test GitHub API interaction functionality using PyGithub."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_collect_markdown_files_success(
        self, runbooks_service: RunbooksService
    ) -> None:
        """Test successful GitHub API content fetching with PyGithub."""
        # Mock PyGithub objects
        mock_file1 = Mock()
        mock_file1.type = "file"
        mock_file1.name = "runbook1.md"
        mock_file1.path = "runbooks/runbook1.md"

        mock_file2 = Mock()
        mock_file2.type = "file"
        mock_file2.name = "runbook2.md"
        mock_file2.path = "runbooks/runbook2.md"

        mock_dir = Mock()
        mock_dir.type = "dir"
        mock_dir.name = "subdir"
        mock_dir.path = "runbooks/subdir"

        mock_repo = Mock()
        mock_repo.get_contents = Mock(return_value=[mock_file1, mock_file2, mock_dir])

        runbooks_service.github.get_repo = Mock(return_value=mock_repo)

        # Mock the recursive call for subdirectory
        with patch.object(
            runbooks_service,
            "_collect_markdown_files",
            side_effect=lambda org, repo, path, ref: (
                ["https://github.com/test-org/test-repo/blob/master/runbooks/runbook1.md",
                 "https://github.com/test-org/test-repo/blob/master/runbooks/runbook2.md"]
                if path == "runbooks"
                else []
            ),
        ):
            result = await runbooks_service._collect_markdown_files(
                "test-org", "test-repo", "runbooks", "master"
            )

        assert len(result) == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_collect_markdown_files_with_authentication(
        self, mock_settings: Settings
    ) -> None:
        """Test GitHub API calls use authentication when token is provided."""
        with patch("tarsy.services.runbooks_service.Github") as mock_github_class:
            with patch("tarsy.services.runbooks_service.Auth") as mock_auth:
                service = RunbooksService(mock_settings)

                # Verify Auth.Token was called with the token
                mock_auth.Token.assert_called_once_with("test_token_123")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_collect_markdown_files_404_error(
        self, runbooks_service: RunbooksService
    ) -> None:
        """Test GitHub API handles 404 errors gracefully."""
        mock_repo = Mock()
        error_data = {"message": "Not Found"}
        mock_repo.get_contents = Mock(
            side_effect=GithubException(404, error_data, headers={})
        )
        runbooks_service.github.get_repo = Mock(return_value=mock_repo)

        result = await runbooks_service._collect_markdown_files(
            "org", "repo", "path", "master"
        )

        assert result == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_collect_markdown_files_401_error(
        self, runbooks_service: RunbooksService
    ) -> None:
        """Test GitHub API handles authentication errors."""
        mock_repo = Mock()
        error_data = {"message": "Bad credentials"}
        mock_repo.get_contents = Mock(
            side_effect=GithubException(401, error_data, headers={})
        )
        runbooks_service.github.get_repo = Mock(return_value=mock_repo)

        result = await runbooks_service._collect_markdown_files(
            "org", "repo", "path", "master"
        )

        assert result == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_collect_markdown_files_generic_error(
        self, runbooks_service: RunbooksService
    ) -> None:
        """Test GitHub API handles generic errors gracefully."""
        mock_repo = Mock()
        mock_repo.get_contents = Mock(side_effect=Exception("Network error"))
        runbooks_service.github.get_repo = Mock(return_value=mock_repo)

        result = await runbooks_service._collect_markdown_files(
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
        mock_file1 = Mock()
        mock_file1.type = "file"
        mock_file1.name = "runbook1.md"
        mock_file1.path = "runbooks/runbook1.md"

        mock_file2 = Mock()
        mock_file2.type = "file"
        mock_file2.name = "runbook2.md"
        mock_file2.path = "runbooks/runbook2.md"

        mock_file3 = Mock()
        mock_file3.type = "file"
        mock_file3.name = "README.txt"
        mock_file3.path = "runbooks/README.txt"

        mock_repo = Mock()
        mock_repo.get_contents = Mock(return_value=[mock_file1, mock_file2, mock_file3])
        runbooks_service.github.get_repo = Mock(return_value=mock_repo)

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
        mock_file = Mock()
        mock_file.type = "file"
        mock_file.name = "root.md"
        mock_file.path = "runbooks/root.md"

        mock_dir = Mock()
        mock_dir.type = "dir"
        mock_dir.name = "subdir"
        mock_dir.path = "runbooks/subdir"

        # Mock nested file
        mock_nested_file = Mock()
        mock_nested_file.type = "file"
        mock_nested_file.name = "nested.md"
        mock_nested_file.path = "runbooks/subdir/nested.md"

        mock_repo = Mock()

        def mock_get_contents(path: str, ref: str) -> list[Any]:
            if path == "runbooks":
                return [mock_file, mock_dir]
            elif path == "runbooks/subdir":
                return [mock_nested_file]
            return []

        mock_repo.get_contents = mock_get_contents
        runbooks_service.github.get_repo = Mock(return_value=mock_repo)

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
        mock_md = Mock()
        mock_md.type = "file"
        mock_md.name = "valid.md"
        mock_md.path = "runbooks/valid.md"

        mock_txt = Mock()
        mock_txt.type = "file"
        mock_txt.name = "README.txt"
        mock_txt.path = "runbooks/README.txt"

        mock_yaml = Mock()
        mock_yaml.type = "file"
        mock_yaml.name = "config.yaml"
        mock_yaml.path = "runbooks/config.yaml"

        mock_repo = Mock()
        mock_repo.get_contents = Mock(return_value=[mock_md, mock_txt, mock_yaml])
        runbooks_service.github.get_repo = Mock(return_value=mock_repo)

        result = await runbooks_service._collect_markdown_files(
            "org", "repo", "runbooks", "master"
        )

        assert len(result) == 1
        assert "https://github.com/org/repo/blob/master/runbooks/valid.md" in result

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_collect_markdown_files_empty_directory(
        self, runbooks_service: RunbooksService
    ) -> None:
        """Test collecting from empty directory returns empty list."""
        mock_repo = Mock()
        mock_repo.get_contents = Mock(return_value=[])
        runbooks_service.github.get_repo = Mock(return_value=mock_repo)

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
        with patch("tarsy.services.runbooks_service.Github"):
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
        
        with patch("tarsy.services.runbooks_service.Github"):
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
        
        with patch("tarsy.services.runbooks_service.Github"):
            service = RunbooksService(mock_settings)
            result = await service.get_runbooks()

        assert result == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_runbooks_handles_github_api_failure(
        self, mock_settings: Settings
    ) -> None:
        """Test get_runbooks handles GitHub API failures gracefully."""
        with patch("tarsy.services.runbooks_service.Github"):
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
        with patch("tarsy.services.runbooks_service.Github"):
            service = RunbooksService(mock_settings)

            with patch.object(
                service, "_collect_markdown_files", return_value=[]
            ) as mock_collect:
                await service.get_runbooks()

                # Verify correct parsing
                mock_collect.assert_called_once_with(
                    org="test-org", repo="test-repo", path="runbooks", ref="master"
                )
