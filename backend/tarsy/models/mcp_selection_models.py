"""
MCP Server/Tool Selection Models

These models define the structure for user-selectable MCP server and tool configurations
that can override default agent MCP server assignments.
"""

from typing import List, Optional

from pydantic import BaseModel, Field


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
    When specified, this configuration completely replaces the provider's default
    native tools settings for the duration of the session.
    
    All fields are optional. If a tool is not specified (None), it will be disabled.
    This provides explicit control over which native tools are available.
    """
    
    google_search: Optional[bool] = Field(
        None,
        description="Enable/disable Google Search tool"
    )
    code_execution: Optional[bool] = Field(
        None,
        description="Enable/disable Python code execution tool"
    )
    url_context: Optional[bool] = Field(
        None,
        description="Enable/disable URL context/grounding tool"
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

