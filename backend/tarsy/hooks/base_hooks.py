"""
Base event hook infrastructure for transparent service integration.

Provides the foundation for event hooks that capture data from existing services
without modifying their core logic, with comprehensive error handling to prevent
hooks from breaking parent operations.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

import asyncio
import functools
import inspect
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from tarsy.models.history import now_us

logger = logging.getLogger(__name__)


class HookContext:
    """
    Context manager for handling hook lifecycle with automatic timing and error handling.
    
    Eliminates code duplication in service integrations by providing a standardized
    way to handle pre/post/error hooks with timing and context management.
    """
    
    def __init__(self, service_type: str, method_name: str, session_id: Optional[str] = None, **method_args):
        """
        Initialize hook context.
        
        Args:
            service_type: Type of service (e.g., 'llm', 'mcp')
            method_name: Name of the method being hooked
            session_id: Session ID for history tracking
            **method_args: Method arguments to include in context
        """
        self.service_type = service_type
        self.method_name = method_name
        self.session_id = session_id
        self.method_args = method_args
        
        # Generate unique request ID and timing
        self.request_id = str(uuid.uuid4())[:8]
        self.start_time_us: Optional[int] = None
        self.end_time_us: Optional[int] = None
        
        # Hook context and manager
        self.hook_context: Dict[str, Any] = {}
        self.hook_manager: Optional[HookManager] = None
        
    async def __aenter__(self) -> 'HookContext':
        """Enter the hook context and trigger pre-execution hooks."""
        self.start_time_us = now_us()
        self.hook_manager = get_hook_manager()
        
        # Prepare hook context for pre-execution
        self.hook_context = {
            'session_id': self.session_id,
            'method': self.method_name,
            'args': {
                'request_id': self.request_id,
                **self.method_args
            },
            'start_time_us': self.start_time_us,
            'timestamp_us': self.start_time_us
        }
        
        # Trigger pre-execution hooks
        await self.hook_manager.trigger_hooks(f"{self.service_type}.pre", **self.hook_context)
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the hook context and trigger post/error hooks based on outcome."""
        self.end_time_us = now_us()
        
        if exc_type is None:
            # Success case - will be updated with result via complete_success()
            pass
        else:
            # Error case - trigger error hooks
            self.hook_context.update({
                'error': str(exc_val) if exc_val else 'Unknown error',
                'end_time_us': self.end_time_us,
                'success': False
            })
            
            if self.hook_manager:
                await self.hook_manager.trigger_hooks(f"{self.service_type}.error", **self.hook_context)
        
        # Don't suppress exceptions
        return False
    
    async def complete_success(self, result: Any) -> None:
        """
        Mark the operation as successful and trigger post-execution hooks.
        
        Args:
            result: The result of the operation
        """
        if not self.end_time_us:
            self.end_time_us = now_us()
            
        self.hook_context.update({
            'result': result,
            'end_time_us': self.end_time_us,
            'success': True
        })
        
        if self.hook_manager:
            await self.hook_manager.trigger_hooks(f"{self.service_type}.post", **self.hook_context)
    
    def get_request_id(self) -> str:
        """Get the generated request ID for logging purposes."""
        return self.request_id

