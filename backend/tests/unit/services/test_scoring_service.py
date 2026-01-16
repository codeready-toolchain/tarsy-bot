"""
Unit tests for ScoringService - Alert session quality evaluation.

Tests scoring service components including prompt building, score extraction,
database operations, and async scoring execution with LLM judge integration.
"""

from contextlib import asynccontextmanager
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from tarsy.agents.prompts.judges import (
    CURRENT_PROMPT_HASH,
    JUDGE_PROMPT_FOLLOWUP_MISSING_TOOLS,
    JUDGE_PROMPT_SCORE,
)
from tarsy.models.constants import AlertSessionStatus, ScoringStatus
from tarsy.models.db_models import AlertSession, SessionScore
from tarsy.models.history_models import (
    ConversationMessage,
    FinalAnalysisResponse,
    LLMConversationHistory,
)
from tarsy.services.scoring_service import ScoringService
from tarsy.utils.timestamp import now_us


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def mock_llm_conversation_history():
    """Create mock LLM conversation history with sample messages."""
    return LLMConversationHistory(
        model_name="gemini-2.5-pro",
        provider="gemini",
        timestamp_us=now_us(),
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        messages=[
            ConversationMessage(
                role="system", content="You are a helpful assistant analyzing alerts."
            ),
            ConversationMessage(role="user", content="Analyze this pod crash..."),
            ConversationMessage(
                role="assistant",
                content="I'll investigate the pod crash using available tools.",
            ),
            ConversationMessage(
                role="user", content="Tool result: logs show OOMKilled"
            ),
            ConversationMessage(
                role="assistant", content="The pod was terminated due to out of memory."
            ),
        ],
    )


@pytest.fixture
def mock_chat_conversation_history():
    """Create mock chat conversation history."""
    return LLMConversationHistory(
        model_name="gemini-2.5-pro",
        provider="gemini",
        timestamp_us=now_us(),
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
        messages=[
            ConversationMessage(
                role="system", content="You are helping with follow-up questions."
            ),
            ConversationMessage(role="user", content="What caused the OOM?"),
            ConversationMessage(
                role="assistant", content="Memory limit was set too low."
            ),
        ],
    )


@pytest.fixture
def mock_alert_data():
    """Create mock alert data."""
    return {
        "severity": "critical",
        "environment": "production",
        "cluster": "main-cluster",
        "namespace": "test-namespace",
        "pod": "app-pod-123",
        "message": "Pod OOMKilled",
    }


@pytest.fixture
def mock_final_analysis_response(
    mock_llm_conversation_history, mock_chat_conversation_history, mock_alert_data
):
    """Create complete FinalAnalysisResponse for testing."""
    return FinalAnalysisResponse(
        final_analysis="## Root Cause\n\nPod was OOMKilled due to memory limit being too low.\n\n## Recommendations\n\n1. Increase memory limit\n2. Add monitoring",
        final_analysis_summary="Pod crashed due to OOM. Increase memory limit.",
        session_id="test-session-123",
        status=AlertSessionStatus.COMPLETED,
        llm_conversation=mock_llm_conversation_history,
        chat_conversation=mock_chat_conversation_history,
        alert_data=mock_alert_data,
    )


@pytest.fixture
def mock_session_completed(mock_alert_data):
    """Create mock completed session."""
    session = Mock(spec=AlertSession)
    session.session_id = "test-session-123"
    session.status = AlertSessionStatus.COMPLETED.value
    session.final_analysis = "## Root Cause\n\nPod was OOMKilled"
    session.final_analysis_summary = "Pod crashed due to OOM"
    session.alert_data = mock_alert_data
    return session


@pytest.fixture
def mock_score_record_pending():
    """Create mock pending score record."""
    return SessionScore(
        score_id=str(uuid4()),
        session_id="test-session-123",
        prompt_hash=CURRENT_PROMPT_HASH,
        status=ScoringStatus.PENDING.value,
        score_triggered_by="test-user",
        scored_at_us=now_us(),
        started_at_us=now_us(),
    )


