"""
Tests for MCP result summarizer.

This module tests the MCPResultSummarizer class used for reducing large
MCP tool output sizes using LLM-powered summarization.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tarsy.integrations.mcp.summarizer import MCPResultSummarizer
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole


@pytest.mark.unit
class TestMCPResultSummarizer:
    """Test cases for MCPResultSummarizer class."""
    
    def setup_method(self):
        """Set up test environment before each test."""
        self.mock_llm_client = MagicMock()
        self.mock_prompt_builder = MagicMock()
        
        # Set up prompt builder mock responses
        self.mock_prompt_builder.build_mcp_summarization_system_prompt.return_value = "System prompt for summarization"
        self.mock_prompt_builder.build_mcp_summarization_user_prompt.return_value = "User prompt with context"
        
        self.summarizer = MCPResultSummarizer(self.mock_llm_client, self.mock_prompt_builder)
    
    @pytest.mark.asyncio
    async def test_summarize_result_success(self):
        """Test successful result summarization."""
        # Set up test data
        server_name = "kubectl"
        tool_name = "get_pods"
        test_result = {
            "result": {"pods": [{"name": "pod1"}, {"name": "pod2"}]},
            "metadata": "some metadata"
        }
        
        # Create mock investigation conversation
        investigation_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are investigating pods"),
            LLMMessage(role=MessageRole.USER, content="Check pod status"),
        ])
        
        # Mock LLM client response
        mock_response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt for summarization"),
            LLMMessage(role=MessageRole.USER, content="User prompt with context"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Summarized: 2 pods found - pod1 and pod2")
        ])
        self.mock_llm_client.generate_response = AsyncMock(return_value=mock_response_conversation)
        
        # Execute summarization
        result = await self.summarizer.summarize_result(
            server_name=server_name,
            tool_name=tool_name,
            result=test_result,
            investigation_conversation=investigation_conversation,
            session_id="test-session",
            stage_execution_id="test-stage",
            max_summary_tokens=1000
        )
        
        # Verify result structure
        assert isinstance(result, dict)
        assert result["result"] == "Summarized: 2 pods found - pod1 and pod2"
        assert result["metadata"] == "some metadata"  # Original metadata preserved
        
        # Verify prompt builder was called correctly
        self.mock_prompt_builder.build_mcp_summarization_system_prompt.assert_called_once_with(
            server_name, tool_name, 1000
        )
        self.mock_prompt_builder.build_mcp_summarization_user_prompt.assert_called_once()
        
        # Verify LLM client was called with max_tokens config
        self.mock_llm_client.generate_response.assert_called_once()
        call_args = self.mock_llm_client.generate_response.call_args
        assert call_args[0][1] == "test-session"  # session_id
        assert call_args[0][2] == "test-stage"   # stage_execution_id
        assert call_args[0][3] == {"max_tokens": 1000}  # llm_config with max_tokens
    
    @pytest.mark.asyncio
    async def test_summarize_result_with_string_result(self):
        """Test summarization when result content is a string."""
        test_result = {
            "result": "Simple string result",
            "status": "success"
        }
        
        investigation_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System message")
        ])
        
        mock_response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt for summarization"),
            LLMMessage(role=MessageRole.USER, content="User prompt with context"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Summary of string result")
        ])
        self.mock_llm_client.generate_response = AsyncMock(return_value=mock_response_conversation)
        
        result = await self.summarizer.summarize_result(
            "server", "tool", test_result, investigation_conversation, "session"
        )
        
        assert result["result"] == "Summary of string result"
        
        # Verify user prompt was built with string content (not JSON)
        user_prompt_call = self.mock_prompt_builder.build_mcp_summarization_user_prompt.call_args
        assert "Simple string result" in user_prompt_call[0][3]  # result_text parameter
    
    @pytest.mark.asyncio
    async def test_summarize_result_without_result_key(self):
        """Test summarization when result doesn't have 'result' key."""
        test_result = {"status": "running", "message": "Processing"}
        
        investigation_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System message")
        ])
        
        mock_response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt for summarization"),
            LLMMessage(role=MessageRole.USER, content="User prompt with context"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Summary of full result")
        ])
        self.mock_llm_client.generate_response = AsyncMock(return_value=mock_response_conversation)
        
        result = await self.summarizer.summarize_result(
            "server", "tool", test_result, investigation_conversation, "session"
        )
        
        assert result["result"] == "Summary of full result"
        
        # Original structure should be preserved except for result content
        assert result["status"] == "running"
        assert result["message"] == "Processing"
    
    @pytest.mark.asyncio 
    async def test_summarize_result_llm_failure(self):
        """Test handling of LLM client failures."""
        test_result = {"result": "test data"}
        investigation_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System message")
        ])
        
        # Mock LLM client to raise exception
        self.mock_llm_client.generate_response = AsyncMock(side_effect=Exception("LLM unavailable"))
        
        with pytest.raises(Exception, match="LLM unavailable"):
            await self.summarizer.summarize_result(
                "server", "tool", test_result, investigation_conversation, "session"
            )
    
    @pytest.mark.asyncio
    async def test_summarize_result_no_assistant_response(self):
        """Test handling when LLM doesn't return assistant message."""
        test_result = {"result": "test data"}
        investigation_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System message")
        ])
        
        # Mock response with no assistant message
        mock_response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt for summarization"),
            LLMMessage(role=MessageRole.USER, content="Only user message")
        ])
        self.mock_llm_client.generate_response = AsyncMock(return_value=mock_response_conversation)
        
        with pytest.raises(Exception, match="No response from LLM for summarization"):
            await self.summarizer.summarize_result(
                "server", "tool", test_result, investigation_conversation, "session"
            )
    
    def test_serialize_conversation_context(self):
        """Test conversation context serialization."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System instructions with domain knowledge"),
            LLMMessage(role=MessageRole.USER, content="User query"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Assistant response"),
        ])
        
        context = self.summarizer._serialize_conversation_context(conversation)
        
        assert "SYSTEM: System instructions with domain knowledge" in context
        assert "USER: User query" in context
        assert "ASSISTANT: Assistant response" in context
    
    def test_serialize_conversation_context_with_long_messages(self):
        """Test conversation context serialization with message truncation."""
        long_content = "x" * 15000  # Exceeds 10000 char limit
        
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="Short system message"),
            LLMMessage(role=MessageRole.USER, content=long_content),
        ])
        
        context = self.summarizer._serialize_conversation_context(conversation)
        
        assert "SYSTEM: Short system message" in context
        assert "USER: " + "x" * 10000 + "... [truncated]" in context
        assert len([line for line in context.split('\n') if line.startswith('USER:')][0]) < 15000
    
    @patch('tarsy.agents.prompts.templates.REACT_FORMATTING_INSTRUCTIONS', 'REACT_INSTRUCTIONS_PATTERN')
    def test_extract_domain_knowledge_from_system_message(self):
        """Test domain knowledge extraction from system messages."""
        system_content = "Domain knowledge about Kubernetes\n\nREACT_INSTRUCTIONS_PATTERN\nFormatting instructions here"
        
        result = self.summarizer._extract_domain_knowledge_from_system_message(system_content)
        
        assert result == "Domain knowledge about Kubernetes"
    
    def test_extract_domain_knowledge_without_pattern(self):
        """Test domain knowledge extraction when pattern is not found."""
        system_content = "Some system instructions without the pattern"
        
        result = self.summarizer._extract_domain_knowledge_from_system_message(system_content)
        
        # Should return first 1000 chars with suffix
        expected = system_content[:1000] + "... [domain knowledge extracted]"
        assert result == expected
    
    def test_extract_domain_knowledge_short_content(self):
        """Test domain knowledge extraction with content shorter than 1000 chars."""
        system_content = "Short content"
        
        result = self.summarizer._extract_domain_knowledge_from_system_message(system_content)
        
        assert result == "Short content... [domain knowledge extracted]"
    
    @pytest.mark.asyncio
    async def test_summarize_result_custom_max_tokens(self):
        """Test that custom max_tokens values are properly passed to LLM client."""
        test_result = {"result": "test data"}
        investigation_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System message")
        ])
        
        mock_response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt for summarization"),
            LLMMessage(role=MessageRole.USER, content="User prompt with context"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Custom length summary")
        ])
        self.mock_llm_client.generate_response = AsyncMock(return_value=mock_response_conversation)
        
        # Test with custom max_tokens value
        custom_max_tokens = 500
        await self.summarizer.summarize_result(
            "server", "tool", test_result, investigation_conversation, "session",
            max_summary_tokens=custom_max_tokens
        )
        
        # Verify LLM client received correct max_tokens config
        call_args = self.mock_llm_client.generate_response.call_args
        assert call_args[0][3] == {"max_tokens": custom_max_tokens}
    
    @pytest.mark.asyncio
    async def test_summarize_result_max_tokens_enforcement(self):
        """Test that max_tokens is enforced at LLM provider level."""
        test_result = {"result": "Large data that should be summarized"}
        investigation_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System message")
        ])
        
        # Mock LLM client to return response constrained by max_tokens
        constrained_response = "Truncated summary due to max_tokens"  # Simulates LLM truncation
        mock_response_conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt for summarization"),
            LLMMessage(role=MessageRole.USER, content="User prompt with context"),
            LLMMessage(role=MessageRole.ASSISTANT, content=constrained_response)
        ])
        self.mock_llm_client.generate_response = AsyncMock(return_value=mock_response_conversation)
        
        result = await self.summarizer.summarize_result(
            "kubectl", "get_pods", test_result, investigation_conversation, "session",
            max_summary_tokens=100  # Very small limit to test enforcement
        )
        
        # Verify result contains the constrained response
        assert result["result"] == constrained_response
        
        # Verify max_tokens was passed correctly
        call_args = self.mock_llm_client.generate_response.call_args
        assert call_args[0][3] == {"max_tokens": 100}
