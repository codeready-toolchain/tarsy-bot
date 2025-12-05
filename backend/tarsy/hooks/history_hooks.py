"""
Typed history hooks for clean, type-safe interaction logging.

This module provides typed hooks that handle LLM and MCP interactions
using structured Pydantic models, ensuring data integrity and preventing
contamination between hook context and actual results.
"""

import asyncio
import logging

from tarsy.hooks.hook_context import BaseHook, _apply_llm_interaction_truncation
from tarsy.models.db_models import StageExecution
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.services.history_service import HistoryService

logger = logging.getLogger(__name__)


class LLMHistoryHook(BaseHook[LLMInteraction]):
    """
    Typed hook for logging LLM interactions to history database.
    
    Receives unified LLMInteraction and stores it using HistoryService.
    """
    
    def __init__(self, history_service: HistoryService):
        super().__init__("llm_history")
        self.history_service = history_service

    async def execute(self, interaction: LLMInteraction) -> None:
        """Log LLM interaction to history database with content truncation."""
        try:
            # Apply content truncation before database write if needed
            truncated_interaction = _apply_llm_interaction_truncation(interaction)
            
            ok = await asyncio.to_thread(
                self.history_service.store_llm_interaction, truncated_interaction
            )
            if ok:
                logger.debug(
                    f"Stored LLM interaction {interaction.interaction_id} to history"
                )
                
                # Update last interaction timestamp for orphan detection (non-blocking)
                if interaction.session_id:
                    rec = self.history_service.record_session_interaction
                    # If async, await directly; if sync, offload to thread
                    if asyncio.iscoroutinefunction(rec):
                        await rec(interaction.session_id)
                    else:
                        await asyncio.to_thread(rec, interaction.session_id)
            else:
                logger.warning(
                    f"History service returned False for LLM interaction {interaction.interaction_id}"
                )
            
        except Exception as e:
            logger.error(f"Failed to log LLM interaction to history: {e}")
            raise


class MCPHistoryHook(BaseHook[MCPInteraction]):
    """
    Typed hook for logging MCP tool interactions to history database.
    
    Receives unified MCPInteraction and stores it using HistoryService.
    """
    
    def __init__(self, history_service: HistoryService):
        super().__init__("mcp_history")
        self.history_service = history_service

    async def execute(self, interaction: MCPInteraction) -> None:
        """
        Log MCP interaction to history database.
        
        Args:
            interaction: Unified MCP interaction data
        """
        try:
            ok = await asyncio.to_thread(
                self.history_service.store_mcp_interaction, interaction
            )
            if ok:
                logger.debug(
                    f"Stored MCP interaction {interaction.request_id} to history"
                )
                
                # Update last interaction timestamp for orphan detection (non-blocking)
                if interaction.session_id:
                    rec = self.history_service.record_session_interaction
                    # If async, await directly; if sync, offload to thread
                    if asyncio.iscoroutinefunction(rec):
                        await rec(interaction.session_id)
                    else:
                        await asyncio.to_thread(rec, interaction.session_id)
            else:
                logger.warning(
                    f"History service returned False for MCP interaction {interaction.request_id}"
                )
            
        except Exception as e:
            logger.error(f"Failed to log MCP interaction to history: {e}")
            raise


class MCPListHistoryHook(BaseHook[MCPInteraction]):
    """
    Typed hook for logging MCP tool list operations to history database.
    
    Receives unified MCPInteraction and stores it using HistoryService.
    """
    
    def __init__(self, history_service: HistoryService):
        super().__init__("mcp_list_history")
        self.history_service = history_service

    async def execute(self, interaction: MCPInteraction) -> None:
        """
        Log MCP tool list operation to history database.
        
        Args:
            interaction: Unified MCP tool list data
        """
        try:
            ok = await asyncio.to_thread(
                self.history_service.store_mcp_interaction, interaction
            )
            if ok:
                logger.debug(
                    f"Stored MCP tool list {interaction.request_id} to history"
                )
            else:
                logger.warning(
                    f"History service returned False for MCP tool list {interaction.request_id}"
                )
            
        except Exception as e:
            logger.error(f"Failed to log MCP tool list to history: {e}")
            raise


class StageExecutionHistoryHook(BaseHook[StageExecution]):
    """
    Typed hook for logging stage execution events to history database.
    
    Receives StageExecution and creates/updates it using HistoryService.
    """
    
    def __init__(self, history_service: HistoryService):
        super().__init__("stage_history")
        self.history_service = history_service

    async def execute(self, stage_execution: StageExecution) -> None:
        """
        Create or update stage execution in history database.
        
        Args:
            stage_execution: Stage execution data
        """
        try:
            # For new stage executions, we always create them first
            # The StageExecution model auto-generates execution_id, so we need to check
            # if this execution_id already exists in the database
            
            # Check if this is an initial creation (no started_at_us means it hasn't started yet)
            if stage_execution.started_at_us is None:
                # This is a new stage execution being created
                execution_id = await self.history_service.create_stage_execution(stage_execution)
                logger.debug(f"Created stage execution {execution_id} in history")
            else:
                # This is an update to an existing stage execution (has started/completed times)
                success = await self.history_service.update_stage_execution(stage_execution)
                if not success:
                    execution_id = await self.history_service.create_stage_execution(stage_execution)
                    logger.debug(f"Created (via fallback) stage execution {execution_id} in history")
                else:
                    logger.debug(f"Updated stage execution {stage_execution.execution_id} in history")
                
        except Exception as e:
            logger.error(f"Failed to log stage execution to history: {e}")
            raise