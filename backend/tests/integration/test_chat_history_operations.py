"""
Integration tests for chat database operations.

Tests HistoryRepository and HistoryService chat CRUD operations with real database.
"""

import pytest
from tarsy.models.db_models import Chat, ChatUserMessage, AlertSession
from tarsy.models.constants import AlertSessionStatus
from tarsy.services.history_service import HistoryService
from tarsy.utils.timestamp import now_us


@pytest.mark.integration
class TestChatHistoryOperations:
    """Integration tests for chat database operations."""
    
    @pytest.fixture
    async def test_session(self, history_service_with_test_db: HistoryService):
        """Create a test session for chat tests."""
        history_service = history_service_with_test_db
        
        session = AlertSession(
            session_id="chat-hist-session",
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            chain_id="test-chain",
            status=AlertSessionStatus.COMPLETED.value,
            started_at_us=now_us(),
            completed_at_us=now_us(),
            author="test-user@example.com",
        )
        
        with history_service.get_repository() as repo:
            repo.session.add(session)
            repo.session.commit()
            repo.session.refresh(session)
        
        yield session
        
        # Cleanup
        def _cleanup():
            with history_service.get_repository() as repo:
                from sqlmodel import select
                stmt = select(AlertSession).where(AlertSession.session_id == "chat-hist-session")
                sessions = repo.session.exec(stmt).all()
                for session in sessions:
                    repo.session.delete(session)
                repo.session.commit()
        
        try:
            _cleanup()
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_create_and_get_chat(
        self, history_service_with_test_db, test_session
    ):
        """Test creating and retrieving a chat."""
        history_service = history_service_with_test_db
        
        chat = Chat(
            session_id=test_session.session_id,
            created_by="user@example.com",
            conversation_history="Test investigation history",
            chain_id="test-chain",
            context_captured_at_us=now_us(),
        )
        
        created_chat = await history_service.create_chat(chat)
        
        assert created_chat.chat_id is not None
        assert created_chat.session_id == test_session.session_id
        
        # Retrieve by ID
        retrieved_chat = await history_service.get_chat_by_id(created_chat.chat_id)
        assert retrieved_chat.chat_id == created_chat.chat_id
        assert retrieved_chat.conversation_history == "Test investigation history"
    
    @pytest.mark.asyncio
    async def test_get_chat_by_session(
        self, history_service_with_test_db, test_session
    ):
        """Test retrieving chat by session ID."""
        history_service = history_service_with_test_db
        
        chat = Chat(
            session_id=test_session.session_id,
            created_by="user@example.com",
            conversation_history="History",
            chain_id="test-chain",
            context_captured_at_us=now_us(),
        )
        
        created_chat = await history_service.create_chat(chat)
        
        # Retrieve by session
        retrieved_chat = await history_service.get_chat_by_session(test_session.session_id)
        assert retrieved_chat.chat_id == created_chat.chat_id
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_chat(self, history_service_with_test_db):
        """Test retrieving nonexistent chat returns None."""
        history_service = history_service_with_test_db
        
        chat = await history_service.get_chat_by_id("nonexistent-chat-id")
        assert chat is None
        
        chat_by_session = await history_service.get_chat_by_session("nonexistent-session")
        assert chat_by_session is None
    
    @pytest.mark.asyncio
    async def test_create_and_retrieve_chat_user_messages(
        self, history_service_with_test_db, test_session
    ):
        """Test creating and retrieving chat user messages."""
        history_service = history_service_with_test_db
        
        # Create chat
        chat = Chat(
            session_id=test_session.session_id,
            created_by="user@example.com",
            conversation_history="History",
            chain_id="test-chain",
            context_captured_at_us=now_us(),
        )
        created_chat = await history_service.create_chat(chat)
        
        # Create messages
        messages_data = [
            ("First question", "user1@example.com"),
            ("Second question", "user2@example.com"),
            ("Third question", "user1@example.com"),
        ]
        
        for i, (content, author) in enumerate(messages_data):
            msg = ChatUserMessage(
                chat_id=created_chat.chat_id,
                content=content,
                author=author,
                created_at_us=now_us() + i,  # Ensure ordering
            )
            await history_service.create_chat_user_message(msg)
        
        # Retrieve all messages
        messages = await history_service.get_chat_user_messages(
            chat_id=created_chat.chat_id,
            limit=10,
            offset=0
        )
        
        assert len(messages) == 3
        assert messages[0].content == "First question"
        assert messages[1].content == "Second question"
        assert messages[2].content == "Third question"
        
        # Check count
        count = await history_service.get_chat_user_message_count(created_chat.chat_id)
        assert count == 3
    
    @pytest.mark.asyncio
    async def test_chat_user_messages_pagination(
        self, history_service_with_test_db, test_session
    ):
        """Test paginating chat user messages."""
        history_service = history_service_with_test_db
        
        # Create chat
        chat = Chat(
            session_id=test_session.session_id,
            created_by="user@example.com",
            conversation_history="History",
            chain_id="test-chain",
            context_captured_at_us=now_us(),
        )
        created_chat = await history_service.create_chat(chat)
        
        # Create 10 messages
        for i in range(10):
            msg = ChatUserMessage(
                chat_id=created_chat.chat_id,
                content=f"Question {i}",
                author="user@example.com",
                created_at_us=now_us() + i,
            )
            await history_service.create_chat_user_message(msg)
        
        # Test pagination
        page1 = await history_service.get_chat_user_messages(
            chat_id=created_chat.chat_id,
            limit=4,
            offset=0
        )
        page2 = await history_service.get_chat_user_messages(
            chat_id=created_chat.chat_id,
            limit=4,
            offset=4
        )
        page3 = await history_service.get_chat_user_messages(
            chat_id=created_chat.chat_id,
            limit=4,
            offset=8
        )
        
        assert len(page1) == 4
        assert len(page2) == 4
        assert len(page3) == 2
        
        assert page1[0].content == "Question 0"
        assert page2[0].content == "Question 4"
        assert page3[0].content == "Question 8"
    
    @pytest.mark.asyncio
    async def test_chat_cascade_delete(
        self, history_service_with_test_db, test_session
    ):
        """Test deleting chat cascades to user messages."""
        history_service = history_service_with_test_db
        
        # Create chat with messages
        chat = Chat(
            session_id=test_session.session_id,
            created_by="user@example.com",
            conversation_history="History",
            chain_id="test-chain",
            context_captured_at_us=now_us(),
        )
        created_chat = await history_service.create_chat(chat)
        
        # Create messages
        for i in range(3):
            msg = ChatUserMessage(
                chat_id=created_chat.chat_id,
                content=f"Question {i}",
                author="user@example.com",
                created_at_us=now_us() + i,
            )
            await history_service.create_chat_user_message(msg)
        
        # Verify messages exist
        messages_before = await history_service.get_chat_user_messages(
            chat_id=created_chat.chat_id,
            limit=10,
            offset=0
        )
        assert len(messages_before) == 3
        
        # Delete chat
        with history_service.get_repository() as repo:
            from sqlmodel import select
            stmt = select(Chat).where(Chat.chat_id == created_chat.chat_id)
            chats = repo.session.exec(stmt).all()
            for chat in chats:
                repo.session.delete(chat)
            repo.session.commit()
        
        # Verify chat and messages deleted
        deleted_chat = await history_service.get_chat_by_id(created_chat.chat_id)
        assert deleted_chat is None
        
        messages_after = await history_service.get_chat_user_messages(
            chat_id=created_chat.chat_id,
            limit=10,
            offset=0
        )
        assert len(messages_after) == 0