@pytest.fixture
def mock_llm_score_response():
    """Create mock LLM response with score on last line."""
    return """## Evaluation

**Logical Flow: 15/25**
The investigation followed a basic pattern but missed several optimization opportunities.

**Consistency: 18/25**
The conclusions are reasonable but confidence level is not well justified.

**Tool Relevance: 12/25**
Only basic tools were used. Did not attempt log inspection or historical data review.

**Synthesis Quality: 14/25**
The final analysis acknowledges some gaps but could be more comprehensive.

**Total Score:**

59"""


@pytest.fixture
def mock_llm_missing_tools_response():
    """Create mock LLM response for missing tools analysis."""
    return """1. **kubectl-logs**: Would have provided direct evidence from pod logs instead of relying on status messages.

2. **read-file**: Could have inspected pod configuration to verify memory limits.

3. **kubectl-events**: Would have shown event history leading up to the OOM condition."""


@pytest.fixture
def scoring_service(isolated_test_settings):
    """Create ScoringService instance with mocked dependencies."""
    with patch(
        "tarsy.services.scoring_service.get_settings",
        return_value=isolated_test_settings,
    ):
        service = ScoringService(isolated_test_settings)
        # Mock the database manager to avoid actual DB initialization
        service.db_manager = Mock()
        service._is_healthy = True
        return service


# ==============================================================================
# TEST HELPERS
# ==============================================================================


def create_mock_repository(mock_repo):
    """Helper to create async context manager for mocking _get_repository."""

    @asynccontextmanager
    async def mock_get_repo():
        yield mock_repo

    return mock_get_repo


# ==============================================================================
# TEST CLASSES
# ==============================================================================


@pytest.mark.unit
class TestConversationFormatting:
    """Test conversation message formatting for judge prompts."""

    def test_format_conversation_messages_with_valid_history(
        self, scoring_service, mock_llm_conversation_history
    ):
        """Test formatting conversation messages with valid LLMConversationHistory."""
        result = scoring_service._format_conversation_messages(
            mock_llm_conversation_history
        )

        # Verify each message is formatted correctly
        assert "[system]" in result
        assert "You are a helpful assistant analyzing alerts." in result
        assert "[user]" in result
        assert "Analyze this pod crash..." in result
        assert "[assistant]" in result
        assert "I'll investigate the pod crash using available tools." in result

        # Verify messages are separated correctly
        lines = result.split("\n")
        assert any("system" in line for line in lines)
        assert any("user" in line for line in lines)
        assert any("assistant" in line for line in lines)

    def test_format_conversation_messages_with_none(self, scoring_service):
        """Test formatting conversation messages with None input."""
        result = scoring_service._format_conversation_messages(None)
        assert result == "(No conversation available)"

    def test_format_conversation_preserves_message_content(
        self, scoring_service, mock_llm_conversation_history
    ):
        """Test that message content is preserved exactly."""
        result = scoring_service._format_conversation_messages(
            mock_llm_conversation_history
        )

        for msg in mock_llm_conversation_history.messages:
            assert msg.content in result


