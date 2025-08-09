"""
Unit tests for Base Hooks infrastructure.

Tests the foundational hook infrastructure including utility functions,
context management, hook execution, and registration management.
"""

from datetime import datetime
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.hooks.base_hooks import (
    BaseEventHook,
    BaseLLMHook,
    BaseMCPHook,
    HookContext,
    HookManager,
    generate_step_description,
    get_hook_manager,
)


class TestGenerateStepDescription:
    """Test the generate_step_description utility function."""

    @pytest.mark.unit
    def test_llm_interaction_description(self):
        """Test step description generation for LLM interactions."""
        context = {
            "model": "gpt-4",
            "purpose": "analysis",
            "has_tools": True
        }
        
        description = generate_step_description("llm_interaction", context)
        assert description == "LLM analysis using gpt-4"

    @pytest.mark.unit
    def test_llm_interaction_default_purpose(self):
        """Test LLM interaction with default purpose."""
        context = {
            "model": "claude-3",
            # No purpose specified
        }
        
        description = generate_step_description("llm_interaction", context)
        assert description == "LLM analysis using claude-3"

    @pytest.mark.unit
    def test_llm_interaction_unknown_model(self):
        """Test LLM interaction with unknown model."""
        context = {
            "purpose": "resolution"
            # No model specified
        }
        
        description = generate_step_description("llm_interaction", context)
        assert description == "LLM resolution using unknown"

    @pytest.mark.unit
    def test_mcp_tool_call_description(self):
        """Test step description generation for MCP tool calls."""
        context = {
            "tool_name": "kubectl-get-pods",
            "server": "kubernetes"
        }
        
        description = generate_step_description("mcp_tool_call", context)
        assert description == "Execute kubectl-get-pods via kubernetes"

    @pytest.mark.unit
    def test_mcp_tool_call_default_values(self):
        """Test MCP tool call with default values."""
        context = {}  # Empty context
        
        description = generate_step_description("mcp_tool_call", context)
        assert description == "Execute unknown via unknown"

    @pytest.mark.unit
    def test_mcp_tool_discovery_description(self):
        """Test step description generation for MCP tool discovery."""
        context = {
            "server": "filesystem"
        }
        
        description = generate_step_description("mcp_tool_discovery", context)
        assert description == "Discover available tools from filesystem"

    @pytest.mark.unit
    def test_mcp_tool_discovery_default_server(self):
        """Test MCP tool discovery with default server."""
        context = {}  # Empty context
        
        description = generate_step_description("mcp_tool_discovery", context)
        assert description == "Discover available tools from unknown"

    @pytest.mark.unit
    def test_unknown_operation_fallback(self):
        """Test fallback for unknown operations."""
        context = {"some": "data"}
        
        description = generate_step_description("custom_operation", context)
        assert description == "Execute custom_operation"

    @pytest.mark.unit
    def test_empty_operation_fallback(self):
        """Test fallback for empty operation."""
        context = {"some": "data"}
        
        description = generate_step_description("", context)
        assert description == "Execute "

