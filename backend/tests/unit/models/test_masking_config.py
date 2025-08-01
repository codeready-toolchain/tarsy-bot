"""
Unit tests for masking configuration models.

Tests focus on practical validation and model behavior:
- Field validation (regex patterns, required fields)
- Default values and configuration combinations  
- Error handling for invalid configurations
"""

import pytest
from pydantic import ValidationError

from tarsy.models.masking_config import MaskingConfig, MaskingPattern


@pytest.mark.unit
class TestMaskingPattern:
    """Test MaskingPattern model validation and behavior."""
    
    def test_valid_pattern_creation(self):
        """Test creating a valid masking pattern."""
        pattern = MaskingPattern(
            name="test_pattern",
            pattern=r"secret_\d+",
            replacement="***MASKED_SECRET***",
            description="Test secret pattern"
        )
        
        assert pattern.name == "test_pattern"
        assert pattern.pattern == r"secret_\d+"
        assert pattern.replacement == "***MASKED_SECRET***"
        assert pattern.description == "Test secret pattern"
        assert pattern.enabled is True  # Default value
    
    def test_pattern_with_disabled_flag(self):
        """Test creating pattern with enabled=False."""
        pattern = MaskingPattern(
            name="disabled_pattern",
            pattern=r"test_\d+",
            replacement="***MASKED***",
            description="Disabled pattern",
            enabled=False
        )
        
        assert pattern.enabled is False
    
    def test_invalid_regex_pattern_validation(self):
        """Test that invalid regex patterns are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MaskingPattern(
                name="invalid",
                pattern=r"[unclosed bracket",  # Invalid regex
                replacement="***MASKED***",
                description="Invalid pattern"
            )
        
        error = exc_info.value
        assert "Invalid regex pattern" in str(error)
    
    def test_empty_name_validation(self):
        """Test that empty names are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MaskingPattern(
                name="",  # Empty name
                pattern=r"valid_\d+",
                replacement="***MASKED***",
                description="Valid pattern"
            )
        
        error = exc_info.value
        assert "Pattern name cannot be empty" in str(error)
    
    def test_whitespace_name_validation(self):
        """Test that whitespace-only names are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MaskingPattern(
                name="   ",  # Whitespace only
                pattern=r"valid_\d+",
                replacement="***MASKED***",
                description="Valid pattern"
            )
        
        error = exc_info.value
        assert "Pattern name cannot be empty" in str(error)
    
    def test_name_trimming(self):
        """Test that names are trimmed of whitespace."""
        pattern = MaskingPattern(
            name="  trimmed_name  ",
            pattern=r"test_\d+",
            replacement="***MASKED***",
            description="Test trimming"
        )
        
        assert pattern.name == "trimmed_name"
    
    def test_complex_regex_patterns(self):
        """Test various complex but valid regex patterns."""
        valid_patterns = [
            r"(?i)(?:api[_-]?key|apikey)[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_\-]{20,})[\"']?",
            r"-----BEGIN [A-Z ]+-----.*?-----END [A-Z ]+-----",
            r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
            r"(?:password|pwd|pass)[\"']?\s*[:=]\s*[\"']?([^\"'\s\n]{6,})[\"']?"
        ]
        
        for i, regex in enumerate(valid_patterns):
            pattern = MaskingPattern(
                name=f"pattern_{i}",
                pattern=regex,
                replacement="***MASKED***",
                description=f"Test pattern {i}"
            )
            assert pattern.pattern == regex


@pytest.mark.unit
class TestMaskingConfig:
    """Test MaskingConfig model validation and behavior."""
    
    def test_minimal_config_creation(self):
        """Test creating minimal config with defaults."""
        config = MaskingConfig()
        
        assert config.enabled is True  # Default value
        assert config.pattern_groups == []  # Default empty list
        assert config.patterns == []  # Default empty list
        assert config.custom_patterns is None  # Default None
    
    def test_config_with_all_fields(self):
        """Test creating config with all fields specified."""
        custom_pattern = MaskingPattern(
            name="custom_test",
            pattern=r"test_\d+",
            replacement="***MASKED_TEST***",
            description="Custom test pattern"
        )
        
        config = MaskingConfig(
            enabled=True,
            pattern_groups=["basic", "security"],
            patterns=["api_key", "password"],
            custom_patterns=[custom_pattern]
        )
        
        assert config.enabled is True
        assert config.pattern_groups == ["basic", "security"]
        assert config.patterns == ["api_key", "password"]
        assert len(config.custom_patterns) == 1
        assert config.custom_patterns[0].name == "custom_test"
    
    def test_disabled_config(self):
        """Test creating disabled masking config."""
        config = MaskingConfig(
            enabled=False,
            pattern_groups=["basic"],  # Should be ignored when disabled
            patterns=["api_key"]       # Should be ignored when disabled
        )
        
        assert config.enabled is False
        # Fields should still be set even when disabled (for potential re-enabling)
        assert config.pattern_groups == ["basic"]
        assert config.patterns == ["api_key"]
    
    def test_multiple_custom_patterns(self):
        """Test config with multiple custom patterns."""
        patterns = [
            MaskingPattern(
                name="pattern1",
                pattern=r"test1_\d+",
                replacement="***MASKED_1***",
                description="First pattern"
            ),
            MaskingPattern(
                name="pattern2",
                pattern=r"test2_\d+",
                replacement="***MASKED_2***",
                description="Second pattern"
            )
        ]
        
        config = MaskingConfig(custom_patterns=patterns)
        
        assert len(config.custom_patterns) == 2
        assert config.custom_patterns[0].name == "pattern1"
        assert config.custom_patterns[1].name == "pattern2"
    
    def test_empty_lists_vs_none(self):
        """Test behavior with empty lists vs None values."""
        # Empty lists should work fine
        config1 = MaskingConfig(
            pattern_groups=[],
            patterns=[]
        )
        assert config1.pattern_groups == []
        assert config1.patterns == []
        
        # None for custom_patterns should work
        config2 = MaskingConfig(custom_patterns=None)
        assert config2.custom_patterns is None
    
    def test_realistic_production_configs(self):
        """Test realistic production configuration scenarios."""
        # Basic security config
        basic_config = MaskingConfig(
            enabled=True,
            pattern_groups=["basic"]
        )
        assert basic_config.enabled is True
        assert "basic" in basic_config.pattern_groups
        
        # Comprehensive security config
        comprehensive_config = MaskingConfig(
            enabled=True,
            pattern_groups=["security"],
            patterns=["token"],
            custom_patterns=[
                MaskingPattern(
                    name="internal_id",
                    pattern=r"internal_id_\d{8}",
                    replacement="***MASKED_ID***",
                    description="Internal system IDs"
                )
            ]
        )
        assert comprehensive_config.enabled is True
        assert "security" in comprehensive_config.pattern_groups
        assert "token" in comprehensive_config.patterns
        assert len(comprehensive_config.custom_patterns) == 1
        
        # Disabled config (for development)
        dev_config = MaskingConfig(enabled=False)
        assert dev_config.enabled is False


@pytest.mark.unit 
class TestMaskingConfigValidation:
    """Test edge cases and validation scenarios."""
    
    def test_duplicate_pattern_names_in_custom_patterns(self):
        """Test handling duplicate names in custom patterns list."""
        # This should be allowed at the model level - service layer handles uniqueness
        patterns = [
            MaskingPattern(
                name="duplicate",
                pattern=r"test1_\d+",
                replacement="***MASKED_1***",
                description="First pattern"
            ),
            MaskingPattern(
                name="duplicate",  # Same name
                pattern=r"test2_\d+", 
                replacement="***MASKED_2***",
                description="Second pattern"
            )
        ]
        
        config = MaskingConfig(custom_patterns=patterns)
        
        # Model should allow this - validation happens at service level
        assert len(config.custom_patterns) == 2
        assert config.custom_patterns[0].name == "duplicate"
        assert config.custom_patterns[1].name == "duplicate"
    
    def test_invalid_custom_pattern_in_config(self):
        """Test that invalid custom patterns fail config creation."""
        with pytest.raises(ValidationError):
            MaskingConfig(
                custom_patterns=[
                    MaskingPattern(
                        name="valid_pattern",
                        pattern=r"valid_\d+",
                        replacement="***MASKED***",
                        description="Valid pattern"
                    ),
                    MaskingPattern(
                        name="invalid_pattern",
                        pattern=r"[invalid regex(",  # Invalid regex
                        replacement="***MASKED***",
                        description="Invalid pattern"
                    )
                ]
            )
    
    def test_config_serialization_roundtrip(self):
        """Test that config can be serialized and deserialized."""
        original_config = MaskingConfig(
            enabled=True,
            pattern_groups=["basic", "security"],
            patterns=["api_key"],
            custom_patterns=[
                MaskingPattern(
                    name="test_pattern",
                    pattern=r"test_\d+",
                    replacement="***MASKED***",
                    description="Test pattern"
                )
            ]
        )
        
        # Convert to dict and back
        config_dict = original_config.model_dump()
        restored_config = MaskingConfig(**config_dict)
        
        assert restored_config.enabled == original_config.enabled
        assert restored_config.pattern_groups == original_config.pattern_groups
        assert restored_config.patterns == original_config.patterns
        assert len(restored_config.custom_patterns) == 1
        assert restored_config.custom_patterns[0].name == "test_pattern"