@pytest.mark.unit
class TestPromptBuilding:
    """Test judge prompt construction with placeholder substitution."""

    def test_build_score_prompt_with_complete_response(
        self, scoring_service, mock_final_analysis_response
    ):
        """Test building score prompt with complete FinalAnalysisResponse."""
        result = scoring_service._build_score_prompt(mock_final_analysis_response)

        # Verify all placeholders are replaced (not present in result)
        assert "{{ALERT_DATA}}" not in result
        assert "{{FINAL_ANALYSIS}}" not in result
        assert "{{LLM_CONVERSATION}}" not in result
        assert "{{CHAT_CONVERSATION}}" not in result
        assert "{{OUTPUT_SCHEMA}}" not in result

        # Verify actual data is present
        assert "critical" in result  # From alert_data
        assert "Pod was OOMKilled" in result  # From final_analysis
        assert "[system]" in result  # From llm_conversation
        assert "[user]" in result  # From llm_conversation
        assert "[assistant]" in result  # From llm_conversation
        assert (
            "You MUST end your response with a single line" in result
        )  # Output schema

    def test_build_score_prompt_with_missing_final_analysis(
        self, scoring_service, mock_final_analysis_response
    ):
        """Test building score prompt when final_analysis is None."""
        mock_final_analysis_response.final_analysis = None

        result = scoring_service._build_score_prompt(mock_final_analysis_response)

        assert "(No final analysis available)" in result

    def test_build_score_prompt_with_missing_llm_conversation(
        self, scoring_service, mock_final_analysis_response
    ):
        """Test building score prompt when llm_conversation is None."""
        mock_final_analysis_response.llm_conversation = None

        result = scoring_service._build_score_prompt(mock_final_analysis_response)

        assert "(No conversation available)" in result

    def test_build_score_prompt_with_missing_chat_conversation(
        self, scoring_service, mock_final_analysis_response
    ):
        """Test building score prompt when chat_conversation is None."""
        mock_final_analysis_response.chat_conversation = None

        result = scoring_service._build_score_prompt(mock_final_analysis_response)

        assert "(No chat conversation)" in result

    def test_build_score_prompt_with_chat_conversation_present(
        self,
        scoring_service,
        mock_final_analysis_response,
        mock_chat_conversation_history,
    ):
        """Test building score prompt with chat_conversation present."""
        result = scoring_service._build_score_prompt(mock_final_analysis_response)

        # Verify chat conversation is formatted
        assert "What caused the OOM?" in result
        assert "Memory limit was set too low" in result

    def test_build_score_prompt_alert_data_is_json(
        self, scoring_service, mock_final_analysis_response
    ):
        """Test that alert_data is properly JSON formatted."""
        result = scoring_service._build_score_prompt(mock_final_analysis_response)

        # Verify it's valid JSON by finding and parsing the alert data section
        # The alert data should be properly indented JSON
        assert '"severity": "critical"' in result or '"severity":"critical"' in result


@pytest.mark.unit
class TestScoreExtraction:
    """Test score extraction from LLM responses."""

    @pytest.mark.parametrize(
        "score,expected_score",
        [
            (0, 0),
            (50, 50),
            (100, 100),
            (75, 75),
        ],
    )
    def test_extract_valid_score_from_response(
        self, scoring_service, score, expected_score
    ):
        """Test extracting valid scores from responses."""
        response = f"This is analysis text.\n\n{score}"
        total_score, score_analysis = scoring_service._extract_score_from_response(
            response
        )

        assert total_score == expected_score
        assert score_analysis == "This is analysis text.\n"

    @pytest.mark.parametrize(
        "response",
        [
            "Analysis text\n\n75\n",
            "Analysis text\n\n75 \n",
            "Analysis text\n\n75\t\n",
        ],
    )
    def test_extract_score_with_whitespace(self, scoring_service, response):
        """Test extracting score with various whitespace patterns."""
        total_score, score_analysis = scoring_service._extract_score_from_response(
            response
        )

        assert total_score == 75
        assert "Analysis text\n" in score_analysis

    def test_extract_score_no_score_found(self, scoring_service):
        """Test that None is returned when no score found in response."""
        response = "This is analysis text without a score"

        total_score, score_analysis = scoring_service._extract_score_from_response(
            response
        )

        assert total_score is None
        assert score_analysis == response

    @pytest.mark.parametrize(
        "score",
        [-1, 101, 150, 200],
    )
    def test_extract_score_out_of_range(self, scoring_service, score):
        """Test that scores outside 0-100 range are still extracted (no range validation)."""
        response = f"Analysis text\n\n{score}"

        total_score, score_analysis = scoring_service._extract_score_from_response(
            response
        )

        # Implementation does not validate range, just extracts the integer
        assert total_score == score
        assert score_analysis == "Analysis text\n"

    @pytest.mark.parametrize(
        "invalid_ending",
        ["abc", "75.5", "seventy-five"],
    )
    def test_extract_score_non_integer(self, scoring_service, invalid_ending):
        """Test that None is returned when last line is not a valid integer."""
        response = f"Analysis text\n\n{invalid_ending}"

        total_score, score_analysis = scoring_service._extract_score_from_response(
            response
        )

        # Implementation returns None when it can't parse the score
        assert total_score is None
        assert score_analysis == response


