"""
Base event hook infrastructure for transparent service integration.

Provides the foundation for event hooks that capture data from existing services
without modifying their core logic, with comprehensive error handling to prevent
hooks from breaking parent operations.
Uses Unix timestamps (microseconds since epoch) throughout for optimal
performance and consistency with the rest of the system.
"""

import asyncio
import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from tarsy.models.history import now_us

logger = logging.getLogger(__name__)



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
                self.is_enabled = False
                logger.warning(f"Hook '{self.name}' disabled due to excessive errors")
            
            return False


class HookManager:
    """
    Manages registration and execution of event hooks.
    
    Provides centralized hook management with async execution
    and error isolation.
    """
    
    def __init__(self):
        """Initialize hook manager."""
        self.hooks: Dict[str, List[BaseEventHook]] = {}
    
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
                    else:
                        results[hook_name] = result
                
            except Exception as e:
                logger.error(f"Unexpected error executing hooks for '{event_type}': {e}")
                for hook_name in hook_names:
                    results[hook_name] = False
        
        duration_ms = (now_us() - start_time_us) / 1000  # Convert microseconds to milliseconds
        logger.debug(f"Triggered {len(results)} hooks for '{event_type}' in {duration_ms:.1f}ms")
        
        return results

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
        # Note: The HookContext spreads data directly into kwargs, not under 'args'
        method_args = kwargs  # All data is spread directly into kwargs
        
        # Extract the actual result data - it's mixed in kwargs, so we need to identify the result keys
        # From LLM client: {'content': response.content, 'provider': ..., 'model': ..., 'request_id': ...}
        result = {
            'content': kwargs.get('content'),
            'provider': kwargs.get('provider'),
            'model': kwargs.get('model'),
            'request_id': kwargs.get('request_id')
        }
        
        error = kwargs.get('error')
        success = not bool(error)
        
        # Extract JSON request/response format
        request_json = self._extract_request_json(method_args)
        response_json = self._extract_response_json(result) if success else None
        
        # Extract response text from JSON for error handling and previews
        if success:
            response_text = self._extract_response_from_json(response_json)
            if not response_text or response_text.strip() == "":
                response_text = "⚠️ LLM returned empty response - the model generated no content for this request"
        else:
            # Use error message as response text for debugging
            response_text = f"❌ LLM API Error: {error}" if error else "❌ Unknown LLM error"
        
        # Extract model information
        model_used = self._extract_model_info(method_args)
        
        # Extract tool calls and timing
        tool_calls = self._extract_tool_calls(method_args, result) if success else None
        tool_results = self._extract_tool_results(result) if success else None
        token_usage = self._extract_token_usage(result) if success else None
        duration_ms = self._calculate_duration(kwargs.get('start_time_us'), kwargs.get('end_time_us'))
        
        # Generate human-readable step description
        step_description = generate_step_description("llm_interaction", {
            "model": model_used,
            "purpose": self._infer_purpose_from_json(request_json),
            "has_tools": bool(tool_calls)
        })
        
        # Prepare standardized interaction data
        interaction_data = {
            "request_json": request_json,  # Full API request format
            "response_json": response_json,  # Full API response format
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
    

    def _extract_model_info(self, method_args: Dict) -> str:
        """Extract model information from method arguments."""
        # Try 'model' first
        if 'model' in method_args and method_args['model']:
            return str(method_args['model'])
        
        # Try 'provider' as fallback
        if 'provider' in method_args and method_args['provider']:
            return str(method_args['provider'])
        
        return "unknown"
    
    def _extract_response_from_json(self, response_json: Optional[Dict]) -> str:
        """Extract response text from response JSON."""
        if not response_json:
            return "No response available"
            
        # Extract from OpenAI-style response format
        if 'choices' in response_json and response_json['choices']:
            choice = response_json['choices'][0]
            if isinstance(choice, dict) and 'message' in choice:
                message = choice['message']
                if isinstance(message, dict) and 'content' in message:
                    return str(message['content'])
        
        # Fallback - look for any content in the JSON
        if isinstance(response_json, dict):
            for key in ['content', 'text', 'response', 'answer']:
                if key in response_json:
                    return str(response_json[key])
        
        return "No response content available"
    
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
    
    def _extract_request_json(self, method_args: Dict) -> Optional[Dict]:
        """
        Extract full request JSON in the format sent to LLM APIs.
        
        Args:
            method_args: Arguments passed to the LLM method
            
        Returns:
            Dictionary matching the API request format, or None if extraction fails
        """
        try:
            request_data = {}
            
            # Extract model
            if 'model' in method_args and method_args['model']:
                request_data['model'] = str(method_args['model'])
            
            # Extract messages (most important part)
            if 'messages' in method_args and method_args['messages']:
                messages = method_args['messages']
                if isinstance(messages, list):
                    # Convert LLMMessage objects to API format
                    api_messages = []
                    for msg in messages:
                        if hasattr(msg, 'role') and hasattr(msg, 'content'):
                            # LLMMessage object - safely convert to dict
                            api_messages.append({
                                "role": str(msg.role),
                                "content": str(msg.content)
                            })
                        elif isinstance(msg, dict):
                            # Already in dict format
                            api_messages.append({
                                "role": str(msg.get('role', 'unknown')),
                                "content": str(msg.get('content', ''))
                            })
                    
                    request_data['messages'] = api_messages
                else:
                    # Fallback for non-list messages
                    request_data['messages'] = [{"role": "user", "content": str(messages)}]
            
            # Extract other common LLM parameters
            for param in ['temperature', 'max_tokens', 'top_p', 'frequency_penalty', 'presence_penalty', 'stop']:
                if param in method_args and method_args[param] is not None:
                    request_data[param] = method_args[param]
            
            # Only return if we have at least messages
            return request_data if 'messages' in request_data else None
            
        except Exception as e:
            # Log error but don't fail the hook
            logger.error(f"Failed to extract request JSON: {str(e)}")
            return None
    
    def _extract_response_json(self, result: Any) -> Optional[Dict]:
        """
        Extract full response JSON in the format received from LLM APIs.
        
        Args:
            result: Raw result from the LLM method
            
        Returns:
            Dictionary matching the API response format, or None if extraction fails
        """
        try:
            response_data = {}
            
            # Extract response text and build proper API format
            if isinstance(result, str):
                response_content = result
            elif isinstance(result, dict):
                response_content = None
                for field in ['content', 'text', 'response', 'message']:
                    if field in result:
                        response_content = str(result[field])
                        break
                if not response_content:
                    response_content = str(result)
            elif hasattr(result, 'content'):
                response_content = str(result.content)
            elif hasattr(result, 'text'):
                response_content = str(result.text)
            else:
                response_content = str(result)
            
            if response_content:
                response_data['choices'] = [{
                    "message": {
                        "role": "assistant", 
                        "content": response_content
                    },
                    "finish_reason": "stop"
                }]
            
            # Extract usage information if available
            usage = self._extract_token_usage(result)
            if usage:
                response_data['usage'] = usage
            
            # Add model info if available in result
            if hasattr(result, 'model') or (isinstance(result, dict) and 'model' in result):
                model = getattr(result, 'model', None) or result.get('model')
                if model:
                    response_data['model'] = str(model)
            
            return response_data if response_data else None
            
        except Exception as e:
            # Log error but don't fail the hook
            logger.error(f"Failed to extract response JSON: {str(e)}")
            return None
    
    def _calculate_duration(self, start_time_us: Optional[int], end_time_us: Optional[int]) -> int:
        """Calculate interaction duration in milliseconds."""
        if start_time_us and end_time_us:
            return int((end_time_us - start_time_us) / 1000)  # Convert microseconds to milliseconds
        return 0
    
    def _infer_purpose_from_json(self, request_json: Optional[Dict]) -> str:
        """Infer the purpose of the LLM interaction from request JSON."""
        if not request_json or 'messages' not in request_json:
            return "processing"
        
        # Analyze message content to infer purpose
        all_content = ""
        for message in request_json['messages']:
            if isinstance(message, dict) and 'content' in message:
                all_content += " " + str(message['content'])
        
        content_lower = all_content.lower()
        
        if any(word in content_lower for word in ['analyze', 'analysis', 'investigate']):
            return "analysis"
        elif any(word in content_lower for word in ['fix', 'resolve', 'solve', 'repair']):
            return "resolution"
        elif any(word in content_lower for word in ['check', 'status', 'inspect']):
            return "inspection"
        elif any(word in content_lower for word in ['plan', 'strategy', 'approach']):
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
        # Note: The HookContext spreads data directly into kwargs, not under 'args'
        method_args = kwargs  # All data is spread directly into kwargs
        result = kwargs  # Result data is also spread directly into kwargs, not under 'result' key
        error = kwargs.get('error')
        success = not bool(error)
        
        # Extract MCP-specific data
        server_name = self._extract_server_name(method_args, kwargs)
        communication_type = self._infer_communication_type(kwargs.get('method', ''), method_args)
        tool_name = self._extract_tool_name(method_args)
        tool_arguments = self._extract_tool_arguments(method_args)
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
    
    def _extract_server_name(self, method_args: Dict, kwargs: Dict) -> str:
        """Extract server name from method arguments with fallbacks."""
        # Try direct extraction first
        if 'server_name' in method_args and method_args['server_name']:
            return str(method_args['server_name'])
        
        # Try from other context if available
        if 'server' in method_args and method_args['server']:
            return str(method_args['server'])
            
        # Try from kwargs context
        if 'server_name' in kwargs and kwargs['server_name']:
            return str(kwargs['server_name'])
            
        return "unknown"
    
    def _extract_tool_name(self, method_args: Dict) -> Optional[str]:
        """Extract tool name from method arguments."""
        # Try 'tool_name' first
        if 'tool_name' in method_args and method_args['tool_name']:
            return str(method_args['tool_name'])
        
        # Try 'tool' as fallback
        if 'tool' in method_args and method_args['tool']:
            return str(method_args['tool'])
            
        return None
    
    def _extract_tool_arguments(self, method_args: Dict) -> Optional[Dict]:
        """Extract tool arguments from method arguments."""
        # Try 'tool_arguments' first (what MCP client should pass)
        if 'tool_arguments' in method_args and method_args['tool_arguments']:
            args = method_args['tool_arguments']
            if isinstance(args, dict):
                return args
            else:
                return {"arguments": args}
        
        # Try 'arguments' as fallback
        if 'arguments' in method_args and method_args['arguments']:
            args = method_args['arguments']
            if isinstance(args, dict):
                return args
            else:
                return {"arguments": args}
        
        # Try 'parameters' as another fallback
        if 'parameters' in method_args and method_args['parameters']:
            args = method_args['parameters']
            if isinstance(args, dict):
                return args
            else:
                return {"parameters": args}
                
        return None


class HookContext:
    """
    Context manager for hook execution during service operations.
    
    Provides automatic hook triggering with proper error handling and timing.
    Restored after cleanup to fix real-time dashboard updates.
    """
    
    def __init__(self, service_type: str, method_name: str, session_id: str, **kwargs):
        """
        Initialize hook context.
        
        Args:
            service_type: Service type (e.g., 'llm', 'mcp')
            method_name: Method being called (e.g., 'generate_response', 'call_tool')
            session_id: Session ID for tracking
            **kwargs: Additional context data to pass to hooks
        """
        self.service_type = service_type
        self.method_name = method_name
        self.session_id = session_id
        self.context_data = kwargs.copy()
        self.start_time_us = None
        self.request_id = None
        self.hook_manager = get_hook_manager()
        
        # Generate unique request ID
        import uuid
        self.request_id = f"{service_type}_{uuid.uuid4().hex[:8]}"
        
    async def __aenter__(self):
        """Enter async context - start timing."""
        self.start_time_us = now_us()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context - handle errors if any occurred."""
        if exc_type is not None:
            # An error occurred during operation
            duration_ms = (now_us() - self.start_time_us) / 1000 if self.start_time_us else 0
            
            error_data = {
                'session_id': self.session_id,
                'request_id': self.request_id,
                'method_name': self.method_name,
                'error_message': str(exc_val),
                'duration_ms': duration_ms,
                'timestamp_us': now_us(),
                'success': False,
                **self.context_data
            }
            
            # Trigger error hooks
            error_event = f"{self.service_type}.error"
            await self.hook_manager.trigger_hooks(error_event, **error_data)
        
        return False  # Don't suppress exceptions
    
    async def complete_success(self, result_data: Dict[str, Any]):
        """
        Complete the operation successfully and trigger post hooks.
        
        Args:
            result_data: Result data from the operation
        """
        duration_ms = (now_us() - self.start_time_us) / 1000 if self.start_time_us else 0
        
        # Prepare success data for hooks
        success_data = {
            'session_id': self.session_id,
            'request_id': self.request_id,
            'method_name': self.method_name,
            'duration_ms': duration_ms,
            'timestamp_us': now_us(),
            'success': True,
            **self.context_data,
            **result_data
        }
        
        # Generate human-readable step description
        if self.service_type == 'llm':
            step_desc = f"LLM analysis using {self.context_data.get('model', 'unknown model')}"
        elif self.service_type == 'mcp':
            tool_name = self.context_data.get('tool_name') or result_data.get('tool_name', 'unknown tool')
            server_name = self.context_data.get('server_name') or result_data.get('server_name', 'unknown server')
            step_desc = f"Execute {tool_name} via {server_name}"
        else:
            step_desc = f"{self.service_type} operation"
        
        success_data['step_description'] = step_desc
        
        # Trigger post hooks (these should trigger dashboard/history updates)
        post_event = f"{self.service_type}.post"
        await self.hook_manager.trigger_hooks(post_event, **success_data)
    
    def get_request_id(self) -> str:
        """Get the unique request ID for this operation."""
        return self.request_id


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