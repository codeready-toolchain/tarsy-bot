"""
Unit tests for MCP selection models.

Tests validation and structure of MCP server/tool selection configuration.
"""

import pytest
from pydantic import ValidationError

from tarsy.models.mcp_selection_models import MCPServerSelection, MCPSelectionConfig


class TestMCPServerSelection:
    """Tests for MCPServerSelection model."""
    
    def test_server_selection_without_tools(self):
        """Test creating server selection without tool filtering."""
        selection = MCPServerSelection(name="kubernetes-server")
        
        assert selection.name == "kubernetes-server"
        assert selection.tools is None
    
    def test_server_selection_with_tools(self):
        """Test creating server selection with specific tools."""
        selection = MCPServerSelection(
            name="kubernetes-server",
            tools=["core_v1_list_pod", "core_v1_read_namespaced_pod"]
        )
        
        assert selection.name == "kubernetes-server"
        assert selection.tools == ["core_v1_list_pod", "core_v1_read_namespaced_pod"]
    
    def test_server_selection_with_empty_tools_list(self):
        """Test creating server selection with empty tools list (treated as None)."""
        selection = MCPServerSelection(
            name="kubernetes-server",
            tools=[]
        )
        
        assert selection.name == "kubernetes-server"
        assert selection.tools == []  # Empty list is valid
    
    def test_server_selection_requires_name(self):
        """Test that server name is required."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerSelection()
        
        errors = exc_info.value.errors()
        assert any(e['loc'] == ('name',) for e in errors)
    
    def test_server_selection_rejects_empty_name(self):
        """Test that empty server name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MCPServerSelection(name="")
        
        errors = exc_info.value.errors()
        assert any(e['loc'] == ('name',) and 'at least 1 character' in str(e['msg']).lower() for e in errors)


class TestMCPSelectionConfig:
    """Tests for MCPSelectionConfig model."""
    
    def test_selection_config_with_single_server(self):
        """Test creating selection config with single server."""
        config = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="kubernetes-server")
            ]
        )
        
        assert len(config.servers) == 1
        assert config.servers[0].name == "kubernetes-server"
        assert config.servers[0].tools is None
    
    def test_selection_config_with_multiple_servers(self):
        """Test creating selection config with multiple servers."""
        config = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="kubernetes-server"),
                MCPServerSelection(name="argocd-server")
            ]
        )
        
        assert len(config.servers) == 2
        assert config.servers[0].name == "kubernetes-server"
        assert config.servers[1].name == "argocd-server"
    
    def test_selection_config_with_mixed_tool_filtering(self):
        """Test selection config with mix of all-tools and specific-tools servers."""
        config = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="kubernetes-server"),  # All tools
                MCPServerSelection(
                    name="argocd-server",
                    tools=["get_application", "get_application_status"]
                )  # Specific tools
            ]
        )
        
        assert len(config.servers) == 2
        assert config.servers[0].tools is None  # All tools
        assert config.servers[1].tools == ["get_application", "get_application_status"]
    
    def test_selection_config_requires_servers(self):
        """Test that servers list is required."""
        with pytest.raises(ValidationError) as exc_info:
            MCPSelectionConfig()
        
        errors = exc_info.value.errors()
        assert any(e['loc'] == ('servers',) for e in errors)
    
    def test_selection_config_rejects_empty_servers_list(self):
        """Test that empty servers list is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            MCPSelectionConfig(servers=[])
        
        errors = exc_info.value.errors()
        assert any(e['loc'] == ('servers',) and 'at least 1' in str(e['msg']).lower() for e in errors)
    
    def test_selection_config_from_dict(self):
        """Test creating selection config from dictionary (API input)."""
        data = {
            "servers": [
                {"name": "kubernetes-server"},
                {"name": "argocd-server", "tools": ["get_application"]}
            ]
        }
        
        config = MCPSelectionConfig(**data)
        
        assert len(config.servers) == 2
        assert config.servers[0].name == "kubernetes-server"
        assert config.servers[0].tools is None
        assert config.servers[1].name == "argocd-server"
        assert config.servers[1].tools == ["get_application"]
    
    def test_selection_config_serialization(self):
        """Test that selection config can be serialized back to dict."""
        config = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="kubernetes-server"),
                MCPServerSelection(name="argocd-server", tools=["get_application"])
            ]
        )
        
        data = config.model_dump()
        
        assert data == {
            "servers": [
                {"name": "kubernetes-server", "tools": None},
                {"name": "argocd-server", "tools": ["get_application"]}
            ]
        }

