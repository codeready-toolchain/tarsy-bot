"""
Typed dashboard hooks for clean, type-safe real-time updates.

This module provides typed hooks that handle LLM and MCP interactions
using structured Pydantic models, broadcasting updates to the dashboard
via WebSocket without data contamination.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from tarsy.hooks.typed_context import BaseTypedHook
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.models.db_models import StageExecution
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
            # Create dashboard update with complete conversation object
            update_data = {
                "type": "llm_interaction",
                "session_id": interaction.session_id,
                "interaction_id": interaction.interaction_id,  # Use interaction_id instead of removed request_id
                "model_name": interaction.model_name,
                "provider": interaction.provider,
                "step_description": f"LLM analysis using {interaction.model_name}",
                # Send complete conversation object instead of individual prompts
                "conversation": (
                    interaction.conversation.model_dump() 
                    if interaction.conversation else None
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
            
            logger.debug(f"Broadcasted LLM interaction {interaction.interaction_id} to dashboard")
            
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


class TypedStageExecutionDashboardHook(BaseTypedHook[StageExecution]):
    """
    Typed hook for broadcasting stage execution progress to dashboard.
    
    Receives StageExecution and broadcasts stage progress updates to WebSocket clients.
    """
    
    def __init__(self, dashboard_broadcaster: DashboardBroadcaster):
        super().__init__("typed_stage_dashboard")
        self.dashboard_broadcaster = dashboard_broadcaster

    async def execute(self, stage_execution: StageExecution) -> None:
        """
        Broadcast stage execution progress to dashboard.
        
        Args:
            stage_execution: Stage execution data
        """
        try:
            # Use stage_name field directly
            stage_name = stage_execution.stage_name
            
            # Get chain_id - fallback to session_id if not available in context
            # In a proper implementation, this would be passed through context
            chain_id = stage_execution.session_id  # Using session_id as fallback
            
            # Format stage progress as dashboard update - this ensures it gets wrapped properly
            # and sent to both session and dashboard channels like other interactions
            stage_update = {
                "type": "stage_progress",
                "session_id": stage_execution.session_id,
                "chain_id": chain_id,
                "stage_execution_id": stage_execution.execution_id,
                "stage_id": stage_execution.stage_id,
                "stage_name": stage_name,
                "stage_index": stage_execution.stage_index,
                "agent": stage_execution.agent,
                "status": stage_execution.status,
                "started_at_us": stage_execution.started_at_us,
                "completed_at_us": stage_execution.completed_at_us,
                "duration_ms": stage_execution.duration_ms,
                "error_message": stage_execution.error_message,
                "iteration_strategy": getattr(stage_execution, 'iteration_strategy', None),
                "timestamp": datetime.now().isoformat()
            }
            
            # Send to session-specific channel wrapped in dashboard_update format
            session_count = await self.dashboard_broadcaster.broadcast_session_update(
                stage_execution.session_id, stage_update
            )
            
            # Also send to dashboard channel for general monitoring
            dashboard_count = await self.dashboard_broadcaster.broadcast_dashboard_update(stage_update)
            
            logger.debug(f"Broadcasted stage execution {stage_execution.execution_id} progress to dashboard: session={session_count}, dashboard={dashboard_count}")
            
        except Exception as e:
            logger.error(f"Failed to broadcast stage execution to dashboard: {e}")
            raise