"""Unit tests for agent configuration Pydantic models."""

import pytest
from pydantic import ValidationError

from tarsy.models.agent_config import (
    AgentConfigModel,
    CombinedConfigModel,
    MCPServerConfigModel,
)
from tarsy.models.constants import IterationStrategy


@pytest.mark.unit
class TestAgentConfigModel:
    """Test cases for AgentConfigModel validation."""

    def test_valid_agent_config(self):
        """Test valid agent configuration."""
        config_data = {
            "alert_types": ["security", "performance"],
            "mcp_servers": ["security-tools", "monitoring-server"],
            "custom_instructions": "Focus on threat detection and response."
        }
        
        config = AgentConfigModel(**config_data)
        
        assert config.alert_types == ["security", "performance"]
        assert config.mcp_servers == ["security-tools", "monitoring-server"]
        assert config.custom_instructions == "Focus on threat detection and response."

    def test_minimal_valid_agent_config(self):
        """Test minimal valid agent configuration."""
        config_data = {
            "alert_types": ["security"],
            "mcp_servers": ["security-tools"]
        }
        
        config = AgentConfigModel(**config_data)
        
        assert config.alert_types == ["security"]
        assert config.mcp_servers == ["security-tools"]
        assert config.custom_instructions == ""
        assert config.iteration_strategy == IterationStrategy.REACT  # Default value

    def test_serialization_roundtrip(self, model_test_helpers):
        """Test that agent config can be serialized and deserialized correctly."""
        valid_data = {
            "alert_types": ["security", "performance"],
            "mcp_servers": ["security-tools", "monitoring-server"],
            "custom_instructions": "Focus on threat detection and response.",
            "iteration_strategy": "react"
        }
        
        model_test_helpers.test_serialization_roundtrip(AgentConfigModel, valid_data)

    def test_required_fields_validation(self, model_validation_tester):
        """Test that required fields are enforced."""
        valid_data = {
            "alert_types": ["security"],
            "mcp_servers": ["security-tools"]
        }
        
        required_fields = ["alert_types", "mcp_servers"]
        model_validation_tester.test_required_fields(AgentConfigModel, required_fields, valid_data)

    @pytest.mark.parametrize("invalid_data,expected_error_type", [
        ({"alert_types": [], "mcp_servers": ["security-tools"]}, "too_short"),
        ({"alert_types": ["security"], "mcp_servers": []}, "too_short"),
        ({"alert_types": "security", "mcp_servers": ["security-tools"]}, "list_type"),
        ({"alert_types": ["security"], "mcp_servers": "security-tools"}, "list_type"),
    ])
    def test_field_validation(self, invalid_data, expected_error_type):
        """Test field validation for various invalid inputs."""
        with pytest.raises(ValidationError) as exc_info:
            AgentConfigModel(**invalid_data)
            
        errors = exc_info.value.errors()
        assert len(errors) >= 1
        assert any(error["type"] == expected_error_type for error in errors)

    @pytest.mark.parametrize("strategy_value,expected_strategy", [
        ("react", IterationStrategy.REACT),
        ("react-stage", IterationStrategy.REACT_STAGE),
        (IterationStrategy.REACT, IterationStrategy.REACT),
        (IterationStrategy.REACT_STAGE, IterationStrategy.REACT_STAGE),
    ])
    def test_valid_iteration_strategies(self, strategy_value, expected_strategy):
        """Test valid iteration strategy values."""
        config_data = {
            "alert_types": ["security"],
            "mcp_servers": ["security-tools"],
            "iteration_strategy": strategy_value
        }
        
        config = AgentConfigModel(**config_data)
        assert config.iteration_strategy == expected_strategy

    @pytest.mark.parametrize("invalid_strategy", [
        "invalid_strategy",
        "REACT",  # Wrong case
        "REACT_STAGE",  # Wrong case
        "React",  # Wrong case
    ])
    def test_invalid_iteration_strategies(self, invalid_strategy):
        """Test that invalid iteration strategies fail validation."""
        config_data = {
            "alert_types": ["security"],
            "mcp_servers": ["security-tools"],
            "iteration_strategy": invalid_strategy
        }
        
        with pytest.raises(ValidationError) as exc_info:
            AgentConfigModel(**config_data)
            
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("iteration_strategy",) for e in errors)

