"""
Tests for typed context system.

Tests the typed context manager system that ensures proper data flow
from service methods to hooks without contamination or type mismatches.
"""


import pytest

from tarsy.hooks.typed_context import (
    BaseTypedHook,
    InteractionHookContext,
    TypedHookManager,
    get_typed_hook_manager,
    llm_interaction_context,
    mcp_interaction_context,
)
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction


class TestLLMHook(BaseTypedHook[LLMInteraction]):
    """Test LLM hook implementation."""
    
    def __init__(self, name: str = "test_llm_hook"):
        super().__init__(name)
        self.interactions_received = []
        
    async def execute(self, interaction: LLMInteraction) -> None:
        self.interactions_received.append(interaction)


class TestMCPHook(BaseTypedHook[MCPInteraction]):
    """Test MCP hook implementation."""
    
    def __init__(self, name: str = "test_mcp_hook"):
        super().__init__(name)
        self.interactions_received = []
        
    async def execute(self, interaction: MCPInteraction) -> None:
        self.interactions_received.append(interaction)


@pytest.mark.unit
class TestBaseTypedHook:
    """Test BaseTypedHook functionality."""
    
    def test_initialization(self):
        """Test hook initialization with name."""
        hook = TestLLMHook("my_hook")
        assert hook.name == "my_hook"
    
    def test_abstract_nature(self):
        """Test that BaseTypedHook cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseTypedHook("test")
    
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
class TestTypedHookManager:
    """Test TypedHookManager functionality."""
    
    @pytest.fixture
    def manager(self):
        """Create a TypedHookManager instance."""
        return TypedHookManager()
    
    def test_initialization(self, manager):
        """Test TypedHookManager initialization."""
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
    
    def test_get_typed_hook_manager(self):
        """Test get_typed_hook_manager factory function."""
        manager = get_typed_hook_manager()
        assert isinstance(manager, TypedHookManager)
        
        # Should return same instance (singleton behavior)
        manager2 = get_typed_hook_manager()
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