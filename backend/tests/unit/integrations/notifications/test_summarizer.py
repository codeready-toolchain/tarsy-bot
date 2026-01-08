"""Tests for ExecutiveSummaryAgent."""

from unittest.mock import AsyncMock, Mock

import pytest

from tarsy.integrations.notifications.summarizer import ExecutiveSummaryAgent
from tarsy.models.constants import LLMInteractionType
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole


@pytest.fixture
def mock_llm_client():
    """Create mock LLM client."""
    client = Mock()
    client.generate_response = AsyncMock()
    return client


@pytest.fixture
def mock_settings():
    """Create mock settings."""
    settings = Mock()
    settings.llm_iteration_timeout = 180
    return settings


@pytest.fixture
def summary_agent(mock_llm_client, mock_settings):
    """Create SummaryAgent with mocked dependencies."""
    return ExecutiveSummaryAgent(llm_manager=mock_llm_client, settings=mock_settings)


@pytest.mark.unit
class TestExecutiveSummaryAgent:
    """Test suite for ExecutiveSummaryAgent."""
    
    @pytest.mark.asyncio
    async def test_generate_executive_summary_success(self, summary_agent, mock_llm_client):
        """Test successful summary generation."""
        response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
            LLMMessage(role=MessageRole.ASSISTANT, content="Brief summary of the analysis")
        ])
        mock_llm_client.generate_response.return_value = response_conversation
        
        result = await summary_agent.generate_executive_summary(
            content="Long analysis text here...",
            session_id="test-session"
        )
        
        assert result == "Brief summary of the analysis" 
        mock_llm_client.generate_response.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_generate_executive_summary_strips_whitespace(self, summary_agent, mock_llm_client):
        """Test that summary generation strips leading/trailing whitespace."""
        response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
            LLMMessage(role=MessageRole.ASSISTANT, content="  \n\nSummary with whitespace\n\n  ")
        ])
        mock_llm_client.generate_response.return_value = response_conversation
        
        result = await summary_agent.generate_executive_summary(
            content="Analysis content",
            session_id="test-session"
        )
        
        assert result == "Summary with whitespace"
    
    @pytest.mark.asyncio
    async def test_generate_executive_summary_with_stage_execution_id(self, summary_agent, mock_llm_client):
        """Test summary generation with stage_execution_id parameter."""
        response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Summary")
        ])
        mock_llm_client.generate_response.return_value = response_conversation
        
        result = await summary_agent.generate_executive_summary(
            content="Analysis",
            session_id="test-session",
            stage_execution_id="stage-123"
        )
        
        assert result == "Summary"
        
        call_args = mock_llm_client.generate_response.call_args
        assert call_args.kwargs["stage_execution_id"] == "stage-123"
    
    @pytest.mark.asyncio
    async def test_generate_executive_summary_custom_max_tokens(self, summary_agent, mock_llm_client):
        """Test summary generation with custom max_tokens."""
        response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Summary")
        ])
        mock_llm_client.generate_response.return_value = response_conversation
        
        await summary_agent.generate_executive_summary(
            content="Analysis",
            session_id="test-session",
            max_tokens=200
        )
        
        call_args = mock_llm_client.generate_response.call_args
        assert call_args.kwargs["max_tokens"] == 200
    
    @pytest.mark.asyncio
    async def test_generate_executive_summary_uses_correct_interaction_type(self, summary_agent, mock_llm_client):
        """Test that summary generation uses FINAL_ANALYSIS_SUMMARY interaction type."""
        response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Summary")
        ])
        mock_llm_client.generate_response.return_value = response_conversation
        
        await summary_agent.generate_executive_summary(
            content="Analysis",
            session_id="test-session"
        )
        
        call_args = mock_llm_client.generate_response.call_args
        assert call_args.kwargs["interaction_type"] == LLMInteractionType.FINAL_ANALYSIS_SUMMARY.value
    
    @pytest.mark.asyncio
    async def test_generate_executive_summary_builds_conversation_correctly(self, summary_agent, mock_llm_client):
        """Test that summary generation builds conversation with system and user messages."""
        response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Summary")
        ])
        mock_llm_client.generate_response.return_value = response_conversation
        
        analysis_content = "Detailed analysis of the incident"
        await summary_agent.generate_executive_summary(
            content=analysis_content,
            session_id="test-session"
        )
        
        call_args = mock_llm_client.generate_response.call_args
        conversation = call_args.kwargs["conversation"]
        
        assert len(conversation.messages) == 2
        assert conversation.messages[0].role == MessageRole.SYSTEM
        assert "Site Reliability Engineer" in conversation.messages[0].content
        assert conversation.messages[1].role == MessageRole.USER
        assert analysis_content in conversation.messages[1].content
    
    @pytest.mark.asyncio
    async def test_generate_executive_summary_empty_analysis_raises_error(self, summary_agent):
        """Test with empty analysis text raises ValueError."""
        with pytest.raises(ValueError, match="Cannot generate executive summary: content is required"):
            await summary_agent.generate_executive_summary(
                content="",
                session_id="test-session"
            )
        
        with pytest.raises(ValueError, match="Cannot generate executive summary: content is required"):
            await summary_agent.generate_executive_summary(
                content=None,
                session_id="test-session"
            )
    
    @pytest.mark.asyncio
    async def test_generate_executive_summary_no_assistant_response(self, summary_agent, mock_llm_client):
        """Test handling when no assistant response is received."""
        response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt")
        ])
        mock_llm_client.generate_response.return_value = response_conversation
        
        result = await summary_agent.generate_executive_summary(
            content="Analysis",
            session_id="test-session"
        )
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_generate_executive_summary_llm_exception(self, summary_agent, mock_llm_client):
        """Test handling when LLM client raises exception."""
        mock_llm_client.generate_response.side_effect = Exception("LLM service unavailable")
        
        result = await summary_agent.generate_executive_summary(
            content="Analysis",
            session_id="test-session"
        )
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_generate_executive_summary_long_content(self, summary_agent, mock_llm_client):
        """Test summary generation with very long analysis content."""
        long_analysis = "Analysis section\n" * 1000
        
        response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Concise summary")
        ])
        mock_llm_client.generate_response.return_value = response_conversation
        
        result = await summary_agent.generate_executive_summary(
            content=long_analysis,
            session_id="test-session"
        )
        
        assert result == "Concise summary"
        
        call_args = mock_llm_client.generate_response.call_args
        conversation = call_args.kwargs["conversation"]
        assert long_analysis in conversation.messages[1].content
    
    @pytest.mark.asyncio
    async def test_generate_executive_summary_multiline_summary(self, summary_agent, mock_llm_client):
        """Test that multiline summaries are handled correctly."""
        multiline_summary = "Line 1: Critical issue detected\nLine 2: Immediate action required\nLine 3: Systems affected"
        
        response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System"),
            LLMMessage(role=MessageRole.ASSISTANT, content=multiline_summary)
        ])
        mock_llm_client.generate_response.return_value = response_conversation
        
        result = await summary_agent.generate_executive_summary(
            content="Analysis",
            session_id="test-session"
        )
        
        assert result == multiline_summary
        assert "Line 1:" in result
        assert "Line 3:" in result