"""
Unit tests for Alert and ProcessingAlert models from EP-0021.

These tests verify the two-model architecture's BUSINESS LOGIC, specifically:
1. ProcessingAlert.from_api_alert() transformation logic
2. Name collision prevention between client data and metadata
3. Data preservation (pristine client data, no pollution)
4. Complex nested JSON handling

Note: We don't test basic Pydantic validation (required fields, defaults, etc.)
as that's already tested by Pydantic itself. We test OUR logic.
"""

import pytest

from tarsy.models.alert import Alert, ProcessingAlert
from tarsy.utils.timestamp import now_us


@pytest.mark.unit  
class TestProcessingAlertTransformation:
    """Test ProcessingAlert.from_api_alert() transformation - our core business logic."""
    
    def test_from_api_alert_basic_transformation(self):
        """Test basic transformation from Alert to ProcessingAlert."""
        alert = Alert(
            alert_type="kubernetes",
            runbook="https://github.com/company/runbooks/blob/main/k8s.md",
            severity="critical",
            timestamp=123456789,
            data={
                "namespace": "prod",
                "pod": "api-123"
            }
        )
        
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
        # Metadata correctly extracted
        assert processing_alert.alert_type == "kubernetes"
        assert processing_alert.severity == "critical"
        assert processing_alert.timestamp == 123456789
        assert processing_alert.runbook_url == "https://github.com/company/runbooks/blob/main/k8s.md"
        
        # Client data pristine
        assert processing_alert.alert_data == {
            "namespace": "prod",
            "pod": "api-123"
        }
    
    def test_default_severity_when_not_provided(self):
        """Test transformation defaults severity to 'warning' if not provided."""
        alert = Alert(
            alert_type="kubernetes",
            data={"test": "data"}
        )
        
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
        assert processing_alert.severity == "warning"
    
    def test_auto_generate_timestamp_when_not_provided(self):
        """Test transformation auto-generates timestamp if not provided."""
        alert = Alert(
            alert_type="kubernetes",
            data={"test": "data"}
        )
        
        before = now_us()
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        after = now_us()
        
        # Timestamp should be generated within test duration
        assert before <= processing_alert.timestamp <= after
    
    def test_uses_default_alert_type_when_not_provided(self):
        """Test transformation uses default alert_type when not provided in alert."""
        alert = Alert(
            data={"test": "data"}
        )
        
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="PodCrashLoop")
        
        # Should use the default alert type
        assert processing_alert.alert_type == "PodCrashLoop"
    
    def test_explicit_alert_type_overrides_default(self):
        """Test that explicitly provided alert_type takes precedence over default."""
        alert = Alert(
            alert_type="custom-alert",
            data={"test": "data"}
        )
        
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
        # Should use the explicit alert type, not the default
        assert processing_alert.alert_type == "custom-alert"
    
    def test_extract_environment_from_client_data(self):
        """Test transformation extracts environment from client data (but keeps it there!)."""
        alert = Alert(
            alert_type="kubernetes",
            data={
                "environment": "staging",
                "pod": "test-pod"
            }
        )
        
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
        # Environment extracted as metadata
        assert processing_alert.environment == "staging"
        
        # But ALSO kept in client data (pristine!)
        assert processing_alert.alert_data["environment"] == "staging"
    
    
    def test_preserves_complex_nested_json(self):
        """Test transformation preserves complex nested JSON structures exactly."""
        alert = Alert(
            alert_type="prometheus",
            data={
                "receiver": "team-X-pager",
                "status": "firing",
                "alerts": [
                    {
                        "status": "firing",
                        "labels": {
                            "alertname": "HighMemoryUsage",
                            "instance": "server-01:9100",
                            "severity": "warning"
                        },
                        "annotations": {
                            "description": "Memory usage is above 90%",
                            "runbook_url": "https://wiki/memory-runbook"
                        },
                        "metrics": [
                            {"timestamp": 1234567, "value": 92.5},
                            {"timestamp": 1234568, "value": 93.2}
                        ]
                    }
                ],
                "groupLabels": {"alertname": "HighMemoryUsage"}
            }
        )
        
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
        # Complex nested structure preserved exactly
        assert processing_alert.alert_data["receiver"] == "team-X-pager"
        assert len(processing_alert.alert_data["alerts"]) == 1
        assert processing_alert.alert_data["alerts"][0]["labels"]["severity"] == "warning"
        assert len(processing_alert.alert_data["alerts"][0]["metrics"]) == 2
        assert processing_alert.alert_data["alerts"][0]["metrics"][0]["value"] == 92.5
        
        # Nested structures stay nested (not flattened)
        assert isinstance(processing_alert.alert_data["alerts"], list)
        assert isinstance(processing_alert.alert_data["alerts"][0]["labels"], dict)
        assert isinstance(processing_alert.alert_data["alerts"][0]["metrics"], list)


