"""
Dashboard broadcast hooks for real-time WebSocket updates.

Implements specialized hooks for broadcasting LLM interactions and MCP communications
to dashboard clients via WebSocket connections using the same event pipeline as
history hooks for consistent data and timing.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

import logging
from typing import Any, Dict

from .base_hooks import BaseLLMHook, BaseMCPHook

logger = logging.getLogger(__name__)


class DashboardLLMHooks(BaseLLMHook):
    """
    Dashboard broadcast hooks for LLM interactions.
    
    Captures LLM interactions and broadcasts real-time updates to dashboard
    clients subscribed to relevant channels, working alongside history hooks
    using the same event data for consistency.
    """
    
    def __init__(self, dashboard_manager, update_service=None):
        """
        Initialize dashboard LLM broadcast hooks.
        
        Args:
        dashboard_manager: Dashboard connection manager for broadcasting
            update_service: Optional dashboard update service for intelligent batching
        """
        super().__init__("llm_dashboard_broadcast_hook")
        self.dashboard_manager = dashboard_manager
        # Use provided update_service or fall back to dashboard_manager's update_service
        self.update_service = update_service or getattr(dashboard_manager, 'update_service', None)
    
    async def process_llm_interaction(self, session_id: str, interaction_data: Dict[str, Any]) -> None:
        """
        Process LLM interaction by broadcasting to dashboard clients.
        
        Args:
            session_id: Session identifier
            interaction_data: Processed interaction data from base class
        """
        # Create dashboard update for session-specific channel
        session_update_data = {
            "interaction_type": "llm",
            "session_id": session_id,
            "step_description": interaction_data["step_description"],
            "model_used": interaction_data["model_used"],
            "success": interaction_data["success"],
            "duration_ms": interaction_data["duration_ms"],
            "timestamp_us": interaction_data["timestamp_us"],
            "tool_calls_present": bool(interaction_data["tool_calls"]),
            "error_message": interaction_data["error_message"]
        }
        
        # Include JSON format for proper dashboard display
        session_update_data["request_json"] = interaction_data.get("request_json")
        session_update_data["response_json"] = interaction_data.get("response_json")
        
        # Extract response text from JSON for quick preview
        response_json = interaction_data.get("response_json")
        response_text = ""
        if response_json:
            # Extract from OpenAI-style response format
            if 'choices' in response_json and response_json['choices']:
                choice = response_json['choices'][0]
                if isinstance(choice, dict) and 'message' in choice:
                    message = choice['message']
                    if isinstance(message, dict) and 'content' in message:
                        response_text = str(message['content'])
        
        if response_text:
            session_update_data["response_preview"] = response_text[:200] + "..." if len(response_text) > 200 else response_text
        
        # Use dashboard update service if available, otherwise fallback to direct broadcasting
        if self.update_service:
            # Use update service for session tracking and immediate broadcasting
            sent_count = await self.update_service.process_llm_interaction(
                session_id, session_update_data
            )
            
            if sent_count > 0:
                logger.debug(f"Dashboard update service processed LLM interaction for session {session_id}: {interaction_data['step_description']}")
        else:
            session_sent = 0
            dashboard_sent = 0
            
            # Fallback to direct broadcaster calls if available
            if self.dashboard_manager.broadcaster:
                session_sent = await self.dashboard_manager.broadcaster.broadcast_session_update(
                session_id, session_update_data
            )
            
            dashboard_update_data = {
                "type": "llm_interaction",
                "session_id": session_id,
                "step_description": interaction_data["step_description"],
                "model": interaction_data["model_used"],
                "status": "completed" if interaction_data["success"] else "error",
                "duration_ms": interaction_data["duration_ms"],
                "timestamp_us": interaction_data["timestamp_us"]
            }
            
            dashboard_sent = await self.dashboard_manager.broadcaster.broadcast_dashboard_update(
                dashboard_update_data
            )
            
            if session_sent or dashboard_sent:
                logger.debug(f"Broadcast LLM interaction for session {session_id} to {session_sent + dashboard_sent} subscribers: {interaction_data['step_description']}")


class DashboardMCPHooks(BaseMCPHook):
    """
    Dashboard broadcast hooks for MCP communications.
    
    Captures MCP communications and broadcasts real-time updates to dashboard
    clients, maintaining exact chronological ordering with LLM interactions.
    """
    
    def __init__(self, dashboard_manager, update_service=None):
        """
        Initialize dashboard MCP broadcast hooks.
        
        Args:
        dashboard_manager: Dashboard connection manager for broadcasting
            update_service: Optional dashboard update service for intelligent batching
        """
        super().__init__("mcp_dashboard_broadcast_hook")
        self.dashboard_manager = dashboard_manager
        # Use provided update_service or fall back to dashboard_manager's update_service
        self.update_service = update_service or getattr(dashboard_manager, 'update_service', None)
    
    async def process_mcp_communication(self, session_id: str, communication_data: Dict[str, Any]) -> None:
        """
        Process MCP communication by broadcasting to dashboard clients.
        
        Args:
            session_id: Session identifier
            communication_data: Processed communication data from base class
        """
        # Create dashboard update for session-specific channel
        session_update_data = {
            "interaction_type": "mcp",
            "session_id": session_id,
            "step_description": communication_data["step_description"],
            "server_name": communication_data["server_name"],
            "communication_type": communication_data["communication_type"],
            "tool_name": communication_data["tool_name"],
            "success": communication_data["success"],
            "duration_ms": communication_data["duration_ms"],
            "timestamp_us": communication_data["timestamp_us"],
            "error_message": communication_data["error_message"]
        }
        
        # Include tool details if present
        if communication_data["tool_arguments"]:
            session_update_data["tool_arguments"] = communication_data["tool_arguments"]
        if communication_data["tool_result"]:
            # Truncate large results
            result_str = str(communication_data["tool_result"])
            session_update_data["tool_result_preview"] = result_str[:300] + "..." if len(result_str) > 300 else result_str
        
        # Use dashboard update service if available, otherwise fallback to direct broadcasting
        if self.update_service:
            # Use update service for session tracking and immediate broadcasting
            sent_count = await self.update_service.process_mcp_communication(
                session_id, session_update_data
            )
            
            if sent_count > 0:
                logger.debug(f"Dashboard update service processed MCP communication for session {session_id}: {communication_data['step_description']}")
        else:
            # Fallback to direct broadcasting
            session_sent = 0
            dashboard_sent = 0
            
            # Fallback to direct broadcaster calls if available
            if self.dashboard_manager.broadcaster:
                session_sent = await self.dashboard_manager.broadcaster.broadcast_session_update(
                session_id, session_update_data
            )
            
            dashboard_update_data = {
                "type": "mcp_communication",
                "session_id": session_id,
                "step_description": communication_data["step_description"],
                "server": communication_data["server_name"],
                "tool": communication_data["tool_name"],
                "status": "completed" if communication_data["success"] else "error",
                "duration_ms": communication_data["duration_ms"],
                "timestamp_us": communication_data["timestamp_us"]
            }
            
            dashboard_sent = await self.dashboard_manager.broadcaster.broadcast_dashboard_update(
                dashboard_update_data
            )
            
            if session_sent or dashboard_sent:
                logger.debug(f"Broadcast MCP communication for session {session_id} to {session_sent + dashboard_sent} subscribers: {communication_data['step_description']}")


def register_dashboard_hooks(dashboard_manager):
    """
    Register dashboard broadcast hooks with the global hook manager.
    
    This function should be called during application startup to enable
    automatic dashboard broadcasting for LLM and MCP interactions.
    
    Args:
        dashboard_manager: Dashboard connection manager for broadcasting
    """
    from .base_hooks import get_hook_manager
    
    hook_manager = get_hook_manager()
    
    # Register dashboard LLM hooks with update_service reference
    llm_dashboard_hooks = DashboardLLMHooks(dashboard_manager, dashboard_manager.update_service)
    hook_manager.register_hook("llm.post", llm_dashboard_hooks)
    hook_manager.register_hook("llm.error", llm_dashboard_hooks)
    
    # Register dashboard MCP hooks with update_service reference
    mcp_dashboard_hooks = DashboardMCPHooks(dashboard_manager, dashboard_manager.update_service)
    hook_manager.register_hook("mcp.post", mcp_dashboard_hooks)
    hook_manager.register_hook("mcp.error", mcp_dashboard_hooks)
    
    logger.info("Dashboard broadcast hooks registered successfully")
    return hook_manager


def register_integrated_hooks(dashboard_manager):
    """
    Register both history and dashboard hooks with the global hook manager.
    
    This function integrates dashboard broadcasting with the existing EP-0003
    history hooks, ensuring both systems receive the same event data for
    consistency between historical records and real-time dashboard updates.
    
    Args:
        dashboard_manager: Dashboard connection manager for broadcasting
    """
    from .base_hooks import get_hook_manager
    
    # Register history hooks first (existing EP-0003 functionality)
    register_history_hooks()
    
    # Register dashboard hooks alongside history hooks
    register_dashboard_hooks(dashboard_manager)
    
    hook_manager = get_hook_manager()
    logger.info("Integrated hook system registered: history + dashboard broadcasting")
    
    return hook_manager


# Import at module level to make it patchable for tests
from .history_hooks import register_history_hooks 