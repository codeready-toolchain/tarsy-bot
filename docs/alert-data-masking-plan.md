# Alert Data Masking Implementation Plan

## Executive Summary

This document outlines the plan for implementing basic data masking for incoming alert data at the `/alerts` endpoint. The implementation will leverage TARSy's existing masking infrastructure (DataMaskingService and built-in masking patterns) to automatically detect and mask sensitive information in alert payloads before processing.

## Background

### Current State

1. **Existing Masking Infrastructure**: TARSy has a comprehensive data masking system currently used for MCP server responses:
   - `DataMaskingService` ([data_masking_service.py](../backend/tarsy/services/data_masking_service.py))
   - Built-in masking patterns in [builtin_config.py](../backend/tarsy/config/builtin_config.py)
   - Pattern groups for convenient configuration (basic, secrets, security, kubernetes, all)

2. **Alert Endpoint**: The `/alerts` endpoint ([alert_controller.py:74](../backend/tarsy/controllers/alert_controller.py#L74)) currently:
   - Validates payload size (10MB max)
   - Parses and validates JSON structure
   - Performs basic XSS sanitization (removes `<>'"` and control characters)
   - Validates using Pydantic Alert model
   - Does NOT mask sensitive data patterns

3. **Alert Data Flow**:
   ```
   Client → /alerts endpoint → Sanitization → Validation → ProcessingAlert → Background processing
   ```

### Problem Statement

Incoming alerts may contain sensitive information that should be masked before:
- Being stored in the history database
- Being sent to LLM providers
- Being logged in application logs
- Being displayed in the dashboard

Examples of sensitive data in alerts:
- API keys, tokens, passwords embedded in error messages
- Email addresses in alert labels/annotations
- Certificate data in configuration snapshots
- Base64-encoded secrets in Kubernetes resource dumps
- SSH keys in deployment configurations

## Proposed Solution

### Recommended Approach: "security" Pattern Group

The **"security" pattern group** is the most appropriate choice for alert data masking because:

1. **Comprehensive Coverage**: Includes all critical security-sensitive patterns:
   - `api_key`: API keys and similar credentials
   - `password`: Password fields in various formats
   - `token`: Access tokens, bearer tokens, JWTs
   - `certificate`: SSL/TLS certificates and private keys
   - `certificate_authority_data`: CA certificates in kubeconfig/YAML
   - `email`: Email addresses (PII)
   - `ssh_key`: SSH public keys

2. **Balanced Approach**:
   - More comprehensive than "basic" (api_key, password only)
   - More focused than "all" (avoids overly aggressive base64 masking)
   - Avoids false positives from kubernetes-specific patterns designed for structured YAML

3. **Production-Ready**: These patterns are battle-tested in the MCP response masking system

### Alternative Options Considered

| Pattern Group | Pros | Cons | Recommendation |
|---------------|------|------|----------------|
| **basic** | Minimal performance impact | Only masks api_key and password - insufficient coverage | ❌ Not recommended |
| **secrets** | Good balance | Missing certificates and emails | ⚠️ Acceptable but incomplete |
| **security** | Comprehensive security coverage | Slightly more processing overhead | ✅ **RECOMMENDED** |
| **kubernetes** | Kubernetes-optimized | Too specific; includes YAML structure patterns that may cause false positives in unstructured alert data | ❌ Not recommended |
| **all** | Maximum coverage | Aggressive base64 masking may cause false positives; higher performance overhead | ⚠️ Only if extreme caution required |

## Implementation Design

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ /alerts Endpoint (alert_controller.py)                      │
│                                                              │
│  1. Payload validation (existing)                           │
│  2. JSON parsing (existing)                                 │
│  3. XSS sanitization (existing)                             │
│  4. ▶ DATA MASKING (NEW) ◀                                  │
│  5. Pydantic validation (existing)                          │
│  6. ProcessingAlert creation (existing)                     │
│  7. Background task queue (existing)                        │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ AlertDataMaskingService (NEW)                               │
│                                                              │
│  • Lightweight wrapper around DataMaskingService            │
│  • Configured with "security" pattern group                 │
│  • Masks arbitrary JSON structures                          │
│  • No dependency on MCPServerRegistry                       │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ DataMaskingService (EXISTING)                               │
│                                                              │
│  • Applies regex patterns to string content                 │
│  • Recursively processes nested data structures             │
│  • Handles errors gracefully with fail-safe masking         │
└─────────────────────────────────────────────────────────────┘
```

### Component Design

#### 1. AlertDataMaskingService (New)

**Location**: `backend/tarsy/services/alert_data_masking_service.py`

**Purpose**:
- Lightweight service specifically for masking incoming alert data
- Configured with the "security" pattern group by default
- Does not depend on MCPServerRegistry (unlike general DataMaskingService usage)

**Key Features**:
```python
class AlertDataMaskingService:
    """Service for masking sensitive data in incoming alert payloads."""

    def __init__(self):
        # Initialize DataMaskingService without MCP registry dependency
        self.masking_service = DataMaskingService(mcp_registry=None)

        # Pre-expand "security" pattern group for performance
        self.alert_patterns = self._get_security_patterns()

    def mask_alert_data(self, alert_data: dict) -> dict:
        """Mask sensitive data in alert payload using security patterns."""
        # Use DataMaskingService's _mask_data_structure method
        return self.masking_service._mask_data_structure(
            alert_data,
            self.alert_patterns
        )
```

#### 2. Integration Point in alert_controller.py

**Location**: After sanitization, before Pydantic validation

**Rationale**:
- Masking should happen after basic sanitization (XSS prevention)
- But before validation so masked data is validated correctly
- Masked data flows through all downstream systems (database, LLM, logs)

**Code Insertion Point** ([alert_controller.py:168](../backend/tarsy/controllers/alert_controller.py#L168)):

```python
# Sanitize the entire payload
sanitized_data = deep_sanitize(raw_data)

# ▶▶▶ INSERT MASKING HERE ◀◀◀
# Mask sensitive data patterns before validation
masked_data = alert_masking_service.mask_alert_data(sanitized_data)

# Validate using Alert model
alert_data = Alert(**masked_data)  # Changed from sanitized_data
```

### Data Flow Example

**Input Alert** (with sensitive data):
```json
{
  "alert_type": "ApplicationError",
  "data": {
    "error_message": "Failed to connect: api_key=sk_live_abc123xyz789",
    "config": {
      "database_url": "postgres://user:MyP@ssw0rd@db.example.com/prod",
      "admin_email": "admin@company.com"
    },
    "certificate": "-----BEGIN PRIVATE KEY-----\nMIIEv...\n-----END PRIVATE KEY-----"
  }
}
```

**After Masking**:
```json
{
  "alert_type": "ApplicationError",
  "data": {
    "error_message": "Failed to connect: \"api_key\": \"***MASKED_API_KEY***\"",
    "config": {
      "database_url": "postgres://user:\"password\": \"***MASKED_PASSWORD***\"@db.example.com/prod",
      "admin_email": "***MASKED_EMAIL***"
    },
    "certificate": "***MASKED_CERTIFICATE***"
  }
}
```

## Implementation Steps

### Phase 1: Core Implementation

1. **Create AlertDataMaskingService**
   - File: `backend/tarsy/services/alert_data_masking_service.py`
   - Initialize DataMaskingService (no registry dependency)
   - Pre-expand "security" pattern group
   - Implement `mask_alert_data()` method
   - Add comprehensive docstrings

2. **Integrate into alert_controller.py**
   - Import AlertDataMaskingService at module level
   - Initialize service instance (singleton pattern)
   - Add masking step after sanitization, before validation
   - Update error handling to catch masking errors
   - Add logging for masking operations

3. **Configuration (Optional Enhancement)**
   - Add settings to `backend/tarsy/config/settings.py`:
     ```python
     # Alert data masking configuration
     ALERT_MASKING_ENABLED: bool = True
     ALERT_MASKING_PATTERN_GROUP: str = "security"
     ```
   - Allow disabling masking for development/testing
   - Allow customizing pattern group via environment variable

### Phase 2: Testing

1. **Unit Tests**
   - File: `backend/tests/unit/services/test_alert_data_masking_service.py`
   - Test each pattern type (api_key, password, token, certificate, email, ssh_key)
   - Test nested data structures (dicts, lists, mixed)
   - Test edge cases (empty data, null values, non-string types)
   - Test fail-safe behavior (malformed patterns, errors)
   - Performance tests (large payloads)

2. **Integration Tests**
   - File: `backend/tests/integration/test_alert_masking_integration.py`
   - Test full alert submission flow with sensitive data
   - Verify masked data in database
   - Verify masked data in API responses
   - Verify masked data in WebSocket events
   - Test that processing continues correctly with masked data

3. **End-to-End Tests**
   - File: `backend/tests/e2e/test_alert_masking_e2e.py`
   - Submit alerts via HTTP POST
   - Verify masking in history database
   - Verify masking in dashboard display
   - Test real-world alert scenarios (Kubernetes, application errors)

### Phase 3: Documentation

1. **Code Documentation**
   - Comprehensive docstrings in AlertDataMaskingService
   - Inline comments explaining pattern choices
   - Update alert_controller.py docstrings

2. **User Documentation**
   - Update `docs/` with masking behavior explanation
   - Document which patterns are used and why
   - Provide examples of masked vs. unmasked data
   - Add troubleshooting guide for masking issues

3. **Configuration Documentation**
   - Document environment variables for customization
   - Provide examples for different security postures
   - Explain performance implications

### Phase 4: Monitoring & Validation

1. **Logging Enhancements**
   - Log masking statistics (patterns matched, data size)
   - Log masking errors with context
   - Add debug logging for pattern application

2. **Metrics (Future Enhancement)**
   - Track masking operations per alert
   - Monitor masking performance impact
   - Alert on masking failures

## Security Considerations

### Threat Model

1. **Credential Leakage**:
   - **Risk**: API keys, passwords, tokens exposed in alert data
   - **Mitigation**: "security" pattern group masks all common credential formats

2. **PII Exposure**:
   - **Risk**: Email addresses, names in alert annotations
   - **Mitigation**: Email pattern included in "security" group
   - **Note**: Consider adding more PII patterns if needed

3. **Certificate/Key Leakage**:
   - **Risk**: SSL/TLS certificates, SSH keys in configuration dumps
   - **Mitigation**: Certificate and ssh_key patterns included

4. **Encoded Secrets**:
   - **Risk**: Base64-encoded secrets in Kubernetes resources
   - **Mitigation**: NOT included in "security" group to avoid false positives
   - **Recommendation**: Use "all" group if aggressive base64 masking required

### Defense in Depth

Masking is one layer in TARSy's security strategy:

1. **Input Validation** (existing): Prevents malformed/malicious payloads
2. **XSS Sanitization** (existing): Removes dangerous characters
3. **Data Masking** (new): Removes sensitive patterns
4. **Access Control** (existing): OAuth2 proxy, JWT authentication
5. **Audit Logging** (existing): History service tracks all operations

### Limitations

1. **Pattern-Based Detection**:
   - May not catch all sensitive data formats
   - Custom/proprietary credential formats may not be detected
   - Context-specific secrets may be missed

2. **False Negatives**:
   - Novel encoding schemes
   - Obfuscated credentials
   - Domain-specific secret formats

3. **False Positives**:
   - Legitimate data matching patterns (e.g., valid base64 that isn't secret)
   - May break alert processing if essential data is masked

### Recommendations

1. **Monitoring**: Track masking operations and review masked data periodically
2. **Tuning**: Adjust patterns based on false positive/negative rates
3. **Custom Patterns**: Add organization-specific patterns as needed
4. **Complementary Controls**: Use network segmentation, encryption, access control
5. **Data Classification**: Tag alerts with sensitivity levels for tiered masking

## Performance Impact

### Expected Overhead

1. **Regex Compilation**: One-time cost at service initialization
2. **Pattern Matching**: O(n) where n = total string content in alert payload
3. **Recursive Traversal**: O(m) where m = number of keys/values in nested structure

### Optimization Strategies

1. **Pre-compiled Patterns**: DataMaskingService compiles patterns once at startup
2. **Lazy Evaluation**: Only process string values (skip numbers, booleans, null)
3. **Early Exit**: Skip masking if no string content present
4. **Pattern Ordering**: Apply most common patterns first (api_key, password, token)

### Benchmarks (Estimated)

| Alert Size | Masking Time | Impact |
|-----------|--------------|---------|
| Small (1KB) | <5ms | Negligible |
| Medium (100KB) | 10-50ms | Minimal |
| Large (1MB) | 100-500ms | Noticeable |
| Max (10MB) | 1-5s | Significant |

**Note**: Actual performance depends on:
- Complexity of alert data structure
- Number of patterns that match
- CPU performance

### Mitigation for Large Alerts

1. **Sampling**: Only mask first N characters of very long strings
2. **Timeout**: Set maximum masking time, fail-safe if exceeded
3. **Selective Masking**: Only mask specific fields (e.g., `data`, `annotations`)
4. **Async Processing**: Masking already happens in background task

## Configuration Reference

### Environment Variables (Proposed)

```bash
# Enable/disable alert data masking
ALERT_MASKING_ENABLED=true

# Pattern group to use for alert masking
# Options: basic, secrets, security, kubernetes, all
ALERT_MASKING_PATTERN_GROUP=security

# Enable detailed masking logs
ALERT_MASKING_DEBUG=false
```

### Code Configuration (Proposed)

```python
# backend/tarsy/config/settings.py

class Settings(BaseSettings):
    # ... existing settings ...

    # Alert Data Masking
    alert_masking_enabled: bool = Field(
        default=True,
        description="Enable data masking for incoming alert payloads"
    )

    alert_masking_pattern_group: str = Field(
        default="security",
        description="Pattern group to use for alert masking (basic|secrets|security|kubernetes|all)"
    )

    alert_masking_debug: bool = Field(
        default=False,
        description="Enable debug logging for alert masking operations"
    )
```

## Migration & Rollout

### Rollout Strategy

1. **Phase 1: Testing Environment**
   - Deploy to dev/test environment first
   - Verify masking with sample alerts
   - Monitor for false positives/negatives

2. **Phase 2: Production with Logging**
   - Enable masking in production
   - Log all masking operations extensively
   - Review logs for issues

3. **Phase 3: Optimization**
   - Tune patterns based on production data
   - Add custom patterns as needed
   - Optimize performance if needed

### Rollback Plan

If issues arise:

1. **Quick Disable**: Set `ALERT_MASKING_ENABLED=false` and restart
2. **Pattern Adjustment**: Change `ALERT_MASKING_PATTERN_GROUP` to less aggressive group
3. **Code Rollback**: Revert alert_controller.py changes

### Backward Compatibility

- **API Contract**: No changes to `/alerts` endpoint contract
- **Database Schema**: No schema changes required
- **Existing Alerts**: Historic alerts remain unmasked (masking is forward-only)
- **Client Impact**: No client changes required

## Testing Strategy

### Test Scenarios

1. **Happy Path**:
   - Submit alert with sensitive data
   - Verify data is masked correctly
   - Verify processing continues normally

2. **Edge Cases**:
   - Empty alert data
   - Alert with no sensitive data
   - Alert with only sensitive data
   - Deeply nested structures (10+ levels)
   - Large arrays (1000+ elements)

3. **Error Handling**:
   - Malformed regex patterns (shouldn't happen with built-ins)
   - Masking service failures
   - Out of memory scenarios

4. **Performance**:
   - Small alerts (1KB): <5ms masking time
   - Medium alerts (100KB): <50ms masking time
   - Large alerts (1MB): <500ms masking time
   - Max alerts (10MB): <5s masking time

### Test Data Examples

```python
# Example test cases
TEST_ALERTS = {
    "api_key_in_error": {
        "alert_type": "APIError",
        "data": {"error": "Auth failed with api_key=sk_live_abc123"}
    },
    "password_in_config": {
        "alert_type": "ConfigError",
        "data": {"db": "postgres://user:SecretPass123@host/db"}
    },
    "email_in_labels": {
        "alert_type": "Alert",
        "data": {"labels": {"owner": "admin@company.com"}}
    },
    "certificate_in_secret": {
        "alert_type": "K8sSecret",
        "data": {"tls.crt": "-----BEGIN CERTIFICATE-----\n..."}
    },
    "nested_sensitive_data": {
        "alert_type": "Alert",
        "data": {
            "level1": {
                "level2": {
                    "level3": {"token": "Bearer eyJhbGc..."}
                }
            }
        }
    }
}
```

## Open Questions & Future Enhancements

### Open Questions

1. **Custom Patterns**: Should we provide a UI for adding custom masking patterns?
2. **Selective Masking**: Should users be able to disable masking for specific alert types?
3. **Audit Trail**: Should we log what was masked (pattern name, location) for compliance?
4. **Unmasking**: Should admins have the ability to view unmasked data in certain scenarios?

### Future Enhancements

1. **Machine Learning-Based Detection**:
   - Train model to detect secrets beyond regex patterns
   - Context-aware detection (e.g., "this looks like a credential")

2. **Configurable Masking Per Alert Type**:
   - Different pattern groups for different alert types
   - Kubernetes alerts use "kubernetes" group
   - Application alerts use "security" group

3. **Masking Metrics Dashboard**:
   - Visualize masking statistics
   - Alert on unusual masking patterns
   - Track false positive rates

4. **Reversible Masking for Admins**:
   - Encrypt sensitive data instead of replacing
   - Allow privileged users to decrypt
   - Audit all decryption operations

5. **PII Detection Enhancement**:
   - Add patterns for phone numbers, SSNs, credit cards
   - Integrate with PII detection libraries
   - Support multiple locales/formats

6. **Performance Optimization**:
   - Implement pattern caching
   - Use compiled Rust regex library for speed
   - Parallelize masking for large payloads

## Success Criteria

### Functional Requirements

- ✅ Sensitive data is masked before storage/processing
- ✅ Masking works for all supported alert types
- ✅ Masking does not break alert processing
- ✅ Masked data is properly validated by Pydantic models
- ✅ Masking can be disabled via configuration

### Non-Functional Requirements

- ✅ Masking adds <50ms latency for typical alerts (100KB)
- ✅ Masking has >99% uptime (fail-safe on errors)
- ✅ False positive rate <5% (legitimate data incorrectly masked)
- ✅ False negative rate <10% (sensitive data not masked)
- ✅ Code coverage >80% for masking service

### Operational Requirements

- ✅ Logging provides visibility into masking operations
- ✅ Errors are handled gracefully without data loss
- ✅ Configuration is documented and easy to understand
- ✅ Performance impact is monitored and acceptable

## Conclusion

Implementing alert data masking using the "security" pattern group provides:

1. **Strong Security**: Comprehensive coverage of common credential/PII patterns
2. **Minimal Impact**: Leverages existing, tested masking infrastructure
3. **Easy Integration**: Simple addition to existing alert processing flow
4. **Flexibility**: Configurable pattern groups for different security postures
5. **Production-Ready**: Built on battle-tested DataMaskingService

**Recommendation**: Proceed with implementation using the "security" pattern group as the default, with configuration options to adjust masking behavior as needed.

---

**Document Version**: 1.0
**Date**: 2025-10-22
**Author**: TARSy Development Team
**Status**: Proposed
