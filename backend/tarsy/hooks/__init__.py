"""
Typed hooks package for clean, type-safe interaction handling.

Provides typed hook infrastructure for capturing LLM interactions and MCP
communications with structured Pydantic models, ensuring data integrity
and preventing contamination between hook contexts and actual results.
"""

from .hook_context import (
    BaseHook, 
    HookManager, 
    InteractionHookContext, 
    get_hook_manager,
    llm_interaction_context,
    mcp_interaction_context,
    mcp_list_context
)
from .history_hooks import (
    LLMHistoryHook, 
    MCPHistoryHook, 
    MCPListHistoryHook,
    StageExecutionHistoryHook
)
from .event_hooks import (
    LLMEventHook, 
    MCPEventHook, 
    MCPListEventHook,
    StageExecutionEventHook
)
from .hook_registry import HookRegistry, get_hook_registry

__all__ = [
    # Core hook system
    "BaseHook",
    "HookManager", 
    "InteractionHookContext",
    "get_hook_manager",
    
    # Context managers
    "llm_interaction_context",
    "mcp_interaction_context", 
    "mcp_list_context",
    
    # Hook implementations
    "LLMHistoryHook",
    "MCPHistoryHook", 
    "MCPListHistoryHook",
    "StageExecutionHistoryHook",
    "LLMEventHook",
    "MCPEventHook",
    "MCPListEventHook",
    "StageExecutionEventHook",
    
    # Registry
    "HookRegistry",
    "get_hook_registry"
]