class TestHookContext:
    """Test the HookContext class for lifecycle and timing management."""

    @pytest.mark.unit
    def test_initialization(self):
        """Test HookContext initialization."""
        context = HookContext(
            service_type="test_service",
            method_name="test_method",
            session_id="test_session_123",
            param1="value1",
            param2="value2"
        )
        
        assert context.service_type == "test_service"
        assert context.method_name == "test_method"
        assert context.session_id == "test_session_123"
        assert context.method_args == {"param1": "value1", "param2": "value2"}
        assert context.start_time_us is None
        assert context.end_time_us is None
        assert len(context.request_id) == 8  # UUID truncated to 8 chars
        assert context.hook_context == {}
        assert context.hook_manager is None

    @pytest.mark.unit
    def test_initialization_without_session_id(self):
        """Test HookContext initialization without session ID."""
        context = HookContext(
            service_type="llm",
            method_name="generate",
            prompt="test prompt"
        )
        
        assert context.session_id is None
        assert context.method_args == {"prompt": "test prompt"}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_context_manager_success_flow(self):
        """Test HookContext as async context manager with success flow."""
        mock_hook_manager = Mock()
        mock_hook_manager.trigger_hooks = AsyncMock()
        
        with patch('tarsy.hooks.base_hooks.get_hook_manager', return_value=mock_hook_manager):
            context = HookContext("test", "method", session_id="session123", param="value")
            
            async with context as ctx:
                assert ctx is context
                assert context.start_time_us is not None
                assert context.hook_manager == mock_hook_manager
                assert "session_id" in context.hook_context
                assert "start_time_us" in context.hook_context
                assert context.hook_context["session_id"] == "session123"
                
                # Verify pre-hooks were triggered (check immediately after context entry)
                assert mock_hook_manager.trigger_hooks.call_count == 1
                pre_call = mock_hook_manager.trigger_hooks.call_args_list[0]
                assert pre_call[0][0] == "test.pre"
                pre_context = pre_call[1]
                assert pre_context["session_id"] == "session123"
                assert "start_time_us" in pre_context
                
                # Simulate some work
                result_data = {"status": "success", "data": "processed"}
                await context.complete_success(result_data)
            
            # Verify post-hooks were triggered
            assert mock_hook_manager.trigger_hooks.call_count == 2
            post_call = mock_hook_manager.trigger_hooks.call_args_list[1]
            assert post_call[0][0] == "test.post"
            post_context = post_call[1]
            assert post_context["result"] == result_data
            assert post_context["success"] is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_context_manager_error_flow(self):
        """Test HookContext with exception handling."""
        mock_hook_manager = Mock()
        mock_hook_manager.trigger_hooks = AsyncMock()
        
        with patch('tarsy.hooks.base_hooks.get_hook_manager', return_value=mock_hook_manager):
            context = HookContext("test", "method", session_id="session456")
            
            with pytest.raises(ValueError, match="Test error"):
                async with context:
                    raise ValueError("Test error")
            
            # Verify error hooks were triggered
            assert mock_hook_manager.trigger_hooks.call_count == 2
            error_call = mock_hook_manager.trigger_hooks.call_args_list[1]
            assert error_call[0][0] == "test.error"
            error_context = error_call[1]
            assert error_context["error"] == "Test error"
            assert error_context["success"] is False

    @pytest.mark.unit
    def test_get_request_id(self):
        """Test getting the request ID."""
        context = HookContext("test", "method")
        request_id = context.get_request_id()
        
        assert isinstance(request_id, str)
        assert len(request_id) == 8
        assert request_id == context.request_id



    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_complete_success_sets_end_time(self):
        """Test that complete_success sets end time if not already set."""
        mock_hook_manager = Mock()
        mock_hook_manager.trigger_hooks = AsyncMock()
        
        context = HookContext("test", "method")
        context.hook_manager = mock_hook_manager
        context.hook_context = {"session_id": "test"}
        
        result_data = {"result": "success"}
        await context.complete_success(result_data)
        
        assert context.end_time_us is not None
        assert context.hook_context["result"] == result_data
        assert context.hook_context["success"] is True
        mock_hook_manager.trigger_hooks.assert_called_once_with("test.post", **context.hook_context)


class TestConcreteHook(BaseEventHook):
    """Concrete implementation of BaseEventHook for testing."""
    
    def __init__(self, name: str):
        super().__init__(name)
        self.execution_log = []
    
    async def execute(self, event_type: str, **kwargs) -> None:
        """Log execution for testing."""
        self.execution_log.append({
            "event_type": event_type,
            "kwargs": kwargs
        })


class TestFailingHook(BaseEventHook):
    """Hook that always fails for testing error handling."""
    
    def __init__(self, name: str, error_message: str = "Test error"):
        super().__init__(name)
        self.error_message = error_message
    
    async def execute(self, event_type: str, **kwargs) -> None:
        """Always raise an exception."""
        raise Exception(self.error_message)


