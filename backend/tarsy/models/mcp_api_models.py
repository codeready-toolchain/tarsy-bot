"""
MCP API Models

Type-safe Pydantic models for MCP server/tool discovery API endpoints.
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class MCPToolInfo(BaseModel):
    """Information about a single MCP tool."""
    
    name: str = Field(..., description="Tool name")
    description: str = Field(default="", description="Tool description")
    input_schema: Dict[str, Any] = Field(
        default_factory=dict, 
        description="JSON Schema for tool inputs"
    )


class MCPServerInfo(BaseModel):
    """Information about an MCP server and its available tools."""
    
    server_id: str = Field(..., description="Unique server identifier")
    server_type: str = Field(..., description="Server type (e.g., 'kubernetes', 'argocd')")
    enabled: bool = Field(..., description="Whether server is enabled")
    tools: List[MCPToolInfo] = Field(
        default_factory=list, 
        description="Available tools from this server"
    )


class MCPServersResponse(BaseModel):
    """Response model for MCP servers listing endpoint."""
    
    servers: List[MCPServerInfo] = Field(
        ..., 
        description="List of available MCP servers with tools"
    )
    total_servers: int = Field(..., description="Total number of servers")
    total_tools: int = Field(..., description="Total number of tools across all servers")

