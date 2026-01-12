"""
Integration tests for executive summary generation.

Tests the end-to-end flow of generating executive summaries after alert processing
completion, including LLM interaction, database persistence, and API response.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from tarsy.integrations.notifications.summarizer import ExecutiveSummaryAgent
from tarsy.models.constants import AlertSessionStatus, LLMInteractionType
from tarsy.models.db_models import AlertSession
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.utils.timestamp import now_us


@pytest.mark.integration
class TestExecutiveSummaryGeneration:
    """Integration tests for executive summary generation flow."""
    
    @pytest.fixture
    def mock_llm_manager(self):
        """Create mock LLM manager for summary generation."""
        manager = Mock()
        manager.generate_response = AsyncMock()
        return manager
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        settings = Mock()
        settings.llm_iteration_timeout = 180
        return settings
    
    @pytest.fixture
    def summary_agent(self, mock_llm_manager, mock_settings):
        """Create ExecutiveSummaryAgent with mocked LLM."""
        return ExecutiveSummaryAgent(llm_manager=mock_llm_manager, settings=mock_settings)
    
    @pytest.mark.asyncio
    async def test_summary_generation_with_real_prompt_builder(self, summary_agent, mock_llm_manager):
        """Test that summary generation uses real PromptBuilder for prompts."""
        final_analysis = """# Incident Analysis

## Root Cause
The pod crashed due to missing environment variable DATABASE_URL.

## Impact
Service was unavailable for 5 minutes.

## Resolution
Added the missing environment variable and restarted the pod."""
        
        response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Pod crashed due to missing DATABASE_URL env var, service down 5 minutes, resolved by adding variable and restarting.")
        ])
        mock_llm_manager.generate_response.return_value = response_conversation
        
        summary = await summary_agent.generate_executive_summary(
            content=final_analysis,
            session_id="integration-test-session"
        )
        
        assert summary is not None
        assert len(summary) > 0
        
        call_args = mock_llm_manager.generate_response.call_args
        conversation = call_args.kwargs["conversation"]
        
        assert len(conversation.messages) == 2
        assert conversation.messages[0].role == MessageRole.SYSTEM
        assert conversation.messages[1].role == MessageRole.USER
        assert final_analysis in conversation.messages[1].content
        assert "CRITICAL RULES" in conversation.messages[1].content
    
    @pytest.mark.asyncio
    async def test_summary_persisted_to_database(self, history_service_with_test_db, summary_agent, mock_llm_manager):
        """Test that generated summary is persisted to database."""
        history_service = history_service_with_test_db
        
        session_id = f"test-summary-persist-{now_us()}"
        
        session = AlertSession(
            session_id=session_id,
            alert_data={"test": "data"},
            agent_type="test-agent",
            alert_type="TestAlert",
            status=AlertSessionStatus.IN_PROGRESS.value,
            started_at_us=now_us(),
            chain_id="test-chain"
        )
        
        with history_service.get_repository() as repo:
            if repo:
                repo.create_alert_session(session)
        
        response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Test summary generated")
        ])
        mock_llm_manager.generate_response.return_value = response_conversation
        
        summary = await summary_agent.generate_executive_summary(
            content="Test analysis content",
            session_id=session_id
        )
        
        assert summary == "Test summary generated"
        
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.COMPLETED.value,
            final_analysis="Full analysis",
            final_analysis_summary=summary
        )
        
        assert success
        
        with history_service.get_repository() as repo:
            if repo:
                retrieved_session = repo.get_alert_session(session_id)
                assert retrieved_session is not None
                assert retrieved_session.final_analysis_summary == "Test summary generated"
    
    @pytest.mark.asyncio
    async def test_summary_generation_failure_does_not_break_flow(self, summary_agent, mock_llm_manager):
        """Test that summary generation failure doesn't affect main processing."""
        mock_llm_manager.generate_response.side_effect = Exception("LLM timeout")
        
        summary = await summary_agent.generate_executive_summary(
            content="Analysis content",
            session_id="test-session"
        )
        
        assert summary is None
    
    @pytest.mark.asyncio
    async def test_summary_with_different_analysis_lengths(self, summary_agent, mock_llm_manager):
        """Test summary generation with various analysis content lengths."""
        test_cases = [
            ("Short analysis.", "Brief summary"),
            ("Medium length analysis with multiple sentences. " * 10, "Medium summary"),
            ("Very long analysis.\n" * 100, "Concise long summary"),
        ]
        
        for analysis_content, expected_summary in test_cases:
            response_conversation = LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.ASSISTANT, content=expected_summary)
            ])
            mock_llm_manager.generate_response.return_value = response_conversation
            
            summary = await summary_agent.generate_executive_summary(
                content=analysis_content,
                session_id=f"test-{len(analysis_content)}"
            )
            
            assert summary == expected_summary
    
    @pytest.mark.asyncio
    async def test_summary_uses_correct_llm_parameters(self, summary_agent, mock_llm_manager):
        """Test that summary generation passes correct parameters to LLM."""
        response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Summary")
        ])
        mock_llm_manager.generate_response.return_value = response_conversation
        
        await summary_agent.generate_executive_summary(
            content="Analysis",
            session_id="test-session",
            stage_execution_id="stage-456",
            max_tokens=200
        )
        
        call_args = mock_llm_manager.generate_response.call_args
        
        assert call_args.kwargs["session_id"] == "test-session"
        assert call_args.kwargs["stage_execution_id"] == "stage-456"
        assert call_args.kwargs["max_tokens"] == 200
        assert call_args.kwargs["interaction_type"] == LLMInteractionType.FINAL_ANALYSIS_SUMMARY.value
    
    @pytest.mark.asyncio
    async def test_summary_with_multiline_analysis(self, summary_agent, mock_llm_manager):
        """Test summary generation with multiline markdown analysis."""
        analysis = """# Kubernetes Pod Failure

## Symptoms
- Pod stuck in CrashLoopBackOff
- Container exits with code 1
- Logs show "Config file not found"

## Root Cause
Missing ConfigMap reference in pod spec.

## Resolution
1. Created missing ConfigMap
2. Restarted deployment
3. Verified pod running successfully"""
        
        response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Pod failed due to missing ConfigMap, resolved by creating ConfigMap and restarting deployment.")
        ])
        mock_llm_manager.generate_response.return_value = response_conversation
        
        summary = await summary_agent.generate_executive_summary(
            content=analysis,
            session_id="test-multiline"
        )
        
        assert summary is not None
        assert "ConfigMap" in summary
    
    @pytest.mark.asyncio
    async def test_summary_trims_whitespace(self, summary_agent, mock_llm_manager):
        """Test that summary generation trims surrounding whitespace from the response."""
        expected_summary = "This is the actual summary"
        test_responses = [
            f"   {expected_summary}   ",
            f"\n\n{expected_summary}\n\n",
            f"\t{expected_summary}\t"
        ]
        
        for response_content in test_responses:
            response_conversation = LLMConversation(messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.ASSISTANT, content=response_content)
            ])
            mock_llm_manager.generate_response.return_value = response_conversation
            
            summary = await summary_agent.generate_executive_summary(
                content="Analysis",
                session_id="test-whitespace"
            )
            
            assert summary == expected_summary


