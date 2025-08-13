"""
Hook registry for initializing and managing typed hooks.

This module provides centralized registration of typed hooks, ensuring
proper initialization and dependency injection for the new typed hook system.
"""

import logging
from typing import Optional

from tarsy.hooks.typed_context import get_typed_hook_manager
from tarsy.hooks.typed_history_hooks import (
    TypedLLMHistoryHook,
    TypedMCPHistoryHook,
    TypedMCPListHistoryHook,
    TypedStageExecutionHistoryHook
)
from tarsy.hooks.typed_dashboard_hooks import (
    TypedLLMDashboardHook,
    TypedMCPDashboardHook,
    TypedMCPListDashboardHook,
    TypedStageExecutionDashboardHook
)
from tarsy.services.history_service import HistoryService
from tarsy.services.dashboard_broadcaster import DashboardBroadcaster

logger = logging.getLogger(__name__)


class TypedHookRegistry:
    """
    Registry for typed hooks with dependency injection.
    
    Manages initialization and registration of all typed hooks with their
    required service dependencies.
    """
    
    def __init__(self):
        self.typed_hook_manager = get_typed_hook_manager()
        self._initialized = False

    async def initialize_hooks(self, 
                             history_service: HistoryService,
                             dashboard_broadcaster: DashboardBroadcaster) -> None:
        """
        Initialize and register all typed hooks.
        
        Args:
            history_service: History service for database logging
            dashboard_broadcaster: Dashboard broadcaster for WebSocket updates
        """
        if self._initialized:
            logger.debug("Typed hooks already initialized")
            return
        
        try:
            # Initialize history hooks
            llm_history_hook = TypedLLMHistoryHook(history_service)
            mcp_history_hook = TypedMCPHistoryHook(history_service)
            mcp_list_history_hook = TypedMCPListHistoryHook(history_service)
            stage_history_hook = TypedStageExecutionHistoryHook(history_service)
            
            # Initialize dashboard hooks
            llm_dashboard_hook = TypedLLMDashboardHook(dashboard_broadcaster)
            mcp_dashboard_hook = TypedMCPDashboardHook(dashboard_broadcaster)
            mcp_list_dashboard_hook = TypedMCPListDashboardHook(dashboard_broadcaster)
            stage_dashboard_hook = TypedStageExecutionDashboardHook(dashboard_broadcaster)
            
            # Register hooks with typed hook manager
            self.typed_hook_manager.register_llm_hook(llm_history_hook)
            self.typed_hook_manager.register_llm_hook(llm_dashboard_hook)
            
            self.typed_hook_manager.register_mcp_hook(mcp_history_hook)
            self.typed_hook_manager.register_mcp_hook(mcp_dashboard_hook)
            
            self.typed_hook_manager.register_mcp_list_hook(mcp_list_history_hook)
            self.typed_hook_manager.register_mcp_list_hook(mcp_list_dashboard_hook)
            
            # Register stage execution hooks
            self.typed_hook_manager.register_stage_hook(stage_history_hook)
            self.typed_hook_manager.register_stage_hook(stage_dashboard_hook)
            
            self._initialized = True
            logger.info("Successfully initialized all typed hooks")
            
        except Exception as e:
            logger.error(f"Failed to initialize typed hooks: {e}")
            raise

    def is_initialized(self) -> bool:
        """Check if hooks have been initialized."""
        return self._initialized


# Global registry instance
_global_typed_hook_registry: Optional[TypedHookRegistry] = None

def get_typed_hook_registry() -> TypedHookRegistry:
    """Get the global typed hook registry instance."""
    global _global_typed_hook_registry
    if _global_typed_hook_registry is None:
        _global_typed_hook_registry = TypedHookRegistry()
    return _global_typed_hook_registry