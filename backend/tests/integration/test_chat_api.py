"""
Integration tests for chat API endpoints.

Tests the complete chat flow including chat creation, message sending,
and history retrieval with real database and service interactions.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from tarsy.main import app
from tarsy.models.constants import AlertSessionStatus
from tarsy.models.db_models import AlertSession, ChatUserMessage
from tarsy.services.chat_service import ChatService
from tarsy.services.history_service import HistoryService
from tarsy.utils.timestamp import now_us


@pytest.mark.integration
class TestChatAPIIntegration:
    """Integration tests for chat API flow."""

    @pytest.fixture
    async def completed_session(self, history_service_with_test_db: HistoryService):
        """Create a completed session for testing."""
        history_service = history_service_with_test_db
        session = AlertSession(
            session_id="test-session-integration",
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            chain_id="test-chain",
            status=AlertSessionStatus.COMPLETED.value,
            started_at_us=now_us(),
            completed_at_us=now_us(),
            author="test-user@example.com",
        )
        
        # Create session using repository directly
        def _create_session():
            with history_service.get_repository() as repo:
                repo.session.add(session)
                repo.session.commit()
                repo.session.refresh(session)
                return session
        
        created_session = _create_session()
        
        yield created_session
        
        # Cleanup
        def _cleanup():
            with history_service.get_repository() as repo:
                # Delete session (cascades to chat and messages)
                stmt = repo.session.query(AlertSession).filter_by(
                    session_id="test-session-integration"
                )
                stmt.delete()
                repo.session.commit()
        
        try:
            _cleanup()
        except Exception:
            pass  # Cleanup failed, ok for tests

    @pytest.fixture
    def mock_agent_factory(self):
        """Mock agent factory for testing."""
        mock_factory = Mock()
        mock_agent = AsyncMock()
        mock_agent.process_alert = AsyncMock(return_value=Mock(
            status=Mock(value="completed"),
            final_analysis="Test analysis response",
            timestamp_us=now_us()
        ))
        # ChatService uses get_agent(), not create_agent()
        mock_factory.get_agent.return_value = mock_agent
        return mock_factory

    @pytest.fixture
    def mock_mcp_client_factory(self):
        """Mock MCP client factory for testing."""
        mock_factory = AsyncMock()
        mock_client = AsyncMock()
        mock_client.close = AsyncMock()
        mock_factory.create_client = AsyncMock(return_value=mock_client)
        return mock_factory

    @pytest.mark.asyncio
    async def test_create_chat_for_completed_session(
        self, history_service_with_test_db, completed_session, mock_agent_factory, mock_mcp_client_factory
    ):
        """Test creating a chat for a completed session."""
        history_service = history_service_with_test_db
        # Create chat service
        chat_service = ChatService(
            history_service=history_service,
            agent_factory=mock_agent_factory,
            mcp_client_factory=mock_mcp_client_factory,
        )
        
        # Mock LLM interactions for context capture
        from tarsy.models.unified_interactions import (
            LLMConversation,
            LLMInteraction,
            LLMMessage,
            MessageRole,
        )
        
        mock_interaction = LLMInteraction(
            interaction_id="test-interaction",
            session_id=completed_session.session_id,
            stage_execution_id=None,
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System instructions"),
                LLMMessage(role=MessageRole.USER, content="Test alert data"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Test analysis"),
            ]),
            tokens_used=100,
            created_at_us=now_us(),
        )
        
        # Store mock interaction
        with history_service.get_repository() as repo:
            repo.session.add(mock_interaction)
            repo.session.commit()
        
        # Create chat
        chat = await chat_service.create_chat(
            session_id=completed_session.session_id,
            created_by="test-user@example.com"
        )
        
        # Verify chat was created
        assert chat is not None
        assert chat.session_id == completed_session.session_id
        assert chat.created_by == "test-user@example.com"
        assert chat.conversation_history is not None
        assert len(chat.conversation_history) > 0
        
        # Verify chat is idempotent
        chat2 = await chat_service.create_chat(
            session_id=completed_session.session_id,
            created_by="another-user@example.com"
        )
        assert chat2.chat_id == chat.chat_id

    @pytest.mark.asyncio
    async def test_send_message_creates_stage_execution(
        self, history_service_with_test_db, completed_session, mock_agent_factory, mock_mcp_client_factory
    ):
        """Test sending a message creates proper stage execution."""
        history_service = history_service_with_test_db
        # Setup chat
        chat_service = ChatService(
            history_service=history_service,
            agent_factory=mock_agent_factory,
            mcp_client_factory=mock_mcp_client_factory,
        )
        
        # Create mock LLM interaction for context
        from tarsy.models.unified_interactions import (
            LLMConversation,
            LLMInteraction,
            LLMMessage,
            MessageRole,
        )
        
        mock_interaction = LLMInteraction(
            interaction_id="test-interaction-2",
            session_id=completed_session.session_id,
            stage_execution_id=None,
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Alert data"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Analysis"),
            ]),
            tokens_used=100,
            created_at_us=now_us(),
        )
        
        with history_service.get_repository() as repo:
            repo.session.add(mock_interaction)
            repo.session.commit()
        
        # Create chat
        chat = await chat_service.create_chat(
            session_id=completed_session.session_id,
            created_by="test-user@example.com"
        )
        
        # Create user message and get IDs
        import uuid
        stage_execution_id = str(uuid.uuid4())
        message_id, returned_stage_id = await chat_service.create_user_message_and_start_processing(
            chat_id=chat.chat_id,
            user_question="What caused the issue?",
            author="test-user@example.com",
            stage_execution_id=stage_execution_id
        )
        
        # Verify IDs returned
        assert message_id is not None
        assert returned_stage_id == stage_execution_id
        
        # Send message for processing
        # Mock the stage execution updates since hooks aren't fully initialized in this test
        with patch.object(chat_service, '_update_stage_execution_started', AsyncMock()), \
             patch.object(chat_service, '_update_stage_execution_completed', AsyncMock()), \
             patch("tarsy.services.chat_service.stage_execution_context"):
            returned_id = await chat_service.process_chat_message(
                chat_id=chat.chat_id,
                user_question="What caused the issue?",
                author="test-user@example.com",
                stage_execution_id=stage_execution_id,
                message_id=message_id
            )
        
        # Verify stage execution was created
        assert returned_id == stage_execution_id
        
        # Verify user message was created with the correct message_id
        messages = await history_service.get_chat_user_messages(chat.chat_id, limit=10, offset=0)
        assert len(messages) == 1
        assert messages[0].message_id == message_id
        assert messages[0].content == "What caused the issue?"
        assert messages[0].author == "test-user@example.com"

    @pytest.mark.asyncio
    async def test_get_chat_message_history(
        self, history_service_with_test_db, completed_session, mock_agent_factory, mock_mcp_client_factory
    ):
        """Test retrieving chat message history with pagination."""
        history_service = history_service_with_test_db
        # Setup
        chat_service = ChatService(
            history_service=history_service,
            agent_factory=mock_agent_factory,
            mcp_client_factory=mock_mcp_client_factory,
        )
        
        # Create mock LLM interaction
        from tarsy.models.unified_interactions import (
            LLMConversation,
            LLMInteraction,
            LLMMessage,
            MessageRole,
        )
        
        mock_interaction = LLMInteraction(
            interaction_id="test-interaction-3",
            session_id=completed_session.session_id,
            stage_execution_id=None,
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Alert"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response"),
            ]),
            tokens_used=100,
            created_at_us=now_us(),
        )
        
        with history_service.get_repository() as repo:
            repo.session.add(mock_interaction)
            repo.session.commit()
        
        # Create chat
        chat = await chat_service.create_chat(
            session_id=completed_session.session_id,
            created_by="test-user@example.com"
        )
        
        # Create multiple messages directly in database
        messages_to_create = [
            ChatUserMessage(
                chat_id=chat.chat_id,
                content=f"Question {i}",
                author="test-user@example.com",
                created_at_us=now_us() + i,
            )
            for i in range(5)
        ]
        
        with history_service.get_repository() as repo:
            for msg in messages_to_create:
                repo.session.add(msg)
            repo.session.commit()
        
        # Retrieve messages with pagination
        page1 = await history_service.get_chat_user_messages(chat.chat_id, limit=3, offset=0)
        page2 = await history_service.get_chat_user_messages(chat.chat_id, limit=3, offset=3)
        
        assert len(page1) == 3
        assert len(page2) == 2
        assert page1[0].content == "Question 0"
        assert page2[0].content == "Question 3"
        
        # Check total count
        count = await history_service.get_chat_user_message_count(chat.chat_id)
        assert count == 5

    @pytest.mark.asyncio
    async def test_chat_not_available_for_non_completed_session(
        self, history_service_with_test_db, mock_agent_factory, mock_mcp_client_factory
    ):
        """Test chat cannot be created for non-completed sessions."""
        history_service = history_service_with_test_db
        # Create in-progress session
        session = AlertSession(
            session_id="test-session-in-progress",
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            chain_id="test-chain",
            status=AlertSessionStatus.IN_PROGRESS.value,
            started_at_us=now_us(),
            author="test-user@example.com",
        )
        
        with history_service.get_repository() as repo:
            repo.session.add(session)
            repo.session.commit()
        
        try:
            chat_service = ChatService(
                history_service=history_service,
                agent_factory=mock_agent_factory,
                mcp_client_factory=mock_mcp_client_factory,
            )
            
            # Attempt to create chat
            with pytest.raises(ValueError, match="completed"):
                await chat_service.create_chat(
                    session_id="test-session-in-progress",
                    created_by="test-user@example.com"
                )
        
        finally:
            # Cleanup
            with history_service.get_repository() as repo:
                stmt = repo.session.query(AlertSession).filter_by(
                    session_id="test-session-in-progress"
                )
                stmt.delete()
                repo.session.commit()

    @pytest.mark.asyncio
    async def test_multi_user_chat_participation(
        self, history_service_with_test_db, completed_session, mock_agent_factory, mock_mcp_client_factory
    ):
        """Test multiple users can participate in same chat."""
        history_service = history_service_with_test_db
        # Setup
        chat_service = ChatService(
            history_service=history_service,
            agent_factory=mock_agent_factory,
            mcp_client_factory=mock_mcp_client_factory,
        )
        
        # Create mock LLM interaction
        from tarsy.models.unified_interactions import (
            LLMConversation,
            LLMInteraction,
            LLMMessage,
            MessageRole,
        )
        
        mock_interaction = LLMInteraction(
            interaction_id="test-interaction-4",
            session_id=completed_session.session_id,
            stage_execution_id=None,
            model_name="gpt-4",
            conversation=LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Alert"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Response"),
            ]),
            tokens_used=100,
            created_at_us=now_us(),
        )
        
        with history_service.get_repository() as repo:
            repo.session.add(mock_interaction)
            repo.session.commit()
        
        # User 1 creates chat
        chat = await chat_service.create_chat(
            session_id=completed_session.session_id,
            created_by="user1@example.com"
        )
        
        # Create messages from different users
        users = ["user1@example.com", "user2@example.com", "user3@example.com"]
        for i, user in enumerate(users):
            msg = ChatUserMessage(
                chat_id=chat.chat_id,
                content=f"Question from {user}",
                author=user,
                created_at_us=now_us() + i,
            )
            with history_service.get_repository() as repo:
                repo.session.add(msg)
                repo.session.commit()
        
        # Retrieve all messages
        messages = await history_service.get_chat_user_messages(chat.chat_id, limit=10, offset=0)
        
        assert len(messages) == 3
        assert {msg.author for msg in messages} == set(users)
        assert all("Question from" in msg.content for msg in messages)


@pytest.mark.integration
class TestChatCancellationEndpoint:
    """Integration tests for chat cancellation endpoint."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create test client for FastAPI app."""
        return TestClient(app)

    @pytest.mark.integration
    def test_cancel_chat_execution_returns_success(self, client: TestClient) -> None:
        """Test that cancellation endpoint returns success response."""
        with patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock):
            response = client.post("/api/v1/chats/executions/test-exec-123/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data

    @pytest.mark.integration
    def test_cancel_chat_execution_publishes_event(self, client: TestClient) -> None:
        """Test that cancellation endpoint publishes cancellation event."""
        with patch("tarsy.services.events.event_helpers.publish_chat_cancel_request", new_callable=AsyncMock) as mock_publish:
            response = client.post("/api/v1/chats/executions/exec-456/cancel")

        assert response.status_code == 200
        
        # Verify cancellation request was published
        mock_publish.assert_called_once_with("exec-456")

    @pytest.mark.integration
    def test_cancel_nonexistent_execution_succeeds(self, client: TestClient) -> None:
        """Test that cancelling non-existent execution still succeeds."""
        with patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock):
            response = client.post("/api/v1/chats/executions/nonexistent-id/cancel")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.integration
    def test_cancel_endpoint_handles_publish_error(self, client: TestClient) -> None:
        """Test that endpoint handles event publishing errors gracefully."""
        with patch(
            "tarsy.services.events.event_helpers.publish_chat_cancel_request",
            side_effect=Exception("Event system error")
        ):
            response = client.post("/api/v1/chats/executions/test-exec/cancel")

        assert response.status_code == 500
        data = response.json()
        assert "detail" in data

