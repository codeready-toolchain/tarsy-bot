"""
E2E Tests for Slack Integration.

Tests the complete Slack notification flow integrated with Alert processing:
1. Alert processing started notifications (threaded)
2. Alert processing completed notifications (threaded and direct)
3. Alert processing error notifications (threaded and direct)
4. Alert processing paused notifications (threaded and direct)

Architecture:
- REAL: FastAPI app, AlertService, Slack service integration
- MOCKED: Slack SDK API calls, LLM APIs, MCP servers
"""

import logging
from unittest.mock import AsyncMock

import pytest
from slack_sdk.errors import SlackApiError

from .conftest import create_mock_stream
from .e2e_utils import E2ETestUtils

from tarsy.services.alert_service import get_alert_service

logger = logging.getLogger(__name__)


def create_slack_call_tracker(mock_slack_client, slack_calls):
    """
    Helper to track Slack API calls for testing.
    
    Args:
        mock_slack_client: The mocked Slack client
        slack_calls: List to append call records to
        
    Returns:
        Function that wraps a Slack client method to track calls
    """
    def track_slack_call(method_name):
        original_method = getattr(mock_slack_client, method_name)
        
        async def wrapper(*args, **kwargs):
            slack_calls.append({
                "method": method_name,
                "args": args,
                "kwargs": kwargs
            })
            return await original_method(*args, **kwargs)
        
        setattr(mock_slack_client, method_name, wrapper)
    
    return track_slack_call


@pytest.fixture
def mock_slack_service():
    """Create and configure a mock Slack client for E2E tests."""
    mock_client = AsyncMock()
    mock_client.conversations_history = AsyncMock(return_value={
        "messages": []
    })
    mock_client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "1234567890.123456"})
    return mock_client


@pytest.fixture
def slack_alert_with_fingerprint():
    """Alert with Slack message fingerprint for threaded replies."""
    return {
        "alert_type": "test-kubernetes",
        "timestamp": 1234567890,
        "data": {
            "namespace": "production",
            "pod_name": "api-server-abc123",
            "container": "api-server",
            "restart_count": 5
        },
        "slack_message_fingerprint": "incident-12345"
    }


@pytest.fixture
def slack_alert_without_fingerprint():
    """Alert without Slack fingerprint for direct channel posting."""
    return {
        "alert_type": "test-kubernetes",
        "timestamp": 1234567890,
        "data": {
            "namespace": "production",
            "pod_name": "api-server-abc123",
            "container": "api-server",
            "restart_count": 5
        }
        # No slack_message_fingerprint
    }


