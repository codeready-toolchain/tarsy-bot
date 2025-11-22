"""
MCP Server/Tool Selection Models

These models define the structure for user-selectable MCP server and tool configurations
that can override default agent MCP server assignments.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_serializer


class MCPServerSelection(BaseModel):
    """
    Selection of a single MCP server with optional tool filtering.
    
    When tools is None, all tools from the server are used.
    When tools is a list, only the specified tools are available.
    """
    
    name: str = Field(
        ..., 
        description="MCP server name/ID (must match configured server ID)",
        min_length=1
    )
    tools: Optional[List[str]] = Field(
        None, 
        description="Optional list of specific tool names. If None or empty, all tools from the server are used."
    )


class NativeToolsConfig(BaseModel):
    """
    Configuration for Google/Gemini native tools override.
    
    Allows per-session override of native tools configured in the LLM provider.
    
    **Tri-state Semantics (per field):**
    - `None` (field not specified): Use provider default configuration
    - `True`: Explicitly enable the tool (override provider default)
    - `False`: Explicitly disable the tool (override provider default)
    
    **Examples:**
    - Omitting `native_tools` entirely → All tools use provider defaults
    - Sending `native_tools: {}` → All tools use provider defaults (same as omitting)
    - Sending `native_tools: {google_search: true}` → Enable google_search, use provider defaults for code_execution and url_context
    - Sending `native_tools: {google_search: true, code_execution: false}` → Enable google_search, disable code_execution, use provider default for url_context
    
    **Provider Defaults (when field is `None`):**
    - google_search: enabled by default
    - code_execution: disabled by default
    - url_context: enabled by default
    """
    
    google_search: Optional[bool] = Field(
        None,
        description="Enable/disable Google Search tool. None = use provider default (enabled)"
    )
    code_execution: Optional[bool] = Field(
        None,
        description="Enable/disable Python code execution tool. None = use provider default (disabled)"
    )
    url_context: Optional[bool] = Field(
        None,
        description="Enable/disable URL context/grounding tool. None = use provider default (enabled)"
    )


class MCPSelectionConfig(BaseModel):
    """
    Configuration for MCP server/tool selection and native tools override.
    
    Allows users to override default agent configuration by specifying:
    - Which MCP servers to use
    - Optionally, which specific tools from each server to make available
    - Optionally, override Google/Gemini native tools settings
    
    This configuration applies to all agents in the chain.
    """
    
    servers: List[MCPServerSelection] = Field(
        ..., 
        min_length=1,
        description="List of selected MCP servers with optional tool filtering"
    )
    native_tools: Optional[NativeToolsConfig] = Field(
        None,
        description="Optional native tools override for Google/Gemini models. "
                    "When specified, completely replaces provider default settings."
    )
    
    @model_serializer(mode='wrap', when_used='always')
    def _serialize_model(self, serializer: Any, info: Any) -> Dict[str, Any]:
        """
        Custom serializer to omit native_tools when it's empty (all fields None).
        
        This ensures that NativeToolsConfig() with all None fields is treated
        the same as omitting native_tools entirely, both semantically meaning
        "use provider defaults".
        """
        data = serializer(self)
        
        # If native_tools exists in serialized data and is an empty dict,
        # remove it (meaning all fields were None)
        if isinstance(data, dict) and "native_tools" in data:
            native_tools_data = data["native_tools"]
            if isinstance(native_tools_data, dict) and not native_tools_data:
                del data["native_tools"]
        
        return data

