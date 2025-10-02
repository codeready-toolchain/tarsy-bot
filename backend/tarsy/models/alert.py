"""
Alert data models for tarsy.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Alert(BaseModel):
    """
    API input model - what external clients send.
    
    This model validates incoming alert payloads from external systems
    (AlertManager, Prometheus, webhooks, monitoring tools, etc.).
    
    The 'data' field accepts any complex, nested JSON structure:
    - Deeply nested objects
    - Arrays and mixed types
    - Any field names (including those that might conflict with our metadata)
    - Completely arbitrary schema - we don't control what clients send
    
    Client data is preserved exactly as received and passed pristine to processing.
    """
    
    alert_type: str = Field(
        ..., 
        description="Alert type for agent selection"
    )
    runbook: Optional[str] = Field(
        None, 
        description="Processing runbook URL (optional, uses built-in default if not provided)"
    )
    severity: Optional[str] = Field(
        None, 
        description="Alert severity (defaults to 'warning')"
    )
    timestamp: Optional[int] = Field(
        None, 
        description="Alert timestamp in unix microseconds (auto-generated if not provided)"
    )
    data: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Client's alert data - can be any complex nested JSON structure"
    )
    
    @classmethod
    def get_required_fields(cls) -> List[str]:
        """Get list of required API field names."""
        return [
            field_name 
            for field_name, field_info in cls.model_fields.items() 
            if field_info.is_required()
        ]
    
    @classmethod
    def get_optional_fields(cls) -> List[str]:
        """Get list of optional API field names."""
        return [
            field_name 
            for field_name, field_info in cls.model_fields.items() 
            if not field_info.is_required()
        ]


class ProcessingAlert(BaseModel):
    """
    Internal processing model - what we use for alert processing.
    
    This model contains:
    1. Normalized metadata (our fields)
    2. Client's pristine alert data (untouched)
    
    Keeps client data completely separate from our processing metadata.
    No name collisions, no data pollution.
    """
    
    # === Processing Metadata (our fields) ===
    alert_type: str = Field(
        ..., 
        min_length=1,
        description="Alert type (always set)"
    )
    severity: str = Field(
        ..., 
        description="Normalized severity (always set, default: 'warning')"
    )
    timestamp: int = Field(
        ..., 
        description="Processing timestamp in unix microseconds (always set)"
    )
    environment: str = Field(
        default="production",
        description="Environment (from client data or default)"
    )
    runbook_url: Optional[str] = Field(
        None, 
        description="Runbook URL if provided"
    )
    
    # === Client's Pristine Data ===
    alert_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Client's original alert data (pristine, no metadata mixed in)"
    )
    
    @classmethod
    def from_api_alert(cls, alert: Alert) -> ProcessingAlert:
        """
        Transform API Alert to ProcessingAlert.
        
        Applies minimal manipulation:
        1. Extract/generate metadata (severity, timestamp, environment)
        2. Keep client's data pristine (no merging, no modifications)
        
        Args:
            alert: Validated API Alert from client
            
        Returns:
            ProcessingAlert ready for ChainContext
        """
        from tarsy.utils.timestamp import now_us
        from datetime import datetime
        
        # Extract environment from client data if present (but keep it there too)
        environment = alert.data.get('environment', 'production')
        
        # Generate timestamp if not provided
        if alert.timestamp is None:
            timestamp = now_us()
        elif isinstance(alert.timestamp, datetime):
            timestamp = int(alert.timestamp.timestamp() * 1000000)
        else:
            timestamp = alert.timestamp
        
        return cls(
            alert_type=alert.alert_type,
            severity=alert.severity or 'warning',
            timestamp=timestamp,
            environment=environment,
            runbook_url=alert.runbook,
            alert_data=alert.data  # ← PRISTINE!
        )


class AlertResponse(BaseModel):
    """Response model for alert submission."""
    
    alert_id: str
    status: str
    message: str