@pytest.mark.asyncio
@pytest.mark.e2e
class TestSlackThreadedNotificationCompleted:
    """Test Slack threaded notification with completed session."""

    async def test_slack_threaded_notification_with_completed_session(
        self,
        e2e_test_client,
        mock_slack_service,
        slack_alert_with_fingerprint
    ):
        """
        Test complete alert processing with Slack threaded notifications with completed session.
        
        Verifies:
        1. Started notification sent to Slack thread
        2. Alert processing completes successfully
        3. Completion notification sent to same Slack thread
        4. All messages use correct thread_ts for threading
        """
        print("🚀 Testing Slack threaded notification flow...")
        
        # Use the mock Slack client from fixture
        mock_slack_client = mock_slack_service
        
        # Configure mock responses for this test
        mock_slack_client.conversations_history = AsyncMock(return_value={
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "text": "Pod api-server-abc123 is crash-looping - incident-12345",
                    "attachments": []
                },
                {
                    "ts": "1234567889.123455",
                    "text": "Some other message",
                    "attachments": []
                }
            ]
        })
        mock_slack_client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "1234567891.123457"})
        
        # Track Slack API calls
        slack_calls = []
        track_slack_call = create_slack_call_tracker(mock_slack_client, slack_calls)
        track_slack_call("conversations_history")
        track_slack_call("chat_postMessage")
        
        # Mock LLM streaming responses at LangChain level
        async def mock_astream(*_args, **_kwargs):
            """Mock astream that returns a simple successful response."""
            # Simple successful analysis
            response = """Final Answer: The pod is crash-looping due to memory limit exceeded. 
Recommendation: Increase memory limit to 512Mi and add restart backoff policy."""
            
            usage = {
                "input_tokens": 200,
                "output_tokens": 100,
                "total_tokens": 300
            }
            async for chunk in create_mock_stream(response, usage_metadata=usage):
                yield chunk
        
        streaming_mock = mock_astream
        
        # Inject mock Slack client into the app's SlackService
        alert_service = get_alert_service()
        alert_service.slack_service.client = mock_slack_client
        alert_service.slack_service.enabled = True
        
        with (
            E2ETestUtils.create_llm_patch_context(streaming_mock=streaming_mock),
            E2ETestUtils.setup_runbook_service_patching(),
        ):
                # Submit alert
                print("📤 Submitting alert with Slack fingerprint...")
                response = e2e_test_client.post(
                    "/api/v1/alerts",
                    json=slack_alert_with_fingerprint
                )
                
                assert response.status_code == 200
                session_id = response.json()["session_id"]
                print(f"✅ Alert submitted, session_id: {session_id}")
                
                # Wait for processing to complete
                print("⏳ Waiting for processing...")
                session, final_status = await E2ETestUtils.wait_for_session_completion(
                    e2e_test_client, 
                    max_wait_seconds=30,
                )
                
                assert session == session_id and final_status == "completed"
                print(f"✅ Session completed: {final_status}")
                
                # Verify Slack API calls
                print(f"📊 Total Slack calls: {len(slack_calls)}")
                
                # Should have exactly 4 calls (started + completion with executive summary):
                # 1. conversations_history (find message for started notification)
                # 2. chat_postMessage (started notification)
                # 3. conversations_history (find message for completion notification)
                # 4. chat_postMessage (completion notification with executive summary)
                
                assert len(slack_calls) == 4, f"Expected exactly 4 Slack calls, got {len(slack_calls)}"
                
                # Verify started notification
                started_post_calls = [c for c in slack_calls if c["method"] == "chat_postMessage" and "🔄 Processing alert started. This may take a few minutes..." in str(c["kwargs"].get("attachments", []))]
                assert len(started_post_calls) == 1, f"Expected exactly 1 started notification, got {len(started_post_calls)}"
                
                started_call = started_post_calls[0]
                assert "thread_ts" in started_call["kwargs"], "Started notification should use threading"
                assert started_call["kwargs"]["thread_ts"] == "1234567890.123456", "Wrong thread timestamp"
                print("✅ Started notification sent to correct thread")
                
                # Verify completion notification
                completion_post_calls = [c for c in slack_calls if c["method"] == "chat_postMessage" and c not in started_post_calls]
                assert len(completion_post_calls) == 1, f"Expected exactly 1 completion notification, got {len(completion_post_calls)}"
                
                completion_call = completion_post_calls[0]
                assert "thread_ts" in completion_call["kwargs"], "Completion notification should use threading"
                assert completion_call["kwargs"]["thread_ts"] == "1234567890.123456", "Wrong thread timestamp"
                
                # Verify completion message content
                attachments = completion_call["kwargs"].get("attachments", [])
                assert len(attachments) > 0, "No attachments in completion notification"
                assert attachments[0]["color"] == "good", "Completion should use 'good' color"
                
                completion_text = attachments[0].get("text", "")
                assert session_id in completion_text, "Session ID should be in completion message"
                print("✅ Completion notification sent to correct thread with proper content")


