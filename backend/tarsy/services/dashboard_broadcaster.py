"""
Dashboard message broadcasting with filtering and throttling.

Key Feature: Session Message Buffering
- Solves timing race condition where background alert processing starts immediately
- but UI needs time to connect → subscribe to session channels  
- Without buffering: early LLM/MCP interactions are lost forever
- With buffering: messages are queued until first subscriber, then flushed chronologically
"""

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from tarsy.models.websocket_models import OutgoingMessage, ChannelType
from tarsy.models.constants import StageStatus, ChainStatus
from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)

# Configuration constants for bounded session message buffer
MAX_MESSAGES_PER_SESSION = 100  # Maximum messages to buffer per session
MESSAGE_TTL_SECONDS = 300       # 5 minutes TTL for buffered messages
CLEANUP_INTERVAL_SECONDS = 60   # Run cleanup every minute


@dataclass
class TimestampedMessage:
    """Message with timestamp for TTL management."""
    message: Dict[str, Any]
    timestamp: datetime


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
        
        # Bounded session message buffer with TTL: solves timing race condition where background processing
        # starts immediately after alert submission but UI needs time to connect and subscribe.
        # Without this buffer, early LLM/MCP interactions are lost because no one is subscribed yet.
        # Bounded buffer: session_channel -> deque[TimestampedMessage] with max size and TTL
        self.session_message_buffer: Dict[str, deque[TimestampedMessage]] = {}
        self._buffer_lock = asyncio.Lock()
        self._cleanup_task: asyncio.Task = None
    
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
    
    def start_cleanup_task(self):
        """Start the periodic cleanup task for session message buffers."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
            logger.debug("Started session buffer cleanup task")
    
    def stop_cleanup_task(self):
        """Stop the periodic cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            logger.debug("Stopped session buffer cleanup task")
    
    async def _periodic_cleanup(self):
        """Periodically clean up expired messages and empty sessions."""
        while True:
            try:
                await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
                await self._cleanup_expired_messages()
            except asyncio.CancelledError:
                logger.debug("Session buffer cleanup task cancelled")
                break
            except Exception as e:
                logger.error(f"Error in session buffer cleanup: {e}")
    
    async def _cleanup_expired_messages(self):
        """Remove expired messages and empty sessions from buffer."""
        async with self._buffer_lock:
            now = datetime.now()
            expired_sessions = []
            
            for session_channel, message_buffer in self.session_message_buffer.items():
                # Remove expired messages
                while message_buffer and (now - message_buffer[0].timestamp).total_seconds() > MESSAGE_TTL_SECONDS:
                    expired_msg = message_buffer.popleft()
                    logger.debug(f"Removed expired message from {session_channel} (age: {(now - expired_msg.timestamp).total_seconds():.1f}s)")
                
                # Mark empty sessions for removal
                if not message_buffer:
                    expired_sessions.append(session_channel)
            
            # Remove empty sessions
            for session_channel in expired_sessions:
                del self.session_message_buffer[session_channel]
                logger.debug(f"Removed empty session buffer for {session_channel}")
            
            if expired_sessions:
                logger.debug(f"Cleaned up {len(expired_sessions)} empty session buffers")
    
    async def _add_message_to_buffer(self, channel: str, message_dict: Dict[str, Any]):
        """Add a message to the session buffer with TTL and size limits."""
        async with self._buffer_lock:
            if channel not in self.session_message_buffer:
                self.session_message_buffer[channel] = deque()
            
            buffer = self.session_message_buffer[channel]
            now = datetime.now()
            
            # Remove expired messages first
            while buffer and (now - buffer[0].timestamp).total_seconds() > MESSAGE_TTL_SECONDS:
                expired_msg = buffer.popleft()
                logger.debug(f"Removed expired message from {channel} during append (age: {(now - expired_msg.timestamp).total_seconds():.1f}s)")
            
            # Add new message
            timestamped_msg = TimestampedMessage(message=message_dict, timestamp=now)
            buffer.append(timestamped_msg)
            
            # Enforce size limit by removing oldest messages
            while len(buffer) > MAX_MESSAGES_PER_SESSION:
                oldest_msg = buffer.popleft()
                logger.debug(f"Removed oldest message from {channel} (buffer size limit exceeded)")
            
            logger.debug(f"Buffered message for {channel} (buffer size: {len(buffer)}/{MAX_MESSAGES_PER_SESSION})")
    
    async def _get_and_clear_buffer(self, channel: str) -> List[Dict[str, Any]]:
        """Get all valid messages from buffer and clear it."""
        async with self._buffer_lock:
            if channel not in self.session_message_buffer:
                return []
            
            buffer = self.session_message_buffer[channel]
            now = datetime.now()
            valid_messages = []
            
            # Collect valid (non-expired) messages
            while buffer:
                msg = buffer.popleft()
                if (now - msg.timestamp).total_seconds() <= MESSAGE_TTL_SECONDS:
                    valid_messages.append(msg.message)
                else:
                    logger.debug(f"Skipped expired message from {channel} during flush (age: {(now - msg.timestamp).total_seconds():.1f}s)")
            
            # Remove the empty buffer
            del self.session_message_buffer[channel]
            
            return valid_messages
    
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
            await self._add_message_to_buffer(channel, message_dict)
            return 0
        
        if not subscribers:
            logger.debug(f"No subscribers for channel: {channel}")
            return 0
        
        # FLUSH BUFFER: If there are subscribers and this is a session channel, 
        # send any buffered messages first (in chronological order)
        sent_count = 0
        if ChannelType.is_session_channel(channel):
            buffered_messages = await self._get_and_clear_buffer(channel)
            if buffered_messages:
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
    
    async def broadcast_interaction_update(
        self,
        session_id: str,
        update_data: Dict[str, Any],
        exclude_users: Set[str] = None
    ) -> int:
        """
        Broadcast interaction update to both session-specific and dashboard channels.
        
        This ensures real-time updates are visible in both the session detail view
        and the main dashboard during active processing.
        
        Args:
            session_id: Session identifier
            update_data: Interaction update data
            exclude_users: Users to exclude from broadcast
            
        Returns:
            Total number of clients the update was sent to
        """
        total_sent = 0
        
        # Send to session-specific channel for detail views
        session_sent = await self.broadcast_session_update(session_id, update_data, exclude_users)
        total_sent += session_sent
        
        # Also send to dashboard channel for real-time updates in main dashboard
        dashboard_sent = await self.broadcast_dashboard_update(update_data, exclude_users)
        total_sent += dashboard_sent
        
        logger.debug(f"Broadcasted interaction update for session {session_id}: session={session_sent}, dashboard={dashboard_sent}")
        return total_sent

    async def broadcast_chain_progress_update(
        self,
        session_id: str,
        chain_id: str,
        current_stage: Optional[str] = None,
        current_stage_index: Optional[int] = None,
        total_stages: Optional[int] = None,
        completed_stages: Optional[int] = None,
        failed_stages: Optional[int] = None,
        overall_status: ChainStatus = ChainStatus.PROCESSING,
        stage_details: Optional[Dict[str, Any]] = None,
        exclude_users: Optional[Set[str]] = None
    ) -> int:
        """
        Broadcast chain execution progress update.
        
        Args:
            session_id: Session identifier
            chain_id: Chain identifier
            current_stage: Currently executing stage name
            current_stage_index: Current stage index (0-based)
            total_stages: Total number of stages in chain
            completed_stages: Number of completed stages
            failed_stages: Number of failed stages
            overall_status: Overall chain status
            stage_details: Current stage execution details
            exclude_users: Users to exclude from broadcast
            
        Returns:
            Number of clients the update was sent to
        """
        from tarsy.models.websocket_models import ChainProgressUpdate
        
        message = ChainProgressUpdate(
            session_id=session_id,
            chain_id=chain_id,
            current_stage=current_stage,
            current_stage_index=current_stage_index,
            total_stages=total_stages,
            completed_stages=completed_stages,
            failed_stages=failed_stages,
            overall_status=overall_status,
            stage_details=stage_details
        )
        
        return await self.broadcast_message(
            ChannelType.session_channel(session_id), message, exclude_users
        )

    async def broadcast_stage_progress_update(
        self,
        session_id: str,
        chain_id: str,
        stage_execution_id: str,
        stage_id: str,
        stage_name: str,
        stage_index: int,
        agent: str,
        status: StageStatus = StageStatus.PENDING,
        started_at_us: Optional[int] = None,
        completed_at_us: Optional[int] = None,
        duration_ms: Optional[int] = None,
        error_message: Optional[str] = None,
        iteration_strategy: Optional[str] = None,
        exclude_users: Optional[Set[str]] = None
    ) -> int:
        """
        Broadcast individual stage execution progress update.
        
        Args:
            session_id: Session identifier
            chain_id: Chain identifier
            stage_execution_id: Stage execution identifier
            stage_id: Logical stage identifier (e.g., 'initial-analysis')
            stage_name: Stage name
            stage_index: Stage index in chain
            agent: Agent executing the stage
            status: Stage status (pending, active, completed, failed)
            started_at_us: Stage start timestamp
            completed_at_us: Stage completion timestamp
            duration_ms: Stage execution duration
            error_message: Error message if failed
            iteration_strategy: Stage iteration strategy
            exclude_users: Users to exclude from broadcast
            
        Returns:
            Number of clients the update was sent to
        """
        from tarsy.models.websocket_models import StageProgressUpdate
        
        message = StageProgressUpdate(
            session_id=session_id,
            chain_id=chain_id,
            stage_execution_id=stage_execution_id,
            stage_id=stage_id,
            stage_name=stage_name,
            stage_index=stage_index,
            agent=agent,
            status=status,
            started_at_us=started_at_us,
            completed_at_us=completed_at_us,
            duration_ms=duration_ms,
            error_message=error_message,
            iteration_strategy=iteration_strategy
        )
        
        return await self.broadcast_message(
            ChannelType.session_channel(session_id), message, exclude_users
        )