class BaseEventHook(ABC):
    """
    Abstract base class for event hooks.
    
    Provides the foundation for all event hooks with error handling,
    async support, and registration management.
    """
    
    def __init__(self, name: str):
        """
        Initialize base event hook.
        
        Args:
            name: Unique name for this hook
        """
        self.name = name
        self.is_enabled = True
        self.error_count = 0
        self.max_errors = 5  # Disable hook after 5 consecutive errors
    
    @abstractmethod
    async def execute(self, event_type: str, **kwargs) -> None:
        """
        Execute the hook logic.
        
        Args:
            event_type: Type of event being hooked
            **kwargs: Event-specific data
        """
        pass
    
    def enable(self) -> None:
        """Enable this hook."""
        self.is_enabled = True
        self.error_count = 0
        logger.info(f"Hook '{self.name}' enabled")
    
    def disable(self) -> None:
        """Disable this hook."""
        self.is_enabled = False
        logger.info(f"Hook '{self.name}' disabled")
    
    async def safe_execute(self, event_type: str, **kwargs) -> bool:
        """
        Safely execute the hook with error handling.
        
        Args:
            event_type: Type of event being hooked
            **kwargs: Event-specific data
            
        Returns:
            True if executed successfully, False otherwise
        """
        if not self.is_enabled:
            return False
        
        try:
            await self.execute(event_type, **kwargs)
            self.error_count = 0  # Reset error count on success
            return True
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"Hook '{self.name}' error ({self.error_count}/{self.max_errors}): {e}")
            
            # Disable hook if too many errors
            if self.error_count >= self.max_errors:
                self.disable()
                logger.warning(f"Hook '{self.name}' disabled due to excessive errors")
            
            return False


class HookManager:
    """
    Manages registration and execution of event hooks.
    
    Provides centralized hook management with async execution,
    error isolation, and performance monitoring.
    """
    
    def __init__(self):
        """Initialize hook manager."""
        self.hooks: Dict[str, List[BaseEventHook]] = {}
        self.execution_stats: Dict[str, Dict[str, int]] = {}
    
    def register_hook(self, event_type: str, hook: BaseEventHook) -> None:
        """
        Register a hook for a specific event type.
        
        Args:
            event_type: The event type to hook
            hook: The hook instance to register
        """
        if event_type not in self.hooks:
            self.hooks[event_type] = []
        
        self.hooks[event_type].append(hook)
        logger.info(f"Registered hook '{hook.name}' for event type '{event_type}'")
    

    
    async def trigger_hooks(self, event_type: str, **kwargs) -> Dict[str, bool]:
        """
        Trigger all hooks for a specific event type.
        
        Args:
            event_type: The event type to trigger
            **kwargs: Event data to pass to hooks
            
        Returns:
            Dictionary mapping hook names to execution success status
        """
        if event_type not in self.hooks:
            return {}
        
        # Initialize stats if needed
        if event_type not in self.execution_stats:
            self.execution_stats[event_type] = {"total": 0, "success": 0, "failed": 0}
        
        results = {}
        start_time_us = now_us()
        
        # Execute all hooks concurrently for better performance
        tasks = []
        hook_names = []
        
        for hook in self.hooks[event_type]:
            if hook.is_enabled:
                tasks.append(hook.safe_execute(event_type, **kwargs))
                hook_names.append(hook.name)
        
        if tasks:
            # Execute hooks concurrently but don't let them block each other
            try:
                # Use asyncio.gather with return_exceptions=True to prevent one hook failure from affecting others
                hook_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for hook_name, result in zip(hook_names, hook_results, strict=False):
                    if isinstance(result, Exception):
                        logger.error(f"Hook '{hook_name}' raised exception: {result}")
                        results[hook_name] = False
                        self.execution_stats[event_type]["failed"] += 1
                    else:
                        results[hook_name] = result
                        if result:
                            self.execution_stats[event_type]["success"] += 1
                        else:
                            self.execution_stats[event_type]["failed"] += 1
                
                self.execution_stats[event_type]["total"] += len(hook_results)
                
            except Exception as e:
                logger.error(f"Unexpected error executing hooks for '{event_type}': {e}")
                for hook_name in hook_names:
                    results[hook_name] = False
        
        duration_ms = (now_us() - start_time_us) / 1000  # Convert microseconds to milliseconds
        logger.debug(f"Triggered {len(results)} hooks for '{event_type}' in {duration_ms:.1f}ms")
        
        return results
    



def create_sync_hook_wrapper(func: Callable) -> Callable:
    """
    Create a wrapper that converts sync functions to async hooks.
    
    Args:
        func: Synchronous function to wrap
        
    Returns:
        Async wrapper function
    """
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        # Run sync function in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
    
    return async_wrapper

