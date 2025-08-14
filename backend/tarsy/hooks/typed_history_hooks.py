"""
Typed history hooks for clean, type-safe interaction logging.

This module provides typed hooks that handle LLM and MCP interactions
using structured Pydantic models, ensuring data integrity and preventing
contamination between hook context and actual results.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from tarsy.hooks.typed_context import BaseTypedHook
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.models.history import StageExecution
from tarsy.services.history_service import HistoryService

logger = logging.getLogger(__name__)


class TypedLLMHistoryHook(BaseTypedHook[LLMInteraction]):
    """
    Typed hook for logging LLM interactions to history database.
    
    Receives unified LLMInteraction and stores it using HistoryService.
    """
    
    def __init__(self, history_service: HistoryService):
        super().__init__("typed_llm_history")
        self.history_service = history_service

    async def execute(self, interaction: LLMInteraction) -> None:
        """
        Log LLM interaction to history database.
        
        Args:
            interaction: Unified LLM interaction data
        """
        try:
            # Direct unified model conversion - no more parameter extraction!
            self.history_service.log_llm_interaction(interaction)
            
            logger.debug(f"Logged LLM interaction {interaction.request_id} to history")
            
        except Exception as e:
            logger.error(f"Failed to log LLM interaction to history: {e}")
            raise


class TypedMCPHistoryHook(BaseTypedHook[MCPInteraction]):
    """
    Typed hook for logging MCP tool interactions to history database.
    
    Receives unified MCPInteraction and stores it using HistoryService.
    """
    
    def __init__(self, history_service: HistoryService):
        super().__init__("typed_mcp_history")
        self.history_service = history_service

    async def execute(self, interaction: MCPInteraction) -> None:
        """
        Log MCP interaction to history database.
        
        Args:
            interaction: Unified MCP interaction data
        """
        try:
            # Direct unified model conversion - no more parameter extraction!
            self.history_service.log_mcp_interaction(interaction)
            
            logger.debug(f"Logged MCP interaction {interaction.request_id} to history")
            
        except Exception as e:
            logger.error(f"Failed to log MCP interaction to history: {e}")
            raise


class TypedMCPListHistoryHook(BaseTypedHook[MCPInteraction]):
    """
    Typed hook for logging MCP tool list operations to history database.
    
    Receives unified MCPInteraction and stores it using HistoryService.
    """
    
    def __init__(self, history_service: HistoryService):
        super().__init__("typed_mcp_list_history")
        self.history_service = history_service

    async def execute(self, interaction: MCPInteraction) -> None:
        """
        Log MCP tool list operation to history database.
        
        Args:
            interaction: Unified MCP tool list data
        """
        try:
            # Direct unified model conversion - no more parameter extraction!
            self.history_service.log_mcp_interaction(interaction)
            
            logger.debug(f"Logged MCP tool list {interaction.request_id} to history")
            
        except Exception as e:
            logger.error(f"Failed to log MCP tool list to history: {e}")
            raise


class TypedStageExecutionHistoryHook(BaseTypedHook[StageExecution]):
    """
    Typed hook for logging stage execution events to history database.
    
    Receives StageExecution and creates/updates it using HistoryService.
    """
    
    def __init__(self, history_service: HistoryService):
        super().__init__("typed_stage_history")
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
                await self.history_service.update_stage_execution(stage_execution)
                logger.debug(f"Updated stage execution {stage_execution.execution_id} in history")
                
        except Exception as e:
            logger.error(f"Failed to log stage execution to history: {e}")
            raise