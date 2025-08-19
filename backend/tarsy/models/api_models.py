"""
API Models for Request/Response Serialization

Defines Pydantic models for API request/response structures.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from tarsy.models.constants import ChainStatus

# Non-history related response models

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

class ChainExecutionResult(BaseModel):
    """
    Result from chain execution.
    
    This model represents the result of executing a chain of agent stages,
    containing both success and failure information.
    """
    
    # Core execution metadata - always present
    status: ChainStatus = Field(description="Overall execution status")
    timestamp_us: int = Field(description="Execution completion timestamp (microseconds since epoch UTC)")
    
    # Success case fields - present when status is completed or partial
    final_analysis: Optional[str] = Field(None, description="Final analysis result from the chain")
    
    # Error case fields - present when status is failed
    error: Optional[str] = Field(None, description="Error message when execution fails")