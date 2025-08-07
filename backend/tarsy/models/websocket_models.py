"""
WebSocket message models for dashboard communications.

Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

from typing import Any, Dict, Literal, Optional, Union
from pydantic import BaseModel, Field

from tarsy.models.history import now_us


class WebSocketMessage(BaseModel):
    """Base WebSocket message model."""
    type: str
    timestamp_us: int = Field(default_factory=now_us, description="Message timestamp (microseconds since epoch UTC)")


class SubscriptionMessage(WebSocketMessage):
    """Message for subscribing/unsubscribing to channels."""
    type: Literal["subscribe", "unsubscribe"]
    channel: str = Field(description="Channel name to subscribe/unsubscribe")


class SubscriptionResponse(WebSocketMessage):
    """Response to subscription requests."""
    type: Literal["subscription_response"] = "subscription_response"
    action: Literal["subscribe", "unsubscribe"]
    channel: str
    success: bool
    message: Optional[str] = None


class ConnectionEstablished(WebSocketMessage):
    """Confirmation message when connection is established."""
    type: Literal["connection_established"] = "connection_established"
    user_id: str


class ErrorMessage(WebSocketMessage):
    """Error message for invalid requests."""
    type: Literal["error"] = "error"
    message: str
    code: Optional[str] = None


class DashboardUpdate(WebSocketMessage):
    """Dashboard update message."""
    type: Literal["dashboard_update"] = "dashboard_update"
    data: Dict[str, Any]
    channel: str = "dashboard_updates"


class SessionUpdate(WebSocketMessage):
    """Session-specific update message."""
    type: Literal["session_update"] = "session_update"
    session_id: str
    data: Dict[str, Any]
    channel: Optional[str] = None  # Will be set to session_{session_id}


class SystemHealthUpdate(WebSocketMessage):
    """System health status update."""
    type: Literal["system_health"] = "system_health"
    status: Literal["healthy", "degraded", "unhealthy"]
    services: Dict[str, Any]
    channel: str = "system_health"


class AlertStatusUpdate(WebSocketMessage):
    """Alert processing status update."""
    type: Literal["alert_status"] = "alert_status"
    alert_id: str
    status: str
    progress: int
    current_step: str
    current_agent: Optional[str] = None
    assigned_mcp_servers: Optional[list] = None
    result: Optional[str] = None
    error: Optional[str] = None


# Union type for all possible incoming messages from clients
IncomingMessage = Union[SubscriptionMessage]

# Union type for all possible outgoing messages to clients  
OutgoingMessage = Union[
    SubscriptionResponse,
    ConnectionEstablished, 
    ErrorMessage,
    DashboardUpdate,
    SessionUpdate,
    SystemHealthUpdate,
    AlertStatusUpdate
]


class ChannelType:
    """Channel type constants."""
    DASHBOARD_UPDATES = "dashboard_updates"
    SYSTEM_HEALTH = "system_health"
    
    @staticmethod
    def session_channel(session_id: str) -> str:
        """Generate session-specific channel name."""
        return f"session_{session_id}"
    
    @staticmethod
    def is_session_channel(channel: str) -> bool:
        """Check if channel is a session-specific channel."""
        return channel.startswith("session_")
    
    @staticmethod
    def extract_session_id(channel: str) -> Optional[str]:
        """Extract session ID from session channel name."""
        if not ChannelType.is_session_channel(channel):
            return None
        return channel[8:]  # Remove "session_" prefix 