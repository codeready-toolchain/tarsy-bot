"""MCP transport configuration models.

This module defines Pydantic models for MCP transport configurations, supporting both
stdio and HTTP transports with proper validation and type safety. Uses discriminated
unions to automatically handle transport type resolution.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator

# Transport type constants
TRANSPORT_STDIO = "stdio"
TRANSPORT_HTTP = "http"  
TRANSPORT_SSE = "sse"


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


class HTTPBasedTransportConfig(BaseTransportConfig):
    """Base configuration for HTTP-based transports (HTTP and SSE).
    
    Contains common fields and validation for transports that use HTTP/HTTPS
    endpoints with bearer token authentication and SSL verification.
    """
    
    url: HttpUrl = Field(
        ..., 
        description="MCP endpoint URL (e.g., 'https://api.example.com/mcp')"
    )
    bearer_token: Optional[str] = Field(
        default=None,
        description="Bearer access token for authentication",
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
    timeout: float = Field(
        default=30.0,
        description="HTTP timeout for requests (seconds)",
        ge=1.0
    )

    @field_validator('bearer_token')
    def validate_bearer_token_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate bearer token format if provided."""
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Bearer token cannot be empty if provided")
            if any(char in v for char in ['\n', '\r', '\t']):
                raise ValueError("Bearer token cannot contain newlines, carriage returns, or tabs")
        return v

    @field_validator('headers')
    def validate_headers_no_auth(cls, v: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """Ensure Authorization header is not manually set (use bearer_token instead)."""
        if v and any(key.lower() == 'authorization' for key in v.keys()):
            raise ValueError("Use 'bearer_token' field instead of manually setting Authorization header")
        return v


class HTTPTransportConfig(HTTPBasedTransportConfig):
    """Configuration for HTTP transport per MCP Streamable HTTP specification.
    
    This transport type uses HTTP/HTTPS endpoints to communicate with MCP servers
    using JSON-RPC 2.0 protocol over HTTP with auto-detection of JSON-RPC vs SSE modes.
    """
    
    type: Literal["http"] = Field(
        default="http", 
        description="Transport type - automatically set to 'http'"
    )


class SSETransportConfig(HTTPBasedTransportConfig):
    """Configuration for SSE transport using dedicated MCP SDK SSE client.
    
    This transport type uses Server-Sent Events (SSE) for incoming messages
    and HTTP POST for outgoing messages. Optimized for real-time streaming
    applications with endpoint discovery protocol.
    """
    
    type: Literal["sse"] = Field(
        default="sse",
        description="Transport type - automatically set to 'sse'"
    )
    sse_read_timeout: float = Field(
        default=300.0,  # 5 minutes - SSE connections need longer timeouts
        description="SSE read timeout for event stream (seconds)",
        ge=10.0
    )


# Union type for transport configurations
TransportConfig = StdioTransportConfig | HTTPTransportConfig | SSETransportConfig
