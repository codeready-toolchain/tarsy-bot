"""
Unit tests for DataMaskingService.

Tests focus on practical functionality without complex mocking:
- Pattern matching and replacement
- Data structure traversal 
- Fail-safe behavior
- Configuration integration
"""

import pytest
from unittest.mock import Mock

from tarsy.services.data_masking_service import DataMaskingService
from tarsy.models.masking_config import MaskingConfig, MaskingPattern


@pytest.mark.unit
class TestDataMaskingServiceInitialization:
    """Test service initialization and builtin pattern loading."""
    
    def test_initialization_without_registry(self):
        """Test initialization with no registry disables all masking."""
        service = DataMaskingService()
        
        assert service.mcp_registry is None
        assert isinstance(service.compiled_patterns, dict)
        assert isinstance(service.custom_pattern_metadata, dict)
        # Should load builtin patterns
        assert len(service.compiled_patterns) > 0
        assert "api_key" in service.compiled_patterns
        assert "password" in service.compiled_patterns
    
    def test_initialization_with_registry(self):
        """Test initialization with registry enables configuration lookup."""
        mock_registry = Mock()
        service = DataMaskingService(mock_registry)
        
        assert service.mcp_registry is mock_registry
        assert len(service.compiled_patterns) > 0


@pytest.mark.unit 
class TestBasicPatternMatching:
    """Test core pattern matching functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # No registry = masking disabled by default, good for controlled testing
        self.service = DataMaskingService()
    
    def test_api_key_masking(self):
        """Test API key pattern matching."""
        test_data = 'api_key: "sk_test_123456789012345678901234567890"'
        patterns = ["api_key"]
        
        result = self.service._apply_patterns(test_data, patterns)
        
        assert "sk_test_123456789012345678901234567890" not in result
        assert "***MASKED_API_KEY***" in result
    
    def test_password_masking(self):
        """Test password pattern matching."""
        test_data = '"password": "mySecretPassword123"'
        patterns = ["password"]
        
        result = self.service._apply_patterns(test_data, patterns)
        
        assert "mySecretPassword123" not in result
        assert "***MASKED_PASSWORD***" in result
    
    def test_certificate_masking(self):
        """Test certificate pattern matching."""
        test_data = """-----BEGIN CERTIFICATE-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890