def generate_step_description(operation: str, context: Dict[str, Any]) -> str:
    """
    Generate human-readable step descriptions for timeline visualization.
    
    Args:
        operation: The operation being performed
        context: Context data for the operation
        
    Returns:
        Human-readable step description
    """
    if operation == "llm_interaction":
        model = context.get("model", "unknown")
        purpose = context.get("purpose", "analysis")
        return f"LLM {purpose} using {model}"
    
    elif operation == "mcp_tool_call":
        tool_name = context.get("tool_name", "unknown")
        server = context.get("server", "unknown")
        return f"Execute {tool_name} via {server}"
    
    elif operation == "mcp_tool_discovery":
        server = context.get("server", "unknown")
        return f"Discover available tools from {server}"
    
    else:
        return f"Execute {operation}"




class BaseLLMHook(BaseEventHook):
    """
    Abstract base class for LLM interaction hooks.
    
    Provides common data extraction and processing logic for LLM interactions,
    eliminating code duplication between history and dashboard hooks.
    """
    
    def __init__(self, name: str):
        """Initialize base LLM hook."""
        super().__init__(name)
    
    @abstractmethod
    async def process_llm_interaction(self, session_id: str, interaction_data: Dict[str, Any]) -> None:
        """
        Process the extracted LLM interaction data.
        
        Args:
            session_id: Session identifier
            interaction_data: Processed interaction data
        """
        pass
    
    async def execute(self, event_type: str, **kwargs) -> None:
        """
        Execute LLM interaction processing with common data extraction.
        
        Args:
            event_type: Type of LLM event (pre, post, error)
            **kwargs: LLM interaction context data
        """
        # Only process post-execution and error events
        if not (event_type.endswith('.post') or event_type.endswith('.error')):
            return
        
        session_id = kwargs.get('session_id')
        if not session_id:
            logger.debug(f"{self.name} triggered without session_id")
            return
        
        # Extract interaction details
        method_args = kwargs.get('args', {})
        result = kwargs.get('result', {})
        error = kwargs.get('error')
        success = not bool(error)
        
        # Extract core interaction data
        prompt_text = method_args.get('prompt', '') or method_args.get('messages', '')
        if success:
            response_text = self._extract_response_text(result)
            # Handle empty successful responses - LLM connected but returned no content
            if not response_text or response_text.strip() == "":
                response_text = "⚠️ LLM returned empty response - the model generated no content for this request"
        else:
            # Use error message as response text so operators can see what went wrong in history
            response_text = f"❌ LLM API Error: {error}" if error else "❌ Unknown LLM error"
        model_used = method_args.get('model', 'unknown')
        
        # Extract tool calls and timing
        tool_calls = self._extract_tool_calls(method_args, result) if success else None
        tool_results = self._extract_tool_results(result) if success else None
        token_usage = self._extract_token_usage(result) if success else None
        duration_ms = self._calculate_duration(kwargs.get('start_time_us'), kwargs.get('end_time_us'))
        
        # Generate human-readable step description
        step_description = generate_step_description("llm_interaction", {
            "model": model_used,
            "purpose": self._infer_purpose(prompt_text),
            "has_tools": bool(tool_calls)
        })
        
        # Prepare standardized interaction data
        interaction_data = {
            "prompt_text": str(prompt_text),
            "response_text": str(response_text),  # Always has content (success response or error message)
            "model_used": model_used,
            "step_description": step_description,
            "tool_calls": tool_calls,
            "tool_results": tool_results,
            "token_usage": token_usage,
            "duration_ms": duration_ms,
            "success": success,
            "error_message": str(error) if error else None,
            "start_time_us": kwargs.get('start_time_us'),
            "end_time_us": kwargs.get('end_time_us'),
            "timestamp_us": kwargs.get('end_time_us', now_us())
        }
        
        # Delegate to concrete implementation
        await self.process_llm_interaction(session_id, interaction_data)
    
    def _extract_response_text(self, result: Any) -> str:
        """Extract response text from LLM result."""
        if isinstance(result, str):
            return result
        elif isinstance(result, dict):
            for field in ['content', 'text', 'response', 'message']:
                if field in result:
                    return str(result[field])
            return str(result)
        elif hasattr(result, 'content'):
            return str(result.content)
        elif hasattr(result, 'text'):
            return str(result.text)
        else:
            return str(result)
    
    def _extract_tool_calls(self, args: Dict, result: Any) -> Optional[Dict]:
        """Extract tool calls from LLM interaction."""
        tool_calls = None
        
        if isinstance(result, dict):
            if 'tool_calls' in result:
                tool_calls = result['tool_calls']
            elif 'function_calls' in result:
                tool_calls = result['function_calls']
        
        if not tool_calls and 'tools' in args:
            return {"available_tools": args['tools']}
        
        return tool_calls if tool_calls else None
    
    def _extract_tool_results(self, result: Any) -> Optional[Dict]:
        """Extract tool execution results."""
        if isinstance(result, dict):
            for field in ['tool_results', 'function_results', 'tool_outputs']:
                if field in result:
                    return result[field]
        return None
    
    def _extract_token_usage(self, result: Any) -> Optional[Dict]:
        """Extract token usage statistics."""
        if isinstance(result, dict):
            if 'usage' in result:
                return result['usage']
            elif 'token_usage' in result:
                return result['token_usage']
        elif hasattr(result, 'usage'):
            usage = result.usage
            if hasattr(usage, 'dict'):
                return usage.dict()
            else:
                return str(usage)
        return None
    
    def _calculate_duration(self, start_time_us: Optional[int], end_time_us: Optional[int]) -> int:
        """Calculate interaction duration in milliseconds."""
        if start_time_us and end_time_us:
            return int((end_time_us - start_time_us) / 1000)  # Convert microseconds to milliseconds
        return 0
    
    def _infer_purpose(self, prompt_text: str) -> str:
        """Infer the purpose of the LLM interaction from prompt."""
        prompt_lower = str(prompt_text).lower()
        
        if any(word in prompt_lower for word in ['analyze', 'analysis', 'investigate']):
            return "analysis"
        elif any(word in prompt_lower for word in ['fix', 'resolve', 'solve', 'repair']):
            return "resolution"
        elif any(word in prompt_lower for word in ['check', 'status', 'inspect']):
            return "inspection"
        elif any(word in prompt_lower for word in ['plan', 'strategy', 'approach']):
            return "planning"
        else:
            return "processing"


