"""
Custom exceptions for agent processing.

Provides a consistent exception hierarchy for better error handling,
recovery strategies, and debugging throughout the agent system.
"""

from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from tarsy.models.unified_interactions import LLMConversation


class AgentError(Exception):
    """
    Base exception for all agent-related errors.
    
    Provides common error attributes and recovery guidance.
    """
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None, recoverable: bool = True):
        """
        Initialize agent error.
        
        Args:
            message: Human-readable error description
            context: Additional context data for debugging
            recoverable: Whether this error allows for graceful recovery
        """
        super().__init__(message)
        self.context = context or {}
        self.recoverable = recoverable
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging/serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "context": self.context,
            "recoverable": self.recoverable
        }


class ToolSelectionError(AgentError):
    """
    Error during MCP tool selection.
    
    Usually recoverable by providing error info to LLM for analysis.
    """
    
    def __init__(self, message: str, response: str = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, context, recoverable=True)
        self.llm_response = response
        
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result["llm_response"] = self.llm_response
        return result


class ToolExecutionError(AgentError):
    """
    Error during MCP tool execution.
    
    Usually recoverable by including error in results for LLM analysis.
    """
    
    def __init__(self, message: str, tool_name: str = None, server_name: str = None, 
                 context: Optional[Dict[str, Any]] = None):
        super().__init__(message, context, recoverable=True)
        self.tool_name = tool_name
        self.server_name = server_name
        
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result.update({
            "tool_name": self.tool_name,
            "server_name": self.server_name
        })
        return result


class MCPServerSelectionError(AgentError):
    """
    Error when user-selected MCP servers don't exist or aren't available.
    
    Non-recoverable as it represents invalid user input for MCP selection.
    """
    
    def __init__(self, message: str, requested_servers: list = None, 
                 available_servers: list = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, context, recoverable=False)
        self.requested_servers = requested_servers or []
        self.available_servers = available_servers or []
        
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result.update({
            "requested_servers": self.requested_servers,
            "available_servers": self.available_servers
        })
        return result


class MCPToolSelectionError(AgentError):
    """
    Error when user-selected tools don't exist on the specified MCP server.
    
    Non-recoverable as it represents invalid user input for tool selection.
    """
    
    def __init__(self, message: str, server_name: str = None, requested_tools: list = None,
                 available_tools: list = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, context, recoverable=False)
        self.server_name = server_name
        self.requested_tools = requested_tools or []
        self.available_tools = available_tools or []
        
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result.update({
            "server_name": self.server_name,
            "requested_tools": self.requested_tools,
            "available_tools": self.available_tools
        })
        return result



class ConfigurationError(AgentError):
    """
    Error in agent configuration or setup.
    
    Non-recoverable as it represents a system configuration issue.
    """
    
    def __init__(self, message: str, missing_config: str = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, context, recoverable=False)
        self.missing_config = missing_config
        
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result["missing_config"] = self.missing_config
        return result


class MaxIterationsFailureError(AgentError):
    """
    Error when max iterations is reached and the last interaction failed.
    
    Non-recoverable as it indicates stage failure condition.
    """
    
    def __init__(self, message: str, max_iterations: int, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, context, recoverable=False)
        self.max_iterations = max_iterations
        
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result["max_iterations"] = self.max_iterations
        return result


class SessionPaused(AgentError):
    """
    Control flow signal when session is paused at max iterations.
    
    Not an error condition, but a normal pause state that requires user action to resume.
    Recoverable as processing can continue after resume.
    """
    
    def __init__(
        self, 
        message: str, 
        iteration: int, 
        conversation: Optional['LLMConversation'] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, context, recoverable=True)
        self.iteration = iteration
        self.conversation = conversation  # Full conversation history for resume
        
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result["iteration"] = self.iteration
        # Don't include conversation in to_dict - it's for internal use only
        return result


class ForceConclusion(AgentError):
    """
    Signal to force LLM conclusion at max iterations.
    
    Used when max iterations reached and system should force conclusion
    instead of pausing. Not an error condition but a control flow signal.
    """
    
    def __init__(
        self, 
        iteration: int, 
        conversation: Optional['LLMConversation'] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__("Max iterations reached, forcing conclusion", context, recoverable=True)
        self.iteration = iteration
        self.conversation = conversation
        
    def to_dict(self) -> Dict[str, Any]:
        result = super().to_dict()
        result["iteration"] = self.iteration
        # Don't include conversation in to_dict - it's for internal use only
        return result


# Recovery strategies
class ErrorRecoveryHandler:
    """
    Handler for consistent error recovery across agent operations.
    """
    

    
    @staticmethod
    def handle_tool_execution_error(error: ToolExecutionError) -> Dict[str, Any]:
        """
        Handle tool execution errors by creating error result for LLM analysis.
        
        Args:
            error: The tool execution error
            
        Returns:
            Error result structure for inclusion in MCP data
        """
        return {
            "tool": error.tool_name or "unknown",
            "server": error.server_name or "unknown",
            "error": str(error),
            "error_type": "tool_execution_failure",
            "message": "Tool execution failed but analysis can continue with this error information"
        }
