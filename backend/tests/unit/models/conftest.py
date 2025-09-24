"""
Shared fixtures and utilities for model tests.

This module provides common fixtures and utilities to reduce redundancy
across model test files.
"""

import pytest

from tests.utils import ModelValidationTester


@pytest.fixture
def model_validation_tester():
    """Shared utility for testing model validation."""
    return ModelValidationTester()


@pytest.fixture
def sample_kubernetes_alert_data():
    """Sample data for Kubernetes alert model tests."""
    return {
        "alert_type": "kubernetes",
        "runbook": "https://github.com/company/runbooks/blob/main/k8s.md",
        "severity": "critical",
        "timestamp": 1640995200000000,
        "data": {
            "environment": "production",
            "cluster": "main-cluster",
            "namespace": "default",
            "message": "Namespace is terminating",
            "alert": "NamespaceTerminating"
        }
    }


@pytest.fixture
def sample_generic_alert_data():
    """Sample data for generic alert model tests."""
    return {
        "alert_type": "generic",
        "runbook": "https://example.com/runbook",
        "severity": "warning",
        "timestamp": 1640995200000000,
        "data": {
            "environment": "production",
            "message": "Generic alert message",
            "source": "monitoring-system"
        }
    }


@pytest.fixture
def sample_chain_stage_data():
    """Sample data for chain stage model tests."""
    return {
        "name": "analysis",
        "agent": "KubernetesAgent",
        "iteration_strategy": "react"
    }


@pytest.fixture
def sample_chain_definition_data():
    """Sample data for chain definition model tests."""
    return {
        "chain_id": "kubernetes-troubleshooting",
        "alert_types": ["kubernetes"],
        "stages": [
            {
                "name": "data-collection",
                "agent": "KubernetesAgent",
                "iteration_strategy": "react"
            },
            {
                "name": "analysis",
                "agent": "KubernetesAgent",
                "iteration_strategy": "react"
            }
        ],
        "description": "Kubernetes troubleshooting chain"
    }


@pytest.fixture
def sample_websocket_message_data():
    """Sample data for WebSocket message model tests."""
    return {
        "type": "subscription",
        "channel": "alerts",
        "timestamp": 1640995200000000
    }


@pytest.fixture
def sample_masking_pattern_data():
    """Sample data for masking pattern model tests."""
    return {
        "name": "api_key_pattern",
        "pattern": r"api_key['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9]{32,}['\"]?",
        "replacement": "[API_KEY_MASKED]",
        "enabled": True
    }


@pytest.fixture
def sample_masking_config_data():
    """Sample data for masking config model tests."""
    return {
        "enabled": True,
        "default_replacement": "[MASKED]",
        "custom_patterns": [
            {
                "name": "api_key_pattern",
                "pattern": r"api_key['\"]?\s*[:=]\s*['\"]?[a-zA-Z0-9]{32,}['\"]?",
                "replacement": "[API_KEY_MASKED]",
                "enabled": True
            },
            {
                "name": "password_pattern",
                "pattern": r"password['\"]?\s*[:=]\s*['\"]?[^\s\"']+['\"]?",
                "replacement": "[PASSWORD_MASKED]",
                "enabled": True
            }
        ]
    }


@pytest.fixture
def sample_agent_config_data():
    """Sample data for agent config model tests."""
    return {
        "name": "kubernetes-agent",
        "alert_types": ["kubernetes"],
        "mcp_servers": ["kubernetes-server"],
        "iteration_strategy": "react",
        "transport": {
            "kubeconfig": "/path/to/kubeconfig",
            "context": "production"
        }
    }


@pytest.fixture
def sample_mcp_server_config_data():
    """Sample data for MCP server config model tests."""
    return {
        "server_id": "kubernetes-server",
        "command": "kubectl",
        "args": ["proxy", "--port=8001"],
        "env": {
            "KUBECONFIG": "/path/to/kubeconfig"
        },
        "enabled": True
    }


class ModelTestHelpers:
    """Helper methods for model testing."""
    
    @staticmethod
    def test_serialization_roundtrip(model_class, valid_data):
        """Test that a model can be serialized and deserialized correctly."""
        # Create model instance
        model_instance = model_class(**valid_data)
        
        # Serialize to dict (handle both Pydantic and dataclass models)
        if hasattr(model_instance, 'model_dump'):
            # Pydantic v2
            model_dict = model_instance.model_dump()
        elif hasattr(model_instance, 'dict'):
            # Pydantic v1
            model_dict = model_instance.dict()
        elif hasattr(model_instance, 'to_dict'):
            # Custom dataclass with to_dict method
            model_dict = model_instance.to_dict()
        else:
            # Fallback to asdict for dataclasses
            from dataclasses import asdict
            model_dict = asdict(model_instance)
        
        # Deserialize back to model
        reconstructed_model = model_class(**model_dict)
        
        # Verify they're equal
        assert model_instance == reconstructed_model
        
        return model_instance, model_dict
    
    @staticmethod
    def test_json_serialization(model_class, valid_data):
        """Test that a model can be serialized to and from JSON."""
        # Create model instance
        model_instance = model_class(**valid_data)
        
        # Serialize to JSON
        model_json = model_instance.model_dump_json()
        
        # Deserialize from JSON
        reconstructed_model = model_class.model_validate_json(model_json)
        
        # Verify they're equal
        assert model_instance == reconstructed_model
        
        return model_instance, model_json
    
    @staticmethod
    def test_optional_fields(model_class, required_fields, optional_fields, valid_data):
        """Test that optional fields can be omitted."""
        # Test with all fields
        full_model = model_class(**valid_data)
        
        # Test with only required fields
        required_data = {field: valid_data[field] for field in required_fields}
        minimal_model = model_class(**required_data)
        
        # Verify both are valid
        assert full_model is not None
        assert minimal_model is not None
        
        return full_model, minimal_model
    
    @staticmethod
    def test_field_defaults(model_class, field_defaults, valid_data):
        """Test that fields have correct default values."""
        # Create model with minimal data
        minimal_data = {k: v for k, v in valid_data.items() if k not in field_defaults}
        model_instance = model_class(**minimal_data)
        
        # Check default values
        for field, expected_default in field_defaults.items():
            actual_value = getattr(model_instance, field)
            assert actual_value == expected_default, \
                f"Field {field} has value {actual_value}, expected {expected_default}"
        
        return model_instance


@pytest.fixture
def model_test_helpers():
    """Shared helper methods for model testing."""
    return ModelTestHelpers()

