"""
Typed event hooks for clean, type-safe real-time updates.

This module provides typed hooks that handle LLM and MCP interactions
using structured Pydantic models, publishing events to the event stream
for real-time dashboard updates via WebSocket.
"""

import logging
from tarsy.hooks.hook_context import BaseHook
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.models.db_models import StageExecution

logger = logging.getLogger(__name__)


class LLMEventHook(BaseHook[LLMInteraction]):
    """
    Typed hook for publishing LLM interaction events.
    
    Receives unified LLMInteraction and publishes minimal event to the event stream
    for real-time dashboard notifications.
    """
    
    def __init__(self):
        super().__init__("llm_event")

    async def execute(self, interaction: LLMInteraction) -> None:
        """Publish LLM interaction event to event stream."""
        from tarsy.services.events.event_helpers import publish_llm_interaction
        
        await publish_llm_interaction(
            session_id=interaction.session_id,
            interaction_id=interaction.interaction_id,
            stage_id=interaction.stage_execution_id
        )

class MCPEventHook(BaseHook[MCPInteraction]):
    """
    Typed hook for publishing MCP tool call events.
    
    Receives unified MCPInteraction and publishes minimal event to the event stream
    for real-time dashboard notifications.
    """
    
    def __init__(self):
        super().__init__("mcp_event")

    async def execute(self, interaction: MCPInteraction) -> None:
        """
        Publish MCP tool call event to event stream.
        
        Args:
            interaction: Unified MCP interaction data
        """
        from tarsy.services.events.event_helpers import publish_mcp_tool_call
        
        await publish_mcp_tool_call(
            session_id=interaction.session_id,
            interaction_id=interaction.request_id,
            tool_name=interaction.tool_name,
            stage_id=interaction.stage_execution_id
        )


class MCPListEventHook(BaseHook[MCPInteraction]):
    """
    Typed hook for publishing MCP tool list events.
    
    Receives unified MCPInteraction and publishes minimal event to the event stream
    for real-time dashboard notifications.
    """
    
    def __init__(self):
        super().__init__("mcp_list_event")

    async def execute(self, interaction: MCPInteraction) -> None:
        """
        Publish MCP tool list event to event stream.
        
        Args:
            interaction: Unified MCP tool list data
        """
        from tarsy.services.events.event_helpers import publish_mcp_tool_list
        
        await publish_mcp_tool_list(
            session_id=interaction.session_id,
            request_id=interaction.request_id,
            server_name=interaction.server_name,
            stage_id=interaction.stage_execution_id
        )


class StageExecutionEventHook(BaseHook[StageExecution]):
    """
    Typed hook for publishing stage execution events.
    
    Receives StageExecution and publishes minimal stage progress events to the event stream
    for real-time dashboard notifications.
    """
    
    def __init__(self):
        super().__init__("stage_event")

    async def execute(self, stage_execution: StageExecution) -> None:
        """
        Publish stage execution events to event stream.
        
        Args:
            stage_execution: Stage execution data
        """
        from tarsy.models.constants import StageStatus
        from tarsy.services.events.event_helpers import (
            publish_stage_started,
            publish_stage_completed
        )
        
        if stage_execution.status == StageStatus.ACTIVE.value:
            await publish_stage_started(
                session_id=stage_execution.session_id,
                stage_id=stage_execution.execution_id,
                stage_name=stage_execution.stage_name
            )
        elif stage_execution.status in [StageStatus.COMPLETED.value, StageStatus.FAILED.value, StageStatus.PARTIAL.value]:
            await publish_stage_completed(
                session_id=stage_execution.session_id,
                stage_id=stage_execution.execution_id,
                stage_name=stage_execution.stage_name,
                status=stage_execution.status
            )