"""
Unit tests for ChatService.

Tests chat lifecycle management, context building, and message processing
with mocked dependencies.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from tarsy.models.db_models import Chat, AlertSession
from tarsy.models.constants import StageStatus, AlertSessionStatus
from tarsy.models.unified_interactions import LLMInteraction, LLMConversation, LLMMessage, MessageRole
from tarsy.models.processing_context import SessionContextData, ChatMessageContext
from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.services.chat_service import ChatService
from tarsy.utils.timestamp import now_us


@pytest.mark.unit
class TestChatService:
    """Test ChatService business logic with mocked dependencies."""
    
    @pytest.fixture
    def mock_history_service(self):
        """Mock history service for testing."""
        return Mock()
    
    @pytest.fixture
    def mock_agent_factory(self):
        """Mock agent factory for testing."""
        return Mock()
    
    @pytest.fixture
    def mock_mcp_client_factory(self):
        """Mock MCP client factory for testing."""
        mock = AsyncMock()
        mock.create_client = AsyncMock(return_value=AsyncMock())
        return mock
    
    @pytest.fixture
    def chat_service(self, mock_history_service, mock_agent_factory, mock_mcp_client_factory):
        """Create ChatService with mocked dependencies."""
        # Mock agent_configs as dict (not Mock) for iteration
        mock_agent_factory.agent_configs = {}
        return ChatService(
            history_service=mock_history_service,
            agent_factory=mock_agent_factory,
            mcp_client_factory=mock_mcp_client_factory
        )
    
    @pytest.fixture
    def sample_session(self):
        """Sample completed session for testing."""
        session = Mock(spec=AlertSession)
        session.session_id = "test-session-123"
        session.status = AlertSessionStatus.COMPLETED.value
        session.chain_id = "kubernetes-investigation"
        session.mcp_selection = None
        session.chain_definition = {
            "stages": [
                {"agent": "KubernetesAgent"},
                {"agent": "DeepDiveAgent"}
            ]
        }
        return session
    
    @pytest.fixture
    def sample_llm_interactions(self):
        """Sample LLM interactions for context capture."""
        return [
            LLMInteraction(
                interaction_id="int-1",
                session_id="test-session-123",
                stage_execution_id="stage-1",
                model_name="gpt-4",
                conversation=LLMConversation(messages=[
                    LLMMessage(role=MessageRole.SYSTEM, content="System"),
                    LLMMessage(role=MessageRole.USER, content="Pod crashed in production"),
                    LLMMessage(role=MessageRole.ASSISTANT, content="Analyzing pod status..."),
                ]),
                tokens_used=100,
                created_at_us=now_us(),
            )
        ]
    
    # ===== create_chat() Tests =====
    
    @pytest.mark.asyncio
    async def test_create_chat_success(
        self, chat_service, mock_history_service, sample_session, sample_llm_interactions
    ):
        """Test successful chat creation for completed session."""
        mock_history_service.get_session.return_value = sample_session
        mock_history_service.get_chat_by_session = AsyncMock(return_value=None)
        mock_history_service.get_llm_interactions_for_session = AsyncMock(
            return_value=sample_llm_interactions
        )
        mock_history_service.create_chat = AsyncMock(return_value=Chat(
            chat_id="new-chat-123",
            session_id="test-session-123",
            created_by="user@example.com",
            conversation_history="Formatted history",
            chain_id="kubernetes-investigation",
            context_captured_at_us=now_us(),
        ))
        
        with patch("tarsy.services.events.event_helpers.publish_chat_created", new=AsyncMock()):
            chat = await chat_service.create_chat(
                session_id="test-session-123",
                created_by="user@example.com"
            )
        
        assert chat.chat_id == "new-chat-123"
        assert chat.session_id == "test-session-123"
        assert chat.created_by == "user@example.com"
        mock_history_service.create_chat.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_chat_idempotent(
        self, chat_service, mock_history_service, sample_session
    ):
        """Test creating chat twice returns existing chat."""
        existing_chat = Chat(
            chat_id="existing-chat",
            session_id="test-session-123",
            created_by="first-user@example.com",
            conversation_history="History",
            chain_id="test-chain",
            context_captured_at_us=now_us(),
        )
        
        mock_history_service.get_session.return_value = sample_session
        mock_history_service.get_chat_by_session = AsyncMock(return_value=existing_chat)
        
        chat = await chat_service.create_chat(
            session_id="test-session-123",
            created_by="second-user@example.com"
        )
        
        assert chat.chat_id == "existing-chat"
        assert chat.created_by == "first-user@example.com"  # Original creator preserved
    
    @pytest.mark.asyncio
    async def test_create_chat_session_not_found(
        self, chat_service, mock_history_service
    ):
        """Test create chat fails when session doesn't exist."""
        mock_history_service.get_session.return_value = None
        
        with pytest.raises(ValueError, match="not found"):
            await chat_service.create_chat(
                session_id="nonexistent",
                created_by="user@example.com"
            )
    
    @pytest.mark.asyncio
    async def test_create_chat_session_not_completed(
        self, chat_service, mock_history_service, sample_session
    ):
        """Test create chat fails when session is not completed."""
        sample_session.status = AlertSessionStatus.IN_PROGRESS.value
        mock_history_service.get_session.return_value = sample_session
        
        with pytest.raises(ValueError, match="terminated"):
            await chat_service.create_chat(
                session_id="test-session-123",
                created_by="user@example.com"
            )
    
    # ===== MCP Selection Tests =====
    
    def test_determine_mcp_selection_from_custom(
        self, chat_service, sample_session
    ):
        """Test MCP selection uses custom selection from session."""
        sample_session.mcp_selection = {
            "servers": [
                {"name": "kubectl", "tools": ["logs", "describe"]},
                {"name": "postgres", "tools": None}
            ]
        }
        
        result = chat_service._determine_mcp_selection_from_session(sample_session)
        
        assert result is not None
        assert len(result.servers) == 2
        assert result.servers[0].name == "kubectl"
        assert result.servers[0].tools == ["logs", "describe"]
        assert result.servers[1].name == "postgres"
    
    def test_determine_mcp_selection_from_agent_defaults(
        self, chat_service, mock_agent_factory, sample_session
    ):
        """Test MCP selection reconstructs from agent defaults."""
        sample_session.mcp_selection = None
        sample_session.chain_definition = {
            "stages": [
                {"agent": "KubernetesAgent"},
                {"agent": "DatabaseAgent"}
            ]
        }
        
        # Mock agent configs
        mock_agent_factory.agent_configs = {
            "KubernetesAgent": Mock(mcp_servers=["kubectl", "prometheus"]),
            "DatabaseAgent": Mock(mcp_servers=["postgres"])
        }
        
        with patch("tarsy.config.builtin_config.get_builtin_agent_config", return_value=None):
            result = chat_service._determine_mcp_selection_from_session(sample_session)
        
        assert result is not None
        server_names = {s.name for s in result.servers}
        assert server_names == {"kubectl", "prometheus", "postgres"}
        # No tool filtering for defaults
        assert all(s.tools is None for s in result.servers)
    
    def test_determine_mcp_selection_no_servers(
        self, chat_service, sample_session
    ):
        """Test MCP selection returns None when no servers found."""
        sample_session.mcp_selection = None
        sample_session.chain_definition = {"stages": []}
        
        result = chat_service._determine_mcp_selection_from_session(sample_session)
        
        assert result is None
    
    # ===== Context Building Tests =====
    
    @pytest.mark.asyncio
    async def test_capture_session_context(
        self, chat_service, mock_history_service, sample_session, sample_llm_interactions
    ):
        """Test capturing session context from LLM interactions."""
        mock_history_service.get_llm_interactions_for_session = AsyncMock(
            return_value=sample_llm_interactions
        )
        mock_history_service.get_session.return_value = sample_session
        
        context = await chat_service._capture_session_context("test-session-123")
        
        assert isinstance(context, SessionContextData)
        assert context.chain_id == "kubernetes-investigation"
        assert "Pod crashed in production" in context.conversation_history
        assert context.captured_at_us > 0
    
    @pytest.mark.asyncio
    async def test_capture_session_context_no_interactions(
        self, chat_service, mock_history_service
    ):
        """Test context capture fails when no LLM interactions exist."""
        mock_history_service.get_llm_interactions_for_session = AsyncMock(return_value=[])
        
        with pytest.raises(ValueError, match="No LLM interactions"):
            await chat_service._capture_session_context("test-session-123")
    
    @pytest.mark.asyncio
    async def test_build_message_context_first_message(
        self, chat_service, mock_history_service
    ):
        """Test building context for first chat message uses chat history."""
        chat = Chat(
            chat_id="chat-123",
            session_id="session-123",
            created_by="user@example.com",
            conversation_history="Pre-formatted investigation history",
            chain_id="test-chain",
            context_captured_at_us=now_us(),
        )
        
        mock_history_service.get_stage_executions_for_chat = AsyncMock(return_value=[])
        
        context = await chat_service._build_message_context(chat, "What caused the crash?")
        
        assert isinstance(context, ChatMessageContext)
        assert context.conversation_history == "Pre-formatted investigation history"
        assert context.user_question == "What caused the crash?"
        assert context.chat_id == "chat-123"
    
    @pytest.mark.asyncio
    async def test_build_message_context_subsequent_message(
        self, chat_service, mock_history_service, sample_llm_interactions
    ):
        """Test building context for subsequent messages combines original history with chat exchanges."""
        chat = Chat(
            chat_id="chat-123",
            session_id="session-123",
            created_by="user@example.com",
            conversation_history="Original history",
            chain_id="test-chain",
            context_captured_at_us=now_us(),
        )
        
        # Mock previous execution
        prev_execution = Mock()
        prev_execution.execution_id = "exec-1"
        prev_execution.started_at_us = now_us()
        prev_execution.chat_user_message_id = "msg-1"  # Link to the user message
        
        # Mock chat user message
        chat_user_message = Mock()
        chat_user_message.content = "Previous question"
        chat_user_message.created_at_us = now_us() - 1000
        chat_user_message.message_id = "msg-1"
        
        mock_history_service.get_stage_executions_for_chat = AsyncMock(
            return_value=[prev_execution]
        )
        mock_history_service.get_chat_user_messages = AsyncMock(
            return_value=[chat_user_message]
        )
        mock_history_service.get_llm_interactions_for_stage = AsyncMock(
            return_value=sample_llm_interactions
        )
        
        context = await chat_service._build_message_context(chat, "Follow-up question")
        
        assert isinstance(context, ChatMessageContext)
        # Should contain original history
        assert "Original history" in context.conversation_history
        assert context.user_question == "Follow-up question"
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "conversation_value,should_skip",
        [
            (None, True),
            (LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
                LLMMessage(role=MessageRole.USER, content="test")
            ]), False),
        ],
    )
    async def test_build_chat_exchanges_handles_none_conversation(
        self, chat_service, mock_history_service, conversation_value, should_skip
    ):
        """Test that chat exchanges with None conversation are skipped."""
        chat_user_message = Mock()
        chat_user_message.content = "Test question"
        chat_user_message.message_id = "msg-1"
        
        execution = Mock()
        execution.execution_id = "exec-1"
        execution.chat_user_message_id = "msg-1"
        
        llm_interaction = LLMInteraction(
            interaction_id="int-1",
            session_id="session-123",
            stage_execution_id="exec-1",
            model_name="gpt-4",
            conversation=conversation_value,
            tokens_used=100,
            created_at_us=now_us(),
        )
        
        mock_history_service.get_chat_user_messages = AsyncMock(
            return_value=[chat_user_message]
        )
        mock_history_service.get_stage_executions_for_chat = AsyncMock(
            return_value=[execution]
        )
        mock_history_service.get_llm_interactions_for_stage = AsyncMock(
            return_value=[llm_interaction]
        )
        
        exchanges = await chat_service._build_chat_exchanges("chat-123")
        
        if should_skip:
            assert len(exchanges) == 0
        else:
            assert len(exchanges) == 1
            assert exchanges[0].user_question == "Test question"
    
    @pytest.mark.asyncio
    async def test_build_chat_exchanges_skips_cancelled_includes_successful(
        self, chat_service, mock_history_service
    ):
        """Test that cancelled messages are skipped while successful ones are included."""
        # Create two messages: one cancelled (None conversation), one successful
        msg1 = Mock()
        msg1.content = "First question (cancelled)"
        msg1.message_id = "msg-1"
        
        msg2 = Mock()
        msg2.content = "Second question (successful)"
        msg2.message_id = "msg-2"
        
        exec1 = Mock()
        exec1.execution_id = "exec-1"
        exec1.chat_user_message_id = "msg-1"
        
        exec2 = Mock()
        exec2.execution_id = "exec-2"
        exec2.chat_user_message_id = "msg-2"
        
        # First interaction has None conversation (cancelled)
        interaction1 = LLMInteraction(
            interaction_id="int-1",
            session_id="session-123",
            stage_execution_id="exec-1",
            model_name="gpt-4",
            conversation=None,
            tokens_used=0,
            created_at_us=now_us(),
        )
        
        # Second interaction has valid conversation
        interaction2 = LLMInteraction(
            interaction_id="int-2",
            session_id="session-123",
            stage_execution_id="exec-2",
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
                LLMMessage(role=MessageRole.USER, content="Second question (successful)"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response"),
            ]),
            tokens_used=100,
            created_at_us=now_us(),
        )
        
        mock_history_service.get_chat_user_messages = AsyncMock(
            return_value=[msg1, msg2]
        )
        mock_history_service.get_stage_executions_for_chat = AsyncMock(
            return_value=[exec1, exec2]
        )
        
        # Mock to return different interactions based on execution_id
        async def get_interactions_by_stage(execution_id):
            if execution_id == "exec-1":
                return [interaction1]
            elif execution_id == "exec-2":
                return [interaction2]
            return []
        
        mock_history_service.get_llm_interactions_for_stage = AsyncMock(
            side_effect=get_interactions_by_stage
        )
        
        exchanges = await chat_service._build_chat_exchanges("chat-123")
        
        # Should only include the successful message
        assert len(exchanges) == 1
        assert exchanges[0].user_question == "Second question (successful)"
        assert exchanges[0].conversation is not None
    
    @pytest.mark.asyncio
    async def test_build_message_context_after_cancelled_message(
        self, chat_service, mock_history_service
    ):
        """Test that building context works correctly when previous message was cancelled."""
        chat = Chat(
            chat_id="chat-123",
            session_id="session-123",
            created_by="user@example.com",
            conversation_history="Original investigation history",
            chain_id="test-chain",
            context_captured_at_us=now_us(),
        )
        
        # Mock one cancelled execution (no conversation data)
        cancelled_msg = Mock()
        cancelled_msg.content = "Cancelled question"
        cancelled_msg.message_id = "msg-cancelled"
        
        cancelled_exec = Mock()
        cancelled_exec.execution_id = "exec-cancelled"
        cancelled_exec.chat_user_message_id = "msg-cancelled"
        
        cancelled_interaction = LLMInteraction(
            interaction_id="int-cancelled",
            session_id="session-123",
            stage_execution_id="exec-cancelled",
            model_name="gpt-4",
            conversation=None,
            tokens_used=0,
            created_at_us=now_us(),
        )
        
        mock_history_service.get_stage_executions_for_chat = AsyncMock(
            return_value=[cancelled_exec]
        )
        mock_history_service.get_chat_user_messages = AsyncMock(
            return_value=[cancelled_msg]
        )
        mock_history_service.get_llm_interactions_for_stage = AsyncMock(
            return_value=[cancelled_interaction]
        )
        
        # Should not raise an error and should build context successfully
        context = await chat_service._build_message_context(chat, "New question after cancellation")
        
        assert isinstance(context, ChatMessageContext)
        assert context.user_question == "New question after cancellation"
        # Should only have original history since cancelled message was skipped
        assert "Original investigation history" in context.conversation_history
        assert context.chat_id == "chat-123"


