"""
Typed hook context system for type-safe interaction handling.

This module provides a typed context manager system that ensures proper data flow
from service methods to hooks without contamination or type mismatches.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager, Dict, Generic, Optional, TypeVar, Union

from tarsy.models.db_models import StageExecution
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.utils.timestamp import now_us

logger = logging.getLogger(__name__)

# Type variables for generic hook context
TInteraction = TypeVar('TInteraction', LLMInteraction, MCPInteraction, StageExecution)


class BaseTypedHook(ABC, Generic[TInteraction]):
    """
    Abstract base class for typed hooks.
    
    Provides type-safe hook execution with proper error handling.
    """
    
    def __init__(self, name: str):
        self.name = name
        self.is_enabled = True
        self.error_count = 0
        self.max_errors = 5

    @abstractmethod
    async def execute(self, interaction: TInteraction) -> None:
        """
        Execute the hook logic with typed interaction data.
        
        Args:
            interaction: Typed interaction data
        """
        pass

    async def safe_execute(self, interaction: TInteraction) -> bool:
        """
        Safely execute the hook with error handling.
        
        Args:
            interaction: Typed interaction data
            
        Returns:
            True if executed successfully, False otherwise
        """
        if not self.is_enabled:
            return False
        
        try:
            await self.execute(interaction)
            self.error_count = 0
            return True
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"Typed hook '{self.name}' error ({self.error_count}/{self.max_errors}): {e}")
            
            if self.error_count >= self.max_errors:
                self.is_enabled = False
                logger.warning(f"Typed hook '{self.name}' disabled due to excessive errors")
            
            return False


class TypedHookManager:
    """
    Manages registration and execution of typed hooks.
    
    Provides centralized typed hook management with async execution
    and error isolation.
    """
    
    def __init__(self):
        self.llm_hooks: Dict[str, BaseTypedHook[LLMInteraction]] = {}
        self.mcp_hooks: Dict[str, BaseTypedHook[MCPInteraction]] = {}
        self.mcp_list_hooks: Dict[str, BaseTypedHook[MCPInteraction]] = {}
        self.stage_hooks: Dict[str, BaseTypedHook[StageExecution]] = {}

    def register_llm_hook(self, hook: BaseTypedHook[LLMInteraction]) -> None:
        """Register an LLM interaction hook."""
        self.llm_hooks[hook.name] = hook
        logger.info(f"Registered typed LLM hook: {hook.name}")

    def register_mcp_hook(self, hook: BaseTypedHook[MCPInteraction]) -> None:
        """Register an MCP interaction hook."""
        self.mcp_hooks[hook.name] = hook
        logger.info(f"Registered typed MCP hook: {hook.name}")

    def register_mcp_list_hook(self, hook: BaseTypedHook[MCPInteraction]) -> None:
        """Register an MCP tool list hook."""
        self.mcp_list_hooks[hook.name] = hook
        logger.info(f"Registered typed MCP list hook: {hook.name}")

    def register_stage_hook(self, hook: BaseTypedHook[StageExecution]) -> None:
        """Register a stage execution hook."""
        self.stage_hooks[hook.name] = hook
        logger.info(f"Registered typed stage execution hook: {hook.name}")

    async def trigger_llm_hooks(self, interaction: LLMInteraction) -> Dict[str, bool]:
        """Trigger all LLM hooks with typed data."""
        return await self._trigger_hooks(self.llm_hooks, interaction, "LLM")

    async def trigger_mcp_hooks(self, interaction: MCPInteraction) -> Dict[str, bool]:
        """Trigger all MCP hooks with typed data."""
        return await self._trigger_hooks(self.mcp_hooks, interaction, "MCP")

    async def trigger_mcp_list_hooks(self, interaction: MCPInteraction) -> Dict[str, bool]:
        """Trigger all MCP list hooks with typed data."""
        return await self._trigger_hooks(self.mcp_list_hooks, interaction, "MCP_LIST")

    async def trigger_stage_hooks(self, stage_execution: StageExecution) -> Dict[str, bool]:
        """Trigger all stage execution hooks with typed data."""
        return await self._trigger_hooks(self.stage_hooks, stage_execution, "STAGE_EXECUTION")

    async def _trigger_hooks(self, hooks: Dict[str, BaseTypedHook[TInteraction]], 
                           interaction: TInteraction, hook_type: str) -> Dict[str, bool]:
        """Generic hook triggering with type safety."""
        if not hooks:
            return {}
        
        results = {}
        start_time_us = now_us()
        
        # Execute all hooks concurrently
        tasks = []
        hook_names = []
        
        for hook_name, hook in hooks.items():
            if hook.is_enabled:
                tasks.append(hook.safe_execute(interaction))
                hook_names.append(hook_name)
        
        if tasks:
            try:
                hook_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for hook_name, result in zip(hook_names, hook_results, strict=False):
                    if isinstance(result, Exception):
                        logger.error(f"Typed {hook_type} hook '{hook_name}' raised exception: {result}")
                        results[hook_name] = False
                    else:
                        results[hook_name] = result
                
            except Exception as e:
                logger.error(f"Unexpected error executing typed {hook_type} hooks: {e}")
                for hook_name in hook_names:
                    results[hook_name] = False
        
        duration_ms = (now_us() - start_time_us) / 1000
        logger.debug(f"Triggered {len(results)} typed {hook_type} hooks in {duration_ms:.1f}ms")
        
        return results


class InteractionHookContext(Generic[TInteraction]):
    """
    Context manager for LLM/MCP interaction hook execution within stage operations.
    
    Designed specifically for interactions (LLM calls, MCP tool calls) that occur during stage execution.
    For stage-level operations (create/update stage executions), use StageExecutionHookContext instead.
    
    Provides automatic typed hook triggering with proper error handling and timing.
    Manages interaction-specific fields like start_time_us, end_time_us, duration_ms, success, etc.
    """
    
    def __init__(self, interaction_template: TInteraction, typed_hook_manager: TypedHookManager):
        """
        Initialize typed hook context.
        
        Args:
            interaction_template: Template interaction with session_id and basic info
            typed_hook_manager: Manager for typed hooks
        """
        self.interaction = interaction_template
        self.typed_hook_manager = typed_hook_manager
        self.start_time_us = None

    async def __aenter__(self) -> 'InteractionHookContext[TInteraction]':
        """Enter async context - start timing."""
        self.start_time_us = now_us()
        self.interaction.start_time_us = self.start_time_us
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context - trigger error hooks if needed."""
        end_time_us = now_us()
        self.interaction.end_time_us = end_time_us
        self.interaction.timestamp_us = end_time_us
        
        if self.start_time_us:
            self.interaction.duration_ms = int((end_time_us - self.start_time_us) / 1000)
        
        if exc_type is not None:
            # Handle errors
            self.interaction.success = False
            self.interaction.error_message = str(exc_val)
            await self._trigger_appropriate_hooks()
        
        return False  # Don't suppress exceptions

    async def complete_success(self, result_data: Union[Dict[str, Any], TInteraction]) -> None:
        """
        Complete the operation successfully and trigger hooks.
        
        Args:
            result_data: Either a dict of result data or complete interaction object
        """
        end_time_us = now_us()
        self.interaction.end_time_us = end_time_us
        self.interaction.timestamp_us = end_time_us
        
        if self.start_time_us:
            self.interaction.duration_ms = int((end_time_us - self.start_time_us) / 1000)
        
        # If result_data is a complete interaction, use it; otherwise update template
        if isinstance(result_data, type(self.interaction)):
            self.interaction = result_data
        else:
            # Update template with result data
            self._update_interaction_with_result(result_data)
        
        self.interaction.success = True
        await self._trigger_appropriate_hooks()

    def _update_interaction_with_result(self, result_data: Dict[str, Any]) -> None:
        """Update interaction template with result data."""
        # Type-specific result handling for unified models
        if isinstance(self.interaction, LLMInteraction):
            # LLM-specific result processing
            if 'response_json' in result_data:
                self.interaction.response_json = result_data['response_json']
            if 'provider' in result_data:
                self.interaction.provider = result_data['provider']
            if 'model_name' in result_data:
                self.interaction.model_name = result_data['model_name']
            if 'token_usage' in result_data:
                self.interaction.token_usage = result_data['token_usage']
                
        elif isinstance(self.interaction, MCPInteraction):
            # MCP-specific result processing
            if 'tool_result' in result_data:
                self.interaction.tool_result = result_data['tool_result']
            if 'available_tools' in result_data:
                self.interaction.available_tools = result_data['available_tools']

    async def _trigger_appropriate_hooks(self) -> None:
        """Trigger the appropriate typed hooks based on interaction type."""
        if isinstance(self.interaction, LLMInteraction):
            await self.typed_hook_manager.trigger_llm_hooks(self.interaction)
        elif isinstance(self.interaction, MCPInteraction):
            # Determine if it's a tool list or tool call based on communication_type
            if self.interaction.communication_type == "tool_list":
                await self.typed_hook_manager.trigger_mcp_list_hooks(self.interaction)
            else:
                await self.typed_hook_manager.trigger_mcp_hooks(self.interaction)
        else:
            logger.warning(f"Unknown interaction type: {type(self.interaction)}")

    def get_request_id(self) -> str:
        """Get the unique request ID for this operation."""
        return self.interaction.request_id


