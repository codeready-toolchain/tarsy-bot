"""
LLM provider models and type definitions.

This module defines type definitions for LLM provider configurations,
including supported provider types and configuration structures.
"""

from typing import TypedDict, Literal, NotRequired


# Supported LLM provider types
ProviderType = Literal["openai", "google", "xai", "anthropic"]


class LLMProviderConfig(TypedDict):
    """Type definition for LLM provider configuration.
    
    Defines the structure for LLM provider configurations including
    required fields (type, model, api_key_env) and optional settings
    (base_url, temperature, verify_ssl).
    """
    type: ProviderType
    model: str
    api_key_env: str
    base_url: NotRequired[str]
    temperature: NotRequired[float]
    verify_ssl: NotRequired[bool]