@pytest.mark.unit
class TestNameCollisionPrevention:
    """Test that EP-0021 prevents name collisions between client data and our metadata."""
    
    def test_client_severity_does_not_collide_with_metadata_severity(self):
        """Test that client can have their own 'severity' field without collision."""
        alert = Alert(
            alert_type="kubernetes",
            severity="critical",  # Our metadata
            data={
                "severity": "INFO",  # Client's field
                "message": "Test alert"
            }
        )
        
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
        # Our metadata has our value
        assert processing_alert.severity == "critical"
        
        # Client's data has their value (no collision!)
        assert processing_alert.alert_data["severity"] == "INFO"
    
    def test_client_timestamp_does_not_collide_with_metadata_timestamp(self):
        """Test that client can have their own 'timestamp' field without collision."""
        our_timestamp = 1759360789012345
        alert = Alert(
            alert_type="kubernetes",
            timestamp=our_timestamp,  # Our metadata
            data={
                "timestamp": "2025-10-01T10:00:00Z",  # Client's field (different format!)
                "message": "Test alert"
            }
        )
        
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
        # Our metadata has our value (int microseconds)
        assert processing_alert.timestamp == our_timestamp
        
        # Client's data has their value (ISO string) - no collision!
        assert processing_alert.alert_data["timestamp"] == "2025-10-01T10:00:00Z"
    


@pytest.mark.unit
class TestDataPreservationAndPurity:
    """Test that client data remains pristine - no pollution, no modification."""
    
    def test_client_data_not_polluted_with_metadata(self):
        """Test that client data does NOT contain any of our internal metadata."""
        alert = Alert(
            alert_type="kubernetes",
            severity="critical",
            runbook="https://example.com/runbook",
            timestamp=123456789,
            data={
                "pod": "api-123",
                "namespace": "prod"
            }
        )
        
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
        # Client data should ONLY contain what they sent
        assert processing_alert.alert_data == {
            "pod": "api-123",
            "namespace": "prod"
        }
        
        # Should NOT contain any of our metadata fields
        assert "alert_type" not in processing_alert.alert_data
        assert "severity" not in processing_alert.alert_data
        assert "runbook" not in processing_alert.alert_data
        assert "timestamp" not in processing_alert.alert_data
        assert "runbook_url" not in processing_alert.alert_data
    
    def test_client_data_with_conflicting_names_preserved_pristine(self):
        """Test that even when client uses our field names, their data stays pristine."""
        alert = Alert(
            alert_type="kubernetes",
            severity="critical",
            data={
                "namespace": "prod",
                "severity": "user-severity",  # Client's severity (different!)
                "custom_field": "value",
                "nested": {
                    "deeply": {
                        "nested": "value"
                    }
                },
                "array": [1, 2, 3]
            }
        )
        
        processing_alert = ProcessingAlert.from_api_alert(alert, default_alert_type="kubernetes")
        
        # Client data completely pristine - no merging, no overwrites
        assert processing_alert.alert_data == {
            "namespace": "prod",
            "severity": "user-severity",  # ← PRESERVED!
            "custom_field": "value",
            "nested": {
                "deeply": {
                    "nested": "value"
                }
            },
            "array": [1, 2, 3]
        }
        
        # Our metadata separate
        assert processing_alert.severity == "critical"  # Our value, not theirs