@pytest.mark.asyncio
@pytest.mark.e2e
class TestSlackDirectChannelNotificationCompleted:
    """Test Slack direct channel notification with completed session."""

    async def test_slack_direct_channel_notification_with_completed_session(
        self, 
        e2e_test_client,
        mock_slack_service,
        slack_alert_without_fingerprint
    ):
        """
        Test alert processing with direct channel posting (no threading) with completed session.
        
        Verifies:
        1. Started notification NOT sent (no fingerprint)
        2. Alert processing completes successfully
        3. Completion notification sent directly to channel (no thread_ts)
        """
        print("🚀 Testing Slack direct channel posting...")
        
        # Use the mock Slack client from fixture
        mock_slack_client = mock_slack_service
        
        # Configure mock for this test
        mock_slack_client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "1234567891.123457"})
        
        slack_calls = []
        track_slack_call = create_slack_call_tracker(mock_slack_client, slack_calls)
        track_slack_call("conversations_history")
        track_slack_call("chat_postMessage")
        
        # Mock LLM streaming at LangChain level
        async def mock_astream(*_args, **_kwargs):
            """Mock astream that returns a simple successful response."""
            response = """Final Answer: Analysis complete. Issue resolved."""
            usage = {
                "input_tokens": 150,
                "output_tokens": 80,
                "total_tokens": 230
            }
            async for chunk in create_mock_stream(response, usage_metadata=usage):
                yield chunk
        
        streaming_mock = mock_astream
        
        # Inject mock Slack client into the app's SlackService
        alert_service = get_alert_service()
        alert_service.slack_service.client = mock_slack_client
        alert_service.slack_service.enabled = True
        
        with (
            E2ETestUtils.create_llm_patch_context(streaming_mock=streaming_mock),
            E2ETestUtils.setup_runbook_service_patching(),
        ):
                print("📤 Submitting alert without fingerprint...")
                response = e2e_test_client.post(
                    "/api/v1/alerts",
                    json=slack_alert_without_fingerprint
                )
                
                assert response.status_code == 200
                session_id = response.json()["session_id"]
                print(f"✅ Alert submitted, session_id: {session_id}")
                
                # Wait for completion
                print("⏳ Waiting for processing...")
                session, final_status = await E2ETestUtils.wait_for_session_completion(
                    e2e_test_client, 
                    max_wait_seconds=30,
                )

                assert session == session_id and final_status == "completed"
                print(f"✅ Session completed: {final_status}")

                # Verify Slack API calls
                print(f"📊 Total Slack calls: {len(slack_calls)}")

                # Should have exactly 1 call (completion only, no started notification without fingerprint):
                # 1. chat_postMessage (completion notification)
                assert len(slack_calls) == 1, f"Expected exactly 1 Slack call, got {len(slack_calls)}"
                
                # Verify direct channel posting
                post_calls = [c for c in slack_calls if c["method"] == "chat_postMessage"]
                assert len(post_calls) == 1, f"Expected exactly 1 completion notification, got {len(post_calls)}"

                # Verify conversations_history was not called
                conversations_history_calls = [c for c in slack_calls if c["method"] == "conversations_history"]
                assert len(conversations_history_calls) == 0, f"Expected exactly 0 conversations_history calls, got {len(conversations_history_calls)}"
                
                # Verify NO thread_ts in any calls (direct posting)
                for call in post_calls:
                    assert "thread_ts" not in call["kwargs"], "Direct posting should not use thread_ts"
                
                print("✅ Completion notification posted directly to channel (no threading)")


@pytest.mark.asyncio
@pytest.mark.e2e
class TestSlackThreadedNotificationFailed:
    """Test Slack threaded notification with failed session."""

    async def test_slack_threaded_notification_with_failed_session(
        self, 
        e2e_test_client,
        mock_slack_service,
        slack_alert_with_fingerprint
    ):
        """
        Test Slack threaded notification with failed session.
        
        Verifies:
        1. Started notification sent to Slack thread
        2. Alert processing fails (simulated LLM error)
        3. Error notification sent to Slack thread with 'danger' color
        """
        print("🚀 Testing Slack error notification...")
        
        # Use the mock Slack client from fixture
        mock_slack_client = mock_slack_service
        
        # Configure mock responses for this test
        mock_slack_client.conversations_history = AsyncMock(return_value={
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "text": "Pod api-server-abc123 is crash-looping - incident-12345",
                    "attachments": []
                }
            ]
        })
        mock_slack_client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "1234567891.123457"})
        
        slack_calls = []
        track_slack_call = create_slack_call_tracker(mock_slack_client, slack_calls)
        track_slack_call("conversations_history")
        track_slack_call("chat_postMessage")
        
        # Mock LLM to raise an error
        async def mock_astream_failing(*_args, **_kwargs):
            raise Exception("LLM API connection failed - simulated error")
        
        streaming_mock = mock_astream_failing
        
        # Inject mock Slack client into the app's SlackService
        alert_service = get_alert_service()
        alert_service.slack_service.client = mock_slack_client
        alert_service.slack_service.enabled = True
        
        with (
            E2ETestUtils.create_llm_patch_context(streaming_mock=streaming_mock),
            E2ETestUtils.setup_runbook_service_patching(),
        ):
                print("📤 Submitting alert (will fail)...")
                response = e2e_test_client.post(
                    "/api/v1/alerts",
                    json=slack_alert_with_fingerprint
                )
                
                assert response.status_code == 200
                session_id = response.json()["session_id"]
                
                # Wait for failure
                print("⏳ Waiting for processing to fail...")
                session, final_status = await E2ETestUtils.wait_for_session_completion(
                    e2e_test_client, 
                    max_wait_seconds=30,
                )
                
                assert session == session_id and final_status == "failed"
                print("✅ Session failed as expected")
                
                # Verify Slack API calls
                print(f"📊 Total Slack calls: {len(slack_calls)}")

                # Should have exactly 4 calls (started + error):
                # 1. conversations_history (find message for started notification)
                # 2. chat_postMessage (started notification)
                # 3. conversations_history (find message for error notification)
                # 4. chat_postMessage (error notification)
                # Verify error notification sent

                post_calls = [c for c in slack_calls if c["method"] == "chat_postMessage"]
                assert len(post_calls) == 2, "Expected exactly 2 error notifications"
                
                # Find error notification (last post call)
                error_call = post_calls[-1]
                attachments = error_call["kwargs"].get("attachments", [])
                assert len(attachments) > 0, "No attachments in error notification"
                assert attachments[0]["color"] == "danger", "Error should use 'danger' color"
                
                error_text = attachments[0].get("text", "")
                assert "Error" in error_text or "failed" in error_text.lower(), "Error message should mention failure"
                print("✅ Error notification sent with correct formatting")

