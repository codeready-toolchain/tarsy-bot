"""Unit tests for LLM provider configuration models."""

import pytest
from pydantic import ValidationError

from tarsy.models.llm_models import LLMProviderConfig, LLMProviderType


@pytest.mark.unit
class TestLLMProviderType:
    """Test cases for LLMProviderType enum."""

    def test_enum_values(self) -> None:
        """Test that all expected provider types are defined in the enum."""
        assert LLMProviderType.OPENAI.value == "openai"
        assert LLMProviderType.GOOGLE.value == "google"
        assert LLMProviderType.XAI.value == "xai"
        assert LLMProviderType.ANTHROPIC.value == "anthropic"
        assert LLMProviderType.VERTEXAI.value == "vertexai"

    def test_enum_membership(self) -> None:
        """Test that enum values can be used for membership checks."""
        provider_types = [e.value for e in LLMProviderType]
        
        assert "openai" in provider_types
        assert "google" in provider_types
        assert "xai" in provider_types
        assert "anthropic" in provider_types
        assert "vertexai" in provider_types
        assert "invalid" not in provider_types


@pytest.mark.unit
class TestLLMProviderConfigNativeSearch:
    """Test cases for native search configuration in LLMProviderConfig."""

    def test_enable_native_search_defaults_to_false(self) -> None:
        """Test that enable_native_search defaults to False."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY"
        )
        
        assert config.enable_native_search is False

    def test_enable_native_search_can_be_enabled(self) -> None:
        """Test that enable_native_search can be explicitly set to True."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            enable_native_search=True
        )
        
        assert config.enable_native_search is True

    def test_enable_native_search_with_non_google_provider(self) -> None:
        """Test that enable_native_search can be set for non-Google providers.
        
        Note: The configuration allows setting this field for any provider,
        but the LLM client only uses it for Google providers.
        """
        config = LLMProviderConfig(
            type="openai",
            model="gpt-4",
            api_key_env="OPENAI_API_KEY",
            enable_native_search=True
        )
        
        # Configuration should accept it
        assert config.enable_native_search is True

    @pytest.mark.parametrize(
        "enable_value",
        [True, False],
    )
    def test_enable_native_search_accepts_boolean_values(
        self, enable_value: bool
    ) -> None:
        """Test that enable_native_search accepts both True and False."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            enable_native_search=enable_value
        )
        
        assert config.enable_native_search == enable_value

    def test_config_serialization_includes_enable_native_search(self) -> None:
        """Test that enable_native_search is included in serialization."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            enable_native_search=True
        )
        
        config_dict = config.model_dump()
        assert "enable_native_search" in config_dict
        assert config_dict["enable_native_search"] is True


@pytest.mark.unit
class TestLLMProviderConfigValidation:
    """Test cases for LLMProviderConfig validation with provider type enum."""

    @pytest.mark.parametrize(
        "provider_type",
        ["openai", "google", "xai", "anthropic", "vertexai"],
    )
    def test_valid_provider_types(self, provider_type: str) -> None:
        """Test that all LLMProviderType enum values are accepted."""
        config = LLMProviderConfig(
            type=provider_type,
            model="test-model",
            api_key_env="TEST_API_KEY"
        )
        
        # Validator converts string to enum
        assert config.type == LLMProviderType(provider_type)

    @pytest.mark.parametrize(
        "provider_type",
        [
            LLMProviderType.OPENAI,
            LLMProviderType.GOOGLE,
            LLMProviderType.XAI,
            LLMProviderType.ANTHROPIC,
            LLMProviderType.VERTEXAI,
        ],
    )
    def test_valid_enum_provider_types(self, provider_type: LLMProviderType) -> None:
        """Test that LLMProviderType enum values are accepted and normalized."""
        config = LLMProviderConfig(
            type=provider_type,
            model="test-model",
            api_key_env="TEST_API_KEY",
        )
        # Validator should preserve enum type
        assert config.type == provider_type

    def test_invalid_provider_type_raises_validation_error(self) -> None:
        """Test that invalid provider types are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            LLMProviderConfig(
                type="invalid_provider",  # type: ignore
                model="test-model",
                api_key_env="TEST_API_KEY"
            )
        
        errors = exc_info.value.errors()
        assert len(errors) >= 1
        # Should fail either at type validation or provider validation
        assert any(
            "type" in error["loc"] or "provider" in str(error)
            for error in errors
        )

    def test_provider_type_is_case_sensitive(self) -> None:
        """Test that provider type validation is case-sensitive."""
        with pytest.raises(ValidationError):
            LLMProviderConfig(
                type="GOOGLE",  # type: ignore # Should be lowercase
                model="test-model",
                api_key_env="TEST_API_KEY"
            )

    def test_complete_config_with_all_fields(self) -> None:
        """Test a complete configuration with all fields set."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            base_url="https://custom.api.endpoint",
            temperature=0.7,
            verify_ssl=True,
            max_tool_result_tokens=500000,
            enable_native_search=True,
            api_key="test-key-value",
            disable_ssl_verification=False
        )
        
        assert config.type == LLMProviderType.GOOGLE
        assert config.model == "gemini-2.5-flash"
        assert config.api_key_env == "GOOGLE_API_KEY"
        assert config.base_url == "https://custom.api.endpoint"
        assert config.temperature == 0.7
        assert config.verify_ssl is True
        assert config.max_tool_result_tokens == 500000
        assert config.enable_native_search is True
        assert config.api_key == "test-key-value"
        assert config.disable_ssl_verification is False

