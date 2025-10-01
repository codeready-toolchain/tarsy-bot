"""
Dashboard connection manager for WebSocket connections.
"""

import json
from datetime import datetime
from typing import Dict, Set

from fastapi import WebSocket
from pydantic import ValidationError

from tarsy.utils.logger import get_module_logger
from tarsy.models.websocket_models import (
    ChannelType,
    SubscriptionMessage,
    SubscriptionResponse,
    ErrorMessage
)

logger = get_module_logger(__name__)


class DashboardConnectionManager:
    """Manages WebSocket connections for dashboard real-time updates."""
    
    def __init__(self):
        # Dictionary to store active connections by user_id
        self.active_connections: Dict[str, WebSocket] = {}
        # Track subscriptions per user: user_id -> set of channels
        self.user_subscriptions: Dict[str, Set[str]] = {}
        # Track channels to users mapping for efficient broadcasting
        self.channel_subscribers: Dict[str, Set[str]] = {}
        # Advanced broadcasting with batching and throttling
        self.broadcaster = None  # Will be initialized after connection manager is created
        # Dashboard update service for intelligent update management
        self.update_service = None  # Will be initialized after broadcaster is created
    
    def _datetime_serializer(self, obj):
        """Custom JSON serializer for datetime objects."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    async def connect(self, websocket: WebSocket, user_id: str):
        """Connect a WebSocket for a specific user."""
        await websocket.accept()
        
        # Store connection
        self.active_connections[user_id] = websocket
        
        # Initialize subscription tracking
        if user_id not in self.user_subscriptions:
            self.user_subscriptions[user_id] = set()
        
        logger.info(f"Dashboard connection established for user: {user_id}")
    
    def disconnect(self, user_id: str):
        """Disconnect a WebSocket and clean up subscriptions."""
        if user_id in self.active_connections:
            # Remove from active connections
            del self.active_connections[user_id]
            
            # Clean up subscriptions
            if user_id in self.user_subscriptions:
                user_channels = self.user_subscriptions[user_id].copy()
                for channel in user_channels:
                    self._unsubscribe_from_channel(user_id, channel)
                del self.user_subscriptions[user_id]
            
            logger.info(f"Dashboard connection disconnected for user: {user_id}")
    
    async def subscribe_to_channel(self, user_id: str, channel: str) -> bool:
        """
        Subscribe user to a specific channel.
        
        For session channels, this will immediately flush any buffered messages
        to fix the race condition where alerts complete before the UI subscribes.
        
        Args:
            user_id: User identifier
            channel: Channel name to subscribe to
            
        Returns:
            True if subscription was successful, False otherwise
        """
        if user_id not in self.user_subscriptions:
            self.user_subscriptions[user_id] = set()
        
        if user_id not in self.active_connections:
            logger.warning(f"Attempted to subscribe inactive user {user_id} to channel {channel}")
            return False
        
        # Add to user subscriptions
        self.user_subscriptions[user_id].add(channel)
        
        # Add to channel subscribers
        if channel not in self.channel_subscribers:
            self.channel_subscribers[channel] = set()
        self.channel_subscribers[channel].add(user_id)
        
        logger.info(f"User {user_id} subscribed to channel: {channel}")
        
        # Immediately flush buffered messages for session channels
        # This fixes the race condition where:
        # 1. Alert completes/fails quickly (before UI subscribes)
        # 2. Status updates are buffered
        # 3. Session is archived (no more messages will be sent)
        # 4. UI subscribes (too late - buffer never flushes because no new messages)
        # Solution: Flush buffer immediately upon subscription
        if self.broadcaster and ChannelType.is_session_channel(channel):
            await self.broadcaster.flush_session_buffer(channel)
        
        return True
    
    def unsubscribe_from_channel(self, user_id: str, channel: str):
        """Unsubscribe user from a specific channel."""
        return self._unsubscribe_from_channel(user_id, channel)
    
    def _unsubscribe_from_channel(self, user_id: str, channel: str):
        """Internal method to unsubscribe user from channel."""
        # Remove from user subscriptions
        if user_id in self.user_subscriptions:
            self.user_subscriptions[user_id].discard(channel)
        
        # Remove from channel subscribers
        if channel in self.channel_subscribers:
            self.channel_subscribers[channel].discard(user_id)
            # Clean up empty channels
            if not self.channel_subscribers[channel]:
                del self.channel_subscribers[channel]
        
        logger.info(f"User {user_id} unsubscribed from channel: {channel}")
        return True    
    

    def get_channel_subscribers(self, channel: str) -> Set[str]:
        """Get all users subscribed to a channel."""
        return self.channel_subscribers.get(channel, set()).copy()
    
    async def send_to_user(self, user_id: str, message: dict):
        """Send a message to a specific user."""
        if user_id not in self.active_connections:
            logger.warning(f"Attempted to send message to inactive user: {user_id}")
            return False
        
        try:
            message_json = json.dumps(message, default=self._datetime_serializer)
            await self.active_connections[user_id].send_text(message_json)
            return True
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {str(e)}")
            # Clean up broken connection
            self.disconnect(user_id)
            return False
    

    def _is_valid_channel(self, channel: str) -> bool:
        """Validate if a channel is valid for subscription."""
        # Check predefined channels
        predefined_channels = [ChannelType.DASHBOARD_UPDATES, ChannelType.SYSTEM_HEALTH]
        if channel in predefined_channels:
            return True
        
        # Check session channels (any string starting with "session_")
        if ChannelType.is_session_channel(channel):
            session_id = ChannelType.extract_session_id(channel)
            return session_id is not None and len(session_id) > 0
        
        # Unknown channel
        return False
    
    async def handle_subscription_message(self, user_id: str, message: dict):
        """Handle subscription/unsubscription messages from clients."""
        try:
            # Validate and parse subscription message
            subscription_msg = SubscriptionMessage(**message)
            channel = subscription_msg.channel
            action = subscription_msg.type
            
            # Validate channel
            if not self._is_valid_channel(channel):
                logger.warning(f"Invalid subscription request from {user_id} to channel {channel}")
                response = SubscriptionResponse(
                    action=action,
                    channel=channel,
                    success=False,
                    message=f"Unknown channel: {channel}"
                )
                await self.send_to_user(user_id, response.model_dump())
                return
            
            # Handle subscription/unsubscription
            if action == "subscribe":
                await self.subscribe_to_channel(user_id, channel)
            elif action == "unsubscribe":
                self.unsubscribe_from_channel(user_id, channel)
            
            # Log successful request
            logger.info(f"Processed {action} request from {user_id} for channel {channel}")
            
            # Send success response
            response = SubscriptionResponse(
                action=action,
                channel=channel,
                success=True,
                message=f"Successfully {action}d to {channel}"
            )
            await self.send_to_user(user_id, response.model_dump())
            
        except ValidationError as e:
            # Handle invalid message format
            error_response = ErrorMessage(
                message=f"Invalid subscription message format: {str(e)}"
            )
            await self.send_to_user(user_id, error_response.model_dump())
        except Exception as e:
            # Handle other errors
            logger.error(f"Error handling subscription message from {user_id}: {str(e)}")
            error_response = ErrorMessage(
                message="Internal error processing subscription request"
            )
            await self.send_to_user(user_id, error_response.model_dump())
    
    async def initialize_broadcaster(self):
        """Initialize the advanced broadcaster and update service."""
        from tarsy.services.dashboard_broadcaster import DashboardBroadcaster
        from tarsy.services.dashboard_update_service import DashboardUpdateService
        
        if self.broadcaster is None:
            self.broadcaster = DashboardBroadcaster(self)
            logger.info("Dashboard broadcaster initialized")
            
            # Start the session buffer cleanup task
            self.broadcaster.start_cleanup_task()
            logger.info("Dashboard broadcaster cleanup task started")
            
            # Initialize update service with broadcaster
            self.update_service = DashboardUpdateService(self.broadcaster)
            await self.update_service.start()
            logger.info("Dashboard update service initialized and started")
        
        return self.broadcaster
    
    async def shutdown_broadcaster(self):
        """Shutdown the broadcaster and update service."""
        if self.update_service:
            await self.update_service.stop()
            self.update_service = None
            logger.info("Dashboard update service stopped")
            
        if self.broadcaster:
            # Stop the cleanup task before shutting down broadcaster
            self.broadcaster.stop_cleanup_task()
            logger.info("Dashboard broadcaster cleanup task stopped")
            self.broadcaster = None
            logger.info("Dashboard broadcaster stopped")
