"""
Unit tests for LLM client streaming with llm_interaction_id support.

Tests the _publish_stream_chunk method with llm_interaction_id parameter for
deduplication of thought/final_answer/native_thinking streams in the dashboard.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tarsy.integrations.llm.client import LLMClient
from tarsy.models.constants import StreamingEventType

from .conftest import create_test_config


@pytest.mark.unit
class TestLLMClientStreamingWithLLMInteractionID:
    """Test streaming chunk publishing with llm_interaction_id parameter."""
    
    @pytest.fixture
    def client(self):
        """Create client for testing."""
        with patch("tarsy.integrations.llm.client.ChatOpenAI"):
            client = LLMClient("openai", create_test_config(api_key="test"))
            client.available = True
            return client
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_thought_with_llm_interaction_id(self, client):
        """Test publishing thought chunk with llm_interaction_id."""
        with patch(
            "tarsy.database.init_db.get_async_session_factory"
        ) as mock_factory, patch(
            "tarsy.services.events.publisher.publish_transient_event",
            new_callable=AsyncMock
        ) as mock_publish:
            mock_session = AsyncMock()
            mock_session.bind.dialect.name = "postgresql"
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__.return_value = mock_session
            mock_factory.return_value.return_value = mock_session_context
            
            await client._streaming_publisher.publish_chunk(
                session_id="test-session",
                stage_execution_id="stage-123",
                stream_type=StreamingEventType.THOUGHT,
                chunk="This is my thought process",
                is_complete=False,
                llm_interaction_id="interaction-abc123"
            )
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args.kwargs["event"]
            
            assert event.stream_type == StreamingEventType.THOUGHT.value
            assert event.chunk == "This is my thought process"
            assert event.llm_interaction_id == "interaction-abc123"
            assert event.is_complete is False
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_final_answer_with_llm_interaction_id(self, client):
        """Test publishing final answer chunk with llm_interaction_id."""
        with patch(
            "tarsy.database.init_db.get_async_session_factory"
        ) as mock_factory, patch(
            "tarsy.services.events.publisher.publish_transient_event",
            new_callable=AsyncMock
        ) as mock_publish:
            mock_session = AsyncMock()
            mock_session.bind.dialect.name = "postgresql"
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__.return_value = mock_session
            mock_factory.return_value.return_value = mock_session_context
            
            await client._streaming_publisher.publish_chunk(
                session_id="test-session",
                stage_execution_id="stage-456",
                stream_type=StreamingEventType.FINAL_ANSWER,
                chunk="The root cause is...",
                is_complete=True,
                llm_interaction_id="interaction-def456"
            )
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args.kwargs["event"]
            
            assert event.stream_type == StreamingEventType.FINAL_ANSWER.value
            assert event.llm_interaction_id == "interaction-def456"
            assert event.is_complete is True
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_native_thinking_with_llm_interaction_id(self, client):
        """Test publishing native thinking chunk with llm_interaction_id."""
        with patch(
            "tarsy.database.init_db.get_async_session_factory"
        ) as mock_factory, patch(
            "tarsy.services.events.publisher.publish_transient_event",
            new_callable=AsyncMock
        ) as mock_publish:
            mock_session = AsyncMock()
            mock_session.bind.dialect.name = "postgresql"
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__.return_value = mock_session
            mock_factory.return_value.return_value = mock_session_context
            
            await client._streaming_publisher.publish_chunk(
                session_id="test-session",
                stage_execution_id="stage-789",
                stream_type=StreamingEventType.NATIVE_THINKING,
                chunk="Let me analyze this situation...",
                is_complete=False,
                llm_interaction_id="interaction-ghi789"
            )
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args.kwargs["event"]
            
            assert event.stream_type == StreamingEventType.NATIVE_THINKING.value
            assert event.chunk == "Let me analyze this situation..."
            assert event.llm_interaction_id == "interaction-ghi789"
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_without_llm_interaction_id(self, client):
        """Test publishing chunk without llm_interaction_id (should be None)."""
        with patch(
            "tarsy.database.init_db.get_async_session_factory"
        ) as mock_factory, patch(
            "tarsy.services.events.publisher.publish_transient_event",
            new_callable=AsyncMock
        ) as mock_publish:
            mock_session = AsyncMock()
            mock_session.bind.dialect.name = "postgresql"
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__.return_value = mock_session
            mock_factory.return_value.return_value = mock_session_context
            
            await client._streaming_publisher.publish_chunk(
                session_id="test-session",
                stage_execution_id="stage-123",
                stream_type=StreamingEventType.THOUGHT,
                chunk="Thought without interaction ID",
                is_complete=False
            )
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args.kwargs["event"]
            
            assert event.stream_type == StreamingEventType.THOUGHT.value
            assert event.llm_interaction_id is None
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_with_both_mcp_event_id_and_llm_interaction_id(self, client):
        """Test publishing summarization with both mcp_event_id and llm_interaction_id."""
        with patch(
            "tarsy.database.init_db.get_async_session_factory"
        ) as mock_factory, patch(
            "tarsy.services.events.publisher.publish_transient_event",
            new_callable=AsyncMock
        ) as mock_publish:
            mock_session = AsyncMock()
            mock_session.bind.dialect.name = "postgresql"
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__.return_value = mock_session
            mock_factory.return_value.return_value = mock_session_context
            
            await client._streaming_publisher.publish_chunk(
                session_id="test-session",
                stage_execution_id="stage-123",
                stream_type=StreamingEventType.SUMMARIZATION,
                chunk="Summary of tool call result",
                is_complete=False,
                mcp_event_id="mcp-event-123",
                llm_interaction_id="interaction-456"
            )
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args.kwargs["event"]
            
            assert event.stream_type == StreamingEventType.SUMMARIZATION.value
            assert event.mcp_event_id == "mcp-event-123"
            assert event.llm_interaction_id == "interaction-456"
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_error_handling_with_llm_interaction_id(self, client):
        """Test that errors don't fail when llm_interaction_id is present."""
        with patch(
            "tarsy.database.init_db.get_async_session_factory"
        ) as mock_factory:
            mock_factory.side_effect = Exception("Event system failure")
            
            # Should not raise exception even with llm_interaction_id
            await client._streaming_publisher.publish_chunk(
                session_id="test-session",
                stage_execution_id=None,
                stream_type=StreamingEventType.THOUGHT,
                chunk="Test content",
                is_complete=False,
                llm_interaction_id="interaction-error-test"
            )

