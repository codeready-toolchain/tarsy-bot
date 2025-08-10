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
            # Create LLM interaction record using existing API
            self.history_service.log_llm_interaction(
                session_id=interaction.session_id,
                model_used=interaction.model_name,
                step_description=f"LLM analysis using {interaction.model_name}",
                tool_calls=None,  # TODO: Extract from response if needed
                tool_results=None,  # TODO: Extract from response if needed
                token_usage=(
                    {
                        "prompt_tokens": interaction.response.usage.prompt_tokens,
                        "completion_tokens": interaction.response.usage.completion_tokens,
                        "total_tokens": interaction.response.usage.total_tokens
                    } if interaction.response and interaction.response.usage else None
                ),
                duration_ms=interaction.duration_ms,
                request_json={
                    "model": interaction.request.model,
                    "messages": [
                        {"role": msg.role, "content": msg.content} 
                        for msg in interaction.request.messages
                    ],
                    "temperature": interaction.request.temperature
                },
                response_json={
                    "choices": [
                        {
                            "message": {
                                "role": choice.message.role,
                                "content": choice.message.content
                            },
                            "finish_reason": choice.finish_reason
                        }
                        for choice in (interaction.response.choices if interaction.response else [])
                    ],
                    "model": interaction.response.model if interaction.response else None,
                    "usage": (
                        {
                            "prompt_tokens": interaction.response.usage.prompt_tokens,
                            "completion_tokens": interaction.response.usage.completion_tokens,
                            "total_tokens": interaction.response.usage.total_tokens
                        } if interaction.response and interaction.response.usage else None
                    )
                } if interaction.response else None
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
            # Create MCP communication record
            self.history_service.log_mcp_communication(
                session_id=interaction.session_id,
                server_name=interaction.tool_call.server_name,
                communication_type=interaction.communication_type,
                step_description=interaction.get_step_description(),
                tool_name=interaction.tool_call.tool_name,
                tool_arguments=interaction.tool_call.arguments,
                tool_result=(
                    interaction.tool_result.result if interaction.tool_result else None
                ),
                available_tools=None,  # Not applicable for tool calls
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
            # Create MCP communication record for tool listing
            self.history_service.log_mcp_communication(
                session_id=interaction.session_id,
                server_name=interaction.server_name or "all_servers",
                communication_type=interaction.communication_type,
                step_description=interaction.get_step_description(),
                tool_name=None,  # Not applicable for tool listing
                tool_arguments=None,  # Not applicable for tool listing
                tool_result=None,  # Not applicable for tool listing
                available_tools=(
                    interaction.result.tools if interaction.result else None
                ),
                duration_ms=interaction.duration_ms,
                success=interaction.success,
                error_message=interaction.error_message
            )
            
            logger.debug(f"Logged MCP tool list {interaction.request_id} to history")
            
        except Exception as e:
            logger.error(f"Failed to log MCP tool list to history: {e}")
            raise