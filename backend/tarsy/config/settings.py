"""
Application settings and configuration management.
"""

import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urlparse

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from tarsy.config.builtin_config import get_builtin_llm_providers
from tarsy.models.llm_models import LLMProviderConfig, LLMProviderType

def is_testing() -> bool:
    """Check if we're running in a test environment."""
    return (
        "pytest" in os.environ.get("_", "") or
        "PYTEST_CURRENT_TEST" in os.environ or
        os.environ.get("TESTING", "").lower() == "true" or
        ("test" in sys.argv[0].lower() if len(sys.argv) > 0 else False)
    )


class Settings(BaseSettings):
    """Application settings."""
    
    # Server Configuration
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    log_level: str = Field(default="INFO")
    
    # CORS Configuration  
    cors_origins_str: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
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
    google_cloud_project: str = Field(
        default="",
        description="GCP project ID for VertexAI (Claude on Vertex AI). Maps to GOOGLE_CLOUD_PROJECT env var (standard GCP)."
    )
    google_cloud_location: str = Field(
        default="us-east5",
        description="GCP region for VertexAI (Claude on Vertex AI). Maps to GOOGLE_CLOUD_LOCATION env var (standard GCP). Default: us-east5"
    )
    llm_provider: str = Field(default="google-default")
    disable_ssl_verification: bool = Field(default=False, description="Disable SSL certificate verification for LLM API calls (use with caution)")
    
    @field_validator('google_api_key', 'openai_api_key', 'xai_api_key', 'anthropic_api_key', 'google_cloud_project', 'google_cloud_location', mode='after')
    @classmethod
    def strip_api_keys(cls, v: str) -> str:
        """Strip whitespace from API keys and configuration values to avoid errors."""
        return v.strip() if v else v
    
    # LLM Configuration File Path
    llm_config_path: str = Field(default="../config/llm_providers.yaml", description="Path to external LLM providers configuration file")
    
    # GitHub Configuration
    github_token: Optional[str] = Field(default=None)
    runbooks_repo_url: Optional[str] = Field(
        default=None,
        description="GitHub repository URL for runbooks (e.g., https://github.com/org/repo/tree/branch/path). "
        "Private repos require github_token to be set."
    )
    
    # Alert Processing Configuration
    max_llm_mcp_iterations: int = Field(
        default=30,
        description="Maximum number of LLM->MCP iterative loops for multi-step processing"
    )
    force_conclusion_at_max_iterations: bool = Field(
        default=False,
        description="Force LLM to conclude with available data when max iterations reached (instead of pausing for manual resume). Chats always use forced conclusion regardless of this setting."
    )
    
    # LLM Streaming Configuration
    enable_llm_streaming: bool = Field(
        default=True,
        description="Enable real-time streaming of LLM thoughts via WebSocket (PostgreSQL only)"
    )
    
    # Database Configuration
    database_url: str = Field(
        default="",
        description="Database connection string for alert processing history"
    )
    
    @field_validator('database_url', mode='after')
    @classmethod
    def strip_database_url(cls, v: str) -> str:
        """Strip whitespace from database URL to avoid common configuration errors."""
        return v.strip() if v else v

    database_host: str = Field(
        default="localhost",
        description="Database host"
    )
    database_port: int = Field(
        default=5432,
        description="Database port"
    )
    database_user: str = Field(
        default="tarsy",
        description="Database username"
    )
    database_password: str = Field(
        default="",
        description="Database password"
    )
    database_name: str = Field(
        default="tarsy",
        description="Database name"
    )
    history_retention_days: int = Field(
        default=365,
        description="Number of days to retain alert processing history data"
    )
    history_cleanup_interval_hours: int = Field(
        default=12,
        description="How often to run history retention cleanup (hours)"
    )
    orphaned_session_timeout_minutes: int = Field(
        default=30,
        description="Mark sessions as orphaned if no activity for N minutes"
    )
    orphaned_session_check_interval_minutes: int = Field(
        default=10,
        description="How often to check for orphaned sessions (minutes)"
    )
    
    # Event System Configuration
    event_retention_hours: int = Field(
        default=24,
        description="How long to retain events in events table (hours)"
    )
    event_cleanup_interval_hours: int = Field(
        default=6,
        description="How often to run event cleanup (hours)"
    )
    
    # PostgreSQL Connection Pool Configuration
    postgres_pool_size: int = Field(
        default=5,
        description="PostgreSQL connection pool size"
    )
    postgres_max_overflow: int = Field(
        default=10,
        description="PostgreSQL connection pool max overflow"
    )
    postgres_pool_timeout: int = Field(
        default=30,
        description="PostgreSQL connection pool timeout in seconds"
    )
    postgres_pool_recycle: int = Field(
        default=3600,
        description="PostgreSQL connection pool recycle time in seconds"
    )
    postgres_pool_pre_ping: bool = Field(
        default=True,
        description="Enable PostgreSQL connection pool pre-ping to validate connections"
    )
    
    # Alert Queue Configuration
    max_concurrent_alerts: int = Field(
        default=5,
        description="Maximum alerts processing concurrently across ALL pods (global limit). "
                    "Enforced via database-backed queue with SessionClaimWorker."
    )
    max_queue_size: Optional[int] = Field(
        default=None,
        description="Maximum number of alerts waiting in PENDING state. "
                    "None = unlimited queue. Rejects new alerts with HTTP 429 when full."
    )
    queue_claim_interval_seconds: float = Field(
        default=1.0,
        description="Interval between queue claim attempts (seconds)"
    )
    
    @field_validator('max_concurrent_alerts', mode='after')
    @classmethod
    def validate_max_concurrent_alerts(cls, v: int) -> int:
        """Ensure max_concurrent_alerts is a positive integer."""
        if not isinstance(v, int) or v <= 0:
            raise ValueError(
                f"max_concurrent_alerts must be an integer greater than 0, got: {v}"
            )
        return v
    
    @field_validator('max_queue_size', mode='after')
    @classmethod
    def validate_max_queue_size(cls, v: Optional[int]) -> Optional[int]:
        """Ensure max_queue_size is either None or a non-negative integer."""
        if v is not None and (not isinstance(v, int) or v < 0):
            raise ValueError(
                f"max_queue_size must be None or an integer >= 0, got: {v}"
            )
        return v
    
    @field_validator('queue_claim_interval_seconds', mode='after')
    @classmethod
    def validate_queue_claim_interval_seconds(cls, v: float) -> float:
        """Ensure queue_claim_interval_seconds is a positive float."""
        if not isinstance(v, (int, float)) or v <= 0:
            raise ValueError(
                f"queue_claim_interval_seconds must be a number greater than 0, got: {v}"
            )
        return float(v)
    
    alert_processing_timeout: int = Field(
        default=900,
        description="Timeout in seconds for processing a single alert (default: 15 minutes)"
    )
    llm_iteration_timeout: int = Field(
        default=210,
        description="Timeout in seconds for a single LLM iteration (default: 3.5 minutes). "
                   "Must accommodate LLM call (120s max) + tool execution (70s max) + overhead."
    )
    mcp_tool_call_timeout: int = Field(
        default=70,
        description="Timeout in seconds for a single MCP tool call (default: 70 seconds)"
    )
    scoring_timeout: int = Field(
        default=300,
        description="Timeout in seconds for scoring a single session (default: 5 minutes). "
                    "Allows for 2 LLM turns (120s each) + retries + overhead."
    )

    # Agent Configuration
    agent_config_path: str = Field(
        default="../config/agents.yaml",
        description="Path to agent and MCP server configuration file"
    )
    
    # JWT Authentication Configuration
    jwt_public_key_path: str = Field(
        default="../config/keys/jwt_public_key.pem",
        description="Path to JWT public key file for token validation"
    )
    
    # Alert Data Masking Configuration
    alert_data_masking_enabled: bool = Field(
        default=True,
        description="Enable masking of sensitive data in incoming alerts"
    )
    alert_data_masking_pattern_group: str = Field(
        default="security",
        description="Pattern group to use for alert data masking (basic, secrets, security, kubernetes, all)"
    )
    
    # Template Variable Defaults
    # These provide default values for template variables if not set in environment
    kubeconfig_default: str = Field(
        default_factory=lambda: os.path.expanduser("~/.kube/config"),
        description="Default kubeconfig path for Kubernetes MCP server (tilde expanded)"
    )

    # Slack Configuration
    slack_bot_token: str = Field(
        default="",
        description="Slack bot token for sending notifications"
    )

    slack_channel: str = Field(
        default="",
        description="Slack channel for sending notifications"
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set default database URL based on environment if not explicitly provided
        if not self.database_url:
            if is_testing():
                # Use in-memory database for tests by default
                self.database_url = "sqlite:///:memory:"
            elif self.database_password:
                # Compose PostgreSQL URL from separate components if password is provided
                # quote_plus automatically handles special characters like @ # $ % etc.
                self.database_url = f"postgresql://{quote_plus(self.database_user)}:{quote_plus(self.database_password)}@{self.database_host}:{self.database_port}/{self.database_name}"
            else:
                # Use file database for dev/production when no PostgreSQL credentials
                self.database_url = "sqlite:///history.db"
    
    @model_validator(mode='after')
    def validate_database_url(self) -> 'Settings':
        """
        Validate DATABASE_URL for common issues with special characters.
        
        Provides helpful error messages if unencoded special characters are detected
        in the password portion of the DATABASE_URL.
        """
        if not self.database_url or self.database_url.startswith('sqlite'):
            return self
        
        try:
            # Try to parse the URL
            parsed = urlparse(self.database_url)
            
            # Check if URL looks like it should have credentials but parsing failed
            # Pattern: scheme://something:something@host suggests credentials
            # If parsed.username is None but the URL contains '://' and '@', parsing likely failed due to special chars
            if parsed.username is None and '://' in self.database_url and '@' in self.database_url:
                # URL has @ but no username parsed - likely due to special characters breaking parsing
                # Extract the part between :// and @ to show in error
                match = re.search(r'://([^@/]+)@', self.database_url)
                if match:
                    raise ValueError(
                        f"\n{'='*80}\n"
                        f"DATABASE_URL CONFIGURATION ERROR\n"
                        f"{'='*80}\n"
                        f"Your DATABASE_URL appears to contain special characters that break URL parsing.\n"
                        f"This usually means the password contains unencoded special characters like #, $, !, etc.\n\n"
                        f"SOLUTION 1 (Recommended): Use separate configuration components:\n"
                        f"  DATABASE_USER=<your-username>\n"
                        f"  DATABASE_PASSWORD=<your-password>  # Automatic URL encoding\n"
                        f"  DATABASE_HOST=<your-host>\n"
                        f"  DATABASE_PORT=5432\n"
                        f"  DATABASE_NAME=<your-database>\n\n"
                        f"SOLUTION 2: Manually URL-encode the password in DATABASE_URL\n"
                        f"  Example: @ becomes %40, ! becomes %21, # becomes %23\n"
                        f"{'='*80}\n"
                    )
            
            # If we successfully parsed and have a password, check for unencoded special chars
            if parsed.password:
                password = parsed.password
                
                # Remove all properly encoded sequences (%XX where XX are hex digits)
                # This helps us detect actual unencoded special characters
                # Pattern: % followed by exactly two hex digits
                password_without_encoding = re.sub(r'%[0-9A-Fa-f]{2}', '', password)
                
                # Check for common special characters that must be URL-encoded
                # These characters have special meaning in URLs and will break parsing
                # Note: We check the password after removing encoded sequences
                special_chars = ['@', '#', '$', '%', '&', '/', ':', '?', '=', '+', ' ', '!']
                found_chars = [char for char in special_chars if char in password_without_encoding]
                
                if found_chars:
                    # Remove duplicates and sort for consistent error messages
                    found_chars = sorted(set(found_chars))
                    chars_list = ', '.join(f"'{c}'" for c in found_chars)
                    
                    raise ValueError(
                        f"\n{'='*80}\n"
                        f"DATABASE_URL CONFIGURATION ERROR\n"
                        f"{'='*80}\n"
                        f"Your database password contains special characters ({chars_list}) that must be URL-encoded.\n\n"
                        f"SOLUTION 1 (Recommended): Use separate configuration components:\n"
                        f"  DATABASE_USER={parsed.username}\n"
                        f"  DATABASE_PASSWORD=<your-password>  # Automatic URL encoding\n"
                        f"  DATABASE_HOST={parsed.hostname}\n"
                        f"  DATABASE_PORT={parsed.port or 5432}\n"
                        f"  DATABASE_NAME={parsed.path.lstrip('/') if parsed.path else ''}\n\n"
                        f"SOLUTION 2: Manually URL-encode the password in DATABASE_URL\n"
                        f"  Example: @ becomes %40, ! becomes %21, # becomes %23\n"
                        f"{'='*80}\n"
                    )
        except ValueError:
            # Re-raise our validation error
            raise
        except Exception:
            # If URL parsing fails for any other reason, let it through
            # The database connection will fail with its own error
            from tarsy.utils.logger import get_module_logger
            get_module_logger(__name__).debug(
                "DATABASE_URL parsing encountered an unexpected issue; deferring to connection time"
            )
        
        return self
    
    model_config = SettingsConfigDict(
        env_file=".env" if not is_testing() else None,
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
        provider_type = base_config.type  # Type-safe field access
        
        # Special handling for VertexAI - uses project/location instead of api_key
        if provider_type == LLMProviderType.VERTEXAI:
            # Read from project_env and location_env specified in config
            project = ""
            location = self.google_cloud_location  # Default
            
            if base_config.project_env:
                project = os.getenv(base_config.project_env, "").strip()
                if not project:
                    project = self.google_cloud_project  # Fallback to Settings field
            else:
                project = self.google_cloud_project
                
            if base_config.location_env:
                env_location = os.getenv(base_config.location_env, "").strip()
                if env_location:
                    location = env_location
                # else: use default from Settings field
            
            return base_config.model_copy(update={
                "project": project,
                "location": location,
                "disable_ssl_verification": self.disable_ssl_verification
            })
        
        # Standard handling for other providers (api_key)
        api_key = ""
        if base_config.api_key_env:
            api_key = os.getenv(base_config.api_key_env, "").strip()
        
        # Fallback to provider-specific Settings fields if env var not set
        if not api_key:
            if provider_type == LLMProviderType.GOOGLE:
                api_key = self.google_api_key
            elif provider_type == LLMProviderType.OPENAI:
                api_key = self.openai_api_key
            elif provider_type == LLMProviderType.XAI:
                api_key = self.xai_api_key
            elif provider_type == LLMProviderType.ANTHROPIC:
                api_key = self.anthropic_api_key

        # Create new config instance with runtime fields
        return base_config.model_copy(update={
            "api_key": api_key,
            "disable_ssl_verification": self.disable_ssl_verification
        })
    
    @property
    def llm_providers(self) -> Dict[str, LLMProviderConfig]:
        """
        Get merged LLM providers configuration (built-in defaults + YAML overrides).
        Fails fast if YAML file exists but is invalid.
        
        Raises:
            Exception: If LLM providers configuration file exists but is invalid
        """
        # Start with built-in defaults from builtin_config
        merged_providers = get_builtin_llm_providers()
        
        # Load and merge YAML if file exists
        # Note: _load_yaml_providers will raise if file exists but is invalid
        yaml_providers = self._load_yaml_providers()
        if yaml_providers:
            merged_providers.update(yaml_providers)
        
        return merged_providers
    
    def _load_yaml_providers(self) -> Optional[Dict[str, LLMProviderConfig]]:
        """
        Load LLM providers from YAML configuration file.
        Fails fast if file exists but is invalid (syntax error or validation error).
        
        Returns:
            Dict of validated providers, or None if file doesn't exist
            
        Raises:
            yaml.YAMLError: If YAML syntax is invalid
            Exception: If provider configuration is invalid
        """
        from tarsy.utils.logger import get_module_logger
        logger = get_module_logger(__name__)
        
        config_path = Path(self.llm_config_path)
        
        # If file doesn't exist, return None (use built-ins - OK)
        if not config_path.exists():
            logger.debug(f"LLM providers config file not found at {config_path}, using built-in providers only")
            return None
        
        # File exists - it MUST be valid! Fail fast on errors.
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f)
            
            # Empty file is OK - use built-ins
            if not yaml_config:
                logger.warning(f"LLM providers config file is empty: {config_path}")
                return None
            
            # File must have llm_providers section if not empty
            if 'llm_providers' not in yaml_config:
                logger.critical(f"LLM providers config file exists but missing 'llm_providers' section: {config_path}")
                raise ValueError(f"Invalid LLM providers config: missing 'llm_providers' section in {config_path}")
            
            providers = yaml_config['llm_providers']
            
            # Validate YAML providers using Pydantic
            validated_providers: Dict[str, LLMProviderConfig] = {}
            validation_errors = []
            
            for provider_name, config_dict in providers.items():
                try:
                    # Validate using Pydantic BaseModel
                    config = LLMProviderConfig.model_validate(config_dict)
                    validated_providers[provider_name] = config
                except Exception as e:
                    validation_errors.append(f"Provider '{provider_name}': {e}")
            
            # If any providers failed validation, fail fast
            if validation_errors:
                error_msg = "\n  - ".join(validation_errors)
                logger.critical(f"LLM providers config validation errors in {config_path}:\n  - {error_msg}")
                raise ValueError(f"Invalid LLM provider configurations in {config_path}. Errors:\n  - {error_msg}")
            
            logger.info(f"Loaded {len(validated_providers)} LLM providers from {config_path}")
            return validated_providers
            
        except yaml.YAMLError as e:
            logger.critical(f"YAML syntax error in {config_path}: {e}")
            raise
        except ValueError:
            # Re-raise validation errors
            raise
        except Exception as e:
            logger.critical(f"Failed to load LLM providers from {config_path}: {e}")
            raise
    
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
