"""
Tests for typed context system.

Tests the typed context manager system that ensures proper data flow
from service methods to hooks without contamination or type mismatches.
"""


import pytest
from unittest.mock import Mock, AsyncMock

from tarsy.hooks.hook_context import (
    BaseHook,
    InteractionHookContext,
    HookManager,
    get_hook_manager,
    llm_interaction_context,
    mcp_interaction_context,
    _apply_llm_interaction_truncation,
)
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction, LLMConversation, LLMMessage, MessageRole
from tarsy.models.db_models import StageExecution
from tarsy.models.constants import MAX_LLM_MESSAGE_CONTENT_SIZE


class TestLLMHook(BaseHook[LLMInteraction]):
    """Test LLM hook implementation."""
    
    def __init__(self, name: str = "test_llm_hook"):
        super().__init__(name)
        self.interactions_received = []
        
    async def execute(self, interaction: LLMInteraction) -> None:
        self.interactions_received.append(interaction)


class TestMCPHook(BaseHook[MCPInteraction]):
    """Test MCP hook implementation."""
    
    def __init__(self, name: str = "test_mcp_hook"):
        super().__init__(name)
        self.interactions_received = []
        
    async def execute(self, interaction: MCPInteraction) -> None:
        self.interactions_received.append(interaction)