@pytest.mark.asyncio
@pytest.mark.e2e
class TestSlackDirectChannelNotificationFailed:
    """Test Slack direct channel notification with failed session."""

    async def test_slack_direct_channel_notification_with_failed_session(
        self, 
        e2e_test_client,
        mock_slack_service,
        slack_alert_without_fingerprint
    ):
        """
        Test Slack direct channel notification with failed session.
        
        Verifies:
        1. No started notification (direct posting, no fingerprint)
        2. Alert processing fails (simulated LLM error)
        3. Error notification sent directly to channel (no threading)
        4. Error notification has 'danger' color
        """
        print("🚀 Testing Slack direct channel error notification...")
        
        # Use the mock Slack client from fixture
        mock_slack_client = mock_slack_service
        
        # Configure mock for direct messages (no threading)
        mock_slack_client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "1234567891.123457"})
        
        slack_calls = []
        track_slack_call = create_slack_call_tracker(mock_slack_client, slack_calls)
        track_slack_call("conversations_history")
        track_slack_call("chat_postMessage")
        
        # Mock LLM to raise an error
        async def mock_astream_failing(*_args, **_kwargs):
            raise Exception("LLM API connection failed - simulated error")
        
        streaming_mock = mock_astream_failing
        
        # Inject mock Slack client into the app's SlackService
        alert_service = get_alert_service()
        alert_service.slack_service.client = mock_slack_client
        alert_service.slack_service.enabled = True
        
        with (
            E2ETestUtils.create_llm_patch_context(streaming_mock=streaming_mock),
            E2ETestUtils.setup_runbook_service_patching(),
        ):
                print("📤 Submitting alert (will fail)...")
                response = e2e_test_client.post(
                    "/api/v1/alerts",
                    json=slack_alert_without_fingerprint
                )
                
                assert response.status_code == 200
                session_id = response.json()["session_id"]
                
                # Wait for failure
                print("⏳ Waiting for processing to fail...")
                session, final_status = await E2ETestUtils.wait_for_session_completion(
                    e2e_test_client, 
                    max_wait_seconds=30,
                )
                
                assert session == session_id and final_status == "failed"
                print("✅ Session failed as expected")
                
                # Verify Slack API calls
                print(f"📊 Total Slack calls: {len(slack_calls)}")

                # Should have exactly 1 call (error only, no started notification):
                # 1. chat_postMessage (error notification)
                
                post_calls = [c for c in slack_calls if c["method"] == "chat_postMessage"]
                assert len(post_calls) == 1, f"Expected exactly 1 error notification (no started for direct), got {len(post_calls)}"
                
                # Verify no conversations_history was called (no threading)
                history_calls = [c for c in slack_calls if c["method"] == "conversations_history"]
                assert len(history_calls) == 0, "Expected 0 history calls for direct posting"
                
                # Verify error notification is direct (no thread_ts)
                error_call = post_calls[0]
                assert "thread_ts" not in error_call["kwargs"], "Direct posting should not use thread_ts"
                
                # Verify error formatting
                attachments = error_call["kwargs"].get("attachments", [])
                assert len(attachments) > 0, "No attachments in error notification"
                assert attachments[0]["color"] == "danger", "Error should use 'danger' color"
                
                error_text = attachments[0].get("text", "")
                assert "Error" in error_text or "failed" in error_text.lower(), "Error message should mention failure"
                print("✅ Error notification sent directly to channel with correct formatting")

