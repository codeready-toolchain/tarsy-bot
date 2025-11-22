"""
LLM provider models and type definitions.

This module defines type definitions for LLM provider configurations,
including supported provider types and configuration structures.
"""

from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field, field_validator


class LLMProviderType(str, Enum):
    """Supported LLM provider types."""
    
    OPENAI = "openai"
    GOOGLE = "google"
    XAI = "xai"
    ANTHROPIC = "anthropic"
    VERTEXAI = "vertexai"


class GoogleNativeTool(str, Enum):
    """Supported Google/Gemini native tools."""
    
    GOOGLE_SEARCH = "google_search"
    CODE_EXECUTION = "code_execution"
    URL_CONTEXT = "url_context"


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
    native_tools: Optional[Dict[str, bool]] = Field(
        default=None,
        description="Native tool configuration for Google/Gemini models (GoogleNativeTool enum values). Default: all enabled"
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
    
    @field_validator("type", mode="before")
    @classmethod
    def validate_provider_type(cls, v: str | LLMProviderType) -> LLMProviderType:
        """Validate that provider type is supported and convert to enum."""
        # Convert to string for validation
        value = v.value if isinstance(v, LLMProviderType) else str(v)
        
        # Validate against enum values
        supported = [e.value for e in LLMProviderType]
        if value not in supported:
            raise ValueError(f"Unsupported provider type: {value}. Must be one of: {', '.join(supported)}")
        
        # Return enum instance
        return LLMProviderType(value)
    
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
    
    @field_validator("native_tools", mode="before")
    @classmethod
    def validate_native_tools(cls, v: Optional[Dict[str, bool]]) -> Optional[Dict[str, bool]]:
        """Validate native_tools configuration.
        
        Validates that tool names are recognized and values are boolean.
        Supported tools defined in GoogleNativeTool enum.
        """
        if v is None:
            return None
        
        if not isinstance(v, dict):
            raise ValueError(f"native_tools must be a dictionary, got: {type(v).__name__}")
        
        # Get supported tool names from enum
        supported_tools = {tool.value for tool in GoogleNativeTool}
        
        # Validate all provided tools are recognized
        for tool_name in v.keys():
            if tool_name not in supported_tools:
                raise ValueError(
                    f"Unsupported native tool: {tool_name}. "
                    f"Must be one of: {', '.join(sorted(supported_tools))}"
                )
        
        # Validate all values are boolean (strict check before Pydantic coercion)
        for tool_name, enabled in v.items():
            if not isinstance(enabled, bool):
                raise ValueError(
                    f"Native tool '{tool_name}' value must be boolean, got: {type(enabled).__name__}"
                )
        
        return v
    
    def get_native_tool_status(self, tool_name: str) -> bool:
        """Get native tool status with default=True behavior.
        
        Args:
            tool_name: Name of the tool (use GoogleNativeTool enum values)
            
        Returns:
            True if tool is enabled (or should be enabled by default), False if explicitly disabled
            
        Default behavior:
            - If native_tools is None (not configured) → True (all tools enabled)
            - If native_tools exists but tool not listed → True (tool enabled by default)
            - If tool explicitly set to False → False (tool disabled)
            - If tool explicitly set to True → True (tool enabled)
        """
        if self.native_tools is None:
            return True  # All tools enabled if section missing
        return self.native_tools.get(tool_name, True)  # Default to True if tool not in dict
