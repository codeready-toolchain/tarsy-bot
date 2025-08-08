"""
WebSocket manager for dashboard real-time updates.
"""

from fastapi import WebSocket

from tarsy.services.dashboard_connection_manager import DashboardConnectionManager


class WebSocketManager:
    """Manages WebSocket connections for dashboard real-time updates."""
    
    def __init__(self):
        # Dashboard connection manager for dashboard WebSocket connections
        self.dashboard_manager = DashboardConnectionManager()
    
    # Dashboard WebSocket methods
    async def connect_dashboard(self, websocket: WebSocket, user_id: str):
        """Connect a dashboard WebSocket for a specific user."""
        await self.dashboard_manager.connect(websocket, user_id)
    
    def disconnect_dashboard(self, user_id: str):
        """Disconnect a dashboard WebSocket."""
        self.dashboard_manager.disconnect(user_id)
    
    async def handle_dashboard_message(self, user_id: str, message: dict):
        """Handle dashboard WebSocket messages (subscriptions, etc.)."""
        await self.dashboard_manager.handle_subscription_message(user_id, message)
    
    async def broadcast_dashboard_update(self, channel: str, message: dict, exclude_users: set = None):
        """Broadcast a message to dashboard subscribers of a specific channel."""
        return await self.dashboard_manager.broadcast_to_channel(channel, message, exclude_users)
    
    def get_dashboard_stats(self):
        """Get dashboard connection statistics."""
        stats = self.dashboard_manager.get_connection_stats()
        
        # Include broadcaster stats if available
        if self.dashboard_manager.broadcaster:
            stats["broadcaster"] = self.dashboard_manager.broadcaster.get_broadcast_stats()
        
        return stats
    
    async def initialize_dashboard_broadcaster(self):
        """Initialize the advanced dashboard broadcaster."""
        return await self.dashboard_manager.initialize_broadcaster()
    
    async def shutdown_dashboard_broadcaster(self):
        """Shutdown the dashboard broadcaster."""
        await self.dashboard_manager.shutdown_broadcaster()
    
    async def broadcast_dashboard_update_advanced(self, data: dict, exclude_users: set = None):
        """Broadcast dashboard update using advanced broadcaster."""
        if self.dashboard_manager.broadcaster:
            return await self.dashboard_manager.broadcaster.broadcast_dashboard_update(
                data, exclude_users
            )
        return 0
    
    async def broadcast_session_update_advanced(self, session_id: str, data: dict, exclude_users: set = None):
        """Broadcast session update using advanced broadcaster."""
        if self.dashboard_manager.broadcaster:
            return await self.dashboard_manager.broadcaster.broadcast_session_update(
                session_id, data, exclude_users
            )
        return 0
    
    async def broadcast_system_health_advanced(self, status: str, services: dict, exclude_users: set = None):
        """Broadcast system health update using advanced broadcaster."""
        if self.dashboard_manager.broadcaster:
            return await self.dashboard_manager.broadcaster.broadcast_system_health_update(
                status, services, exclude_users
            )
        return 0 
    
 