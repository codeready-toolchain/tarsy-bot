"""
API Models for Request/Response Serialization

Defines Pydantic models for API request/response structures.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


# Non-history related response models (Phase 5: History models moved to history_models.py)

class HealthCheckResponse(BaseModel):
    """Response for health check endpoints."""
    service: str = Field(description="Service name")
    status: str = Field(description="Service status ('healthy', 'unhealthy', 'disabled')")
    timestamp_us: int = Field(description="Health check timestamp (microseconds since epoch UTC)")
    details: Dict[str, Any] = Field(description="Additional health check details")

class ErrorResponse(BaseModel):
    """Standard error response model."""
    error: str = Field(description="Error type or category")
    message: str = Field(description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(description="Additional error details")
    timestamp_us: int = Field(description="When the error occurred (microseconds since epoch UTC)") 