class TestBaseEventHook:
    """Test the BaseEventHook abstract base class."""

    @pytest.mark.unit
    def test_initialization(self):
        """Test BaseEventHook initialization."""
        hook = TestConcreteHook("test_hook")
        
        assert hook.name == "test_hook"
        assert hook.is_enabled is True
        assert hook.error_count == 0
        assert hook.max_errors == 5



    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_safe_execute_success(self):
        """Test successful hook execution."""
        hook = TestConcreteHook("test_hook")
        
        result = await hook.safe_execute("test.event", param1="value1", param2="value2")
        
        assert result is True
        assert len(hook.execution_log) == 1
        assert hook.execution_log[0]["event_type"] == "test.event"
        assert hook.execution_log[0]["kwargs"] == {"param1": "value1", "param2": "value2"}
        assert hook.error_count == 0



    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_safe_execute_error_handling(self):
        """Test error handling in safe_execute."""
        hook = TestFailingHook("failing_hook", "Test failure")
        
        result = await hook.safe_execute("test.event")
        
        assert result is False
        assert hook.error_count == 1
        assert hook.is_enabled is True  # Still enabled after first error

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_safe_execute_auto_disable_after_max_errors(self):
        """Test automatic disable after max errors reached."""
        hook = TestFailingHook("failing_hook", "Persistent failure")
        
        # Execute multiple times to reach max_errors
        for i in range(6):  # max_errors is 5
            result = await hook.safe_execute("test.event")
            assert result is False
            
            if i < 4:  # 0-4 (5 errors)
                assert hook.is_enabled is True
                assert hook.error_count == i + 1
            else:  # 5th error and beyond
                assert hook.is_enabled is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_safe_execute_error_count_reset_on_success(self):
        """Test that error count resets on successful execution."""
        # Create a hook that fails then succeeds
        hook = TestConcreteHook("test_hook")
        
        # Manually set error count
        hook.error_count = 3
        
        result = await hook.safe_execute("test.event")
        
        assert result is True
        assert hook.error_count == 0  # Reset on success


class TestHookManager:
    """Test the HookManager class for hook registration and execution."""

    @pytest.fixture
    def hook_manager(self):
        """Create a fresh HookManager instance."""
        return HookManager()

    @pytest.fixture
    def test_hooks(self):
        """Create test hooks for registration."""
        return [
            TestConcreteHook("hook1"),
            TestConcreteHook("hook2"),
            TestConcreteHook("hook3")
        ]

    @pytest.mark.unit
    def test_initialization(self, hook_manager):
        """Test HookManager initialization."""
        assert hook_manager.hooks == {}


    @pytest.mark.unit
    def test_register_hook(self, hook_manager, test_hooks):
        """Test hook registration."""
        hook = test_hooks[0]
        
        hook_manager.register_hook("test.event", hook)
        
        assert "test.event" in hook_manager.hooks
        assert len(hook_manager.hooks["test.event"]) == 1
        assert hook_manager.hooks["test.event"][0] == hook

    @pytest.mark.unit
    def test_register_multiple_hooks_same_event(self, hook_manager, test_hooks):
        """Test registering multiple hooks for the same event."""
        for hook in test_hooks:
            hook_manager.register_hook("test.event", hook)
        
        assert len(hook_manager.hooks["test.event"]) == 3
        assert all(hook in hook_manager.hooks["test.event"] for hook in test_hooks)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_trigger_hooks_success(self, hook_manager, test_hooks):
        """Test successful hook triggering."""
        for hook in test_hooks:
            hook_manager.register_hook("test.event", hook)
        
        results = await hook_manager.trigger_hooks("test.event", param1="value1", param2="value2")
        
        assert len(results) == 3
        assert all(result is True for result in results.values())
        assert set(results.keys()) == {"hook1", "hook2", "hook3"}
        
        # Verify all hooks were executed
        for hook in test_hooks:
            assert len(hook.execution_log) == 1
            assert hook.execution_log[0]["kwargs"]["param1"] == "value1"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_trigger_hooks_no_hooks_registered(self, hook_manager):
        """Test triggering hooks when none are registered."""
        results = await hook_manager.trigger_hooks("nonexistent.event", param="value")
        
        assert results == {}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_trigger_hooks_with_failing_hook(self, hook_manager):
        """Test hook triggering with one failing hook."""
        good_hook = TestConcreteHook("good_hook")
        bad_hook = TestFailingHook("bad_hook", "Test failure")
        
        hook_manager.register_hook("test.event", good_hook)
        hook_manager.register_hook("test.event", bad_hook)
        
        results = await hook_manager.trigger_hooks("test.event", param="value")
        
        assert len(results) == 2
        assert results["good_hook"] is True
        assert results["bad_hook"] is False
        assert len(good_hook.execution_log) == 1
        assert bad_hook.error_count == 1






