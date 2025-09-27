"""
Unit tests for Settings module.

Tests critical configuration loading, validation, and template functionality.
"""

import os
import tempfile
import pytest
from unittest.mock import patch

from tarsy.config.settings import Settings, is_testing, get_settings


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
        assert custom_openai.type == 'openai'
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
        """Test validation rejects providers with invalid type."""
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
            
            with patch('tarsy.utils.logger.get_module_logger') as mock_get_logger:
                mock_logger = mock_get_logger.return_value
                settings = Settings(llm_config_path=f.name)
                providers = settings.llm_providers
                
                # Should log validation error
                mock_logger.error.assert_called()
                error_message = str(mock_logger.error.call_args)
                # Pydantic validation error should mention the field validation failure
                assert ("validation error" in error_message.lower() and 
                       ("type" in error_message.lower() or "literal_error" in error_message.lower()))
                
                # Invalid provider should not be included
                assert 'invalid-provider' not in providers
            
            os.unlink(f.name)
    
    def test_yaml_provider_validation_missing_fields(self, missing_fields_yaml_file):
        """Test validation rejects providers with missing required fields."""
        settings = Settings(llm_config_path=missing_fields_yaml_file)
        providers = settings.llm_providers
        
        # Invalid provider should not be included due to missing required fields
        assert 'incomplete-provider' not in providers
        
        # Should only contain valid built-in providers
        from tarsy.config.builtin_config import get_builtin_llm_providers
        builtin_providers = get_builtin_llm_providers()
        
        # All returned providers should be built-in ones (invalid provider rejected)
        for provider_name in providers:
            assert provider_name in builtin_providers


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
        settings = Settings(
            google_api_key="test-google-key",
            openai_api_key="test-openai-key"
        )
        
        # Get config for built-in provider
        config = settings.get_llm_config("google-default")
        
        assert config.type == 'google'
        assert config.api_key == "test-google-key"
        assert hasattr(config, 'disable_ssl_verification')
    
    def test_get_llm_config_unknown_provider(self):
        """Test error for unknown provider."""
        settings = Settings()
        
        with pytest.raises(ValueError, match="Unsupported LLM provider: unknown-provider"):
            settings.get_llm_config("unknown-provider")
    
    def test_get_llm_config_api_key_mapping(self):
        """Test correct API key mapping by provider type."""
        settings = Settings(
            google_api_key="google-key",
            openai_api_key="openai-key", 
            xai_api_key="xai-key",
            anthropic_api_key="anthropic-key"
        )
        
        # Test each provider type gets correct API key
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
            "anthropic-default": 150000   # Conservative for 200K context
        }
        
        for provider_name, expected_limit in expected_limits.items():
            assert provider_name in BUILTIN_LLM_PROVIDERS
            provider_config = BUILTIN_LLM_PROVIDERS[provider_name]
            assert hasattr(provider_config, 'max_tool_result_tokens')
            assert provider_config.max_tool_result_tokens == expected_limit
    
    def test_builtin_providers_config_structure(self):
        """Test that built-in provider configs have all required fields."""
        from tarsy.config.builtin_config import BUILTIN_LLM_PROVIDERS
        
        required_fields = {"type", "model", "api_key_env", "temperature"}
        optional_fields = {"base_url", "verify_ssl", "max_tool_result_tokens"}
        
        for provider_name, config in BUILTIN_LLM_PROVIDERS.items():
            # Check all required fields are present
            for field in required_fields:
                assert hasattr(config, field), f"Provider {provider_name} missing required field: {field}"
            
            # Check max_tool_result_tokens is present (EP-0016 requirement)
            assert hasattr(config, 'max_tool_result_tokens'), f"Provider {provider_name} missing max_tool_result_tokens"
            assert isinstance(config.max_tool_result_tokens, int), f"Provider {provider_name} max_tool_result_tokens must be int"
            assert config.max_tool_result_tokens > 0, f"Provider {provider_name} max_tool_result_tokens must be positive"


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
            
            # Should compose URL with special characters
            expected_url = "postgresql://tarsy:p@ssw0rd!#$%@localhost:5432/tarsy"
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
