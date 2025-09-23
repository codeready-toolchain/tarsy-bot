"""MCP transport configuration models.

This module defines Pydantic models for MCP transport configurations, supporting both
stdio and HTTP transports with proper validation and type safety. Uses discriminated
unions to automatically handle transport type resolution.
"""

from enum import Enum
from typing import Dict, Optional, List, Literal
from pydantic import BaseModel, Field, HttpUrl, field_validator


class TransportType(str, Enum):
    """Supported MCP transport types."""
    
    STDIO = "stdio"
    HTTP = "http"


class BaseTransportConfig(BaseModel):
    """Base configuration for MCP transports."""
    
    type: str = Field(..., description="Transport type identifier")
    timeout: Optional[int] = Field(
        default=30, 
        description="Connection timeout in seconds",
        ge=1,
        le=300
    )


class StdioTransportConfig(BaseTransportConfig):
    """Configuration for stdio transport (existing functionality).
    
    This transport type uses subprocess communication via stdin/stdout to
    interact with MCP servers running as command-line processes.
    """
    
    type: Literal["stdio"] = Field(
        default="stdio", 
        description="Transport type - automatically set to 'stdio'"
    )
    command: str = Field(
        ..., 
        description="Command to execute for the MCP server",
        min_length=1
    )
    args: Optional[List[str]] = Field(
        default_factory=list, 
        description="Command line arguments for the MCP server"
    )
    env: Optional[Dict[str, str]] = Field(
        default_factory=dict, 
        description="Environment variables for the MCP server process"
    )

    @field_validator('command')
    def validate_command_not_empty(cls, v: str) -> str:
        """Validate that command is not empty or only whitespace."""
        if not v or not v.strip():
            raise ValueError("Command cannot be empty")
        return v.strip()


class HTTPTransportConfig(BaseTransportConfig):
    """Configuration for HTTP transport per MCP Streamable HTTP specification.
    
    This transport type uses HTTP/HTTPS endpoints to communicate with MCP servers
    using JSON-RPC 2.0 protocol over HTTP. Supports bearer token authentication
    and SSL verification options.
    """
    
    type: Literal["http"] = Field(
        default="http", 
        description="Transport type - automatically set to 'http'"
    )
    url: HttpUrl = Field(
        ..., 
        description="Single MCP endpoint URL (e.g., 'https://api.example.com/mcp')"
    )
    bearer_token: Optional[str] = Field(
        default=None,
        description="Bearer access token for machine-to-machine authentication",
        min_length=1
    )
    headers: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Additional HTTP headers (Authorization header managed by bearer_token)"
    )
    verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificates (strongly recommended for production)"
    )

    # Note: HttpUrl automatically validates that scheme is http or https

    @field_validator('bearer_token')
    def validate_bearer_token_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate bearer token format if provided."""
        if v is not None:
            # Remove any whitespace
            v = v.strip()
            if not v:
                raise ValueError("Bearer token cannot be empty if provided")
            # Basic validation - should not contain spaces or special characters that would break HTTP headers
            if any(char in v for char in ['\n', '\r', '\t']):
                raise ValueError("Bearer token cannot contain newlines, carriage returns, or tabs")
        return v

    @field_validator('headers')
    def validate_headers_no_auth(cls, v: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """Validate that Authorization header is not manually set (use bearer_token instead)."""
        if v:
            # Check for Authorization header (case-insensitive)
            auth_headers = [key.lower() for key in v.keys() if key.lower() == 'authorization']
            if auth_headers:
                raise ValueError(
                    "Do not set 'Authorization' header manually - use 'bearer_token' field instead"
                )
        return v
