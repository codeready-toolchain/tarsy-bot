"""
Unit tests for ChatReActController.

Tests the chat-specific ReAct controller that builds initial conversations
with investigation history context.
"""

import pytest
from unittest.mock import AsyncMock

from tarsy.agents.iteration_controllers.chat_react_controller import ChatReActController
from tarsy.agents.prompts.builders import PromptBuilder
from tarsy.models.processing_context import ChatMessageContext


@pytest.mark.unit
class TestChatReActController:
    """Test ChatReActController functionality."""
    
    @pytest.fixture
    def mock_llm_client(self):
        """Mock LLM client for testing."""
        return AsyncMock()
    
    @pytest.fixture
    def prompt_builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    @pytest.fixture
    def controller(self, mock_llm_client, prompt_builder):
        """Create ChatReActController instance."""
        return ChatReActController(mock_llm_client, prompt_builder)
    
    @pytest.fixture
    def chat_message_context(self):
        """Sample chat message context."""
        return ChatMessageContext(
            conversation_history="=== INVESTIGATION HISTORY ===\nPod crashed due to OOM",
            user_question="What can we do to prevent this?",
            chat_id="chat-123"
        )
    
    def test_extract_final_analysis_from_react(self, controller):
        """Test extracting final answer from ReAct conversation."""
        react_response = """Thought: I need to analyze the issue
Action: kubectl logs
Action Input: pod-name

Observation: Logs show OOM error

Thought: Clear OOM issue
Final Answer: The pod ran out of memory. Increase memory limits."""
        
        result = controller.extract_final_analysis(react_response, None)
        
        assert "ran out of memory" in result
        assert "Increase memory limits" in result


@pytest.mark.unit
class TestPromptBuilderChatExtensions:
    """Test PromptBuilder chat-specific methods."""
    
    @pytest.fixture
    def prompt_builder(self):
        """Create PromptBuilder instance."""
        return PromptBuilder()
    
    def test_build_chat_user_message_includes_history_and_question(self, prompt_builder):
        """Test chat user message properly combines investigation history with user question."""
        investigation_context = "=== INVESTIGATION ===\nAlert: Pod crashed"
        user_question = "Can you check the logs?"
        
        result = prompt_builder.build_chat_user_message(
            investigation_context=investigation_context,
            user_question=user_question
        )
        
        # Both history and question should be present
        assert investigation_context in result
        assert user_question in result
        # Should have clear section markers with new emoji format
        assert "🎯 CURRENT TASK" in result
        # Should mention investigation context
        assert "investigation" in result.lower() or "tools" in result.lower()
    
    def test_get_chat_instructions(self, prompt_builder):
        """Test getting chat-specific instructions."""
        instructions = prompt_builder.get_chat_instructions()
        
        assert instructions is not None
        assert len(instructions) > 0
        # Should mention follow-up context
        assert "follow-up" in instructions.lower() or "investigation" in instructions.lower()
        # Should have guidelines or instructions
        assert "guidelines" in instructions.lower() or "instructions" in instructions.lower()

