"""
Unit tests for Settings module.

Tests critical configuration loading, validation, and template functionality.
"""

import os
import tempfile
from unittest.mock import patch

import pytest

from tarsy.config.settings import Settings, get_settings, is_testing
from tarsy.models.llm_models import LLMProviderType


@pytest.mark.unit
class TestIsTesting:
    """Test environment detection function."""
    
    def test_is_testing_with_pytest_env(self):
        """Test is_testing returns True when pytest is in environment."""
        with patch.dict(os.environ, {"_": "/usr/bin/pytest"}, clear=False):
            assert is_testing() is True
    
    def test_is_testing_with_pytest_current_test(self):
        """Test is_testing returns True with PYTEST_CURRENT_TEST."""
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "test_something::test_case"}, clear=False):
            assert is_testing() is True
    
    def test_is_testing_with_testing_flag(self):
        """Test is_testing returns True with TESTING=true."""
        with patch.dict(os.environ, {"TESTING": "true"}, clear=False):
            assert is_testing() is True
    
    def test_is_testing_with_test_in_argv(self):
        """Test is_testing returns True when 'test' is in argv[0]."""
        with patch('sys.argv', ["/usr/bin/test-runner"]):
            assert is_testing() is True
    
    def test_is_testing_normal_environment(self):
        """Test is_testing returns False in normal environment."""
        # Create a clean environment without test indicators
        test_env = {
            "_": "/usr/bin/python",
            "PATH": os.environ.get("PATH", "")
        }
        
        with patch.dict(os.environ, test_env, clear=True), \
             patch('sys.argv', ["/usr/bin/python", "app.py"]):
            assert is_testing() is False


