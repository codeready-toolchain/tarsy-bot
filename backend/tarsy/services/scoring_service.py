"""
Scoring Service for Alert Session Quality Evaluation.

Provides centralized management of session scoring including LLM-based judge
evaluation, score extraction, and database persistence with async execution.
"""

import asyncio
import random
import re
import uuid
from contextlib import asynccontextmanager
from typing import Optional, Tuple

from tarsy.agents.prompts.judges import (
    CURRENT_PROMPT_HASH,
    JUDGE_PROMPT_FOLLOWUP_MISSING_TOOLS,
    JUDGE_PROMPT_SCORE,
    JUDGE_PROMPT_SCORE_REMINDER,
    JUDGE_SYSTEM_PROMPT,
)
from tarsy.config.settings import Settings, get_settings
from tarsy.integrations.llm.client import LLMClient
from tarsy.integrations.llm.manager import LLMManager
from tarsy.models.constants import (
    AlertSessionStatus,
    LLMInteractionType,
    ScoringStatus,
)
from tarsy.models.db_models import SessionScore
from tarsy.models.history_models import FinalAnalysisResponse, LLMConversationHistory
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.repositories.base_repository import DatabaseManager
from tarsy.repositories.session_score_repository import SessionScoreRepository
from tarsy.services.history_service import get_history_service
from tarsy.utils.logger import get_logger
from tarsy.utils.timestamp import now_us

logger = get_logger(__name__)


