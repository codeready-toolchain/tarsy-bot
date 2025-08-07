"""
History-specific event hooks for capturing LLM and MCP interactions.

Implements specialized hooks for logging LLM interactions and MCP communications
to the history service with microsecond-precision timestamps and human-readable
step descriptions for chronological timeline reconstruction.
"""

import logging
from typing import Any, Dict

from tarsy.services.history_service import get_history_service

from .base_hooks import BaseLLMHook, BaseMCPHook
# BaseReActHook removed - dead code cleanup

logger = logging.getLogger(__name__)


class LLMHooks(BaseLLMHook):
    """
    Event hooks for capturing LLM interactions.
    
    Captures all LLM prompts, responses, tool calls, and performance metrics
    with microsecond-precision timestamps for exact chronological ordering.
    """
    
    def __init__(self):
        """Initialize LLM history hooks."""
        super().__init__("llm_history_hook")
        self.history_service = get_history_service()
    
    async def process_llm_interaction(self, session_id: str, interaction_data: Dict[str, Any]) -> None:
        """
        Process LLM interaction by logging to history service.
        
        Args:
            session_id: Session identifier
            interaction_data: Processed interaction data from base class
        """
        # Log the interaction to history service
        success = self.history_service.log_llm_interaction(
            session_id=session_id,
            prompt_text=interaction_data["prompt_text"][:10000000],  # Limit to 10MB - SQLite supports up to 1GB
            response_text=interaction_data["response_text"][:10000000],  # Always has content (success or error message)
            model_used=interaction_data["model_used"],
            step_description=interaction_data["step_description"],
            tool_calls=interaction_data["tool_calls"],
            tool_results=interaction_data["tool_results"],
            token_usage=interaction_data["token_usage"],
            duration_ms=interaction_data["duration_ms"]
        )
        
        if success:
            logger.debug(f"Logged LLM interaction for session {session_id}: {interaction_data['step_description']}")
        else:
            logger.warning(f"Failed to log LLM interaction for session {session_id}")


class MCPHooks(BaseMCPHook):
    """
    Event hooks for capturing MCP communications.
    
    Captures tool discovery, invocations, and results with microsecond-precision
    timestamps to maintain exact chronological ordering with LLM interactions.
    """
    
    def __init__(self):
        """Initialize MCP history hooks."""
        super().__init__("mcp_history_hook")
        self.history_service = get_history_service()
    
    async def process_mcp_communication(self, session_id: str, communication_data: Dict[str, Any]) -> None:
        """
        Process MCP communication by logging to history service.
        
        Args:
            session_id: Session identifier
            communication_data: Processed communication data from base class
        """
        # Log the communication to history service
        log_success = self.history_service.log_mcp_communication(
            session_id=session_id,
            server_name=communication_data["server_name"],
            communication_type=communication_data["communication_type"],
            step_description=communication_data["step_description"],
            success=communication_data["success"],
            duration_ms=communication_data["duration_ms"],
            tool_name=communication_data["tool_name"],
            tool_arguments=communication_data["tool_arguments"],
            tool_result=communication_data["tool_result"],
            available_tools=communication_data["available_tools"],
            error_message=communication_data["error_message"]
        )
        
        if log_success:
            logger.debug(f"Logged MCP communication for session {session_id}: {communication_data['step_description']}")
        else:
            logger.warning(f"Failed to log MCP communication for session {session_id}")


class ReActHooks:
    """
    ReAct reasoning hooks for history logging.
    
    Captures ReAct reasoning steps and iterations, logging them to the history service
    for complete audit trails and analytics.
    """
    
    def __init__(self):
        """Initialize ReAct history hooks."""
        super().__init__("react_history_hook")
        self.history_service = get_history_service()
    
    async def process_react_reasoning(self, session_id: str, reasoning_data: Dict[str, Any]) -> None:
        """
        Process ReAct reasoning by logging to history service.
        
        Args:
            session_id: Session identifier
            reasoning_data: Processed reasoning data from base class
        """
        if not self.history_service or not self.history_service.enabled:
            logger.debug(f"History service unavailable for ReAct reasoning in session {session_id}")
            return
        
        try:
            event_type = reasoning_data.get("event_type")
            
            if event_type == "reasoning_step":
                # ReAct step logging removed - dead code cleanup
                logger.debug(f"ReAct reasoning step event ignored - simplified implementation")
            
            elif event_type == "iteration_complete":
                # ReAct iteration processing removed - dead code cleanup
                logger.debug(f"ReAct iteration complete event ignored - simplified implementation")
        
        except Exception as e:
            logger.error(f"Error processing ReAct reasoning for session {session_id}: {str(e)}")


def register_history_hooks():
    """
    Register history hooks with the global hook manager.
    
    This function should be called during application startup to enable
    automatic history capture for LLM and MCP interactions.
    """
    from .base_hooks import get_hook_manager
    
    hook_manager = get_hook_manager()
    
    # Register LLM hooks
    llm_hooks = LLMHooks()
    hook_manager.register_hook("llm.post", llm_hooks)
    hook_manager.register_hook("llm.error", llm_hooks)
    
    # Register MCP hooks  
    mcp_hooks = MCPHooks()
    hook_manager.register_hook("mcp.post", mcp_hooks)
    hook_manager.register_hook("mcp.error", mcp_hooks)
    
    # ReAct hooks removed - dead code cleanup
    
    logger.info("History hooks registered successfully (LLM, MCP)")
    return hook_manager 