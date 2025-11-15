"""
E2E Test for Pause/Resume Functionality.

This test verifies the complete pause/resume workflow:
1. Submit alert with low max_iterations
2. Wait for session to pause (max iterations reached)
3. Resume the paused session
4. Wait for session to complete (or pause again)

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: HTTP requests to LLM APIs, MCP servers, GitHub runbooks
- CONFIGURED: max_llm_mcp_iterations set to 2 for quick pause
"""

import asyncio
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.config.builtin_config import BUILTIN_MCP_SERVERS
from tarsy.integrations.mcp.client import MCPClient
from mcp.types import Tool

from .e2e_utils import E2ETestUtils
from .conftest import create_mock_stream

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestPauseResumeE2E:
    """
    E2E test for pause/resume functionality.

    Tests the complete system flow:
    1. HTTP POST to /api/v1/alerts endpoint with low max_iterations
    2. Real alert processing through AlertService
    3. Session pauses when max_iterations is reached
    4. HTTP POST to /api/v1/sessions/{session_id}/resume endpoint
    5. Session resumes and continues processing
    6. Verification of pause metadata and state transitions
    """

    @pytest.mark.e2e
    async def test_pause_and_resume_workflow(
        self, e2e_test_client, e2e_realistic_kubernetes_alert
    ):
        """
        Test complete pause and resume workflow.

        Flow:
        1. POST alert with max_iterations=2
        2. Wait for session to pause (max iterations reached)
        3. Verify pause metadata and state
        4. POST to resume endpoint
        5. Wait for session to complete or pause again
        6. Verify final state and audit trail
        """

        # Wrap entire test in timeout to prevent hanging
        async def run_test():
            print("🚀 Starting pause/resume e2e test...")
            result = await self._execute_test(
                e2e_test_client, e2e_realistic_kubernetes_alert
            )
            print("✅ Pause/resume e2e test completed!")
            return result

        try:
            task = asyncio.create_task(run_test())
            done, pending = await asyncio.wait({task}, timeout=120.0)

            if pending:
                for t in pending:
                    t.cancel()
                print("❌ TIMEOUT: Test exceeded 120 seconds!")
                raise AssertionError("Test exceeded timeout of 120 seconds")
            else:
                return task.result()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            raise

    async def _execute_test(self, e2e_test_client, e2e_realistic_kubernetes_alert):
        """Execute the pause/resume test with mocked external dependencies."""
        print("🔧 _execute_test started")

        # Override max_iterations to 2 for quick pause
        from tarsy.config.settings import get_settings
        settings = get_settings()
        original_max_iterations = settings.max_llm_mcp_iterations
        settings.max_llm_mcp_iterations = 2
        print(f"🔧 Overrode max_llm_mcp_iterations from {original_max_iterations} to 2")

        # Track all LLM interactions
        all_llm_interactions = []

        # Define mock response map for LLM interactions
        # Each interaction gets a mock response to simulate ReAct pattern
        # We'll set max_iterations=2, so we expect:
        # - Interaction 1: Initial thought + action (will succeed)
        # - Interaction 2: After tool result, should trigger pause
        # - After resume:
        # - Interaction 3: Continue analysis
        # - Interaction 4: Final answer
        mock_response_map = {
            1: {  # First iteration - initial analysis
                "response_content": """Thought: I need to get namespace information to understand the issue.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}""",
                "input_tokens": 200,
                "output_tokens": 80,
                "total_tokens": 280,
            },
            2: {  # Second iteration - will trigger pause
                "response_content": """Thought: I see the namespace is in Terminating state. I need more information to continue the analysis, but I've reached the iteration limit.
Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "namespace", "name": "stuck-namespace"}""",
                "input_tokens": 220,
                "output_tokens": 90,
                "total_tokens": 310,
            },
            3: {  # Third iteration - after resume
                "response_content": """Thought: Continuing my analysis after pause. The namespace is stuck due to finalizers.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "events", "namespace": "stuck-namespace"}""",
                "input_tokens": 240,
                "output_tokens": 85,
                "total_tokens": 325,
            },
            4: {  # Fourth iteration - final answer
                "response_content": """Final Answer: Analysis completed after resume. The namespace 'stuck-namespace' is stuck in Terminating state due to finalizers (kubernetes.io/pvc-protection) blocking deletion. To resolve: manually remove finalizers using kubectl patch.""",
                "input_tokens": 260,
                "output_tokens": 110,
                "total_tokens": 370,
            },
        }

        # Create streaming mock for LLM client
        def create_streaming_mock():
            """Create a mock astream function that returns streaming responses."""

            async def mock_astream(*args, **kwargs):
                interaction_num = len(all_llm_interactions) + 1
                all_llm_interactions.append(interaction_num)

                print(f"\n🔍 LLM REQUEST #{interaction_num}:")
                if args and len(args) > 0:
                    messages = args[0]
                    for i, msg in enumerate(messages):
                        role = getattr(msg, "type", "unknown") if hasattr(msg, "type") else "unknown"
                        content = getattr(msg, "content", "") if hasattr(msg, "content") else ""
                        print(f"  Message {i+1} ({role}): {content[:100]}...")

                # Get mock response for this interaction
                mock_response = mock_response_map.get(
                    interaction_num,
                    {"response_content": "", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                )

                content = mock_response["response_content"]
                usage_metadata = {
                    "input_tokens": mock_response["input_tokens"],
                    "output_tokens": mock_response["output_tokens"],
                    "total_tokens": mock_response["total_tokens"],
                }

                async for chunk in create_mock_stream(content, usage_metadata):
                    yield chunk

            return mock_astream

        # Create MCP session mock
        def create_mcp_session_mock():
            """Create a mock MCP session that provides kubectl tools."""
            mock_session = AsyncMock()

            async def mock_call_tool(tool_name, _parameters):
                mock_result = Mock()

                if tool_name == "kubectl_get":
                    resource = _parameters.get("resource", "pods")
                    name = _parameters.get("name", "")
                    namespace = _parameters.get("namespace", "")

                    if resource == "namespaces" and name == "stuck-namespace":
                        mock_content = Mock()
                        mock_content.text = "stuck-namespace   Terminating   45m"
                        mock_result.content = [mock_content]
                    elif resource == "events":
                        mock_content = Mock()
                        mock_content.text = "LAST SEEN   TYPE      REASON      OBJECT                MESSAGE\n5m          Warning   FailedDelete namespace/stuck-namespace   Finalizers blocking deletion"
                        mock_result.content = [mock_content]
                    else:
                        mock_content = Mock()
                        mock_content.text = f"Mock kubectl get {resource} response"
                        mock_result.content = [mock_content]

                elif tool_name == "kubectl_describe":
                    # Simulate a kubectl describe response
                    mock_content = Mock()
                    mock_content.text = """Name:         stuck-namespace
Status:       Terminating
Finalizers:   [kubernetes.io/pvc-protection]
"""
                    mock_result.content = [mock_content]
                else:
                    mock_content = Mock()
                    mock_content.text = f"Mock response for tool: {tool_name}"
                    mock_result.content = [mock_content]

                return mock_result

            async def mock_list_tools():
                mock_tool1 = Tool(
                    name="kubectl_get",
                    description="Get Kubernetes resources",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "resource": {"type": "string"},
                            "namespace": {"type": "string"},
                            "name": {"type": "string"},
                        },
                    },
                )

                mock_tool2 = Tool(
                    name="kubectl_describe",
                    description="Describe Kubernetes resources",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "resource": {"type": "string"},
                            "namespace": {"type": "string"},
                            "name": {"type": "string"},
                        },
                    },
                )

                mock_result = Mock()
                mock_result.tools = [mock_tool1, mock_tool2]
                return mock_result

            mock_session.call_tool.side_effect = mock_call_tool
            mock_session.list_tools.side_effect = mock_list_tools

            return mock_session

        # Create test MCP server configurations
        k8s_config = E2ETestUtils.create_simple_kubernetes_mcp_config(
            command_args=["kubernetes-mock-server-ready"],
            instructions="Test kubernetes server for pause/resume e2e testing",
        )

        test_mcp_servers = E2ETestUtils.create_test_mcp_servers(
            BUILTIN_MCP_SERVERS, {"kubernetes-server": k8s_config}
        )

        # Apply comprehensive mocking
        with patch("tarsy.config.builtin_config.BUILTIN_MCP_SERVERS", test_mcp_servers), \
             patch("tarsy.services.mcp_server_registry.MCPServerRegistry._DEFAULT_SERVERS", test_mcp_servers), \
             E2ETestUtils.setup_runbook_service_patching():

                # Mock LLM streaming
                streaming_mock = create_streaming_mock()

                from langchain_openai import ChatOpenAI
                from langchain_anthropic import ChatAnthropic
                from langchain_xai import ChatXAI
                from langchain_google_genai import ChatGoogleGenerativeAI

                with patch.object(ChatOpenAI, "astream", streaming_mock), \
                     patch.object(ChatAnthropic, "astream", streaming_mock), \
                     patch.object(ChatXAI, "astream", streaming_mock), \
                     patch.object(ChatGoogleGenerativeAI, "astream", streaming_mock):

                    # Mock MCP client
                    mock_kubernetes_session = create_mcp_session_mock()
                    mock_sessions = {"kubernetes-server": mock_kubernetes_session}
                    mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

                    async def mock_initialize(self):
                        """Mock initialization that sets up mock sessions."""
                        self.sessions = mock_sessions.copy()
                        self._initialized = True

                    with patch.object(MCPClient, "initialize", mock_initialize), \
                         patch.object(MCPClient, "list_tools", mock_list_tools), \
                         patch.object(MCPClient, "call_tool", mock_call_tool):

                        print("⏳ Step 1: Submitting alert with max_iterations=2...")
                        session_id = E2ETestUtils.submit_alert(
                            e2e_test_client, e2e_realistic_kubernetes_alert
                        )

                        print("⏳ Step 2: Waiting for session to pause...")
                        paused_session_id, paused_status = await E2ETestUtils.wait_for_session_completion(
                            e2e_test_client, max_wait_seconds=15, debug_logging=True
                        )

                        print("🔍 Step 3: Verifying pause state...")
                        assert paused_session_id == session_id, "Session ID mismatch"
                        assert paused_status == "paused", f"Expected status 'paused', got '{paused_status}'"
                        print(f"✅ Session paused: {session_id}")

                        # Get session details to verify pause metadata
                        detail_data = E2ETestUtils.get_session_details(e2e_test_client, session_id)
                        
                        # Verify pause metadata exists
                        pause_metadata = detail_data.get("pause_metadata")
                        assert pause_metadata is not None, "pause_metadata missing from paused session"
                        assert pause_metadata.get("reason") == "max_iterations_reached", \
                            f"Expected pause reason 'max_iterations_reached', got '{pause_metadata.get('reason')}'"
                        assert pause_metadata.get("current_iteration") == 2, \
                            f"Expected current_iteration=2, got {pause_metadata.get('current_iteration')}"
                        assert "message" in pause_metadata, "pause_metadata missing 'message' field"
                        assert "paused_at_us" in pause_metadata, "pause_metadata missing 'paused_at_us' field"
                        print(f"✅ Pause metadata verified: {pause_metadata}")

                        # Verify stages exist and last stage is paused
                        stages = detail_data.get("stages", [])
                        assert len(stages) > 0, "No stages found in paused session"
                        
                        # Find the paused stage
                        paused_stage = None
                        for stage in stages:
                            if stage.get("status") == "paused":
                                paused_stage = stage
                                break
                        
                        assert paused_stage is not None, "No paused stage found"
                        # Note: current_iteration is stored in DB but not exposed in API DetailedStage model
                        # The iteration information is available in pause_metadata at session level
                        print(f"✅ Paused stage verified: {paused_stage.get('stage_name')}")

                        print("⏳ Step 4: Resuming paused session...")
                        resume_response = e2e_test_client.post(
                            f"/api/v1/history/sessions/{session_id}/resume"
                        )
                        assert resume_response.status_code == 200, \
                            f"Resume failed with status {resume_response.status_code}: {resume_response.text}"
                        
                        resume_data = resume_response.json()
                        assert resume_data.get("success") is True, "Resume response indicates failure"
                        assert resume_data.get("status") == "resuming", \
                            f"Expected status 'resuming', got '{resume_data.get('status')}'"
                        print(f"✅ Resume initiated: {resume_data}")

                        print("⏳ Step 5: Waiting for resumed session to complete or pause again...")
                        # After resume, the session will continue and might pause again (since we still have max_iterations=2)
                        # or complete if we have enough iterations configured
                        final_session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                            e2e_test_client, max_wait_seconds=15, debug_logging=True
                        )

                        print("🔍 Step 6: Verifying final state...")
                        assert final_session_id == session_id, "Session ID mismatch after resume"
                        # Session might complete or pause again depending on the analysis
                        assert final_status in ["completed", "paused"], \
                            f"Expected final status 'completed' or 'paused', got '{final_status}'"
                        print(f"✅ Final status: {final_status}")

                        # Verify audit trail
                        final_detail_data = E2ETestUtils.get_session_details(e2e_test_client, session_id)
                        
                        # Verify session-level timestamps
                        assert final_detail_data.get("started_at_us") > 0, "started_at_us missing"
                        if final_status == "completed":
                            assert final_detail_data.get("completed_at_us") > 0, "completed_at_us missing"
                            assert final_detail_data.get("completed_at_us") > final_detail_data.get("started_at_us"), \
                                "completed_at_us should be after started_at_us"
                        
                        # Verify stages structure after resume
                        final_stages = final_detail_data.get("stages", [])
                        assert len(final_stages) > 0, "No stages found after resume"
                        
                        # Count how many times the stage was paused (should be at least 1)
                        # We should see evidence of pause in the stage history
                        print(f"✅ Session has {len(final_stages)} stage(s) after resume")

                        # Verify LLM interactions increased after resume
                        # Initially we had 2 interactions (before pause), after resume we should have more
                        total_llm_interactions = sum(
                            len(stage.get("llm_interactions", [])) for stage in final_stages
                        )
                        print(f"✅ Total LLM interactions: {total_llm_interactions}")
                        # We should have had at least 2 interactions before pause
                        # After resume, we might have 1-2 more interactions
                        assert total_llm_interactions >= 2, \
                            f"Expected at least 2 LLM interactions, got {total_llm_interactions}"

                        print("✅ PAUSE/RESUME E2E TEST PASSED!")
                        
                        # Restore original max_iterations
                        settings.max_llm_mcp_iterations = original_max_iterations
                        print(f"🔧 Restored max_llm_mcp_iterations to {original_max_iterations}")
                        return