@pytest.mark.asyncio
@pytest.mark.e2e
class TestSlackThreadedNotificationPaused:
    """Test Slack threaded notification with paused session."""

    async def test_slack_threaded_notification_with_paused_session(
        self, 
        e2e_test_client,
        mock_slack_service,
        slack_alert_with_fingerprint
    ):
        """
        Test Slack notification when alert processing pauses.
        
        Verifies:
        1. Started notification sent
        2. Processing pauses (max iterations reached)
        3. Paused notification sent with 'warning' color
        4. Resume works and sends completion notification
        """
        print("🚀 Testing Slack paused notification...")
        
        # Use the mock Slack client from fixture
        mock_slack_client = mock_slack_service
        
        # Configure mock responses for this test
        mock_slack_client.conversations_history = AsyncMock(return_value={
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "text": "Pod api-server-abc123 is crash-looping - incident-12345",
                    "attachments": []
                }
            ]
        })
        mock_slack_client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "1234567891.123457"})
        
        slack_calls = []
        track_slack_call = create_slack_call_tracker(mock_slack_client, slack_calls)
        track_slack_call("conversations_history")
        track_slack_call("chat_postMessage")
        
        # Create alert with max_iterations=1 to trigger pause
        paused_alert = slack_alert_with_fingerprint.copy()
        
        # Mock LLM to not provide Final Answer (triggers iteration)
        call_count = [0]
        
        async def mock_astream_iterating(*_args, **_kwargs):
            call_count[0] += 1
            
            if call_count[0] == 1:
                # First iteration - no Final Answer
                response = """Thought: Let me investigate further.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "namespace": "production"}"""
            else:
                # Second iteration - provide answer
                response = """Final Answer: Investigation complete. Pod issue identified and resolved."""
            
            usage = {
                "input_tokens": 150,
                "output_tokens": 80,
                "total_tokens": 230
            }
            async for chunk in create_mock_stream(response, usage_metadata=usage):
                yield chunk
        
        streaming_mock = mock_astream_iterating
        
        # Override max_iterations to 1 for quick pause
        from tarsy.config.settings import get_settings
        settings = get_settings()
        original_max_iterations = settings.max_llm_mcp_iterations
        original_force_conclusion = settings.force_conclusion_at_max_iterations
        
        settings.max_llm_mcp_iterations = 1
        settings.force_conclusion_at_max_iterations = False
        print(f"🔧 Set max_llm_mcp_iterations to 1 (was {original_max_iterations})")
        
        try:
            # Inject mock Slack client into the app's SlackService
            alert_service = get_alert_service()
            alert_service.slack_service.client = mock_slack_client
            alert_service.slack_service.enabled = True
            
            with (
                E2ETestUtils.create_llm_patch_context(streaming_mock=streaming_mock),
                E2ETestUtils.setup_runbook_service_patching(),
            ):
                print("📤 Submitting alert (will pause)...")
                response = e2e_test_client.post(
                    "/api/v1/alerts",
                    json=paused_alert
                )
                
                assert response.status_code == 200
                session_id = response.json()["session_id"]
                
                # Wait for pause
                print("⏳ Waiting for processing to pause...")
                session, final_status = await E2ETestUtils.wait_for_session_completion(
                    e2e_test_client, 
                    max_wait_seconds=30,
                )
                
                assert session == session_id and final_status == "paused"
                print("✅ Session paused as expected")
                
                # Verify paused notifications
                post_calls = [c for c in slack_calls if c["method"] == "chat_postMessage"]
                assert len(post_calls) == 3, f"Expected started + stage paused + session paused notifications, got {len(post_calls)}"
                
                # Verify the notifications are correct
                started_calls = [c for c in post_calls if "Processing alert started" in str(c)]
                stage_paused_calls = [c for c in post_calls if "paused after" in str(c) and "iterations" in str(c)]
                session_paused_calls = [c for c in post_calls if "Session paused - waiting for user" in str(c)]

                assert len(started_calls) == 1, "Expected 1 started notification"
                assert len(stage_paused_calls) == 1, "Expected 1 stage-level paused notification"
                assert len(session_paused_calls) == 1, "Expected 1 session-level paused notification"

                # Verify the last pause notification has warning color
                pause_call = post_calls[-1]
                attachments = pause_call["kwargs"].get("attachments", [])
                assert len(attachments) > 0, "No attachments in pause notification"
                assert attachments[0]["color"] == "warning", "Pause should use 'warning' color"
                print("✅ Paused notifications sent with correct formatting")

                # Resume session
                print("🔄 Resuming session...")
                slack_calls.clear()  # Clear to track resume notifications separately
                
                resume_response = e2e_test_client.post(
                    f"/api/v1/history/sessions/{session_id}/resume"
                )
                assert resume_response.status_code == 200
                
                # Wait for completion after resume
                print("⏳ Waiting for completion after resume...")
                session, final_status = await E2ETestUtils.wait_for_session_completion(
                    e2e_test_client, 
                    max_wait_seconds=30,
                )
                
                assert session == session_id and final_status == "completed"
                print("✅ Session completed after resume")
                
                # Verify completion notification after resume
                post_calls_after_resume = [c for c in slack_calls if c["method"] == "chat_postMessage"]
                assert len(post_calls_after_resume) == 1, "Expected completion notification after resume"
                print("✅ Completion notification sent after resume")
        finally:
                # Restore original settings
                settings.max_llm_mcp_iterations = original_max_iterations
                settings.force_conclusion_at_max_iterations = original_force_conclusion


