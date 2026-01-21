"""
Typed event hooks for clean, type-safe real-time updates.

This module provides typed hooks that handle LLM and MCP interactions
using structured Pydantic models, publishing events to the event stream
for real-time dashboard updates via WebSocket.
"""

import logging

from tarsy.hooks.hook_context import BaseHook
from tarsy.models.db_models import ChatUserMessage, StageExecution
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction

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
        from sqlmodel import select

        from tarsy.database.init_db import get_async_session_factory
        from tarsy.models.constants import StageStatus
        from tarsy.services.events.event_helpers import (
            publish_stage_completed,
            publish_stage_started,
        )
        
        if stage_execution.status == StageStatus.ACTIVE.value:
            # Fetch user message if this is a chat stage
            chat_user_message_id = None
            chat_user_message_content = None
            chat_user_message_author = None
            
            if stage_execution.chat_user_message_id:
                try:
                    async_session_factory = get_async_session_factory()
                    async with async_session_factory() as session:
                        stmt = select(ChatUserMessage).where(
                            ChatUserMessage.message_id == stage_execution.chat_user_message_id
                        )
                        result = await session.exec(stmt)
                        user_message = result.first()
                        
                        if user_message:
                            chat_user_message_id = user_message.message_id
                            chat_user_message_content = user_message.content
                            chat_user_message_author = user_message.author
                except Exception as e:
                    logger.warning(f"Failed to fetch user message for stage event: {e}")
            
            await publish_stage_started(
                session_id=stage_execution.session_id,
                stage_id=stage_execution.execution_id,
                stage_name=stage_execution.stage_name,
                chat_id=stage_execution.chat_id,
                chat_user_message_id=chat_user_message_id,
                chat_user_message_content=chat_user_message_content,
                chat_user_message_author=chat_user_message_author,
                parallel_type=stage_execution.parallel_type,
                expected_parallel_count=stage_execution.expected_parallel_count,
                parent_stage_execution_id=stage_execution.parent_stage_execution_id,
                parallel_index=stage_execution.parallel_index,
            )
        elif stage_execution.status in [
            StageStatus.COMPLETED.value, 
            StageStatus.FAILED.value, 
            StageStatus.PARTIAL.value,
            StageStatus.TIMED_OUT.value,
            StageStatus.CANCELLED.value,
        ]:
            await publish_stage_completed(
                session_id=stage_execution.session_id,
                stage_id=stage_execution.execution_id,
                stage_name=stage_execution.stage_name,
                status=stage_execution.status,
                chat_id=stage_execution.chat_id,
                parent_stage_execution_id=stage_execution.parent_stage_execution_id,
                parallel_index=stage_execution.parallel_index,
            )