"""
Application settings and configuration management.
"""

import os
from functools import lru_cache
from typing import Dict, List, Any, Optional

from pydantic import Field
from pydantic_settings import BaseSettings

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    """Application settings."""
    
    # Server Configuration
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    
    # CORS Configuration
    cors_origins_str: str = Field(
        default="http://localhost:3001,http://127.0.0.1:3001",
        alias="cors_origins"
    )
    
    @property
    def cors_origins(self) -> List[str]:
        """Get CORS origins as a list."""
        return [origin.strip() for origin in self.cors_origins_str.split(',') if origin.strip()]
    
    # LLM Provider Configuration
    gemini_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    grok_api_key: str = Field(default="")
    default_llm_provider: str = Field(default="gemini")
    
    # GitHub Configuration
    github_token: Optional[str] = Field(default=None)
    
    # MCP Server Configuration
    kubernetes_mcp_url: str = Field(default="http://localhost:8080")
    
    # LLM Providers Configuration
    llm_providers: Dict = Field(default={
        "gemini": {
            "model": "gemini-2.5-pro",
            "api_key_env": "GEMINI_API_KEY",
            "type": "gemini"
        },
        "openai": {
            "model": "gpt-4",
            "api_key_env": "OPENAI_API_KEY", 
            "type": "openai"
        },
        "grok": {
            "model": "grok-3",
            "api_key_env": "GROK_API_KEY",
            "type": "grok"
        }
    })
    
    # MCP Servers Configuration
    mcp_servers: Dict[str, Any] = Field(
        default={
            "kubernetes": {
                "type": "kubernetes",
                "enabled": True,
                "command": "npx",
                "args": ["-y", "kubernetes-mcp-server@latest"]
            }
        },
        description="MCP server configurations"
    )
    
    # Supported Alert Types
    supported_alerts: List[str] = Field(default=[
        "Namespace is stuck in Terminating"
    ])
    
    # Alert Type to Runbook Mapping
    alert_runbook_mapping: Dict = Field(default={
        "Namespace is stuck in Terminating": {
            "default_runbook": "https://github.com/alexeykazakov/runbooks/blob/master/namespace-terminating.md",
            "mcp_servers": ["kubernetes"]
        }
    })
    
    # Alert Processing Configuration
    max_llm_mcp_iterations: int = Field(
        default=5,
        description="Maximum number of LLM->MCP iterative loops for multi-step runbook processing"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        
    def get_llm_config(self, provider: str) -> Dict:
        """Get LLM configuration for a specific provider."""
        if provider not in self.llm_providers:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        
        config = self.llm_providers[provider].copy()
        
        # Get API key from the corresponding field
        if provider == "gemini":
            config["api_key"] = self.gemini_api_key
        elif provider == "openai":
            config["api_key"] = self.openai_api_key
        elif provider == "grok":
            config["api_key"] = self.grok_api_key
        else:
            config["api_key"] = ""
        
        return config
    
    def get_mcp_config(self, server: str) -> Dict:
        """Get MCP server configuration."""
        if server not in self.mcp_servers:
            raise ValueError(f"Unsupported MCP server: {server}")
        
        config = self.mcp_servers[server].copy()
        
        # Get URL from environment
        url_env = config.get("url_env")
        if url_env:
            config["url"] = getattr(self, url_env.lower(), "")
        
        return config


@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings() 