@pytest.mark.asyncio
@pytest.mark.e2e
class TestSlackDirectedNotificationPaused:
    """Test Slack directed notification with paused session."""

    async def test_slack_directed_notification_with_paused_session(
        self, 
        e2e_test_client,
        mock_slack_service,
        slack_alert_without_fingerprint
    ):
        """
        Test Slack directed notification when alert processing pauses.
        
        Verifies:
        1. No started notification (direct posting, no fingerprint)
        2. Processing pauses (max iterations reached)
        3. Paused notification sent with 'warning' color
        4. Resume works and sends completion notification
        5. All notifications are direct messages (not threaded)
        """
        print("🚀 Testing Slack directed paused notification...")
        
        # Use the mock Slack client from fixture
        mock_slack_client = mock_slack_service
        
        # Configure mock for directed messages (no existing thread)
        mock_slack_client.conversations_history = AsyncMock(return_value={
            "messages": []  # No existing messages - will send as new message
        })
        mock_slack_client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "1234567890.123456"})
        
        slack_calls = []
        track_slack_call = create_slack_call_tracker(mock_slack_client, slack_calls)
        track_slack_call("conversations_history")
        track_slack_call("chat_postMessage")
        
        # Create alert with max_iterations=1 to trigger pause
        paused_alert = slack_alert_without_fingerprint.copy()
        
        # Mock LLM to not provide Final Answer (triggers iteration)
        call_count = [0]
        
        async def mock_astream_iterating(*_args, **_kwargs):
            call_count[0] += 1
            
            if call_count[0] == 1:
                # First iteration - no Final Answer
                response = """Thought: Let me investigate further.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "namespace": "production"}"""
            else:
                # Second iteration - provide answer
                response = """Final Answer: Investigation complete. Pod issue identified and resolved."""
            
            usage = {
                "input_tokens": 150,
                "output_tokens": 80,
                "total_tokens": 230
            }
            async for chunk in create_mock_stream(response, usage_metadata=usage):
                yield chunk
        
        streaming_mock = mock_astream_iterating
        
        # Override max_iterations to 1 for quick pause
        from tarsy.config.settings import get_settings
        settings = get_settings()
        original_max_iterations = settings.max_llm_mcp_iterations
        original_force_conclusion = settings.force_conclusion_at_max_iterations
        
        settings.max_llm_mcp_iterations = 1
        settings.force_conclusion_at_max_iterations = False
        print(f"🔧 Set max_llm_mcp_iterations to 1 (was {original_max_iterations})")
        
        try:
            # Inject mock Slack client into the app's SlackService
            alert_service = get_alert_service()
            alert_service.slack_service.client = mock_slack_client
            alert_service.slack_service.enabled = True
            
            with (
                E2ETestUtils.create_llm_patch_context(streaming_mock=streaming_mock),
                E2ETestUtils.setup_runbook_service_patching(),
            ):
                print("📤 Submitting alert (will pause)...")
                response = e2e_test_client.post(
                    "/api/v1/alerts",
                    json=paused_alert
                )
                
                assert response.status_code == 200
                session_id = response.json()["session_id"]
                
                # Wait for pause
                print("⏳ Waiting for processing to pause...")
                session, final_status = await E2ETestUtils.wait_for_session_completion(
                    e2e_test_client, 
                    max_wait_seconds=30,
                )
                
                assert session == session_id and final_status == "paused"
                print("✅ Session paused as expected")
                
                # Verify directed notifications (no thread_ts)
                post_calls = [c for c in slack_calls if c["method"] == "chat_postMessage"]
                assert len(post_calls) == 2, f"Expected 2 paused notifications (stage + session, no started for direct posting), got {len(post_calls)}"

                # Verify all calls are directed (not threaded)
                for call in post_calls:
                    assert "thread_ts" not in call["kwargs"], "Directed notifications should not have thread_ts"

                # Verify both are pause notifications (no started)
                stage_paused_calls = [c for c in post_calls if "paused after" in str(c) and "iterations" in str(c)]
                session_paused_calls = [c for c in post_calls if "Session paused - waiting for user" in str(c)]

                assert len(stage_paused_calls) == 1, "Expected 1 stage-level paused notification"
                assert len(session_paused_calls) == 1, "Expected 1 session-level paused notification"

                # Verify both pause notifications have warning color
                for pause_call in post_calls:
                    attachments = pause_call["kwargs"].get("attachments", [])
                    assert len(attachments) > 0, "No attachments in pause notification"
                    assert attachments[0]["color"] == "warning", "Pause should use 'warning' color"
                print("✅ All pause notifications sent with correct formatting")

                # Resume session
                print("🔄 Resuming session...")
                slack_calls.clear()  # Clear to track resume notifications separately
                
                resume_response = e2e_test_client.post(
                    f"/api/v1/history/sessions/{session_id}/resume"
                )
                assert resume_response.status_code == 200
                
                # Wait for completion after resume
                print("⏳ Waiting for completion after resume...")
                session, final_status = await E2ETestUtils.wait_for_session_completion(
                    e2e_test_client, 
                    max_wait_seconds=30,
                )
                
                assert session == session_id and final_status == "completed"
                print("✅ Session completed after resume")
                
                # Verify completion notification after resume
                post_calls_after_resume = [c for c in slack_calls if c["method"] == "chat_postMessage"]
                assert len(post_calls_after_resume) == 1, "Expected completion notification after resume"
                
                # Verify completion is also directed (not threaded)
                for call in post_calls_after_resume:
                    assert "thread_ts" not in call["kwargs"], "Completion notification should also be directed"
                print("✅ Completion notification sent as directed message after resume")
        finally:
            # Restore original settings
            settings.max_llm_mcp_iterations = original_max_iterations
            settings.force_conclusion_at_max_iterations = original_force_conclusion


