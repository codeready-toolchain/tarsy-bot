"""
LLM provider models and type definitions.

This module defines type definitions for LLM provider configurations,
including supported provider types and configuration structures.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class LLMProviderType(str, Enum):
    """Supported LLM provider types."""
    
    OPENAI = "openai"
    GOOGLE = "google"
    XAI = "xai"
    ANTHROPIC = "anthropic"
    VERTEXAI = "vertexai"


# Type alias for backward compatibility
ProviderType = LLMProviderType


class LLMProviderConfig(BaseModel):
    """Pydantic model for LLM provider configuration.
    
    Defines the structure for LLM provider configurations with runtime validation,
    default values, and proper error handling for YAML-based configurations.
    """
    model_config = {"extra": "forbid", "frozen": True}
    
    # Required fields
    type: ProviderType = Field(
        description="Provider type (openai, google, xai, anthropic, vertexai)"
    )
    model: str = Field(
        min_length=1,
        description="Model name to use (e.g., gpt-4, gemini-2.5-flash)"
    )
    api_key_env: str = Field(
        min_length=1,
        description="Environment variable name containing the API key"
    )
    
    # Optional fields with defaults
    base_url: Optional[str] = Field(
        default=None,
        description="Custom base URL for the provider API"
    )
    temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="Temperature for response generation (0.0-2.0)"
    )
    verify_ssl: bool = Field(
        default=True,
        description="Whether to verify SSL certificates"
    )
    max_tool_result_tokens: int = Field(
        default=100000,
        gt=0,
        description="Maximum tokens for tool results truncation"
    )
    enable_native_search: bool = Field(
        default=False,
        description="Enable native search grounding (currently Google-only: enables Google Search for Gemini models)"
    )
    
    # Runtime fields (added by Settings.get_llm_config())
    api_key: Optional[str] = Field(
        default=None,
        description="Runtime API key (populated from environment)"
    )
    disable_ssl_verification: bool = Field(
        default=False,
        description="Runtime SSL verification setting"
    )
    
    @field_validator("type")
    @classmethod
    def validate_provider_type(cls, v: str | LLMProviderType) -> str:
        """Validate that provider type is supported."""
        # Convert enum to string if needed
        value = v.value if isinstance(v, LLMProviderType) else v
        
        # Validate against enum values
        supported = [e.value for e in LLMProviderType]
        if value not in supported:
            raise ValueError(f"Unsupported provider type: {value}. Must be one of: {', '.join(supported)}")
        return value
    
    @field_validator("model")
    @classmethod
    def validate_model_name(cls, v: str) -> str:
        """Validate model name is not empty."""
        if not v.strip():
            raise ValueError("Model name cannot be empty")
        return v.strip()
    
    @field_validator("api_key_env")
    @classmethod
    def validate_api_key_env(cls, v: str) -> str:
        """Validate API key environment variable name."""
        if not v.strip():
            raise ValueError("API key environment variable name cannot be empty")
        if not v.isupper():
            raise ValueError("API key environment variable should be uppercase")
        return v.strip()
