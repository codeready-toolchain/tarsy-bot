"""
Runbooks Service

Fetches and manages runbook URLs from GitHub repositories.
Supports both public and private repositories (with authentication).
"""

import re
from typing import Optional
from urllib.parse import urlparse

import httpx

from tarsy.config.settings import Settings
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class RunbooksService:
    """Service for fetching runbook URLs from GitHub repositories."""

    def __init__(self, settings: Settings) -> None:
        """
        Initialize the RunbooksService.

        Args:
            settings: Application settings containing GitHub configuration
        """
        self.settings = settings
        self.github_token = settings.github_token
        self.runbooks_repo_url = settings.runbooks_repo_url

    def _parse_github_url(self, url: str) -> Optional[dict[str, str]]:
        """
        Parse a GitHub repository URL to extract components.

        Supports formats:
        - https://github.com/org/repo/tree/branch/path
        - https://github.com/org/repo/blob/branch/path/file.md

        Args:
            url: GitHub repository URL

        Returns:
            Dictionary with org, repo, ref, and path, or None if parsing fails
        """
        try:
            parsed = urlparse(url)
            if parsed.hostname != "github.com":
                logger.error(f"Invalid GitHub URL hostname: {parsed.hostname}")
                return None

            # Pattern: /org/repo/tree|blob/ref/path...
            # Example: /codeready-toolchain/sandbox-sre/tree/master/runbooks/ai
            pattern = r"^/([^/]+)/([^/]+)/(tree|blob)/([^/]+)(/(.*))?$"
            match = re.match(pattern, parsed.path)

            if not match:
                logger.error(f"GitHub URL doesn't match expected pattern: {url}")
                return None

            org = match.group(1)
            repo = match.group(2)
            ref = match.group(4)
            path = match.group(6) or ""

            return {
                "org": org,
                "repo": repo,
                "ref": ref,
                "path": path,
            }
        except Exception as e:
            logger.error(f"Failed to parse GitHub URL {url}: {e}")
            return None

    async def _fetch_github_contents(
        self, org: str, repo: str, path: str, ref: str
    ) -> list[dict]:
        """
        Fetch contents from GitHub repository using the API.

        Args:
            org: GitHub organization or user
            repo: Repository name
            path: Path within the repository
            ref: Branch or tag reference

        Returns:
            List of content items from GitHub API
        """
        api_url = f"https://api.github.com/repos/{org}/{repo}/contents/{path}"
        params = {"ref": ref}

        headers = {
            "Accept": "application/vnd.github.v3+json",
        }

        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(api_url, params=params, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(
                    f"GitHub path not found: {org}/{repo}/{path} (ref: {ref})"
                )
            elif e.response.status_code == 401:
                logger.error("GitHub authentication failed - check github_token")
            else:
                logger.error(
                    f"GitHub API error {e.response.status_code}: {e.response.text}"
                )
            return []
        except Exception as e:
            logger.error(f"Failed to fetch GitHub contents: {e}")
            return []

    async def _collect_markdown_files(
        self, org: str, repo: str, path: str, ref: str
    ) -> list[str]:
        """
        Recursively collect all .md files from a GitHub directory.

        Args:
            org: GitHub organization or user
            repo: Repository name
            path: Path within the repository
            ref: Branch or tag reference

        Returns:
            List of full GitHub URLs to markdown files
        """
        markdown_urls: list[str] = []
        contents = await self._fetch_github_contents(org, repo, path, ref)

        for item in contents:
            item_type = item.get("type")
            item_name = item.get("name", "")
            item_path = item.get("path", "")

            if item_type == "file" and item_name.endswith(".md"):
                # Construct full GitHub URL for the file
                file_url = f"https://github.com/{org}/{repo}/blob/{ref}/{item_path}"
                markdown_urls.append(file_url)
                logger.debug(f"Found runbook: {file_url}")

            elif item_type == "dir":
                # Recursively process subdirectories
                logger.debug(f"Exploring subdirectory: {item_path}")
                subdir_urls = await self._collect_markdown_files(
                    org, repo, item_path, ref
                )
                markdown_urls.extend(subdir_urls)

        return markdown_urls

    async def get_runbooks(self) -> list[str]:
        """
        Get list of runbook URLs from configured GitHub repository.

        Returns:
            List of full GitHub URLs to runbook markdown files.
            Returns empty list if:
            - runbooks_repo_url is not configured
            - GitHub API request fails
            - Repository is not accessible
        """
        if not self.runbooks_repo_url:
            logger.info("runbooks_repo_url not configured, returning empty list")
            return []

        logger.info(f"Fetching runbooks from: {self.runbooks_repo_url}")

        # Parse the GitHub URL
        parsed = self._parse_github_url(self.runbooks_repo_url)
        if not parsed:
            logger.error(f"Invalid runbooks_repo_url: {self.runbooks_repo_url}")
            return []

        # Fetch markdown files recursively
        try:
            runbook_urls = await self._collect_markdown_files(
                org=parsed["org"],
                repo=parsed["repo"],
                path=parsed["path"],
                ref=parsed["ref"],
            )

            logger.info(f"Found {len(runbook_urls)} runbook(s)")
            return runbook_urls

        except Exception as e:
            logger.error(f"Failed to fetch runbooks: {e}", exc_info=True)
            return []

