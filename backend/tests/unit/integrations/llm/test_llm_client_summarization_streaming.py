"""
Unit tests for plain text summarization streaming in LLM client.

Tests the streaming behavior when interaction_type is SUMMARIZATION,
ensuring that the entire response is streamed as plain text without
"Thought:" or "Final Answer:" parsing.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.integrations.llm.client import LLMClient
from tarsy.models.constants import LLMInteractionType, StreamingEventType
from tarsy.models.unified_interactions import LLMConversation, LLMMessage, MessageRole

from .conftest import create_stream_side_effect, create_test_config


@pytest.mark.unit
class TestLLMClientSummarizationStreaming:
    """Test plain text summarization streaming behavior."""
    
    @pytest.fixture
    def client(self):
        """Create LLM client for testing."""
        with patch("tarsy.integrations.llm.client.ChatOpenAI"):
            client = LLMClient("openai", create_test_config(api_key="test"))
            client.available = True
            return client
    
    @pytest.mark.asyncio
    async def test_summarization_streams_entire_response_as_plain_text(self, client):
        """Test that summarization streams entire response without parsing."""
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="Summarize this result"),
                LLMMessage(role=MessageRole.USER, content="Tool result data"),
            ]
        )
        
        # Mock LLM response - plain text summary (no "Thought:" or "Final Answer:")
        summary_text = "The tool returned 3 pods: pod-1, pod-2, pod-3. All are running."
        
        # Mock the LLM client to return streaming chunks
        mock_llm_client = AsyncMock()
        mock_llm_client.astream = Mock(side_effect=create_stream_side_effect(
            summary_text,
            usage_metadata={"input_tokens": 50, "output_tokens": 20, "total_tokens": 70}
        ))
        client.llm_client = mock_llm_client
        
        # Mock streaming infrastructure
        published_chunks = []
        
        async def capture_publish(*args, **kwargs):
            """Capture published streaming chunks."""
            # Args: session, channel, event
            if len(args) >= 3:
                event = args[2]
                published_chunks.append({
                    "stream_type": event.stream_type,
                    "chunk": event.chunk,
                    "is_complete": event.is_complete,
                    "mcp_event_id": event.mcp_event_id
                })
        
        with patch("tarsy.database.init_db.get_async_session_factory") as mock_factory, \
             patch("tarsy.services.events.publisher.publish_transient_event", side_effect=capture_publish):
            mock_session = AsyncMock()
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__.return_value = mock_session
            mock_factory.return_value.return_value = mock_session_context
            
            # Execute with summarization interaction type
            result = await client.generate_response(
                conversation,
                session_id="test-session",
                stage_execution_id="stage-123",
                interaction_type=LLMInteractionType.SUMMARIZATION.value,
                mcp_event_id="mcp-event-789"
            )
        
        # Verify response was generated correctly
        assert result is not None
        assistant_msg = result.get_latest_assistant_message()
        assert assistant_msg is not None
        assert assistant_msg.content == summary_text
        
        # Verify streaming chunks were published
        assert len(published_chunks) > 0
        
        # All chunks should be of type 'summarization'
        for chunk in published_chunks:
            assert chunk["stream_type"] == StreamingEventType.SUMMARIZATION.value
            assert chunk["mcp_event_id"] == "mcp-event-789"
        
        # Last chunk should be complete
        assert published_chunks[-1]["is_complete"] is True
        assert published_chunks[-1]["chunk"] == summary_text
    
    @pytest.mark.asyncio
    async def test_summarization_streams_as_plain_text(self, client):
        """Test that summarization streams content as plain text."""
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="Summarize"),
                LLMMessage(role=MessageRole.USER, content="Data"),
            ]
        )
        
        # Plain text summary without ReAct markers (typical for summarization)
        summary_text = "The data indicates an upward trend over the past quarter."
        
        mock_llm_client = AsyncMock()
        mock_llm_client.astream = Mock(side_effect=create_stream_side_effect(summary_text))
        client.llm_client = mock_llm_client
        
        published_chunks = []
        
        async def capture_publish(*args, **kwargs):
            if len(args) >= 3:
                event = args[2]
                published_chunks.append({
                    "stream_type": event.stream_type,
                    "chunk": event.chunk,
                })
        
        with patch("tarsy.database.init_db.get_async_session_factory") as mock_factory, \
             patch("tarsy.services.events.publisher.publish_transient_event", side_effect=capture_publish):
            mock_session = AsyncMock()
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__.return_value = mock_session
            mock_factory.return_value.return_value = mock_session_context
            
            result = await client.generate_response(
                conversation,
                session_id="test-session",
                interaction_type=LLMInteractionType.SUMMARIZATION.value
            )
        
        # Response should contain the summary text
        assistant_msg = result.get_latest_assistant_message()
        assert "upward trend" in assistant_msg.content
        
        # All streaming chunks should be 'summarization' type
        for chunk in published_chunks:
            assert chunk["stream_type"] == StreamingEventType.SUMMARIZATION.value
    
    @pytest.mark.asyncio
    async def test_summarization_streaming_with_stage_execution_id(self, client):
        """Test that stage_execution_id is passed through streaming events."""
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="User"),
            ]
        )
        
        summary_text = "Brief summary."
        
        mock_llm_client = AsyncMock()
        mock_llm_client.astream = Mock(side_effect=create_stream_side_effect(summary_text))
        client.llm_client = mock_llm_client
        
        published_events = []
        
        async def capture_publish(*args, **kwargs):
            if len(args) >= 3:
                published_events.append(args[2])
        
        with patch("tarsy.database.init_db.get_async_session_factory") as mock_factory, \
             patch("tarsy.services.events.publisher.publish_transient_event", side_effect=capture_publish):
            mock_session = AsyncMock()
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__.return_value = mock_session
            mock_factory.return_value.return_value = mock_session_context
            
            await client.generate_response(
                conversation,
                session_id="test-session",
                stage_execution_id="stage-456",
                interaction_type=LLMInteractionType.SUMMARIZATION.value
            )
        
        # Verify all events have the correct stage_execution_id
        for event in published_events:
            assert event.stage_execution_id == "stage-456"
    
    @pytest.mark.asyncio
    async def test_summarization_streaming_without_mcp_event_id(self, client):
        """Test summarization streaming when mcp_event_id is not provided."""
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="User"),
            ]
        )
        
        summary_text = "Summary without MCP event."
        
        mock_llm_client = AsyncMock()
        mock_llm_client.astream = Mock(side_effect=create_stream_side_effect(summary_text))
        client.llm_client = mock_llm_client
        
        published_events = []
        
        async def capture_publish(*args, **kwargs):
            if len(args) >= 3:
                published_events.append(args[2])
        
        with patch("tarsy.database.init_db.get_async_session_factory") as mock_factory, \
             patch("tarsy.services.events.publisher.publish_transient_event", side_effect=capture_publish):
            mock_session = AsyncMock()
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__.return_value = mock_session
            mock_factory.return_value.return_value = mock_session_context
            
            await client.generate_response(
                conversation,
                session_id="test-session",
                interaction_type=LLMInteractionType.SUMMARIZATION.value
                # No mcp_event_id provided
            )
        
        # Verify all events have mcp_event_id as None
        for event in published_events:
            assert event.mcp_event_id is None
    
    @pytest.mark.asyncio
    async def test_investigation_does_not_use_summarization_streaming(self, client):
        """Test that investigation interaction type does not use summarization streaming."""
        conversation = LLMConversation(
            messages=[
                LLMMessage(role=MessageRole.SYSTEM, content="System"),
                LLMMessage(role=MessageRole.USER, content="User"),
            ]
        )
        
        # Response with ReAct pattern
        react_response = "Thought: I need to analyze this.\n\nAction: check_status"
        
        mock_llm_client = AsyncMock()
        mock_llm_client.astream = Mock(side_effect=create_stream_side_effect(react_response))
        client.llm_client = mock_llm_client
        
        published_chunks = []
        
        async def capture_publish(*args, **kwargs):
            if len(args) >= 3:
                event = args[2]
                published_chunks.append({
                    "stream_type": event.stream_type,
                })
        
        with patch("tarsy.database.init_db.get_async_session_factory") as mock_factory, \
             patch("tarsy.services.events.publisher.publish_transient_event", side_effect=capture_publish):
            mock_session = AsyncMock()
            mock_session_context = AsyncMock()
            mock_session_context.__aenter__.return_value = mock_session
            mock_factory.return_value.return_value = mock_session_context
            
            await client.generate_response(
                conversation,
                session_id="test-session",
                interaction_type=LLMInteractionType.INVESTIGATION.value
            )
        
        # Should use 'thought' streaming, not 'summarization'
        # (at least one chunk should be 'thought')
        stream_types = [chunk["stream_type"] for chunk in published_chunks]
        assert StreamingEventType.THOUGHT.value in stream_types
        assert StreamingEventType.SUMMARIZATION.value not in stream_types

