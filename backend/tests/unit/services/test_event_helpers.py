"""
Unit tests for event helper functions.

This module tests the helper functions for publishing events.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.services.events.channels import EventChannel
from tarsy.models.constants import ProgressPhase
from tarsy.services.events.event_helpers import (
    publish_chat_cancel_request,
    publish_llm_interaction,
    publish_mcp_tool_call,
    publish_mcp_tool_call_started,
    publish_mcp_tool_list,
    publish_session_completed,
    publish_session_created,
    publish_session_failed,
    publish_session_progress_update,
    publish_session_started,
    publish_stage_completed,
    publish_stage_started,
)


@pytest.mark.unit
class TestPublishSessionCreated:
    """Test publish_session_created helper."""

    @pytest.mark.asyncio
    async def test_publishes_session_created_event(self):
        """Test that it publishes session.created event to both channels."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_session_created("test-session-123", "alert-type-1")

            # Should publish to both 'sessions' and 'session:{session_id}' channels
            assert mock_publish.call_count == 2
            
            # First call: global sessions channel
            first_call = mock_publish.call_args_list[0]
            assert first_call[0][0] is mock_session
            assert first_call[0][1] == EventChannel.SESSIONS
            event = first_call[0][2]
            assert event.session_id == "test-session-123"
            assert event.alert_type == "alert-type-1"
            
            # Second call: session-specific channel
            second_call = mock_publish.call_args_list[1]
            assert second_call[0][0] is mock_session
            assert second_call[0][1] == "session:test-session-123"
            event = second_call[0][2]
            assert event.session_id == "test-session-123"
            assert event.alert_type == "alert-type-1"

    @pytest.mark.asyncio
    async def test_handles_publish_error(self):
        """Test that it handles publish errors gracefully."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", side_effect=Exception("DB error")):
            # Should not raise
            await publish_session_created("test-session-123", "alert-type-1")


@pytest.mark.unit
class TestPublishSessionStarted:
    """Test publish_session_started helper."""

    @pytest.mark.asyncio
    async def test_publishes_session_started_event(self):
        """Test that it publishes session.started event to both channels."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_session_started("test-session-123", "alert-type-1")

            # Should publish to both 'sessions' and 'session:{session_id}' channels
            assert mock_publish.call_count == 2
            
            # First call: global sessions channel
            first_call = mock_publish.call_args_list[0]
            assert first_call[0][1] == EventChannel.SESSIONS
            event = first_call[0][2]
            assert event.session_id == "test-session-123"
            assert event.alert_type == "alert-type-1"
            
            # Second call: session-specific channel
            second_call = mock_publish.call_args_list[1]
            assert second_call[0][1] == "session:test-session-123"
            event = second_call[0][2]
            assert event.session_id == "test-session-123"
            assert event.alert_type == "alert-type-1"

    @pytest.mark.asyncio
    async def test_handles_publish_error(self):
        """Test that it handles publish errors gracefully."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", side_effect=Exception("DB error")):
            # Should not raise
            await publish_session_started("test-session-123", "alert-type-1")


@pytest.mark.unit
class TestPublishSessionCompleted:
    """Test publish_session_completed helper."""

    @pytest.mark.asyncio
    async def test_publishes_session_completed_event(self):
        """Test that it publishes session.completed event to both channels."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_session_completed("test-session-123")

            # Should publish to both 'sessions' and 'session:{session_id}' channels
            assert mock_publish.call_count == 2
            
            # First call: global sessions channel
            first_call = mock_publish.call_args_list[0]
            assert first_call[0][1] == EventChannel.SESSIONS
            event = first_call[0][2]
            assert event.session_id == "test-session-123"
            assert event.status == "completed"
            
            # Second call: session-specific channel
            second_call = mock_publish.call_args_list[1]
            assert second_call[0][1] == "session:test-session-123"
            event = second_call[0][2]
            assert event.session_id == "test-session-123"
            assert event.status == "completed"

    @pytest.mark.asyncio
    async def test_handles_publish_error(self):
        """Test that it handles publish errors gracefully."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", side_effect=Exception("DB error")):
            # Should not raise
            await publish_session_completed("test-session-123")


@pytest.mark.unit
class TestPublishSessionFailed:
    """Test publish_session_failed helper."""

    @pytest.mark.asyncio
    async def test_publishes_session_failed_event(self):
        """Test that it publishes session.failed event to both channels."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_session_failed("test-session-123")

            # Should publish to both 'sessions' and 'session:{session_id}' channels
            assert mock_publish.call_count == 2
            
            # First call: global sessions channel
            first_call = mock_publish.call_args_list[0]
            assert first_call[0][1] == EventChannel.SESSIONS
            event = first_call[0][2]
            assert event.session_id == "test-session-123"
            assert event.status == "failed"
            
            # Second call: session-specific channel
            second_call = mock_publish.call_args_list[1]
            assert second_call[0][1] == "session:test-session-123"
            event = second_call[0][2]
            assert event.session_id == "test-session-123"
            assert event.status == "failed"

    @pytest.mark.asyncio
    async def test_handles_publish_error(self):
        """Test that it handles publish errors gracefully."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", side_effect=Exception("DB error")):
            # Should not raise
            await publish_session_failed("test-session-123")


@pytest.mark.unit
class TestPublishLLMInteraction:
    """Test publish_llm_interaction helper."""

    @pytest.mark.asyncio
    async def test_publishes_llm_interaction_event(self):
        """Test that it publishes llm.interaction event."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_llm_interaction("test-session-123", "interaction-456", "stage-789")

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][1] == EventChannel.session_details("test-session-123")
            event = call_args[0][2]
            assert event.session_id == "test-session-123"
            assert event.interaction_id == "interaction-456"
            assert event.stage_id == "stage-789"

    @pytest.mark.asyncio
    async def test_publishes_without_stage_id(self):
        """Test publishing without stage_id."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_llm_interaction("test-session-123", "interaction-456")

            event = mock_publish.call_args[0][2]
            assert event.stage_id is None

    @pytest.mark.asyncio
    async def test_handles_publish_error(self):
        """Test that it handles publish errors gracefully."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", side_effect=Exception("DB error")):
            # Should not raise
            await publish_llm_interaction("test-session-123", "interaction-456")


