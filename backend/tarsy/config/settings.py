"""
Application settings and configuration management.
"""

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from tarsy.config.builtin_config import get_builtin_llm_providers
from tarsy.models.llm_models import LLMProviderConfig


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
    google_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    xai_api_key: str = Field(default="")
    anthropic_api_key: str = Field(default="")
    llm_provider: str = Field(default="google-default")
    disable_ssl_verification: bool = Field(default=False, description="Disable SSL certificate verification for LLM API calls (use with caution)")
    
    # LLM Configuration File Path
    llm_config_path: str = Field(default="../config/llm_providers.yaml", description="Path to external LLM providers configuration file")
    
    # GitHub Configuration
    github_token: Optional[str] = Field(default=None)
    
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
        default="../config/agents.yaml",
        description="Path to agent and MCP server configuration file"
    )
    
    # Template Variable Defaults
    # These provide default values for template variables if not set in environment
    kubeconfig_default: str = Field(
        default_factory=lambda: os.path.expanduser("~/.kube/config"),
        description="Default kubeconfig path for Kubernetes MCP server (tilde expanded)"
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
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Allow extra fields to be ignored for backward compatibility
        extra="ignore"
    )
        
    def get_llm_config(self, provider: str) -> LLMProviderConfig:
        """Get LLM configuration for a specific provider."""
        if provider not in self.llm_providers:
            available = list(self.llm_providers.keys())
            raise ValueError(f"Unsupported LLM provider: {provider}. Available: {available}")
        
        base_config = self.llm_providers[provider]
        
        # Get API key based on provider type (not provider name)
        provider_type = base_config.type  # Type-safe field access
        
        if provider_type == "google":
            api_key = self.google_api_key
        elif provider_type == "openai":
            api_key = self.openai_api_key
        elif provider_type == "xai":
            api_key = self.xai_api_key
        elif provider_type == "anthropic":
            api_key = self.anthropic_api_key
        else:
            api_key = ""
        
        # Create new config instance with runtime fields
        return base_config.model_copy(update={
            "api_key": api_key,
            "disable_ssl_verification": self.disable_ssl_verification
        })
    
    @property
    def llm_providers(self) -> Dict[str, LLMProviderConfig]:
        """Get merged LLM providers configuration (built-in defaults + YAML overrides)."""
        try:
            # Start with built-in defaults from builtin_config
            merged_providers = get_builtin_llm_providers()
            
            # Load and merge YAML if file exists
            yaml_providers = self._load_yaml_providers()
            if yaml_providers:
                merged_providers.update(yaml_providers)
            
            return merged_providers
        except Exception as e:
            # Log error and fall back to built-in defaults
            from tarsy.utils.logger import get_module_logger
            logger = get_module_logger(__name__)
            logger.error(f"Failed to load LLM providers configuration: {e}")
            return get_builtin_llm_providers()
    
    def _load_yaml_providers(self) -> Optional[Dict[str, LLMProviderConfig]]:
        """Load LLM providers from YAML configuration file."""
        try:
            config_path = Path(self.llm_config_path)
            if not config_path.exists():
                return None
            
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f)
                
            if not yaml_config or 'llm_providers' not in yaml_config:
                return None
            
            providers = yaml_config['llm_providers']
            
            # Validate YAML providers using Pydantic
            validated_providers: Dict[str, LLMProviderConfig] = {}
            for provider_name, config_dict in providers.items():
                try:
                    # Validate using Pydantic BaseModel
                    config = LLMProviderConfig.model_validate(config_dict)
                    validated_providers[provider_name] = config
                except Exception as e:
                    from tarsy.utils.logger import get_module_logger
                    logger = get_module_logger(__name__)
                    logger.error(f"Invalid LLM provider config '{provider_name}': {e}")
                    # Skip invalid configs instead of failing completely
                    continue
            
            return validated_providers
            
        except yaml.YAMLError as e:
            from tarsy.utils.logger import get_module_logger
            logger = get_module_logger(__name__)
            logger.error(f"YAML parsing error in {self.llm_config_path}: {e}")
            return None
        except Exception as e:
            from tarsy.utils.logger import get_module_logger
            logger = get_module_logger(__name__)
            logger.error(f"Error loading YAML providers from {self.llm_config_path}: {e}")
            return None
    
    def get_template_default(self, var_name: str) -> Optional[str]:
        """
        Get default value for a template variable.
        
        Args:
            var_name: Template variable name (e.g., 'KUBECONFIG')
            
        Returns:
            Default value if available, None otherwise
        """
        # Import logger here to avoid circular imports
        from tarsy.utils.logger import get_module_logger
        logger = get_module_logger(__name__)
        
        # Convert template variable name to settings attribute name
        # VARNAME -> varname_default
        # VAR_NAME -> var_name_default
        default_attr = f"{var_name.lower()}_default"
        default_value = getattr(self, default_attr, None)
        
        # Log presence only, not the actual value to avoid exposing sensitive data
        presence = "found" if default_value is not None else "not found"
        logger.debug(f"Template default lookup for '{var_name}': attribute='{default_attr}', {presence}")
        
        return default_value

@lru_cache()
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings() 