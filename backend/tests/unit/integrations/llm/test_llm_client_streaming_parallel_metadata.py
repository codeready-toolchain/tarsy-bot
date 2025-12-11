"""
Unit tests for LLM client streaming with parallel execution metadata support.

Tests the publish_chunk method with ParallelExecutionMetadata parameter to ensure
parallel execution context is correctly propagated to streaming events for proper
frontend filtering and display in parallel agent tabs.
"""

from unittest.mock import AsyncMock, patch

import pytest

from tarsy.integrations.llm.client import LLMClient
from tarsy.models.constants import StreamingEventType
from tarsy.models.parallel_metadata import ParallelExecutionMetadata

from .conftest import create_test_config


@pytest.mark.unit
class TestLLMClientStreamingWithParallelMetadata:
    """Test streaming chunk publishing with parallel execution metadata."""
    
    @pytest.fixture
    def client(self):
        """Create client for testing."""
        with patch("tarsy.integrations.llm.client.ChatOpenAI"):
            client = LLMClient("openai", create_test_config(api_key="test"))
            client.available = True
            return client
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_with_complete_parallel_metadata(self, client):
        """Test publishing chunk with full parallel execution metadata."""
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
            
            metadata = ParallelExecutionMetadata(
                parent_stage_execution_id="parent-stage-123",
                parallel_index=2,
                agent_name="LogAnalysisAgent"
            )
            
            await client._streaming_publisher.publish_chunk(
                session_id="test-session",
                stage_execution_id="child-stage-456",
                stream_type=StreamingEventType.THOUGHT,
                chunk="Analyzing logs for errors...",
                is_complete=False,
                llm_interaction_id="interaction-789",
                parallel_metadata=metadata
            )
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args.kwargs["event"]
            
            # Verify parallel metadata is unpacked correctly
            assert event.parent_stage_execution_id == "parent-stage-123"
            assert event.parallel_index == 2
            assert event.agent_name == "LogAnalysisAgent"
            
            # Verify other fields are correct
            assert event.stream_type == StreamingEventType.THOUGHT.value
            assert event.chunk == "Analyzing logs for errors..."
            assert event.stage_execution_id == "child-stage-456"
            assert event.llm_interaction_id == "interaction-789"
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_without_parallel_metadata(self, client):
        """Test publishing chunk without parallel metadata (single agent case)."""
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
                stream_type=StreamingEventType.FINAL_ANSWER,
                chunk="The issue is resolved.",
                is_complete=True,
                parallel_metadata=None
            )
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args.kwargs["event"]
            
            # Verify all parallel metadata fields are None
            assert event.parent_stage_execution_id is None
            assert event.parallel_index is None
            assert event.agent_name is None
            
            # Verify other fields are correct
            assert event.stream_type == StreamingEventType.FINAL_ANSWER.value
            assert event.chunk == "The issue is resolved."
            assert event.is_complete is True
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_with_partial_parallel_metadata(self, client):
        """Test publishing chunk with partially filled parallel metadata."""
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
            
            # Metadata with only agent_name set
            metadata = ParallelExecutionMetadata(
                parent_stage_execution_id=None,
                parallel_index=None,
                agent_name="MetricsAgent"
            )
            
            await client._streaming_publisher.publish_chunk(
                session_id="test-session",
                stage_execution_id="stage-abc",
                stream_type=StreamingEventType.NATIVE_THINKING,
                chunk="Thinking about metrics...",
                is_complete=False,
                parallel_metadata=metadata
            )
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args.kwargs["event"]
            
            # Verify partial metadata is unpacked correctly
            assert event.parent_stage_execution_id is None
            assert event.parallel_index is None
            assert event.agent_name == "MetricsAgent"
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_parallel_metadata_with_different_stream_types(self, client):
        """Test that parallel metadata works with all stream types."""
        stream_types = [
            StreamingEventType.THOUGHT,
            StreamingEventType.FINAL_ANSWER,
            StreamingEventType.NATIVE_THINKING,
            StreamingEventType.SUMMARIZATION
        ]
        
        for stream_type in stream_types:
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
                
                metadata = ParallelExecutionMetadata(
                    parent_stage_execution_id="parent-123",
                    parallel_index=1,
                    agent_name="TestAgent"
                )
                
                await client._streaming_publisher.publish_chunk(
                    session_id="test-session",
                    stage_execution_id="child-456",
                    stream_type=stream_type,
                    chunk="Test content",
                    is_complete=False,
                    parallel_metadata=metadata
                )
                
                mock_publish.assert_called_once()
                event = mock_publish.call_args.kwargs["event"]
                
                # Verify metadata is present regardless of stream type
                assert event.parent_stage_execution_id == "parent-123"
                assert event.parallel_index == 1
                assert event.agent_name == "TestAgent"
                assert event.stream_type == stream_type.value
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_error_handling_with_parallel_metadata(self, client):
        """Test that errors don't fail when parallel metadata is present."""
        with patch(
            "tarsy.database.init_db.get_async_session_factory"
        ) as mock_factory:
            mock_factory.side_effect = Exception("Event system failure")
            
            metadata = ParallelExecutionMetadata(
                parent_stage_execution_id="parent-error-test",
                parallel_index=1,
                agent_name="ErrorTestAgent"
            )
            
            # Should not raise exception even with parallel metadata
            await client._streaming_publisher.publish_chunk(
                session_id="test-session",
                stage_execution_id="stage-error",
                stream_type=StreamingEventType.THOUGHT,
                chunk="Test content",
                is_complete=False,
                parallel_metadata=metadata
            )
    
    @pytest.mark.asyncio
    async def test_publish_stream_chunk_with_all_optional_parameters(self, client):
        """Test publishing chunk with all optional parameters including parallel metadata."""
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
            
            metadata = ParallelExecutionMetadata(
                parent_stage_execution_id="parent-full-test",
                parallel_index=3,
                agent_name="FullTestAgent"
            )
            
            await client._streaming_publisher.publish_chunk(
                session_id="test-session",
                stage_execution_id="stage-full",
                stream_type=StreamingEventType.SUMMARIZATION,
                chunk="Complete test with all parameters",
                is_complete=True,
                mcp_event_id="mcp-123",
                llm_interaction_id="interaction-456",
                parallel_metadata=metadata
            )
            
            mock_publish.assert_called_once()
            event = mock_publish.call_args.kwargs["event"]
            
            # Verify all fields are correctly set
            assert event.session_id == "test-session"
            assert event.stage_execution_id == "stage-full"
            assert event.stream_type == StreamingEventType.SUMMARIZATION.value
            assert event.chunk == "Complete test with all parameters"
            assert event.is_complete is True
            assert event.mcp_event_id == "mcp-123"
            assert event.llm_interaction_id == "interaction-456"
            assert event.parent_stage_execution_id == "parent-full-test"
            assert event.parallel_index == 3
            assert event.agent_name == "FullTestAgent"

