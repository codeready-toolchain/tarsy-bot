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

from tarsy.models.constants import (
    MAX_LLM_MESSAGE_CONTENT_SIZE,
    MAX_MCP_TOOL_RESULT_SIZE,
    LLMInteractionType,
)
from tarsy.models.db_models import StageExecution
from tarsy.models.unified_interactions import (
    LLMInteraction,
    MCPInteraction,
    MessageRole,
)
from tarsy.utils.timestamp import now_us

logger = logging.getLogger(__name__)

# Export public API - truncation utilities are used by history hooks
__all__ = [
    '_apply_llm_interaction_truncation',
    'BaseHook',
    'TypedHookContext',
    'llm_interaction_context',
    'mcp_interaction_context',
    'stage_execution_context',
]

# Type variables for generic hook context
TInteraction = TypeVar('TInteraction', LLMInteraction, MCPInteraction, StageExecution)

# Note: TypedHookContext forward declaration for __all__ compatibility
# The actual class is defined below as InteractionHookContext
TypedHookContext = None  # Will be set after InteractionHookContext definition


def _apply_llm_interaction_truncation(interaction: LLMInteraction) -> LLMInteraction:
    """Apply content truncation to LLM interaction for hook processing."""
    if not interaction.conversation:
        return interaction
        
    truncated_conversation = interaction.conversation.model_copy(deep=True)
    truncation_applied = False
    
    for message in truncated_conversation.messages:
        # Only truncate user messages for hook processing
        if (message.role == MessageRole.USER and 
            len(message.content) > MAX_LLM_MESSAGE_CONTENT_SIZE):
            
            original_size = len(message.content)
            message.content = (
                message.content[:MAX_LLM_MESSAGE_CONTENT_SIZE] + 
                f"\n\n[HOOK TRUNCATED - Original size: {original_size:,} chars, "
                f"Hook size: {MAX_LLM_MESSAGE_CONTENT_SIZE:,} chars]"
            )
            truncation_applied = True
    
    if truncation_applied:
        # Create new interaction with truncated conversation
        truncated_interaction = interaction.model_copy()
        truncated_interaction.conversation = truncated_conversation
        return truncated_interaction
    
    return interaction


