"""
Unit tests for KubernetesSecretMasker using matrix-based approach.

Each test case is a tuple of (input_data, expected_output).
"""

import pytest

from tarsy.services.maskers.kubernetes_secret_masker import KubernetesSecretMasker

# Test data matrix: (input, expected_output, description)
TEST_CASES = [
    # ============================================================================
    # VALID YAML SECRETS - Should be masked
    # ============================================================================
    (
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
data:
  password: c3VwZXJzZWNyZXRwYXNzd29yZDEyMw==
type: Opaque""",
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
data:
  __MASKED_SECRET_DATA__
type: Opaque""",
        "Simple YAML Secret with data section"
    ),
    (
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
stringData:
  username: admin
  password: supersecret
type: Opaque""",
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
stringData:
  __MASKED_SECRET_DATA__
type: Opaque""",
        "YAML Secret with stringData section"
    ),
    (
        """apiVersion: v1
data:
  password: c3VwZXJzZWNyZXRwYXNzd29yZDEyMw==
kind: Secret
metadata:
  name: test-secret""",
        """apiVersion: v1
data:
  __MASKED_SECRET_DATA__
kind: Secret
metadata:
  name: test-secret""",
        "YAML Secret with data before kind"
    ),
    (
        """apiVersion: v1
data:
  password: c3VwZXJzZWNyZXRwYXNzd29yZDEyMw==
kind: Secret
metadata:
  annotations:
    kubectl.kubernetes.io/last-applied-configuration: |
      {"apiVersion":"v1","data":{"password":"c3VwZXJzZWNyZXRwYXNzd29yZDEyMw=="},"kind":"Secret","metadata":{"name":"test"},"type":"Opaque"}
  name: test-secret""",
        """apiVersion: v1
data:
  __MASKED_SECRET_DATA__
kind: Secret
metadata:
  annotations:
    kubectl.kubernetes.io/last-applied-configuration: |
      {"apiVersion":"v1","data":"__MASKED_SECRET_DATA__","kind":"Secret","metadata":{"name":"test"},"type":"Opaque"}
  name: test-secret""",
        "YAML Secret with JSON in last-applied-configuration annotation"
    ),
    
    # ============================================================================
    # VALID JSON SECRETS - Should be masked
    # ============================================================================
    (
        '{"apiVersion":"v1","kind":"Secret","metadata":{"name":"test"},"data":{"password":"c3VwZXJzZWNyZXRwYXNzd29yZDEyMw=="},"type":"Opaque"}',
        '{"apiVersion":"v1","kind":"Secret","metadata":{"name":"test"},"data":"__MASKED_SECRET_DATA__","type":"Opaque"}',
        "JSON Secret with data field"
    ),
    (
        '{"apiVersion":"v1","kind":"Secret","metadata":{"name":"test"},"stringData":{"password":"secret123"},"type":"Opaque"}',
        '{"apiVersion":"v1","kind":"Secret","metadata":{"name":"test"},"stringData":"__MASKED_SECRET_DATA__","type":"Opaque"}',
        "JSON Secret with stringData field"
    ),
    
    # ============================================================================
    # CONFIGMAPS - Should NOT be masked
    # ============================================================================
    (
        """apiVersion: v1
kind: ConfigMap
metadata:
  name: test-config
data:
  config.yaml: |
    database:
      host: localhost
      port: 5432
  app.properties: debug=true""",
        """apiVersion: v1
kind: ConfigMap
metadata:
  name: test-config
data:
  config.yaml: |
    database:
      host: localhost
      port: 5432
  app.properties: debug=true""",
        "YAML ConfigMap - should NOT be masked"
    ),
    (
        '{"apiVersion":"v1","kind":"ConfigMap","metadata":{"name":"test"},"data":{"config":"value"}}',
        '{"apiVersion":"v1","kind":"ConfigMap","metadata":{"name":"test"},"data":{"config":"value"}}',
        "JSON ConfigMap - should NOT be masked (unchanged)"
    ),
    
    # ============================================================================
    # MULTI-DOCUMENT YAML
    # ============================================================================
    (
        """apiVersion: v1
kind: Secret
metadata:
  name: secret1
data:
  key1: dmFsdWUx
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: config1
data:
  key2: value2""",
        """apiVersion: v1
kind: Secret
metadata:
  name: secret1
data:
  __MASKED_SECRET_DATA__
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: config1
data:
  key2: value2""",
        "Multi-doc YAML with Secret and ConfigMap"
    ),
    (
        """apiVersion: v1
kind: Secret
metadata:
  name: secret1
data:
  key1: dmFsdWUx
---
apiVersion: v1
kind: Secret
metadata:
  name: secret2
data:
  key2: dmFsdWUy""",
        """apiVersion: v1
kind: Secret
metadata:
  name: secret1
data:
  __MASKED_SECRET_DATA__
---
apiVersion: v1
kind: Secret
metadata:
  name: secret2
data:
  __MASKED_SECRET_DATA__""",
        "Multi-doc YAML with multiple Secrets"
    ),
    
    # ============================================================================
    # FALSE POSITIVES - Random text, should NOT be masked
    # ============================================================================
    (
        "This documentation explains how Secret resources work in Kubernetes.",
        "This documentation explains how Secret resources work in Kubernetes.",
        "Documentation text with 'Secret' word"
    ),
    (
        "The kind of problem we're solving here is related to Secret management.",
        "The kind of problem we're solving here is related to Secret management.",
        "Text with 'kind' and 'Secret' but not a resource"
    ),
    (
        "Secret information should not be stored in ConfigMap resources.",
        "Secret information should not be stored in ConfigMap resources.",
        "Text mentioning both Secret and ConfigMap"
    ),
    (
        "What kind of Secret are you looking for?",
        "What kind of Secret are you looking for?",
        "Question with 'kind' and 'Secret'"
    ),
    (
        """# Documentation
## Kubernetes Secrets
Secrets are used to store sensitive data.
ConfigMaps are for non-sensitive configuration.""",
        """# Documentation
## Kubernetes Secrets
Secrets are used to store sensitive data.
ConfigMaps are for non-sensitive configuration.""",
        "Markdown documentation"
    ),
    
    # ============================================================================
    # INDENTATION PRESERVATION
    # ============================================================================
    (
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
data:
  password: c3VwZXJzZWNyZXQ=
  username: YWRtaW4=
type: Opaque""",
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
data:
  __MASKED_SECRET_DATA__
type: Opaque""",
        "Secret with 2-space indentation (standard kubectl)"
    ),
    (
        """apiVersion: v1
kind: Secret
metadata:
    name: test-secret
data:
    password: c3VwZXJzZWNyZXQ=
    username: YWRtaW4=
type: Opaque""",
        """apiVersion: v1
kind: Secret
metadata:
    name: test-secret
data:
    __MASKED_SECRET_DATA__
type: Opaque""",
        "Secret with 4-space indentation"
    ),
    (
        """apiVersion: v1
kind: Secret
metadata:
	name: test-secret
data:
	password: c3VwZXJzZWNyZXQ=
	username: YWRtaW4=
type: Opaque""",
        """apiVersion: v1
kind: Secret
metadata:
	name: test-secret
data:
	password: c3VwZXJzZWNyZXQ=
	username: YWRtaW4=
type: Opaque""",
        "Secret with tab indentation (tabs not valid in YAML, returns unchanged)"
    ),
    (
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
data:
      password: c3VwZXJzZWNyZXQ=
      username: YWRtaW4=
      nested:
        value: dmFsdWU=
type: Opaque""",
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
data:
      __MASKED_SECRET_DATA__
type: Opaque""",
        "Secret with 6-space indentation (nested level)"
    ),
    (
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
stringData:
    username: admin
    password: supersecret
type: Opaque""",
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
stringData:
    __MASKED_SECRET_DATA__
type: Opaque""",
        "Secret with stringData and 4-space indentation"
    ),
    
    # ============================================================================
    # EDGE CASES
    # ============================================================================
    (
        "",
        "",
        "Empty string"
    ),
    (
        "some random text",
        "some random text",
        "Random text without Kubernetes resources"
    ),
    (
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
type: Opaque""",
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
type: Opaque""",
        "Secret without data section"
    ),
    (
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
data:
type: Opaque""",
        """apiVersion: v1
kind: Secret
metadata:
  name: test-secret
data:
 __MASKED_SECRET_DATA__
type: Opaque""",
        "Secret with empty data section"
    ),
    (
        """apiVersion: v1
kind: Secret
metadata:
  name: secret1
data:
  password: c3VwZXJzZWNyZXQ=

---

apiVersion: v1
kind: ConfigMap
metadata:
  name: config1
data:
  key: value""",
        """apiVersion: v1
kind: Secret
metadata:
  name: secret1
data:
  __MASKED_SECRET_DATA__
---

apiVersion: v1
kind: ConfigMap
metadata:
  name: config1
data:
  key: value""",
        "Multi-doc with unusual separator spacing (normalizes separator)"
    ),
    
    # ============================================================================
    # MALFORMED INPUT - Should handle gracefully
    # ============================================================================
    (
        """apiVersion: v1
kind: Secret
data:
  [this is not valid yaml""",
        """apiVersion: v1
kind: Secret
data:
  [this is not valid yaml""",
        "Malformed YAML - should return unchanged"
    ),
    (
        '{"kind":"Secret","data":{"incomplete',
        '{"kind":"Secret","data":{"incomplete',
        "Malformed JSON - should return unchanged"
    ),
]


@pytest.mark.unit
class TestKubernetesSecretMaskerMatrix:
    """Test KubernetesSecretMasker using matrix approach."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.masker = KubernetesSecretMasker()
    
    @pytest.mark.parametrize("input_data,expected_output,description", TEST_CASES)
    def test_masking_matrix(self, input_data, expected_output, description):
        """Test masking with matrix of input/expected output pairs."""
        # Use applies_to() first, then mask() - mirrors actual service usage
        if self.masker.applies_to(input_data):
            result = self.masker.mask(input_data)
        else:
            # If applies_to returns False, data should remain unchanged
            result = input_data
        
        assert result == expected_output, f"\nTest: {description}\n\nInput:\n{input_data}\n\nExpected:\n{expected_output}\n\nGot:\n{result}"
    
    def test_masker_name(self):
        """Test masker name."""
        assert self.masker.name() == "kubernetes_secret"
    
    @pytest.mark.parametrize("input_data,should_apply", [
        ("kind: Secret\ndata:\n  key: value", True),
        ('{"kind":"Secret","data":{}}', True),
        ("kind: ConfigMap\ndata:\n  key: value", False),
        ('{"kind":"ConfigMap","data":{}}', False),
        ("This is about Secret management", False),
        ("The kind of Secret we need", False),
        ("random text", False),
        ("", False),
    ])
    def test_applies_to_matrix(self, input_data, should_apply):
        """Test applies_to with various inputs."""
        result = self.masker.applies_to(input_data)
        assert result == should_apply, f"applies_to({input_data!r}) should be {should_apply}, got {result}"
    
    def test_mask_json_format_produces_compact_output(self):
        """Test that _mask_json_format produces compact single-line JSON, not pretty-printed.
        
        This ensures consistency with _mask_json_in_text and prevents formatting changes
        that could break tests or cause semantic diffs.
        """
        # Input: compact JSON Secret
        input_json = '{"apiVersion":"v1","kind":"Secret","metadata":{"name":"test"},"data":{"password":"c3VwZXJzZWNyZXRwYXNzd29yZDEyMw=="},"type":"Opaque"}'
        expected = '{"apiVersion":"v1","kind":"Secret","metadata":{"name":"test"},"data":"__MASKED_SECRET_DATA__","type":"Opaque"}'
        
        # Call _mask_json_format directly to test this specific code path
        result = self.masker._mask_json_format(input_json)
        
        # Verify it returns compact JSON (no newlines, no extra spaces)
        assert result == expected, f"\nExpected compact JSON:\n{expected}\n\nGot:\n{result}"
        assert '\n' not in result, "Result should be single-line JSON without newlines"
    
    def test_mask_json_format_consistency_with_mask_json_in_text(self):
        """Test that _mask_json_format and _mask_json_in_text use the same formatting.
        
        Both functions should produce identical output format (compact JSON) to maintain
        consistency across the codebase.
        """
        input_json = '{"apiVersion":"v1","kind":"Secret","metadata":{"name":"test"},"stringData":{"key":"value"},"type":"Opaque"}'
        
        # Get results from both methods
        result_from_json_format = self.masker._mask_json_format(input_json)
        result_from_json_in_text = self.masker._mask_json_in_text(input_json)
        
        # Both should produce the same compact format
        assert result_from_json_format == result_from_json_in_text, \
            f"Both methods should produce identical formatting:\n" \
            f"_mask_json_format: {result_from_json_format}\n" \
            f"_mask_json_in_text: {result_from_json_in_text}"
    
    def test_document_count_mismatch_triggers_fallback(self, caplog):
        """Test that document count mismatch triggers fallback masking with warning.
        
        When the number of parsed YAML docs differs from the number of text splits,
        a warning should be logged and fallback masking should be applied.
        """
        # Input that will split into 3 parts but parse as 2 docs
        input_with_extra_separator = """apiVersion: v1
kind: Secret
metadata:
  name: secret1
data:
  password: c3VwZXJzZWNyZXQ=
---
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: config1
data:
  key: value"""
        
        # This input splits by '\n---\n' into 3 parts but YAML parses as 2 docs (empty doc is skipped)
        result = self.masker.mask(input_with_extra_separator)
        
        # Verify warning was logged
        assert any("Document count mismatch" in record.message for record in caplog.records), \
            "Expected warning about document count mismatch to be logged"
        
        # Verify data was still masked (fallback worked)
        assert "__MASKED_SECRET_DATA__" in result, \
            "Secret data should still be masked via fallback path"