@pytest.mark.integration
class TestSummaryInAlertProcessingFlow:
    """Integration tests for summary generation within complete alert processing."""
    
    @pytest.mark.asyncio
    async def test_summary_generated_after_successful_processing(self, history_service_with_test_db):
        """Test that summary is generated after successful alert processing."""
        history_service = history_service_with_test_db
        
        session_id = f"test-processing-{now_us()}"
        
        session = AlertSession(
            session_id=session_id,
            alert_data={"test": "alert"},
            agent_type="test-agent",
            alert_type="TestAlert",
            status=AlertSessionStatus.IN_PROGRESS.value,
            started_at_us=now_us(),
            chain_id="test-chain"
        )
        
        with history_service.get_repository() as repo:
            if repo:
                repo.create_alert_session(session)
        
        final_analysis = "# Alert Analysis\n\nIssue resolved."
        final_summary = "Issue resolved successfully."
        
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.COMPLETED.value,
            final_analysis=final_analysis,
            final_analysis_summary=final_summary
        )
        
        assert success
        
        with history_service.get_repository() as repo:
            if repo:
                retrieved = repo.get_alert_session(session_id)
                assert retrieved.status == AlertSessionStatus.COMPLETED.value
                assert retrieved.final_analysis == final_analysis
                assert retrieved.final_analysis_summary == final_summary
    
    @pytest.mark.asyncio
    async def test_summary_not_generated_on_failure(self, history_service_with_test_db):
        """Test that summary is not generated when processing fails."""
        history_service = history_service_with_test_db
        
        session_id = f"test-failure-{now_us()}"
        
        session = AlertSession(
            session_id=session_id,
            alert_data={"test": "alert"},
            agent_type="test-agent",
            alert_type="TestAlert",
            status=AlertSessionStatus.IN_PROGRESS.value,
            started_at_us=now_us(),
            chain_id="test-chain"
        )
        
        with history_service.get_repository() as repo:
            if repo:
                repo.create_alert_session(session)
        
        success = history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.FAILED.value,
            error_message="Processing failed"
        )
        
        assert success
        
        with history_service.get_repository() as repo:
            if repo:
                retrieved = repo.get_alert_session(session_id)
                assert retrieved.status == AlertSessionStatus.FAILED.value
                assert retrieved.final_analysis is None
                assert retrieved.final_analysis_summary is None
    
    @pytest.mark.asyncio
    async def test_summary_optional_field_in_database(self, history_service_with_test_db):
        """Test that final_analysis_summary field is optional in database."""
        history_service = history_service_with_test_db
        
        session_id = f"test-optional-{now_us()}"
        
        session = AlertSession(
            session_id=session_id,
            alert_data={"test": "alert"},
            agent_type="test-agent",
            alert_type="TestAlert",
            status=AlertSessionStatus.COMPLETED.value,
            started_at_us=now_us(),
            chain_id="test-chain",
            final_analysis="Analysis without summary"
        )
        
        with history_service.get_repository() as repo:
            if repo:
                created = repo.create_alert_session(session)
                assert created is not None
                assert created.final_analysis_summary is None