class BaseHook(ABC, Generic[TInteraction]):
    """
    Abstract base class for hooks.
    
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
            logger.error(f"Hook '{self.name}' error ({self.error_count}/{self.max_errors}): {e}")
            
            if self.error_count >= self.max_errors:
                self.is_enabled = False
                logger.warning(f"Hook '{self.name}' disabled due to excessive errors")
            
            return False


class HookManager:
    """
    Manages registration and execution of hooks.
    
    Provides centralized hook management with async execution
    and error isolation.
    """
    
    def __init__(self):
        self.llm_hooks: Dict[str, BaseHook[LLMInteraction]] = {}
        self.mcp_hooks: Dict[str, BaseHook[MCPInteraction]] = {}
        self.mcp_list_hooks: Dict[str, BaseHook[MCPInteraction]] = {}
        self.stage_hooks: Dict[str, BaseHook[StageExecution]] = {}

    def register_llm_hook(self, hook: BaseHook[LLMInteraction]) -> None:
        """Register an LLM interaction hook."""
        self.llm_hooks[hook.name] = hook
        logger.info(f"Registered typed LLM hook: {hook.name}")

    def register_mcp_hook(self, hook: BaseHook[MCPInteraction]) -> None:
        """Register an MCP interaction hook."""
        self.mcp_hooks[hook.name] = hook
        logger.info(f"Registered typed MCP hook: {hook.name}")

    def register_mcp_list_hook(self, hook: BaseHook[MCPInteraction]) -> None:
        """Register an MCP tool list hook."""
        self.mcp_list_hooks[hook.name] = hook
        logger.info(f"Registered typed MCP list hook: {hook.name}")

    def register_stage_hook(self, hook: BaseHook[StageExecution]) -> None:
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
        """
        Trigger all stage execution hooks with typed data.
        
        Unlike other hooks, stage execution hooks use stricter error handling because
        stage creation/updates are critical operations that must succeed.
        """
        return await self._trigger_hooks(
            self.stage_hooks, 
            stage_execution, 
            "STAGE_EXECUTION",
            allow_exceptions=True  # Let exceptions propagate for critical stage operations
        )

    async def _trigger_hooks(self, hooks: Dict[str, BaseHook[TInteraction]], 
                           interaction: TInteraction, hook_type: str,
                           allow_exceptions: bool = False) -> Dict[str, bool]:
        """
        Generic hook triggering with type safety.
        
        Args:
            hooks: Dictionary of hooks to execute
            interaction: Interaction data to pass to hooks
            hook_type: Type of hook for logging
            allow_exceptions: If True, let exceptions propagate instead of catching them.
                            Use for critical operations like stage execution creation.
        """
        if not hooks:
            return {}
        
        results = {}
        start_time_us = now_us()
        
        # Execute all hooks concurrently
        tasks = []
        hook_names = []
        
        for hook_name, hook in hooks.items():
            if hook.is_enabled:
                # For critical hooks, call execute() directly to propagate exceptions
                # For non-critical hooks, use safe_execute() to catch and log errors
                if allow_exceptions:
                    tasks.append(hook.execute(interaction))
                else:
                    tasks.append(hook.safe_execute(interaction))
                hook_names.append(hook_name)
        
        if tasks:
            try:
                # For critical hooks, don't catch exceptions - let them propagate
                if allow_exceptions:
                    await asyncio.gather(*tasks)
                    # All hooks succeeded if we reach here (exceptions would have propagated)
                    for hook_name in hook_names:
                        results[hook_name] = True
                else:
                    # For non-critical hooks, catch exceptions and log them
                    hook_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for hook_name, result in zip(hook_names, hook_results, strict=False):
                        if isinstance(result, Exception):
                            logger.error(f"Typed {hook_type} hook '{hook_name}' raised exception: {result}")
                            results[hook_name] = False
                        else:
                            results[hook_name] = result
                
            except Exception as e:
                # Only reached for critical hooks with allow_exceptions=True
                logger.error(f"CRITICAL: {hook_type} hook failed: {e}", exc_info=True)
                # Re-raise to propagate critical failures
                raise
        
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
    
    def __init__(self, interaction_template: TInteraction, hook_manager: HookManager):
        """
        Initialize typed hook context.
        
        Args:
            interaction_template: Template interaction with session_id and basic info
            hook_manager: Manager for hooks
        """
        self.interaction = interaction_template
        self.hook_manager = hook_manager
        self.start_time_us = None

    async def __aenter__(self) -> 'InteractionHookContext[TInteraction]':
        """Enter async context - start timing."""
        self.start_time_us = now_us()
        # Only set start_time_us if the interaction model has this field (for runtime-only fields)
        if hasattr(self.interaction, 'start_time_us'):
            self.interaction.start_time_us = self.start_time_us
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context - trigger error hooks if needed."""
        end_time_us = now_us()
        # Only set end_time_us if the interaction model has this field (for runtime-only fields)
        if hasattr(self.interaction, 'end_time_us'):
            self.interaction.end_time_us = end_time_us
        self.interaction.timestamp_us = end_time_us
        
        if self.start_time_us:
            self.interaction.duration_ms = int((end_time_us - self.start_time_us) / 1000)
        
        if exc_type is not None:
            # Handle errors
            self.interaction.success = False
            # CancelledError has empty str() but reason in args[0] - use existing utility
            if isinstance(exc_val, asyncio.CancelledError):
                from tarsy.utils.agent_execution_utils import extract_cancellation_reason
                reason = extract_cancellation_reason(exc_val)
                self.interaction.error_message = f"Operation cancelled ({reason})"
            else:
                self.interaction.error_message = str(exc_val) or type(exc_val).__name__
            await self._trigger_appropriate_hooks()
        
        return False  # Don't suppress exceptions

    async def complete_success(self, result_data: Union[Dict[str, Any], TInteraction]) -> None:
        """
        Complete the operation successfully and trigger hooks.
        
        Args:
            result_data: Either a dict of result data or complete interaction object
        """
        end_time_us = now_us()
        # Only set end_time_us if the interaction model has this field (for runtime-only fields)
        if hasattr(self.interaction, 'end_time_us'):
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
        
        # Apply truncation to MCP interactions BEFORE distributing to hooks
        # This ensures ALL hooks (history, event, etc.) see the same truncated data
        if isinstance(self.interaction, MCPInteraction):
            self._apply_mcp_truncation_inplace()
        
        self.interaction.success = True
        await self._trigger_appropriate_hooks()

    def _update_interaction_with_result(self, result_data: Dict[str, Any]) -> None:
        """Update interaction template with result data."""
        # Type-specific result handling for unified models
        if isinstance(self.interaction, LLMInteraction):
            # LLM-specific result processing
            if 'provider' in result_data:
                self.interaction.provider = result_data['provider']
            if 'model_name' in result_data:
                self.interaction.model_name = result_data['model_name']
                
        elif isinstance(self.interaction, MCPInteraction):
            # MCP-specific result processing
            if 'tool_result' in result_data:
                self.interaction.tool_result = result_data['tool_result']
            if 'available_tools' in result_data:
                self.interaction.available_tools = result_data['available_tools']
    
    def _apply_mcp_truncation_inplace(self) -> None:
        """
        Apply content truncation to MCP tool results in-place.
        
        Truncates large tool_result content while preserving all metadata keys.
        This modifies the interaction's tool_result dict to create a NEW dict
        with preserved keys, avoiding cross-hook contamination issues.
        """
        import json
        
        # Check and truncate tool_result if needed
        if not self.interaction.tool_result:
            return
        
        # Handle dict with "result" key
        if isinstance(self.interaction.tool_result, dict) and "result" in self.interaction.tool_result:
            content = self.interaction.tool_result["result"]
            
            # Case 1: String result - truncate directly (fast path)
            if isinstance(content, str):
                if len(content) > MAX_MCP_TOOL_RESULT_SIZE:
                    original_size = len(content)
                    truncated_content = content[:MAX_MCP_TOOL_RESULT_SIZE]
                    last_newline = truncated_content.rfind('\n')
                    if last_newline > 0:
                        truncated_content = truncated_content[:last_newline]
                    
                    truncated_content += (
                        f"\n\n... [TRUNCATED - Original size: {original_size//1024}KB, "
                        f"limit: {MAX_MCP_TOOL_RESULT_SIZE//1024}KB]"
                    )
                    
                    # Create new dict preserving all existing keys, only update "result"
                    self.interaction.tool_result = {**self.interaction.tool_result, "result": truncated_content}
                    logger.info(
                        f"Truncated MCP tool_result from {original_size:,} bytes "
                        f"for {self.interaction.tool_name or 'tool_list'}"
                    )
            
            # Case 2: Non-string result - serialize just the result value
            else:
                result_str = json.dumps(content, indent=2, default=str)
                if len(result_str) > MAX_MCP_TOOL_RESULT_SIZE:
                    original_size = len(result_str)
                    truncated_str = result_str[:MAX_MCP_TOOL_RESULT_SIZE]
                    last_newline = truncated_str.rfind('\n')
                    if last_newline > 0:
                        truncated_str = truncated_str[:last_newline]
                    
                    truncated_str += (
                        f"\n\n... [TRUNCATED - Original size: {original_size//1024}KB, "
                        f"limit: {MAX_MCP_TOOL_RESULT_SIZE//1024}KB]"
                    )
                    
                    # Create new dict preserving all existing keys, replace "result" with serialized string
                    self.interaction.tool_result = {**self.interaction.tool_result, "result": truncated_str}
                    logger.info(
                        f"Truncated MCP tool_result from {original_size:,} bytes "
                        f"for {self.interaction.tool_name or 'tool_list'}"
                    )
        
        # Case 3: No "result" key or not a dict - serialize entire structure
        else:
            result_str = json.dumps(self.interaction.tool_result, indent=2, default=str)
            if len(result_str) > MAX_MCP_TOOL_RESULT_SIZE:
                original_size = len(result_str)
                
                # Truncate the serialized version
                truncated_str = result_str[:MAX_MCP_TOOL_RESULT_SIZE]
                last_newline = truncated_str.rfind('\n')
                if last_newline > 0:
                    truncated_str = truncated_str[:last_newline]
                
                truncated_str += (
                    f"\n\n... [TRUNCATED - Original size: {original_size//1024}KB, "
                    f"limit: {MAX_MCP_TOOL_RESULT_SIZE//1024}KB]"
                )
                
                # Replace entire tool_result with serialized truncated version as "result" key
                self.interaction.tool_result = {"result": truncated_str}
                
                logger.info(
                    f"Truncated MCP tool_result from {original_size:,} bytes "
                    f"for {self.interaction.tool_name or 'tool_list'}"
                )

    async def _trigger_appropriate_hooks(self) -> None:
        """Trigger the appropriate typed hooks based on interaction type."""
        if isinstance(self.interaction, LLMInteraction):
            await self.hook_manager.trigger_llm_hooks(self.interaction)
        elif isinstance(self.interaction, MCPInteraction):
            # Determine if it's a tool list or tool call based on communication_type
            if self.interaction.communication_type == "tool_list":
                await self.hook_manager.trigger_mcp_list_hooks(self.interaction)
            else:
                await self.hook_manager.trigger_mcp_hooks(self.interaction)
        else:
            logger.warning(f"Unknown interaction type: {type(self.interaction)}")

    def get_request_id(self) -> str:
        """Get the unique request ID for this operation."""
        # LLMInteraction uses interaction_id, MCPInteraction uses request_id
        if hasattr(self.interaction, 'request_id'):
            return self.interaction.request_id
        elif hasattr(self.interaction, 'interaction_id'):
            return self.interaction.interaction_id
        else:
            return f"unknown_{id(self.interaction)}"


