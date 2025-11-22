"""Unit tests for LLM provider configuration models."""

import pytest
from pydantic import ValidationError

from tarsy.models.llm_models import GoogleNativeTool, LLMProviderConfig, LLMProviderType


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
class TestLLMProviderConfigNativeTools:
    """Test cases for native tools configuration in LLMProviderConfig."""

    def test_native_tools_defaults_to_none(self) -> None:
        """Test that native_tools defaults to None."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY"
        )
        
        assert config.native_tools is None

    def test_native_tools_can_be_configured(self) -> None:
        """Test that native_tools can be explicitly set."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            native_tools={
                GoogleNativeTool.GOOGLE_SEARCH.value: True,
                GoogleNativeTool.CODE_EXECUTION.value: True,
                GoogleNativeTool.URL_CONTEXT.value: False
            }
        )
        
        assert config.native_tools == {
            GoogleNativeTool.GOOGLE_SEARCH.value: True,
            GoogleNativeTool.CODE_EXECUTION.value: True,
            GoogleNativeTool.URL_CONTEXT.value: False
        }

    def test_native_tools_with_non_google_provider(self) -> None:
        """Test that native_tools can be set for non-Google providers.
        
        Note: The configuration allows setting this field for any provider,
        but the LLM client only uses it for Google providers.
        """
        config = LLMProviderConfig(
            type="openai",
            model="gpt-4",
            api_key_env="OPENAI_API_KEY",
            native_tools={GoogleNativeTool.GOOGLE_SEARCH.value: True}
        )
        
        # Configuration should accept it
        assert config.native_tools == {"google_search": True}

    def test_native_tools_rejects_invalid_tool_names(self) -> None:
        """Test that invalid tool names are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            LLMProviderConfig(
                type="google",
                model="gemini-2.5-flash",
                api_key_env="GOOGLE_API_KEY",
                native_tools={"invalid_tool": True}
            )
        
        errors = exc_info.value.errors()
        assert len(errors) >= 1
        assert "invalid_tool" in str(errors[0]["ctx"]["error"])

    def test_native_tools_rejects_non_boolean_values(self) -> None:
        """Test that non-boolean values are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            LLMProviderConfig(
                type="google",
                model="gemini-2.5-flash",
                api_key_env="GOOGLE_API_KEY",
                native_tools={GoogleNativeTool.GOOGLE_SEARCH.value: "yes"}  # type: ignore
            )
        
        errors = exc_info.value.errors()
        assert len(errors) >= 1

    def test_config_serialization_includes_native_tools(self) -> None:
        """Test that native_tools is included in serialization."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            native_tools={GoogleNativeTool.GOOGLE_SEARCH.value: True, GoogleNativeTool.CODE_EXECUTION.value: False}
        )
        
        config_dict = config.model_dump()
        assert "native_tools" in config_dict
        assert config_dict["native_tools"] == {GoogleNativeTool.GOOGLE_SEARCH.value: True, GoogleNativeTool.CODE_EXECUTION.value: False}

    def test_get_native_tool_status_with_none_returns_true(self) -> None:
        """Test that get_native_tool_status returns True when native_tools is None."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY"
        )
        
        # All tools enabled by default
        assert config.get_native_tool_status(GoogleNativeTool.GOOGLE_SEARCH.value) is True
        assert config.get_native_tool_status(GoogleNativeTool.CODE_EXECUTION.value) is True
        assert config.get_native_tool_status(GoogleNativeTool.URL_CONTEXT.value) is True

    def test_get_native_tool_status_with_missing_tool_returns_true(self) -> None:
        """Test that get_native_tool_status returns True for missing tools."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            native_tools={GoogleNativeTool.GOOGLE_SEARCH.value: False}
        )
        
        # GOOGLE_SEARCH explicitly disabled
        assert config.get_native_tool_status(GoogleNativeTool.GOOGLE_SEARCH.value) is False
        # Other tools default to enabled
        assert config.get_native_tool_status(GoogleNativeTool.CODE_EXECUTION.value) is True
        assert config.get_native_tool_status(GoogleNativeTool.URL_CONTEXT.value) is True

    def test_get_native_tool_status_respects_explicit_values(self) -> None:
        """Test that get_native_tool_status respects explicit True/False values."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            native_tools={
                "google_search": True,
                "code_execution": False,
                "url_context": True
            }
        )
        
        assert config.get_native_tool_status("google_search") is True
        assert config.get_native_tool_status("code_execution") is False
        assert config.get_native_tool_status("url_context") is True


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
            native_tools={
                GoogleNativeTool.GOOGLE_SEARCH.value: True,
                GoogleNativeTool.CODE_EXECUTION.value: True,
                GoogleNativeTool.URL_CONTEXT.value: False
            },
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
        assert config.native_tools == {
            GoogleNativeTool.GOOGLE_SEARCH.value: True,
            GoogleNativeTool.CODE_EXECUTION.value: True,
            GoogleNativeTool.URL_CONTEXT.value: False
        }
        assert config.api_key == "test-key-value"
        assert config.disable_ssl_verification is False

