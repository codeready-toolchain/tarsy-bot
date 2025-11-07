"""
Unit tests for typed hook system.

Tests the typed hook infrastructure that provides type-safe
interaction logging to history service.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.hooks.hook_context import BaseHook
from tarsy.hooks.history_hooks import (
    LLMHistoryHook,
    MCPHistoryHook,
    StageExecutionHistoryHook,
)
from tarsy.models.constants import StageStatus, MAX_LLM_MESSAGE_CONTENT_SIZE
from tarsy.models.db_models import StageExecution
from tarsy.models.unified_interactions import LLMInteraction, MCPInteraction, LLMConversation, LLMMessage, MessageRole
from tarsy.services.history_service import HistoryService


@pytest.mark.unit
class TestBaseHook:
    """Test the base typed hook functionality."""
    
    def test_base_typed_hook_initialization(self):
        """Test base hook can be initialized with name."""
        # Create a concrete implementation for testing
        class TestHook(BaseHook[LLMInteraction]):
            async def execute(self, interaction: LLMInteraction) -> None:
                pass
        
        hook = TestHook("test_hook")
        assert hook.name == "test_hook"
    
    def test_base_typed_hook_is_abstract(self):
        """Test that BaseHook cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseHook("test")


@pytest.mark.unit  
class TestLLMHistoryHook:
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
        return LLMHistoryHook(mock_history_service)
    
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
        hook = LLMHistoryHook(mock_history_service)
        assert hook.name == "llm_history"
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
        with patch('tarsy.hooks.history_hooks._apply_llm_interaction_truncation') as mock_truncate:
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
class TestMCPHistoryHook:
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
        return MCPHistoryHook(mock_history_service)
    
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
        hook = MCPHistoryHook(mock_history_service)
        assert hook.name == "mcp_history"
        assert hook.history_service == mock_history_service
    
    @pytest.mark.asyncio
    async def test_execute_success(self, mcp_hook, mock_history_service, sample_mcp_interaction):
        """Test successful execution logs interaction."""
        await mcp_hook.execute(sample_mcp_interaction)
        
        mock_history_service.store_mcp_interaction.assert_called_once_with(sample_mcp_interaction)


@pytest.mark.unit
class TestStageExecutionHistoryHook:
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
        return StageExecutionHistoryHook(mock_history_service)
    
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
        hook = StageExecutionHistoryHook(mock_history_service)
        assert hook.name == "stage_history"
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
class TestStageExecutionEventHook:
    """Test typed stage execution event hook for real-time event publishing."""
    
    @pytest.fixture
    def event_hook(self):
        """Create stage execution event hook."""
        from tarsy.hooks.event_hooks import StageExecutionEventHook
        return StageExecutionEventHook()
    
    @pytest.fixture
    def active_stage_execution(self):
        """Create active stage execution."""
        return StageExecution(
            execution_id="test-stage-execution-0",
            session_id="test-session",
            stage_id="test-stage-0",
            stage_index=0,
            stage_name="Test Stage",
            agent="KubernetesAgent",
            status=StageStatus.ACTIVE.value,
            started_at_us=1640995200000000
        )
    
    @pytest.fixture
    def completed_stage_execution(self):
        """Create completed stage execution."""
        return StageExecution(
            execution_id="test-stage-execution-0",
            session_id="test-session",
            stage_id="test-stage-0",
            stage_index=0,
            stage_name="Test Stage",
            agent="KubernetesAgent",
            status=StageStatus.COMPLETED.value,
            started_at_us=1640995200000000
        )
    
    @pytest.fixture
    def failed_stage_execution(self):
        """Create failed stage execution."""
        return StageExecution(
            execution_id="test-stage-execution-0",
            session_id="test-session",
            stage_id="test-stage-0",
            stage_index=0,
            stage_name="Test Stage",
            agent="KubernetesAgent",
            status=StageStatus.FAILED.value,
            started_at_us=1640995200000000
        )
    
    @pytest.fixture
    def partial_stage_execution(self):
        """Create partial stage execution."""
        return StageExecution(
            execution_id="test-stage-execution-0",
            session_id="test-session",
            stage_id="test-stage-0",
            stage_index=0,
            stage_name="Test Stage",
            agent="KubernetesAgent",
            status=StageStatus.PARTIAL.value,
            started_at_us=1640995200000000
        )
    
    def test_hook_initialization(self, event_hook):
        """Test hook initializes correctly."""
        assert event_hook.name == "stage_event"
    
    @pytest.mark.asyncio
    async def test_execute_active_status_publishes_started(self, event_hook, active_stage_execution):
        """Test that ACTIVE status publishes stage.started event."""
        with patch("tarsy.services.events.event_helpers.publish_stage_started", new_callable=AsyncMock) as mock_started:
            with patch("tarsy.services.events.event_helpers.publish_stage_completed", new_callable=AsyncMock) as mock_completed:
                await event_hook.execute(active_stage_execution)
                
                mock_started.assert_called_once_with(
                    session_id="test-session",
                    stage_id="test-stage-execution-0",
                    stage_name="Test Stage",
                    chat_id=None
                )
                mock_completed.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_execute_completed_status_publishes_completed_with_string_value(self, event_hook, completed_stage_execution):
        """Test that COMPLETED status publishes stage.completed event with string value."""
        with patch("tarsy.services.events.event_helpers.publish_stage_started", new_callable=AsyncMock) as mock_started:
            with patch("tarsy.services.events.event_helpers.publish_stage_completed", new_callable=AsyncMock) as mock_completed:
                await event_hook.execute(completed_stage_execution)
                
                mock_started.assert_not_called()
                mock_completed.assert_called_once_with(
                    session_id="test-session",
                    stage_id="test-stage-execution-0",
                    stage_name="Test Stage",
                    status="completed",  # Verify it's a string, not enum
                    chat_id=None
                )
    
    @pytest.mark.asyncio
    async def test_execute_failed_status_publishes_completed_with_string_value(self, event_hook, failed_stage_execution):
        """Test that FAILED status publishes stage.completed event with string value."""
        with patch("tarsy.services.events.event_helpers.publish_stage_started", new_callable=AsyncMock) as mock_started:
            with patch("tarsy.services.events.event_helpers.publish_stage_completed", new_callable=AsyncMock) as mock_completed:
                await event_hook.execute(failed_stage_execution)
                
                mock_started.assert_not_called()
                mock_completed.assert_called_once_with(
                    session_id="test-session",
                    stage_id="test-stage-execution-0",
                    stage_name="Test Stage",
                    status="failed",  # Verify it's a string, not enum
                    chat_id=None
                )
    
    @pytest.mark.asyncio
    async def test_execute_partial_status_publishes_completed_with_string_value(self, event_hook, partial_stage_execution):
        """Test that PARTIAL status publishes stage.completed event with string value."""
        with patch("tarsy.services.events.event_helpers.publish_stage_started", new_callable=AsyncMock) as mock_started:
            with patch("tarsy.services.events.event_helpers.publish_stage_completed", new_callable=AsyncMock) as mock_completed:
                await event_hook.execute(partial_stage_execution)
                
                mock_started.assert_not_called()
                mock_completed.assert_called_once_with(
                    session_id="test-session",
                    stage_id="test-stage-execution-0",
                    stage_name="Test Stage",
                    status="partial",  # Verify it's a string, not enum
                    chat_id=None
                )