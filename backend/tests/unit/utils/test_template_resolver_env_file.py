"""
Tests for .env file functionality in TemplateResolver.

This module tests the new .env file loading and priority order functionality
added to the template resolution system.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tarsy.utils.template_resolver import (
    TemplateResolutionError,
    TemplateResolver,
)


@pytest.mark.unit
class TestTemplateResolverEnvFileLoading:
    """Test .env file loading functionality."""
    
    def test_load_valid_env_file(self):
        """Test loading a valid .env file."""
        env_content = """
# Test environment file
TEST_VAR1=value1
TEST_VAR2=value2
TEST_VAR3="quoted_value"
TEST_VAR4='single_quoted'
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                resolver = TemplateResolver(env_file_path=f.name)
                
                # Verify variables were loaded (quotes now preserved)
                assert resolver.env_file_vars['TEST_VAR1'] == 'value1'
                assert resolver.env_file_vars['TEST_VAR2'] == 'value2'
                assert resolver.env_file_vars['TEST_VAR3'] == '"quoted_value"'  # Quotes preserved
                assert resolver.env_file_vars['TEST_VAR4'] == "'single_quoted'"  # Quotes preserved
                
                # Verify resolution works
                config = {"key": "${TEST_VAR1}"}
                result = resolver.resolve_configuration(config)
                assert result == {"key": "value1"}
                
            finally:
                os.unlink(f.name)
    
    def test_missing_env_file_no_error(self):
        """Test that missing .env file doesn't cause errors."""
        resolver = TemplateResolver(env_file_path="/nonexistent/path/.env")
        
        # Should not raise error
        assert resolver.env_file_vars == {}
        
        # Should still work with system environment
        with patch.dict(os.environ, {'TEST_VAR': 'system_value'}):
            config = {"key": "${TEST_VAR}"}
            result = resolver.resolve_configuration(config)
            assert result == {"key": "system_value"}
    
    def test_malformed_env_file_lines_skipped(self):
        """Test ultra-simple parsing - only lines without equals are skipped."""
        env_content = """
# Valid lines
VALID_VAR1=value1
VALID_VAR2=value2

# Lines without equals (should be skipped)
INVALID_LINE_NO_EQUALS
=NO_KEY_BEFORE_EQUALS

# Variables with non-standard names (loaded but may cause issues during template resolution)
123INVALID_NAME=value
INVALID-NAME=value

# More valid lines
VALID_VAR3=value3
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                resolver = TemplateResolver(env_file_path=f.name)
                
                # Valid variables should be loaded
                assert resolver.env_file_vars['VALID_VAR1'] == 'value1'
                assert resolver.env_file_vars['VALID_VAR2'] == 'value2'
                assert resolver.env_file_vars['VALID_VAR3'] == 'value3'
                
                # Non-standard variable names are now loaded (no validation)
                assert resolver.env_file_vars['123INVALID_NAME'] == 'value'
                assert resolver.env_file_vars['INVALID-NAME'] == 'value'
                
                # Lines without equals should not be loaded
                assert 'INVALID_LINE_NO_EQUALS' not in resolver.env_file_vars
                
                # Empty key is now loaded too (ultra-simple logic)
                assert resolver.env_file_vars[''] == 'NO_KEY_BEFORE_EQUALS'
                
                # Should have 6 loaded variables (3 standard + 2 non-standard + 1 empty key)
                assert len(resolver.env_file_vars) == 6
                
            finally:
                os.unlink(f.name)
    
    def test_env_file_quote_handling(self):
        """Test that quotes are preserved as-is (no quote stripping)."""
        env_content = '''
UNQUOTED=plain_value
DOUBLE_QUOTED="double quoted value"
SINGLE_QUOTED='single quoted value'
MIXED_QUOTES="value with 'single' quotes inside"
EMPTY_QUOTES=""
EMPTY_SINGLE_QUOTES=''
SPACES_AROUND = spaced_value 
'''
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                resolver = TemplateResolver(env_file_path=f.name)
                
                # All quotes are now preserved (no quote stripping)
                assert resolver.env_file_vars['UNQUOTED'] == 'plain_value'
                assert resolver.env_file_vars['DOUBLE_QUOTED'] == '"double quoted value"'  # Quotes preserved
                assert resolver.env_file_vars['SINGLE_QUOTED'] == "'single quoted value'"  # Quotes preserved
                assert resolver.env_file_vars['MIXED_QUOTES'] == '"value with \'single\' quotes inside"'  # Quotes preserved
                assert resolver.env_file_vars['EMPTY_QUOTES'] == '""'  # Quotes preserved
                assert resolver.env_file_vars['EMPTY_SINGLE_QUOTES'] == "''"  # Quotes preserved
                assert resolver.env_file_vars['SPACES_AROUND'] == 'spaced_value'  # Spaces still trimmed
                
            finally:
                os.unlink(f.name)
    
    def test_env_file_comments_and_empty_lines(self):
        """Test that comments and empty lines are properly handled."""
        env_content = """
