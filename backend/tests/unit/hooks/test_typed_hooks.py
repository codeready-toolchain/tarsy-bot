"""
Unit tests for typed hook system.

Tests the new typed hook infrastructure that provides type-safe
interaction logging and dashboard updates.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from tarsy.hooks.typed_history_hooks import TypedLLMHistoryHook, TypedMCPHistoryHook
from tarsy.hooks.typed_dashboard_hooks import TypedLLMDashboardHook, TypedMCPDashboardHook
from tarsy.hooks.typed_context import BaseTypedHook
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction
from tarsy.services.history_service import HistoryService
from tarsy.services.dashboard_broadcaster import DashboardBroadcaster


@pytest.mark.unit
class TestBaseTypedHook:
    """Test the base typed hook functionality."""
    
    def test_base_typed_hook_initialization(self):
        """Test base hook can be initialized with name."""
        # Create a concrete implementation for testing
        class TestHook(BaseTypedHook[LLMInteraction]):
            async def execute(self, interaction: LLMInteraction) -> None:
                pass
        
        hook = TestHook("test_hook")
        assert hook.name == "test_hook"
    
    def test_base_typed_hook_is_abstract(self):
        """Test that BaseTypedHook cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseTypedHook("test")


@pytest.mark.unit  
class TestTypedLLMHistoryHook:
    """Test typed LLM history hook."""
    
    @pytest.fixture
    def mock_history_service(self):
        """Mock history service."""
        service = Mock(spec=HistoryService)
        service.log_llm_interaction = Mock(return_value=True)
        return service
    
    @pytest.fixture
    def llm_hook(self, mock_history_service):
        """Create LLM history hook."""
        return TypedLLMHistoryHook(mock_history_service)
    
    @pytest.fixture
    def sample_llm_interaction(self):
        """Create sample LLM interaction."""
        return LLMInteraction(
            session_id="test-session",
            model_name="gpt-4",
            step_description="Test LLM interaction",
            request_json={"messages": [{"role": "user", "content": "test"}]},
            response_json={"choices": [{"message": {"role": "assistant", "content": "response"}, "finish_reason": "stop"}]},
            duration_ms=1000
        )
    
    def test_hook_initialization(self, mock_history_service):
        """Test hook initializes correctly."""
        hook = TypedLLMHistoryHook(mock_history_service)
        assert hook.name == "typed_llm_history"
        assert hook.history_service == mock_history_service
    
    @pytest.mark.asyncio
    async def test_execute_success(self, llm_hook, mock_history_service, sample_llm_interaction):
        """Test successful execution logs interaction."""
        await llm_hook.execute(sample_llm_interaction)
        
        mock_history_service.log_llm_interaction.assert_called_once_with(sample_llm_interaction)
    
    @pytest.mark.asyncio
    async def test_execute_handles_service_error(self, llm_hook, mock_history_service, sample_llm_interaction):
        """Test execution handles history service errors gracefully."""
        mock_history_service.log_llm_interaction.side_effect = Exception("Database error")
        
        # Should raise the exception (hook doesn't catch it)
        with pytest.raises(Exception, match="Database error"):
            await llm_hook.execute(sample_llm_interaction)


@pytest.mark.unit
class TestTypedMCPHistoryHook:
    """Test typed MCP history hook."""
    
    @pytest.fixture
    def mock_history_service(self):
        """Mock history service."""
        service = Mock(spec=HistoryService)
        service.log_mcp_interaction = Mock(return_value=True)
        return service
    
    @pytest.fixture
    def mcp_hook(self, mock_history_service):
        """Create MCP history hook."""
        return TypedMCPHistoryHook(mock_history_service)
    
    @pytest.fixture
    def sample_mcp_interaction(self):
        """Create sample MCP interaction."""
        return MCPInteraction(
            session_id="test-session",
            server_name="test-server",
            communication_type="tool_call",
            tool_name="test_tool",
            step_description="Test MCP interaction",
            success=True
        )
    
    def test_hook_initialization(self, mock_history_service):
        """Test hook initializes correctly."""
        hook = TypedMCPHistoryHook(mock_history_service)
        assert hook.name == "typed_mcp_history"
        assert hook.history_service == mock_history_service
    
    @pytest.mark.asyncio
    async def test_execute_success(self, mcp_hook, mock_history_service, sample_mcp_interaction):
        """Test successful execution logs interaction."""
        await mcp_hook.execute(sample_mcp_interaction)
        
        mock_history_service.log_mcp_interaction.assert_called_once_with(sample_mcp_interaction)


