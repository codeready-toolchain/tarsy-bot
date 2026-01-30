"""
Alert data models for tarsy.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from tarsy.models.mcp_selection_models import MCPSelectionConfig


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
    
    alert_type: Optional[str] = Field(
        None, 
        description="Alert type for agent selection (uses default if not specified)"
    )
    runbook: Optional[str] = Field(
        None, 
        description="Processing runbook URL (optional, uses built-in default if not provided)"
    )
    timestamp: Optional[int] = Field(
        None, 
        description="Alert timestamp in unix microseconds (auto-generated if not provided)"
    )
    slack_message_fingerprint: Optional[str] = Field(
        None,
        description="Optional Slack message fingerprint for Slack message threading"
    )
    data: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Client's alert data - can be any complex nested JSON structure"
    )
    mcp: Optional[MCPSelectionConfig] = Field(
        None,
        description="Optional MCP server/tool selection to override default agent configuration"
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
        default="warning",
        description="DEPRECATED: Legacy field, will be removed in future version. Default: 'warning'"
    )
    timestamp: int = Field(
        ..., 
        description="Processing timestamp in unix microseconds (always set)"
    )
    environment: str = Field(
        default="production",
        description="DEPRECATED: Legacy field, will be removed in future version. Default: 'production'"
    )
    runbook_url: Optional[str] = Field(
        None, 
        description="Runbook URL if provided"
    )
    slack_message_fingerprint: Optional[str] = Field(
        None,
        description="Slack message fingerprint for Slack message threading"
    )
    # === Client's Pristine Data ===
    alert_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Client's original alert data (pristine, no metadata mixed in)"
    )
    
    # === MCP Configuration Override ===
    mcp: Optional[MCPSelectionConfig] = Field(
        None,
        description="Optional MCP server/tool selection to override default agent configuration"
    )
    
    @classmethod
    def from_api_alert(cls, alert: Alert, default_alert_type: str) -> ProcessingAlert:
        """
        Transform API Alert to ProcessingAlert.
        
        Applies minimal manipulation:
        1. Extract/generate metadata (severity, timestamp, environment)
        2. Keep client's data pristine (no merging, no modifications)
        3. Use default_alert_type if alert.alert_type is not provided
        
        Args:
            alert: Validated API Alert from client
            default_alert_type: Default alert type to use if not specified in alert
            
        Returns:
            ProcessingAlert ready for ChainContext
        """
        from datetime import datetime

        from tarsy.utils.timestamp import now_us
        
        # Extract severity and environment from client data if present (but keep them there too)
        severity = alert.data.get('severity', 'warning')
        environment = alert.data.get('environment', 'production')

        # Generate timestamp if not provided
        if alert.timestamp is None:
            timestamp = now_us()
        elif isinstance(alert.timestamp, datetime):
            timestamp = int(alert.timestamp.timestamp() * 1000000)
        else:
            timestamp = alert.timestamp
        
        # Use provided alert_type or fall back to default
        alert_type = alert.alert_type if alert.alert_type else default_alert_type
        
        return cls(
            alert_type=alert_type,
            severity=severity,
            timestamp=timestamp,
            environment=environment,
            runbook_url=alert.runbook,
            slack_message_fingerprint=alert.slack_message_fingerprint,
            alert_data=alert.data,  # ← PRISTINE!
            mcp=alert.mcp  # Pass through MCP selection config
        )


class AlertResponse(BaseModel):
    """Response model for alert submission."""
    
    session_id: str
    status: str
    message: str


class AlertTypesResponse(BaseModel):
    """Response model for alert types endpoint."""
    
    alert_types: List[str] = Field(
        ...,
        description="List of all available alert types"
    )
    default_alert_type: str = Field(
        ...,
        description="Default alert type to use by the clients"
    )