@pytest.mark.unit
class TestPublishMCPToolCallStarted:
    """Test publish_mcp_tool_call_started helper."""

    @pytest.mark.asyncio
    async def test_publishes_mcp_tool_call_started_event(self):
        """Test that it publishes mcp.tool_call.started event with all required fields."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_mcp_tool_call_started(
                session_id="test-session-123",
                communication_id="comm-456",
                server_name="kubernetes",
                tool_name="kubectl_get_pods",
                tool_arguments={"namespace": "default"},
                stage_id="stage-789"
            )

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][1] == EventChannel.session_details("test-session-123")
            event = call_args[0][2]
            assert event.type == "mcp.tool_call.started"
            assert event.session_id == "test-session-123"
            assert event.communication_id == "comm-456"
            assert event.server_name == "kubernetes"
            assert event.tool_name == "kubectl_get_pods"
            assert event.tool_arguments == {"namespace": "default"}
            assert event.stage_id == "stage-789"

    @pytest.mark.asyncio
    async def test_publishes_without_stage_id(self):
        """Test publishing without stage_id."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_mcp_tool_call_started(
                session_id="test-session-123",
                communication_id="comm-456",
                server_name="kubernetes",
                tool_name="kubectl_get_pods",
                tool_arguments={}
            )

            event = mock_publish.call_args[0][2]
            assert event.stage_id is None

    @pytest.mark.asyncio
    async def test_publishes_with_complex_arguments(self):
        """Test publishing with complex tool arguments."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        complex_args = {
            "namespace": "production",
            "labels": {"app": "frontend", "version": "v1.2.3"},
            "limit": 100,
            "nested": {"field": "value"}
        }

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_mcp_tool_call_started(
                session_id="test-session-123",
                communication_id="comm-789",
                server_name="kubernetes",
                tool_name="kubectl_get_pods",
                tool_arguments=complex_args
            )

            event = mock_publish.call_args[0][2]
            assert event.tool_arguments == complex_args

    @pytest.mark.asyncio
    async def test_handles_publish_error(self):
        """Test that it handles publish errors gracefully."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", side_effect=Exception("DB error")):
            # Should not raise
            await publish_mcp_tool_call_started(
                session_id="test-session-123",
                communication_id="comm-456",
                server_name="kubernetes",
                tool_name="kubectl_get_pods",
                tool_arguments={}
            )


