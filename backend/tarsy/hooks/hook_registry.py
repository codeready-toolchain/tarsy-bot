"""
Hook registry for initializing and managing typed hooks.

This module provides centralized registration of typed hooks, ensuring
proper initialization and dependency injection for the new typed hook system.
"""

import logging
from typing import Optional

from tarsy.hooks.hook_context import get_hook_manager
from tarsy.hooks.history_hooks import (
    LLMHistoryHook,
    MCPHistoryHook,
    MCPListHistoryHook,
    StageExecutionHistoryHook
)
from tarsy.hooks.event_hooks import (
    LLMEventHook,
    MCPEventHook,
    MCPListEventHook,
    StageExecutionEventHook
)
from tarsy.services.history_service import HistoryService

logger = logging.getLogger(__name__)


class HookRegistry:
    """
    Registry for typed hooks with dependency injection.
    
    Manages initialization and registration of all typed hooks with their
    required service dependencies.
    """
    
    def __init__(self):
        self.typed_hook_manager = get_hook_manager()
        self._initialized = False

    async def initialize_hooks(self, history_service: HistoryService) -> None:
        """
        Initialize and register all typed hooks.
        
        Args:
            history_service: History service for database logging
        """
        if self._initialized:
            logger.debug("Typed hooks already initialized")
            return
        
        try:
            # Initialize history hooks
            llm_history_hook = LLMHistoryHook(history_service)
            mcp_history_hook = MCPHistoryHook(history_service)
            mcp_list_history_hook = MCPListHistoryHook(history_service)
            stage_history_hook = StageExecutionHistoryHook(history_service)
            
            # Initialize event hooks (publish to SSE streams)
            llm_event_hook = LLMEventHook()
            mcp_event_hook = MCPEventHook()
            mcp_list_event_hook = MCPListEventHook()
            stage_event_hook = StageExecutionEventHook()
            
            # Register hooks with typed hook manager
            self.typed_hook_manager.register_llm_hook(llm_history_hook)
            self.typed_hook_manager.register_llm_hook(llm_event_hook)
            
            self.typed_hook_manager.register_mcp_hook(mcp_history_hook)
            self.typed_hook_manager.register_mcp_hook(mcp_event_hook)
            
            self.typed_hook_manager.register_mcp_list_hook(mcp_list_history_hook)
            self.typed_hook_manager.register_mcp_list_hook(mcp_list_event_hook)
            
            # Register stage execution hooks
            self.typed_hook_manager.register_stage_hook(stage_history_hook)
            self.typed_hook_manager.register_stage_hook(stage_event_hook)
            
            self._initialized = True
            logger.info("Successfully initialized all typed hooks")
            
        except Exception as e:
            logger.error(f"Failed to initialize typed hooks: {e}")
            raise

    def is_initialized(self) -> bool:
        """Check if hooks have been initialized."""
        return self._initialized


# Global registry instance
_global_hook_registry: Optional[HookRegistry] = None

def get_hook_registry() -> HookRegistry:
    """Get the global typed hook registry instance."""
    global _global_hook_registry
    if _global_hook_registry is None:
        _global_hook_registry = HookRegistry()
    return _global_hook_registry