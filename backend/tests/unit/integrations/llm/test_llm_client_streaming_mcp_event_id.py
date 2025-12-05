"""
Unit tests for LLM client streaming with mcp_event_id support.

Tests the _publish_stream_chunk method with mcp_event_id parameter for linking
summarization streams to their related tool calls.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tarsy.integrations.llm.client import LLMClient
from tarsy.models.constants import StreamingEventType

from .conftest import create_test_config


@pytest.mark.unit
class TestLLMClientStreamingWithMCPEventID:
    """Test streaming chunk publishing with mcp_event_id parameter."""
    
    @pytest.fixture
    def client(self):
        """Create client for testing."""
        with patch("tarsy.integrations.llm.client.ChatOpenAI"):
            client = LLMClient("openai", create_test_config(api_key="test"))
            client.available = True
            return client
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_summarization_with_mcp_event_id(self, client):
        """Test publishing summarization chunk with mcp_event_id."""
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
                chunk="Summary of kubectl get pods result",
                is_complete=False,
                mcp_event_id="mcp-event-456"
            )
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args.kwargs["event"]
            
            assert event.stream_type == StreamingEventType.SUMMARIZATION.value
            assert event.chunk == "Summary of kubectl get pods result"
            assert event.mcp_event_id == "mcp-event-456"
            assert event.is_complete is False
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_summarization_without_mcp_event_id(self, client):
        """Test publishing summarization chunk without mcp_event_id (should be None)."""
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
                stage_execution_id=None,
                stream_type=StreamingEventType.SUMMARIZATION,
                chunk="Summary without MCP event ID",
                is_complete=False
            )
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args.kwargs["event"]
            
            assert event.stream_type == StreamingEventType.SUMMARIZATION.value
            assert event.mcp_event_id is None
    
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_error_handling_with_mcp_event_id(self, client):
        """Test that errors don't fail when mcp_event_id is present."""
        with patch(
            "tarsy.database.init_db.get_async_session_factory"
        ) as mock_factory:
            mock_factory.side_effect = Exception("Event system failure")
            
            # Should not raise exception even with mcp_event_id
            await client._streaming_publisher.publish_chunk(
                session_id="test-session",
                stage_execution_id=None,
                stream_type=StreamingEventType.SUMMARIZATION,
                chunk="Summary content",
                is_complete=False,
                mcp_event_id="mcp-event-error-test"
            )