-----END CERTIFICATE-----"""
        patterns = ["certificate"]
        
        result = self.service._apply_patterns(test_data, patterns)
        
        assert "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890" not in result
        assert "***MASKED_CERTIFICATE***" in result
    
    def test_no_patterns_no_masking(self):
        """Test that text without patterns remains unchanged.""" 
        test_data = "This is just normal text without secrets"
        patterns = ["api_key", "password"]
        
        result = self.service._apply_patterns(test_data, patterns)
        
        assert result == test_data
    
    def test_multiple_patterns_same_text(self):
        """Test multiple patterns applied to same text."""
        test_data = 'api_key: "sk_123456789012345678901234567890" password: "secretpass123"'
        patterns = ["api_key", "password"]
        
        result = self.service._apply_patterns(test_data, patterns)
        
        assert "sk_123456789012345678901234567890" not in result
        assert "secretpass123" not in result
        assert "***MASKED_API_KEY***" in result
        assert "***MASKED_PASSWORD***" in result

    def test_kubernetes_data_section_masking_exactly_what_user_wanted(self):
        """Test Kubernetes data section masking: mask entire data: section, preserve metadata:."""
        test_data = '''apiVersion: v1
data:
  username: YWRtaW4=
  password: c3VwZXJzZWNyZXRwYXNzd29yZDEyMw==
  somekey: xyz
kind: Secret
metadata:
  name: my-secret
  namespace: superman-dev'''
        
        result = self.service._apply_patterns(test_data, ["kubernetes_data_section"])
        
        # All data section secrets should be masked
        assert "YWRtaW4=" not in result
        assert "c3VwZXJzZWNyZXRwYXNzd29yZDEyMw==" not in result
        assert "xyz" not in result
        assert "***MASKED_SECRET_DATA***" in result
        
        # Metadata should be preserved
        assert "my-secret" in result
        assert "superman-dev" in result
        assert "Secret" in result

    def test_base64_secret_masking(self):
        """Test base64 secret pattern matching."""
        # Use longer base64 values that meet the 20+ character requirement
        test_data = 'token: dGhpc2lzYWxvbmdlcmJhc2U2NGVuY29kZWR2YWx1ZQ== another_field: c3VwZXJzZWNyZXRwYXNzd29yZDEyMw=='
        patterns = ["base64_secret"]
        
        result = self.service._apply_patterns(test_data, patterns)
        
        # Base64 values should be masked (these are longer than 20 chars)
        assert "dGhpc2lzYWxvbmdlcmJhc2U2NGVuY29kZWR2YWx1ZQ==" not in result
        assert "c3VwZXJzZWNyZXRwYXNzd29yZDEyMw==" not in result
        assert "***MASKED_BASE64_VALUE***" in result





    def test_short_base64_masking(self):
        """Test masking of short base64 values like YWRtaW4= (8 chars)."""
        test_data = 'username: YWRtaW4= password: cGFzcw== token: dGVzdA=='
        patterns = ["base64_short"]
        
        result = self.service._apply_patterns(test_data, patterns)
        
        # Short base64 values should be masked
        assert "YWRtaW4=" not in result  # base64 "admin" (8 chars)
        assert "cGFzcw==" not in result  # base64 "pass" (8 chars)
        assert "dGVzdA==" not in result  # base64 "test" (8 chars)
        assert "***MASKED_SHORT_BASE64***" in result






@pytest.mark.unit
class TestDataStructureTraversal:
    """Test masking across different data structures."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = DataMaskingService()
    
    def test_mask_dict_structure(self):
        """Test masking nested dictionary structures."""
        data = {"result": {"config": "api_key: sk_123456789012345678901234567890", "normal_field": "normal_value"}}
        
        result = self.service._mask_data_structure(data, ["api_key"])
        
        assert "sk_123456789012345678901234567890" not in str(result)
        assert result["result"]["normal_field"] == "normal_value"
        assert "***MASKED_API_KEY***" in str(result)
    
    def test_mask_list_structure(self):
        """Test masking list structures."""
        data = ["normal item", "password: secret123", "api_key: sk_123456789012345678901234567890"]
        
        result = self.service._mask_data_structure(data, ["password", "api_key"])
        
        assert result[0] == "normal item"  # unchanged
        result_str = str(result)
        assert "secret123" not in result_str and "sk_123456789012345678901234567890" not in result_str
        assert "***MASKED_PASSWORD***" in result_str and "***MASKED_API_KEY***" in result_str
    
    def test_mask_mixed_types(self):
        """Test masking with mixed data types."""
        data = {
            "string_field": "password: secret123",
            "number_field": 42,
            "boolean_field": True,
            "null_field": None,
            "nested": {
                "array": ["api_key: sk_123456789012345678901234567890"]
            }
        }
        patterns = ["password", "api_key"]
        
        result = self.service._mask_data_structure(data, patterns)
        
        # Non-string fields should be unchanged
        assert result["number_field"] == 42
        assert result["boolean_field"] is True
        assert result["null_field"] is None
        
        # String fields should be masked
        assert "secret123" not in str(result)
        assert "sk_123456789012345678901234567890" not in str(result)
        assert "***MASKED_PASSWORD***" in str(result)
        assert "***MASKED_API_KEY***" in str(result)