@pytest.mark.unit
class TestDatabaseOperations:
    """Test async database operations with retry logic."""

    @pytest.mark.asyncio
    async def test_create_score_record_success(
        self, scoring_service, mock_score_record_pending
    ):
        """Test successful score record creation."""
        mock_repo = Mock()
        mock_repo.create_session_score = Mock(return_value=mock_score_record_pending)

        @asynccontextmanager
        async def mock_get_repo():
            yield mock_repo

        with patch.object(scoring_service, "_get_repository", new=mock_get_repo):
            result = await scoring_service._create_score_record(
                mock_score_record_pending
            )

            assert result == mock_score_record_pending
            mock_repo.create_session_score.assert_called_once_with(
                mock_score_record_pending
            )

    @pytest.mark.asyncio
    async def test_update_score_status_success(self, scoring_service):
        """Test successful score status update."""
        score_id = "test-score-123"
        new_status = ScoringStatus.IN_PROGRESS.value

        mock_repo = Mock()
        mock_repo.update_score_status = Mock(return_value=True)

        @asynccontextmanager
        async def mock_get_repo():
            yield mock_repo

        with patch.object(scoring_service, "_get_repository", new=mock_get_repo):
            result = await scoring_service._update_score_status(score_id, new_status)

            assert result is True
            mock_repo.update_score_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_score_completion_success(self, scoring_service):
        """Test successful score completion update."""
        score_id = "test-score-123"
        total_score = 67
        score_analysis = "Detailed analysis..."
        missing_tools_analysis = "Tool 1, Tool 2"

        mock_repo = Mock()
        mock_repo.update_score_status = Mock(return_value=True)

        @asynccontextmanager
        async def mock_get_repo():
            yield mock_repo

        with patch.object(scoring_service, "_get_repository", new=mock_get_repo):
            result = await scoring_service._update_score_completion(
                score_id, total_score, score_analysis, missing_tools_analysis
            )

            assert result is True
            # Verify all fields were passed
            call_args = mock_repo.update_score_status.call_args
            assert call_args[1]["score_id"] == score_id
            assert call_args[1]["total_score"] == total_score
            assert call_args[1]["score_analysis"] == score_analysis
            assert call_args[1]["missing_tools_analysis"] == missing_tools_analysis
            assert call_args[1]["status"] == ScoringStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_update_score_failure_success(self, scoring_service):
        """Test successful score failure update."""
        score_id = "test-score-123"
        error_message = "LLM client failed"

        mock_repo = Mock()
        mock_repo.update_score_status = Mock(return_value=True)

        @asynccontextmanager
        async def mock_get_repo():
            yield mock_repo

        with patch.object(scoring_service, "_get_repository", new=mock_get_repo):
            result = await scoring_service._update_score_failure(
                score_id, error_message
            )

            assert result is True
            call_args = mock_repo.update_score_status.call_args
            assert call_args[1]["score_id"] == score_id
            assert call_args[1]["error_message"] == error_message
            assert call_args[1]["status"] == ScoringStatus.FAILED.value

    @pytest.mark.asyncio
    async def test_get_score_by_id_success(
        self, scoring_service, mock_score_record_pending
    ):
        """Test retrieving score by ID."""
        mock_repo = Mock()
        mock_repo.get_score_by_id = Mock(return_value=mock_score_record_pending)

        @asynccontextmanager
        async def mock_get_repo():
            yield mock_repo

        with patch.object(scoring_service, "_get_repository", new=mock_get_repo):
            result = await scoring_service._get_score_by_id("test-score-123")

            assert result == mock_score_record_pending

    @pytest.mark.asyncio
    async def test_get_score_by_id_not_found(self, scoring_service):
        """Test retrieving score by ID when not found."""
        mock_repo = Mock()
        mock_repo.get_score_by_id = Mock(return_value=None)

        @asynccontextmanager
        async def mock_get_repo():
            yield mock_repo

        with patch.object(scoring_service, "_get_repository", new=mock_get_repo):
            result = await scoring_service._get_score_by_id("nonexistent-score")

            assert result is None

    @pytest.mark.asyncio
    async def test_get_latest_score_success(
        self, scoring_service, mock_score_record_pending
    ):
        """Test retrieving latest score for a session."""
        mock_repo = Mock()
        mock_repo.get_latest_score_for_session = Mock(
            return_value=mock_score_record_pending
        )

        @asynccontextmanager
        async def mock_get_repo():
            yield mock_repo

        with patch.object(scoring_service, "_get_repository", new=mock_get_repo):
            result = await scoring_service._get_latest_score("test-session-123")

            assert result == mock_score_record_pending


