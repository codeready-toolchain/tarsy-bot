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
from tarsy.models.interactions import LLMInteractionData, MCPInteractionData, MCPToolListData
from tarsy.models.history import now_us
from tarsy.services.history_service import HistoryService

logger = logging.getLogger(__name__)


class TypedLLMHistoryHook(BaseTypedHook[LLMInteractionData]):
    """
    Typed hook for logging LLM interactions to history database.
    
    Receives structured LLMInteractionData and stores it using HistoryService.
    """
    
    def __init__(self, history_service: HistoryService):
        super().__init__("typed_llm_history")
        self.history_service = history_service

    async def execute(self, interaction: LLMInteractionData) -> None:
        """
        Log LLM interaction to history database.
        
        Args:
            interaction: Typed LLM interaction data
        """
        try:
            # Direct conversion using model data - no more manual field mapping!
            self.history_service.log_llm_interaction(
                session_id=interaction.session_id,
                model_name=interaction.model_name,
                step_description=f"LLM analysis using {interaction.model_name}",
                tool_calls=interaction.tool_calls,
                tool_results=interaction.tool_results,
                token_usage=interaction.token_usage,
                duration_ms=interaction.duration_ms,
                request_json=interaction.request_json,
                response_json=interaction.response_json
            )
            
            logger.debug(f"Logged LLM interaction {interaction.request_id} to history")
            
        except Exception as e:
            logger.error(f"Failed to log LLM interaction to history: {e}")
            raise


class TypedMCPHistoryHook(BaseTypedHook[MCPInteractionData]):
    """
    Typed hook for logging MCP tool interactions to history database.
    
    Receives structured MCPInteractionData and stores it using HistoryService.
    """
    
    def __init__(self, history_service: HistoryService):
        super().__init__("typed_mcp_history")
        self.history_service = history_service

    async def execute(self, interaction: MCPInteractionData) -> None:
        """
        Log MCP interaction to history database.
        
        Args:
            interaction: Typed MCP interaction data
        """
        try:
            # Direct conversion using model data - no more manual field mapping!
            self.history_service.log_mcp_communication(
                session_id=interaction.session_id,
                server_name=interaction.server_name,
                communication_type=interaction.communication_type,
                step_description=interaction.get_step_description(),
                tool_name=interaction.tool_name,
                tool_arguments=interaction.tool_arguments,
                tool_result=interaction.tool_result,
                available_tools=interaction.available_tools,
                duration_ms=interaction.duration_ms,
                success=interaction.success,
                error_message=interaction.error_message
            )
            
            logger.debug(f"Logged MCP interaction {interaction.request_id} to history")
            
        except Exception as e:
            logger.error(f"Failed to log MCP interaction to history: {e}")
            raise


class TypedMCPListHistoryHook(BaseTypedHook[MCPToolListData]):
    """
    Typed hook for logging MCP tool list operations to history database.
    
    Receives structured MCPToolListData and stores it using HistoryService.
    """
    
    def __init__(self, history_service: HistoryService):
        super().__init__("typed_mcp_list_history")
        self.history_service = history_service

    async def execute(self, interaction: MCPToolListData) -> None:
        """
        Log MCP tool list operation to history database.
        
        Args:
            interaction: Typed MCP tool list data
        """
        try:
            # Direct conversion using model data - no more manual field mapping!
            self.history_service.log_mcp_communication(
                session_id=interaction.session_id,
                server_name=interaction.server_name or "all_servers",
                communication_type=interaction.communication_type,
                step_description=interaction.get_step_description(),
                tool_name=interaction.tool_name,
                tool_arguments=interaction.tool_arguments,
                tool_result=interaction.tool_result,
                available_tools=interaction.available_tools,
                duration_ms=interaction.duration_ms,
                success=interaction.success,
                error_message=interaction.error_message
            )
            
            logger.debug(f"Logged MCP tool list {interaction.request_id} to history")
            
        except Exception as e:
            logger.error(f"Failed to log MCP tool list to history: {e}")
            raise