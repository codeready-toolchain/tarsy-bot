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

    def test_get_native_tool_status_with_none_uses_secure_defaults(self) -> None:
        """Test that get_native_tool_status uses secure defaults when native_tools is None."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY"
        )
        
        # Secure defaults: search and url_context enabled, code_execution disabled
        assert config.get_native_tool_status(GoogleNativeTool.GOOGLE_SEARCH.value) is True
        assert config.get_native_tool_status(GoogleNativeTool.CODE_EXECUTION.value) is False
        assert config.get_native_tool_status(GoogleNativeTool.URL_CONTEXT.value) is True

    def test_get_native_tool_status_with_missing_tool_uses_secure_defaults(self) -> None:
        """Test that get_native_tool_status uses secure defaults for missing tools in dict."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            native_tools={GoogleNativeTool.GOOGLE_SEARCH.value: False}
        )
        
        # GOOGLE_SEARCH explicitly disabled
        assert config.get_native_tool_status(GoogleNativeTool.GOOGLE_SEARCH.value) is False
        # Other tools use secure defaults: url_context enabled, code_execution disabled
        assert config.get_native_tool_status(GoogleNativeTool.CODE_EXECUTION.value) is False
        assert config.get_native_tool_status(GoogleNativeTool.URL_CONTEXT.value) is True

    def test_get_native_tool_status_respects_explicit_values(self) -> None:
        """Test that get_native_tool_status respects explicit True/False values."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            native_tools={
                GoogleNativeTool.GOOGLE_SEARCH.value: True,
                GoogleNativeTool.CODE_EXECUTION.value: False,
                GoogleNativeTool.URL_CONTEXT.value: True
            }
        )
        
        assert config.get_native_tool_status(GoogleNativeTool.GOOGLE_SEARCH.value) is True
        assert config.get_native_tool_status(GoogleNativeTool.CODE_EXECUTION.value) is False
        assert config.get_native_tool_status(GoogleNativeTool.URL_CONTEXT.value) is True

    def test_get_native_tool_status_raises_for_unknown_tool(self) -> None:
        """Test that get_native_tool_status raises ValueError for unknown tool names.
        
        This ensures typos and invalid tool names are caught at runtime rather than
        silently defaulting to enabled, which could be a security concern.
        """
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY"
        )
        
        # Unknown tool name should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            config.get_native_tool_status("unknown_tool")
        
        assert "Unknown native tool: unknown_tool" in str(exc_info.value)
        assert "google_search" in str(exc_info.value)  # Should list valid options
        
        # Typo'd tool name should also raise
        with pytest.raises(ValueError) as exc_info:
            config.get_native_tool_status("google_serach")  # typo
        
        assert "Unknown native tool: google_serach" in str(exc_info.value)
        
        # Test with native_tools dict present as well
        config_with_tools = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key_env="GOOGLE_API_KEY",
            native_tools={"google_search": True}
        )
        
        with pytest.raises(ValueError) as exc_info:
            config_with_tools.get_native_tool_status("invalid_tool")
        
        assert "Unknown native tool: invalid_tool" in str(exc_info.value)


@pytest.mark.unit
class TestLLMProviderConfigVertexAIFields:
    """Test cases for VertexAI-specific configuration fields."""

    def test_vertexai_config_with_project_and_location_env(self) -> None:
        """Test VertexAI config can be created with project_env and location_env."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            project_env="GOOGLE_CLOUD_PROJECT",
            location_env="GOOGLE_CLOUD_LOCATION"
        )
        
        assert config.type == LLMProviderType.VERTEXAI
        assert config.project_env == "GOOGLE_CLOUD_PROJECT"
        assert config.location_env == "GOOGLE_CLOUD_LOCATION"
        assert config.api_key_env is None  # Optional for VertexAI

    def test_vertexai_config_without_api_key_env(self) -> None:
        """Test VertexAI config can be created without api_key_env (now optional)."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            project_env="GOOGLE_CLOUD_PROJECT"
        )
        
        assert config.type == LLMProviderType.VERTEXAI
        assert config.api_key_env is None
        assert config.project_env == "GOOGLE_CLOUD_PROJECT"

    def test_runtime_project_and_location_fields_default_none(self) -> None:
        """Test runtime project and location fields default to None."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            project_env="GOOGLE_CLOUD_PROJECT"
        )
        
        assert config.project is None
        assert config.location is None

    def test_runtime_project_and_location_can_be_set(self) -> None:
        """Test runtime project and location fields can be populated."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            project_env="GOOGLE_CLOUD_PROJECT",
            location_env="GOOGLE_CLOUD_LOCATION",
            project="my-gcp-project",
            location="us-east5"
        )
        
        assert config.project == "my-gcp-project"
        assert config.location == "us-east5"

    def test_project_env_validation_rejects_empty_string(self) -> None:
        """Test that project_env rejects empty strings."""
        with pytest.raises(ValidationError) as exc_info:
            LLMProviderConfig(
                type="vertexai",
                model="claude-sonnet-4-5@20250929",
                project_env=""
            )
        
        errors = exc_info.value.errors()
        assert any("empty" in str(error).lower() for error in errors)

    def test_location_env_validation_rejects_empty_string(self) -> None:
        """Test that location_env rejects empty strings."""
        with pytest.raises(ValidationError) as exc_info:
            LLMProviderConfig(
                type="vertexai",
                model="claude-sonnet-4-5@20250929",
                location_env=""
            )
        
        errors = exc_info.value.errors()
        assert any("empty" in str(error).lower() for error in errors)

    def test_project_env_validation_rejects_lowercase(self) -> None:
        """Test that project_env must be uppercase."""
        with pytest.raises(ValidationError) as exc_info:
            LLMProviderConfig(
                type="vertexai",
                model="claude-sonnet-4-5@20250929",
                project_env="google_cloud_project"  # lowercase
            )
        
        errors = exc_info.value.errors()
        assert any("uppercase" in str(error).lower() for error in errors)

    def test_location_env_validation_rejects_lowercase(self) -> None:
        """Test that location_env must be uppercase."""
        with pytest.raises(ValidationError) as exc_info:
            LLMProviderConfig(
                type="vertexai",
                model="claude-sonnet-4-5@20250929",
                location_env="google_cloud_location"  # lowercase
            )
        
        errors = exc_info.value.errors()
        assert any("uppercase" in str(error).lower() for error in errors)

    def test_project_env_strips_whitespace(self) -> None:
        """Test that project_env strips whitespace."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            project_env="  GOOGLE_CLOUD_PROJECT  "
        )
        
        assert config.project_env == "GOOGLE_CLOUD_PROJECT"

    def test_location_env_strips_whitespace(self) -> None:
        """Test that location_env strips whitespace."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            location_env="  GOOGLE_CLOUD_LOCATION  "
        )
        
        assert config.location_env == "GOOGLE_CLOUD_LOCATION"

    def test_non_vertexai_provider_can_omit_project_location_fields(self) -> None:
        """Test that non-VertexAI providers don't need project/location fields."""
        config = LLMProviderConfig(
            type="openai",
            model="gpt-4",
            api_key_env="OPENAI_API_KEY"
        )
        
        assert config.type == LLMProviderType.OPENAI
        assert config.project_env is None
        assert config.location_env is None
        assert config.project is None
        assert config.location is None


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

