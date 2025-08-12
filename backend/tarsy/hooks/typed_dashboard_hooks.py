"""
Typed dashboard hooks for clean, type-safe real-time updates.

This module provides typed hooks that handle LLM and MCP interactions
using structured Pydantic models, broadcasting updates to the dashboard
via WebSocket without data contamination.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from tarsy.hooks.typed_context import BaseTypedHook
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.utils.timestamp import now_us
from tarsy.services.dashboard_broadcaster import DashboardBroadcaster

logger = logging.getLogger(__name__)


class TypedLLMDashboardHook(BaseTypedHook[LLMInteraction]):
    """
    Typed hook for broadcasting LLM interactions to dashboard.
    
    Receives unified LLMInteraction and broadcasts it to WebSocket clients.
    """
    
    def __init__(self, dashboard_broadcaster: DashboardBroadcaster):
        super().__init__("typed_llm_dashboard")
        self.dashboard_broadcaster = dashboard_broadcaster

    async def execute(self, interaction: LLMInteraction) -> None:
        """
        Broadcast LLM interaction to dashboard.
        
        Args:
            interaction: Unified LLM interaction data
        """
        try:
            # Create dashboard update from typed interaction
            update_data = {
                "type": "llm_interaction",
                "session_id": interaction.session_id,
                "request_id": interaction.request_id,
                "model_name": interaction.model_name,
                "provider": interaction.provider,
                "step_description": f"LLM analysis using {interaction.model_name}",
                "system_prompt": interaction.get_system_prompt(),
                "user_prompt": interaction.get_user_prompt(),
                "response_text": interaction.get_response_text(),
                "success": interaction.success,
                "error_message": interaction.error_message,
                "duration_ms": interaction.duration_ms,
                "token_usage": interaction.token_usage,
                "timestamp_us": interaction.timestamp_us,
                # Chain context for enhanced dashboard visualization
                "stage_execution_id": interaction.stage_execution_id
            }
            
            # Broadcast to dashboard
            await self.dashboard_broadcaster.broadcast_interaction_update(
                session_id=interaction.session_id,
                update_data=update_data
            )
            
            logger.debug(f"Broadcasted LLM interaction {interaction.request_id} to dashboard")
            
        except Exception as e:
            logger.error(f"Failed to broadcast LLM interaction to dashboard: {e}")
            raise


class TypedMCPDashboardHook(BaseTypedHook[MCPInteraction]):
    """
    Typed hook for broadcasting MCP tool interactions to dashboard.
    
    Receives unified MCPInteraction and broadcasts it to WebSocket clients.
    """
    
    def __init__(self, dashboard_broadcaster: DashboardBroadcaster):
        super().__init__("typed_mcp_dashboard")
        self.dashboard_broadcaster = dashboard_broadcaster

    async def execute(self, interaction: MCPInteraction) -> None:
        """
        Broadcast MCP interaction to dashboard.
        
        Args:
            interaction: Unified MCP interaction data
        """
        try:
            # Create dashboard update from typed interaction
            update_data = {
                "type": "mcp_interaction",
                "session_id": interaction.session_id,
                "request_id": interaction.request_id,
                "server_name": interaction.server_name,
                "tool_name": interaction.tool_name,
                "communication_type": interaction.communication_type,
                "step_description": interaction.get_step_description(),
                "tool_arguments": interaction.tool_arguments,
                "tool_result": interaction.tool_result,
                "success": interaction.success,
                "error_message": interaction.error_message,
                "duration_ms": interaction.duration_ms,
                "timestamp_us": interaction.timestamp_us,
                # Chain context for enhanced dashboard visualization
                "stage_execution_id": interaction.stage_execution_id
            }
            
            # Broadcast to dashboard
            await self.dashboard_broadcaster.broadcast_interaction_update(
                session_id=interaction.session_id,
                update_data=update_data
            )
            
            logger.debug(f"Broadcasted MCP interaction {interaction.request_id} to dashboard")
            
        except Exception as e:
            logger.error(f"Failed to broadcast MCP interaction to dashboard: {e}")
            raise


class TypedMCPListDashboardHook(BaseTypedHook[MCPInteraction]):
    """
    Typed hook for broadcasting MCP tool list operations to dashboard.
    
    Receives unified MCPInteraction and broadcasts it to WebSocket clients.
    """
    
    def __init__(self, dashboard_broadcaster: DashboardBroadcaster):
        super().__init__("typed_mcp_list_dashboard")
        self.dashboard_broadcaster = dashboard_broadcaster

    async def execute(self, interaction: MCPInteraction) -> None:
        """
        Broadcast MCP tool list operation to dashboard.
        
        Args:
            interaction: Unified MCP tool list data
        """
        try:
            # Create dashboard update from typed interaction
            update_data = {
                "type": "mcp_tool_list",
                "session_id": interaction.session_id,
                "request_id": interaction.request_id,
                "server_name": interaction.server_name or "all_servers",
                "communication_type": interaction.communication_type,
                "step_description": interaction.get_step_description(),
                "available_tools": interaction.available_tools,
                "tool_count": (
                    sum(len(tools) for tools in interaction.available_tools.values())
                    if interaction.available_tools else 0
                ),
                "success": interaction.success,
                "error_message": interaction.error_message,
                "duration_ms": interaction.duration_ms,
                "timestamp_us": interaction.timestamp_us,
                # Chain context for enhanced dashboard visualization
                "stage_execution_id": interaction.stage_execution_id
            }
            
            # Broadcast to dashboard
            await self.dashboard_broadcaster.broadcast_interaction_update(
                session_id=interaction.session_id,
                update_data=update_data
            )
            
            logger.debug(f"Broadcasted MCP tool list {interaction.request_id} to dashboard")
            
        except Exception as e:
            logger.error(f"Failed to broadcast MCP tool list to dashboard: {e}")
            raise