@pytest.mark.unit 
class TestSettingsYAMLConfiguration:
    """Test YAML configuration loading and validation."""
    
    @pytest.fixture
    def temp_yaml_file(self):
        """Create temporary YAML config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            content = {
                'llm_providers': {
                    'custom-openai': {
                        'type': 'openai',
                        'model': 'gpt-4-custom',
                        'api_key_env': 'CUSTOM_OPENAI_KEY',
                        'base_url': 'https://custom-openai.example.com/v1'
                    },
                    'custom-google': {
                        'type': 'google', 
                        'model': 'gemini-pro-custom',
                        'api_key_env': 'CUSTOM_GOOGLE_KEY'
                    }
                }
            }
            import yaml
            yaml.safe_dump(content, f)
            yield f.name
        
        # Cleanup
        os.unlink(f.name)
    
    @pytest.fixture
    def invalid_yaml_file(self):
        """Create invalid YAML config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [unclosed")
            yield f.name
        
        os.unlink(f.name)
    
    @pytest.fixture
    def missing_fields_yaml_file(self):
        """Create YAML with missing required fields."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            content = {
                'llm_providers': {
                    'incomplete-provider': {
                        'type': 'openai',
                        # Missing 'model' and 'api_key_env'
                    }
                }
            }
            import yaml
            yaml.safe_dump(content, f)
            yield f.name
        
        os.unlink(f.name)
    
    def test_load_valid_yaml_providers(self, temp_yaml_file):
        """Test loading valid YAML providers configuration."""
        settings = Settings(llm_config_path=temp_yaml_file)
        providers = settings.llm_providers
        
        # Should contain both built-in and YAML providers
        assert 'custom-openai' in providers
        assert 'custom-google' in providers
        
        # Check YAML provider details
        custom_openai = providers['custom-openai']
        assert custom_openai.type == LLMProviderType.OPENAI
        assert custom_openai.model == 'gpt-4-custom'
        assert custom_openai.base_url == 'https://custom-openai.example.com/v1'
    
    def test_yaml_providers_override_builtin(self, temp_yaml_file):
        """Test that YAML providers can override built-in providers."""
        # If YAML has same provider name as built-in, YAML should win
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            content = {
                'llm_providers': {
                    'google-default': {  # Override built-in provider
                        'type': 'google',
                        'model': 'custom-gemini-override',
                        'api_key_env': 'CUSTOM_GOOGLE_KEY'
                    }
                }
            }
            import yaml
            yaml.safe_dump(content, f)
            
            settings = Settings(llm_config_path=f.name)
            providers = settings.llm_providers
            
            # Should have overridden the built-in provider
            assert providers['google-default'].model == 'custom-gemini-override'
            
            os.unlink(f.name)
    
    def test_yaml_file_not_found(self):
        """Test behavior when YAML file doesn't exist."""
        settings = Settings(llm_config_path="nonexistent.yaml")
        providers = settings.llm_providers
        
        # Should fall back to built-in providers only
        from tarsy.config.builtin_config import get_builtin_llm_providers
        builtin_providers = get_builtin_llm_providers()
        
        # Should only contain built-in providers
        for provider_name in builtin_providers:
            assert provider_name in providers
    
    def test_invalid_yaml_fallback_to_builtin(self, invalid_yaml_file):
        """Test fallback to built-in providers when YAML is invalid."""
        settings = Settings(llm_config_path=invalid_yaml_file)
        providers = settings.llm_providers
        
        # Should only contain built-in providers when YAML is invalid
        from tarsy.config.builtin_config import get_builtin_llm_providers
        builtin_providers = get_builtin_llm_providers()
        
        # Verify all built-in providers are present 
        for provider_name in builtin_providers:
            assert provider_name in providers
            
        # Should not contain any custom providers due to YAML failure
        assert len(providers) == len(builtin_providers)
        
        # The provider keys should match exactly the built-in ones
        assert set(providers.keys()) == set(builtin_providers.keys())
    
    def test_yaml_provider_validation_invalid_type(self):
        """Test validation fails fast with invalid provider type."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            content = {
                'llm_providers': {
                    'invalid-provider': {
                        'type': 'unsupported-type',  # Invalid type
                        'model': 'some-model',
                        'api_key_env': 'SOME_KEY'
                    }
                }
            }
            import yaml
            yaml.safe_dump(content, f)
            
            # Should raise ValueError for invalid configuration
            settings = Settings(llm_config_path=f.name)
            with pytest.raises(ValueError, match="Invalid LLM provider configurations"):
                _ = settings.llm_providers
            
            os.unlink(f.name)
    
    def test_yaml_provider_validation_missing_fields(self, missing_fields_yaml_file):
        """Test validation fails fast with missing required fields."""
        settings = Settings(llm_config_path=missing_fields_yaml_file)
        
        # Should raise ValueError for invalid configuration (missing required fields)
        with pytest.raises(ValueError, match="Invalid LLM provider configurations"):
            _ = settings.llm_providers


@pytest.mark.unit
class TestSettingsTemplateDefaults:
    """Test template variable defaults functionality."""
    
    def test_get_template_default_kubeconfig(self):
        """Test getting kubeconfig template default."""
        settings = Settings()
        
        kubeconfig_default = settings.get_template_default('KUBECONFIG')
        
        assert kubeconfig_default is not None
        assert kubeconfig_default.endswith('/.kube/config')
        # Should expand tilde
        assert '~' not in kubeconfig_default
    
    def test_get_template_default_unknown_variable(self):
        """Test getting default for unknown template variable."""
        settings = Settings()
        
        result = settings.get_template_default('UNKNOWN_VAR')
        
        assert result is None
    
    def test_get_template_default_case_handling(self):
        """Test that template variable name case is handled correctly."""
        settings = Settings()
        
        # Should convert KUBECONFIG -> kubeconfig_default
        result = settings.get_template_default('KUBECONFIG')
        assert result is not None
        
        # Should handle mixed case
        result_lower = settings.get_template_default('kubeconfig')
        assert result_lower is not None


@pytest.mark.unit
class TestSettingsLLMConfiguration:
    """Test LLM configuration retrieval and validation."""
    
    def test_get_llm_config_success(self):
        """Test successful LLM config retrieval."""
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-google-key"}, clear=False):
            settings = Settings()

            # Get config for built-in provider
            config = settings.get_llm_config("google-default")

            assert config.type == LLMProviderType.GOOGLE
            assert config.api_key == "test-google-key"
            assert hasattr(config, 'disable_ssl_verification')
    
    def test_get_llm_config_unknown_provider(self):
        """Test error for unknown provider."""
        settings = Settings()
        
        with pytest.raises(ValueError, match="Unsupported LLM provider: unknown-provider"):
            settings.get_llm_config("unknown-provider")
    
    def test_get_llm_config_api_key_mapping(self):
        """Test correct API key mapping by provider type."""
        with patch.dict(
            os.environ,
            {
                "GOOGLE_API_KEY": "google-key",
                "OPENAI_API_KEY": "openai-key",
                "XAI_API_KEY": "xai-key",
                "ANTHROPIC_API_KEY": "anthropic-key"
            },
            clear=False
        ):
            settings = Settings()

            # Test each provider type gets correct API key from env vars
            google_config = settings.get_llm_config("google-default")
            assert google_config.api_key == "google-key"

            openai_config = settings.get_llm_config("openai-default")
            assert openai_config.api_key == "openai-key"

            xai_config = settings.get_llm_config("xai-default")
            assert xai_config.api_key == "xai-key"

            anthropic_config = settings.get_llm_config("anthropic-default")
            assert anthropic_config.api_key == "anthropic-key"
    
    def test_get_llm_config_ssl_verification_setting(self):
        """Test SSL verification setting is included in config."""
        settings = Settings(
            google_api_key="test-key",
            disable_ssl_verification=True
        )
        
        config = settings.get_llm_config("google-default")
        
        assert config.disable_ssl_verification is True
    
    def test_get_llm_config_max_tool_result_tokens(self):
        """Test that max_tool_result_tokens are included in LLM config."""
        settings = Settings(
            openai_api_key="test-openai-key",
            google_api_key="test-google-key",
            xai_api_key="test-xai-key",
            anthropic_api_key="test-anthropic-key"
        )
        
        # Test each built-in provider has correct max_tool_result_tokens
        openai_config = settings.get_llm_config("openai-default")
        assert openai_config.max_tool_result_tokens == 250000
        
        google_config = settings.get_llm_config("google-default")
        assert google_config.max_tool_result_tokens == 950000
        
        xai_config = settings.get_llm_config("xai-default")
        assert xai_config.max_tool_result_tokens == 200000
        
        anthropic_config = settings.get_llm_config("anthropic-default")
        assert anthropic_config.max_tool_result_tokens == 150000

    def test_get_llm_config_builtin_provider_uses_standard_env_var(self):
        """Test that built-in providers read from their standard environment variables."""
        # For built-in providers, api_key_env matches the standard env var name
        # So both primary and fallback paths read from the same env var
        with patch.dict(
            os.environ,
            {
                "GOOGLE_API_KEY": "google-test-key",
                "OPENAI_API_KEY": "openai-test-key"
            },
            clear=False
        ):
            settings = Settings()

            google_config = settings.get_llm_config("google-default")
            assert google_config.api_key == "google-test-key"

            openai_config = settings.get_llm_config("openai-default")
            assert openai_config.api_key == "openai-test-key"

    def test_get_llm_config_custom_env_var_takes_precedence(self):
        """Test that custom api_key_env takes precedence over standard env var for provider type."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            content = {
                'llm_providers': {
                    'custom-openai': {
                        'type': 'openai',
                        'model': 'gpt-4-custom',
                        'api_key_env': 'CUSTOM_OPENAI_KEY'  # Custom env var name
                    }
                }
            }
            import yaml
            yaml.safe_dump(content, f)
            temp_file = f.name

        try:
            # Set both custom env var and standard env var
            with patch.dict(
                os.environ,
                {
                    "CUSTOM_OPENAI_KEY": "custom-value",  # Should use this
                    "OPENAI_API_KEY": "standard-value"    # Should NOT use this
                },
                clear=False
            ):
                settings = Settings(llm_config_path=temp_file)
                config = settings.get_llm_config("custom-openai")

                # Should use CUSTOM_OPENAI_KEY (from api_key_env), not OPENAI_API_KEY
                assert config.api_key == "custom-value"
        finally:
            os.unlink(temp_file)

    def test_get_llm_config_custom_env_var_fallback_to_standard(self):
        """Test fallback to standard env var when custom api_key_env is not set."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            content = {
                'llm_providers': {
                    'custom-openai': {
                        'type': 'openai',
                        'model': 'gpt-4-custom',
                        'api_key_env': 'CUSTOM_OPENAI_KEY'
                    }
                }
            }
            import yaml
            yaml.safe_dump(content, f)
            temp_file = f.name

        try:
            # Don't set CUSTOM_OPENAI_KEY, but set OPENAI_API_KEY
            with patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "fallback-value"},
                clear=False
            ):
                # Make sure CUSTOM_OPENAI_KEY is not set
                env_clean = {k: v for k, v in os.environ.items() if k != "CUSTOM_OPENAI_KEY"}
                env_clean["OPENAI_API_KEY"] = "fallback-value"

                with patch.dict(os.environ, env_clean, clear=True):
                    settings = Settings(llm_config_path=temp_file)
                    config = settings.get_llm_config("custom-openai")

                    # Should fall back to OPENAI_API_KEY (Settings field reads from env var)
                    assert config.api_key == "fallback-value"
        finally:
            os.unlink(temp_file)

    def test_get_llm_config_custom_env_var_whitespace_fallback(self):
        """Test fallback when custom env var contains only whitespace."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            content = {
                'llm_providers': {
                    'custom-openai': {
                        'type': 'openai',
                        'model': 'gpt-4-custom',
                        'api_key_env': 'CUSTOM_OPENAI_KEY'
                    }
                }
            }
            import yaml
            yaml.safe_dump(content, f)
            temp_file = f.name

        try:
            # Set custom env var to whitespace, standard env var to a value
            with patch.dict(
                os.environ,
                {
                    "CUSTOM_OPENAI_KEY": "   \t\n   ",  # Whitespace only
                    "OPENAI_API_KEY": "fallback-value"
                },
                clear=False
            ):
                settings = Settings(llm_config_path=temp_file)
                config = settings.get_llm_config("custom-openai")

                # Should fall back when custom is whitespace-only
                assert config.api_key == "fallback-value"
        finally:
            os.unlink(temp_file)

    def test_get_llm_config_strips_env_var_whitespace(self):
        """Test that environment variable values have whitespace stripped."""
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "  key-with-spaces  \n"}, clear=False):
            settings = Settings()
            config = settings.get_llm_config("google-default")

            # Should strip whitespace
            assert config.api_key == "key-with-spaces"

    def test_get_llm_config_vertexai_provider_uses_gcp_env_vars(self):
        """Test that VertexAI provider uses GCP standard env vars (project and location)."""
        # Test with both env vars set
        with patch.dict(os.environ, {
            "GOOGLE_CLOUD_PROJECT": "my-project",
            "GOOGLE_CLOUD_LOCATION": "us-central1"
        }, clear=False):
            settings = Settings()
            config = settings.get_llm_config("vertexai-default")

            # Should use env var values
            assert config.project == "my-project"
            assert config.location == "us-central1"

        # Test with only project set (location should use default)
        env_clean = {k: v for k, v in os.environ.items() if k not in ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"]}
        with patch.dict(os.environ, {**env_clean, "GOOGLE_CLOUD_PROJECT": "test-project"}, clear=True):
            settings = Settings()
            config = settings.get_llm_config("vertexai-default")

            # Should use env var for project and default for location
            assert config.project == "test-project"
            assert config.location == "us-east5"  # Default location

        # Test without any env vars set (should use Settings field defaults)
        env_clean = {k: v for k, v in os.environ.items() if k not in ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"]}
        with patch.dict(os.environ, env_clean, clear=True):
            settings = Settings()
            config = settings.get_llm_config("vertexai-default")

            # Should use Settings field defaults
            assert config.project == ""  # google_cloud_project default
            assert config.location == "us-east5"  # google_cloud_location default

    def test_get_llm_config_vertexai_does_not_populate_api_key(self):
        """Test that VertexAI provider does not populate api_key field."""
        with patch.dict(os.environ, {
            "GOOGLE_CLOUD_PROJECT": "my-project"
        }, clear=False):
            settings = Settings()
            config = settings.get_llm_config("vertexai-default")

            # api_key should remain None for VertexAI
            assert config.api_key is None
            assert config.project == "my-project"

    def test_get_llm_config_vertexai_custom_provider_with_different_env_vars(self):
        """Test custom VertexAI provider with custom env var names."""
        from tarsy.models.llm_models import LLMProviderConfig, LLMProviderType
        
        # Create a custom VertexAI provider with different env var names
        custom_provider = LLMProviderConfig(
            type=LLMProviderType.VERTEXAI,
            model="claude-sonnet-4-5@20250929",
            project_env="CUSTOM_PROJECT",
            location_env="CUSTOM_LOCATION"
        )
        
        with patch.dict(os.environ, {
            "CUSTOM_PROJECT": "custom-project",
            "CUSTOM_LOCATION": "europe-west1"
        }, clear=False):
            # Mock get_builtin_llm_providers to include our custom provider
            from tarsy.config.builtin_config import get_builtin_llm_providers
            original_providers = get_builtin_llm_providers()
            custom_providers = {**original_providers, "custom-vertexai": custom_provider}
            
            with patch('tarsy.config.settings.get_builtin_llm_providers', return_value=custom_providers):
                settings = Settings()
                config = settings.get_llm_config("custom-vertexai")

                # Should use custom env var values
                assert config.project == "custom-project"
                assert config.location == "europe-west1"

    def test_get_llm_config_vertexai_fallback_to_settings_fields(self):
        """Test VertexAI provider falls back to Settings fields when env vars not set."""
        # Clean environment
        env_clean = {k: v for k, v in os.environ.items() if k not in ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"]}
        
        with patch.dict(os.environ, env_clean, clear=True):
            # Set values directly on Settings fields
            settings = Settings(
                google_cloud_project="settings-project",
                google_cloud_location="us-west2"
            )
            config = settings.get_llm_config("vertexai-default")

            # Should use Settings field values
            assert config.project == "settings-project"
            assert config.location == "us-west2"

    def test_get_llm_config_vertexai_env_var_takes_precedence_over_settings(self):
        """Test that env vars take precedence over Settings fields for VertexAI."""
        with patch.dict(os.environ, {
            "GOOGLE_CLOUD_PROJECT": "env-project",
            "GOOGLE_CLOUD_LOCATION": "env-location"
        }, clear=False):
            # Set different values on Settings fields
            settings = Settings(
                google_cloud_project="settings-project",
                google_cloud_location="settings-location"
            )
            config = settings.get_llm_config("vertexai-default")

            # Env vars should take precedence
            assert config.project == "env-project"
            assert config.location == "env-location"


@pytest.mark.unit
class TestBuiltinLLMProvidersConfiguration:
    """Test built-in LLM provider configurations from EP-0016."""
    
    def test_builtin_providers_have_max_tool_result_tokens(self):
        """Test that all built-in providers have max_tool_result_tokens configured."""
        from tarsy.config.builtin_config import BUILTIN_LLM_PROVIDERS
        
        expected_limits = {
            "openai-default": 250000,     # Conservative for 272K context
            "google-default": 950000,     # Conservative for 1M context
            "xai-default": 200000,        # Conservative for 256K context
            "anthropic-default": 150000,  # Conservative for 200K context
            "vertexai-default": 150000    # Conservative for 200K context
        }
        
        for provider_name, expected_limit in expected_limits.items():
            assert provider_name in BUILTIN_LLM_PROVIDERS
            provider_config = BUILTIN_LLM_PROVIDERS[provider_name]
            assert hasattr(provider_config, 'max_tool_result_tokens')
            assert provider_config.max_tool_result_tokens == expected_limit
    
    def test_builtin_providers_config_structure(self):
        """Test that built-in provider configs have appropriate fields."""
        from tarsy.config.builtin_config import BUILTIN_LLM_PROVIDERS
        
        for provider_name, config in BUILTIN_LLM_PROVIDERS.items():
            # All providers must have type and model
            assert hasattr(config, 'type'), f"Provider {provider_name} missing type"
            assert hasattr(config, 'model'), f"Provider {provider_name} missing model"
            
            # Check max_tool_result_tokens is present (EP-0016 requirement)
            assert hasattr(config, 'max_tool_result_tokens'), f"Provider {provider_name} missing max_tool_result_tokens"
            assert isinstance(config.max_tool_result_tokens, int), f"Provider {provider_name} max_tool_result_tokens must be int"
            assert config.max_tool_result_tokens > 0, f"Provider {provider_name} max_tool_result_tokens must be positive"

    def test_vertexai_default_uses_project_and_location_env(self):
        """Test that vertexai-default provider uses project_env and location_env."""
        from tarsy.config.builtin_config import BUILTIN_LLM_PROVIDERS
        from tarsy.models.llm_models import LLMProviderType
        
        vertexai_config = BUILTIN_LLM_PROVIDERS["vertexai-default"]
        
        # Should use GCP standard env vars
        assert vertexai_config.project_env == "GOOGLE_CLOUD_PROJECT"
        assert vertexai_config.location_env == "GOOGLE_CLOUD_LOCATION"
        
        # Should be VertexAI type
        assert vertexai_config.type == LLMProviderType.VERTEXAI
        
        # Should NOT have api_key_env set (optional for VertexAI)
        assert vertexai_config.api_key_env is None

    def test_non_vertexai_providers_use_api_key_env(self):
        """Test that non-VertexAI providers use api_key_env."""
        from tarsy.config.builtin_config import BUILTIN_LLM_PROVIDERS
        from tarsy.models.llm_models import LLMProviderType
        
        non_vertexai_providers = [
            ("openai-default", LLMProviderType.OPENAI),
            ("google-default", LLMProviderType.GOOGLE),
            ("xai-default", LLMProviderType.XAI),
            ("anthropic-default", LLMProviderType.ANTHROPIC),
        ]
        
        for provider_name, expected_type in non_vertexai_providers:
            config = BUILTIN_LLM_PROVIDERS[provider_name]
            
            # Should have api_key_env set
            assert config.api_key_env is not None, f"{provider_name} should have api_key_env"
            assert isinstance(config.api_key_env, str), f"{provider_name} api_key_env should be string"
            
            # Should be the expected type
            assert config.type == expected_type
            
            # Should NOT have project_env or location_env
            assert config.project_env is None, f"{provider_name} should not have project_env"
            assert config.location_env is None, f"{provider_name} should not have location_env"


@pytest.mark.unit
class TestSettingsDatabaseURL:
    """Test database URL configuration based on environment."""
    
    def test_database_url_testing_environment(self):
        """Test database URL in testing environment."""
        with patch('tarsy.config.settings.is_testing', return_value=True):
            settings = Settings()
            
            assert settings.database_url == "sqlite:///:memory:"
    
    def test_database_url_production_environment(self):
        """Test database URL in production environment."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            settings = Settings()
            
            assert settings.database_url == "sqlite:///history.db"
    
    def test_database_url_explicit_override(self):
        """Test explicit database URL override."""
        explicit_url = "postgresql://user:pass@host:5432/db"
        
        with patch('tarsy.config.settings.is_testing', return_value=True):
            settings = Settings(database_url=explicit_url)
            
            # Should use explicit URL even in test environment
            assert settings.database_url == explicit_url
    
    def test_postgresql_pool_settings_defaults(self):
        """Test PostgreSQL connection pool settings have correct defaults."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            settings = Settings()
            
            assert settings.postgres_pool_size == 5
            assert settings.postgres_max_overflow == 10
            assert settings.postgres_pool_timeout == 30
            assert settings.postgres_pool_recycle == 3600
            assert settings.postgres_pool_pre_ping is True
    
    def test_postgresql_pool_settings_override(self):
        """Test PostgreSQL connection pool settings can be overridden."""
        settings = Settings(
            postgres_pool_size=15,
            postgres_max_overflow=25,
            postgres_pool_timeout=60,
            postgres_pool_recycle=7200,
            postgres_pool_pre_ping=False
        )
        
        assert settings.postgres_pool_size == 15
        assert settings.postgres_max_overflow == 25
        assert settings.postgres_pool_timeout == 60
        assert settings.postgres_pool_recycle == 7200
        assert settings.postgres_pool_pre_ping is False

    def test_database_url_composed_from_components(self):
        """Test database URL composed from separate components."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            settings = Settings(
                database_host="db.example.com",
                database_port=5433,
                database_user="myuser",
                database_password="mypass",
                database_name="mydb"
            )
            
            expected_url = "postgresql://myuser:mypass@db.example.com:5433/mydb"
            assert settings.database_url == expected_url

    def test_database_url_composed_with_defaults(self):
        """Test database URL composed with default values."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            settings = Settings(database_password="testpass")
            
            # Should use defaults for other components
            expected_url = "postgresql://tarsy:testpass@localhost:5432/tarsy"
            assert settings.database_url == expected_url

    def test_database_url_no_password_falls_back_to_sqlite(self):
        """Test that without password, falls back to SQLite."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            settings = Settings(
                database_host="db.example.com",
                database_user="myuser",
                database_name="mydb"
                # No password provided
            )
            
            # Should fall back to SQLite
            assert settings.database_url == "sqlite:///history.db"

    def test_database_url_empty_password_falls_back_to_sqlite(self):
        """Test that empty password falls back to SQLite."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            settings = Settings(
                database_host="db.example.com", 
                database_password="",  # Empty password
                database_user="myuser"
            )
            
            # Should fall back to SQLite
            assert settings.database_url == "sqlite:///history.db"

    def test_database_url_explicit_overrides_composition(self):
        """Test explicit database_url overrides component composition."""
        explicit_url = "postgresql://explicit:user@explicit.host:9999/explicitdb"
        
        with patch('tarsy.config.settings.is_testing', return_value=False):
            settings = Settings(
                database_url=explicit_url,
                database_host="should.be.ignored.com",
                database_password="should_be_ignored",
                database_user="ignored_user"
            )
            
            # Should use explicit URL, not composed one
            assert settings.database_url == explicit_url

    def test_database_url_testing_overrides_composition(self):
        """Test testing environment overrides component composition."""
        with patch('tarsy.config.settings.is_testing', return_value=True):
            settings = Settings(
                database_host="production.db.com",
                database_password="prodpass",
                database_user="produser"
            )
            
            # Should use in-memory SQLite for testing, ignoring components
            assert settings.database_url == "sqlite:///:memory:"

    def test_database_component_defaults(self):
        """Test database component default values."""
        settings = Settings()
        
        assert settings.database_host == "localhost"
        assert settings.database_port == 5432
        assert settings.database_user == "tarsy"
        assert settings.database_password == ""
        assert settings.database_name == "tarsy"

    def test_database_url_with_special_characters_in_password(self):
        """Test database URL composition with special characters in password."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            settings = Settings(
                database_password="p@ssw0rd!#$%"
            )
            
            # Should compose URL with URL-encoded special characters
            expected_url = "postgresql://tarsy:p%40ssw0rd%21%23%24%25@localhost:5432/tarsy"
            assert settings.database_url == expected_url

    def test_database_configuration_priority_order(self):
        """Test the priority order: explicit URL > composed URL > SQLite fallback."""
        # Test 1: Explicit URL has highest priority
        explicit_url = "postgresql://explicit:pass@host:5432/db"
        with patch('tarsy.config.settings.is_testing', return_value=False):
            settings = Settings(
                database_url=explicit_url,
                database_password="ignored"
            )
            assert settings.database_url == explicit_url

        # Test 2: Composed URL when password provided but no explicit URL
        with patch('tarsy.config.settings.is_testing', return_value=False):
            settings = Settings(database_password="testpass")
            assert settings.database_url == "postgresql://tarsy:testpass@localhost:5432/tarsy"

        # Test 3: SQLite fallback when no explicit URL and no password
        with patch('tarsy.config.settings.is_testing', return_value=False):
            settings = Settings()
            assert settings.database_url == "sqlite:///history.db"
    
    def test_database_url_validation_catches_unencoded_at_symbol(self):
        """Test that validator catches unencoded @ symbol in password."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            with pytest.raises(ValueError) as exc_info:
                Settings(
                    database_url="postgresql://user:p@ssword@localhost:5432/db"
                )
            
            # Check error message contains helpful information
            error_msg = str(exc_info.value)
            assert "DATABASE_URL CONFIGURATION ERROR" in error_msg
            assert "special characters" in error_msg.lower()
            assert "'@'" in error_msg
            assert "SOLUTION 1" in error_msg
            assert "DATABASE_USER" in error_msg
            assert "SOLUTION 2" in error_msg
            assert "URL-encode" in error_msg
    
    def test_database_url_validation_catches_multiple_special_chars(self):
        """Test that validator catches multiple special characters."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            with pytest.raises(ValueError) as exc_info:
                Settings(
                    database_url="postgresql://user:p#ssw0rd$!@localhost:5432/db"
                )
            
            error_msg = str(exc_info.value)
            # When URL parsing fails completely due to special chars, we show a generic error
            assert "DATABASE_URL CONFIGURATION ERROR" in error_msg
            assert "special characters" in error_msg.lower()
            # Should suggest solutions
            assert "SOLUTION 1" in error_msg
            assert "DATABASE_USER" in error_msg
            assert "SOLUTION 2" in error_msg
            assert "URL-encode" in error_msg
    
    def test_database_url_validation_allows_encoded_special_chars(self):
        """Test that properly encoded special characters pass validation."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            # This should NOT raise an error - password is properly encoded
            settings = Settings(
                database_url="postgresql://user:p%40ssw0rd@localhost:5432/db"
            )
            assert settings.database_url == "postgresql://user:p%40ssw0rd@localhost:5432/db"
    
    def test_database_url_validation_allows_simple_passwords(self):
        """Test that simple passwords without special chars pass validation."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            settings = Settings(
                database_url="postgresql://user:simplepass123@localhost:5432/db"
            )
            assert settings.database_url == "postgresql://user:simplepass123@localhost:5432/db"
    
    def test_database_url_validation_skips_sqlite(self):
        """Test that SQLite URLs are not validated for special characters."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            # SQLite URLs should not be validated, even with weird characters
            settings = Settings(
                database_url="sqlite:///path/with/@special#chars.db"
            )
            assert settings.database_url == "sqlite:///path/with/@special#chars.db"
    
    def test_database_url_validation_skips_urls_without_password(self):
        """Test that URLs without password are not validated."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            # URLs without password should pass validation
            settings = Settings(
                database_url="postgresql://user@localhost:5432/db"
            )
            assert settings.database_url == "postgresql://user@localhost:5432/db"
    
    def test_database_url_validation_error_message_suggests_solutions(self):
        """Test that error message provides actionable solutions."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            with pytest.raises(ValueError) as exc_info:
                Settings(
                    database_url="postgresql://myuser:my@pass@db.example.com:5432/mydb"
                )
            
            error_msg = str(exc_info.value)
            
            # Should provide clear error message and solutions
            assert "DATABASE_URL CONFIGURATION ERROR" in error_msg
            assert "SOLUTION 1" in error_msg
            assert "DATABASE_USER=myuser" in error_msg
            assert "DATABASE_HOST=db.example.com" in error_msg
            assert "DATABASE_PORT=5432" in error_msg
            assert "DATABASE_NAME=mydb" in error_msg
            assert "SOLUTION 2" in error_msg
            assert "URL-encode" in error_msg
    
    def test_database_url_strips_whitespace(self):
        """Test that DATABASE_URL automatically strips whitespace and newlines."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            # Test with trailing newline
            settings = Settings(database_url="postgresql://user:pass@host:5432/db\n")
            assert settings.database_url == "postgresql://user:pass@host:5432/db"
            
            # Test with leading/trailing spaces
            settings = Settings(database_url="  postgresql://user:pass@host:5432/db  ")
            assert settings.database_url == "postgresql://user:pass@host:5432/db"
            
            # Test with tabs and newlines
            settings = Settings(database_url="\tpostgresql://user:pass@host:5432/db\n\t")
            assert settings.database_url == "postgresql://user:pass@host:5432/db"
    
    def test_database_url_empty_string_not_modified(self):
        """Test that empty DATABASE_URL triggers SQLite fallback."""
        with patch('tarsy.config.settings.is_testing', return_value=False):
            settings = Settings(database_url="")
            assert settings.database_url == "sqlite:///history.db"  # Falls back to SQLite


@pytest.mark.unit
class TestSettingsAPIKeyStripping:
    """Test API key whitespace stripping functionality."""
    
    @pytest.mark.parametrize(
        "api_key_field,input_value,expected_value",
        [
            # Google API key tests
            ("google_api_key", "   test-google-key", "test-google-key"),
            ("google_api_key", "test-google-key   ", "test-google-key"),
            ("google_api_key", "   test-google-key   ", "test-google-key"),
            ("google_api_key", "\ttest-google-key\t", "test-google-key"),
            ("google_api_key", "\ntest-google-key\n", "test-google-key"),
            ("google_api_key", "  \t\n test-google-key \n\t  ", "test-google-key"),
            ("google_api_key", "test-google-key", "test-google-key"),
            # OpenAI API key tests
            ("openai_api_key", "   test-openai-key", "test-openai-key"),
            ("openai_api_key", "test-openai-key   ", "test-openai-key"),
            ("openai_api_key", "   test-openai-key   ", "test-openai-key"),
            ("openai_api_key", "\ttest-openai-key\t", "test-openai-key"),
            # xAI API key tests
            ("xai_api_key", "   test-xai-key", "test-xai-key"),
            ("xai_api_key", "test-xai-key   ", "test-xai-key"),
            ("xai_api_key", "   test-xai-key   ", "test-xai-key"),
            # Anthropic API key tests
            ("anthropic_api_key", "   test-anthropic-key", "test-anthropic-key"),
            ("anthropic_api_key", "test-anthropic-key   ", "test-anthropic-key"),
            ("anthropic_api_key", "   test-anthropic-key   ", "test-anthropic-key"),
            # GCP project and location tests
            ("google_cloud_project", "   my-project", "my-project"),
            ("google_cloud_project", "my-project   ", "my-project"),
            ("google_cloud_project", "   my-project   ", "my-project"),
            ("google_cloud_location", "   us-east5", "us-east5"),
            ("google_cloud_location", "us-east5   ", "us-east5"),
            ("google_cloud_location", "   us-east5   ", "us-east5"),
        ],
    )
    def test_api_key_whitespace_stripping(
        self, api_key_field: str, input_value: str, expected_value: str
    ) -> None:
        """Test that API keys and GCP config have whitespace stripped during Settings initialization."""
        settings = Settings(**{api_key_field: input_value})
        
        actual_value = getattr(settings, api_key_field)
        assert actual_value == expected_value
    
    @pytest.mark.parametrize(
        "api_key_field",
        ["google_api_key", "openai_api_key", "xai_api_key", "anthropic_api_key"],
    )
    def test_api_key_empty_string_preserved(self, api_key_field: str) -> None:
        """Test that empty strings are preserved (not converted to None)."""
        settings = Settings(**{api_key_field: ""})
        
        actual_value = getattr(settings, api_key_field)
        assert actual_value == ""
    
    @pytest.mark.parametrize(
        "api_key_field",
        ["google_api_key", "openai_api_key", "xai_api_key", "anthropic_api_key"],
    )
    def test_api_key_whitespace_only_becomes_empty(self, api_key_field: str) -> None:
        """Test that whitespace-only strings become empty after stripping."""
        settings = Settings(**{api_key_field: "   \t\n   "})
        
        actual_value = getattr(settings, api_key_field)
        assert actual_value == ""
    
    def test_all_api_keys_stripped_together(self) -> None:
        """Test that all API keys are stripped when provided together."""
        settings = Settings(
            google_api_key="   google-key   ",
            openai_api_key="  openai-key  ",
            xai_api_key="\txai-key\t",
            anthropic_api_key="\nanthropic-key\n"
        )
        
        assert settings.google_api_key == "google-key"
        assert settings.openai_api_key == "openai-key"
        assert settings.xai_api_key == "xai-key"
        assert settings.anthropic_api_key == "anthropic-key"
    
    def test_api_key_stripping_with_internal_spaces_preserved(self) -> None:
        """Test that internal spaces within API keys are preserved."""
        settings = Settings(
            google_api_key="   key with spaces   "
        )
        
        # Internal spaces should be preserved, only leading/trailing stripped
        assert settings.google_api_key == "key with spaces"
    
    def test_api_key_real_world_grpc_scenario(self) -> None:
        """Test real-world scenario where gRPC metadata error would occur."""
        # Simulate a scenario where API key has trailing newline (common from env files)
        settings = Settings(
            google_api_key="dummy-key\n"
        )
        
        # Should strip the newline to prevent gRPC metadata errors
        assert settings.google_api_key == "dummy-key"
        assert "\n" not in settings.google_api_key


@pytest.mark.unit
class TestGetSettings:
    """Test settings singleton function."""
    
    def test_get_settings_returns_singleton(self):
        """Test that get_settings returns the same instance."""
        # Clear the cache first
        get_settings.cache_clear()
        
        settings1 = get_settings()
        settings2 = get_settings()
        
        assert settings1 is settings2
    
    def test_get_settings_cache_clear(self):
        """Test cache clearing functionality."""
        get_settings.cache_clear()
        
        settings1 = get_settings()
        get_settings.cache_clear()
        settings2 = get_settings()
        
        # Should be different instances after cache clear
        assert settings1 is not settings2