@pytest.mark.unit
class TestPatternGroupExpansion:
    """Test pattern group expansion functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = DataMaskingService()
    
    def test_expand_basic_group(self):
        """Test expanding basic pattern group."""
        result = self.service._expand_pattern_groups(["basic"])
        
        assert "api_key" in result
        assert "password" in result
        assert len(result) == 2
    
    def test_expand_multiple_groups(self):
        """Test expanding multiple pattern groups."""
        result = self.service._expand_pattern_groups(["basic", "security"])
        
        # Should contain all patterns from both groups (deduplicated)
        assert "api_key" in result
        assert "password" in result
        assert "token" in result
        assert "certificate" in result
    
    def test_expand_unknown_group(self):
        """Test handling unknown pattern groups."""
        result = self.service._expand_pattern_groups(["unknown_group", "basic"])
        
        # Should skip unknown group but process known ones
        assert "api_key" in result
        assert "password" in result
        assert len(result) == 2  # Only from basic group
    
    def test_expand_empty_groups(self):
        """Test expanding empty group list."""
        result = self.service._expand_pattern_groups([])
        
        assert result == []

    def test_expand_kubernetes_group(self):
        """Test kubernetes pattern group contains the right patterns for secure masking."""
        result = self.service._expand_pattern_groups(["kubernetes"])
        
        # Should contain kubernetes-specific patterns for comprehensive data masking
        assert "kubernetes_data_section" in result
        assert "kubernetes_stringdata_json" in result 
        assert "api_key" in result
        assert "password" in result
        # Should have exactly 4 patterns (removed base64_short to prevent over-masking)
        assert len(result) == 4


@pytest.mark.unit
class TestCustomPatterns:
    """Test custom pattern compilation and usage."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = DataMaskingService()
    
    def test_compile_valid_custom_patterns(self):
        """Test compiling valid custom patterns."""
        custom_patterns = [
            MaskingPattern(
                name="test_pattern",
                pattern=r"test_\d+",
                replacement="***MASKED_TEST***",
                description="Test pattern"
            )
        ]
        
        pattern_names = self.service._compile_and_add_custom_patterns(custom_patterns)
        
        assert "custom_test_pattern" in pattern_names
        assert "custom_test_pattern" in self.service.compiled_patterns
        assert "custom_test_pattern" in self.service.custom_pattern_metadata
    
    def test_compile_invalid_regex_pattern(self):
        """Test handling invalid regex patterns."""
        # Invalid patterns should fail at Pydantic validation level
        with pytest.raises(Exception):  # ValidationError
            MaskingPattern(
                name="invalid_pattern",
                pattern=r"[invalid regex(",  # Invalid regex
                replacement="***MASKED***",
                description="Invalid pattern"
            )
        
        # Valid pattern should work fine
        valid_pattern = MaskingPattern(
            name="valid_pattern",
            pattern=r"valid_\d+",
            replacement="***MASKED_VALID***",
            description="Valid pattern"
        )
        
        pattern_names = self.service._compile_and_add_custom_patterns([valid_pattern])
        
        assert "custom_valid_pattern" in pattern_names
        assert "custom_valid_pattern" in self.service.compiled_patterns
    
    def test_use_custom_pattern(self):
        """Test using compiled custom pattern for masking."""
        # Add custom pattern
        custom_patterns = [
            MaskingPattern(
                name="credit_card",
                pattern=r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",
                replacement="***MASKED_CREDIT_CARD***",
                description="Credit card numbers"
            )
        ]
        self.service._compile_and_add_custom_patterns(custom_patterns)
        
        # Test masking with correct pattern name (prefixed with "custom_")
        test_data = "Credit card: 1234-5678-9012-3456"
        result = self.service._apply_patterns(test_data, ["custom_credit_card"])
        
        assert "1234-5678-9012-3456" not in result
        assert "***MASKED_CREDIT_CARD***" in result