@pytest.mark.unit
class TestMCPServerConfigModel:
    """Test cases for MCPServerConfigModel validation."""

    def test_valid_mcp_server_config(self):
        """Test valid MCP server configuration."""
        config_data = {
            "server_id": "security-tools",
            "server_type": "security",
            "enabled": True,
            "connection_params": {"host": "localhost", "port": 8080},
            "instructions": "Security analysis tools"
        }
        
        config = MCPServerConfigModel(**config_data)
        
        assert config.server_id == "security-tools"
        assert config.server_type == "security"
        assert config.enabled is True
        assert config.connection_params == {"host": "localhost", "port": 8080}
        assert config.instructions == "Security analysis tools"

    def test_minimal_valid_mcp_server_config(self):
        """Test minimal valid MCP server configuration."""
        config_data = {
            "server_id": "security-tools",
            "server_type": "security",
            "connection_params": {}
        }
        
        config = MCPServerConfigModel(**config_data)
        
        assert config.server_id == "security-tools"
        assert config.server_type == "security"
        assert config.enabled is True  # Default value
        assert config.connection_params == {}  # Default value
        assert config.instructions == ""

    def test_disabled_mcp_server_config(self):
        """Test disabled MCP server configuration."""
        config_data = {
            "server_id": "disabled-server",
            "server_type": "monitoring",
            "enabled": False,
            "connection_params": {}
        }
        
        config = MCPServerConfigModel(**config_data)
        
        assert config.enabled is False

    def test_serialization_roundtrip(self, model_test_helpers):
        """Test that MCP server config can be serialized and deserialized correctly."""
        valid_data = {
            "server_id": "security-tools",
            "server_type": "security",
            "enabled": True,
            "connection_params": {"host": "localhost", "port": 8080},
            "instructions": "Security analysis tools"
        }
        
        model_test_helpers.test_serialization_roundtrip(MCPServerConfigModel, valid_data)

    def test_required_fields_validation(self, model_validation_tester):
        """Test that required fields are enforced."""
        valid_data = {
            "server_id": "security-tools",
            "server_type": "security",
            "connection_params": {}
        }
        
        required_fields = ["server_id", "server_type"]
        model_validation_tester.test_required_fields(MCPServerConfigModel, required_fields, valid_data)

    def test_invalid_field_types(self):
        """Test that invalid field types fail validation."""
        # connection_params as string instead of dict
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfigModel(
                server_id="security-tools",
                server_type="security",
                connection_params="localhost:8080"
            )
            
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("connection_params",) for e in errors)

