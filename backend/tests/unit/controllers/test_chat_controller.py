"""
Unit tests for chat controller endpoints.

Tests all chat REST API endpoints including request validation, error handling,
authorization header extraction, and response model serialization.
"""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from tarsy.main import app
from tarsy.models.db_models import Chat, ChatUserMessage


@pytest.mark.unit
class TestChatController:
    """Test chat controller REST endpoints."""

    @pytest.fixture
    def mock_chat_service(self):
        """Mock chat service for testing."""
        return AsyncMock()

    @pytest.fixture
    def mock_history_service(self):
        """Mock history service for testing."""
        return AsyncMock()

    @pytest.fixture
    def client(self, mock_chat_service, mock_history_service):
        """Create test client with dependency overrides."""
        from tarsy.services.chat_service import get_chat_service
        from tarsy.services.history_service import get_history_service
        
        app.dependency_overrides[get_chat_service] = lambda: mock_chat_service
        app.dependency_overrides[get_history_service] = lambda: mock_history_service
        
        # Mock the process_chat_message_callback
        app.state.process_chat_message_callback = AsyncMock()
        
        yield TestClient(app)
        
        app.dependency_overrides.clear()
        # Clean up state
        if hasattr(app.state, 'process_chat_message_callback'):
            delattr(app.state, 'process_chat_message_callback')

    @pytest.fixture
    def sample_chat(self):
        """Sample chat object for testing."""
        return Chat(
            chat_id="test-chat-123",
            session_id="test-session-456",
            created_at_us=int(time.time() * 1_000_000),
            created_by="test-user@example.com",
            conversation_history="Test conversation history",
            chain_id="test-chain",
            context_captured_at_us=int(time.time() * 1_000_000),
        )

    @pytest.fixture
    def sample_session(self):
        """Sample session object for testing."""
        mock_session = Mock()
        mock_session.session_id = "test-session-456"
        mock_session.status = "completed"
        mock_session.chain_id = "test-chain"
        return mock_session

    # ===== POST /api/v1/sessions/{session_id}/chat =====

    def test_create_chat_success(
        self, client, mock_chat_service, mock_history_service, sample_chat, sample_session
    ):
        """Test successful chat creation."""
        mock_chat_service.create_chat = AsyncMock(return_value=sample_chat)
        mock_history_service.get_chat_user_message_count = AsyncMock(return_value=5)

        response = client.post(
            "/api/v1/sessions/test-session-456/chat",
            headers={"X-Forwarded-User": "test-user@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chat_id"] == "test-chat-123"
        assert data["session_id"] == "test-session-456"
        assert data["created_by"] == "test-user@example.com"
        assert data["message_count"] == 5

    def test_create_chat_author_extraction(
        self, client, mock_chat_service, mock_history_service, sample_chat
    ):
        """Test author extraction from oauth2-proxy headers."""
        mock_chat_service.create_chat = AsyncMock(return_value=sample_chat)
        mock_history_service.get_chat_user_message_count = AsyncMock(return_value=0)

        # Test X-Forwarded-User
        response = client.post(
            "/api/v1/sessions/test-session-456/chat",
            headers={"X-Forwarded-User": "github-user"},
        )
        assert response.status_code == 200
        mock_chat_service.create_chat.assert_called_with("test-session-456", "github-user")

        # Test X-Forwarded-Email fallback
        mock_chat_service.create_chat.reset_mock()
        response = client.post(
            "/api/v1/sessions/test-session-456/chat",
            headers={"X-Forwarded-Email": "user@example.com"},
        )
        assert response.status_code == 200
        mock_chat_service.create_chat.assert_called_with(
            "test-session-456", "user@example.com"
        )

        # Test api-client default
        mock_chat_service.create_chat.reset_mock()
        response = client.post("/api/v1/sessions/test-session-456/chat")
        assert response.status_code == 200
        mock_chat_service.create_chat.assert_called_with("test-session-456", "api-client")

    def test_create_chat_session_not_found(self, client, mock_chat_service):
        """Test create chat when session not found."""
        mock_chat_service.create_chat = AsyncMock(
            side_effect=ValueError("Session test-session-456 not found")
        )

        response = client.post("/api/v1/sessions/test-session-456/chat")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_create_chat_session_not_completed(self, client, mock_chat_service):
        """Test create chat when session not completed."""
        mock_chat_service.create_chat = AsyncMock(
            side_effect=ValueError("Can only create chat for completed sessions")
        )

        response = client.post("/api/v1/sessions/test-session-456/chat")

        assert response.status_code == 400
        assert "completed" in response.json()["detail"].lower()

    @patch("tarsy.main.shutdown_in_progress", True)
    def test_create_chat_during_shutdown(self, client):
        """Test create chat rejects during shutdown."""
        response = client.post("/api/v1/sessions/test-session-456/chat")

        assert response.status_code == 503
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error"] == "Service shutting down"
        assert data["detail"]["retry_after"] == 30

    # ===== GET /api/v1/sessions/{session_id}/chat-available =====

    def test_check_chat_availability_available(
        self, client, mock_history_service, sample_session
    ):
        """Test chat availability when session is completed."""
        mock_history_service.get_session = Mock(return_value=sample_session)
        mock_history_service.get_chat_by_session = AsyncMock(return_value=None)

        response = client.get("/api/v1/sessions/test-session-456/chat-available")

        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
        assert data.get("chat_id") is None

    def test_check_chat_availability_existing_chat(
        self, client, mock_history_service, sample_session, sample_chat
    ):
        """Test chat availability when chat already exists."""
        mock_history_service.get_session = Mock(return_value=sample_session)
        mock_history_service.get_chat_by_session = AsyncMock(return_value=sample_chat)

        response = client.get("/api/v1/sessions/test-session-456/chat-available")

        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True
        assert data["chat_id"] == "test-chat-123"

    def test_check_chat_availability_session_not_completed(
        self, client, mock_history_service, sample_session
    ):
        """Test chat availability when session is not completed."""
        sample_session.status = "in_progress"
        mock_history_service.get_session = Mock(return_value=sample_session)
        mock_history_service.get_chat_by_session = AsyncMock(return_value=None)

        response = client.get("/api/v1/sessions/test-session-456/chat-available")

        assert response.status_code == 200
        data = response.json()
        assert data["available"] is False
        assert "terminal state" in data["reason"].lower()

    def test_check_chat_availability_session_not_found(self, client, mock_history_service):
        """Test chat availability when session doesn't exist."""
        mock_history_service.get_session = Mock(return_value=None)

        response = client.get("/api/v1/sessions/test-session-456/chat-available")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    # ===== GET /api/v1/chats/{chat_id} =====

    def test_get_chat_success(self, client, mock_history_service, sample_chat):
        """Test successful chat retrieval."""
        mock_history_service.get_chat_by_id = AsyncMock(return_value=sample_chat)
        mock_history_service.get_chat_user_message_count = AsyncMock(return_value=10)

        response = client.get("/api/v1/chats/test-chat-123")

        assert response.status_code == 200
        data = response.json()
        assert data["chat_id"] == "test-chat-123"
        assert data["session_id"] == "test-session-456"
        assert data["message_count"] == 10

    def test_get_chat_not_found(self, client, mock_history_service):
        """Test get chat when chat doesn't exist."""
        mock_history_service.get_chat_by_id = AsyncMock(return_value=None)

        response = client.get("/api/v1/chats/test-chat-123")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    # ===== POST /api/v1/chats/{chat_id}/messages =====

    @patch("tarsy.services.history_service.HistoryService.get_chat_by_id", new_callable=AsyncMock)
    def test_send_message_success(self, mock_get_chat, client, mock_chat_service, sample_chat):
        """Test successful message send."""
        mock_get_chat.return_value = sample_chat
        # Mock the new create_user_message_and_start_processing method
        # Returns tuple of (message_id, stage_execution_id)
        mock_chat_service.create_user_message_and_start_processing = AsyncMock(
            return_value=("msg-abc-123", "stage-exec-789")
        )

        # Patch the lock and tasks dict
        with patch("tarsy.main.active_tasks_lock", asyncio.Lock()):
            with patch("tarsy.main.active_chat_tasks", {}):
                response = client.post(
                    "/api/v1/chats/test-chat-123/messages",
                    json={"content": "Test question about the alert"},
                    headers={"X-Forwarded-User": "test-user"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["chat_id"] == "test-chat-123"
        assert data["content"] == "Test question about the alert"
        assert data["author"] == "test-user"
        # Verify the response contains the real database message_id
        assert data["message_id"] == "msg-abc-123"
        # Stage execution ID should also be present for async tracking
        assert data["stage_execution_id"] == "stage-exec-789"
        mock_get_chat.assert_awaited_once_with("test-chat-123")

    def test_send_message_validation_empty_content(self, client):
        """Test message validation rejects empty content."""
        response = client.post(
            "/api/v1/chats/test-chat-123/messages",
            json={"content": ""},
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, list)
        assert len(detail) > 0
        assert detail[0]["type"] == "string_too_short"

    def test_send_message_validation_missing_body(self, client):
        """Test message validation rejects missing request body."""
        response = client.post(
            "/api/v1/chats/test-chat-123/messages",
            json=None,  # No JSON body
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, list)
        # FastAPI should return a validation error for missing required body

    def test_send_message_validation_whitespace_only(self, client):
        """Test message validation rejects whitespace-only content."""
        response = client.post(
            "/api/v1/chats/test-chat-123/messages",
            json={"content": "   "},
        )

        assert response.status_code == 422

    def test_send_message_validation_too_long(self, client):
        """Test message validation rejects content exceeding max length."""
        long_content = "x" * 100001  # Exceeds 100000 char limit
        response = client.post(
            "/api/v1/chats/test-chat-123/messages",
            json={"content": long_content},
        )

        assert response.status_code == 422

    def test_send_message_chat_not_found(self, client, mock_chat_service):
        """Test send message when chat doesn't exist."""
        # Mock create_user_message_and_start_processing to raise ValueError for chat not found
        mock_chat_service.create_user_message_and_start_processing = AsyncMock(
            side_effect=ValueError("Chat test-chat-123 not found")
        )

        response = client.post(
            "/api/v1/chats/test-chat-123/messages",
            json={"content": "Test question"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @patch("tarsy.main.shutdown_in_progress", True)
    def test_send_message_during_shutdown(self, client):
        """Test send message rejects during shutdown."""
        response = client.post(
            "/api/v1/chats/test-chat-123/messages",
            json={"content": "Test question"},
        )

        assert response.status_code == 503
        data = response.json()
        assert "detail" in data
        assert data["detail"]["error"] == "Service shutting down"

    # ===== GET /api/v1/chats/{chat_id}/messages =====

    def test_get_chat_messages_success(self, client, mock_history_service, sample_chat):
        """Test successful message history retrieval."""
        messages = [
            ChatUserMessage(
                message_id=f"msg-{i}",
                chat_id="test-chat-123",
                content=f"Question {i}",
                author="user@example.com",
                created_at_us=int(time.time() * 1_000_000) + i,
            )
            for i in range(3)
        ]

        mock_history_service.get_chat_by_id = AsyncMock(return_value=sample_chat)
        mock_history_service.get_chat_user_messages = AsyncMock(return_value=messages)
        mock_history_service.get_chat_user_message_count = AsyncMock(return_value=3)

        response = client.get("/api/v1/chats/test-chat-123/messages")

        assert response.status_code == 200
        data = response.json()
        assert data["chat_id"] == "test-chat-123"
        assert data["total_count"] == 3
        assert len(data["messages"]) == 3
        assert all(msg["content"].startswith("Question") for msg in data["messages"])

    def test_get_chat_messages_pagination(self, client, mock_history_service, sample_chat):
        """Test message history pagination."""
        mock_history_service.get_chat_by_id = AsyncMock(return_value=sample_chat)
        mock_history_service.get_chat_user_messages = AsyncMock(return_value=[])
        mock_history_service.get_chat_user_message_count = AsyncMock(return_value=100)

        response = client.get("/api/v1/chats/test-chat-123/messages?limit=25&offset=50")

        assert response.status_code == 200
        mock_history_service.get_chat_user_messages.assert_called_once_with(
            chat_id="test-chat-123", limit=25, offset=50
        )

    def test_get_chat_messages_validation_limit_too_high(self, client):
        """Test message history rejects limit exceeding maximum."""
        response = client.get("/api/v1/chats/test-chat-123/messages?limit=200")

        assert response.status_code == 422

    def test_get_chat_messages_validation_negative_offset(self, client):
        """Test message history rejects negative offset."""
        response = client.get("/api/v1/chats/test-chat-123/messages?offset=-5")

        assert response.status_code == 422

    def test_get_chat_messages_chat_not_found(self, client, mock_history_service):
        """Test get messages when chat doesn't exist."""
        mock_history_service.get_chat_by_id = AsyncMock(return_value=None)

        response = client.get("/api/v1/chats/test-chat-123/messages")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

