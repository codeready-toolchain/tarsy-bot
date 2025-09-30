"""
Runbook service for downloading runbooks from GitHub.
"""

from typing import Optional

import httpx

from tarsy.config.settings import Settings
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class RunbookService:
    """Service for handling runbook operations."""

    def __init__(
        self, settings: Settings, http_client: Optional[httpx.AsyncClient] = None
    ) -> None:
        self.settings = settings
        self._owns_client = http_client is None
        self.client = http_client or httpx.AsyncClient()

        # GitHub API headers
        self.headers = {
            "Accept": "application/vnd.github.v3.raw",
            "User-Agent": "TARSy/1.0",
        }

        # Check if GitHub token is missing or a placeholder
        has_valid_token = self.settings.github_token and self.settings.github_token not in [
            "your_github_token_here",
            "your_token",
            "placeholder",
        ]

        # Only add Authorization header if we have a valid (non-placeholder) token
        if has_valid_token:
            self.headers["Authorization"] = f"token {self.settings.github_token}"
        else:
            # Add warning if GitHub token is missing
            from tarsy.config.builtin_config import DEFAULT_RUNBOOK_CONTENT
            from tarsy.models.system_models import WarningCategory
            from tarsy.services.system_warnings_service import get_warnings_service

            logger.warning(
                "No GitHub token configured - using built-in default runbook"
            )

            warnings = get_warnings_service()
            warnings.add_warning(
                WarningCategory.RUNBOOK_SERVICE,
                "Runbook service disabled: GitHub token not configured. Using built-in default runbook.",
                details="Set GITHUB_TOKEN environment variable to enable GitHub runbook integration.",
            )

            self._default_runbook = DEFAULT_RUNBOOK_CONTENT
    
    async def download_runbook(self, url: str) -> str:
        """Download runbook content from GitHub URL."""
        # If no GitHub token, return default runbook
        if hasattr(self, "_default_runbook"):
            logger.debug(
                f"GitHub token not available, using default runbook for: {url}"
            )
            return self._default_runbook

        try:
            # Convert GitHub URL to raw content URL
            raw_url = self._convert_to_raw_url(url)

            # Download the runbook
            response = await self.client.get(raw_url, headers=self.headers)
            response.raise_for_status()

            return response.text

        except httpx.HTTPError as e:
            raise Exception(f"Failed to download runbook from {url}: {str(e)}")
    
    def _convert_to_raw_url(self, github_url: str) -> str:
        """Convert GitHub URL to raw content URL."""
        # Example: https://github.com/user/repo/blob/master/file.md
        # Should become: https://raw.githubusercontent.com/user/repo/refs/heads/master/file.md
        
        if "raw.githubusercontent.com" in github_url:
            return github_url
        
        if "github.com" in github_url:
            # Parse the URL
            parts = github_url.replace("https://github.com/", "").split("/")
            if len(parts) >= 5 and parts[2] == "blob":
                user = parts[0]
                repo = parts[1]
                branch = parts[3]
                file_path = "/".join(parts[4:])
                
                return f"https://raw.githubusercontent.com/{user}/{repo}/refs/heads/{branch}/{file_path}"
        
        # If we can't convert, return as-is and let the request fail
        return github_url
    
    async def close(self) -> None:
        """Close the HTTP client only if we own it."""
        if self._owns_client:
            await self.client.aclose() 