"""
Integration tests for chat orphan detection and cleanup.

Tests the chat pod tracking, orphan detection, and cleanup mechanisms
that mirror the session orphan detection pattern.
"""

import pytest
import time

from tarsy.models.db_models import Chat, AlertSession
from tarsy.models.constants import AlertSessionStatus
from tarsy.services.history_service import HistoryService
from tarsy.utils.timestamp import now_us


@pytest.mark.integration
class TestChatOrphanDetection:
    """Integration tests for chat orphan detection and cleanup."""
    
    @pytest.fixture
    async def completed_session_with_chat(self, history_service_with_test_db: HistoryService):
        """Create a completed session with a chat for testing."""
        history_service = history_service_with_test_db
        
        # Create session
        session = AlertSession(
            session_id="orphan-test-session",
            alert_type="kubernetes",
            agent_type="KubernetesAgent",
            chain_id="test-chain",
            status=AlertSessionStatus.COMPLETED.value,
            started_at_us=now_us(),
            completed_at_us=now_us(),
            author="test-user@example.com",
        )
        
        def _create_session():
            with history_service.get_repository() as repo:
                repo.session.add(session)
                repo.session.commit()
                repo.session.refresh(session)
                return session
        
        created_session = _create_session()
        
        # Create chat
        chat = Chat(
            session_id=created_session.session_id,
            created_by="test-user@example.com",
            conversation_history="Test history",
            chain_id="test-chain",
            context_captured_at_us=now_us(),
        )
        
        created_chat = await history_service.create_chat(chat)
        
        yield created_session, created_chat
        
        # Cleanup
        def _cleanup():
            with history_service.get_repository() as repo:
                from sqlmodel import select
                stmt = select(AlertSession).where(AlertSession.session_id == "orphan-test-session")
                sessions = repo.session.exec(stmt).all()
                for session in sessions:
                    repo.session.delete(session)
                repo.session.commit()
        
        try:
            _cleanup()
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_start_chat_message_processing_sets_pod_tracking(
        self, history_service_with_test_db, completed_session_with_chat
    ):
        """Test starting message processing sets pod_id and last_interaction_at."""
        history_service = history_service_with_test_db
        session, chat = completed_session_with_chat
        
        # Start processing
        success = await history_service.start_chat_message_processing(
            chat_id=chat.chat_id,
            pod_id="test-pod-123"
        )
        
        assert success is True
        
        # Verify pod tracking was set
        updated_chat = await history_service.get_chat_by_id(chat.chat_id)
        assert updated_chat.pod_id == "test-pod-123"
        assert updated_chat.last_interaction_at is not None
    
    @pytest.mark.asyncio
    async def test_record_chat_interaction_updates_timestamp(
        self, history_service_with_test_db, completed_session_with_chat
    ):
        """Test recording chat interaction updates last_interaction_at."""
        history_service = history_service_with_test_db
        session, chat = completed_session_with_chat
        
        # Start processing
        await history_service.start_chat_message_processing(chat.chat_id, "pod-1")
        
        initial_chat = await history_service.get_chat_by_id(chat.chat_id)
        initial_timestamp = initial_chat.last_interaction_at
        
        # Wait a bit
        time.sleep(0.1)
        
        # Record interaction
        history_service.record_chat_interaction(chat.chat_id)
        
        # Verify timestamp was updated
        updated_chat = await history_service.get_chat_by_id(chat.chat_id)
        assert updated_chat.last_interaction_at > initial_timestamp
    
    @pytest.mark.asyncio
    async def test_find_orphaned_chats_detects_stale_processing(
        self, history_service_with_test_db, completed_session_with_chat
    ):
        """Test orphan detection finds chats with stale last_interaction_at."""
        history_service = history_service_with_test_db
        session, chat = completed_session_with_chat
        
        # Start processing with old timestamp
        old_timestamp = now_us() - (35 * 60 * 1_000_000)  # 35 minutes ago
        
        # Directly set old timestamp in database to simulate orphaned processing
        def _set_old_timestamp():
            with history_service.get_repository() as repo:
                chat_obj = repo.get_chat_by_id(chat.chat_id)
                chat_obj.pod_id = "pod-1"
                chat_obj.last_interaction_at = old_timestamp
                repo.session.add(chat_obj)
                repo.session.commit()
        
        _set_old_timestamp()
        
        # Verify it was set
        check_chat = await history_service.get_chat_by_id(chat.chat_id)
        assert check_chat.pod_id == "pod-1"
        assert check_chat.last_interaction_at == old_timestamp
        
        # Run orphan detection (30 minute timeout)
        orphan_count = history_service.cleanup_orphaned_chats(timeout_minutes=30)
        
        assert orphan_count == 1
        
        # Verify processing markers were cleared
        updated_chat = await history_service.get_chat_by_id(chat.chat_id)
        assert updated_chat.pod_id is None
        assert updated_chat.last_interaction_at is None
    
    @pytest.mark.asyncio
    async def test_orphan_detection_ignores_active_chats(
        self, history_service_with_test_db, completed_session_with_chat
    ):
        """Test orphan detection doesn't affect actively processing chats."""
        history_service = history_service_with_test_db
        session, chat = completed_session_with_chat
        
        # Start processing with recent timestamp
        await history_service.start_chat_message_processing(chat.chat_id, "pod-1")
        
        # Run orphan detection
        orphan_count = history_service.cleanup_orphaned_chats(timeout_minutes=30)
        
        assert orphan_count == 0
        
        # Verify processing markers preserved
        updated_chat = await history_service.get_chat_by_id(chat.chat_id)
        assert updated_chat.pod_id == "pod-1"
        assert updated_chat.last_interaction_at is not None
    
    @pytest.mark.asyncio
    async def test_mark_pod_chats_interrupted_clears_markers(
        self, history_service_with_test_db, completed_session_with_chat
    ):
        """Test graceful shutdown clears processing markers for pod's chats."""
        history_service = history_service_with_test_db
        session, chat = completed_session_with_chat
        
        # Start processing on specific pod
        await history_service.start_chat_message_processing(chat.chat_id, "shutting-down-pod")
        
        # Mark pod chats as interrupted
        interrupted_count = await history_service.mark_pod_chats_interrupted("shutting-down-pod")
        
        assert interrupted_count == 1
        
        # Verify processing markers cleared
        updated_chat = await history_service.get_chat_by_id(chat.chat_id)
        assert updated_chat.pod_id is None
        assert updated_chat.last_interaction_at is None
    
    @pytest.mark.asyncio
    async def test_mark_pod_chats_interrupted_only_affects_pod_chats(
        self, history_service_with_test_db, completed_session_with_chat
    ):
        """Test interrupted marking only affects specified pod's chats."""
        history_service = history_service_with_test_db
        session, chat = completed_session_with_chat
        
        # Start processing on different pod
        await history_service.start_chat_message_processing(chat.chat_id, "other-pod")
        
        # Mark different pod as interrupted
        interrupted_count = await history_service.mark_pod_chats_interrupted("shutting-down-pod")
        
        assert interrupted_count == 0
        
        # Verify processing markers still set
        updated_chat = await history_service.get_chat_by_id(chat.chat_id)
        assert updated_chat.pod_id == "other-pod"
        assert updated_chat.last_interaction_at is not None