@pytest.mark.unit
class TestCombinedConfigModel:
    """Test cases for CombinedConfigModel validation."""

    def test_valid_combined_config(self):
        """Test valid combined configuration."""
        config_data = {
            "agents": {
                "security-agent": {
                    "alert_types": ["security"],
                    "mcp_servers": ["security-tools"]
                },
                "performance-agent": {
                    "alert_types": ["performance"],
                    "mcp_servers": ["monitoring-server"]
                }
            },
            "mcp_servers": {
                "security-tools": {
                    "server_id": "security-tools",
                    "server_type": "security",
                    "connection_params": {}
                },
                "monitoring-server": {
                    "server_id": "monitoring-server",
                    "server_type": "monitoring",
                    "connection_params": {}
                }
            }
        }
        
        config = CombinedConfigModel(**config_data)
        
        assert len(config.agents) == 2
        assert "security-agent" in config.agents
        assert "performance-agent" in config.agents
        assert len(config.mcp_servers) == 2
        assert "security-tools" in config.mcp_servers
        assert "monitoring-server" in config.mcp_servers

    def test_empty_sections_valid(self):
        """Test that empty agents and mcp_servers sections are valid."""
        config_data = {
            "agents": {},
            "mcp_servers": {}
        }
        
        config = CombinedConfigModel(**config_data)
        
        assert config.agents == {}
        assert config.mcp_servers == {}

    def test_server_id_mismatch_fails(self):
        """Test that server_id mismatch with dictionary key fails validation."""
        config_data = {
            "agents": {},
            "mcp_servers": {
                "security-tools": {
                    "server_id": "wrong-id",  # Should match key "security-tools"
                    "server_type": "security",
                    "connection_params": {"command": "/usr/bin/security"}
                }
            }
        }
        
        with pytest.raises(ValidationError) as exc_info:
            CombinedConfigModel(**config_data)
            
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert "server_id" in str(errors[0]["msg"])
        assert "security-tools" in str(errors[0]["msg"])
        assert "wrong-id" in str(errors[0]["msg"])

    def test_multiple_server_id_mismatches_fails(self):
        """Test multiple server_id mismatches in validation."""
        config_data = {
            "agents": {},
            "mcp_servers": {
                "security-tools": {
                    "server_id": "wrong-id-1",      
                    "server_type": "security",
                    "connection_params": {"command": "/usr/bin/security"}
                },
                "monitoring-server": {
                    "server_id": "wrong-id-2",
                    "server_type": "monitoring",
                    "connection_params": {"command": "/usr/bin/monitoring"}
                }
            }
        }
        
        with pytest.raises(ValidationError) as exc_info:
            CombinedConfigModel(**config_data)
            
        errors = exc_info.value.errors()
        assert len(errors) == 1
        error_msg = str(errors[0]["msg"])
        assert "server_id" in error_msg
        # Should contain the first mismatch found (validator stops on first error)
        assert ("security-tools" in error_msg and "wrong-id-1" in error_msg) or ("monitoring-server" in error_msg and "wrong-id-2" in error_msg)

    def test_missing_sections_use_defaults(self):
        """Test that missing sections use default empty dictionaries."""
        # Missing agents section should default to empty dict
        config = CombinedConfigModel(mcp_servers={})
        assert config.agents == {}
        assert config.mcp_servers == {}

        # Missing mcp_servers section should default to empty dict
        config = CombinedConfigModel(agents={})
        assert config.agents == {}
        assert config.mcp_servers == {}
        
        # Both missing should default to empty dicts
        config = CombinedConfigModel()
        assert config.agents == {}
        assert config.mcp_servers == {}

    def test_invalid_nested_agent_config(self):
        """Test that invalid nested agent configuration fails validation."""
        config_data = {
            "agents": {
                "security-agent": {
                    "alert_types": [],  # Invalid: empty list
                    "mcp_servers": ["security-tools"]
                }
            },
            "mcp_servers": {
                "security-tools": {
                    "server_id": "security-tools",
                    "server_type": "security"
                }
            }
        }
        
        with pytest.raises(ValidationError) as exc_info:
            CombinedConfigModel(**config_data)
            
        errors = exc_info.value.errors()
        # Should have error for empty alert_types
        agent_error = next((e for e in errors if "agents" in e["loc"] and "alert_types" in e["loc"]), None)
        assert agent_error is not None

    def test_invalid_nested_mcp_server_config(self):
        """Test that invalid nested MCP server configuration fails validation."""
        config_data = {
            "agents": {
                "security-agent": {
                    "alert_types": ["security"],
                    "mcp_servers": ["security-tools"]
                }
            },
            "mcp_servers": {
                "security-tools": {
                    # Missing required server_type
                    "server_id": "security-tools"
                }
            }
        }
        
        with pytest.raises(ValidationError) as exc_info:
            CombinedConfigModel(**config_data)
            
        errors = exc_info.value.errors()
        # Should have error for missing server_type
        server_error = next((e for e in errors if "mcp_servers" in e["loc"] and "server_type" in e["loc"]), None)
        assert server_error is not None

    def test_valid_configurable_agent_references(self):
        """Test valid configurable agent references in chain stages."""
        
        config_data = {
            "agents": {
                "my-security-agent": {
                    "alert_types": ["security"],
                    "mcp_servers": ["security-tools"]
                },
                "performance-agent": {
                    "alert_types": ["performance"],
                    "mcp_servers": ["monitoring-server"]
                }
            },
            "mcp_servers": {
                "security-tools": {
                    "server_id": "security-tools",
                    "server_type": "security",
                    "connection_params": {}
                }
            },
            "agent_chains": {
                "security-chain": {
                    "chain_id": "security-chain",
                    "alert_types": ["security"],
                    "stages": [
                        {
                            "name": "analysis",
                            "agent": "ConfigurableAgent:my-security-agent"
                        },
                        {
                            "name": "response",
                            "agent": "KubernetesAgent"  # Non-configurable agent should be ignored
                        },
                        {
                            "name": "final",
                            "agent": "ConfigurableAgent:performance-agent"
                        }
                    ]
                }
            }
        }
        
        # Should not raise any validation errors
        config = CombinedConfigModel(**config_data)
        assert len(config.agent_chains) == 1
        assert "security-chain" in config.agent_chains

    def test_missing_configurable_agent_reference_fails(self):
        """Test that missing configurable agent references fail validation."""
        
        config_data = {
            "agents": {
                "existing-agent": {
                    "alert_types": ["security"],
                    "mcp_servers": ["security-tools"]
                }
            },
            "mcp_servers": {
                "security-tools": {
                    "server_id": "security-tools",
                    "server_type": "security",
                    "connection_params": {}
                }
            },
            "agent_chains": {
                "test-chain": {
                    "chain_id": "test-chain",
                    "alert_types": ["security"],
                    "stages": [
                        {
                            "name": "analysis",
                            "agent": "ConfigurableAgent:nonexistent-agent"
                        }
                    ]
                }
            }
        }
        
        with pytest.raises(ValidationError) as exc_info:
            CombinedConfigModel(**config_data)
            
        errors = exc_info.value.errors()
        assert len(errors) == 1
        error_msg = str(errors[0]["msg"])
        assert "Chain 'test-chain' stage 'analysis' references missing configurable agent 'nonexistent-agent'" in error_msg

    def test_non_configurable_agent_references_ignored(self):
        """Test that non-configurable agent references are ignored by validator."""
        
        config_data = {
            "agents": {},
            "mcp_servers": {},
            "agent_chains": {
                "builtin-chain": {
                    "chain_id": "builtin-chain",
                    "alert_types": ["kubernetes"],
                    "stages": [
                        {
                            "name": "k8s-analysis",
                            "agent": "KubernetesAgent"  # Non-configurable, should be ignored
                        },
                        {
                            "name": "custom-analysis", 
                            "agent": "SomeCustomAgent"  # Non-configurable, should be ignored
                        }
                    ]
                }
            }
        }
        
        # Should not raise any validation errors since these are not ConfigurableAgent references
        config = CombinedConfigModel(**config_data)
        assert len(config.agent_chains) == 1
        assert "builtin-chain" in config.agent_chains

    def test_multiple_chain_validation_errors(self):
        """Test validation errors across multiple chains and stages."""
        
        config_data = {
            "agents": {
                "valid-agent": {
                    "alert_types": ["security"],
                    "mcp_servers": ["security-tools"]
                }
            },
            "mcp_servers": {},
            "agent_chains": {
                "chain1": {
                    "chain_id": "chain1",
                    "alert_types": ["security"],
                    "stages": [
                        {
                            "name": "stage1",
                            "agent": "ConfigurableAgent:missing-agent-1"
                        }
                    ]
                },
                "chain2": {
                    "chain_id": "chain2",
                    "alert_types": ["performance"],
                    "stages": [
                        {
                            "name": "stage2",
                            "agent": "ConfigurableAgent:valid-agent"  # This one exists
                        },
                        {
                            "name": "stage3",
                            "agent": "ConfigurableAgent:missing-agent-2"  # This one doesn't
                        }
                    ]
                }
            }
        }
        
        with pytest.raises(ValidationError) as exc_info:
            CombinedConfigModel(**config_data)
            
        errors = exc_info.value.errors()
        assert len(errors) == 1  # Should fail fast on first missing agent
        error_msg = str(errors[0]["msg"])
        # Should reference the first missing agent found
        assert "missing configurable agent" in error_msg
        assert ("missing-agent-1" in error_msg or "missing-agent-2" in error_msg) 