@pytest.mark.unit
class TestBaseHook:
    """Test BaseHook functionality."""
    
    def test_initialization(self):
        """Test hook initialization with name."""
        hook = TestLLMHook("my_hook")
        assert hook.name == "my_hook"
    
    def test_abstract_nature(self):
        """Test that BaseHook cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseHook("test")
    
    @pytest.mark.asyncio
    async def test_execute_method(self):
        """Test execute method is properly implemented."""
        hook = TestLLMHook()
        interaction = LLMInteraction(
            session_id="test_session",
            request_data={"prompt": "test"},
            response_data={"content": "response"},
            timestamp_start=1234567890.0,
            timestamp_end=1234567891.0,
            provider="test_provider"
        )
        
        await hook.execute(interaction)
        
        assert len(hook.interactions_received) == 1
        assert hook.interactions_received[0] == interaction


@pytest.mark.unit
class TestHookManager:
    """Test HookManager functionality."""
    
    @pytest.fixture
    def manager(self):
        """Create a HookManager instance."""
        return HookManager()
    
    def test_initialization(self, manager):
        """Test HookManager initialization."""
        assert isinstance(manager.llm_hooks, dict)
        assert isinstance(manager.mcp_hooks, dict)
        assert isinstance(manager.mcp_list_hooks, dict)
        assert len(manager.llm_hooks) == 0
        assert len(manager.mcp_hooks) == 0
        assert len(manager.mcp_list_hooks) == 0
    
    def test_register_llm_hook(self, manager):
        """Test registering an LLM hook."""
        hook = TestLLMHook("test_llm_hook")
        manager.register_llm_hook(hook)
        
        assert len(manager.llm_hooks) == 1
        assert "test_llm_hook" in manager.llm_hooks
        assert manager.llm_hooks["test_llm_hook"] == hook
    
    def test_register_mcp_hook(self, manager):
        """Test registering an MCP hook."""
        hook = TestMCPHook("test_mcp_hook")
        manager.register_mcp_hook(hook)
        
        assert len(manager.mcp_hooks) == 1
        assert "test_mcp_hook" in manager.mcp_hooks
        assert manager.mcp_hooks["test_mcp_hook"] == hook
    
    def test_register_mcp_list_hook(self, manager):
        """Test registering an MCP list hook."""
        hook = TestMCPHook("test_mcp_list_hook")
        manager.register_mcp_list_hook(hook)
        
        assert len(manager.mcp_list_hooks) == 1
        assert "test_mcp_list_hook" in manager.mcp_list_hooks
        assert manager.mcp_list_hooks["test_mcp_list_hook"] == hook
    
    @pytest.mark.asyncio
    async def test_trigger_llm_hooks(self, manager):
        """Test triggering LLM hooks."""
        hook1 = TestLLMHook("hook1")
        hook2 = TestLLMHook("hook2")
        
        manager.register_llm_hook(hook1)
        manager.register_llm_hook(hook2)
        
        interaction = LLMInteraction(
            session_id="test_session",
            request_data={"prompt": "test"},
            response_data={"content": "response"},
            timestamp_start=1234567890.0,
            timestamp_end=1234567891.0,
            provider="test_provider"
        )
        
        results = await manager.trigger_llm_hooks(interaction)
        
        assert len(results) == 2
        assert results["hook1"] is True
        assert results["hook2"] is True
        assert len(hook1.interactions_received) == 1
        assert len(hook2.interactions_received) == 1
    
    @pytest.mark.asyncio
    async def test_trigger_mcp_hooks(self, manager):
        """Test triggering MCP hooks."""
        hook1 = TestMCPHook("hook1")
        hook2 = TestMCPHook("hook2")
        
        manager.register_mcp_hook(hook1)
        manager.register_mcp_hook(hook2)
        
        interaction = MCPInteraction(
            session_id="test_session",
            server_name="test_server",
            tool_name="test_tool",
            arguments={"param": "value"},
            result={"output": "result"},
            timestamp_start=1234567890.0,
            timestamp_end=1234567891.0
        )
        
        results = await manager.trigger_mcp_hooks(interaction)
        
        assert len(results) == 2
        assert results["hook1"] is True
        assert results["hook2"] is True
        assert len(hook1.interactions_received) == 1
        assert len(hook2.interactions_received) == 1


@pytest.mark.unit
class TestFactoryFunctions:
    """Test factory functions."""
    
    def test_get_hook_manager(self):
        """Test get_hook_manager factory function."""
        manager = get_hook_manager()
        assert isinstance(manager, HookManager)
        
        # Should return same instance (singleton behavior)
        manager2 = get_hook_manager()
        assert manager is manager2
    
    @pytest.mark.asyncio
    async def test_llm_interaction_context(self):
        """Test llm_interaction_context factory function."""
        session_id = "test_session"
        request_data = {"prompt": "test"}
        
        async with llm_interaction_context(session_id, request_data) as ctx:
            assert isinstance(ctx, InteractionHookContext)
            assert ctx.get_request_id() is not None
    
    @pytest.mark.asyncio
    async def test_mcp_interaction_context(self):
        """Test mcp_interaction_context factory function."""
        session_id = "test_session"
        server_name = "test_server"
        tool_name = "test_tool"
        arguments = {"param": "value"}
        
        async with mcp_interaction_context(session_id, server_name, tool_name, arguments) as ctx:
            assert isinstance(ctx, InteractionHookContext)
            assert ctx.get_request_id() is not None


class TestBaseHookErrorHandling:
    """Test error handling in BaseHook."""
    
    @pytest.fixture
    def failing_hook(self):
        """Create a hook that always throws an exception."""
        class FailingHook(BaseHook[LLMInteraction]):
            async def execute(self, interaction: LLMInteraction) -> None:
                raise ValueError("Test error")
        
        return FailingHook("failing_hook")
    
    @pytest.mark.asyncio
    async def test_safe_execute_disabled_hook_returns_false(self):
        """Test that disabled hook returns False without executing."""
        class DummyHook(BaseHook[LLMInteraction]):
            async def execute(self, interaction: LLMInteraction) -> None:
                pass
        
        hook = DummyHook("disabled_hook")
        hook.is_enabled = False
        
        interaction = LLMInteraction(session_id="test", provider="openai", model_name="gpt-4", success=True)
        result = await hook.safe_execute(interaction)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_safe_execute_handles_exceptions(self, failing_hook):
        """Test that exceptions are caught and logged."""
        interaction = LLMInteraction(session_id="test", provider="openai", model_name="gpt-4", success=True)
        
        result = await failing_hook.safe_execute(interaction)
        
        assert result is False
        assert failing_hook.error_count == 1
        assert failing_hook.is_enabled is True  # Should still be enabled after first error
    
    @pytest.mark.asyncio
    async def test_safe_execute_disables_hook_after_max_errors(self, failing_hook):
        """Test that hook gets disabled after max errors."""
        failing_hook.max_errors = 2
        interaction = LLMInteraction(session_id="test", provider="openai", model_name="gpt-4", success=True)
        
        # First error
        result1 = await failing_hook.safe_execute(interaction)
        assert result1 is False
        assert failing_hook.error_count == 1
        assert failing_hook.is_enabled is True
        
        # Second error - should disable hook
        result2 = await failing_hook.safe_execute(interaction)
        assert result2 is False
        assert failing_hook.error_count == 2
        assert failing_hook.is_enabled is False
    
    @pytest.mark.asyncio
    async def test_safe_execute_resets_error_count_on_success(self):
        """Test that error count is reset on successful execution."""
        class SometimesFailingHook(BaseHook[LLMInteraction]):
            def __init__(self, name: str):
                super().__init__(name)
                self.should_fail = True
                
            async def execute(self, interaction: LLMInteraction) -> None:
                if self.should_fail:
                    raise ValueError("Test error")
        
        hook = SometimesFailingHook("sometimes_failing")
        interaction = LLMInteraction(session_id="test", provider="openai", model_name="gpt-4", success=True)
        
        # First call fails
        result1 = await hook.safe_execute(interaction)
        assert result1 is False
        assert hook.error_count == 1
        
        # Second call succeeds
        hook.should_fail = False
        result2 = await hook.safe_execute(interaction)
        assert result2 is True
        assert hook.error_count == 0


class TestHookManagerRegistration:
    """Test hook registration methods."""
    
    @pytest.fixture
    def hook_manager(self):
        """Create a fresh HookManager for testing."""
        return HookManager()
    
    def test_register_llm_hook(self, hook_manager):
        """Test registering an LLM hook."""
        class DummyLLMHook(BaseHook[LLMInteraction]):
            async def execute(self, interaction: LLMInteraction) -> None:
                pass
        
        hook = DummyLLMHook("test_llm_hook")
        hook_manager.register_llm_hook(hook)
        
        assert "test_llm_hook" in hook_manager.llm_hooks
        assert hook_manager.llm_hooks["test_llm_hook"] is hook
    
    def test_register_mcp_hook(self, hook_manager):
        """Test registering an MCP hook."""
        class DummyMCPHook(BaseHook[MCPInteraction]):
            async def execute(self, interaction: MCPInteraction) -> None:
                pass
        
        hook = DummyMCPHook("test_mcp_hook")
        hook_manager.register_mcp_hook(hook)
        
        assert "test_mcp_hook" in hook_manager.mcp_hooks
        assert hook_manager.mcp_hooks["test_mcp_hook"] is hook
    
    def test_register_mcp_list_hook(self, hook_manager):
        """Test registering an MCP list hook."""
        class DummyMCPListHook(BaseHook[MCPInteraction]):
            async def execute(self, interaction: MCPInteraction) -> None:
                pass
        
        hook = DummyMCPListHook("test_mcp_list_hook")
        hook_manager.register_mcp_list_hook(hook)
        
        assert "test_mcp_list_hook" in hook_manager.mcp_list_hooks
        assert hook_manager.mcp_list_hooks["test_mcp_list_hook"] is hook
    
    def test_register_stage_hook(self, hook_manager):
        """Test registering a stage execution hook."""
        class DummyStageHook(BaseHook[StageExecution]):
            async def execute(self, stage_execution: StageExecution) -> None:
                pass
        
        hook = DummyStageHook("test_stage_hook")
        hook_manager.register_stage_hook(hook)
        
        assert "test_stage_hook" in hook_manager.stage_hooks
        assert hook_manager.stage_hooks["test_stage_hook"] is hook


class TestInteractionHookContextCompletion:
    """Test completion flows in InteractionHookContext."""
    
    @pytest.fixture
    def hook_manager(self):
        """Mock hook manager for testing."""
        mock_manager = Mock()
        mock_manager.trigger_llm_hooks = AsyncMock()
        mock_manager.trigger_mcp_hooks = AsyncMock()
        mock_manager.trigger_mcp_list_hooks = AsyncMock()
        return mock_manager
    
    @pytest.fixture
    def llm_context(self, hook_manager):
        """Create an LLM interaction context for testing."""
        interaction = LLMInteraction(
            session_id="test_session", 
            provider="openai", 
            model_name="gpt-4", 
            success=False  # Start as unsuccessful
        )
        return InteractionHookContext(interaction, hook_manager)
    
    @pytest.mark.asyncio
    async def test_complete_success_with_dict_result(self, llm_context):
        """Test completing with success using dict result data."""
        result_data = {"provider": "openai", "model_name": "gpt-3.5"}
        
        await llm_context.complete_success(result_data)
        
        assert llm_context.interaction.success is True
        assert llm_context.interaction.provider == "openai"
        assert llm_context.interaction.model_name == "gpt-3.5"
        assert llm_context.interaction.duration_ms is not None
    
    @pytest.mark.asyncio
    async def test_complete_success_with_interaction_object(self, llm_context):
        """Test completing with success using full interaction object."""
        new_interaction = LLMInteraction(
            session_id="test_session",
            provider="claude", 
            model_name="claude-3",
            success=True
        )
        
        await llm_context.complete_success(new_interaction)
        
        assert llm_context.interaction is new_interaction
        assert llm_context.interaction.success is True
        assert llm_context.interaction.provider == "claude"
    
    @pytest.mark.asyncio
    async def test_context_manager_error_handling(self, hook_manager):
        """Test error handling in context manager __aexit__."""
        interaction = LLMInteraction(
            session_id="test_session",
            provider="openai",
            model_name="gpt-4",
            success=False
        )
        context = InteractionHookContext(interaction, hook_manager)
        
        # Simulate an error
        test_exception = ValueError("Test error")
        
        result = await context.__aexit__(ValueError, test_exception, None)
        
        assert result is False  # Don't suppress exception
        assert context.interaction.success is False
        assert context.interaction.error_message == "Test error"
        assert context.interaction.duration_ms is not None
    
    @pytest.mark.asyncio 
    async def test_trigger_appropriate_hooks_llm(self, hook_manager):
        """Test triggering LLM hooks."""
        interaction = LLMInteraction(session_id="test", provider="openai", model_name="gpt-4", success=True)
        context = InteractionHookContext(interaction, hook_manager)
        
        await context._trigger_appropriate_hooks()
        
        hook_manager.trigger_llm_hooks.assert_called_once_with(interaction)
    
    @pytest.mark.asyncio
    async def test_trigger_appropriate_hooks_mcp_tool_call(self, hook_manager):
        """Test triggering MCP hooks for tool calls."""
        interaction = MCPInteraction(
            session_id="test", 
            server_name="test_server", 
            communication_type="tool_call",
            step_description="test"
        )
        context = InteractionHookContext(interaction, hook_manager)
        
        await context._trigger_appropriate_hooks()
        
        hook_manager.trigger_mcp_hooks.assert_called_once_with(interaction)
    
    @pytest.mark.asyncio
    async def test_trigger_appropriate_hooks_mcp_tool_list(self, hook_manager):
        """Test triggering MCP list hooks for tool lists."""
        interaction = MCPInteraction(
            session_id="test",
            server_name="test_server", 
            communication_type="tool_list",
            step_description="test"
        )
        context = InteractionHookContext(interaction, hook_manager)
        
        await context._trigger_appropriate_hooks()
        
        hook_manager.trigger_mcp_list_hooks.assert_called_once_with(interaction)
    
    @pytest.mark.asyncio
    async def test_trigger_appropriate_hooks_unknown_type(self, hook_manager):
        """Test handling of unknown interaction types."""
        # Create a mock interaction that's not LLM or MCP
        unknown_interaction = Mock()
        context = InteractionHookContext(unknown_interaction, hook_manager)
        
        # Should not raise an exception
        await context._trigger_appropriate_hooks()
        
        # No hooks should be triggered
        hook_manager.trigger_llm_hooks.assert_not_called()
        hook_manager.trigger_mcp_hooks.assert_not_called()
        hook_manager.trigger_mcp_list_hooks.assert_not_called()


@pytest.mark.unit
class TestLLMInteractionTruncation:
    """Test the _apply_llm_interaction_truncation utility function."""
    
    @pytest.fixture
    def small_conversation(self):
        """Create a conversation with small content."""
        return LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="What is the capital of France?"),
            LLMMessage(role=MessageRole.ASSISTANT, content="The capital of France is Paris.")
        ])
    
    @pytest.fixture
    def large_user_message_conversation(self):
        """Create a conversation with a large user message exceeding size limit."""
        # Create content that exceeds MAX_LLM_MESSAGE_CONTENT_SIZE (1MB)
        large_content = "X" * (MAX_LLM_MESSAGE_CONTENT_SIZE + 1000)
        return LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content=large_content),
            LLMMessage(role=MessageRole.ASSISTANT, content="I understand your request.")
        ])
    
    @pytest.fixture
    def large_assistant_message_conversation(self):
        """Create a conversation with a large assistant message (should NOT be truncated)."""
        # Create content that exceeds MAX_LLM_MESSAGE_CONTENT_SIZE (1MB)
        large_content = "Y" * (MAX_LLM_MESSAGE_CONTENT_SIZE + 1000)
        return LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Give me a detailed response."),
            LLMMessage(role=MessageRole.ASSISTANT, content=large_content)
        ])
    
    @pytest.fixture
    def mixed_size_conversation(self):
        """Create a conversation with mixed message sizes."""
        large_user_content = "X" * (MAX_LLM_MESSAGE_CONTENT_SIZE + 500)
        large_assistant_content = "Y" * (MAX_LLM_MESSAGE_CONTENT_SIZE + 300)
        return LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content="Small user message"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Small assistant response"),
            LLMMessage(role=MessageRole.USER, content=large_user_content),
            LLMMessage(role=MessageRole.ASSISTANT, content=large_assistant_content),
            LLMMessage(role=MessageRole.USER, content="Another small message")
        ])
    
    def test_no_conversation_returns_original(self):
        """Test that interaction without conversation returns unchanged."""
        interaction = LLMInteraction(
            session_id="test-session",
            model_name="gpt-4",
            provider="openai",
            success=True
        )
        
        result = _apply_llm_interaction_truncation(interaction)
        
        assert result is interaction
        assert result.conversation is None
    
    def test_small_conversation_returns_original(self, small_conversation):
        """Test that conversation with small messages returns unchanged."""
        interaction = LLMInteraction(
            session_id="test-session",
            model_name="gpt-4",
            provider="openai",
            success=True,
            conversation=small_conversation
        )
        
        result = _apply_llm_interaction_truncation(interaction)
        
        assert result is interaction
        assert result.conversation is small_conversation
        
        # Verify no messages were modified
        for original_msg, result_msg in zip(small_conversation.messages, result.conversation.messages):
            assert original_msg.content == result_msg.content
    
    def test_large_user_message_gets_truncated(self, large_user_message_conversation):
        """Test that large user messages are truncated with metadata."""
        interaction = LLMInteraction(
            session_id="test-session",
            model_name="gpt-4",
            provider="openai",
            success=True,
            conversation=large_user_message_conversation
        )
        
        result = _apply_llm_interaction_truncation(interaction)
        
        # Should return a new interaction (not the same object)
        assert result is not interaction
        assert result.conversation is not large_user_message_conversation
        
        # Check that user message was truncated
        truncated_messages = result.conversation.messages
        user_message = truncated_messages[1]  # Second message is the large user message
        
        assert len(user_message.content) <= MAX_LLM_MESSAGE_CONTENT_SIZE + 200  # Allow for truncation marker
        assert "[HOOK TRUNCATED" in user_message.content
        assert "Original size:" in user_message.content
        assert "Hook size:" in user_message.content
        
        # Other messages should remain unchanged
        assert truncated_messages[0].content == "You are a helpful assistant."
        assert truncated_messages[2].content == "I understand your request."
    
    def test_large_assistant_message_not_truncated(self, large_assistant_message_conversation):
        """Test that large assistant messages are NOT truncated."""
        interaction = LLMInteraction(
            session_id="test-session", 
            model_name="gpt-4",
            provider="openai",
            success=True,
            conversation=large_assistant_message_conversation
        )
        
        result = _apply_llm_interaction_truncation(interaction)
        
        # Should return original interaction (no truncation needed)
        assert result is interaction
        assert result.conversation is large_assistant_message_conversation
        
        # Assistant message should remain unchanged
        assistant_message = result.conversation.messages[2]
        assert len(assistant_message.content) > MAX_LLM_MESSAGE_CONTENT_SIZE
        assert "[HOOK TRUNCATED" not in assistant_message.content
    
    def test_mixed_size_conversation_selective_truncation(self, mixed_size_conversation):
        """Test that only large user messages are truncated in mixed conversation."""
        interaction = LLMInteraction(
            session_id="test-session",
            model_name="gpt-4", 
            provider="openai",
            success=True,
            conversation=mixed_size_conversation
        )
        
        result = _apply_llm_interaction_truncation(interaction)
        
        # Should return new interaction due to truncation
        assert result is not interaction
        
        messages = result.conversation.messages
        
        # Check individual messages
        assert messages[0].content == "You are a helpful assistant."  # System - unchanged
        assert messages[1].content == "Small user message"  # Small user - unchanged  
        assert messages[2].content == "Small assistant response"  # Small assistant - unchanged
        assert "[HOOK TRUNCATED" in messages[3].content  # Large user - truncated
        assert len(messages[4].content) > MAX_LLM_MESSAGE_CONTENT_SIZE  # Large assistant - NOT truncated
        assert "[HOOK TRUNCATED" not in messages[4].content
        assert messages[5].content == "Another small message"  # Small user - unchanged
    
    def test_truncation_preserves_conversation_structure(self, large_user_message_conversation):
        """Test that truncation preserves overall conversation structure."""
        interaction = LLMInteraction(
            session_id="test-session",
            model_name="gpt-4",
            provider="openai", 
            success=True,
            conversation=large_user_message_conversation
        )
        
        result = _apply_llm_interaction_truncation(interaction)
        
        # Check conversation structure is preserved
        assert len(result.conversation.messages) == len(large_user_message_conversation.messages)
        
        # Check message roles are preserved
        for original_msg, truncated_msg in zip(large_user_message_conversation.messages, result.conversation.messages):
            assert original_msg.role == truncated_msg.role
    
    def test_truncation_metadata_format(self, large_user_message_conversation):
        """Test that truncation metadata follows expected format."""
        interaction = LLMInteraction(
            session_id="test-session",
            model_name="gpt-4",
            provider="openai",
            success=True,
            conversation=large_user_message_conversation
        )
        
        result = _apply_llm_interaction_truncation(interaction)
        
        # Get the truncated user message
        user_message = result.conversation.messages[1]
        
        # Check metadata format
        assert "[HOOK TRUNCATED - Original size:" in user_message.content
        assert f"Hook size: {MAX_LLM_MESSAGE_CONTENT_SIZE:,} chars]" in user_message.content
        
        # Verify the truncated content starts with original content
        original_content = large_user_message_conversation.messages[1].content
        truncated_content_start = user_message.content[:MAX_LLM_MESSAGE_CONTENT_SIZE]
        expected_start = original_content[:MAX_LLM_MESSAGE_CONTENT_SIZE]
        assert truncated_content_start == expected_start
    
    def test_conversation_with_only_system_message_returns_original(self):
        """Test that conversation with only system message returns unchanged."""
        system_only_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant.")
        ])
        interaction = LLMInteraction(
            session_id="test-session",
            model_name="gpt-4",
            provider="openai",
            success=True,
            conversation=system_only_conversation
        )
        
        result = _apply_llm_interaction_truncation(interaction)
        
        assert result is interaction
        assert result.conversation is system_only_conversation
        assert len(result.conversation.messages) == 1
        assert result.conversation.messages[0].role == MessageRole.SYSTEM