@pytest.mark.asyncio
@pytest.mark.e2e
class TestSlackThreadedNotificationMessageNotFound:
    """Test Slack threaded notification when message fingerprint is not found."""

    async def test_slack_threaded_notification_with_message_not_found(
        self, 
        e2e_test_client,
        mock_slack_service,
        slack_alert_with_fingerprint
    ):
        """
        Test fallback behavior when Slack threaded notification message fingerprint is not found.
        
        Verifies:
        1. Slack searches for message but doesn't find it
        2. Processing continues normally
        3. No error thrown, just logged
        """
        print("🚀 Testing Slack message not found fallback...")
        
        # Use the mock Slack client from fixture
        mock_slack_client = mock_slack_service
        
        # Configure mock to return no matching messages
        mock_slack_client.conversations_history = AsyncMock(return_value={
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "text": "Some completely different message",
                    "user": "U123456",
                    "attachments": []
                }
            ]
        })
        mock_slack_client.chat_postMessage = AsyncMock(return_value={"ok": True, "ts": "1234567891.123457"})
        
        slack_calls = []
        track_slack_call = create_slack_call_tracker(mock_slack_client, slack_calls)
        
        track_slack_call("conversations_history")
        track_slack_call("chat_postMessage")
        
        # Mock LLM streaming at LangChain level
        async def mock_astream(*_args, **_kwargs):
            """Mock astream that returns a simple successful response."""
            response = """Final Answer: Analysis complete."""
            usage = {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150
            }
            async for chunk in create_mock_stream(response, usage_metadata=usage):
                yield chunk
        
        streaming_mock = mock_astream
        
        # Inject mock Slack client into the app's SlackService
        alert_service = get_alert_service()
        alert_service.slack_service.client = mock_slack_client
        alert_service.slack_service.enabled = True
        
        with (
            E2ETestUtils.create_llm_patch_context(streaming_mock=streaming_mock),
            E2ETestUtils.setup_runbook_service_patching(),
        ):
                print("📤 Submitting alert with non-matching fingerprint...")
                response = e2e_test_client.post(
                    "/api/v1/alerts",
                    json=slack_alert_with_fingerprint
                )
                
                assert response.status_code == 200
                session_id = response.json()["session_id"]
                
                # Wait for completion
                print("⏳ Waiting for processing...")
                session, final_status = await E2ETestUtils.wait_for_session_completion(
                        e2e_test_client, 
                        max_wait_seconds=30,
                )
                
                assert session == session_id and final_status == "completed"
                print("✅ Session completed despite message not found")
                
                # Verify history was searched exactly twice (started + completion notifications)
                # Each notification independently attempts to find the message, both fail gracefully
                history_calls = [c for c in slack_calls if c["method"] == "conversations_history"]
                assert len(history_calls) == 2, f"Expected exactly 2 history searches (started + completion), got {len(history_calls)}"
                print(f"✅ Searched for message {len(history_calls)} times (both failed, no posts made)")
                
                # Verify no postMessage calls (message not found, can't thread)
                post_calls = [c for c in slack_calls if c["method"] == "chat_postMessage"]
                assert len(post_calls) == 0, "Should not post when message not found"
                print("✅ Gracefully handled message not found scenario (no posts)")