class TestGlobalHookManager:
    """Test global hook manager functionality."""

    @pytest.mark.unit
    def test_get_hook_manager_singleton(self):
        """Test that get_hook_manager returns the same instance."""
        manager1 = get_hook_manager()
        manager2 = get_hook_manager()
        
        assert manager1 is manager2
        assert isinstance(manager1, HookManager)

    @pytest.mark.unit
    def test_get_hook_manager_is_hook_manager_instance(self):
        """Test that get_hook_manager returns a HookManager instance."""
        manager = get_hook_manager()
        
        assert isinstance(manager, HookManager)
        assert hasattr(manager, 'register_hook')
        assert hasattr(manager, 'trigger_hooks')


class TestBaseLLMHookUtilityMethods:
    """Test BaseLLMHook utility methods for data extraction and processing."""
    
    class ConcreteLLMHook(BaseLLMHook):
        """Concrete implementation for testing."""
        def __init__(self):
            super().__init__("test_llm_hook")
        
        async def process_llm_interaction(self, session_id: str, interaction_data: Dict[str, Any]) -> None:
            pass  # No-op for testing
    
    @pytest.fixture
    def llm_hook(self):
        """Create concrete LLM hook instance for utility method testing."""
        return self.ConcreteLLMHook()

    @pytest.mark.unit
    def test_extract_response_text_string_result(self, llm_hook):
        """Test response text extraction from string result."""
        result = "This is a simple string response"
        extracted = llm_hook._extract_response_text(result)
        assert extracted == "This is a simple string response"

    @pytest.mark.unit
    def test_extract_response_text_dict_with_content(self, llm_hook):
        """Test response text extraction from dict with content field."""
        result = {"content": "Response content", "metadata": {"tokens": 150}}
        extracted = llm_hook._extract_response_text(result)
        assert extracted == "Response content"

    @pytest.mark.unit
    def test_extract_response_text_dict_with_text(self, llm_hook):
        """Test response text extraction from dict with text field."""
        result = {"text": "Text response", "status": "success"}
        extracted = llm_hook._extract_response_text(result)
        assert extracted == "Text response"

    @pytest.mark.unit
    def test_extract_response_text_dict_with_message(self, llm_hook):
        """Test response text extraction from dict with message field."""
        result = {"message": "Message response", "id": "msg_123"}
        extracted = llm_hook._extract_response_text(result)
        assert extracted == "Message response"

    @pytest.mark.unit
    def test_extract_response_text_object_with_content_attr(self, llm_hook):
        """Test response text extraction from object with content attribute."""
        class MockResponse:
            def __init__(self):
                self.content = "Object content response"
                self.status = "completed"
        
        result = MockResponse()
        extracted = llm_hook._extract_response_text(result)
        assert extracted == "Object content response"

    @pytest.mark.unit
    def test_extract_response_text_object_with_text_attr(self, llm_hook):
        """Test response text extraction from object with text attribute."""
        class MockResponse:
            def __init__(self):
                self.text = "Object text response"
                self.other = "ignored"
        
        result = MockResponse()
        extracted = llm_hook._extract_response_text(result)
        assert extracted == "Object text response"

    @pytest.mark.unit
    def test_extract_response_text_fallback_str_conversion(self, llm_hook):
        """Test response text extraction with fallback to string conversion."""
        result = {"complex": "data", "no_text_fields": True}
        extracted = llm_hook._extract_response_text(result)
        assert "complex" in extracted
        assert "data" in extracted

    @pytest.mark.unit
    def test_extract_tool_calls_from_result_tool_calls(self, llm_hook):
        """Test tool calls extraction from result with tool_calls field."""
        args = {}
        result = {"tool_calls": [{"name": "test_tool", "args": {"param": "value"}}]}
        extracted = llm_hook._extract_tool_calls(args, result)
        assert extracted == [{"name": "test_tool", "args": {"param": "value"}}]

    @pytest.mark.unit
    def test_extract_tool_calls_from_result_function_calls(self, llm_hook):
        """Test tool calls extraction from result with function_calls field."""
        args = {}
        result = {"function_calls": [{"function": "test_func", "parameters": {}}]}
        extracted = llm_hook._extract_tool_calls(args, result)
        assert extracted == [{"function": "test_func", "parameters": {}}]

    @pytest.mark.unit
    def test_extract_tool_calls_from_args_tools(self, llm_hook):
        """Test tool calls extraction from args with tools available."""
        args = {"tools": [{"name": "available_tool", "description": "Test tool"}]}
        result = {}
        extracted = llm_hook._extract_tool_calls(args, result)
        assert extracted == {"available_tools": [{"name": "available_tool", "description": "Test tool"}]}

    @pytest.mark.unit
    def test_extract_tool_calls_none_when_missing(self, llm_hook):
        """Test tool calls extraction returns None when no tools present."""
        args = {}
        result = {}
        extracted = llm_hook._extract_tool_calls(args, result)
        assert extracted is None

    @pytest.mark.unit
    def test_extract_tool_results_tool_results_field(self, llm_hook):
        """Test tool results extraction from tool_results field."""
        result = {"tool_results": [{"tool": "test", "result": "success"}]}
        extracted = llm_hook._extract_tool_results(result)
        assert extracted == [{"tool": "test", "result": "success"}]

    @pytest.mark.unit
    def test_extract_tool_results_function_results_field(self, llm_hook):
        """Test tool results extraction from function_results field."""
        result = {"function_results": [{"function": "test", "output": "data"}]}
        extracted = llm_hook._extract_tool_results(result)
        assert extracted == [{"function": "test", "output": "data"}]

    @pytest.mark.unit
    def test_extract_tool_results_tool_outputs_field(self, llm_hook):
        """Test tool results extraction from tool_outputs field."""
        result = {"tool_outputs": [{"id": "1", "content": "output"}]}
        extracted = llm_hook._extract_tool_results(result)
        assert extracted == [{"id": "1", "content": "output"}]

    @pytest.mark.unit
    def test_extract_tool_results_none_when_missing(self, llm_hook):
        """Test tool results extraction returns None when no results present."""
        result = {"other": "data"}
        extracted = llm_hook._extract_tool_results(result)
        assert extracted is None

    @pytest.mark.unit
    def test_extract_token_usage_usage_field(self, llm_hook):
        """Test token usage extraction from usage field."""
        result = {"usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}}
        extracted = llm_hook._extract_token_usage(result)
        assert extracted == {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}

    @pytest.mark.unit
    def test_extract_token_usage_token_usage_field(self, llm_hook):
        """Test token usage extraction from token_usage field."""
        result = {"token_usage": {"input": 15, "output": 25}}
        extracted = llm_hook._extract_token_usage(result)
        assert extracted == {"input": 15, "output": 25}

    @pytest.mark.unit
    def test_extract_token_usage_object_with_usage_attr(self, llm_hook):
        """Test token usage extraction from object with usage attribute."""
        class MockUsage:
            def __init__(self):
                self.prompt_tokens = 10
                self.completion_tokens = 20
            
            def dict(self):
                return {"prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens}
        
        class MockResult:
            def __init__(self):
                self.usage = MockUsage()
        
        result = MockResult()
        extracted = llm_hook._extract_token_usage(result)
        assert extracted == {"prompt_tokens": 10, "completion_tokens": 20}

    @pytest.mark.unit
    def test_extract_token_usage_object_without_dict_method(self, llm_hook):
        """Test token usage extraction from object without dict method."""
        class MockUsage:
            def __init__(self):
                self.prompt_tokens = 10
        
        class MockResult:
            def __init__(self):
                self.usage = MockUsage()
        
        result = MockResult()
        extracted = llm_hook._extract_token_usage(result)
        assert isinstance(extracted, str)

    @pytest.mark.unit
    def test_extract_token_usage_none_when_missing(self, llm_hook):
        """Test token usage extraction returns None when no usage present."""
        result = {"other": "data"}
        extracted = llm_hook._extract_token_usage(result)
        assert extracted is None

    @pytest.mark.unit
    def test_calculate_duration_with_valid_times(self, llm_hook):
        """Test duration calculation with valid start and end times (Unix timestamps)."""
        start_time_us = 1672574400000000  # 2023-01-01T12:00:00Z in microseconds
        end_time_us = 1672574401500000    # 1.5 seconds later
        duration = llm_hook._calculate_duration(start_time_us, end_time_us)
        assert duration == 1500  # 1500 milliseconds

    @pytest.mark.unit
    def test_calculate_duration_with_missing_times(self, llm_hook):
        """Test duration calculation with missing times."""
        assert llm_hook._calculate_duration(None, None) == 0
        assert llm_hook._calculate_duration(datetime.now(), None) == 0
        assert llm_hook._calculate_duration(None, datetime.now()) == 0

    @pytest.mark.unit
    def test_infer_purpose_analysis_keywords(self, llm_hook):
        """Test purpose inference for analysis keywords."""
        test_cases = [
            "Please analyze this error log",
            "Can you investigate what happened?",
            "I need an analysis of the performance issue"
        ]
        for prompt in test_cases:
            purpose = llm_hook._infer_purpose(prompt)
            assert purpose == "analysis"

    @pytest.mark.unit
    def test_infer_purpose_resolution_keywords(self, llm_hook):
        """Test purpose inference for resolution keywords."""
        test_cases = [
            "Please fix this bug",
            "How can I resolve this issue?",
            "Help me solve this problem",
            "Can you repair the configuration?"
        ]
        for prompt in test_cases:
            purpose = llm_hook._infer_purpose(prompt)
            assert purpose == "resolution"

    @pytest.mark.unit
    def test_infer_purpose_inspection_keywords(self, llm_hook):
        """Test purpose inference for inspection keywords."""
        test_cases = [
            "Check the system status",
            "Please inspect the logs",
            "Can you check if everything is working?"
        ]
        for prompt in test_cases:
            purpose = llm_hook._infer_purpose(prompt)
            assert purpose == "inspection"

    @pytest.mark.unit
    def test_infer_purpose_planning_keywords(self, llm_hook):
        """Test purpose inference for planning keywords."""
        test_cases = [
            "Create a plan for deployment",
            "What strategy should we use?",
            "Help me approach this problem"
        ]
        for prompt in test_cases:
            purpose = llm_hook._infer_purpose(prompt)
            assert purpose == "planning"

    @pytest.mark.unit
    def test_infer_purpose_default_processing(self, llm_hook):
        """Test purpose inference defaults to processing."""
        test_cases = [
            "Hello world",
            "Random text without keywords",
            "Just some content"
        ]
        for prompt in test_cases:
            purpose = llm_hook._infer_purpose(prompt)
            assert purpose == "processing"

    @pytest.mark.unit
    def test_infer_purpose_case_insensitive(self, llm_hook):
        """Test purpose inference is case insensitive."""
        test_cases = [
            ("ANALYZE this data", "analysis"),
            ("FIX the issue", "resolution"),
            ("CHECK the status", "inspection"),
            ("PLAN the approach", "planning")
        ]
        for prompt, expected in test_cases:
            purpose = llm_hook._infer_purpose(prompt)
            assert purpose == expected


class TestBaseMCPHookUtilityMethods:
    """Test BaseMCPHook utility methods for data extraction and processing."""
    
    class ConcreteMCPHook(BaseMCPHook):
        """Concrete implementation for testing."""
        def __init__(self):
            super().__init__("test_mcp_hook")
        
        async def process_mcp_communication(self, session_id: str, communication_data: Dict[str, Any]) -> None:
            pass  # No-op for testing
    
    @pytest.fixture
    def mcp_hook(self):
        """Create concrete MCP hook instance for utility method testing."""
        return self.ConcreteMCPHook()

    @pytest.mark.unit
    def test_infer_communication_type_tool_list(self, mcp_hook):
        """Test communication type inference for tool list operations."""
        test_cases = [
            ("list_tools", {}),
            ("discover_tools", {}),
            ("get_tools", {})
        ]
        for method, args in test_cases:
            comm_type = mcp_hook._infer_communication_type(method, args)
            assert comm_type == "tool_list"

    @pytest.mark.unit
    def test_infer_communication_type_tool_call_by_method(self, mcp_hook):
        """Test communication type inference for tool calls by method name."""
        test_cases = [
            ("call_tool", {}),
            ("execute_tool", {}),
            ("invoke_tool", {})
        ]
        for method, args in test_cases:
            comm_type = mcp_hook._infer_communication_type(method, args)
            assert comm_type == "tool_call"

    @pytest.mark.unit
    def test_infer_communication_type_tool_call_by_args(self, mcp_hook):
        """Test communication type inference for tool calls by arguments."""
        args = {"tool_name": "kubectl_get_pods"}
        comm_type = mcp_hook._infer_communication_type("some_method", args)
        assert comm_type == "tool_call"

    @pytest.mark.unit
    def test_infer_communication_type_result(self, mcp_hook):
        """Test communication type inference for result operations."""
        test_cases = [
            ("get_result", {}),
            ("tool_response", {}),
            ("fetch_response", {})
        ]
        for method, args in test_cases:
            comm_type = mcp_hook._infer_communication_type(method, args)
            assert comm_type == "result"

    @pytest.mark.unit
    def test_infer_communication_type_default(self, mcp_hook):
        """Test communication type inference defaults to tool_call."""
        comm_type = mcp_hook._infer_communication_type("unknown_method", {})
        assert comm_type == "tool_call"

    @pytest.mark.unit
    def test_extract_tool_result_none_input(self, mcp_hook):
        """Test tool result extraction with None input."""
        result = mcp_hook._extract_tool_result(None)
        assert result is None

    @pytest.mark.unit
    def test_extract_tool_result_dict_input(self, mcp_hook):
        """Test tool result extraction with dict input."""
        input_dict = {"status": "success", "data": {"key": "value"}}
        result = mcp_hook._extract_tool_result(input_dict)
        assert result == input_dict

    @pytest.mark.unit
    def test_extract_tool_result_primitive_types(self, mcp_hook):
        """Test tool result extraction with primitive types."""
        test_cases = [
            ("string_result", {"result": "string_result"}),
            (42, {"result": 42}),
            (3.14, {"result": 3.14}),
            (True, {"result": True})
        ]
        for input_val, expected in test_cases:
            result = mcp_hook._extract_tool_result(input_val)
            assert result == expected

    @pytest.mark.unit
    def test_extract_tool_result_complex_object(self, mcp_hook):
        """Test tool result extraction with complex object."""
        class ComplexObject:
            def __init__(self):
                self.attr = "value"
        
        obj = ComplexObject()
        result = mcp_hook._extract_tool_result(obj)
        assert result == {"result": str(obj)}

    @pytest.mark.unit
    def test_extract_available_tools_dict_with_tools(self, mcp_hook):
        """Test available tools extraction from dict with tools field."""
        result = {"tools": [{"name": "tool1"}, {"name": "tool2"}]}
        extracted = mcp_hook._extract_available_tools(result)
        assert extracted == result

    @pytest.mark.unit
    def test_extract_available_tools_dict_as_list(self, mcp_hook):
        """Test available tools extraction from dict that is actually a list."""
        result = [{"name": "tool1"}, {"name": "tool2"}]
        extracted = mcp_hook._extract_available_tools(result)
        assert extracted == {"tools": result}

    @pytest.mark.unit
    def test_extract_available_tools_direct_list(self, mcp_hook):
        """Test available tools extraction from direct list."""
        result = [{"name": "tool1"}, {"name": "tool2"}]
        extracted = mcp_hook._extract_available_tools(result)
        assert extracted == {"tools": result}

    @pytest.mark.unit
    def test_extract_available_tools_none_when_missing(self, mcp_hook):
        """Test available tools extraction returns None when no tools present."""
        result = {"other": "data"}
        extracted = mcp_hook._extract_available_tools(result)
        assert extracted is None

    @pytest.mark.unit
    def test_calculate_duration_with_valid_times(self, mcp_hook):
        """Test duration calculation with valid start and end times (Unix timestamps)."""
        start_time_us = 1672574400000000  # 2023-01-01T12:00:00Z in microseconds
        end_time_us = 1672574400750000    # 750ms later
        duration = mcp_hook._calculate_duration(start_time_us, end_time_us)
        assert duration == 750

    @pytest.mark.unit
    def test_calculate_duration_with_missing_times(self, mcp_hook):
        """Test duration calculation with missing times."""
        assert mcp_hook._calculate_duration(None, None) == 0
        assert mcp_hook._calculate_duration(datetime.now(), None) == 0
        assert mcp_hook._calculate_duration(None, datetime.now()) == 0

    @pytest.mark.unit
    def test_generate_step_description_tool_list(self, mcp_hook):
        """Test step description generation for tool list operations."""
        description = mcp_hook._generate_step_description("tool_list", "k8s-server", None, {})
        assert description == "Discover available tools from k8s-server"

    @pytest.mark.unit
    def test_generate_step_description_kubectl_with_namespace(self, mcp_hook):
        """Test step description generation for kubectl with namespace."""
        args = {"tool_arguments": {"namespace": "production"}}
        description = mcp_hook._generate_step_description("tool_call", "k8s-server", "kubectl_get_pods", args)
        assert description == "Execute kubectl_get_pods in production namespace"

    @pytest.mark.unit
    def test_generate_step_description_kubectl_without_namespace(self, mcp_hook):
        """Test step description generation for kubectl without namespace."""
        args = {"tool_arguments": {}}
        description = mcp_hook._generate_step_description("tool_call", "k8s-server", "kubectl_status", args)
        assert description == "Execute Kubernetes command kubectl_status"

    @pytest.mark.unit
    def test_generate_step_description_file_operation_with_path(self, mcp_hook):
        """Test step description generation for file operations with path."""
        args = {"tool_arguments": {"path": "/etc/config.yaml"}}
        description = mcp_hook._generate_step_description("tool_call", "fs-server", "file_read", args)
        assert description == "File operation file_read on /etc/config.yaml"

    @pytest.mark.unit
    def test_generate_step_description_file_operation_without_path(self, mcp_hook):
        """Test step description generation for file operations without path."""
        args = {"tool_arguments": {}}
        description = mcp_hook._generate_step_description("tool_call", "fs-server", "file_list", args)
        assert description == "Execute file operation file_list"

    @pytest.mark.unit
    def test_generate_step_description_generic_tool(self, mcp_hook):
        """Test step description generation for generic tools."""
        args = {}
        description = mcp_hook._generate_step_description("tool_call", "api-server", "weather_check", args)
        assert description == "Execute weather_check via api-server"

    @pytest.mark.unit
    def test_generate_step_description_fallback(self, mcp_hook):
        """Test step description generation fallback case."""
        description = mcp_hook._generate_step_description("unknown", "test-server", None, {})
        assert description == "Communicate with test-server"


if __name__ == "__main__":
    pytest.main([__file__]) 