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
from tests.utils import MockFactory, TestUtils, DataMaskingFactory


@pytest.mark.unit
class TestDataMaskingServiceInitialization:
    """Test service initialization and builtin pattern loading."""
    
    @pytest.mark.parametrize("registry,expected_registry,expected_patterns", [
        (None, None, ["api_key", "password"]),  # No registry
        (Mock(), "mock", ["api_key", "password"]),  # With registry
    ])
    def test_initialization_scenarios(self, registry, expected_registry, expected_patterns):
        """Test initialization for various registry scenarios."""
        if registry == "mock":
            registry = Mock()
        
        service = DataMaskingService(registry)
        
        assert service.mcp_registry == registry
        assert isinstance(service.compiled_patterns, dict)
        assert isinstance(service.custom_pattern_metadata, dict)
        # Should load builtin patterns
        assert len(service.compiled_patterns) > 0
        for pattern in expected_patterns:
            assert pattern in service.compiled_patterns


@pytest.mark.unit 
class TestBasicPatternMatching:
    """Test core pattern matching functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # No registry = masking disabled by default, good for controlled testing
        self.service = DataMaskingService()
    
    @pytest.mark.parametrize("test_data,patterns,expected_masked,expected_preserved", [
        (f'api_key: "{DataMaskingFactory.create_test_data_with_secrets()["api_key"]}"', ["api_key"], 
         ["***MASKED_API_KEY***"], [DataMaskingFactory.create_test_data_with_secrets()["api_key"]]),
        (f'"password": "{DataMaskingFactory.create_test_data_with_secrets()["password"]}"', ["password"], 
         ["***MASKED_PASSWORD***"], [DataMaskingFactory.create_test_data_with_secrets()["password"]]),
        ("""-----BEGIN CERTIFICATE-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890
-----END CERTIFICATE-----""", ["certificate"], 
         ["***MASKED_CERTIFICATE***"], ["MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890"]),
        ("This is just normal text without secrets", ["api_key", "password"], 
         [], []),  # No masking
        (f'api_key: "{DataMaskingFactory.create_test_data_with_secrets()["api_key"]}" password: "secretpass123"', ["api_key", "password"], 
         ["***MASKED_API_KEY***", "***MASKED_PASSWORD***"], [DataMaskingFactory.create_test_data_with_secrets()["api_key"], "secretpass123"]),
    ])
    def test_pattern_masking_scenarios(self, test_data, patterns, expected_masked, expected_preserved):
        """Test pattern masking for various scenarios."""
        result = self.service._apply_patterns(test_data, patterns)
        
        # Check that sensitive data is masked
        for masked in expected_masked:
            assert masked in result
        
        # Check that sensitive data is not present
        for preserved in expected_preserved:
            assert preserved not in result
        
        # For no-pattern case, ensure original text is unchanged
        if not expected_masked:
            assert result == test_data

    def test_kubernetes_data_section_masking_exactly_what_user_wanted(self):
        """Test Kubernetes data section masking: mask entire data: section, preserve metadata:."""
        test_data = DataMaskingFactory.create_kubernetes_secret_data()
        
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

    @pytest.mark.parametrize("test_data,patterns,expected_masked,expected_preserved", [
        (f'token: {DataMaskingFactory.create_base64_test_data()["token"]} another_field: {DataMaskingFactory.create_base64_test_data()["another_field"]}', ["base64_secret"], 
         ["***MASKED_BASE64_VALUE***"], [DataMaskingFactory.create_base64_test_data()["token"], DataMaskingFactory.create_base64_test_data()["another_field"]]),
        (f'username: {DataMaskingFactory.create_base64_test_data()["username"]} password: {DataMaskingFactory.create_base64_test_data()["password"]} token: {DataMaskingFactory.create_base64_test_data()["short_token"]}', ["base64_short"], 
         ["***MASKED_SHORT_BASE64***"], [DataMaskingFactory.create_base64_test_data()["username"], DataMaskingFactory.create_base64_test_data()["password"], DataMaskingFactory.create_base64_test_data()["short_token"]]),
    ])
    def test_base64_masking_scenarios(self, test_data, patterns, expected_masked, expected_preserved):
        """Test base64 masking for various scenarios."""
        result = self.service._apply_patterns(test_data, patterns)
        
        # Check that base64 values are masked
        for masked in expected_masked:
            assert masked in result
        
        # Check that base64 values are not present
        for preserved in expected_preserved:
            assert preserved not in result






@pytest.mark.unit
class TestDataStructureTraversal:
    """Test masking across different data structures."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = DataMaskingService()
    
    @pytest.mark.parametrize("data,patterns,expected_masked,expected_preserved", [
        ({"result": {"config": f"api_key: {DataMaskingFactory.create_test_data_with_secrets()['api_key']}", "normal_field": "normal_value"}}, ["api_key"], 
         ["***MASKED_API_KEY***"], [DataMaskingFactory.create_test_data_with_secrets()["api_key"]]),
        (["normal item", "password: secret123", f"api_key: {DataMaskingFactory.create_test_data_with_secrets()['api_key']}"], ["password", "api_key"], 
         ["***MASKED_PASSWORD***", "***MASKED_API_KEY***"], ["secret123", DataMaskingFactory.create_test_data_with_secrets()["api_key"]]),
        (DataMaskingFactory.create_nested_data_structure(), ["password", "api_key"], 
         ["***MASKED_PASSWORD***", "***MASKED_API_KEY***"], ["secret123", DataMaskingFactory.create_test_data_with_secrets()["api_key"]]),
    ])
    def test_data_structure_masking_scenarios(self, data, patterns, expected_masked, expected_preserved):
        """Test masking across different data structure scenarios."""
        result = self.service._mask_data_structure(data, patterns)
        
        # Check that sensitive data is masked
        result_str = str(result)
        for masked in expected_masked:
            assert masked in result_str
        
        # Check that sensitive data is not present
        for preserved in expected_preserved:
            assert preserved not in result_str
        
        # Check that non-sensitive data is unchanged (basic checks)
        if isinstance(data, dict):
            # For dict, check that non-string fields are unchanged
            if "number_field" in data:
                assert result["number_field"] == 42
            if "boolean_field" in data:
                assert result["boolean_field"] is True
            if "null_field" in data:
                assert result["null_field"] is None
        elif isinstance(data, list):
            # For list, check that first item is unchanged
            assert result[0] == "normal item"


@pytest.mark.unit
class TestPatternGroupExpansion:
    """Test pattern group expansion functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = DataMaskingService()
    
    @pytest.mark.parametrize("groups,expected_patterns,expected_count", [
        (["basic"], DataMaskingFactory.create_pattern_groups()["basic"], 2),
        (["basic", "security"], DataMaskingFactory.create_pattern_groups()["basic"] + DataMaskingFactory.create_pattern_groups()["security"], 4),
        (["unknown_group", "basic"], DataMaskingFactory.create_pattern_groups()["basic"], 2),  # Skip unknown group
        ([], [], 0),  # Empty groups
        (["kubernetes"], DataMaskingFactory.create_pattern_groups()["kubernetes"] + DataMaskingFactory.create_pattern_groups()["basic"], 4),
    ])
    def test_pattern_group_expansion_scenarios(self, groups, expected_patterns, expected_count):
        """Test pattern group expansion for various scenarios."""
        result = self.service._expand_pattern_groups(groups)
        
        # Check that expected patterns are present
        for pattern in expected_patterns:
            assert pattern in result
        
        # Check the count
        assert len(result) == expected_count


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