# Global typed hook manager instance
_global_typed_hook_manager: Optional[TypedHookManager] = None

def get_typed_hook_manager() -> TypedHookManager:
    """Get the global typed hook manager instance."""
    global _global_typed_hook_manager
    if _global_typed_hook_manager is None:
        _global_typed_hook_manager = TypedHookManager()
    return _global_typed_hook_manager


@asynccontextmanager
async def llm_interaction_context(session_id: str, request_data: Dict[str, Any], stage_execution_id: Optional[str] = None) -> AsyncContextManager[InteractionHookContext[LLMInteraction]]:
    """
    Create a typed context for LLM interactions.
    
    Args:
        session_id: Session identifier
        request_data: LLM request data
        
    Yields:
        Typed hook context for LLM interaction
    """
    interaction = LLMInteraction(
        session_id=session_id,
        stage_execution_id=stage_execution_id,
        model_name=request_data.get('model', 'unknown'),
        provider=request_data.get('provider', 'unknown'),
        request_json=request_data,
        start_time_us=now_us(),
        step_description=""  # Will be set by history service
    )
    
    async with InteractionHookContext(interaction, get_typed_hook_manager()) as ctx:
        yield ctx


@asynccontextmanager
async def mcp_interaction_context(session_id: str, server_name: str, tool_name: str, 
                                 arguments: Dict[str, Any], stage_execution_id: Optional[str] = None) -> AsyncContextManager[InteractionHookContext[MCPInteraction]]:
    """
    Create a typed context for MCP tool interactions.
    
    Args:
        session_id: Session identifier
        server_name: MCP server name
        tool_name: Tool name
        arguments: Tool arguments
        
    Yields:
        Typed hook context for MCP interaction
    """
    interaction = MCPInteraction(
        session_id=session_id,
        stage_execution_id=stage_execution_id,
        server_name=server_name,
        communication_type="tool_call",
        tool_name=tool_name,
        tool_arguments=arguments,
        start_time_us=now_us(),
        step_description=""  # Will be set by history service
    )
    
    async with InteractionHookContext(interaction, get_typed_hook_manager()) as ctx:
        yield ctx


