"""
Tests for LLM models and type definitions.

This module tests the LLM provider models and type definitions,
including LLMProviderConfig TypedDict enhancements from EP-0016.
"""

import pytest
from typing import get_type_hints

from tarsy.models.llm_models import LLMProviderConfig, ProviderType


@pytest.mark.unit
class TestProviderType:
    """Test ProviderType literal type."""
    
    def test_provider_type_values(self):
        """Test that ProviderType contains expected literal values."""
        # Check that ProviderType is defined correctly
        assert hasattr(ProviderType, "__args__")
        expected_types = {"openai", "google", "xai", "anthropic"}
        actual_types = set(ProviderType.__args__)
        assert actual_types == expected_types


@pytest.mark.unit
class TestLLMProviderConfig:
    """Test LLMProviderConfig TypedDict."""
    
    def test_llm_provider_config_required_fields(self):
        """Test that LLMProviderConfig has all required fields."""
        # Get type hints for LLMProviderConfig
        type_hints = get_type_hints(LLMProviderConfig)
        
        # Check required fields are present
        required_fields = {"type", "model", "api_key_env"}
        for field in required_fields:
            assert field in type_hints, f"Required field {field} missing from LLMProviderConfig"
    
    def test_llm_provider_config_optional_fields(self):
        """Test that LLMProviderConfig has all optional fields including EP-0016 additions."""
        # Get type hints for LLMProviderConfig  
        type_hints = get_type_hints(LLMProviderConfig)
        
        # Check EP-0016 field is present
        assert "max_tool_result_tokens" in type_hints, "EP-0016 max_tool_result_tokens field missing"
        
        # Check other optional fields are present
        optional_fields = {"base_url", "temperature", "verify_ssl", "max_tool_result_tokens"}
        for field in optional_fields:
            assert field in type_hints, f"Optional field {field} missing from LLMProviderConfig"
    
    def test_llm_provider_config_valid_creation(self):
        """Test that valid LLMProviderConfig instances can be created."""
        # Test minimal required configuration
        minimal_config = LLMProviderConfig(
            type="openai",
            model="gpt-4",
            api_key_env="OPENAI_API_KEY"
        )
        
        assert minimal_config.type == "openai"
        assert minimal_config.model == "gpt-4"
        assert minimal_config.api_key_env == "OPENAI_API_KEY"
    
    def test_llm_provider_config_with_ep0016_field(self):
        """Test LLMProviderConfig with EP-0016 max_tool_result_tokens field."""
        # Test configuration with EP-0016 field
        config_with_max_tokens = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            temperature=0.1,
            max_tool_result_tokens=950000  # EP-0016 field
        )
        
        assert config_with_max_tokens.type == "google"
        assert config_with_max_tokens.model == "gemini-2.5-flash"
        assert config_with_max_tokens.api_key_env == "GOOGLE_API_KEY"
        assert config_with_max_tokens.temperature == 0.1
        assert config_with_max_tokens.max_tool_result_tokens == 950000
    
    def test_llm_provider_config_all_fields(self):
        """Test LLMProviderConfig with all possible fields."""
        full_config = LLMProviderConfig(
            type="anthropic",
            model="claude-sonnet-4-20250514",
            api_key_env="ANTHROPIC_API_KEY",
            base_url="https://custom-api.example.com",
            temperature=0.2,
            verify_ssl=False,
            max_tool_result_tokens=150000  # EP-0016 field
        )
        
        # Verify all fields are accessible
        assert full_config.type == "anthropic"
        assert full_config.model == "claude-sonnet-4-20250514"
        assert full_config.api_key_env == "ANTHROPIC_API_KEY"
        assert full_config.base_url == "https://custom-api.example.com"
        assert full_config.temperature == 0.2
        assert full_config.verify_ssl is False
        assert full_config.max_tool_result_tokens == 150000
    
    def test_llm_provider_config_provider_type_validation(self):
        """Test that only valid provider types are accepted."""
        # Test valid provider types
        valid_types = ["openai", "google", "xai", "anthropic"]
        
        for provider_type in valid_types:
            config = LLMProviderConfig(
                type=provider_type,  # type: ignore  # We're testing type validation
                model="test-model",
                api_key_env="TEST_API_KEY"
            )
            assert config.type == provider_type
