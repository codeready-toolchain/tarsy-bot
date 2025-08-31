"""
Unit tests for typed hook system.

Tests the new typed hook infrastructure that provides type-safe
interaction logging and dashboard updates.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.hooks.typed_context import BaseTypedHook
from tarsy.hooks.typed_dashboard_hooks import (
    TypedLLMDashboardHook,
    TypedMCPDashboardHook,
)
from tarsy.hooks.typed_history_hooks import (
    TypedLLMHistoryHook,
    TypedMCPHistoryHook,
    TypedStageExecutionHistoryHook,
)
from tarsy.models.constants import StageStatus, MAX_LLM_MESSAGE_CONTENT_SIZE
from tarsy.models.db_models import StageExecution
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction, LLMConversation, LLMMessage, MessageRole
from tarsy.services.dashboard_broadcaster import DashboardBroadcaster
from tarsy.services.history_service import HistoryService


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
        service.store_llm_interaction = Mock(return_value=True)
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
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
                LLMMessage(role=MessageRole.USER, content="test"),
                LLMMessage(role=MessageRole.ASSISTANT, content="response")
            ]),
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
        
        mock_history_service.store_llm_interaction.assert_called_once_with(sample_llm_interaction)
    
    @pytest.mark.asyncio
    async def test_execute_handles_service_error(self, llm_hook, mock_history_service, sample_llm_interaction):
        """Test execution handles history service errors gracefully."""
        mock_history_service.store_llm_interaction.side_effect = Exception("Database error")
        
        # Should raise the exception (hook doesn't catch it)
        with pytest.raises(Exception, match="Database error"):
            await llm_hook.execute(sample_llm_interaction)
    
    @pytest.mark.asyncio
    async def test_execute_applies_truncation(self, llm_hook, mock_history_service, sample_llm_interaction):
        """Test that execute applies content truncation before storing."""
        with patch('tarsy.hooks.typed_history_hooks._apply_llm_interaction_truncation') as mock_truncate:
            # Configure mock to return a modified interaction
            truncated_interaction = sample_llm_interaction.model_copy()
            mock_truncate.return_value = truncated_interaction
            
            await llm_hook.execute(sample_llm_interaction)
            
            # Verify truncation function was called with original interaction
            mock_truncate.assert_called_once_with(sample_llm_interaction)
            
            # Verify history service was called with truncated interaction
            mock_history_service.store_llm_interaction.assert_called_once_with(truncated_interaction)
    
    @pytest.mark.asyncio
    async def test_execute_with_large_conversation(self, llm_hook, mock_history_service):
        """Test execution with large conversation that requires truncation."""
        # Create interaction with large user message
        large_content = "X" * (MAX_LLM_MESSAGE_CONTENT_SIZE + 1000)
        large_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content=large_content),
            LLMMessage(role=MessageRole.ASSISTANT, content="I understand.")
        ])
        
        interaction = LLMInteraction(
            session_id="test-session",
            model_name="gpt-4",
            provider="openai",
            success=True,
            conversation=large_conversation
        )
        
        await llm_hook.execute(interaction)
        
        # Verify history service was called (with truncated content)
        mock_history_service.store_llm_interaction.assert_called_once()
        
        # Get the actual interaction that was stored
        stored_interaction = mock_history_service.store_llm_interaction.call_args[0][0]
        
        # Verify user message was truncated
        user_message = stored_interaction.conversation.messages[1]
        assert len(user_message.content) <= MAX_LLM_MESSAGE_CONTENT_SIZE + 200  # Allow for metadata
        assert "[HOOK TRUNCATED" in user_message.content


@pytest.mark.unit
class TestTypedMCPHistoryHook:
    """Test typed MCP history hook."""
    
    @pytest.fixture
    def mock_history_service(self):
        """Mock history service."""
        service = Mock(spec=HistoryService)
        service.store_mcp_interaction = Mock(return_value=True)
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
        
        mock_history_service.store_mcp_interaction.assert_called_once_with(sample_mcp_interaction)


@pytest.mark.unit
class TestTypedStageExecutionHistoryHook:
    """Test typed stage execution history hook - covers the bug fix for stage creation."""
    
    @pytest.fixture
    def mock_history_service(self):
        """Mock history service."""
        service = Mock(spec=HistoryService)
        service.create_stage_execution = AsyncMock(return_value="stage-exec-123")
        service.update_stage_execution = AsyncMock(return_value=True)
        return service
    
    @pytest.fixture
    def stage_hook(self, mock_history_service):
        """Create stage execution history hook."""
        return TypedStageExecutionHistoryHook(mock_history_service)
    
    @pytest.fixture
    def new_stage_execution(self):
        """Create new stage execution (started_at_us=None)."""
        return StageExecution(
            session_id="test-session",
            stage_id="test-stage-0",
            stage_index=0,
            stage_name="Test Stage",
            agent="KubernetesAgent",
            status=StageStatus.PENDING.value
            # started_at_us=None (default) - indicates new creation
        )
    
    @pytest.fixture
    def existing_stage_execution(self):
        """Create existing stage execution (has started_at_us)."""
        return StageExecution(
            session_id="test-session",
            stage_id="test-stage-0", 
            stage_index=0,
            stage_name="Test Stage",
            agent="KubernetesAgent",
            status=StageStatus.ACTIVE.value,
            started_at_us=1640995200000000  # Has start time - indicates existing record
        )
    
    def test_hook_initialization(self, mock_history_service):
        """Test hook initializes correctly."""
        hook = TypedStageExecutionHistoryHook(mock_history_service)
        assert hook.name == "typed_stage_history"
        assert hook.history_service == mock_history_service
    
    @pytest.mark.asyncio
    async def test_execute_creates_new_stage(self, stage_hook, mock_history_service, new_stage_execution):
        """Test that new stage execution (started_at_us=None) calls create."""
        await stage_hook.execute(new_stage_execution)
        
        # Should call create, not update
        mock_history_service.create_stage_execution.assert_called_once_with(new_stage_execution)
        mock_history_service.update_stage_execution.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_execute_updates_existing_stage(self, stage_hook, mock_history_service, existing_stage_execution):
        """Test that existing stage execution (has started_at_us) calls update."""
        await stage_hook.execute(existing_stage_execution)
        
        # Should call update, not create
        mock_history_service.update_stage_execution.assert_called_once_with(existing_stage_execution)
        mock_history_service.create_stage_execution.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_execute_handles_create_error(self, stage_hook, mock_history_service, new_stage_execution):
        """Test that create errors are properly propagated."""
        mock_history_service.create_stage_execution.side_effect = RuntimeError("Failed to create stage")
        
        with pytest.raises(RuntimeError, match="Failed to create stage"):
            await stage_hook.execute(new_stage_execution)
    
    @pytest.mark.asyncio
    async def test_execute_handles_update_error(self, stage_hook, mock_history_service, existing_stage_execution):
        """Test that update errors are properly propagated."""
        mock_history_service.update_stage_execution.side_effect = RuntimeError("Failed to update stage")
        
        with pytest.raises(RuntimeError, match="Failed to update stage"):
            await stage_hook.execute(existing_stage_execution)


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
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
                LLMMessage(role=MessageRole.USER, content="test"),
                LLMMessage(role=MessageRole.ASSISTANT, content="response")
            ]),
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
    
    @pytest.mark.asyncio
    async def test_execute_applies_truncation(self, dashboard_hook, mock_dashboard_broadcaster, sample_llm_interaction):
        """Test that execute applies content truncation before broadcasting."""
        with patch('tarsy.hooks.typed_dashboard_hooks._apply_llm_interaction_truncation') as mock_truncate:
            # Configure mock to return a modified interaction
            truncated_interaction = sample_llm_interaction.model_copy()
            mock_truncate.return_value = truncated_interaction
            
            await dashboard_hook.execute(sample_llm_interaction)
            
            # Verify truncation function was called with original interaction
            mock_truncate.assert_called_once_with(sample_llm_interaction)
            
            # Verify dashboard broadcaster was called
            mock_dashboard_broadcaster.broadcast_interaction_update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_with_large_conversation(self, dashboard_hook, mock_dashboard_broadcaster):
        """Test execution with large conversation that requires truncation."""
        # Create interaction with large user message
        large_content = "X" * (MAX_LLM_MESSAGE_CONTENT_SIZE + 1000)
        large_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content=large_content),
            LLMMessage(role=MessageRole.ASSISTANT, content="I understand.")
        ])
        
        interaction = LLMInteraction(
            session_id="test-session",
            model_name="gpt-4",
            provider="openai",
            success=True,
            conversation=large_conversation
        )
        
        await dashboard_hook.execute(interaction)
        
        # Verify dashboard broadcaster was called
        mock_dashboard_broadcaster.broadcast_interaction_update.assert_called_once()
        
        # Get the actual update data that was broadcast
        call_args = mock_dashboard_broadcaster.broadcast_interaction_update.call_args
        update_data = call_args[1]["update_data"]
        
        # Verify the conversation in the update data was truncated
        conversation_data = update_data["conversation"]
        user_message_content = conversation_data["messages"][1]["content"]
        assert len(user_message_content) <= MAX_LLM_MESSAGE_CONTENT_SIZE + 200  # Allow for metadata
        assert "[HOOK TRUNCATED" in user_message_content


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
        mock_history_service.store_llm_interaction = Mock(return_value=True)
        
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
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
                LLMMessage(role=MessageRole.USER, content="test"),
                LLMMessage(role=MessageRole.ASSISTANT, content="response")
            ]),
            duration_ms=1500
        )
        
        # Execute both hooks
        await history_hook.execute(interaction)
        await dashboard_hook.execute(interaction)
        
        # Verify both executed
        mock_history_service.store_llm_interaction.assert_called_once_with(interaction)
        mock_broadcaster.broadcast_interaction_update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_stage_execution_integration(self):
        """Integration test for stage execution hook - verifies the bug fix."""
        # This test ensures stage execution records are properly created
        # and covers the specific bug we fixed
        
        mock_history_service = Mock(spec=HistoryService)
        mock_history_service.create_stage_execution = AsyncMock(return_value="stage-exec-integration")
        
        mock_broadcaster = AsyncMock(spec=DashboardBroadcaster)
        mock_broadcaster.broadcast_session_update = AsyncMock(return_value=2)
        
        # Create hooks
        from tarsy.hooks.typed_dashboard_hooks import TypedStageExecutionDashboardHook
        from tarsy.hooks.typed_history_hooks import TypedStageExecutionHistoryHook
        
        history_hook = TypedStageExecutionHistoryHook(mock_history_service)
        dashboard_hook = TypedStageExecutionDashboardHook(mock_broadcaster)
        
        # Create new stage execution (the key is started_at_us=None)
        stage_execution = StageExecution(
            session_id="integration-test-session",
            stage_id="integration-stage-0", 
            stage_index=0,
            stage_name="Integration Test Stage",
            agent="KubernetesAgent",
            status=StageStatus.PENDING.value
            # started_at_us=None (default) - this was the key bug!
        )
        
        # Execute both hooks
        await history_hook.execute(stage_execution)
        await dashboard_hook.execute(stage_execution)
        
        # Verify stage was created (not updated) - this is the bug fix
        mock_history_service.create_stage_execution.assert_called_once_with(stage_execution)
        mock_broadcaster.broadcast_session_update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_llm_truncation_integration_end_to_end(self):
        """Integration test for LLM interaction truncation across history and dashboard hooks."""
        # Create real services (but mocked externals)
        mock_history_service = Mock(spec=HistoryService)
        mock_history_service.store_llm_interaction = Mock(return_value=True)
        
        mock_broadcaster = AsyncMock(spec=DashboardBroadcaster)
        mock_broadcaster.broadcast_interaction_update = AsyncMock(return_value=3)
        
        # Create hooks
        history_hook = TypedLLMHistoryHook(mock_history_service)
        dashboard_hook = TypedLLMDashboardHook(mock_broadcaster)
        
        # Create interaction with large user message that requires truncation
        large_content = "Z" * (MAX_LLM_MESSAGE_CONTENT_SIZE + 2000)
        large_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.USER, content=large_content),
            LLMMessage(role=MessageRole.ASSISTANT, content="I'll help you with that large request.")
        ])
        
        interaction = LLMInteraction(
            session_id="integration-truncation-test",
            model_name="gpt-4",
            provider="openai",
            success=True,
            conversation=large_conversation
        )
        
        # Execute both hooks
        await history_hook.execute(interaction)
        await dashboard_hook.execute(interaction)
        
        # Verify both hooks executed
        mock_history_service.store_llm_interaction.assert_called_once()
        mock_broadcaster.broadcast_interaction_update.assert_called_once()
        
        # Verify history hook received truncated content
        history_stored_interaction = mock_history_service.store_llm_interaction.call_args[0][0]
        history_user_msg = history_stored_interaction.conversation.messages[1]
        assert len(history_user_msg.content) <= MAX_LLM_MESSAGE_CONTENT_SIZE + 200
        assert "[HOOK TRUNCATED" in history_user_msg.content
        
        # Verify dashboard hook received truncated content
        dashboard_call_args = mock_broadcaster.broadcast_interaction_update.call_args
        dashboard_conversation = dashboard_call_args[1]["update_data"]["conversation"]
        dashboard_user_msg = dashboard_conversation["messages"][1]["content"]
        assert len(dashboard_user_msg) <= MAX_LLM_MESSAGE_CONTENT_SIZE + 200
        assert "[HOOK TRUNCATED" in dashboard_user_msg
        
        # Verify original interaction was not modified
        original_user_msg = interaction.conversation.messages[1]
        assert len(original_user_msg.content) > MAX_LLM_MESSAGE_CONTENT_SIZE
        assert "[HOOK TRUNCATED" not in original_user_msg.content