@pytest.mark.integration
class TestChatOrphanDetectionMultipleChats:
    """Test orphan detection with multiple chats scenario."""
    
    @pytest.fixture
    async def multiple_chats_scenario(self, history_service_with_test_db: HistoryService):
        """Create multiple chats for testing orphan detection."""
        history_service = history_service_with_test_db
        
        # Create sessions and chats
        chats = []
        for i in range(3):
            session = AlertSession(
                session_id=f"multi-session-{i}",
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
            
            chat = Chat(
                session_id=session.session_id,
                created_by="test-user@example.com",
                conversation_history=f"History {i}",
                chain_id="test-chain",
                context_captured_at_us=now_us(),
            )
            
            created_chat = await history_service.create_chat(chat)
            chats.append(created_chat)
        
        yield chats
        
        # Cleanup
        def _cleanup():
            with history_service.get_repository() as repo:
                from sqlmodel import select
                for i in range(3):
                    stmt = select(AlertSession).where(AlertSession.session_id == f"multi-session-{i}")
                    sessions = repo.session.exec(stmt).all()
                    for session in sessions:
                        repo.session.delete(session)
                repo.session.commit()
        
        try:
            _cleanup()
        except Exception:
            pass
    
    @pytest.mark.asyncio
    async def test_orphan_detection_multiple_chats(
        self, history_service_with_test_db, multiple_chats_scenario
    ):
        """Test orphan detection handles multiple chats correctly."""
        history_service = history_service_with_test_db
        chats = multiple_chats_scenario
        
        # Chat 0: Orphaned (old timestamp) - set directly in DB
        old_timestamp = now_us() - (35 * 60 * 1_000_000)
        def _set_orphaned():
            with history_service.get_repository() as repo:
                chat_obj = repo.get_chat_by_id(chats[0].chat_id)
                chat_obj.pod_id = "pod-1"
                chat_obj.last_interaction_at = old_timestamp
                repo.session.add(chat_obj)
                repo.session.commit()
        _set_orphaned()
        
        # Chat 1: Active (recent timestamp)
        await history_service.start_chat_message_processing(chats[1].chat_id, "pod-2")
        
        # Chat 2: No processing
        # (no pod_id, no last_interaction_at)
        
        # Run orphan cleanup
        orphan_count = history_service.cleanup_orphaned_chats(timeout_minutes=30)
        
        assert orphan_count == 1
        
        # Verify only orphaned chat was cleared
        chat0 = await history_service.get_chat_by_id(chats[0].chat_id)
        assert chat0.pod_id is None
        assert chat0.last_interaction_at is None
        
        chat1 = await history_service.get_chat_by_id(chats[1].chat_id)
        assert chat1.pod_id == "pod-2"
        assert chat1.last_interaction_at is not None
        
        chat2 = await history_service.get_chat_by_id(chats[2].chat_id)
        assert chat2.pod_id is None
        assert chat2.last_interaction_at is None