@pytest.mark.unit
class TestChatServiceStageExecution:
    """Test ChatService stage execution lifecycle methods."""
    
    @pytest.fixture
    def mock_history_service(self):
        """Mock history service."""
        return Mock()
    
    @pytest.fixture
    def chat_service(self, mock_history_service):
        """Create ChatService with mocked history."""
        return ChatService(
            history_service=mock_history_service,
            agent_factory=Mock(),
            mcp_client_factory=AsyncMock()
        )
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_started(
        self, chat_service, mock_history_service
    ):
        """Test marking stage execution as started."""
        mock_stage = Mock()
        mock_stage.session_id = "session-123"
        mock_stage.status = StageStatus.PENDING.value
        mock_history_service.get_stage_execution = AsyncMock(return_value=mock_stage)
        
        with patch("tarsy.services.chat_service.stage_execution_context"):
            await chat_service._update_stage_execution_started("exec-123")
        
        assert mock_stage.status == StageStatus.ACTIVE.value
        assert mock_stage.started_at_us > 0
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_completed(
        self, chat_service, mock_history_service
    ):
        """Test marking stage execution as completed."""
        start_time = now_us()
        mock_stage = Mock()
        mock_stage.session_id = "session-123"
        mock_stage.started_at_us = start_time
        mock_history_service.get_stage_execution = AsyncMock(return_value=mock_stage)
        
        # Create result with timestamp slightly after start
        result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="ChatAgent",
            result_summary="Analysis complete",
            final_analysis="Analysis complete",
            timestamp_us=start_time + 100_000  # 100ms later
        )
        
        with patch("tarsy.services.chat_service.stage_execution_context"):
            await chat_service._update_stage_execution_completed("exec-123", result)
        
        assert mock_stage.status == StageStatus.COMPLETED.value
        assert mock_stage.completed_at_us > 0
        assert mock_stage.duration_ms == 100  # 100ms duration
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_failed(
        self, chat_service, mock_history_service
    ):
        """Test marking stage execution as failed."""
        mock_stage = Mock()
        mock_stage.session_id = "session-123"
        mock_stage.started_at_us = now_us()
        mock_history_service.get_stage_execution = AsyncMock(return_value=mock_stage)
        
        with patch("tarsy.services.chat_service.stage_execution_context"):
            await chat_service._update_stage_execution_failed("exec-123", "Test error")
        
        assert mock_stage.status == StageStatus.FAILED.value
        assert mock_stage.error_message == "Test error"
        assert mock_stage.completed_at_us > 0

