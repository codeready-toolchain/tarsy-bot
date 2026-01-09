"""
Unit tests for Gemini native thinking streaming event type selection.

Tests that INTERMEDIATE_RESPONSE is used for intermediate iterations
and FINAL_ANSWER is used only for the final iteration.
"""

from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tarsy.integrations.llm.gemini_client import GeminiNativeThinkingClient
from tarsy.models.constants import StreamingEventType
from tarsy.models.llm_models import LLMProviderConfig, LLMProviderType
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole


async def mock_stream_response(response: MagicMock) -> AsyncIterator[MagicMock]:
    """Convert a mock response to an async iterator for streaming simulation."""
    yield response


@pytest.mark.unit
class TestGeminiStreamingEventTypes:
    """Test that streaming uses correct event types based on whether iteration is final."""
    
    @pytest.fixture
    def client(self) -> GeminiNativeThinkingClient:
        """Create a Gemini client with streaming enabled."""
        with patch("tarsy.integrations.llm.gemini_client.get_settings") as mock_settings:
            settings = MagicMock()
            settings.enable_llm_streaming = True
            mock_settings.return_value = settings
            
            config = LLMProviderConfig(
                type=LLMProviderType.GOOGLE,
                model="gemini-2.5-flash",
                api_key_env="GOOGLE_API_KEY",
                api_key="test-api-key",
                temperature=0.7
            )
            return GeminiNativeThinkingClient(config, "test-provider")
    
    @pytest.fixture
    def sample_conversation(self) -> LLMConversation:
        """Create a sample conversation for testing."""
        return LLMConversation(messages=[
            LLMMessage(role=MessageRole.SYSTEM, content="You are an assistant."),
            LLMMessage(role=MessageRole.USER, content="Analyze this alert."),
        ])
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "has_tool_calls,expected_event_type",
        [
            (True, StreamingEventType.INTERMEDIATE_RESPONSE),   # Intermediate iteration
            (False, StreamingEventType.FINAL_ANSWER),          # Final iteration
        ],
    )
    @patch("tarsy.integrations.llm.gemini_client.genai")
    @patch("tarsy.integrations.llm.gemini_client.llm_interaction_context")
    async def test_streaming_uses_correct_event_type_based_on_finality(
        self,
        mock_context: MagicMock,
        mock_genai: MagicMock,
        client: GeminiNativeThinkingClient,
        sample_conversation: LLMConversation,
        has_tool_calls: bool,
        expected_event_type: StreamingEventType
    ) -> None:
        """
        Test that streaming uses INTERMEDIATE_RESPONSE for intermediate iterations
        and FINAL_ANSWER only for final iterations (no tool calls).
        """
        # Create streaming response with thinking and response text
        thinking_chunk = MagicMock()
        thinking_part = MagicMock()
        thinking_part.thought = True
        thinking_part.text = "Analyzing..."
        thinking_part.thought_signature = None
        thinking_chunk.candidates = [MagicMock(content=MagicMock(parts=[thinking_part]))]
        thinking_chunk.function_calls = None
        thinking_chunk.usage_metadata = None
        
        response_chunk = MagicMock()
        response_part = MagicMock()
        response_part.thought = False
        response_part.text = "I will check the pods status."
        response_part.thought_signature = b"sig123"
        response_chunk.candidates = [MagicMock(content=MagicMock(parts=[response_part]))]
        
        # Add function calls for intermediate iteration, none for final iteration
        if has_tool_calls:
            function_call = MagicMock()
            function_call.name = "kubernetes__get_pods"
            function_call.args = {"namespace": "default"}
            response_chunk.function_calls = [function_call]
        else:
            response_chunk.function_calls = None
        
        response_chunk.usage_metadata = MagicMock(
            prompt_token_count=100,
            candidates_token_count=50,
            total_token_count=150
        )
        
        async def multi_chunk_stream():
            yield thinking_chunk
            yield response_chunk
        
        mock_native_client = MagicMock()
        mock_native_client.aio.models.generate_content_stream = AsyncMock(
            return_value=multi_chunk_stream()
        )
        mock_genai.Client.return_value = mock_native_client
        
        mock_ctx = MagicMock()
        mock_ctx.interaction = MagicMock(interaction_id="test-interaction-123")
        mock_ctx.complete_success = AsyncMock()
        mock_context_cm = MagicMock()
        mock_context_cm.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_context_cm.__aexit__ = AsyncMock(return_value=None)
        mock_context.return_value = mock_context_cm
        
        # Mock the streaming publisher to track calls
        with patch.object(
            client._streaming_publisher, 'publish_chunk', new_callable=AsyncMock
        ) as mock_publish:
            result = await client.generate(
                conversation=sample_conversation,
                session_id="test-session",
                mcp_tools=[]
            )
        
        # Verify the result is_final matches expectation
        assert result.is_final == (not has_tool_calls)
        
        # Find the response streaming call (not thinking)
        response_calls = [
            call for call in mock_publish.call_args_list
            if call[0][2] != StreamingEventType.NATIVE_THINKING  # arg[2] is event_type
        ]
        
        # Verify at least one response event was published
        assert len(response_calls) > 0, "Expected at least one response streaming event"
        
        # Verify the final response call used the correct event type
        final_response_call = [
            call for call in response_calls 
            if call[1].get('is_complete', False)  # kwargs['is_complete']
        ]
        
        assert len(final_response_call) > 0, "Expected a final (is_complete=True) response event"
        
        # Extract event_type from the final call (positional arg 2)
        actual_event_type = final_response_call[0][0][2]
        
        assert actual_event_type == expected_event_type, (
            f"Expected {expected_event_type.value} event type for "
            f"{'intermediate' if has_tool_calls else 'final'} iteration, "
            f"but got {actual_event_type.value}"
        )