@pytest.mark.unit
class TestLLMProviderConfigIsAuthConfigured:
    """Test cases for is_auth_configured() method."""

    def test_vertexai_with_both_project_and_location_is_configured(self) -> None:
        """Test that VertexAI with both project and location returns True."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            project="my-gcp-project",
            location="us-east5"
        )

        assert config.is_auth_configured() is True

    def test_vertexai_with_only_project_is_not_configured(self) -> None:
        """Test that VertexAI with only project returns False."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            project="my-gcp-project"
        )

        assert config.is_auth_configured() is False

    def test_vertexai_with_only_location_is_not_configured(self) -> None:
        """Test that VertexAI with only location returns False."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            location="us-east5"
        )

        assert config.is_auth_configured() is False

    def test_vertexai_with_neither_project_nor_location_is_not_configured(self) -> None:
        """Test that VertexAI without project and location returns False."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929"
        )

        assert config.is_auth_configured() is False

    def test_vertexai_with_empty_project_is_not_configured(self) -> None:
        """Test that VertexAI with empty project string returns False."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            project="",
            location="us-east5"
        )

        assert config.is_auth_configured() is False

    def test_vertexai_with_empty_location_is_not_configured(self) -> None:
        """Test that VertexAI with empty location string returns False."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            project="my-gcp-project",
            location=""
        )

        assert config.is_auth_configured() is False

    def test_vertexai_with_both_empty_is_not_configured(self) -> None:
        """Test that VertexAI with both project and location as empty strings returns False."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            project="",
            location=""
        )

        assert config.is_auth_configured() is False
 
    def test_vertexai_with_whitespace_only_project_is_not_configured(self) -> None:
        """Test that VertexAI with whitespace-only project returns False."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            project="   ",
            location="us-east5"
        )

        assert config.is_auth_configured() is False

    def test_vertexai_with_whitespace_only_location_is_not_configured(self) -> None:
        """Test that VertexAI with whitespace-only location returns False."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            project="my-gcp-project",
            location="  \t  "
        )

        assert config.is_auth_configured() is False

    def test_vertexai_with_both_whitespace_only_is_not_configured(self) -> None:
        """Test that VertexAI with both project and location as whitespace-only returns False."""
        config = LLMProviderConfig(
            type="vertexai",
            model="claude-sonnet-4-5@20250929",
            project="   ",
            location=" \t "
        )

        assert config.is_auth_configured() is False

    def test_openai_with_api_key_is_configured(self) -> None:
        """Test that OpenAI with api_key returns True."""
        config = LLMProviderConfig(
            type="openai",
            model="gpt-4",
            api_key="sk-test-key-123"
        )

        assert config.is_auth_configured() is True

    def test_openai_without_api_key_is_not_configured(self) -> None:
        """Test that OpenAI without api_key returns False."""
        config = LLMProviderConfig(
            type="openai",
            model="gpt-4"
        )

        assert config.is_auth_configured() is False

    def test_openai_with_empty_api_key_is_not_configured(self) -> None:
        """Test that OpenAI with empty api_key string returns False."""
        config = LLMProviderConfig(
            type="openai",
            model="gpt-4",
            api_key=""
        )

        assert config.is_auth_configured() is False
 
    def test_openai_with_whitespace_only_api_key_is_not_configured(self) -> None:
        """Test that OpenAI with whitespace-only api_key returns False."""
        config = LLMProviderConfig(
            type="openai",
            model="gpt-4",
            api_key="   \t   "
        )

        assert config.is_auth_configured() is False

    def test_google_with_api_key_is_configured(self) -> None:
        """Test that Google with api_key returns True."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash",
            api_key="test-google-key"
        )

        assert config.is_auth_configured() is True

    def test_google_without_api_key_is_not_configured(self) -> None:
        """Test that Google without api_key returns False."""
        config = LLMProviderConfig(
            type="google",
            model="gemini-2.5-flash"
        )

        assert config.is_auth_configured() is False

    def test_xai_with_api_key_is_configured(self) -> None:
        """Test that xAI with api_key returns True."""
        config = LLMProviderConfig(
            type="xai",
            model="grok-2",
            api_key="xai-test-key"
        )

        assert config.is_auth_configured() is True

    def test_xai_without_api_key_is_not_configured(self) -> None:
        """Test that xAI without api_key returns False."""
        config = LLMProviderConfig(
            type="xai",
            model="grok-2"
        )

        assert config.is_auth_configured() is False

    def test_anthropic_with_api_key_is_configured(self) -> None:
        """Test that Anthropic with api_key returns True."""
        config = LLMProviderConfig(
            type="anthropic",
            model="claude-3-5-sonnet",
            api_key="sk-ant-test-key"
        )

        assert config.is_auth_configured() is True

    def test_anthropic_without_api_key_is_not_configured(self) -> None:
        """Test that Anthropic without api_key returns False."""
        config = LLMProviderConfig(
            type="anthropic",
            model="claude-3-5-sonnet"
        )

        assert config.is_auth_configured() is False

