"""
Runbooks Service

Fetches and manages runbook URLs from GitHub repositories.
Supports both public and private repositories (with authentication).
"""

import asyncio
from typing import Optional
from urllib.parse import urlparse

from github import Auth, Github, GithubException

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

        # Initialize PyGithub client
        if self.github_token:
            auth = Auth.Token(self.github_token)
            self.github = Github(auth=auth)
        else:
            self.github = Github()

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

            # Split path: /org/repo/tree|blob/ref/path...
            parts = parsed.path.strip("/").split("/")
            
            if len(parts) < 4:
                logger.error(f"GitHub URL doesn't have enough segments: {url}")
                return None

            org = parts[0]
            repo = parts[1]
            tree_or_blob = parts[2]  # tree or blob
            
            if tree_or_blob not in ("tree", "blob"):
                logger.error(f"Invalid GitHub URL type (expected tree/blob): {url}")
                return None

            # Everything after tree/blob is ref + optional path
            # PyGithub will handle the ref resolution, so we just extract it
            ref = parts[3]
            path = "/".join(parts[4:]) if len(parts) > 4 else ""

            return {
                "org": org,
                "repo": repo,
                "ref": ref,
                "path": path,
            }
        except Exception as e:
            logger.error(f"Failed to parse GitHub URL {url}: {e}")
            return None

    async def _collect_markdown_files(
        self, org: str, repo: str, path: str, ref: str
    ) -> list[str]:
        """
        Recursively collect all .md files from a GitHub directory using PyGithub.

        Args:
            org: GitHub organization or user
            repo: Repository name
            path: Path within the repository
            ref: Branch or tag reference

        Returns:
            List of full GitHub URLs to markdown files
        """
        markdown_urls: list[str] = []
        
        try:
            # Get repository (run in thread to avoid blocking event loop)
            repo_full_name = f"{org}/{repo}"
            github_repo = await asyncio.to_thread(self.github.get_repo, repo_full_name)
            
            # Get contents at path (run in thread to avoid blocking event loop)
            contents = await asyncio.to_thread(github_repo.get_contents, path, ref=ref)
            
            # Handle both single file and list of contents
            if not isinstance(contents, list):
                contents = [contents]
            
            for content in contents:
                if content.type == "file" and content.name.endswith(".md"):
                    # Construct full GitHub URL for the file
                    file_url = f"https://github.com/{org}/{repo}/blob/{ref}/{content.path}"
                    markdown_urls.append(file_url)
                    logger.debug(f"Found runbook: {file_url}")
                    
                elif content.type == "dir":
                    # Recursively process subdirectories
                    logger.debug(f"Exploring subdirectory: {content.path}")
                    subdir_urls = await self._collect_markdown_files(
                        org, repo, content.path, ref
                    )
                    markdown_urls.extend(subdir_urls)
                    
        except GithubException as e:
            if e.status == 404:
                logger.warning(
                    f"GitHub path not found: {org}/{repo}/{path} (ref: {ref})"
                )
            elif e.status == 401:
                logger.error("GitHub authentication failed - check github_token")
            else:
                logger.error(f"GitHub API error {e.status}: {e.data}")
        except Exception as e:
            logger.error(f"Failed to fetch GitHub contents: {e}")
            
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
