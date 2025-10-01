"""
Dashboard update service for formatting and managing real-time updates.

Provides centralized management of dashboard updates with intelligent batching,
session status tracking, and subscription-based filtering for optimal
performance and user experience.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, Optional
from dataclasses import dataclass

from tarsy.utils.logger import get_module_logger

from tarsy.services.dashboard_broadcaster import DashboardBroadcaster

logger = get_module_logger(__name__)


@dataclass
class SessionSummary:
    """Summary information for active sessions."""
    session_id: str
    status: str  # Valid values from AlertSessionStatus enum: "pending", "in_progress", "completed", "failed"
    agent_type: Optional[str] = None
    start_time: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    interactions_count: int = 0
    llm_interactions: int = 0
    mcp_communications: int = 0
    errors_count: int = 0
    progress_percentage: int = 0


class DashboardUpdateService:
    """
    Service for formatting and managing dashboard updates.
    
    Provides intelligent batching, session tracking, and filtering
    for optimal dashboard performance and user experience.
    """
    
    def __init__(self, broadcaster: DashboardBroadcaster):
        """
        Initialize dashboard update service.
        
        Args:
            broadcaster: Dashboard broadcaster for message distribution
        """
        self.broadcaster = broadcaster
        
        # Session tracking
        self.active_sessions: Dict[str, SessionSummary] = {}
        
        # Session change tracking and heartbeat
        self.last_active_count = 0
        self.session_check_interval = 10  # Check for session changes every 10 seconds
        self.heartbeat_interval = 60  # Send heartbeat every minute to keep WebSocket alive
        self.last_heartbeat = datetime.now()
        
        # Background tasks
        self.session_tracker_task: Optional[asyncio.Task] = None
        self.running = False
    
    async def start(self):
        """Start background tasks for session tracking."""
        if not self.running:
            self.running = True
            self.session_tracker_task = asyncio.create_task(self._session_tracker())
            logger.info("DashboardUpdateService started")
    
    async def stop(self):
        """Stop background tasks."""
        self.running = False
        
        if self.session_tracker_task:
            self.session_tracker_task.cancel()
            try:
                await self.session_tracker_task
            except asyncio.CancelledError:
                pass
        
        logger.info("DashboardUpdateService stopped")
    
    async def process_llm_interaction(
        self, 
        session_id: str, 
        interaction_data: Dict[str, Any]
    ) -> int:
        """
        Process LLM interaction update for dashboard.
        
        Args:
            session_id: Session identifier
            interaction_data: LLM interaction data from hooks
            
        Returns:
            Number of clients the update was sent to
        """
        # Update session tracking
        self._update_session_from_llm(session_id, interaction_data)
        
        # Format update for dashboard
        formatted_update = self._format_llm_update(session_id, interaction_data)
        
        # Always broadcast immediately
        return await self._broadcast_update(formatted_update)
    
    async def process_mcp_communication(
        self, 
        session_id: str, 
        communication_data: Dict[str, Any]
    ) -> int:
        """
        Process MCP communication update for dashboard.
        
        Args:
            session_id: Session identifier
            communication_data: MCP communication data from hooks
            
        Returns:
            Number of clients the update was sent to
        """
        # Update session tracking
        self._update_session_from_mcp(session_id, communication_data)
        
        # Format update for dashboard
        formatted_update = self._format_mcp_update(session_id, communication_data)
        
        # Always broadcast immediately
        return await self._broadcast_update(formatted_update)
    
    async def process_session_status_change(
        self, 
        session_id: str, 
        status: str, 
        details: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Process session status change.
        
        Args:
            session_id: Session identifier
            status: New session status (from AlertSessionStatus enum: 'pending', 'in_progress', 'completed', 'failed')
            details: Additional status details
            
        Returns:
            Number of clients the update was sent to
        """
        logger.debug(f"Processing session status change for {session_id}: status={status}")
        
        # Update session summary
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = SessionSummary(
                session_id=session_id,
                status=status,
                start_time=datetime.now(),
                last_activity=datetime.now()
            )
            logger.debug(f"Created new session summary for {session_id}")
        else:
            self.active_sessions[session_id].status = status
            self.active_sessions[session_id].last_activity = datetime.now()
            logger.debug(f"Updated existing session summary for {session_id}")
        
        # Add details if provided
        if details:
            session = self.active_sessions[session_id]
            if 'agent_type' in details:
                session.agent_type = details['agent_type']
            if 'progress_percentage' in details:
                session.progress_percentage = details['progress_percentage']
        
        # Create status update
        status_update = {
            "type": "session_status_change",
            "session_id": session_id,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        
        # Add details if provided
        if details:
            status_update.update(details)
        
        logger.info(f"Broadcasting session status update for {session_id}: status={status}")
        
        # Broadcast immediately for status changes
        sent_count = await self._broadcast_update(status_update)
        
        logger.info(f"Session status update for {session_id} sent to {sent_count} clients")
        
        # Move to history if session is completed
        # Use enum to ensure we catch all terminal statuses consistently
        from tarsy.models.constants import AlertSessionStatus
        if status in AlertSessionStatus.terminal_values():
            self._archive_session(session_id)
            logger.debug(f"Archived session {session_id} after terminal status: {status}")
        
        return sent_count
    
    async def broadcast_active_sessions(self) -> int:
        """
        Broadcast active sessions list to dashboard for refresh triggering.
        
        Returns:
            Number of clients the update was sent to
        """
        session_data = {
            "type": "system_metrics",  # Keep same type for frontend compatibility
            "active_sessions_list": [
                {
                    "session_id": s.session_id,
                    "status": s.status,
                    "agent_type": s.agent_type,
                    "progress": s.progress_percentage,
                    "interactions": s.interactions_count,
                    "errors": s.errors_count
                }
                for s in self.active_sessions.values()
            ],
            "timestamp": datetime.now().isoformat()
        }
        
        return await self.broadcaster.broadcast_dashboard_update(session_data)
    

    
    # Private methods
    
    def _update_session_from_llm(self, session_id: str, interaction_data: Dict[str, Any]):
        """Update session summary from LLM interaction."""
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = SessionSummary(
                session_id=session_id,
                status="active",
                start_time=datetime.now(),
                last_activity=datetime.now()
            )
        
        session = self.active_sessions[session_id]
        session.last_activity = datetime.now()
        session.interactions_count += 1
        session.llm_interactions += 1
        
        if not interaction_data.get('success', True):
            session.errors_count += 1
    
    def _update_session_from_mcp(self, session_id: str, communication_data: Dict[str, Any]):
        """Update session summary from MCP communication."""
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = SessionSummary(
                session_id=session_id,
                status="active",
                start_time=datetime.now(),
                last_activity=datetime.now()
            )
        
        session = self.active_sessions[session_id]
        session.last_activity = datetime.now()
        session.interactions_count += 1
        session.mcp_communications += 1
        
        if not communication_data.get('success', True):
            session.errors_count += 1
    
    def _format_llm_update(self, session_id: str, interaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format LLM interaction data for dashboard."""
        return {
            "type": "llm_interaction",
            "session_id": session_id,
            "step_description": interaction_data.get('step_description', 'LLM interaction'),
            "model_used": interaction_data.get('model_used', 'unknown'),
            "success": interaction_data.get('success', True),
            "duration_ms": interaction_data.get('duration_ms', 0),
            "timestamp": interaction_data.get('timestamp', datetime.now().isoformat()),
            "error_message": interaction_data.get('error_message')
        }
    
    def _format_mcp_update(self, session_id: str, communication_data: Dict[str, Any]) -> Dict[str, Any]:
        """Format MCP communication data for dashboard."""
        return {
            "type": "mcp_communication",
            "session_id": session_id,
            "step_description": communication_data.get('step_description', 'MCP communication'),
            "server_name": communication_data.get('server_name', 'unknown'),
            "tool_name": communication_data.get('tool_name'),
            "success": communication_data.get('success', True),
            "duration_ms": communication_data.get('duration_ms', 0),
            "timestamp": communication_data.get('timestamp', datetime.now().isoformat()),
            "error_message": communication_data.get('error_message')
        }
    
    async def _broadcast_update(self, update: Dict[str, Any]) -> int:
        """Broadcast single update via broadcaster."""
        try:
            # If this update is session-specific (contains session_id), send to both channels
            if 'session_id' in update:
                session_id = update['session_id']
                
                # Send to session-specific channel for detail views
                session_count = await self.broadcaster.broadcast_session_update(session_id, update)
                
                # FIXED: Send ALL session-specific updates to dashboard channel too
                # This includes llm_interaction, mcp_communication, and session_status_change
                # This ensures the dashboard receives real-time updates during processing
                dashboard_count = await self.broadcaster.broadcast_dashboard_update(update)
                return session_count + dashboard_count
            else:
                # Send general updates to dashboard channel
                return await self.broadcaster.broadcast_dashboard_update(update)
        except Exception as e:
            logger.error(f"Failed to broadcast dashboard update: {str(e)}")
            return 0
    
    def _archive_session(self, session_id: str):
        """Remove completed session from active sessions."""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
            logger.debug(f"Archived completed session: {session_id}")
    
    async def _session_tracker(self):
        """Background task to track session changes and send heartbeats."""
        while self.running:
            try:
                # Check if active session count changed
                current_active_count = len(self.active_sessions)
                should_broadcast = False
                
                # Broadcast if session count changed
                if current_active_count != self.last_active_count:
                    should_broadcast = True
                    logger.debug(f"Active session count changed: {self.last_active_count} → {current_active_count}")
                    self.last_active_count = current_active_count
                
                # Also broadcast if it's been too long since last heartbeat (keep WebSocket alive)
                time_since_heartbeat = (datetime.now() - self.last_heartbeat).total_seconds()
                if time_since_heartbeat >= self.heartbeat_interval:
                    should_broadcast = True
                    logger.debug(f"Heartbeat broadcast after {time_since_heartbeat:.0f}s")
                
                # Broadcast session update if needed
                if should_broadcast:
                    await self.broadcast_active_sessions()
                    self.last_heartbeat = datetime.now()
                
                # Wait for next check
                await asyncio.sleep(self.session_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in session tracker: {str(e)}")
                await asyncio.sleep(5)  # Wait before retry