@pytest.mark.unit
class TestScoringInitiation:
    """Test scoring initiation and validation."""

    @pytest.mark.asyncio
    async def test_initiate_scoring_success(
        self, scoring_service, mock_session_completed, mock_score_record_pending
    ):
        """Test successful scoring initiation for completed session."""
        session_id = "test-session-123"
        triggered_by = "test-user"

        # Mock dependencies
        with patch.object(
            scoring_service.history_service,
            "get_session",
            return_value=mock_session_completed,
        ):
            with patch.object(scoring_service, "_get_latest_score", return_value=None):
                with patch.object(
                    scoring_service,
                    "_create_score_record",
                    return_value=mock_score_record_pending,
                ):
                    with patch("asyncio.create_task") as mock_create_task:
                        result = await scoring_service.initiate_scoring(
                            session_id, triggered_by
                        )

                        assert result == mock_score_record_pending
                        assert result.status == ScoringStatus.PENDING.value
                        mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_initiate_scoring_session_not_found(self, scoring_service):
        """Test error when session not found."""
        from tarsy.services.scoring_service import SessionNotFoundError

        with patch.object(
            scoring_service.history_service, "get_session", return_value=None
        ):
            with pytest.raises(SessionNotFoundError, match="Session .* was not found"):
                await scoring_service.initiate_scoring(
                    "nonexistent-session", "test-user"
                )

    @pytest.mark.asyncio
    async def test_initiate_scoring_session_not_completed(
        self, scoring_service, mock_session_completed
    ):
        """Test error when session is not completed."""
        from tarsy.services.scoring_service import SessionNotCompletedError

        mock_session_completed.status = AlertSessionStatus.IN_PROGRESS.value

        with patch.object(
            scoring_service.history_service,
            "get_session",
            return_value=mock_session_completed,
        ):
            with pytest.raises(SessionNotCompletedError, match="Session must be completed"):
                await scoring_service.initiate_scoring("test-session-123", "test-user")

    @pytest.mark.asyncio
    async def test_initiate_scoring_existing_score_no_force(
        self, scoring_service, mock_session_completed, mock_score_record_pending
    ):
        """Test returning existing score when force_rescore=False."""
        mock_score_record_pending.status = ScoringStatus.COMPLETED.value

        with patch.object(
            scoring_service.history_service,
            "get_session",
            return_value=mock_session_completed,
        ):
            with patch.object(
                scoring_service,
                "_get_latest_score",
                return_value=mock_score_record_pending,
            ):
                result = await scoring_service.initiate_scoring(
                    "test-session-123", "test-user", force_rescore=False
                )

                assert result == mock_score_record_pending

    @pytest.mark.asyncio
    async def test_initiate_scoring_force_rescore_with_completed(
        self, scoring_service, mock_session_completed, mock_score_record_pending
    ):
        """Test force rescoring when existing score is completed."""
        existing_score = Mock(spec=SessionScore)
        existing_score.status = ScoringStatus.COMPLETED.value

        with patch.object(
            scoring_service.history_service,
            "get_session",
            return_value=mock_session_completed,
        ):
            with patch.object(
                scoring_service, "_get_latest_score", return_value=existing_score
            ):
                with patch.object(
                    scoring_service,
                    "_create_score_record",
                    return_value=mock_score_record_pending,
                ):
                    with patch("asyncio.create_task"):
                        result = await scoring_service.initiate_scoring(
                            "test-session-123", "test-user", force_rescore=True
                        )

                        assert result.status == ScoringStatus.PENDING.value

    @pytest.mark.asyncio
    async def test_initiate_scoring_force_rescore_with_in_progress(
        self, scoring_service, mock_session_completed
    ):
        """Test error when forcing rescore while scoring is in progress."""
        existing_score = Mock(spec=SessionScore)
        existing_score.status = ScoringStatus.IN_PROGRESS.value

        with (
            patch.object(
                scoring_service.history_service,
                "get_session",
                return_value=mock_session_completed,
            ),
            patch.object(
                scoring_service, "_get_latest_score", return_value=existing_score
            ),
            pytest.raises(ValueError, match="Cannot force rescore while an already existing scoring"),
        ):
            await scoring_service.initiate_scoring(
                "test-session-123", "test-user", force_rescore=True
            )


