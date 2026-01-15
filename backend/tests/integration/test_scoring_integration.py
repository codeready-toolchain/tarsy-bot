"""
Integration tests for Scoring Service functionality.

Tests the complete scoring service integration including database operations,
LLM client interaction, and end-to-end scoring workflows.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from tarsy.agents.prompts.judges import CURRENT_PROMPT_HASH
from tarsy.models.constants import AlertSessionStatus, ScoringStatus
from tarsy.models.db_models import AlertSession, SessionScore
from tarsy.models.history_models import (
    ConversationMessage,
    LLMConversationHistory,
)
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.repositories.base_repository import DatabaseManager
from tarsy.services.history_service import HistoryService
from tarsy.services.scoring_service import ScoringService
from tarsy.utils.timestamp import now_us


@pytest.mark.integration
class TestScoringServiceIntegration:
    """Integration tests for complete scoring service workflow."""

    @pytest.fixture
    def in_memory_engine(self):
        """Create in-memory SQLite engine for testing."""
        # Use StaticPool for SQLite in-memory to allow access from thread pool
        engine = create_engine(
            "sqlite:///:memory:",
            echo=False,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        SQLModel.metadata.create_all(engine)
        return engine

    @pytest.fixture
    def db_manager(self, in_memory_engine):
        """Create database manager with test database."""
        from sqlmodel import Session
        from sqlalchemy.orm import sessionmaker

        manager = DatabaseManager("sqlite:///:memory:")
        manager.engine = (
            in_memory_engine  # Use the same engine with tables already created
        )
        manager.session_factory = sessionmaker(
            bind=in_memory_engine, class_=Session, expire_on_commit=False
        )
        return manager

    @pytest.fixture
    def history_service(self, db_manager, isolated_test_settings):
        """Create history service with test database."""
        with patch(
            "tarsy.services.history_service.base_infrastructure.get_settings",
            return_value=isolated_test_settings,
        ):
            service = HistoryService()
            service._infra.db_manager = db_manager
            service._infra._set_healthy_for_testing(is_healthy=True)
            return service

    @pytest.fixture
    def scoring_service(self, db_manager, history_service, isolated_test_settings):
        """Create scoring service with test database and real history service."""
        with patch(
            "tarsy.services.scoring_service.get_settings",
            return_value=isolated_test_settings,
        ):
            service = ScoringService()
            service.db_manager = db_manager
            service.history_service = history_service
            service._is_healthy = True
            return service

    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client for scoring."""
        client = Mock()
        client.available = True

        # Mock score response (Turn 1)
        async def mock_generate_score(*args, **kwargs):
            conversation = kwargs.get("conversation")
            # Add assistant message with score
            conversation.append_assistant_message(
                """## Evaluation

**Logical Flow: 18/25**
The investigation followed a reasonable pattern with good use of tools.

**Consistency: 20/25**
Conclusions are well-supported by evidence gathered.

**Tool Relevance: 17/25**
Good tool selection, though some opportunities were missed.

**Synthesis Quality: 18/25**
Final analysis is comprehensive and acknowledges limitations.

73"""
            )
            return conversation

        # Mock missing tools response (Turn 2)
        turn_count = {"count": 0}

        async def mock_generate(*args, **kwargs):
            conversation = kwargs.get("conversation")
            turn_count["count"] += 1

            if turn_count["count"] == 1:
                # Turn 1: Score response
                conversation.append_assistant_message(
                    """## Evaluation

**Logical Flow: 18/25**
The investigation followed a reasonable pattern.

**Consistency: 20/25**
Conclusions are well-supported.

**Tool Relevance: 17/25**
Good tool selection overall.

**Synthesis Quality: 18/25**
Comprehensive final analysis.

73"""
                )
            else:
                # Turn 2: Missing tools analysis
                conversation.append_assistant_message(
                    """1. **kubectl-describe**: Would have provided more detailed pod information.

2. **read-file**: Could have inspected configuration files for root cause analysis."""
                )

            return conversation

        client.generate_response = AsyncMock(side_effect=mock_generate)
        return client

    @pytest.fixture
    def completed_session(self, db_manager):
        """Create a completed alert session in the database."""
        session_id = f"test-session-{uuid4()}"
        alert_data = {
            "severity": "critical",
            "environment": "production",
            "cluster": "main-cluster",
            "namespace": "test-namespace",
            "pod": "app-pod-123",
            "message": "Pod OOMKilled",
        }

        session = AlertSession(
            session_id=session_id,
            agent_type="KubernetesAgent",
            alert_type="kubernetes",
            chain_id="kubernetes_chain",
            status=AlertSessionStatus.COMPLETED.value,
            alert_data=alert_data,
            final_analysis="## Root Cause\n\nPod was OOMKilled due to insufficient memory.\n\n## Recommendations\n\n1. Increase memory limits\n2. Add monitoring",
            final_analysis_summary="Pod crashed due to OOM. Increase memory limit.",
            created_at_us=now_us(),
            started_at_us=now_us(),
            completed_at_us=now_us(),
        )

        with db_manager.get_session() as db_session:
            db_session.add(session)
            db_session.commit()
            db_session.refresh(session)

        return session

    @pytest.mark.asyncio
    async def test_end_to_end_score_completed_session(
        self, scoring_service, completed_session, mock_llm_client
    ):
        """Test complete workflow: initiate scoring → execute → store results."""
        session_id = completed_session.session_id

        # Mock LLM client
        with patch.object(
            scoring_service, "_get_llm_client", return_value=mock_llm_client
        ):
            # Initiate scoring
            score_record = await scoring_service.initiate_scoring(
                session_id=session_id, triggered_by="test-user"
            )

            # Verify initial state
            assert score_record.status == ScoringStatus.PENDING
            assert score_record.session_id == session_id
            assert score_record.prompt_hash == CURRENT_PROMPT_HASH
            assert score_record.score_triggered_by == "test-user"

            # Wait for background task to complete
            await asyncio.sleep(0.5)

            # Retrieve the score from database
            final_score = await scoring_service._get_score_by_id(score_record.score_id)

            # Verify final state
            assert final_score is not None
            assert final_score.status == ScoringStatus.COMPLETED
            assert final_score.total_score == 73
            assert final_score.score_analysis is not None
            assert "Logical Flow" in final_score.score_analysis
            assert final_score.missing_tools_analysis is not None
            assert "kubectl-describe" in final_score.missing_tools_analysis
            assert final_score.completed_at_us is not None

    @pytest.mark.asyncio
    async def test_multiple_scoring_attempts_same_session(
        self, scoring_service, completed_session, mock_llm_client
    ):
        """Test multiple scoring attempts for the same session."""
        session_id = completed_session.session_id

        with patch.object(
            scoring_service, "_get_llm_client", return_value=mock_llm_client
        ):
            # First scoring attempt
            score1 = await scoring_service.initiate_scoring(
                session_id=session_id, triggered_by="user1"
            )
            await asyncio.sleep(0.5)

            # Second attempt without force_rescore should return existing
            score2 = await scoring_service.initiate_scoring(
                session_id=session_id, triggered_by="user2", force_rescore=False
            )

            assert score2.score_id == score1.score_id  # Same score returned

            # Third attempt with force_rescore should create new score
            score3 = await scoring_service.initiate_scoring(
                session_id=session_id, triggered_by="user3", force_rescore=True
            )
            await asyncio.sleep(0.5)

            assert score3.score_id != score1.score_id  # New score created

            # Verify latest score is returned
            latest_score = await scoring_service._get_latest_score(session_id)
            assert latest_score.score_id == score3.score_id

    @pytest.mark.asyncio
    async def test_concurrent_scoring_prevention(
        self, scoring_service, completed_session, mock_llm_client, db_manager
    ):
        """Test that database constraint prevents duplicate concurrent scoring."""
        session_id = completed_session.session_id

        # Manually create a PENDING score to simulate active scoring
        pending_score = SessionScore(
            score_id=str(uuid4()),
            session_id=session_id,
            prompt_hash=CURRENT_PROMPT_HASH,
            status=ScoringStatus.PENDING.value,
            score_triggered_by="concurrent-user",
            scored_at_us=now_us(),
            started_at_us=now_us(),
        )

        with db_manager.get_session() as db_session:
            db_session.add(pending_score)
            db_session.commit()

        # Try to initiate scoring while one is already PENDING
        with patch.object(
            scoring_service, "_get_llm_client", return_value=mock_llm_client
        ):
            with pytest.raises(ValueError, match="Cannot force rescore while scoring"):
                await scoring_service.initiate_scoring(
                    session_id=session_id, triggered_by="test-user", force_rescore=True
                )

    @pytest.mark.asyncio
    async def test_scoring_failure_updates_status(
        self, scoring_service, completed_session, mock_llm_client
    ):
        """Test that scoring failures properly update status to FAILED."""
        session_id = completed_session.session_id

        # Make LLM client raise an exception
        mock_llm_client.generate_response = AsyncMock(
            side_effect=Exception("LLM service unavailable")
        )

        with patch.object(
            scoring_service, "_get_llm_client", return_value=mock_llm_client
        ):
            score_record = await scoring_service.initiate_scoring(
                session_id=session_id, triggered_by="test-user"
            )

            # Wait for background task to fail
            await asyncio.sleep(0.5)

            # Retrieve the score from database
            final_score = await scoring_service._get_score_by_id(score_record.score_id)

            # Verify failure state
            assert final_score.status == ScoringStatus.FAILED
            assert final_score.error_message is not None
            assert "LLM service unavailable" in final_score.error_message
            assert final_score.total_score is None  # No score extracted
            assert (
                final_score.completed_at_us is not None
            )  # Still has completion timestamp

    @pytest.mark.asyncio
    async def test_score_extraction_failure(
        self, scoring_service, completed_session, mock_llm_client
    ):
        """Test scoring fails gracefully when score cannot be extracted from LLM response."""
        session_id = completed_session.session_id

        # Mock LLM client to return response without valid score
        async def mock_generate_bad_response(*args, **kwargs):
            conversation = kwargs.get("conversation")
            conversation.append_assistant_message(
                "This is an analysis but no score at the end!"
            )
            return conversation

        mock_llm_client.generate_response = AsyncMock(
            side_effect=mock_generate_bad_response
        )

        with patch.object(
            scoring_service, "_get_llm_client", return_value=mock_llm_client
        ):
            score_record = await scoring_service.initiate_scoring(
                session_id=session_id, triggered_by="test-user"
            )

            # Wait for background task to fail
            await asyncio.sleep(0.5)

            # Retrieve the score from database
            final_score = await scoring_service._get_score_by_id(score_record.score_id)

            # Verify failure state
            assert final_score.status == ScoringStatus.FAILED
            assert final_score.error_message is not None
            assert "Could not extract the total score" in final_score.error_message
            assert final_score.total_score is None