class ScoringService:
    """
    Core service for managing alert session scoring.

    Provides high-level operations for session scoring, LLM judge evaluation,
    and database persistence with integrated error handling and retry logic.
    """

    def __init__(self, settings: Optional[Settings] = None):
        """Initialize scoring service with configuration."""
        self.settings = settings or get_settings()
        self.history_service = get_history_service()
        self.db_manager: Optional[DatabaseManager] = None
        self._is_healthy = False

        # Retry configuration for database operations (matches HistoryService)
        self.max_retries = 3
        self.base_delay = 0.1  # 100ms base delay
        self.max_delay = 2.0  # 2 second max delay

    def initialize(self):
        """
        Initialize database manager.

        Sets up database connectivity for scoring operations.
        """
        try:
            self.db_manager = DatabaseManager(self.settings.database_url)
            self.db_manager.initialize()
            self.db_manager.create_tables()
            self._is_healthy = True
            logger.info("ScoringService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ScoringService: {str(e)}")
            self._is_healthy = False

    @asynccontextmanager
    async def _get_repository(self):
        """
        Get scoring repository with session management.

        Yields:
            SessionScoreRepository instance or None if unavailable
        """
        if not self.db_manager:
            logger.warning("Database manager not initialized")
            yield None
            return

        try:
            with self.db_manager.get_session() as session:
                yield SessionScoreRepository(session)
        except Exception as e:
            logger.error(f"Failed to get scoring repository: {str(e)}")
            yield None

    def _format_conversation_messages(
        self, conversation: Optional[LLMConversationHistory]
    ) -> str:
        """
        Format LLM conversation messages for judge prompt.

        Extracts only the messages (role + content) without metadata like
        tokens, provider, timestamps.

        Args:
            conversation: LLMConversationHistory or None

        Returns:
            Formatted conversation string
        """
        if conversation is None:
            return "(No conversation available)"

        formatted_messages = []
        for msg in conversation.messages:
            role = msg.role if msg.role else "UNKNOWN"
            formatted_messages.append(f"[{role}]\n{msg.content}\n")

        return "\n".join(formatted_messages)

    def _build_score_prompt(
        self, final_analysis_response: FinalAnalysisResponse
    ) -> str:
        """
        Build judge score prompt with placeholder substitution.

        Replaces placeholders with structured data from the session:
        - {{ALERT_DATA}}: Original alert JSON
        - {{FINAL_ANALYSIS}}: Agent's final analysis (markdown)
        - {{LLM_CONVERSATION}}: Formatted conversation messages (role + content only)
        - {{CHAT_CONVERSATION}}: Formatted chat messages if exists
        - {{OUTPUT_SCHEMA}}: Score format instructions

        Args:
            final_analysis_response: Complete session data from History Service

        Returns:
            Formatted judge prompt ready for LLM
        """
        import json

        # Extract and format each component
        alert_data_json = json.dumps(final_analysis_response.alert_data, indent=2)

        final_analysis_text = (
            final_analysis_response.final_analysis or "(No final analysis available)"
        )

        # Format conversations as readable message sequences (not JSON dumps)
        llm_conversation_text = self._format_conversation_messages(
            final_analysis_response.llm_conversation
        )

        chat_conversation_text = (
            self._format_conversation_messages(
                final_analysis_response.chat_conversation
            )
            if final_analysis_response.chat_conversation
            else "(No chat conversation)"
        )
        output_schema = "You MUST end your response with a single line containing ONLY the total score as an integer (0-100)"

        # Replace all placeholders
        prompt = JUDGE_PROMPT_SCORE
        prompt = prompt.replace("{{ALERT_DATA}}", alert_data_json)
        prompt = prompt.replace("{{FINAL_ANALYSIS}}", final_analysis_text)
        prompt = prompt.replace("{{LLM_CONVERSATION}}", llm_conversation_text)
        prompt = prompt.replace("{{CHAT_CONVERSATION}}", chat_conversation_text)
        prompt = prompt.replace("{{OUTPUT_SCHEMA}}", output_schema)

        logger.debug(
            f"Built prompt with placeholders: "
            f"alert_data={len(alert_data_json)} chars, "
            f"final_analysis={len(final_analysis_text)} chars, "
            f"llm_conversation={len(llm_conversation_text)} chars, "
            f"chat_conversation={len(chat_conversation_text)} chars"
        )

        return prompt

    def _build_score_reminder_prompt(self):
        output_schema = "You MUST respond with single line containing ONLY the total score as an integer (0-100)"
        prompt = JUDGE_PROMPT_SCORE_REMINDER
        prompt = prompt.replace("{{OUTPUT_SCHEMA}}", output_schema)
        return prompt

    def _extract_score_from_response(self, response: str) -> Tuple[Optional[int], str]:
        """
        Extract total_score and analysis from LLM response.

        Score is expected on the last line via regex: r'(\\d+)\\s*$'
        Analysis is everything before the score line.

        If the total score could not be extracted, None is returned instead, along with the full response
        as the score analysis.

        Args:
            response: LLM response text

        Returns:
            Tuple of (total_score, score_analysis)
        """
        # Find score on last line
        lines = response.splitlines()
        last_line = lines[-1]
        score_match = re.search(r"^((\+|-)?(\d+))\s*$", last_line)
        if not score_match:
            logger.error(
                f"No score found on the last line in the response: {last_line[:500]}..."
            )
            return None, response

        total_score = int(score_match.group(1))

        # Extract analysis (everything before score)
        score_analysis = "\n".join(response.splitlines()[0:-1])

        return total_score, score_analysis

    def _get_llm_client(self) -> LLMClient:
        """
        Get LLM client for judge interactions.

        Uses TARSy's default LLM from LLMManager.

        Returns:
            LLM client instance

        Raises:
            RuntimeError: If default client unavailable
        """
        llm_manager = LLMManager(self.settings)
        client = llm_manager.get_client()

        if not client or not client.available:
            raise RuntimeError("Default LLM client not available")

        return client

    async def _retry_database_operation_async(
        self,
        operation_name: str,
        operation_func,
        treat_none_as_success: bool = False,
    ):
        """
        Retry database operations with exponential backoff for transient failures.

        Args:
            operation_name: Name of the operation for logging
            operation_func: Async function to retry
            treat_none_as_success: Whether None is an acceptable outcome

        Returns:
            Result of the operation, or None if all retries failed
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                result = (
                    await operation_func()
                    if asyncio.iscoroutinefunction(operation_func)
                    else operation_func()
                )
                if result is not None:
                    return result
                if treat_none_as_success:
                    return None

                logger.warning(
                    f"Database operation '{operation_name}' returned None on attempt {attempt + 1}"
                )

            except Exception as e:
                last_exception = e
                error_msg = str(e).lower()

                # Check if this is a retryable database error
                is_retryable = any(
                    keyword in error_msg
                    for keyword in [
                        "database is locked",
                        "database disk image is malformed",
                        "sqlite3.operationalerror",
                        "connection timeout",
                        "database table is locked",
                    ]
                )

                if attempt < self.max_retries and is_retryable:
                    # Calculate exponential backoff with jitter
                    delay = min(self.base_delay * (2**attempt), self.max_delay)
                    jitter = random.uniform(0, delay * 0.1)
                    total_delay = delay + jitter

                    logger.warning(
                        f"Database operation '{operation_name}' failed (attempt {attempt + 1}/{self.max_retries + 1}): "
                        f"{str(e)}. Retrying in {total_delay:.2f}s..."
                    )
                    await asyncio.sleep(total_delay)
                else:
                    logger.error(
                        f"Database operation '{operation_name}' failed permanently after {attempt + 1} attempts: {str(e)}"
                    )
                    raise

        # All retries exhausted
        if last_exception:
            logger.error(
                f"Database operation '{operation_name}' failed after all retries"
            )
            raise last_exception

        return None

    async def _create_score_record(self, score: SessionScore) -> Optional[SessionScore]:
        """
        Create a new session scoring record with retry logic.

        Args:
            score: SessionScore instance to create

        Returns:
            Created SessionScore

        Raises:
            RuntimeError: If database operation fails after retries
        """

        async def _create():
            async with self._get_repository() as repo:
                if not repo:
                    raise RuntimeError("Scoring repository unavailable")
                return repo.create_session_score(score)

        return await self._retry_database_operation_async(
            "create_score_record", _create
        )

    async def _update_score_status(
        self,
        score_id: str,
        status: ScoringStatus,
        completed_at_us: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Update scoring status and related fields.

        Args:
            score_id: Score identifier
            status: New status value
            completed_at_us: Optional completion timestamp
            error_message: Optional error details (for FAILED/TIMED_OUT)

        Returns:
            True if successful, False otherwise
        """

        async def _update():
            async with self._get_repository() as repo:
                if not repo:
                    raise RuntimeError("Scoring repository unavailable")
                return repo.update_score_status(
                    score_id=score_id,
                    status=status,
                    completed_at_us=completed_at_us,
                    error_message=error_message,
                )

        return (
            await self._retry_database_operation_async("update_score_status", _update)
            or False
        )

    async def _update_score_completion(
        self,
        score_id: str,
        total_score: int,
        score_analysis: str,
        missing_tools_analysis: str,
    ) -> bool:
        """
        Update score with complete results and mark as completed.

        Args:
            score_id: Score identifier
            total_score: Extracted score (0-100)
            score_analysis: Detailed scoring analysis
            missing_tools_analysis: Missing tools analysis

        Returns:
            True if successful, False otherwise
        """

        async def _update():
            async with self._get_repository() as repo:
                if not repo:
                    raise RuntimeError("Scoring repository unavailable")
                return repo.update_score_status(
                    score_id=score_id,
                    status=ScoringStatus.COMPLETED,
                    completed_at_us=now_us(),
                    total_score=total_score,
                    score_analysis=score_analysis,
                    missing_tools_analysis=missing_tools_analysis,
                )

        return (
            await self._retry_database_operation_async(
                "update_score_completion", _update
            )
            or False
        )

    async def _get_score_by_id(self, score_id: str) -> Optional[SessionScore]:
        """
        Retrieve a score record by ID.

        Args:
            score_id: Score identifier

        Returns:
            SessionScore or None if not found
        """

        async def _get():
            async with self._get_repository() as repo:
                if not repo:
                    raise RuntimeError("Scoring repository unavailable")
                return repo.get_score_by_id(score_id)

        return await self._retry_database_operation_async(
            "get_score_by_id", _get, treat_none_as_success=True
        )

    async def _get_latest_score(self, session_id: str) -> Optional[SessionScore]:
        """
        Get the most recent score for a session.

        Args:
            session_id: Session identifier

        Returns:
            SessionScore or None if no scores exist
        """

        async def _get():
            async with self._get_repository() as repo:
                if not repo:
                    raise RuntimeError("Scoring repository unavailable")
                return repo.get_latest_score_for_session(session_id)

        return await self._retry_database_operation_async(
            "get_latest_score", _get, treat_none_as_success=True
        )

    async def initiate_scoring(
        self, session_id: str, triggered_by: str, force_rescore: bool = False
    ) -> SessionScore:
        """
        Initiate scoring for a session (returns immediately, launches background task).

        Validates session is completed, creates pending score record, and launches
        background scoring task. Returns immediately for async API response.

        Args:
            session_id: Session identifier to score
            triggered_by: User who triggered the scoring
            force_rescore: If True, re-score even if score exists

        Returns:
            Pending SessionScore record

        Raises:
            ValueError: Session not found or not completed
            RuntimeError: Database operation failed
        """
        logger.info(
            f"Initiating scoring for session {session_id} (triggered_by={triggered_by}, force_rescore={force_rescore})"
        )

        # Validate session exists and is COMPLETED
        session = self.history_service.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session.status != AlertSessionStatus.COMPLETED.value:
            raise ValueError(
                f"Session must be completed (current status: {session.status})"
            )

        # Check for existing score
        existing_score = await self._get_latest_score(session_id)
        if existing_score:
            if not force_rescore:
                return existing_score
            else:
                if existing_score.status in ScoringStatus.active_values():
                    raise ValueError(
                        f"Cannot force rescore while scoring is {existing_score.status}"
                    )

        # Create pending score record
        score_record = SessionScore(
            score_id=str(uuid.uuid4()),
            session_id=session_id,
            prompt_hash=CURRENT_PROMPT_HASH,
            status=ScoringStatus.PENDING,
            score_triggered_by=triggered_by,
            scored_at_us=now_us(),
            started_at_us=now_us(),
        )

        score_record = await self._create_score_record(score_record)
        if not score_record:
            raise ValueError(f"Could not create score record {score_record}")

        logger.info(
            f"Created pending score {score_record.score_id} for session {session_id}"
        )

        # Launch background scoring task with timeout wrapper
        asyncio.create_task(
            self._execute_scoring_with_timeout(score_record.score_id, session_id)
        )
        logger.debug(
            f"Launched background scoring task for score {score_record.score_id}"
        )

        return score_record

    async def _execute_scoring_with_timeout(
        self, score_id: str, session_id: str
    ) -> None:
        """
        Wrapper for _execute_scoring() with timeout enforcement.

        Wraps the scoring execution with asyncio.wait_for() to enforce
        the configured timeout. Catches TimeoutError and marks score as
        TIMED_OUT with elapsed time.

        Args:
            score_id: Score record identifier
            session_id: Session to score
        """
        timeout = self.settings.scoring_timeout
        start_time = now_us()

        try:
            await asyncio.wait_for(
                self._execute_scoring(score_id, session_id),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            # Calculate elapsed time in seconds
            elapsed_us = now_us() - start_time
            elapsed_s = elapsed_us // 1_000_000

            error_msg = f"Scoring timed out after {elapsed_s}s (timeout: {timeout}s)"
            await self._update_score_status(
                score_id=score_id,
                status=ScoringStatus.TIMED_OUT,
                completed_at_us=now_us(),
                error_message=error_msg,
            )

            logger.warning(
                f"Scoring timed out for score {score_id}, session {session_id}: {error_msg}"
            )

    async def _execute_scoring(self, score_id: str, session_id: str) -> None:
        """
        Execute scoring in background task (async).

        Performs the complete scoring workflow: retrieve session data, build prompts,
        execute multi-turn LLM conversation, extract scores, and persist results.

        Args:
            score_id: Score record identifier
            session_id: Session to score
        """
        try:
            logger.info(
                f"Starting background scoring for score {score_id}, session {session_id}"
            )

            # Update status to IN_PROGRESS just before LLM calls
            await self._update_score_status(score_id, ScoringStatus.IN_PROGRESS)
            logger.debug(f"Score {score_id} status → IN_PROGRESS")

            # Get session data (following history_controller pattern)
            session = self.history_service.get_session(session_id)
            if not session:
                raise ValueError(f"Session {session_id} not found")

            # Get conversation histories
            llm_conversation, chat_conversation = (
                self.history_service.get_session_conversation_history(
                    session_id=session_id, include_chat=True
                )
            )

            # Build FinalAnalysisResponse
            final_analysis_response = FinalAnalysisResponse(
                final_analysis=session.final_analysis,
                final_analysis_summary=session.final_analysis_summary,
                session_id=session_id,
                status=AlertSessionStatus(session.status),
                llm_conversation=llm_conversation,
                chat_conversation=chat_conversation,
                alert_data=session.alert_data,
            )

            system_prompt = LLMMessage(
                role=MessageRole.SYSTEM, content=JUDGE_SYSTEM_PROMPT
            )

            # Build score prompt with JSON serialization of FinalAnalysisResponse
            score_prompt = LLMMessage(
                role=MessageRole.USER,
                content=self._build_score_prompt(final_analysis_response),
            )

            # Initialize conversation
            conversation = LLMConversation(messages=[system_prompt, score_prompt])

            # Get LLM client
            llm_client = self._get_llm_client()
            logger.debug(f"Using LLM client: {llm_client.__class__.__name__}")

            # Turn 1: Score evaluation
            total_score = None
            score_analysis = ""
            extract_analysis = True
            logger.info(f"Executing Turn 1: Score evaluation for score {score_id}")
            for _ in range(3):  # 3 attempts to get the score
                conversation = await llm_client.generate_response(
                    conversation=conversation,
                    session_id=session_id,
                    interaction_type=LLMInteractionType.INVESTIGATION.value,
                    max_tokens=8192,
                    max_retries=3,
                    timeout_seconds=120,
                )

                logger.debug(f"!!!!! Full conversation after turn 1:\n{conversation}")

                # Extract score
                score_response = conversation.get_latest_assistant_message()
                if score_response is None:
                    raise ValueError("Could not extract the scoring response")

                score_response = score_response.content

                logger.debug(f"Received score response ({len(score_response)} chars)")

                total_score, sa = self._extract_score_from_response(score_response)
                if extract_analysis:
                    score_analysis = sa

                if total_score is not None:
                    logger.info(
                        f"Extracted score: {total_score}/100 for score {score_id}"
                    )
                    break

                # otherwise add a reminder to the LLM and try again
                logger.debug(
                    "could not extract the score from the response. Reminding the LLM to give it to us."
                )
                conversation.append_observation(self._build_score_reminder_prompt())
                extract_analysis = False

            if total_score is None:
                raise ValueError(
                    "Could not extract the total score from the LLM responses even after asking 3 times"
                )

            # Turn 2: Missing tools
            logger.info(
                f"Executing Turn 2: Missing tools analysis for score {score_id}"
            )
            conversation.append_observation(JUDGE_PROMPT_FOLLOWUP_MISSING_TOOLS)
            conversation = await llm_client.generate_response(
                conversation=conversation,
                session_id=session_id,
                interaction_type=LLMInteractionType.INVESTIGATION.value,
                max_tokens=8192,
                max_retries=3,
                timeout_seconds=120,
            )

            score_response = conversation.get_latest_assistant_message()
            missing_tools_analysis = (
                score_response.content if score_response is not None else ""
            )
            logger.debug(
                f"Received missing tools analysis ({len(missing_tools_analysis)} chars)"
            )

            # Persist results and mark completed
            await self._update_score_completion(
                score_id=score_id,
                total_score=total_score,
                score_analysis=score_analysis,
                missing_tools_analysis=missing_tools_analysis,
            )

            logger.info(
                f"Score {score_id} completed successfully (total_score={total_score})"
            )

        except Exception as e:
            # Mark as failed
            error_msg = f"{type(e).__name__}: {str(e)}"
            await self._update_score_status(
                score_id=score_id,
                status=ScoringStatus.FAILED,
                completed_at_us=now_us(),
                error_message=error_msg,
            )
            logger.error(
                f"Scoring failed for score {score_id}, session {session_id}: {error_msg}",
                exc_info=True,
            )


# Global service instance
_scoring_service: Optional[ScoringService] = None


def get_scoring_service() -> ScoringService:
    """
    Get or create global scoring service instance.

    Returns:
        ScoringService singleton instance
    """
    global _scoring_service
    if _scoring_service is None:
        _scoring_service = ScoringService()
        _scoring_service.initialize()
    return _scoring_service
