"""
Unit tests for MCP selection models including native tools configuration.
"""


from tarsy.models.mcp_selection_models import (
    MCPSelectionConfig,
    MCPServerSelection,
    NativeToolsConfig,
)


class TestNativeToolsConfig:
    """Test cases for NativeToolsConfig model."""
    
    def test_empty_config(self):
        """Test that empty config is valid."""
        config = NativeToolsConfig()
        assert config.google_search is None
        assert config.code_execution is None
        assert config.url_context is None
    
    def test_partial_config(self):
        """Test that partial configuration is valid."""
        config = NativeToolsConfig(google_search=True)
        assert config.google_search is True
        assert config.code_execution is None
        assert config.url_context is None
    
    def test_full_config(self):
        """Test that full configuration is valid."""
        config = NativeToolsConfig(
            google_search=True,
            code_execution=False,
            url_context=True
        )
        assert config.google_search is True
        assert config.code_execution is False
        assert config.url_context is True
    
    def test_all_false_config(self):
        """Test that all false configuration is valid."""
        config = NativeToolsConfig(
            google_search=False,
            code_execution=False,
            url_context=False
        )
        assert config.google_search is False
        assert config.code_execution is False
        assert config.url_context is False
    
    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "google_search": True,
            "code_execution": False,
            "url_context": True
        }
        config = NativeToolsConfig(**data)
        assert config.google_search is True
        assert config.code_execution is False
        assert config.url_context is True
    
    def test_model_dump(self):
        """Test serialization to dictionary."""
        config = NativeToolsConfig(
            google_search=True,
            code_execution=False
        )
        data = config.model_dump()
        assert data["google_search"] is True
        assert data["code_execution"] is False
        assert data["url_context"] is None


class TestMCPSelectionConfigWithNativeTools:
    """Test cases for MCPSelectionConfig with native tools."""
    
    def test_config_without_native_tools(self):
        """Test MCP selection without native tools."""
        config = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="kubernetes-server", tools=None)
            ]
        )
        assert len(config.servers) == 1
        assert config.native_tools is None
    
    def test_config_with_native_tools(self):
        """Test MCP selection with native tools."""
        config = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="kubernetes-server", tools=None)
            ],
            native_tools=NativeToolsConfig(
                google_search=True,
                code_execution=False
            )
        )
        assert len(config.servers) == 1
        assert config.native_tools is not None
        assert config.native_tools.google_search is True
        assert config.native_tools.code_execution is False
    
    def test_config_with_inline_native_tools(self):
        """Test MCP selection with inline native tools dict."""
        config = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="kubernetes-server")
            ],
            native_tools={
                "google_search": True,
                "url_context": True
            }
        )
        assert config.native_tools.google_search is True
        assert config.native_tools.url_context is True
        assert config.native_tools.code_execution is None
    
    def test_from_dict_with_native_tools(self):
        """Test creation from dictionary with native tools."""
        data = {
            "servers": [
                {"name": "kubernetes-server", "tools": None}
            ],
            "native_tools": {
                "google_search": True,
                "code_execution": False,
                "url_context": True
            }
        }
        config = MCPSelectionConfig(**data)
        assert len(config.servers) == 1
        assert config.native_tools.google_search is True
        assert config.native_tools.code_execution is False
        assert config.native_tools.url_context is True
    
    def test_model_dump_with_native_tools(self):
        """Test serialization with native tools."""
        config = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="kubernetes-server", tools=None)
            ],
            native_tools=NativeToolsConfig(
                google_search=True,
                code_execution=False
            )
        )
        data = config.model_dump()
        assert "servers" in data
        assert "native_tools" in data
        assert data["native_tools"]["google_search"] is True
        assert data["native_tools"]["code_execution"] is False
    
    def test_empty_native_tools_serialization(self):
        """Test that empty native tools config serializes correctly."""
        config = MCPSelectionConfig(
            servers=[
                MCPServerSelection(name="kubernetes-server")
            ],
            native_tools=NativeToolsConfig()
        )
        data = config.model_dump(exclude_none=True)
        # Empty native tools should not be included when exclude_none=True
        # since all fields are None
        assert "servers" in data
        assert "native_tools" not in data
