"""
Dashboard message broadcasting with filtering and throttling.

Key Feature: Session Message Buffering
- Solves timing race condition where background alert processing starts immediately
- but UI needs time to connect → subscribe to session channels  
- Without buffering: early LLM/MCP interactions are lost forever
- With buffering: messages are queued until first subscriber, then flushed chronologically
"""

from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Dict, Set

from tarsy.models.websocket_models import OutgoingMessage, ChannelType
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class DashboardBroadcaster:
    """
    Message broadcasting system for dashboard clients.
    
    Includes session message buffering to prevent lost messages during the timing gap
    between alert submission (starts background processing) and UI subscription to session channels.
    """
    
    def __init__(self, connection_manager):
        self.connection_manager = connection_manager
        
        # Throttling only (no message filtering)
        self.throttle_limits: Dict[str, Dict[str, Any]] = {}
        self.user_message_counts: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
        
        # Session message buffer: solves timing race condition where background processing
        # starts immediately after alert submission but UI needs time to connect and subscribe.
        # Without this buffer, early LLM/MCP interactions are lost because no one is subscribed yet.
        # Simple dict: session_channel -> [buffered_messages] - flushed when first subscriber joins
        self.session_message_buffer: Dict[str, list] = {}
    
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
        
        # CRITICAL: Handle session channel buffering if no subscribers
        # 
        # Problem: Alert processing starts immediately in background, but UI takes time to:
        # 1. Get alert_id from /alerts response 
        # 2. Connect to WebSocket
        # 3. Fetch session_id from /session-id/{alert_id}  
        # 4. Subscribe to session_{session_id} channel
        #
        # Without buffering, early LLM/MCP interactions are dropped → user sees incomplete timeline
        # Solution: Buffer session messages until first subscriber, then flush all at once
        if not subscribers and ChannelType.is_session_channel(channel):
            message_dict = message.model_dump() if hasattr(message, 'model_dump') else message
            if channel not in self.session_message_buffer:
                self.session_message_buffer[channel] = []
            self.session_message_buffer[channel].append(message_dict)
            logger.debug(f"Buffered message for {channel} (no subscribers yet)")
            return 0
        
        if not subscribers:
            logger.debug(f"No subscribers for channel: {channel}")
            return 0
        
        # FLUSH BUFFER: If there are subscribers and this is a session channel, 
        # send any buffered messages first (in chronological order)
        sent_count = 0
        if ChannelType.is_session_channel(channel) and channel in self.session_message_buffer:
            # pop() removes buffer and returns messages - prevents memory leaks for completed sessions
            buffered_messages = self.session_message_buffer.pop(channel)
            logger.debug(f"First subscriber detected! Flushing {len(buffered_messages)} buffered messages for {channel}")
            
            # Send buffered messages directly to avoid recursion through broadcast_message
            for buffered_msg in buffered_messages:
                for user_id in subscribers - exclude_users:
                    if not self._should_throttle_user(user_id, channel):
                        if await self.connection_manager.send_to_user(user_id, buffered_msg):
                            sent_count += 1
                            self._record_user_message(user_id, channel)
        
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
        current_sent = 0
        message_dict = message.model_dump() if hasattr(message, 'model_dump') else message
        
        for user_id in eligible_users:
            if await self.connection_manager.send_to_user(user_id, message_dict):
                current_sent += 1
                self._record_user_message(user_id, channel)
        
        total_sent = sent_count + current_sent
        if sent_count > 0:
            logger.debug(f"Sent message to {total_sent}/{len(target_users)} users on channel {channel} (buffered: {sent_count}, current: {current_sent})")
        else:
            logger.debug(f"Sent message to {total_sent}/{len(target_users)} users on channel {channel}")
        return total_sent
    
    # Advanced broadcast methods
    async def broadcast_dashboard_update(
        self, 
        data: Dict[str, Any], 
        exclude_users: Set[str] = None
    ) -> int:
        """Broadcast dashboard update."""
        from tarsy.models.websocket_models import DashboardUpdate
        
        message = DashboardUpdate(data=data)
        return await self.broadcast_message(ChannelType.DASHBOARD_UPDATES, message, exclude_users)
    
    async def broadcast_session_update(
        self, 
        session_id: str, 
        data: Dict[str, Any], 
        exclude_users: Set[str] = None
    ) -> int:
        """Broadcast session update."""
        from tarsy.models.websocket_models import SessionUpdate
        
        message = SessionUpdate(session_id=session_id, data=data)
        return await self.broadcast_message(ChannelType.session_channel(session_id), message, exclude_users)