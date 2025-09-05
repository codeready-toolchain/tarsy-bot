"""
Unit tests for DataMaskingService.

Tests focus on practical functionality without complex mocking:
- Pattern matching and replacement
- Data structure traversal 
- Fail-safe behavior
- Configuration integration
"""

from unittest.mock import Mock

import pytest

from tarsy.models.agent_config import MaskingConfig, MaskingPattern
from tarsy.services.data_masking_service import DataMaskingService
from tests.utils import DataMaskingFactory

# Precomputed factory outputs for test reuse
TEST_DATA_WITH_SECRETS = DataMaskingFactory.create_test_data_with_secrets()
BASE64_TEST_DATA = DataMaskingFactory.create_base64_test_data()
PATTERN_GROUPS = DataMaskingFactory.create_pattern_groups()
KUBERNETES_SECRET_DATA = DataMaskingFactory.create_kubernetes_secret_data()
NESTED_DATA_STRUCTURE = DataMaskingFactory.create_nested_data_structure()


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
        (f'api_key: "{TEST_DATA_WITH_SECRETS["api_key"]}"', ["api_key"], 
         ["***MASKED_API_KEY***"], [TEST_DATA_WITH_SECRETS["api_key"]]),
        (f'"password": "{TEST_DATA_WITH_SECRETS["password"]}"', ["password"], 
         ["***MASKED_PASSWORD***"], [TEST_DATA_WITH_SECRETS["password"]]),
        ("""-----BEGIN CERTIFICATE-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890
-----END CERTIFICATE-----""", ["certificate"], 
         ["***MASKED_CERTIFICATE***"], ["MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1234567890"]),
        ("certificate-authority-data: LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0tCk1JSUREakNDQWZZPQ==", ["certificate_authority_data"], 
         ["***MASKED_CA_CERTIFICATE***"], ["LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0tCk1JSUREakNDQWZZPQ=="]),
        ("Contact support at support@example.com for help", ["email"], 
         ["***MASKED_EMAIL***"], ["support@example.com"]),
        ("This is just normal text without secrets", ["api_key", "password"], 
         [], []),  # No masking
        (f'api_key: "{TEST_DATA_WITH_SECRETS["api_key"]}" password: "secretpass123"', ["api_key", "password"], 
         ["***MASKED_API_KEY***", "***MASKED_PASSWORD***"], 
         [TEST_DATA_WITH_SECRETS["api_key"], "secretpass123"]),
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
        test_data = KUBERNETES_SECRET_DATA
        
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

    def test_certificate_authority_data_masking_kubernetes_config(self):
        """Test certificate-authority-data masking in Kubernetes config context."""
        kubeconfig_data = """apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0tCk1JSUREakNDQWZZQ0NRQ1dFamxNOW9zPQ==
    server: https://api.crc.testing:6443
  name: api-crc-testing:6443
contexts:
- context:
    cluster: api-crc-testing:6443
    namespace: default
  name: default"""

        result = self.service._apply_patterns(kubeconfig_data, ["certificate_authority_data"])
        
        # Certificate authority data should be masked
        assert "LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0tCk1JSUREakNDQWZZQ0NRQ1dFamxNOW9zPQ==" not in result
        assert "***MASKED_CA_CERTIFICATE***" in result
        
        # Other config data should be preserved
        assert "https://api.crc.testing:6443" in result
        assert "api-crc-testing:6443" in result
        assert "default" in result

    def test_certificate_authority_data_no_false_positives(self):
        """Test that certificate-authority-data pattern doesn't create false positives."""
        # Test cases that should NOT be masked
        test_cases = [
            # No colon - should not match
            "certificate-authority-data LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0t",
            "certificate-authority-data. LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0t", 
            "certificate-authority-data, LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0t",
            
            # Colon but no data or too short data - should not match
            "certificate-authority-data:",
            "certificate-authority-data: ",
            "certificate-authority-data:   ",
            "certificate-authority-data: short",
            "certificate-authority-data: abc123",
            "certificate-authority-data: notbase64text",
            
            # Descriptive text - should not match (no valid base64 after)
            "The certificate-authority-data: field contains the certificate authority data",
            "Configure certificate-authority-data: property in your kubeconfig",
            "certificate-authority-data: value should be base64 encoded",
            
            # Invalid base64 patterns - should not match
            "certificate-authority-data: this-is-not-base64-format-data",
            "certificate-authority-data: @@@@@@@@@@@@@@@@@@@@@@@@@@@@",
            "certificate-authority-data: spaces in the data here",
        ]
        
        for test_case in test_cases:
            result = self.service._apply_patterns(test_case, ["certificate_authority_data"])
            
            # Should not be masked - original text should remain unchanged
            assert result == test_case, f"False positive detected in: {test_case}"
            assert "***MASKED_CA_CERTIFICATE***" not in result, f"Incorrectly masked: {test_case}"

    def test_certificate_authority_data_valid_cases_are_masked(self):
        """Test that valid certificate-authority-data cases ARE properly masked."""
        # Test cases that SHOULD be masked
        valid_test_cases = [
            # Standard format
            "certificate-authority-data: LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0tCk1JSUREakNDQWZZQ0NRQ1dFamxNOW9zPQ==",
            
            # With extra whitespace
            "certificate-authority-data:   LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0tCk1JSUREakNDQWZZQ0NRQ1dFamxNOW9zPQ==",
            "certificate-authority-data:\t\tLS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0tCk1JSUREakNDQWZZQ0NRQ1dFamxNOW9zPQ==",
            
            # Case variations
            "Certificate-Authority-Data: LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0tCk1JSUREakNDQWZZQ0NRQ1dFamxNOW9zPQ==",
            "CERTIFICATE-AUTHORITY-DATA: LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0tCk1JSUREakNDQWZZQ0NRQ1dFamxNOW9zPQ==",
            
            # Minimum length base64 (20 chars)
            "certificate-authority-data: YWJjZGVmZ2hpamtsbW5vcA==",
            
            # With padding variations
            "certificate-authority-data: LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0tCk1JSUREakNDQWZZQ0NRQ1dFamxNOW9z",  # no padding
            "certificate-authority-data: LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0tCk1JSUREakNDQWZZQ0NRQ1dFamxNOW9zPQ=",  # single =
        ]
        
        for test_case in valid_test_cases:
            result = self.service._apply_patterns(test_case, ["certificate_authority_data"])
            
            # Should be masked
            assert "***MASKED_CA_CERTIFICATE***" in result, f"Should have been masked: {test_case}"
            # Original base64 data should not be present
            original_data = test_case.split(': ', 1)[1] if ': ' in test_case else test_case.split(':\t', 1)[1] if ':\t' in test_case else test_case.split(':', 1)[1]
            assert original_data.strip() not in result, f"Original data still present: {test_case}"

    def test_email_no_false_positives(self):
        """Test that email pattern doesn't create false positives."""
        # Test cases that should NOT be masked - clearly invalid email formats
        test_cases = [
            # No @ symbol
            "email.domain.com",
            "user.domain.com",
            
            # No domain extension
            "user@domain",
            "support@localhost",
            
            # Invalid characters or formats
            "user@@domain.com",
            "@domain.com", 
            "user@",
            "user@.com",
            "user@domain.",
            "user@domain..com",
            
            # Too short TLD (less than 2 chars) 
            "user@domain.c",
            "user@domain.1",
            
            # Domain starting with hyphen or dot
            "user@-domain.com",
            "user@.domain.com",
            
            # Empty username
            "@domain.com",
        ]
        
        for test_case in test_cases:
            result = self.service._apply_patterns(test_case, ["email"])
            
            # Should not be masked - original text should remain unchanged
            assert result == test_case, f"False positive detected in: {test_case}"
            assert "***MASKED_EMAIL***" not in result, f"Incorrectly masked: {test_case}"

    def test_email_contextual_cases(self):
        """Test email pattern in various contextual cases that should be masked."""
        # These cases SHOULD be masked because they contain legitimate emails
        contextual_cases = [
            # Emails in code contexts (these should be masked)
            'var email = "user@domain.com"',
            "func(user@domain.com)",
            "Contact support@example.org for help",
            
            # Technical contexts that contain valid emails
            "git clone user@github.com:repo/project.git",  # Contains valid email
            "ssh user@server.com",  # Contains valid email
        ]
        
        for test_case in contextual_cases:
            result = self.service._apply_patterns(test_case, ["email"])
            
            # Should mask the email part
            assert "***MASKED_EMAIL***" in result, f"Should have masked email in: {test_case}"

    def test_email_valid_cases_are_masked(self):
        """Test that valid email addresses ARE properly masked."""
        # Test cases that SHOULD be masked
        valid_test_cases = [
            # Standard formats
            "Contact user@example.com for support",
            "Send logs to admin@company.org",
            "Email: support@domain.net",
            
            # Various TLD lengths
            "user@example.co.uk",
            "admin@site.museum",
            "info@domain.travel",
            
            # Numbers in domain/user
            "user123@example123.com",
            "test@domain2024.org",
            
            # Special characters in username
            "user.name@example.com",
            "user_name@example.com", 
            "user-name@example.com",
            "user+tag@example.com",
            "user%special@example.com",
            
            # Subdomains
            "admin@mail.example.com",
            "user@subdomain.domain.co.uk",
            
            # Multiple emails in text
            "Contact user@example.com or admin@example.org for help",
            
            # Mixed case
            "User@Example.Com",
            "ADMIN@DOMAIN.ORG",
            
            # In various contexts
            "Log in with user@example.com",
            "From: sender@company.com",
            "To: recipient@domain.net",
            "Reply-To: noreply@service.com",
        ]
        
        for test_case in valid_test_cases:
            result = self.service._apply_patterns(test_case, ["email"])
            
            # Should be masked
            assert "***MASKED_EMAIL***" in result, f"Should have been masked: {test_case}"
            
            # Check that specific email addresses are masked
            import re
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*\.[A-Za-z]{2,}\b'
            found_emails = re.findall(email_pattern, test_case)
            
            for email in found_emails:
                assert email not in result, f"Email {email} still present in result: {result}"

    @pytest.mark.parametrize("test_data,patterns,expected_masked,expected_preserved", [
        (f'token: {BASE64_TEST_DATA["token"]} another_field: {BASE64_TEST_DATA["another_field"]}', ["base64_secret"], 
         ["***MASKED_BASE64_VALUE***"], 
         [BASE64_TEST_DATA["token"], BASE64_TEST_DATA["another_field"]]),
        (f'username: {BASE64_TEST_DATA["username"]} password: {BASE64_TEST_DATA["password"]} ' +
         f'token: {BASE64_TEST_DATA["short_token"]}', ["base64_short"], 
         ["***MASKED_SHORT_BASE64***"], 
         [BASE64_TEST_DATA["username"], BASE64_TEST_DATA["password"], BASE64_TEST_DATA["short_token"]]),
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
        ({"result": {"config": f"api_key: {TEST_DATA_WITH_SECRETS['api_key']}", "normal_field": "normal_value"}}, ["api_key"], 
         ["***MASKED_API_KEY***"], [TEST_DATA_WITH_SECRETS["api_key"]]),
        (["normal item", "password: secret123", f"api_key: {TEST_DATA_WITH_SECRETS['api_key']}"], ["password", "api_key"], 
         ["***MASKED_PASSWORD***", "***MASKED_API_KEY***"], 
         ["secret123", TEST_DATA_WITH_SECRETS["api_key"]]),
        (NESTED_DATA_STRUCTURE, ["password", "api_key"], 
         ["***MASKED_PASSWORD***", "***MASKED_API_KEY***"], 
         ["secret123", TEST_DATA_WITH_SECRETS["api_key"]]),
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
        (["basic"], PATTERN_GROUPS["basic"], 2),
        (["basic", "security"], PATTERN_GROUPS["basic"] + PATTERN_GROUPS["security"], 6),
        (["unknown_group", "basic"], PATTERN_GROUPS["basic"], 2),  # Skip unknown group
        ([], [], 0),  # Empty groups
        (["kubernetes"], PATTERN_GROUPS["kubernetes"] + PATTERN_GROUPS["basic"], 5),
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
        response = {"result": "api_key: not-a-real-api-key-123456789012345678901234567890"}
        
        result = service.mask_response(response, "test-server")
        
        # Should return original response unchanged (no registry = no masking)
        assert result == response
        assert "not-a-real-api-key-123456789012345678901234567890" in str(result)


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
        
        response = {"result": "api_key: not-a-real-api-key-123456789012345678901234567890"}
        result = self.service.mask_response(response, "test-server")
        
        # Should return original response unchanged
        assert result == response
        assert "not-a-real-api-key-123456789012345678901234567890" in str(result)
    
    def test_mask_response_with_enabled_masking(self):
        """Test response with masking enabled."""
        # Mock: server has masking config enabled
        mock_server_config = Mock()
        mock_server_config.data_masking = MaskingConfig(
            enabled=True,
            pattern_groups=["basic"]
        )
        self.mock_registry.get_server_config_safe.return_value = mock_server_config
        
        response = {"result": "api_key: not-a-real-api-key-123456789012345678901234567890"}
        result = self.service.mask_response(response, "test-server")
        
        # Should mask the API key
        assert "not-a-real-api-key-123456789012345678901234567890" not in str(result)
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
      {"apiVersion":"v1","kind":"Secret","metadata":{"annotations":{},"name":"my-secret",""" + \
        """"namespace":"superman-dev"},"stringData":{"password": "supersecretpassword123",""" + \
        """"username":"admin","api-key":"abcdefghijk12345"},"type":"Opaque"}
  name: my-secret
  namespace: superman-dev
type: Opaque"""
        }
        
        result = self.service.mask_response(response, "kubernetes-server")
        
        # Test that sensitive data is properly masked
        assert "***MASKED_SECRET_DATA***" in str(result)  # Our new comprehensive masking
        
        # Verify secrets are masked and metadata is preserved
        result_str = str(result)
        secrets_to_hide = ["c3VwZXJzZWNyZXRwYXNzd29yZDEyMw==", "YWRtaW4=", 
                           "YWJjZGVmZ2hpams12345", "supersecretpassword123"]
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