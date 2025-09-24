"""
Tests for template resolution utilities.

This module tests the template variable expansion functionality
used for MCP server configurations.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from tarsy.utils.template_resolver import (
    TemplateResolutionError,
    TemplateResolver,
    resolve_mcp_server_config,
    validate_mcp_server_templates,
)


@pytest.mark.unit
class TestTemplateResolver:
    """Test cases for TemplateResolver class."""
    
    def setup_method(self):
        """Set up test environment before each test."""
        self.resolver = TemplateResolver()
        
        # Create mock settings for testing defaults
        self.mock_settings = MagicMock()
        self.mock_settings.get_template_default.return_value = None
        self.resolver_with_settings = TemplateResolver(settings=self.mock_settings)
    
    def test_resolve_simple_template(self):
        """Test resolving a simple template variable."""
        with patch.dict(os.environ, {'TEST_VAR': 'test_value'}):
            config = {"key": "${TEST_VAR}"}
            result = self.resolver.resolve_configuration(config)
            assert result == {"key": "test_value"}
    
    def test_resolve_multiple_templates_in_string(self):
        """Test resolving multiple template variables in a single string."""
        # Use unique variable names that don't exist in our .env file
        with patch.dict(os.environ, {'TEST_HOST_UNIQUE': 'localhost', 'TEST_PORT_UNIQUE': '8080'}):
            config = {"url": "http://${TEST_HOST_UNIQUE}:${TEST_PORT_UNIQUE}/api"}
            result = self.resolver.resolve_configuration(config)
            assert result == {"url": "http://localhost:8080/api"}
    
    def test_resolve_nested_structure(self):
        """Test resolving templates in nested dictionaries and lists."""
        with patch.dict(os.environ, {'TOKEN': 'secret123', 'MODE': 'production'}):
            config = {
                "server": {
                    "args": ["--token", "${TOKEN}", "--mode", "${MODE}"],
                    "env": {
                        "API_TOKEN": "${TOKEN}"
                    }
                },
                "enabled": True,
                "count": 42
            }
            result = self.resolver.resolve_configuration(config)
            expected = {
                "server": {
                    "args": ["--token", "secret123", "--mode", "production"],
                    "env": {
                        "API_TOKEN": "secret123"
                    }
                },
                "enabled": True,
                "count": 42
            }
            assert result == expected
    
    def test_resolve_mcp_server_config_structure(self):
        """Test resolving templates in typical MCP server configuration."""
        # Use unique variable names that don't exist in our .env file
        with patch.dict(os.environ, {'TEST_KUBECONFIG_UNIQUE': '/path/to/config', 'TEST_NAMESPACE_UNIQUE': 'prod'}):
            config = {
                "server_id": "kubernetes-server",
                "server_type": "kubernetes",
                "enabled": True,
                "transport": {
                    "command": "npx",
                    "args": [
                        "-y", 
                        "kubernetes-mcp-server@latest", 
                        "--kubeconfig", "${TEST_KUBECONFIG_UNIQUE}",
                        "--namespace", "${TEST_NAMESPACE_UNIQUE}"
                    ]
                },
                "instructions": "Use kubeconfig at ${TEST_KUBECONFIG_UNIQUE}"
            }
            result = self.resolver.resolve_configuration(config)
            assert result["transport"]["args"][3] == "/path/to/config"
            assert result["transport"]["args"][5] == "prod"
            assert "Use kubeconfig at /path/to/config" in result["instructions"]
    
    def test_missing_variable_raises_error(self):
        """Test that missing variables raise an error."""
        config = {"key": "${MISSING_VAR}"}
        with pytest.raises(TemplateResolutionError) as exc_info:
            self.resolver.resolve_configuration(config)
        assert "Missing required environment variables" in str(exc_info.value)
        assert "MISSING_VAR" in str(exc_info.value)
    
    def test_settings_default_used_when_env_missing(self):
        """Test that settings defaults are used when environment variables are missing."""
        self.mock_settings.get_template_default.return_value = "default_value"
        config = {"key": "${TEST_VAR}"}
        result = self.resolver_with_settings.resolve_configuration(config)
        assert result == {"key": "default_value"}
        
        # Verify settings was called with correct variable name
        self.mock_settings.get_template_default.assert_called_with("TEST_VAR")
    
    def test_multiple_missing_variables_error(self):
        """Test error message includes all missing variables."""
        config = {
            "key1": "${MISSING_VAR1}",
            "key2": "${MISSING_VAR2}",
            "key3": "normal_value"
        }
        with pytest.raises(TemplateResolutionError) as exc_info:
            self.resolver.resolve_configuration(config)
        error_msg = str(exc_info.value)
        assert "MISSING_VAR1" in error_msg
        assert "MISSING_VAR2" in error_msg
    
    def test_partial_template_resolution(self):
        """Test strings with both templates and regular text."""
        with patch.dict(os.environ, {'API_KEY': 'abc123'}):
            config = {"auth_header": "Bearer ${API_KEY}"}
            result = self.resolver.resolve_configuration(config)
            assert result == {"auth_header": "Bearer abc123"}
    
    def test_no_templates_in_config(self):
        """Test configuration without any templates is unchanged."""
        config = {
            "server": "localhost",
            "port": 8080,
            "enabled": True,
            "args": ["--verbose", "--config", "/path/to/config"]
        }
        result = self.resolver.resolve_configuration(config)
        assert result == config
    
    def test_empty_configuration(self):
        """Test empty configuration."""
        result = self.resolver.resolve_configuration({})
        assert result == {}
    
    def test_invalid_template_syntax_ignored(self):
        """Test that invalid template syntax is left unchanged."""
        config = {
            "invalid1": "$MISSING_BRACES",
            "invalid2": "${",
            "invalid3": "${}",
            "valid": "${VALID_VAR}"
        }
        with patch.dict(os.environ, {'VALID_VAR': 'valid_value'}):
            result = self.resolver.resolve_configuration(config)
            assert result["invalid1"] == "$MISSING_BRACES"
            assert result["invalid2"] == "${"
            assert result["invalid3"] == "${}"
            assert result["valid"] == "valid_value"
    
    def test_validate_templates(self):
        """Test template validation functionality."""
        config = {
            "key1": "${EXISTING_VAR}",
            "key2": "${MISSING_VAR}",
            "key3": "no_template"
        }
        with patch.dict(os.environ, {'EXISTING_VAR': 'value'}):
            missing_vars = self.resolver.validate_templates(config)
            assert missing_vars == ["MISSING_VAR"]
    
    def test_get_template_variables(self):
        """Test extraction of template variable names."""
        config = {
            "key1": "${VAR1}",
            "key2": "prefix_${VAR2}_suffix",
            "key3": "${VAR1}",  # Duplicate should appear once
            "key4": "no_template",
            "nested": {
                "key5": "${VAR3}"
            }
        }
        template_vars = self.resolver.get_template_variables(config)
        assert sorted(template_vars) == ["VAR1", "VAR2", "VAR3"]
    
    def test_template_caching(self):
        """Test that resolved variables are cached."""
        with patch.dict(os.environ, {'CACHED_VAR': 'cached_value'}):
            # First resolution should cache the variable
            config1 = {"key": "${CACHED_VAR}"}
            result1 = self.resolver.resolve_configuration(config1)
            
            # Second resolution should use cached value
            config2 = {"other_key": "${CACHED_VAR}"}
            result2 = self.resolver.resolve_configuration(config2)
            
            assert result1 == {"key": "cached_value"}
            assert result2 == {"other_key": "cached_value"}
            assert "CACHED_VAR" in self.resolver._template_cache


@pytest.mark.unit
class TestConvenienceFunctions:
    """Test cases for convenience functions."""
    
    def test_resolve_mcp_server_config_success(self):
        """Test the convenience function for MCP server config resolution."""
        with patch.dict(os.environ, {'SERVER_TOKEN': 'token123'}):
            config = {
                "server_id": "test-server",
                "transport": {
                    "args": ["--token", "${SERVER_TOKEN}"]
                }
            }
            result = resolve_mcp_server_config(config)
            assert result["transport"]["args"][1] == "token123"
    
    def test_resolve_mcp_server_config_missing_var(self):
        """Test convenience function with missing variable."""
        config = {
            "server_id": "test-server",
            "transport": {
                "args": ["--token", "${MISSING_TOKEN}"]
            }
        }
        with pytest.raises(TemplateResolutionError):
            resolve_mcp_server_config(config)
    
    def test_resolve_mcp_server_config_with_settings_default(self):
        """Test convenience function using settings defaults."""
        mock_settings = MagicMock()
        mock_settings.get_template_default.return_value = "default_token"
        
        config = {
            "server_id": "test-server",
            "transport": {
                "args": ["--token", "${SERVER_TOKEN}"]
            }
        }
        result = resolve_mcp_server_config(config, settings=mock_settings)
        assert result["transport"]["args"][1] == "default_token"
    
    def test_validate_mcp_server_templates(self):
        """Test the convenience function for template validation."""
        config = {
            "transport": {
                "args": ["--token", "${MISSING_TOKEN}", "--host", "${MISSING_HOST}"]
            }
        }
        missing_vars = validate_mcp_server_templates(config)
        assert sorted(missing_vars) == ["MISSING_HOST", "MISSING_TOKEN"]


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def setup_method(self):
        """Set up test environment."""
        self.resolver = TemplateResolver()
    
    def test_nested_empty_structures(self):
        """Test nested empty dictionaries and lists."""
        config = {
            "empty_dict": {},
            "empty_list": [],
            "nested_empty": {
                "inner_dict": {},
                "inner_list": []
            }
        }
        result = self.resolver.resolve_configuration(config)
        assert result == config
    
    def test_none_values(self):
        """Test handling of None values."""
        config = {
            "null_value": None,
            "template": "${TEST_VAR}",
            "nested": {
                "also_null": None
            }
        }
        with patch.dict(os.environ, {'TEST_VAR': 'resolved'}):
            result = self.resolver.resolve_configuration(config)
            assert result["null_value"] is None
            assert result["template"] == "resolved"
            assert result["nested"]["also_null"] is None
    
    def test_numeric_and_boolean_values(self):
        """Test that non-string values are preserved."""
        config = {
            "integer": 42,
            "float": 3.14,
            "boolean_true": True,
            "boolean_false": False,
            "template": "${TEST_VAR}"
        }
        with patch.dict(os.environ, {'TEST_VAR': 'string_value'}):
            result = self.resolver.resolve_configuration(config)
            assert result["integer"] == 42
            assert result["float"] == 3.14
            assert result["boolean_true"] is True
            assert result["boolean_false"] is False
            assert result["template"] == "string_value"
    
    def test_empty_string_template_value(self):
        """Test template variable that resolves to empty string."""
        with patch.dict(os.environ, {'EMPTY_VAR': ''}):
            config = {"key": "${EMPTY_VAR}"}
            result = self.resolver.resolve_configuration(config)
            assert result == {"key": ""}
    
    def test_whitespace_template_value(self):
        """Test template variable that resolves to whitespace."""
        with patch.dict(os.environ, {'SPACE_VAR': '   '}):
            config = {"key": "${SPACE_VAR}"}
            result = self.resolver.resolve_configuration(config)
            assert result == {"key": "   "}


@pytest.mark.unit
class TestVariableNamingRules:
    """Test variable naming rules and patterns."""
    
    def setup_method(self):
        """Set up test environment."""
        self.resolver = TemplateResolver()
    
    def test_valid_variable_names(self):
        """Test various valid variable name patterns."""
        valid_vars = {
            'SIMPLE': 'value1',
            'WITH_UNDERSCORE': 'value2', 
            'MULTIPLE_UNDER_SCORES': 'value3',
            'MIXED123': 'value4',
            'A': 'value5',  # Single character
            'VERY_LONG_VARIABLE_NAME_WITH_MANY_PARTS': 'value6'
        }
        
        config = {var: f"${{{var}}}" for var in valid_vars}
        
        with patch.dict(os.environ, valid_vars):
            result = self.resolver.resolve_configuration(config)
            for var, expected_value in valid_vars.items():
                assert result[var] == expected_value
    
    def test_invalid_variable_names_ignored(self):
        """Test that invalid variable names are not treated as templates."""
        # These should not be recognized as valid template variables
        config = {
            "lowercase": "${lowercase_var}",      # lowercase not matched
            "starts_digit": "${123VAR}",          # starts with digit
            "special_chars": "${VAR-WITH-DASH}",  # contains dash
            "empty_name": "${}",                  # empty variable name
        }
        
        # None of these should be recognized as templates, so no error should occur
        result = self.resolver.resolve_configuration(config)
        assert result == config  # Should be unchanged