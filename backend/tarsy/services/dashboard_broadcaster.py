"""
Dashboard message broadcasting with filtering and throttling.
Simplified version without batching for immediate updates.
"""

from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Dict, Set

from tarsy.models.websocket_models import OutgoingMessage
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class DashboardBroadcaster:
    """Simplified message broadcasting system for dashboard clients."""
    
    def __init__(self, connection_manager):
        self.connection_manager = connection_manager
        
        # Throttling only (no message filtering)
        self.throttle_limits: Dict[str, Dict[str, Any]] = {}
        self.user_message_counts: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
    
    def _should_throttle_user(self, user_id: str, channel: str) -> bool:
        """Check if user should be throttled for this channel."""
        if channel not in self.throttle_limits:
            return False
        
        limits = self.throttle_limits[channel]
        user_messages = self.user_message_counts[user_id][channel]
        
        # Clean old messages outside time window
        cutoff_time = datetime.now() - timedelta(seconds=limits["time_window"])
        while user_messages and user_messages[0] < cutoff_time:
            user_messages.popleft()
        
        # Check if user exceeds limit
        return len(user_messages) >= limits["max_messages"]
    
    def _record_user_message(self, user_id: str, channel: str):
        """Record that a message was sent to a user."""
        self.user_message_counts[user_id][channel].append(datetime.now())
    
    async def broadcast_message(
        self, 
        channel: str, 
        message: OutgoingMessage, 
        exclude_users: Set[str] = None
    ) -> int:
        """Core broadcast method with filtering and throttling."""
        exclude_users = exclude_users or set()
        
        # Get channel subscribers
        subscribers = self.connection_manager.get_channel_subscribers(channel)
        if not subscribers:
            logger.debug(f"No subscribers for channel: {channel}")
            return 0
        
        # Apply user exclusions
        target_users = subscribers - exclude_users
        if not target_users:
            logger.debug(f"No target users for channel {channel} after exclusions")
            return 0
        
        # Filter users based on throttling only
        eligible_users = set()
        for user_id in target_users:
            # Check throttling
            if self._should_throttle_user(user_id, channel):
                logger.debug(f"Throttled user {user_id} for channel {channel}")
                continue
            
            eligible_users.add(user_id)
        
        if not eligible_users:
            logger.debug(f"No eligible users for channel {channel} after throttling")
            return 0
        
        # Send immediately to all eligible users
        sent_count = 0
        message_dict = message.model_dump() if hasattr(message, 'model_dump') else message
        
        for user_id in eligible_users:
            if await self.connection_manager.send_to_user(user_id, message_dict):
                sent_count += 1
                self._record_user_message(user_id, channel)
        
        logger.debug(f"Sent message to {sent_count}/{len(eligible_users)} users on channel {channel}")
        return sent_count
    
    # Advanced broadcast methods
    async def broadcast_dashboard_update(self, data: Dict[str, Any], exclude_users: Set[str] = None) -> int:
        """Broadcast dashboard update."""
        from tarsy.models.websocket_models import DashboardUpdate
        
        message = DashboardUpdate(data=data)
        return await self.broadcast_message("dashboard_updates", message, exclude_users)
    
    async def broadcast_session_update(self, session_id: str, data: Dict[str, Any], exclude_users: Set[str] = None) -> int:
        """Broadcast session update."""
        from tarsy.models.websocket_models import SessionUpdate
        
        message = SessionUpdate(session_id=session_id, data=data)
        return await self.broadcast_message(f"session:{session_id}", message, exclude_users)