@asynccontextmanager
async def mcp_list_context(session_id: str, server_name: Optional[str] = None, stage_execution_id: Optional[str] = None) -> AsyncContextManager[InteractionHookContext[MCPInteraction]]:
    """
    Create a typed context for MCP tool listing.
    
    Args:
        session_id: Session identifier
        server_name: Target server name (None for all servers)
        stage_execution_id: Stage execution ID for chain context
        
    Yields:
        Typed hook context for MCP tool list interaction
    """
    interaction = MCPInteraction(
        session_id=session_id,
        stage_execution_id=stage_execution_id,
        server_name=server_name or "all_servers",
        communication_type="tool_list",
        start_time_us=now_us(),
        step_description=""  # Will be set by history service
    )
    
    async with InteractionHookContext(interaction, get_typed_hook_manager()) as ctx:
        yield ctx


class StageExecutionHookContext:
    """
    Simple hook context for stage execution events.
    
    Unlike InteractionHookContext, this doesn't try to modify the StageExecution object
    which has different field names and semantics.
    """
    
    def __init__(self, stage_execution: StageExecution, typed_hook_manager: TypedHookManager):
        self.stage_execution = stage_execution
        self.typed_hook_manager = typed_hook_manager

    async def __aenter__(self) -> 'StageExecutionHookContext':
        """Enter async context."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context - trigger hooks."""
        # Always trigger stage hooks - stage execution state is managed by the service
        try:
            await self.typed_hook_manager.trigger_stage_hooks(self.stage_execution)
        except Exception as e:
            logger.error(f"Failed to trigger stage execution hooks: {e}")
        
        return False  # Don't suppress exceptions


@asynccontextmanager
async def stage_execution_context(session_id: str, stage_execution: StageExecution) -> AsyncContextManager[StageExecutionHookContext]:
    """
    Create a simple context for stage execution events.
    
    Args:
        session_id: Session identifier
        stage_execution: Stage execution data
        
    Yields:
        Simple hook context for stage execution
    """
    async with StageExecutionHookContext(stage_execution, get_typed_hook_manager()) as ctx:
        yield ctx