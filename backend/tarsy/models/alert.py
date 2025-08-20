"""
Alert data models for tarsy.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class Alert(BaseModel):
    """Flexible alert model with minimal required fields and arbitrary data payload."""
    
    alert_type: str = Field(..., description="Alert type for agent selection")
    runbook: str = Field(..., description="Processing runbook URL or reference")
    data: Dict[str, Any] = Field(default_factory=dict, description="Flexible alert payload")
    
    # Optional fields with defaults (will be applied in API layer if not provided)
    severity: Optional[str] = Field(None, description="Alert severity (defaults to 'warning')")
    timestamp: Optional[int] = Field(None, description="Alert timestamp in unix microseconds (defaults to current time)")


class AlertResponse(BaseModel):
    """Response model for alert submission."""
    
    alert_id: str
    status: str
    message: str