"""System-level models for warnings, health, and status."""

from typing import Optional

from pydantic import BaseModel, Field


# Warning category constants
class WarningCategory:
    """Constants for system warning categories."""
    
    MCP_INITIALIZATION: str = "mcp_initialization"
    LLM_INITIALIZATION: str = "llm_initialization"
    RUNBOOK_SERVICE: str = "runbook_service"


class SystemWarning(BaseModel):
    """Represents a system-level warning."""

    warning_id: str = Field(..., description="Unique identifier for the warning")
    category: str = Field(
        ...,
        description="Warning category, one of WarningCategory values",
    )
    message: str = Field(..., description="User-facing warning message")
    details: Optional[str] = Field(
        None, description="Optional detailed error information"
    )
    timestamp: int = Field(..., description="Warning timestamp in microseconds")
    server_id: Optional[str] = Field(
        None, description="Server ID for MCP/service-specific warnings"
    )

    class Config:
        """Pydantic configuration."""

        json_schema_extra = {
            "example": {
                "warning_id": "550e8400-e29b-41d4-a716-446655440000",
                "category": "mcp_initialization",
                "message": "MCP Server 'kubernetes-server' failed to initialize",
                "details": "Connection timeout after 30 seconds",
                "timestamp": 1706616000000000,
            }
        }