@pytest.mark.unit
class TestPublishMCPToolCall:
    """Test publish_mcp_tool_call helper."""

    @pytest.mark.asyncio
    async def test_publishes_mcp_tool_call_event(self):
        """Test that it publishes mcp.tool_call event."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_mcp_tool_call(
                "test-session-123", "interaction-456", "kubectl_get_pods", "stage-789"
            )

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][1] == EventChannel.session_details("test-session-123")
            event = call_args[0][2]
            assert event.session_id == "test-session-123"
            assert event.interaction_id == "interaction-456"
            assert event.tool_name == "kubectl_get_pods"
            assert event.stage_id == "stage-789"

    @pytest.mark.asyncio
    async def test_publishes_without_stage_id(self):
        """Test publishing without stage_id."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_mcp_tool_call("test-session-123", "interaction-456", "kubectl_get_pods")

            event = mock_publish.call_args[0][2]
            assert event.stage_id is None

    @pytest.mark.asyncio
    async def test_handles_publish_error(self):
        """Test that it handles publish errors gracefully."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", side_effect=Exception("DB error")):
            # Should not raise
            await publish_mcp_tool_call("test-session-123", "interaction-456", "kubectl_get_pods")


@pytest.mark.unit
class TestPublishMCPToolList:
    """Test publish_mcp_tool_list helper."""

    @pytest.mark.asyncio
    async def test_publishes_mcp_tool_list_event(self):
        """Test that it publishes mcp.tool_list event."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_mcp_tool_list(
                "test-session-123", "request-456", "kubernetes", "stage-789"
            )

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][1] == EventChannel.session_details("test-session-123")
            event = call_args[0][2]
            assert event.session_id == "test-session-123"
            assert event.request_id == "request-456"
            assert event.server_name == "kubernetes"
            assert event.stage_id == "stage-789"

    @pytest.mark.asyncio
    async def test_publishes_without_optional_fields(self):
        """Test publishing without optional fields."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_mcp_tool_list("test-session-123", "request-456")

            event = mock_publish.call_args[0][2]
            assert event.server_name is None
            assert event.stage_id is None

    @pytest.mark.asyncio
    async def test_handles_publish_error(self):
        """Test that it handles publish errors gracefully."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", side_effect=Exception("DB error")):
            # Should not raise
            await publish_mcp_tool_list("test-session-123", "request-456")


@pytest.mark.unit
class TestPublishStageStarted:
    """Test publish_stage_started helper."""

    @pytest.mark.asyncio
    async def test_publishes_stage_started_event(self):
        """Test that it publishes stage.started event with optional chat user message data."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            # Test without user message data
            await publish_stage_started("test-session-123", "stage-456", "Investigation")

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][1] == EventChannel.session_details("test-session-123")
            event = call_args[0][2]
            assert event.session_id == "test-session-123"
            assert event.stage_id == "stage-456"
            assert event.stage_name == "Investigation"
            assert event.chat_id is None
            assert event.chat_user_message_id is None
            assert event.chat_user_message_content is None
            assert event.chat_user_message_author is None
            
            # Test with user message data
            mock_publish.reset_mock()
            await publish_stage_started(
                "test-session-123", 
                "stage-789", 
                "Chat Response",
                chat_id="chat-abc",
                chat_user_message_id="msg-123",
                chat_user_message_content="What's wrong with the pod?",
                chat_user_message_author="john.doe"
            )
            
            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            event = call_args[0][2]
            assert event.chat_id == "chat-abc"
            assert event.chat_user_message_id == "msg-123"
            assert event.chat_user_message_content == "What's wrong with the pod?"
            assert event.chat_user_message_author == "john.doe"

    @pytest.mark.asyncio
    async def test_handles_publish_error(self):
        """Test that it handles publish errors gracefully."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", side_effect=Exception("DB error")):
            # Should not raise
            await publish_stage_started("test-session-123", "stage-456", "Investigation")