@pytest.mark.unit
class TestTypedLLMDashboardHook:
    """Test typed LLM dashboard hook."""
    
    @pytest.fixture
    def mock_dashboard_broadcaster(self):
        """Mock dashboard broadcaster."""
        broadcaster = AsyncMock(spec=DashboardBroadcaster)
        broadcaster.broadcast_interaction_update = AsyncMock(return_value=3)
        return broadcaster
    
    @pytest.fixture
    def dashboard_hook(self, mock_dashboard_broadcaster):
        """Create LLM dashboard hook."""
        return TypedLLMDashboardHook(mock_dashboard_broadcaster)
    
    @pytest.fixture
    def sample_llm_interaction(self):
        """Create sample LLM interaction."""
        return LLMInteraction(
            session_id="test-session",
            model_name="gpt-4", 
            step_description="Test LLM interaction",
            request_json={"messages": [{"role": "user", "content": "test"}]},
            response_json={"choices": [{"message": {"role": "assistant", "content": "response"}, "finish_reason": "stop"}]},
            duration_ms=1000
        )
    
    def test_hook_initialization(self, mock_dashboard_broadcaster):
        """Test hook initializes correctly."""
        hook = TypedLLMDashboardHook(mock_dashboard_broadcaster)
        assert hook.name == "typed_llm_dashboard"
        assert hook.dashboard_broadcaster == mock_dashboard_broadcaster
    
    @pytest.mark.asyncio
    async def test_execute_success(self, dashboard_hook, mock_dashboard_broadcaster, sample_llm_interaction):
        """Test successful execution broadcasts update."""
        await dashboard_hook.execute(sample_llm_interaction)
        
        # Verify broadcast was called
        mock_dashboard_broadcaster.broadcast_interaction_update.assert_called_once()
        
        # Check the update data structure
        call_args = mock_dashboard_broadcaster.broadcast_interaction_update.call_args
        assert call_args[1]["session_id"] == "test-session"  # keyword args
        update_data = call_args[1]["update_data"]
        assert update_data["type"] == "llm_interaction"
        assert update_data["session_id"] == "test-session"
    
    @pytest.mark.asyncio 
    async def test_execute_handles_broadcast_error(self, dashboard_hook, mock_dashboard_broadcaster, sample_llm_interaction):
        """Test execution handles broadcast errors gracefully."""
        mock_dashboard_broadcaster.broadcast_interaction_update.side_effect = Exception("Broadcast error")
        
        # Should raise the exception (hook doesn't catch it)
        with pytest.raises(Exception, match="Broadcast error"):
            await dashboard_hook.execute(sample_llm_interaction)


@pytest.mark.unit
class TestTypedMCPDashboardHook:
    """Test typed MCP dashboard hook."""
    
    @pytest.fixture
    def mock_dashboard_broadcaster(self):
        """Mock dashboard broadcaster."""
        broadcaster = AsyncMock(spec=DashboardBroadcaster)
        broadcaster.broadcast_interaction_update = AsyncMock(return_value=3)
        return broadcaster
    
    @pytest.fixture
    def dashboard_hook(self, mock_dashboard_broadcaster):
        """Create MCP dashboard hook."""
        return TypedMCPDashboardHook(mock_dashboard_broadcaster)
    
    @pytest.fixture
    def sample_mcp_interaction(self):
        """Create sample MCP interaction."""
        return MCPInteraction(
            session_id="test-session",
            server_name="test-server",
            communication_type="tool_call",
            tool_name="test_tool",
            step_description="Test MCP interaction",
            success=True
        )
    
    def test_hook_initialization(self, mock_dashboard_broadcaster):
        """Test hook initializes correctly."""
        hook = TypedMCPDashboardHook(mock_dashboard_broadcaster)
        assert hook.name == "typed_mcp_dashboard"
        assert hook.dashboard_broadcaster == mock_dashboard_broadcaster
    
    @pytest.mark.asyncio
    async def test_execute_success(self, dashboard_hook, mock_dashboard_broadcaster, sample_mcp_interaction):
        """Test successful execution broadcasts update."""
        await dashboard_hook.execute(sample_mcp_interaction)
        
        # Verify broadcast was called
        mock_dashboard_broadcaster.broadcast_interaction_update.assert_called_once()
        
        # Check the update data structure
        call_args = mock_dashboard_broadcaster.broadcast_interaction_update.call_args
        assert call_args[1]["session_id"] == "test-session"  # keyword args
        update_data = call_args[1]["update_data"]
        assert update_data["type"] == "mcp_interaction"
        assert update_data["session_id"] == "test-session"


@pytest.mark.integration
class TestTypedHooksIntegration:
    """Integration tests for typed hooks."""
    
    @pytest.mark.asyncio
    async def test_llm_hook_chain_execution(self):
        """Test that LLM hooks can be chained and executed."""
        # Create real services (but mocked externals)
        mock_history_service = Mock(spec=HistoryService)
        mock_history_service.log_llm_interaction = Mock(return_value=True)
        
        mock_broadcaster = AsyncMock(spec=DashboardBroadcaster)
        mock_broadcaster.broadcast_interaction_update = AsyncMock(return_value=3)
        
        # Create hooks
        history_hook = TypedLLMHistoryHook(mock_history_service)
        dashboard_hook = TypedLLMDashboardHook(mock_broadcaster)
        
        # Create interaction
        interaction = LLMInteraction(
            session_id="integration-test",
            model_name="gpt-4",
            step_description="Integration test interaction", 
            request_json={"messages": [{"role": "user", "content": "test"}]},
            response_json={"choices": [{"message": {"role": "assistant", "content": "response"}, "finish_reason": "stop"}]},
            duration_ms=1500
        )
        
        # Execute both hooks
        await history_hook.execute(interaction)
        await dashboard_hook.execute(interaction)
        
        # Verify both executed
        mock_history_service.log_llm_interaction.assert_called_once_with(interaction)
        mock_broadcaster.broadcast_interaction_update.assert_called_once()