class BaseMCPHook(BaseEventHook):
    """
    Abstract base class for MCP communication hooks.
    
    Provides common data extraction and processing logic for MCP communications,
    eliminating code duplication between history and dashboard hooks.
    """
    
    def __init__(self, name: str):
        """Initialize base MCP hook."""
        super().__init__(name)
    
    @abstractmethod
    async def process_mcp_communication(self, session_id: str, communication_data: Dict[str, Any]) -> None:
        """
        Process the extracted MCP communication data.
        
        Args:
            session_id: Session identifier
            communication_data: Processed communication data
        """
        pass
    
    async def execute(self, event_type: str, **kwargs) -> None:
        """
        Execute MCP communication processing with common data extraction.
        
        Args:
            event_type: Type of MCP event (pre, post, error)
            **kwargs: MCP interaction context data
        """
        # Process both successful completions and errors
        if not (event_type.endswith('.post') or event_type.endswith('.error')):
            return
        
        session_id = kwargs.get('session_id')
        if not session_id:
            logger.debug(f"{self.name} triggered without session_id")
            return
        
        # Extract communication details
        method_args = kwargs.get('args', {})
        result = kwargs.get('result')
        error = kwargs.get('error')
        success = not bool(error)
        
        # Extract MCP-specific data
        server_name = method_args.get('server_name', 'unknown')
        communication_type = self._infer_communication_type(kwargs.get('method', ''), method_args)
        tool_name = method_args.get('tool_name')
        tool_arguments = method_args.get('tool_arguments') or method_args.get('arguments')
        tool_result = self._extract_tool_result(result) if success else None
        available_tools = self._extract_available_tools(result) if communication_type == "tool_list" else None
        
        # Calculate timing
        duration_ms = self._calculate_duration(kwargs.get('start_time_us'), kwargs.get('end_time_us'))
        
        # Generate human-readable step description
        step_description = self._generate_step_description(communication_type, server_name, tool_name, method_args)
        
        # Prepare standardized communication data
        communication_data = {
            "server_name": server_name,
            "communication_type": communication_type,
            "step_description": step_description,
            "tool_name": tool_name,
            "tool_arguments": tool_arguments,
            "tool_result": tool_result,
            "available_tools": available_tools,
            "duration_ms": duration_ms,
            "success": success,
            "error_message": str(error) if error else None,
            "start_time_us": kwargs.get('start_time_us'),
            "end_time_us": kwargs.get('end_time_us'),
            "timestamp_us": kwargs.get('end_time_us', now_us())
        }
        
        # Delegate to concrete implementation
        await self.process_mcp_communication(session_id, communication_data)
    
    def _infer_communication_type(self, method_name: str, args: Dict) -> str:
        """Infer the type of MCP communication."""
        method_lower = method_name.lower()
        
        if 'list' in method_lower or 'discover' in method_lower or 'tools' in method_lower:
            return "tool_list"
        elif 'call' in method_lower or 'execute' in method_lower or args.get('tool_name'):
            return "tool_call"
        elif 'result' in method_lower or 'response' in method_lower:
            return "result"
        else:
            return "tool_call"  # Default assumption
    
    def _extract_tool_result(self, result: Any) -> Optional[Dict]:
        """Extract tool execution result."""
        if result is None:
            return None
        
        if isinstance(result, dict):
            return result
        elif isinstance(result, (str, int, float, bool)):
            return {"result": result}
        else:
            return {"result": str(result)}
    
    def _extract_available_tools(self, result: Any) -> Optional[Dict]:
        """Extract available tools from tool discovery result."""
        if isinstance(result, dict):
            if 'tools' in result:
                return result
            elif isinstance(result, list):
                return {"tools": result}
        elif isinstance(result, list):
            return {"tools": result}
        return None
    
    def _calculate_duration(self, start_time_us: Optional[int], end_time_us: Optional[int]) -> int:
        """Calculate communication duration in milliseconds."""
        if start_time_us and end_time_us:
            return int((end_time_us - start_time_us) / 1000)  # Convert microseconds to milliseconds
        return 0
    
    def _generate_step_description(self, comm_type: str, server_name: str, tool_name: Optional[str], args: Dict) -> str:
        """Generate human-readable step description for MCP communication."""
        if comm_type == "tool_list":
            return f"Discover available tools from {server_name}"
        elif comm_type == "tool_call" and tool_name:
            # Try to make tool calls more descriptive based on common patterns
            if 'kubectl' in tool_name.lower():
                namespace = args.get('tool_arguments', {}).get('namespace', '')
                if namespace:
                    return f"Execute {tool_name} in {namespace} namespace"
                else:
                    return f"Execute Kubernetes command {tool_name}"
            elif 'file' in tool_name.lower():
                path = args.get('tool_arguments', {}).get('path', '')
                if path:
                    return f"File operation {tool_name} on {path}"
                else:
                    return f"Execute file operation {tool_name}"
            else:
                return f"Execute {tool_name} via {server_name}"
        else:
            return f"Communicate with {server_name}"


# Global hook manager instance
_global_hook_manager: Optional[HookManager] = None

def get_hook_manager() -> HookManager:
    """
    Get the global hook manager instance.
    
    Returns:
        Global HookManager instance
    """
    global _global_hook_manager
    if _global_hook_manager is None:
        _global_hook_manager = HookManager()
    return _global_hook_manager
