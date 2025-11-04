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


class MCPSelectionConfig(BaseModel):
    """
    Configuration for MCP server/tool selection.
    
    Allows users to override default agent MCP server configuration by specifying:
    - Which MCP servers to use
    - Optionally, which specific tools from each server to make available
    
    This configuration applies to all agents in the chain.
    """
    
    servers: List[MCPServerSelection] = Field(
        ..., 
        min_length=1,
        description="List of selected MCP servers with optional tool filtering"
    )

