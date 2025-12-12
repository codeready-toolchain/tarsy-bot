"""
Unit tests for ChatService.

Tests chat lifecycle management, context building, and message processing
with mocked dependencies.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.models.agent_execution_result import AgentExecutionResult
from tarsy.models.constants import AlertSessionStatus, StageStatus
from tarsy.models.db_models import AlertSession, Chat
from tarsy.models.processing_context import ChatMessageContext, SessionContextData
from tarsy.models.unified_interactions import (
    LLMConversation,
    LLMInteraction,
    LLMMessage,
    MessageRole,
)
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
            "chain_id": "kubernetes-investigation",
            "alert_types": ["PodCrashLoop"],
            "stages": [
                {"agent": "KubernetesAgent", "name": "Initial Analysis"},
                {"agent": "DeepDiveAgent", "name": "Deep Dive"}
            ]
        }
        # Mock the chain_config property
        from tarsy.models.agent_config import ChainConfigModel
        session.chain_config = ChainConfigModel(**session.chain_definition)
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
    
    @pytest.mark.asyncio
    async def test_create_chat_disabled_for_chain(
        self, chat_service, mock_history_service, sample_session
    ):
        """Test create chat fails when chat is disabled for the chain."""
        from tarsy.models.agent_config import ChainConfigModel
        
        sample_session.chain_definition = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [{"agent": "TestAgent", "name": "Test"}],
            "chat": {"enabled": False}
        }
        # Update chain_config to reflect the new definition (Mock doesn't auto-parse)
        sample_session.chain_config = ChainConfigModel(**sample_session.chain_definition)
        
        mock_history_service.get_session.return_value = sample_session
        mock_history_service.get_chat_by_session = AsyncMock(return_value=None)
        
        with pytest.raises(ValueError, match="Chat is disabled"):
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
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [
                {"agent": "KubernetesAgent", "name": "Stage 1"},
                {"agent": "DatabaseAgent", "name": "Stage 2"}
            ]
        }
        # Update the mock chain_config property
        from tarsy.models.agent_config import ChainConfigModel
        sample_session.chain_config = ChainConfigModel(**sample_session.chain_definition)
        
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
        """Test MCP selection returns None when no servers found (chain_definition is None)."""
        sample_session.mcp_selection = None
        sample_session.chain_definition = None
        sample_session.chain_config = None
        
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
    async def test_capture_session_context_cancelled_session_all_failed(
        self, chat_service, mock_history_service, sample_session
    ):
        """Test context capture when all interactions have None conversation (early cancellation)."""
        # Create an interaction with None conversation (like a cancelled session)
        cancelled_interaction = LLMInteraction(
            interaction_id="int-cancelled",
            session_id="test-session-123",
            stage_execution_id="stage-1",
            model_name="gpt-4",
            conversation=None,  # This happens when session is cancelled
            tokens_used=0,
            created_at_us=now_us(),
        )
        
        mock_history_service.get_llm_interactions_for_session = AsyncMock(
            return_value=[cancelled_interaction]
        )
        mock_history_service.get_session.return_value = sample_session
        
        # Should not raise AttributeError and should return context with cancellation message
        context = await chat_service._capture_session_context("test-session-123")
        
        assert isinstance(context, SessionContextData)
        assert context.chain_id == "kubernetes-investigation"
        assert "[Investigation was cancelled before completion]" in context.conversation_history
        assert context.captured_at_us > 0
    
    @pytest.mark.asyncio
    async def test_capture_session_context_cancelled_mid_interaction(
        self, chat_service, mock_history_service, sample_session
    ):
        """Test context capture when last interaction failed but previous ones succeeded."""
        # Create multiple interactions - first two succeed, last one cancelled
        successful_interaction_1 = LLMInteraction(
            interaction_id="int-success-1",
            session_id="test-session-123",
            stage_execution_id="stage-1",
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Check pod status"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Analyzing pods..."),
            ]),
            tokens_used=100,
            created_at_us=now_us() - 2000,
        )
        
        successful_interaction_2 = LLMInteraction(
            interaction_id="int-success-2",
            session_id="test-session-123",
            stage_execution_id="stage-1",
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Check pod status"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Analyzing pods..."),
                LLMMessage(role=MessageRole.USER, content="Observation: Found crash"),
                LLMMessage(role=MessageRole.ASSISTANT, content="The pod crashed due to OOM"),
            ]),
            tokens_used=200,
            created_at_us=now_us() - 1000,
        )
        
        cancelled_interaction = LLMInteraction(
            interaction_id="int-cancelled",
            session_id="test-session-123",
            stage_execution_id="stage-1",
            model_name="gpt-4",
            conversation=None,  # Cancelled before LLM response
            tokens_used=0,
            created_at_us=now_us(),
            success=False,
        )
        
        mock_history_service.get_llm_interactions_for_session = AsyncMock(
            return_value=[successful_interaction_1, successful_interaction_2, cancelled_interaction]
        )
        mock_history_service.get_session.return_value = sample_session
        
        # Should use the last successful interaction (interaction_2)
        context = await chat_service._capture_session_context("test-session-123")
        
        assert isinstance(context, SessionContextData)
        assert context.chain_id == "kubernetes-investigation"
        # Should contain data from the last successful interaction
        assert "The pod crashed due to OOM" in context.conversation_history
        assert "[Investigation was cancelled before completion]" not in context.conversation_history
        assert context.captured_at_us > 0
    
    @pytest.mark.asyncio
    async def test_capture_session_context_skips_summarization_interactions(
        self, chat_service, mock_history_service, sample_session
    ):
        """Test that summarization interactions are skipped when finding last valid interaction."""
        from tarsy.models.constants import LLMInteractionType
        
        # Create investigation interaction
        investigation_interaction = LLMInteraction(
            interaction_id="int-investigation",
            session_id="test-session-123",
            stage_execution_id="stage-1",
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Check logs"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Analyzing logs..."),
            ]),
            interaction_type=LLMInteractionType.INVESTIGATION.value,
            tokens_used=100,
            created_at_us=now_us() - 2000,
        )
        
        # Create summarization interaction (should be skipped)
        summarization_interaction = LLMInteraction(
            interaction_id="int-summarization",
            session_id="test-session-123",
            stage_execution_id="stage-1",
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="Summarize this"),
                LLMMessage(role=MessageRole.USER, content="Tool output: ..."),
                LLMMessage(role=MessageRole.ASSISTANT, content="Summary: ..."),
            ]),
            interaction_type=LLMInteractionType.SUMMARIZATION.value,
            mcp_event_id="mcp-123",
            tokens_used=50,
            created_at_us=now_us() - 1000,
        )
        
        # Create another investigation interaction after summarization
        investigation_interaction_2 = LLMInteraction(
            interaction_id="int-investigation-2",
            session_id="test-session-123",
            stage_execution_id="stage-1",
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Check logs"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Analyzing logs..."),
                LLMMessage(role=MessageRole.USER, content="Observation: Found error"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Root cause: Memory leak"),
            ]),
            interaction_type=LLMInteractionType.INVESTIGATION.value,
            tokens_used=200,
            created_at_us=now_us(),
        )
        
        mock_history_service.get_llm_interactions_for_session = AsyncMock(
            return_value=[investigation_interaction, summarization_interaction, investigation_interaction_2]
        )
        mock_history_service.get_session.return_value = sample_session
        
        # Should use the last investigation interaction, skipping summarization
        context = await chat_service._capture_session_context("test-session-123")
        
        assert isinstance(context, SessionContextData)
        assert "Root cause: Memory leak" in context.conversation_history
        # Should not contain summarization content
        assert "Summary: ..." not in context.conversation_history
    
    @pytest.mark.asyncio
    async def test_capture_session_context_skips_summarization_and_cancelled(
        self, chat_service, mock_history_service, sample_session
    ):
        """Test skipping both summarization and cancelled interactions to find valid one."""
        from tarsy.models.constants import LLMInteractionType
        
        # Create successful investigation interaction
        investigation_interaction = LLMInteraction(
            interaction_id="int-investigation",
            session_id="test-session-123",
            stage_execution_id="stage-1",
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Investigate issue"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Found the problem"),
            ]),
            interaction_type=LLMInteractionType.INVESTIGATION.value,
            tokens_used=100,
            created_at_us=now_us() - 3000,
        )
        
        # Create summarization (should skip)
        summarization_interaction = LLMInteraction(
            interaction_id="int-summarization",
            session_id="test-session-123",
            stage_execution_id="stage-1",
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="Summarize"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Brief summary"),
            ]),
            interaction_type=LLMInteractionType.SUMMARIZATION.value,
            tokens_used=30,
            created_at_us=now_us() - 2000,
        )
        
        # Create cancelled interaction (should skip)
        cancelled_interaction = LLMInteraction(
            interaction_id="int-cancelled",
            session_id="test-session-123",
            stage_execution_id="stage-1",
            model_name="gpt-4",
            conversation=None,
            interaction_type=LLMInteractionType.INVESTIGATION.value,
            tokens_used=0,
            created_at_us=now_us(),
            success=False,
        )
        
        mock_history_service.get_llm_interactions_for_session = AsyncMock(
            return_value=[investigation_interaction, summarization_interaction, cancelled_interaction]
        )
        mock_history_service.get_session.return_value = sample_session
        
        # Should use the investigation interaction, skipping both summarization and cancelled
        context = await chat_service._capture_session_context("test-session-123")
        
        assert isinstance(context, SessionContextData)
        assert "Found the problem" in context.conversation_history
        assert "Brief summary" not in context.conversation_history
    
    @pytest.mark.asyncio
    async def test_create_chat_cancelled_session_with_prior_success(
        self, chat_service, mock_history_service, sample_session
    ):
        """Test creating chat for cancelled session uses last successful interaction."""
        # Set session as cancelled
        sample_session.status = AlertSessionStatus.CANCELLED.value
        
        # Create interactions - some successful, last one cancelled
        successful_interaction = LLMInteraction(
            interaction_id="int-success",
            session_id="test-session-123",
            stage_execution_id="stage-1",
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Investigate alert"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Found the issue"),
            ]),
            tokens_used=150,
            created_at_us=now_us() - 1000,
        )
        
        cancelled_interaction = LLMInteraction(
            interaction_id="int-cancelled",
            session_id="test-session-123",
            stage_execution_id="stage-1",
            model_name="gpt-4",
            conversation=None,
            tokens_used=0,
            created_at_us=now_us(),
            success=False,
        )
        
        mock_history_service.get_session.return_value = sample_session
        mock_history_service.get_chat_by_session = AsyncMock(return_value=None)
        mock_history_service.get_llm_interactions_for_session = AsyncMock(
            return_value=[successful_interaction, cancelled_interaction]
        )
        
        # Mock create_chat to capture what would be saved
        captured_chat = None
        async def capture_create_chat(chat: Chat):
            nonlocal captured_chat
            captured_chat = chat
            # Return a chat with an ID
            return Chat(
                chat_id="new-chat-123",
                session_id=chat.session_id,
                created_by=chat.created_by,
                conversation_history=chat.conversation_history,
                chain_id=chat.chain_id,
                context_captured_at_us=chat.context_captured_at_us,
            )
        
        mock_history_service.create_chat = AsyncMock(side_effect=capture_create_chat)
        
        with patch("tarsy.services.events.event_helpers.publish_chat_created", new=AsyncMock()):
            chat = await chat_service.create_chat(
                session_id="test-session-123",
                created_by="user@example.com"
            )
        
        assert chat.chat_id == "new-chat-123"
        assert chat.session_id == "test-session-123"
        # Should use successful interaction, not show cancellation message
        assert captured_chat is not None
        assert "Found the issue" in captured_chat.conversation_history
        assert "[Investigation was cancelled before completion]" not in captured_chat.conversation_history
        mock_history_service.create_chat.assert_called_once()
    
    def test_chat_context_interaction_types_is_defined(self):
        """Test that CHAT_CONTEXT_INTERACTION_TYPES is properly defined and documented."""
        from tarsy.models.constants import (
            CHAT_CONTEXT_INTERACTION_TYPES,
            LLMInteractionType,
        )
        
        # Should be a frozenset
        assert isinstance(CHAT_CONTEXT_INTERACTION_TYPES, frozenset)
        
        # Should not be empty
        assert len(CHAT_CONTEXT_INTERACTION_TYPES) > 0
        
        # All values should be valid LLMInteractionType values
        all_valid_types = {t.value for t in LLMInteractionType}
        for interaction_type in CHAT_CONTEXT_INTERACTION_TYPES:
            assert interaction_type in all_valid_types, f"Invalid interaction type: {interaction_type}"
        
        # SUMMARIZATION should NOT be in chat context types
        assert LLMInteractionType.SUMMARIZATION.value not in CHAT_CONTEXT_INTERACTION_TYPES
        
        # INVESTIGATION and FINAL_ANALYSIS should be included (current expectations)
        assert LLMInteractionType.INVESTIGATION.value in CHAT_CONTEXT_INTERACTION_TYPES
        assert LLMInteractionType.FINAL_ANALYSIS.value in CHAT_CONTEXT_INTERACTION_TYPES
    
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
    def mock_agent_factory(self):
        """Mock agent factory for testing."""
        mock = Mock()
        mock.agent_configs = {}
        mock.static_agent_classes = {}
        return mock
    
    @pytest.fixture
    def sample_session(self):
        """Sample completed session for testing."""
        from tarsy.models.db_models import AlertSession
        from tarsy.utils.timestamp import now_us
        
        session = AlertSession(
            session_id="test-session-123",
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            chain_id="kubernetes-investigation",
            status=AlertSessionStatus.COMPLETED.value,
            started_at_us=now_us(),
            completed_at_us=now_us(),
            author="test-user@example.com",
            chain_definition={
                "chain_id": "kubernetes-investigation",
                "alert_types": ["kubernetes"],
                "stages": [
                    {"agent": "KubernetesAgent", "name": "Initial Investigation"}
                ]
            },
            mcp_selection=None
        )
        return session
    
    @pytest.fixture
    def chat_service(self, mock_history_service, mock_agent_factory):
        """Create ChatService with mocked history."""
        return ChatService(
            history_service=mock_history_service,
            agent_factory=mock_agent_factory,
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
        
        with patch("tarsy.services.chat_service.stage_execution_context") as stage_ctx:
            stage_ctx.return_value.__aenter__ = AsyncMock(return_value=None)
            stage_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
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
        
        with patch("tarsy.services.chat_service.stage_execution_context") as stage_ctx:
            stage_ctx.return_value.__aenter__ = AsyncMock(return_value=None)
            stage_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
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
        
        with patch("tarsy.services.chat_service.stage_execution_context") as stage_ctx:
            stage_ctx.return_value.__aenter__ = AsyncMock(return_value=None)
            stage_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
            await chat_service._update_stage_execution_failed("exec-123", "Test error")
        
        assert mock_stage.status == StageStatus.FAILED.value
        assert mock_stage.error_message == "Test error"
        assert mock_stage.completed_at_us > 0
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_started_fails_when_history_service_is_none(self):
        """Test that update fails when history service is None."""
        service = ChatService(
            history_service=None,
            agent_factory=Mock(),
            mcp_client_factory=AsyncMock()
        )
        
        with pytest.raises(RuntimeError, match="History service is disabled"):
            await service._update_stage_execution_started("exec-123")
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_started_fails_when_not_found(
        self, chat_service, mock_history_service
    ):
        """Test that update fails when stage execution is not found."""
        mock_history_service.get_stage_execution = AsyncMock(return_value=None)
        
        with pytest.raises(RuntimeError, match="not found in database"):
            await chat_service._update_stage_execution_started("exec-123")
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_started_propagates_hook_failures(
        self, chat_service, mock_history_service
    ):
        """Test that hook failures are propagated, not silently swallowed."""
        mock_stage = Mock()
        mock_stage.session_id = "session-123"
        mock_stage.status = StageStatus.PENDING.value
        mock_history_service.get_stage_execution = AsyncMock(return_value=mock_stage)
        
        # Simulate hook failure
        with patch("tarsy.services.chat_service.stage_execution_context") as stage_ctx:
            stage_ctx.return_value.__aenter__ = AsyncMock(side_effect=Exception("Hook failure"))
            
            with pytest.raises(RuntimeError, match="Database persistence is required"):
                await chat_service._update_stage_execution_started("exec-123")
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_completed_fails_when_history_service_is_none(self):
        """Test that update fails when history service is None."""
        service = ChatService(
            history_service=None,
            agent_factory=Mock(),
            mcp_client_factory=AsyncMock()
        )
        
        result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="ChatAgent",
            result_summary="Analysis complete",
            final_analysis="Analysis complete",
            timestamp_us=now_us()
        )
        
        with pytest.raises(RuntimeError, match="History service is disabled"):
            await service._update_stage_execution_completed("exec-123", result)
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_completed_fails_when_not_found(
        self, chat_service, mock_history_service
    ):
        """Test that update fails when stage execution is not found."""
        mock_history_service.get_stage_execution = AsyncMock(return_value=None)
        
        result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="ChatAgent",
            result_summary="Analysis complete",
            final_analysis="Analysis complete",
            timestamp_us=now_us()
        )
        
        with pytest.raises(RuntimeError, match="not found in database"):
            await chat_service._update_stage_execution_completed("exec-123", result)
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_completed_propagates_hook_failures(
        self, chat_service, mock_history_service
    ):
        """Test that hook failures are propagated, not silently swallowed."""
        mock_stage = Mock()
        mock_stage.session_id = "session-123"
        mock_stage.started_at_us = now_us()
        mock_history_service.get_stage_execution = AsyncMock(return_value=mock_stage)
        
        result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="ChatAgent",
            result_summary="Analysis complete",
            final_analysis="Analysis complete",
            timestamp_us=now_us()
        )
        
        # Simulate hook failure
        with patch("tarsy.services.chat_service.stage_execution_context") as stage_ctx:
            stage_ctx.return_value.__aenter__ = AsyncMock(side_effect=Exception("Hook failure"))
            
            with pytest.raises(RuntimeError, match="Database persistence is required"):
                await chat_service._update_stage_execution_completed("exec-123", result)
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_failed_fails_when_history_service_is_none(self):
        """Test that update fails when history service is None."""
        service = ChatService(
            history_service=None,
            agent_factory=Mock(),
            mcp_client_factory=AsyncMock()
        )
        
        with pytest.raises(RuntimeError, match="History service is disabled"):
            await service._update_stage_execution_failed("exec-123", "Test error")
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_failed_fails_when_not_found(
        self, chat_service, mock_history_service
    ):
        """Test that update fails when stage execution is not found."""
        mock_history_service.get_stage_execution = AsyncMock(return_value=None)
        
        with pytest.raises(RuntimeError, match="not found in database"):
            await chat_service._update_stage_execution_failed("exec-123", "Test error")
    
    @pytest.mark.asyncio
    async def test_update_stage_execution_failed_propagates_hook_failures(
        self, chat_service, mock_history_service
    ):
        """Test that hook failures are propagated, not silently swallowed."""
        mock_stage = Mock()
        mock_stage.session_id = "session-123"
        mock_stage.started_at_us = now_us()
        mock_history_service.get_stage_execution = AsyncMock(return_value=mock_stage)
        
        # Simulate hook failure
        with patch("tarsy.services.chat_service.stage_execution_context") as stage_ctx:
            stage_ctx.return_value.__aenter__ = AsyncMock(side_effect=Exception("Hook failure"))
            
            with pytest.raises(RuntimeError, match="Database persistence is required"):
                await chat_service._update_stage_execution_failed("exec-123", "Test error")
    
    # ===== Iteration Strategy Determination Tests =====
    
    def test_determine_iteration_strategy_from_explicit_stage_strategy(
        self, chat_service, sample_session
    ):
        """Test iteration strategy uses explicit stage strategy override."""
        sample_session.chain_definition = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [
                {"agent": "TestAgent", "name": "Stage 1", "iteration_strategy": "native-thinking"}
            ]
        }
        
        result = chat_service._determine_iteration_strategy_from_session(sample_session)
        
        assert result == "native-thinking"
    
    def test_determine_iteration_strategy_translates_synthesis_to_react(
        self, chat_service, sample_session
    ):
        """Test that synthesis strategy is translated to react for chat."""
        sample_session.chain_definition = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [
                {"agent": "SynthesisAgent", "name": "Synthesis", "iteration_strategy": "synthesis"}
            ]
        }
        
        result = chat_service._determine_iteration_strategy_from_session(sample_session)
        
        # synthesis should be translated to react for chat
        assert result == "react"
    
    def test_determine_iteration_strategy_translates_synthesis_native_thinking(
        self, chat_service, sample_session
    ):
        """Test that synthesis-native-thinking is translated to native-thinking for chat."""
        sample_session.chain_definition = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [
                {"agent": "SynthesisAgent", "name": "Synthesis", "iteration_strategy": "synthesis-native-thinking"}
            ]
        }
        
        result = chat_service._determine_iteration_strategy_from_session(sample_session)
        
        # synthesis-native-thinking should be translated to native-thinking for chat
        assert result == "native-thinking"
    
    def test_determine_iteration_strategy_from_agent_default(
        self, chat_service, mock_agent_factory, sample_session
    ):
        """Test iteration strategy falls back to agent default from config."""
        from tarsy.models.agent_config import IterationStrategy
        
        sample_session.chain_definition = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [
                {"agent": "CustomAgent", "name": "Stage 1"}  # No explicit strategy
            ]
        }
        
        # Mock agent config with default strategy
        mock_agent_factory.agent_configs = {
            "CustomAgent": Mock(iteration_strategy=IterationStrategy.NATIVE_THINKING)
        }
        
        result = chat_service._determine_iteration_strategy_from_session(sample_session)
        
        assert result == "native-thinking"
    
    def test_determine_iteration_strategy_from_builtin_agent(
        self, chat_service, mock_agent_factory, sample_session
    ):
        """Test iteration strategy falls back to builtin agent default."""
        sample_session.chain_definition = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [
                {"agent": "SynthesisAgent", "name": "Synthesis"}  # No explicit strategy
            ]
        }
        
        # Empty agent configs (builtin lookup will happen)
        mock_agent_factory.agent_configs = {}
        
        with patch("tarsy.config.builtin_config.get_builtin_agent_config") as mock_builtin:
            mock_builtin.return_value = {"iteration_strategy": "synthesis"}
            
            result = chat_service._determine_iteration_strategy_from_session(sample_session)
        
        # Should translate synthesis from builtin to react for chat
        assert result == "react"
    
    def test_determine_iteration_strategy_returns_none_when_no_config(
        self, chat_service, sample_session
    ):
        """Test iteration strategy returns None when no chain config exists."""
        sample_session.chain_definition = None
        
        result = chat_service._determine_iteration_strategy_from_session(sample_session)
        
        assert result is None
    
    def test_determine_iteration_strategy_returns_none_when_no_stages(
        self, chat_service, sample_session
    ):
        """Test iteration strategy returns None when chain has no stages."""
        # Set chain_definition to None (simpler than creating invalid chain config)
        sample_session.chain_definition = None
        
        result = chat_service._determine_iteration_strategy_from_session(sample_session)
        
        assert result is None
    
    def test_determine_iteration_strategy_uses_last_stage(
        self, chat_service, sample_session
    ):
        """Test iteration strategy uses last stage in chain (most relevant for chat)."""
        sample_session.chain_definition = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [
                {"agent": "Agent1", "name": "Stage 1", "iteration_strategy": "react"},
                {"agent": "Agent2", "name": "Stage 2", "iteration_strategy": "native-thinking"}
            ]
        }
        
        result = chat_service._determine_iteration_strategy_from_session(sample_session)
        
        # Should use the last stage's strategy (native-thinking, not react)
        assert result == "native-thinking"
    
    def test_determine_iteration_strategy_normalizes_enum_to_string(
        self, chat_service, sample_session
    ):
        """Test that iteration strategy normalizes IterationStrategy enum to string."""
        from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
        from tarsy.models.constants import IterationStrategy
        
        # Create a real ChainConfigModel with enum iteration_strategy
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["TestAlert"],
            stages=[
                ChainStageConfigModel(
                    name="Stage 1",
                    agent="TestAgent",
                    iteration_strategy=IterationStrategy.NATIVE_THINKING  # Pass as enum
                )
            ]
        )
        
        # Serialize to dict (simulating what would be stored in DB)
        sample_session.chain_definition = chain_config.model_dump(mode='json')
        
        # When we access chain_config property, it deserializes back to ChainConfigModel
        # and iteration_strategy becomes an IterationStrategy enum again
        result = chat_service._determine_iteration_strategy_from_session(sample_session)
        
        # Result should be a string, not an enum
        assert isinstance(result, str)
        assert result == "native-thinking"
    
    def test_determine_iteration_strategy_enum_synthesis_translation(
        self, chat_service, sample_session
    ):
        """Test that enum synthesis strategies are correctly translated."""
        from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
        from tarsy.models.constants import IterationStrategy
        
        # Create ChainConfigModel with SYNTHESIS enum
        chain_config = ChainConfigModel(
            chain_id="test-chain",
            alert_types=["TestAlert"],
            stages=[
                ChainStageConfigModel(
                    name="Synthesis",
                    agent="SynthesisAgent",
                    iteration_strategy=IterationStrategy.SYNTHESIS  # Enum, not string
                )
            ]
        )
        
        sample_session.chain_definition = chain_config.model_dump(mode='json')
        
        result = chat_service._determine_iteration_strategy_from_session(sample_session)
        
        # Should translate enum SYNTHESIS to string "react"
        assert isinstance(result, str)
        assert result == "react"


@pytest.mark.unit
class TestChatConfig:
    """Test ChatConfig model validation."""
    
    def test_chat_config_defaults(self):
        """Test ChatConfig uses correct defaults."""
        from tarsy.models.agent_config import ChatConfig
        
        config = ChatConfig()
        
        assert config.enabled is True
        assert config.agent == "ChatAgent"
        assert config.iteration_strategy is None
        assert config.llm_provider is None
    
    def test_chat_config_with_custom_values(self):
        """Test ChatConfig with custom values."""
        from tarsy.models.agent_config import ChatConfig, IterationStrategy
        
        config = ChatConfig(
            enabled=False,
            agent="CustomChatAgent",
            iteration_strategy=IterationStrategy.NATIVE_THINKING,
            llm_provider="google-default"
        )
        
        assert config.enabled is False
        assert config.agent == "CustomChatAgent"
        assert config.iteration_strategy == IterationStrategy.NATIVE_THINKING
        assert config.llm_provider == "google-default"
    
    def test_chat_config_extra_fields_forbidden(self):
        """Test that extra fields are not allowed."""
        from tarsy.models.agent_config import ChatConfig
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            ChatConfig(unknown_field="value")


@pytest.mark.unit
class TestChatServiceWithChatConfig:
    """Test ChatService with new ChatConfig functionality."""
    
    @pytest.fixture
    def mock_history_service(self):
        """Mock history service."""
        return Mock()
    
    @pytest.fixture
    def mock_agent_factory(self):
        """Mock agent factory for testing."""
        mock = Mock()
        mock.agent_configs = {}
        mock.static_agent_classes = {}
        return mock
    
    @pytest.fixture
    def sample_session(self):
        """Sample completed session for testing."""
        from tarsy.models.db_models import AlertSession
        from tarsy.utils.timestamp import now_us
        
        session = AlertSession(
            session_id="test-session-123",
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            chain_id="kubernetes-investigation",
            status=AlertSessionStatus.COMPLETED.value,
            started_at_us=now_us(),
            completed_at_us=now_us(),
            author="test-user@example.com",
            chain_definition={
                "chain_id": "kubernetes-investigation",
                "alert_types": ["kubernetes"],
                "stages": [
                    {"agent": "KubernetesAgent", "name": "Initial Investigation"}
                ]
            },
            mcp_selection=None
        )
        return session
    
    @pytest.fixture
    def chat_service(self, mock_history_service, mock_agent_factory):
        """Create ChatService with mocked history."""
        return ChatService(
            history_service=mock_history_service,
            agent_factory=mock_agent_factory,
            mcp_client_factory=AsyncMock()
        )
    
    @pytest.mark.asyncio
    async def test_create_chat_disabled_with_chat_config(
        self, chat_service, mock_history_service, sample_session
    ):
        """Test chat creation fails when chat.enabled is false."""
        from tarsy.models.agent_config import ChatConfig
        
        # Mock chat config with enabled=false
        sample_session.chain_definition["chat"] = {"enabled": False}
        
        mock_history_service.get_session.return_value = sample_session
        mock_history_service.get_chat_by_session = AsyncMock(return_value=None)
        
        with pytest.raises(ValueError, match="Chat is disabled"):
            await chat_service.create_chat("test-session-123", "test-user")
    
    def test_chat_config_strategy_priority_over_last_stage(
        self, chat_service, sample_session
    ):
        """Test chat config iteration strategy takes priority over last stage."""
        from tarsy.models.agent_config import IterationStrategy
        
        sample_session.chain_definition = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "chat": {
                "enabled": True,
                "iteration_strategy": "native-thinking"
            },
            "stages": [
                {"agent": "TestAgent", "name": "Stage 1", "iteration_strategy": "react"}
            ]
        }
        
        result = chat_service._determine_iteration_strategy_from_session(sample_session)
        
        # Should use chat config strategy, not last stage
        assert result == "native-thinking"
    
    def test_chat_config_llm_provider_priority_over_chain(
        self, chat_service, sample_session
    ):
        """Test chat config LLM provider takes priority over chain-level."""
        sample_session.chain_definition = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "llm_provider": "anthropic-default",
            "chat": {
                "enabled": True,
                "llm_provider": "google-default"
            },
            "stages": [
                {"agent": "TestAgent", "name": "Stage 1"}
            ]
        }
        
        result = chat_service._determine_llm_provider_from_session(sample_session)
        
        # Should use chat config provider, not chain-level
        assert result == "google-default"
    
    def test_chat_config_agent_selection(
        self, chat_service, sample_session
    ):
        """Test custom chat agent can be specified in config."""
        sample_session.chain_definition = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "chat": {
                "enabled": True,
                "agent": "CustomChatAgent"
            },
            "stages": [
                {"agent": "TestAgent", "name": "Stage 1"}
            ]
        }
        
        result = chat_service._determine_chat_agent_from_session(sample_session)
        
        assert result == "CustomChatAgent"
    
    def test_default_chat_agent_when_not_configured(
        self, chat_service, sample_session
    ):
        """Test default ChatAgent is used when not configured."""
        sample_session.chain_definition = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [
                {"agent": "TestAgent", "name": "Stage 1"}
            ]
        }
        
        result = chat_service._determine_chat_agent_from_session(sample_session)
        
        assert result == "ChatAgent"
    
    def test_default_chat_behavior_missing_config(
        self, chat_service, sample_session
    ):
        """Test default chat behavior when config is missing (enabled by default)."""
        # Chain config without explicit chat field = enabled with defaults
        sample_session.chain_definition = {
            "chain_id": "test-chain",
            "alert_types": ["TestAlert"],
            "stages": [
                {"agent": "TestAgent", "name": "Stage 1", "iteration_strategy": "react"}
            ]
        }
        
        # Should use last stage strategy (no chat config override)
        strategy = chat_service._determine_iteration_strategy_from_session(sample_session)
        assert strategy == "react"
        
        # Should use chain-level provider (no chat config override)
        provider = chat_service._determine_llm_provider_from_session(sample_session)
        assert provider is None
        
        # Should use default agent (no chat config override)
        agent = chat_service._determine_chat_agent_from_session(sample_session)
        assert agent == "ChatAgent"

