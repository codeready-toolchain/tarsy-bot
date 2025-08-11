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