# API alias for backward compatibility
TypedHookContext = InteractionHookContext


# Global hook manager instance
_global_hook_manager: Optional[HookManager] = None

def get_hook_manager() -> HookManager:
    """Get the global hook manager instance."""
    global _global_hook_manager
    if _global_hook_manager is None:
        _global_hook_manager = HookManager()
    return _global_hook_manager


@asynccontextmanager
async def llm_interaction_context(
    session_id: str, 
    request_data: Dict[str, Any], 
    stage_execution_id: Optional[str] = None,
    native_tools_config: Optional[Dict[str, bool]] = None
) -> AsyncContextManager[InteractionHookContext[LLMInteraction]]:
    """
    Create a typed context for LLM interactions.
    
    Args:
        session_id: Session identifier
        request_data: LLM request data
        stage_execution_id: Optional stage execution ID
        native_tools_config: Optional native tools configuration (Google/Gemini only)
        
    Yields:
        Typed hook context for LLM interaction
    """
    interaction = LLMInteraction(
        session_id=session_id,
        stage_execution_id=stage_execution_id,
        model_name=request_data.get('model', 'unknown'),
        provider=request_data.get('provider', 'unknown'),
        temperature=request_data.get('temperature'),
        interaction_type=LLMInteractionType.INVESTIGATION.value,
        native_tools_config=native_tools_config
        # Note: conversation will be set by LLMClient after successful response
        # Note: interaction_type may be updated by LLMClient based on response content
    )
    
    async with InteractionHookContext(interaction, get_hook_manager()) as ctx:
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
    
    async with InteractionHookContext(interaction, get_hook_manager()) as ctx:
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
    
    async with InteractionHookContext(interaction, get_hook_manager()) as ctx:
        yield ctx