@pytest.mark.asyncio
@pytest.mark.e2e
class TestSlackApiErrorResilience:
    """Test that Slack API errors don't fail alert processing."""

    async def test_slack_api_error_does_not_fail_processing(
        self, 
        e2e_test_client,
        mock_slack_service,
        slack_alert_with_fingerprint
    ):
        """
        Test that Slack API errors don't fail the alert processing.
        
        Verifies:
        1. Slack API raises an error
        2. Error is logged but processing continues
        3. Session completes successfully despite Slack failure
        """
        print("🚀 Testing Slack API error resilience...")
        
        # Use the mock Slack client from fixture
        mock_slack_client = mock_slack_service
        
        # Track Slack API calls and failures
        slack_call_attempts = []
        slack_errors = []
        
        # Mock Slack API to raise an error
        async def failing_post_message(*args, **kwargs):
            slack_call_attempts.append({
                "method": "chat_postMessage",
                "args": args,
                "kwargs": kwargs
            })
            error = SlackApiError("API error", response={"error": "channel_not_found"})
            slack_errors.append(error)
            raise error
        
        # Configure mocks for this test
        mock_slack_client.conversations_history = AsyncMock(return_value={
            "messages": [
                {
                    "ts": "1234567890.123456",
                    "text": "Pod api-server-abc123 is crash-looping - incident-12345",
                    "user": "U123456",
                    "attachments": []
                }
            ]
        })
        mock_slack_client.chat_postMessage = failing_post_message
        
        # Mock LLM streaming at LangChain level
        async def mock_astream(*_args, **_kwargs):
            """Mock astream that returns a simple successful response."""
            response = """Final Answer: Analysis complete."""
            usage = {
                "input_tokens": 100,
                "output_tokens": 50,
                "total_tokens": 150
            }
            async for chunk in create_mock_stream(response, usage_metadata=usage):
                yield chunk
        
        streaming_mock = mock_astream
        
        # Inject mock Slack client into the app's SlackService
        alert_service = get_alert_service()
        alert_service.slack_service.client = mock_slack_client
        alert_service.slack_service.enabled = True
        
        with (
            E2ETestUtils.create_llm_patch_context(streaming_mock=streaming_mock),
            E2ETestUtils.setup_runbook_service_patching(),
        ):
                print("📤 Submitting alert (Slack will fail)...")
                response = e2e_test_client.post(
                    "/api/v1/alerts",
                    json=slack_alert_with_fingerprint
                )
                
                assert response.status_code == 200
                session_id = response.json()["session_id"]
                
                # Wait for completion
                print("⏳ Waiting for processing...")
                session, final_status = await E2ETestUtils.wait_for_session_completion(
                        e2e_test_client, 
                        max_wait_seconds=30,
                )
                
                # Verify Slack was actually called and failed
                assert len(slack_call_attempts) == 2, f"Expected 2 Slack API calls (started + completion), got {len(slack_call_attempts)}"
                assert len(slack_errors) == 2, f"Expected 2 Slack API errors (started + completion), got {len(slack_errors)}"
                print(f"✅ Slack API was called {len(slack_call_attempts)} time(s) and failed as expected")
                
                # Processing should complete despite Slack failure
                assert session == session_id and final_status == "completed"
                print("✅ Session completed despite Slack API error")
                print("✅ Alert processing is resilient to Slack failures")
