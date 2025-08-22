"""
Runbook service for downloading runbooks from GitHub.
"""

from typing import Optional
import httpx

from tarsy.config.settings import Settings


class RunbookService:
    """Service for handling runbook operations."""
    
    def __init__(self, settings: Settings, http_client: Optional[httpx.AsyncClient] = None):
        self.settings = settings
        self._owns_client = http_client is None
        self.client = http_client or httpx.AsyncClient()
        
        # GitHub API headers
        self.headers = {
            "Accept": "application/vnd.github.v3.raw",
            "User-Agent": "Tarsy-bot/1.0"
        }
        
        # Only add Authorization header if we have a valid (non-placeholder) token
        if (self.settings.github_token and 
            self.settings.github_token not in ["your_github_token_here", "your_token", "placeholder"]):
            self.headers["Authorization"] = f"token {self.settings.github_token}"
    
    async def download_runbook(self, url: str) -> str:
        """Download runbook content from GitHub URL."""
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
    
    async def close(self):
        """Close the HTTP client only if we own it."""
        if self._owns_client:
            await self.client.aclose() 