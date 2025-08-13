"""
WebSocket message models for dashboard communications.

Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

from typing import Any, Dict, Literal, Optional, Union
from pydantic import BaseModel, Field

from tarsy.models.history import now_us
from tarsy.models.constants import StageStatus, ChainStatus, SystemHealthStatus


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


class ChainProgressUpdate(WebSocketMessage):
    """Chain execution progress update message."""
    type: Literal["chain_progress"] = "chain_progress"
    session_id: str
    chain_id: str
    current_stage: Optional[str] = None
    current_stage_index: Optional[int] = None
    total_stages: Optional[int] = None
    completed_stages: Optional[int] = None
    failed_stages: Optional[int] = None
    overall_status: ChainStatus = ChainStatus.PROCESSING
    stage_details: Optional[Dict[str, Any]] = None  # Current stage execution details
    channel: Optional[str] = None  # Will be set to session_{session_id}


class StageProgressUpdate(WebSocketMessage):
    """Individual stage execution progress update."""
    type: Literal["stage_progress"] = "stage_progress"
    session_id: str
    chain_id: str
    stage_execution_id: str
    stage_id: str  # Logical stage identifier (e.g., 'initial-analysis')
    stage_name: str
    stage_index: int
    agent: str
    status: StageStatus = StageStatus.PENDING
    started_at_us: Optional[int] = None
    completed_at_us: Optional[int] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    iteration_strategy: Optional[str] = None
    channel: Optional[str] = None  # Will be set to session_{session_id}


class SystemHealthUpdate(WebSocketMessage):
    """System health status update."""
    type: Literal["system_health"] = "system_health"
    status: SystemHealthStatus
    services: Dict[str, Any]
    channel: str = "system_health"


# Union type for all possible incoming messages from clients
IncomingMessage = Union[SubscriptionMessage]

# Union type for all possible outgoing messages to clients  
OutgoingMessage = Union[
    SubscriptionResponse,
    ConnectionEstablished, 
    ErrorMessage,
    DashboardUpdate,
    SessionUpdate,
    ChainProgressUpdate,
    StageProgressUpdate,
    SystemHealthUpdate
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