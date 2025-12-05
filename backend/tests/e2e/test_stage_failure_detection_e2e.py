"""
Test for stage failure detection end-to-end.

This test is separated from the main test file to avoid database isolation issues
that occur when running multiple e2e tests together.
"""

import os
from unittest.mock import patch

import pytest

from tarsy.config.builtin_config import BUILTIN_MCP_SERVERS
from tarsy.integrations.mcp.client import MCPClient

# MockChunk and create_mock_stream are provided by conftest.py
from .conftest import create_mock_stream
from .e2e_utils import E2ETestUtils


class TestStageFailureDetectionE2E:
    """Test stage failure detection in isolation."""

    @pytest.mark.e2e
    @pytest.mark.asyncio
    async def test_stage_failure_detection_e2e(
        self, e2e_test_client, e2e_realistic_kubernetes_alert
    ):
        """
        E2E test for new stage failure detection logic.

        Tests scenario where:
        - All stages: All LLM interactions fail -> All Stages FAILED
        - Session: FAILED (due to any stage failure)

        Verifies our new failure detection logic: max iterations + failed last interaction = stage failure.
        """
        print("🚀 Starting stage failure detection E2E test...")

        # Track LLM interactions to control failure behavior
        all_llm_interactions = []

        def create_failing_streaming_mock():
            """Create streaming mock that fails first 50 LLM calls, succeeds afterward."""
            
            async def mock_astream(*args, **kwargs):
                all_llm_interactions.append("interaction")
                total_interactions = len(all_llm_interactions)
                print(f"🔍 LLM REQUEST #{total_interactions}")

                # First 150 interactions: ALL FAIL (ensures first stage fails)
                # This accounts for LLM retries (up to 4-5 retries per iteration * 30 max iterations = 150 interactions)
                # We need to be absolutely sure we exhaust all 30 iterations with failed last interaction
                if total_interactions <= 150:
                    print(f"  ❌ FAILING LLM interaction #{total_interactions} (first stage)")
                    # Raise an exception to simulate LLM failure
                    raise Exception("Invalid request - simulated failure")

                # Later interactions (151+, stages 2, 3, etc.): SUCCEED
                else:
                    print(f"  ✅ SUCCESS LLM interaction #{total_interactions} (later stages)")
                    content = "Final Answer: Analysis completed successfully"
                    usage_metadata = {
                        'input_tokens': 30,
                        'output_tokens': 20,
                        'total_tokens': 50
                    }
                    # Use our mock stream generator
                    async for chunk in create_mock_stream(content, usage_metadata):
                        yield chunk
            
            return mock_astream



        # Create test MCP server config using shared utility
        k8s_config = E2ETestUtils.create_simple_kubernetes_mcp_config(
            command_args=["test"],
            instructions="Test server"
        )
        test_mcp_servers = E2ETestUtils.create_test_mcp_servers(BUILTIN_MCP_SERVERS, {
            "kubernetes-server": k8s_config
        })

        # Create mock session using shared utility
        mock_session = E2ETestUtils.create_generic_mcp_session_mock()

        # Apply mocking and run test
        # Patch both the original constant and the registry's stored reference
        with patch("tarsy.config.builtin_config.BUILTIN_MCP_SERVERS", test_mcp_servers), \
             patch("tarsy.services.mcp_server_registry.MCPServerRegistry._DEFAULT_SERVERS", test_mcp_servers), \
             patch.dict(os.environ, {}, clear=True), \
             E2ETestUtils.setup_runbook_service_patching(content="# Mock Runbook"):  # Patch runbook service
            
            # Mock LLM streaming with failure logic
            streaming_mock = create_failing_streaming_mock()
            
            # Import LangChain clients to patch
            from langchain_anthropic import ChatAnthropic
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_openai import ChatOpenAI
            from langchain_xai import ChatXAI
            
            # Patch the astream method on all LangChain client classes
            with patch.object(ChatOpenAI, 'astream', streaming_mock), \
                 patch.object(ChatAnthropic, 'astream', streaming_mock), \
                 patch.object(ChatXAI, 'astream', streaming_mock), \
                 patch.object(ChatGoogleGenerativeAI, 'astream', streaming_mock):

                # Create MCP client patches using shared utility
                mock_sessions = {"kubernetes-server": mock_session}
                mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

                # Create a mock initialize method that sets up mock sessions without real server processes
                async def mock_initialize(self):
                    """Mock initialization that bypasses real server startup."""
                    self.sessions = mock_sessions.copy()
                    self._initialized = True

                with patch.object(MCPClient, "initialize", mock_initialize), \
                     patch.object(MCPClient, "list_tools", mock_list_tools), \
                     patch.object(MCPClient, "call_tool", mock_call_tool):

                    print("⏳ Step 1: Submitting alert...")
                    E2ETestUtils.submit_alert(e2e_test_client, e2e_realistic_kubernetes_alert)

                    print("⏳ Step 2: Waiting for processing...")
                    # Extended timeout for failure detection with retries (30 iterations * up to 4 seconds each = 120+ seconds)
                    session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                        e2e_test_client, max_wait_seconds=500, debug_logging=True
                    )

                    print("🔍 Step 3: Verifying failure detection results...")

                    # Verify session failed due to stage failure
                    assert session_id is not None, "Session ID missing"
                    assert final_status == "failed", f"Expected session to be 'failed', but got: {final_status}"
                    print(f"✅ Session correctly marked as FAILED: {session_id}")

                    # Get session details with retry logic for robustness
                    detail_data = await E2ETestUtils.get_session_details_async(e2e_test_client, session_id, max_retries=5)
                    stages = detail_data.get("stages", [])
                    assert len(stages) == 3, f"Expected 3 stages, got {len(stages)}"

                    # Verify the created stage(s) failed with appropriate error messages
                    for stage in stages:
                        assert stage["status"] == "failed", f"Expected stage '{stage['stage_name']}' to be 'failed', got: {stage['status']}"
                        stage_error = stage.get("error_message", "")
                        # Verify that stages failed due to our new logic (either max iterations or LLM failure)
                        assert any(keyword in stage_error for keyword in ["reached maximum iterations", "failed", "error"]), f"Expected stage error to indicate failure, got: {stage_error}"
                        print(f"✅ Stage '{stage['stage_name']}' correctly marked as FAILED: {stage_error[:100]}...")

                    print("✅ NEW FAILURE DETECTION TEST PASSED!")
                    print(f"   📊 Summary: {len(stages)} stage(s) created and properly failed, Session=FAILED")

                    return
