"""
Unit tests for LLM interaction type detection and assignment.

Tests the _contains_final_answer() method and interaction_type logic in LLMClient.
"""

import pytest
from tarsy.integrations.llm.client import LLMClient
from tarsy.models.constants import LLMInteractionType
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole
from tarsy.models.llm_models import LLMProviderConfig


@pytest.mark.unit
class TestFinalAnswerDetection:
    """Test the _contains_final_answer() logic."""

    @pytest.fixture
    def llm_client(self):
        """Create a minimal LLM client for testing."""
        config = LLMProviderConfig(
            type="openai",
            model="test-model",
            api_key_env="TEST_API_KEY",
            temperature=0.1
        )
        client = LLMClient("test-provider", config)
        # Set available to True to bypass initialization checks
        client.available = True
        return client

    def test_detects_final_answer_at_start(self, llm_client):
        """Test detection when 'Final Answer:' is at the start of last assistant message."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
            LLMMessage(role=MessageRole.USER, content="Question"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Final Answer: The analysis is complete")
        ])
        
        assert llm_client._contains_final_answer(conversation) is True

    def test_detects_final_answer_after_newline(self, llm_client):
        """Test detection when 'Final Answer:' appears after a newline."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
            LLMMessage(role=MessageRole.USER, content="Question"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Thought: I have enough info\n\nFinal Answer: Complete")
        ])
        
        assert llm_client._contains_final_answer(conversation) is True

    def test_no_final_answer_in_assistant_message(self, llm_client):
        """Test returns False when assistant message has no 'Final Answer:'."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
            LLMMessage(role=MessageRole.USER, content="Question"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Thought: Still investigating...")
        ])
        
        assert llm_client._contains_final_answer(conversation) is False

    def test_no_final_answer_with_user_observation_after(self, llm_client):
        """Test returns False when assistant message lacks Final Answer (with user message after)."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
            LLMMessage(role=MessageRole.USER, content="Question"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Thought: Need more info"),
            LLMMessage(role=MessageRole.USER, content="Observation: Data collected")
        ])
        
        # Returns False because the latest assistant message doesn't have Final Answer
        assert llm_client._contains_final_answer(conversation) is False

    def test_empty_conversation(self, llm_client):
        """Test handles empty conversation gracefully."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt")
        ])
        
        assert llm_client._contains_final_answer(conversation) is False

    def test_final_answer_in_earlier_assistant_message_not_detected(self, llm_client):
        """Test only checks the LATEST assistant message, ignores earlier ones."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
            LLMMessage(role=MessageRole.USER, content="Question"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Final Answer: First attempt"),
            LLMMessage(role=MessageRole.USER, content="Try again"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Thought: Continuing investigation")
        ])
        
        # Should return False because the LATEST assistant message doesn't have Final Answer
        assert llm_client._contains_final_answer(conversation) is False

    def test_case_sensitive_final_answer(self, llm_client):
        """Test that detection is case-sensitive (only 'Final Answer:' with capital F and A)."""
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
            LLMMessage(role=MessageRole.USER, content="Question"),
            LLMMessage(role=MessageRole.ASSISTANT, content="final answer: lowercase")
        ])
        
        # Current implementation is case-sensitive, expects "Final Answer:"
        assert llm_client._contains_final_answer(conversation) is False

    def test_final_answer_detected_with_metadata_observation_after(self, llm_client):
        """Test that Final Answer is detected when metadata observation follows assistant message.
        
        When response metadata is injected as a user observation after the assistant message,
        _contains_final_answer should still find the Final Answer in the assistant message.
        """
        conversation = LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="System prompt"),
            LLMMessage(role=MessageRole.USER, content="Question"),
            LLMMessage(role=MessageRole.ASSISTANT, content="Thought: Analysis complete.\n\nFinal Answer: Issue resolved."),
            # Metadata observation injected after assistant response
            LLMMessage(role=MessageRole.USER, content="[Response Metadata]\n```json\n{\"grounding_metadata\": {}}\n```")
        ])
        
        # Should return True because the latest ASSISTANT message has Final Answer
        assert llm_client._contains_final_answer(conversation) is True