@pytest.mark.unit
class TestFailsafeBehavior:
    """Test fail-safe masking behavior."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = DataMaskingService()
    
    def test_failsafe_masking_response(self):
        """Test fail-safe masking of entire response."""
        response = {
            "result": "Some sensitive data here",
            "metadata": {"key": "value"}
        }
        
        result = self.service._apply_failsafe_masking(response)
        
        # Failsafe preserves structure but masks content
        assert result["result"] == "***MASKED_ERROR***"
    
    def test_mask_response_with_no_registry(self):
        """Test mask_response without registry returns original response."""
        service = DataMaskingService()  # No registry
        response = {"result": "api_key: sk_123456789012345678901234567890"}
        
        result = service.mask_response(response, "test-server")
        
        # Should return original response unchanged (no registry = no masking)
        assert result == response
        assert "sk_123456789012345678901234567890" in str(result)


@pytest.mark.unit
class TestMaskResponseIntegration:
    """Test end-to-end mask_response functionality with minimal mocking."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Mock registry for configuration lookup
        self.mock_registry = Mock()
        self.service = DataMaskingService(self.mock_registry)
    
    def test_mask_response_with_disabled_masking(self):
        """Test response when masking is disabled for server."""
        # Mock: server has no masking config
        self.mock_registry.get_server_config_safe.return_value = None
        
        response = {"result": "api_key: sk_123456789012345678901234567890"}
        result = self.service.mask_response(response, "test-server")
        
        # Should return original response unchanged
        assert result == response
        assert "sk_123456789012345678901234567890" in str(result)
    
    def test_mask_response_with_enabled_masking(self):
        """Test response with masking enabled."""
        # Mock: server has masking config enabled
        mock_server_config = Mock()
        mock_server_config.data_masking = MaskingConfig(
            enabled=True,
            pattern_groups=["basic"]
        )
        self.mock_registry.get_server_config_safe.return_value = mock_server_config
        
        response = {"result": "api_key: sk_123456789012345678901234567890"}
        result = self.service.mask_response(response, "test-server")
        
        # Should mask the API key
        assert "sk_123456789012345678901234567890" not in str(result)
        assert "***MASKED_API_KEY***" in str(result)

    def test_mask_response_kubernetes_secret_comprehensive(self):
        """Test complete masking flow with realistic Kubernetes secret."""
        # Mock: server has kubernetes masking enabled
        mock_server_config = Mock()
        mock_server_config.data_masking = MaskingConfig(
            enabled=True,
            pattern_groups=["kubernetes"]  # Uses enhanced kubernetes group
        )
        self.mock_registry.get_server_config_safe.return_value = mock_server_config
        
        # Realistic Kubernetes secret response (similar to user's example)
        response = {
            "result": """apiVersion: v1
data:
  "password": "c3VwZXJzZWNyZXRwYXNzd29yZDEyMw=="
  username: YWRtaW4=
  api-key: YWJjZGVmZ2hpams12345
kind: Secret
metadata:
  annotations:
    kubectl.kubernetes.io/last-applied-configuration: |
      {"apiVersion":"v1","kind":"Secret","metadata":{"annotations":{},"name":"my-secret","namespace":"superman-dev"},"stringData":{"password": "supersecretpassword123","username":"admin","api-key":"abcdefghijk12345"},"type":"Opaque"}
  name: my-secret
  namespace: superman-dev
type: Opaque"""
        }
        
        result = self.service.mask_response(response, "kubernetes-server")
        
        # Test that sensitive data is properly masked
        assert "***MASKED_SECRET_DATA***" in str(result)  # Our new comprehensive masking
        
        # Verify secrets are masked and metadata is preserved
        result_str = str(result)
        secrets_to_hide = ["c3VwZXJzZWNyZXRwYXNzd29yZDEyMw==", "YWRtaW4=", "YWJjZGVmZ2hpams12345", "supersecretpassword123"]
        for secret in secrets_to_hide:
            assert secret not in result_str
        
        preserved_data = ["my-secret", "superman-dev", "Secret", "Opaque"]
        for data in preserved_data:
            assert data in result_str


    
    def test_mask_response_with_custom_patterns(self):
        """Test response with custom patterns."""
        # Mock: server has custom patterns
        custom_pattern = MaskingPattern(
            name="test_id",
            pattern=r"id_\d{6}",
            replacement="***MASKED_ID***",
            description="Test ID pattern"
        )
        mock_server_config = Mock()
        mock_server_config.data_masking = MaskingConfig(
            enabled=True,
            custom_patterns=[custom_pattern]
        )
        self.mock_registry.get_server_config_safe.return_value = mock_server_config
        
        response = {"result": "Processing id_123456 completed"}
        result = self.service.mask_response(response, "test-server")
        
        # Should mask the custom pattern
        assert "id_123456" not in str(result)
        assert "***MASKED_ID***" in str(result)
    
    def test_mask_response_registry_error_returns_original(self):
        """Test that registry errors return original response (no masking)."""
        # Mock: registry throws exception
        self.mock_registry.get_server_config_safe.side_effect = Exception("Registry error")
        
        response = {"result": "Some sensitive data"}
        result = self.service.mask_response(response, "test-server")
        
        # Registry error means no masking config found, so return original
        assert result == response
        assert result["result"] == "Some sensitive data"