# This is a comment at the start

# Another comment
VALID_VAR1=value1

# More comments
VALID_VAR2=value2   # inline comment should be part of value



VALID_VAR3=value3
# Final comment
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                resolver = TemplateResolver(env_file_path=f.name)
                
                assert resolver.env_file_vars['VALID_VAR1'] == 'value1'
                assert resolver.env_file_vars['VALID_VAR2'] == 'value2   # inline comment should be part of value'
                assert resolver.env_file_vars['VALID_VAR3'] == 'value3'
                assert len(resolver.env_file_vars) == 3
                
            finally:
                os.unlink(f.name)


@pytest.mark.unit  
class TestTemplateResolverPriorityOrder:
    """Test the priority order: .env file > system env > settings defaults."""
    
    def test_env_file_overrides_system_environment(self):
        """Test that .env file variables take priority over system environment."""
        env_content = "PRIORITY_TEST=env_file_value\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                # Set system environment variable
                with patch.dict(os.environ, {'PRIORITY_TEST': 'system_env_value'}):
                    resolver = TemplateResolver(env_file_path=f.name)
                    
                    config = {"key": "${PRIORITY_TEST}"}
                    result = resolver.resolve_configuration(config)
                    
                    # Should use .env file value, not system environment
                    assert result == {"key": "env_file_value"}
                    
            finally:
                os.unlink(f.name)
    
    def test_system_environment_overrides_settings_defaults(self):
        """Test that system environment takes priority over settings defaults."""
        # Create empty .env file (no PRIORITY_TEST)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("")
            f.flush()
            
            try:
                # Mock settings with default
                mock_settings = MagicMock()
                mock_settings.get_template_default.return_value = "settings_default_value"
                
                with patch.dict(os.environ, {'PRIORITY_TEST': 'system_env_value'}):
                    resolver = TemplateResolver(settings=mock_settings, env_file_path=f.name)
                    
                    config = {"key": "${PRIORITY_TEST}"}
                    result = resolver.resolve_configuration(config)
                    
                    # Should use system environment, not settings default
                    assert result == {"key": "system_env_value"}
                    
            finally:
                os.unlink(f.name)
    
    def test_settings_defaults_used_as_fallback(self):
        """Test that settings defaults are used when variable not in .env or system env."""
        # Create empty .env file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("")
            f.flush()
            
            try:
                # Mock settings with default
                mock_settings = MagicMock()
                mock_settings.get_template_default.return_value = "settings_default_value"
                
                # Ensure variable not in system environment
                with patch.dict(os.environ, {}, clear=True):
                    resolver = TemplateResolver(settings=mock_settings, env_file_path=f.name)
                    
                    config = {"key": "${PRIORITY_TEST}"}
                    result = resolver.resolve_configuration(config)
                    
                    # Should use settings default
                    assert result == {"key": "settings_default_value"}
                    mock_settings.get_template_default.assert_called_with('PRIORITY_TEST')
                    
            finally:
                os.unlink(f.name)
    
    def test_full_priority_order_chain(self):
        """Test the complete priority chain with all three sources."""
        env_content = "HIGH_PRIORITY=env_file_value\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                # Mock settings with defaults
                mock_settings = MagicMock()
                mock_settings.get_template_default.side_effect = lambda var: {
                    'HIGH_PRIORITY': 'settings_default_1',
                    'MEDIUM_PRIORITY': 'settings_default_2', 
                    'LOW_PRIORITY': 'settings_default_3'
                }.get(var)
                
                # Set system environment variables
                with patch.dict(os.environ, {
                    'HIGH_PRIORITY': 'system_env_1',  # Should be overridden by .env
                    'MEDIUM_PRIORITY': 'system_env_2',  # Should be used (not in .env)
                    # LOW_PRIORITY not set - should use settings default
                }):
                    resolver = TemplateResolver(settings=mock_settings, env_file_path=f.name)
                    
                    config = {
                        "high": "${HIGH_PRIORITY}",    # .env file wins
                        "medium": "${MEDIUM_PRIORITY}", # system env wins
                        "low": "${LOW_PRIORITY}"        # settings default wins
                    }
                    result = resolver.resolve_configuration(config)
                    
                    assert result == {
                        "high": "env_file_value",       # From .env file
                        "medium": "system_env_2",       # From system env
                        "low": "settings_default_3"     # From settings default
                    }
                    
            finally:
                os.unlink(f.name)


