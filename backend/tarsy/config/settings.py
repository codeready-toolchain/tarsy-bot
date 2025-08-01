"""
Application settings and configuration management.
"""

import os
import sys
from functools import lru_cache
from typing import Dict, List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


def is_testing() -> bool:
    """Check if we're running in a test environment."""
    return (
        "pytest" in os.environ.get("_", "") or
        "PYTEST_CURRENT_TEST" in os.environ or
        os.environ.get("TESTING", "").lower() == "true" or
        "test" in sys.argv[0].lower() if len(sys.argv) > 0 else False
    )


class Settings(BaseSettings):
    """Application settings."""
    
    # Server Configuration
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    
    # CORS Configuration
    cors_origins_str: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001",
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
    
    # LLM Providers Configuration
    llm_providers: Dict = Field(default={
        "gemini": {
            "model": "gemini-2.5-pro",
            "api_key_env": "GEMINI_API_KEY",
            "type": "gemini"
        },
        "openai": {
            "model": "gpt-4-1106-preview",
            "api_key_env": "OPENAI_API_KEY", 
            "type": "openai"
        },
        "grok": {
            "model": "grok-3",
            "api_key_env": "GROK_API_KEY",
            "type": "grok"
        }
    })
    
    # Alert Processing Configuration
    max_llm_mcp_iterations: int = Field(
        default=10,
        description="Maximum number of LLM->MCP iterative loops for multi-step runbook processing"
    )
    max_total_tool_calls: int = Field(
        default=20,
        description="Maximum total tool calls per alert across all iterations"
    )
    max_data_points: int = Field(
        default=20,
        description="Maximum data points before stopping processing (when combined with min iterations)"
    )
    
    # History Service Configuration
    history_database_url: str = Field(
        default="",
        description="Database connection string for alert processing history"
    )
    history_enabled: bool = Field(
        default=True,
        description="Enable/disable history capture for alert processing"
    )
    history_retention_days: int = Field(
        default=90,
        description="Number of days to retain alert processing history data"
    )
    
    # Concurrency Control Configuration
    max_concurrent_alerts: int = Field(
        default=5,
        description="Maximum number of alerts that can be processed concurrently"
    )
    alert_queue_timeout: int = Field(
        default=300,
        description="Timeout in seconds for alerts waiting in queue"
    )
    
    # Agent Configuration
    agent_config_path: str = Field(
        default="./config/agents.yaml",
        description="Path to agent and MCP server configuration file"
    )
    
    # Template Variable Defaults
    # These provide default values for template variables if not set in environment
    kubeconfig_default: str = Field(
        default="~/.kube/config",
        description="Default kubeconfig path for Kubernetes MCP server"
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set default database URL based on environment if not explicitly provided
        if not self.history_database_url:
            if is_testing():
                # Use in-memory database for tests by default
                self.history_database_url = "sqlite:///:memory:"
            else:
                # Use file database for dev/production
                self.history_database_url = "sqlite:///history.db"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow extra fields to be ignored for backward compatibility
        extra = "ignore"
        
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
    
    def get_template_default(self, var_name: str) -> Optional[str]:
        """
        Get default value for a template variable.
        
        Args:
            var_name: Template variable name (e.g., 'KUBECONFIG')
            
        Returns:
            Default value if available, None otherwise
        """
        # Convert template variable name to settings attribute name
        # KUBECONFIG -> kubeconfig_default
        # PROMETHEUS_URL -> prometheus_url_default
        default_attr = f"{var_name.lower()}_default"
        return getattr(self, default_attr, None)
    

@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings() 