@pytest.mark.unit
class TestPublishStageCompleted:
    """Test publish_stage_completed helper."""

    @pytest.mark.asyncio
    async def test_publishes_stage_completed_event(self):
        """Test that it publishes stage.completed event."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_stage_completed(
                "test-session-123", "stage-456", "Investigation", "completed"
            )

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][1] == EventChannel.session_details("test-session-123")
            event = call_args[0][2]
            assert event.session_id == "test-session-123"
            assert event.stage_id == "stage-456"
            assert event.stage_name == "Investigation"
            assert event.status == "completed"

    @pytest.mark.asyncio
    async def test_publishes_failed_status(self):
        """Test publishing with failed status."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_stage_completed(
                "test-session-123", "stage-456", "Investigation", "failed"
            )

            event = mock_publish.call_args[0][2]
            assert event.status == "failed"

    @pytest.mark.asyncio
    async def test_publishes_partial_status(self):
        """Test publishing with partial status."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_stage_completed(
                "test-session-123", "stage-456", "Investigation", "partial"
            )

            event = mock_publish.call_args[0][2]
            assert event.status == "partial"

    @pytest.mark.asyncio
    async def test_handles_publish_error(self):
        """Test that it handles publish errors gracefully."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", side_effect=Exception("DB error")):
            # Should not raise
            await publish_stage_completed(
                "test-session-123", "stage-456", "Investigation", "completed"
            )


@pytest.mark.unit
class TestPublishChatCancelRequest:
    """Test publish_chat_cancel_request helper."""

    @pytest.mark.asyncio
    async def test_publishes_chat_cancel_request_event(self):
        """Test that it publishes chat.cancel_requested event to CANCELLATIONS channel."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_chat_cancel_request("exec-123-456")

            mock_publish.assert_called_once()
            call_args = mock_publish.call_args
            assert call_args[0][0] is mock_session
            assert call_args[0][1] == EventChannel.CANCELLATIONS
            event = call_args[0][2]
            assert event.type == "chat.cancel_requested"
            assert event.stage_execution_id == "exec-123-456"

    @pytest.mark.asyncio
    async def test_handles_publish_error(self):
        """Test that it handles publish errors gracefully."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", side_effect=Exception("DB error")):
            # Should not raise
            await publish_chat_cancel_request("exec-123-456")


@pytest.mark.unit
class TestPublishSessionProgressUpdate:
    """Test publish_session_progress_update helper."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "phase_input,expected_phase_value",
        [
            (ProgressPhase.INVESTIGATING, "investigating"),
            (ProgressPhase.SYNTHESIZING, "synthesizing"),
            (ProgressPhase.SUMMARIZING, "summarizing"),
            ("investigating", "investigating"),
            ("synthesizing", "synthesizing"),
            ("summarizing", "summarizing"),
        ],
    )
    async def test_publishes_progress_update_with_enum_or_string(
        self, phase_input: ProgressPhase | str, expected_phase_value: str
    ) -> None:
        """Test that it publishes progress update event with both enum and string inputs."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_session_progress_update("test-session-123", phase_input, metadata=None)

            # Should publish to both 'sessions' and 'session:{session_id}' channels
            assert mock_publish.call_count == 2
            
            # First call: global sessions channel
            first_call = mock_publish.call_args_list[0]
            assert first_call[0][0] is mock_session
            assert first_call[0][1] == EventChannel.SESSIONS
            event = first_call[0][2]
            assert event.session_id == "test-session-123"
            assert event.phase == expected_phase_value
            assert event.metadata is None
            
            # Second call: session-specific channel
            second_call = mock_publish.call_args_list[1]
            assert second_call[0][0] is mock_session
            assert second_call[0][1] == "session:test-session-123"
            event = second_call[0][2]
            assert event.session_id == "test-session-123"
            assert event.phase == expected_phase_value

    @pytest.mark.asyncio
    async def test_publishes_progress_update_with_metadata(self) -> None:
        """Test that it includes optional metadata when provided."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        test_metadata = {"stage_name": "synthesis", "parallel_count": 3}

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", new_callable=AsyncMock) as mock_publish:
            await publish_session_progress_update(
                "test-session-123", 
                ProgressPhase.SYNTHESIZING,
                metadata=test_metadata
            )

            # Verify metadata is included
            first_call = mock_publish.call_args_list[0]
            event = first_call[0][2]
            assert event.metadata == test_metadata

    @pytest.mark.asyncio
    async def test_handles_publish_error(self) -> None:
        """Test that it handles publish errors gracefully."""
        mock_session = AsyncMock()
        mock_session_factory = Mock(return_value=mock_session)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()

        with patch("tarsy.services.events.event_helpers.get_async_session_factory", return_value=mock_session_factory), \
             patch("tarsy.services.events.event_helpers.publish_event", side_effect=Exception("DB error")):
            # Should not raise
            await publish_session_progress_update("test-session-123", ProgressPhase.INVESTIGATING)