class StageExecutionHookContext:
    """
    Simple hook context for stage execution events.
    
    Unlike InteractionHookContext, this doesn't try to modify the StageExecution object
    which has different field names and semantics.
    """
    
    def __init__(
        self,
        stage_execution: StageExecution,
        hook_manager: HookManager,
        allow_exceptions: bool = True,
    ):
        """
        Initialize stage execution hook context.
        
        Args:
            stage_execution: Stage execution data
            hook_manager: Manager for hooks
            allow_exceptions: If True, let hook exceptions propagate instead of suppressing.
                            Stage execution hooks are critical operations, so defaults to True.
        """
        self.stage_execution = stage_execution
        self.hook_manager = hook_manager
        self.allow_exceptions = allow_exceptions

    async def __aenter__(self) -> 'StageExecutionHookContext':
        """Enter async context."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context - trigger hooks."""
        # Always trigger stage hooks - stage execution state is managed by the service
        try:
            await self.hook_manager.trigger_stage_hooks(self.stage_execution)
        except Exception as e:
            logger.error(f"Failed to trigger stage execution hooks: {e}")
            if self.allow_exceptions:
                raise
        
        return False  # Don't suppress exceptions from the context body


@asynccontextmanager
async def stage_execution_context(
    stage_execution: StageExecution,
    allow_exceptions: bool = True,
) -> AsyncContextManager[StageExecutionHookContext]:
    """
    Create a simple context for stage execution events.
    
    Args:
        stage_execution: Stage execution data
        allow_exceptions: If True, let hook exceptions propagate.
                         Stage execution hooks are critical, so defaults to True.
        
    Yields:
        Simple hook context for stage execution
    """
    async with StageExecutionHookContext(
        stage_execution, get_hook_manager(), allow_exceptions=allow_exceptions
    ) as ctx:
        yield ctx