@pytest.mark.unit
class TestLLMClientIntegration:
    """Test LLM client retrieval and configuration."""

    def test_get_llm_client_success(self, scoring_service, isolated_test_settings):
        """Test successful LLM client retrieval."""
        mock_client = Mock()
        mock_client.available = True

        with patch("tarsy.services.scoring_service.LLMManager") as mock_manager:
            mock_manager.return_value.get_client.return_value = mock_client

            result = scoring_service._get_llm_client()

            assert result == mock_client

    def test_get_llm_client_unavailable(self, scoring_service):
        """Test error when LLM client is unavailable."""
        mock_client = Mock()
        mock_client.available = False

        with patch("tarsy.services.scoring_service.LLMManager") as mock_manager:
            mock_manager.return_value.get_client.return_value = mock_client

            with pytest.raises(RuntimeError, match="Default LLM client not available"):
                scoring_service._get_llm_client()

    def test_get_llm_client_none_returned(self, scoring_service):
        """Test error when no LLM client is returned."""
        with patch("tarsy.services.scoring_service.LLMManager") as mock_manager:
            mock_manager.return_value.get_client.return_value = None

            with pytest.raises(RuntimeError, match="Default LLM client not available"):
                scoring_service._get_llm_client()


@pytest.mark.unit
class TestServiceInitialization:
    """Test scoring service initialization."""

    def test_initialize_success(self, isolated_test_settings):
        """Test successful service initialization."""
        with patch(
            "tarsy.services.scoring_service.get_settings",
            return_value=isolated_test_settings,
        ):
            with patch(
                "tarsy.services.scoring_service.DatabaseManager"
            ) as mock_db_manager:
                service = ScoringService(isolated_test_settings)
                service.initialize()

                assert service._is_healthy is True
                assert service.db_manager is not None
                mock_db_manager.assert_called_once_with(
                    isolated_test_settings.database_url
                )

    def test_initialize_failure(self, isolated_test_settings):
        """Test service initialization failure."""
        with patch(
            "tarsy.services.scoring_service.get_settings",
            return_value=isolated_test_settings,
        ):
            with patch(
                "tarsy.services.scoring_service.DatabaseManager",
                side_effect=Exception("DB connection failed"),
            ):
                service = ScoringService(isolated_test_settings)
                service.initialize()

                assert service._is_healthy is False


@pytest.mark.unit
class TestPromptHash:
    """Test prompt hash computation and storage."""

    def test_current_prompt_hash_is_valid(self):
        """Test that CURRENT_PROMPT_HASH is a valid SHA256 hash."""
        # SHA256 hash should be 64 characters long (hex string)
        assert len(CURRENT_PROMPT_HASH) == 64
        assert all(c in "0123456789abcdef" for c in CURRENT_PROMPT_HASH)

    def test_prompt_hash_changes_with_prompt_changes(self):
        """Test that hash changes when prompts change."""
        import hashlib

        # Compute hash with modified prompts
        modified_prompts = (
            "modified" + JUDGE_PROMPT_SCORE + JUDGE_PROMPT_FOLLOWUP_MISSING_TOOLS
        )
        modified_hash = hashlib.sha256(modified_prompts.encode("utf-8")).hexdigest()

        # Hash should be different from current
        assert modified_hash != CURRENT_PROMPT_HASH

    @pytest.mark.asyncio
    async def test_hash_stored_in_score_record(
        self, scoring_service, mock_session_completed, mock_score_record_pending
    ):
        """Test that prompt hash is stored when creating score record."""
        with patch.object(
            scoring_service.history_service,
            "get_session",
            return_value=mock_session_completed,
        ):
            with patch.object(scoring_service, "_get_latest_score", return_value=None):
                with patch.object(
                    scoring_service,
                    "_create_score_record",
                    return_value=mock_score_record_pending,
                ) as mock_create:
                    with patch("asyncio.create_task"):
                        await scoring_service.initiate_scoring(
                            "test-session-123", "test-user"
                        )

                        # Verify the score record created had the current hash
                        call_args = mock_create.call_args
                        created_score = call_args[0][0]
                        assert created_score.prompt_hash == CURRENT_PROMPT_HASH