@pytest.mark.unit
class TestTemplateResolverEnvFileIntegration:
    """Test integration of .env file functionality with existing features."""
    
    def test_env_file_with_complex_mcp_server_config(self):
        """Test .env file resolution in complex MCP server configuration."""
        env_content = """
MCP_SERVER_TOKEN=secret123
MCP_SERVER_URL=https://api.example.com
MCP_SERVER_TIMEOUT=30
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                resolver = TemplateResolver(env_file_path=f.name)
                
                config = {
                    "server_id": "test-server",
                    "server_type": "custom",
                    "enabled": True,
                    "connection_params": {
                        "command": "custom-server",
                        "args": [
                            "--token", "${MCP_SERVER_TOKEN}",
                            "--url", "${MCP_SERVER_URL}",
                            "--timeout", "${MCP_SERVER_TIMEOUT}"
                        ],
                        "env": {
                            "API_TOKEN": "${MCP_SERVER_TOKEN}",
                            "BASE_URL": "${MCP_SERVER_URL}"
                        }
                    },
                    "instructions": "Connect to ${MCP_SERVER_URL} with timeout ${MCP_SERVER_TIMEOUT}s"
                }
                
                result = resolver.resolve_configuration(config)
                
                # Verify all templates were resolved from .env file
                assert result["connection_params"]["args"][1] == "secret123"
                assert result["connection_params"]["args"][3] == "https://api.example.com"
                assert result["connection_params"]["args"][5] == "30"
                assert result["connection_params"]["env"]["API_TOKEN"] == "secret123"
                assert result["connection_params"]["env"]["BASE_URL"] == "https://api.example.com"
                assert "Connect to https://api.example.com with timeout 30s" in result["instructions"]
                
            finally:
                os.unlink(f.name)
    
    def test_env_file_validation_with_mixed_sources(self):
        """Test template validation with variables from different sources."""
        env_content = "ENV_FILE_VAR=value1\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                mock_settings = MagicMock()
                mock_settings.get_template_default.side_effect = lambda var: {
                    'SETTINGS_DEFAULT_VAR': 'default_value'
                }.get(var)
                
                with patch.dict(os.environ, {'SYSTEM_ENV_VAR': 'system_value'}):
                    resolver = TemplateResolver(settings=mock_settings, env_file_path=f.name)
                    
                    # Config with variables from all three sources plus one missing
                    config = {
                        "env_file": "${ENV_FILE_VAR}",          # Available in .env file
                        "system_env": "${SYSTEM_ENV_VAR}",      # Available in system env
                        "settings": "${SETTINGS_DEFAULT_VAR}",  # Available in settings defaults
                        "missing": "${COMPLETELY_MISSING_VAR}"  # Not available anywhere
                    }
                    
                    missing_vars = resolver.validate_templates(config)
                    
                    # Only the completely missing variable should be reported
                    assert missing_vars == ["COMPLETELY_MISSING_VAR"]
                    
            finally:
                os.unlink(f.name)


@pytest.mark.unit
class TestTemplateResolverEnvFileErrorHandling:
    """Test error handling for .env file functionality."""
    
    def test_corrupted_env_file_continues(self):
        """Test that corrupted .env file doesn't break the resolver."""
        # Create a corrupted file (not readable)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write("VALID_VAR=value\n")
            f.flush()
            
            try:
                # Make file unreadable
                os.chmod(f.name, 0o000)
                
                # Should not raise exception, just log warning and continue
                resolver = TemplateResolver(env_file_path=f.name)
                assert resolver.env_file_vars == {}
                
                # Should still work with other sources
                with patch.dict(os.environ, {'TEST_VAR': 'system_value'}):
                    config = {"key": "${TEST_VAR}"}
                    result = resolver.resolve_configuration(config)
                    assert result == {"key": "system_value"}
                    
            finally:
                # Restore permissions and clean up
                try:
                    os.chmod(f.name, 0o644)
                    os.unlink(f.name)
                except Exception:
                    # Allow KeyboardInterrupt/SystemExit to propagate
                    # but silently handle other cleanup errors
                    pass
    
    def test_template_cache_with_env_file(self):
        """Test that template caching works with .env file variables."""
        env_content = "CACHED_VAR=cached_value\n"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write(env_content)
            f.flush()
            
            try:
                resolver = TemplateResolver(env_file_path=f.name)
                
                # Resolve the same variable multiple times
                config1 = {"key": "${CACHED_VAR}"}
                config2 = {"other_key": "${CACHED_VAR}"}
                
                result1 = resolver.resolve_configuration(config1)
                result2 = resolver.resolve_configuration(config2)
                
                assert result1 == {"key": "cached_value"}
                assert result2 == {"other_key": "cached_value"}
                
                # Variable should be cached
                assert "CACHED_VAR" in resolver._template_cache
                assert resolver._template_cache["CACHED_VAR"] == "cached_value"
                
            finally:
                os.unlink(f.name)
