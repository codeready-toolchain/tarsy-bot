"""
Unit tests for MCPResultSummarizer with mcp_event_id support.

Tests that the summarizer correctly accepts and passes mcp_event_id
to the LLM client for linking summarizations to tool calls.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from tarsy.integrations.mcp.summarizer import MCPResultSummarizer
from tarsy.models.constants import LLMInteractionType
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole


@pytest.mark.unit
class TestMCPResultSummarizerMCPEventID:
    """Test MCPResultSummarizer with mcp_event_id parameter."""
    
    def setup_method(self):
        """Set up test environment before each test."""
        self.mock_llm_client = MagicMock()
        self.mock_prompt_builder = MagicMock()
        
        self.mock_prompt_builder.build_mcp_summarization_system_prompt.return_value = (
            "System prompt for summarization"
        )
        self.mock_prompt_builder.build_mcp_summarization_user_prompt.return_value = (
            "User prompt with context"
        )
        self.mock_llm_client.get_max_tool_result_tokens.return_value = 150000
        
        self.summarizer = MCPResultSummarizer(
            self.mock_llm_client, self.mock_prompt_builder
        )
    
    @pytest.mark.asyncio
    async def test_summarize_result_passes_mcp_event_id_to_llm_client(self):
        """Test that mcp_event_id is passed to LLM client generate_response."""
        test_result = {"result": "Large tool output data"}
        investigation_conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="Query"),
            ]
        )
        
        mock_response = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="User"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Summary result"),
            ]
        )
        self.mock_llm_client.generate_response = AsyncMock(return_value=mock_response)
        
        await self.summarizer.summarize_result(
            server_name="kubectl",
            tool_name="get_pods",
            result=test_result,
            investigation_conversation=investigation_conversation,
            session_id="test-session-123",
            stage_execution_id="stage-456",
            max_summary_tokens=1000,
            mcp_event_id="mcp-event-789"
        )
        
        # Verify generate_response was called with mcp_event_id
        self.mock_llm_client.generate_response.assert_called_once()
        call_kwargs = self.mock_llm_client.generate_response.call_args.kwargs
        
        assert call_kwargs["mcp_event_id"] == "mcp-event-789"
        assert call_kwargs["interaction_type"] == LLMInteractionType.SUMMARIZATION.value
        assert call_kwargs["max_tokens"] == 1000
    
    @pytest.mark.asyncio
    async def test_summarize_result_without_mcp_event_id(self):
        """Test that summarization works without mcp_event_id (defaults to None)."""
        test_result = {"result": "Tool data"}
        investigation_conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
            ]
        )
        
        mock_response = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="User"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Summary"),
            ]
        )
        self.mock_llm_client.generate_response = AsyncMock(return_value=mock_response)
        
        await self.summarizer.summarize_result(
            server_name="server",
            tool_name="tool",
            result=test_result,
            investigation_conversation=investigation_conversation,
            session_id="test-session"
            # No mcp_event_id provided
        )
        
        # Should still call generate_response
        self.mock_llm_client.generate_response.assert_called_once()
        call_kwargs = self.mock_llm_client.generate_response.call_args.kwargs
        
        # mcp_event_id should be None (or not in kwargs if not explicitly passed)
        assert call_kwargs.get("mcp_event_id") is None
    
    @pytest.mark.asyncio
    async def test_summarize_result_mcp_event_id_with_all_parameters(self):
        """Test complete summarization call with all parameters including mcp_event_id."""
        test_result = {
            "result": {"pods": [{"name": "pod-1"}]},
            "metadata": "extra data"
        }
        investigation_conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="Investigation context"),
                LLMMessage(role=MessageRole.USER, content="Previous query"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Previous response"),
            ]
        )
        
        mock_response = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="User"),
                LLMMessage(role=MessageRole.ASSISTANT, content="Complete summary"),
            ]
        )
        self.mock_llm_client.generate_response = AsyncMock(return_value=mock_response)
        
        result = await self.summarizer.summarize_result(
            server_name="kubernetes-server",
            tool_name="list_pods",
            result=test_result,
            investigation_conversation=investigation_conversation,
            session_id="session-abc",
            stage_execution_id="stage-def",
            max_summary_tokens=500,
            mcp_event_id="mcp-event-complete-ghi"
        )
        
        # Verify the result is structured correctly
        assert result["result"] == "Complete summary"
        assert result["metadata"] == "extra data"
        
        # Verify all parameters were passed correctly
        call_args = self.mock_llm_client.generate_response.call_args
        assert call_args[0][1] == "session-abc"  # session_id
        assert call_args[0][2] == "stage-def"  # stage_execution_id
        
        call_kwargs = call_args.kwargs
        assert call_kwargs["max_tokens"] == 500
        assert call_kwargs["interaction_type"] == LLMInteractionType.SUMMARIZATION.value
        assert call_kwargs["mcp_event_id"] == "mcp-event-complete-ghi"
    
    
    @pytest.mark.asyncio
    async def test_summarize_result_llm_failure_with_mcp_event_id(self):
        """Test that LLM failures are properly raised even with mcp_event_id."""
        test_result = {"result": "data"}
        investigation_conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
            ]
        )
        
        self.mock_llm_client.generate_response = AsyncMock(
            side_effect=Exception("LLM call failed")
        )
        
        with pytest.raises(Exception, match="LLM call failed"):
            await self.summarizer.summarize_result(
                "server", "tool", test_result, investigation_conversation,
                "test-session", mcp_event_id="mcp-event-error"
            )

