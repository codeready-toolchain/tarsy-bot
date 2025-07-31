"""Unit tests for agent configuration Pydantic models."""

import pytest
from pydantic import ValidationError

from tarsy.models.agent_config import (
    AgentConfigModel,
    CombinedConfigModel,
    MCPServerConfigModel,
)


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

    def test_empty_alert_types_fails(self):
        """Test that empty alert_types list fails validation."""
        config_data = {
            "alert_types": [],
            "mcp_servers": ["security-tools"]
        }
        
        with pytest.raises(ValidationError) as exc_info:
            AgentConfigModel(**config_data)
            
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "too_short"

    def test_empty_mcp_servers_fails(self):
        """Test that empty mcp_servers list fails validation."""
        config_data = {
            "alert_types": ["security"],
            "mcp_servers": []
        }
        
        with pytest.raises(ValidationError) as exc_info:
            AgentConfigModel(**config_data)
            
        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["type"] == "too_short"

    def test_missing_required_fields_fails(self):
        """Test that missing required fields fail validation."""
        # Missing alert_types
        with pytest.raises(ValidationError) as exc_info:
            AgentConfigModel(mcp_servers=["security-tools"])
            
        errors = exc_info.value.errors()
        alert_types_error = next((e for e in errors if e["loc"] == ("alert_types",)), None)
        assert alert_types_error is not None
        assert alert_types_error["type"] == "missing"

        # Missing mcp_servers
        with pytest.raises(ValidationError) as exc_info:
            AgentConfigModel(alert_types=["security"])
            
        errors = exc_info.value.errors()
        mcp_servers_error = next((e for e in errors if e["loc"] == ("mcp_servers",)), None)
        assert mcp_servers_error is not None
        assert mcp_servers_error["type"] == "missing"

    def test_invalid_field_types(self):
        """Test that invalid field types fail validation."""
        # alert_types as string instead of list
        with pytest.raises(ValidationError) as exc_info:
            AgentConfigModel(
                alert_types="security",
                mcp_servers=["security-tools"]
            )
            
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("alert_types",) for e in errors)

        # mcp_servers as string instead of list
        with pytest.raises(ValidationError) as exc_info:
            AgentConfigModel(
                alert_types=["security"],
                mcp_servers="security-tools"
            )
            
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("mcp_servers",) for e in errors)

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

    def test_missing_required_fields_fails(self):
        """Test that missing required fields fail validation."""
        # Missing server_id
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfigModel(server_type="security")
            
        errors = exc_info.value.errors()
        server_id_error = next((e for e in errors if e["loc"] == ("server_id",)), None)
        assert server_id_error is not None
        assert server_id_error["type"] == "missing"

        # Missing server_type
        with pytest.raises(ValidationError) as exc_info:
            MCPServerConfigModel(server_id="security-tools")
            
        errors = exc_info.value.errors()
        server_type_error = next((e for e in errors if e["loc"] == ("server_type",)), None)
        assert server_type_error is not None
        assert server_type_error["type"] == "missing"

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