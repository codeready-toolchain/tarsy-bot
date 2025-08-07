"""
Custom exceptions for agent processing.

Provides a consistent exception hierarchy for better error handling,
recovery strategies, and debugging throughout the agent system.
"""

from typing import Any, Dict, Optional


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
