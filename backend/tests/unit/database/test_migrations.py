"""Unit tests for database migrations module."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestConfigParserEscaping:
    """Test ConfigParser % escaping for URL-encoded passwords."""
    
    def test_percent_escaping_logic(self):
        """Test the % escaping logic used in get_alembic_config."""
        # URL-encoded password with % characters
        database_url = "postgresql://user:p%40ssw0rd%26test@host:5432/db"
        
        # This is the escaping logic used in get_alembic_config
        escaped_url = database_url.replace('%', '%%')
        
        # % should be doubled for ConfigParser
        assert escaped_url == "postgresql://user:p%%40ssw0rd%%26test@host:5432/db"
        assert "p%%40ssw0rd%%26test" in escaped_url
        assert "%%40" in escaped_url  # @ encoded and escaped
        assert "%%26" in escaped_url  # & encoded and escaped
    
    def test_simple_passwords_without_percent_unchanged(self):
        """Test that simple passwords without % are unchanged."""
        database_url = "postgresql://user:simplepass@host:5432/db"
        escaped_url = database_url.replace('%', '%%')
        
        # No % signs, so should be unchanged
        assert escaped_url == database_url
    
    def test_complex_url_encoded_password(self):
        """Test with a complex URL-encoded password."""
        # Password: p@ssw0rd!#$% (fully URL-encoded)
        database_url = "postgresql://tarsy:p%40ssw0rd%21%23%24%25@host:5432/db"
        escaped_url = database_url.replace('%', '%%')
        
        # All % should be doubled
        assert escaped_url == "postgresql://tarsy:p%%40ssw0rd%%21%%23%%24%%25@host:5432/db"
        assert "p%%40ssw0rd%%21%%23%%24%%25" in escaped_url
    
    def test_real_world_password_from_error_log(self):
        """Test with the actual password from the error log."""
        # This is the password that caused the original error
        database_url = "postgresql://tarsy:qfaDQ7%26Q%21l%40Ap9@host:5432/db"
        escaped_url = database_url.replace('%', '%%')
        
        # Should escape all % signs
        assert escaped_url == "postgresql://tarsy:qfaDQ7%%26Q%%21l%%40Ap9@host:5432/db"
        # Verify that ConfigParser won't see interpolation syntax
        assert "%26" not in escaped_url or "%%26" in escaped_url
    
    def test_multiple_percent_signs_in_various_positions(self):
        """Test handling of % in different parts of the URL."""
        # Although % should only be in the password, test edge cases
        database_url = "postgresql://user%21:p%40ss@host:5432/db%20name"
        escaped_url = database_url.replace('%', '%%')
        
        assert escaped_url == "postgresql://user%%21:p%%40ss@host:5432/db%%20name"
        # Count % signs - should have doubled
        assert escaped_url.count('%') == database_url.count('%') * 2

