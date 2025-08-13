"""
Typed hooks package for clean, type-safe interaction handling.

Provides typed hook infrastructure for capturing LLM interactions and MCP
communications with structured Pydantic models, ensuring data integrity
and preventing contamination between hook contexts and actual results.
"""

from .typed_context import (
    BaseTypedHook, 
    TypedHookManager, 
    InteractionHookContext, 
    get_typed_hook_manager,
    llm_interaction_context,
    mcp_interaction_context,
    mcp_list_context
)
from .typed_history_hooks import (
    TypedLLMHistoryHook, 
    TypedMCPHistoryHook, 
    TypedMCPListHistoryHook
)
from .typed_dashboard_hooks import (
    TypedLLMDashboardHook, 
    TypedMCPDashboardHook, 
    TypedMCPListDashboardHook
)
from .hook_registry import TypedHookRegistry, get_typed_hook_registry

__all__ = [
    # Core typed hook system
    "BaseTypedHook",
    "TypedHookManager", 
    "InteractionHookContext",
    "get_typed_hook_manager",
    
    # Context managers
    "llm_interaction_context",
    "mcp_interaction_context", 
    "mcp_list_context",
    
    # Typed hook implementations
    "TypedLLMHistoryHook",
    "TypedMCPHistoryHook", 
    "TypedMCPListHistoryHook",
    "TypedLLMDashboardHook",
    "TypedMCPDashboardHook",
    "TypedMCPListDashboardHook",
    
    # Registry
    "TypedHookRegistry",
    "get_typed_hook_registry"
]