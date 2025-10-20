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
from .e2e_utils import E2ETestUtils


class MockChunk:
    """Mock chunk for streaming responses."""
    
    def __init__(self, content: str = "", usage_metadata: dict | None = None):
        self.content = content
        self.usage_metadata = usage_metadata
    
    def __add__(self, other):
        """Support chunk aggregation (chunk1 + chunk2)."""
        if other is None:
            return self
        
        # Aggregate content
        new_content = self.content + (other.content if hasattr(other, 'content') else "")
        
        # Aggregate usage_metadata (prefer non-None, or merge if both exist)
        new_usage = self.usage_metadata or (other.usage_metadata if hasattr(other, 'usage_metadata') else None)
        if self.usage_metadata and hasattr(other, 'usage_metadata') and other.usage_metadata:
            # Both have usage metadata - merge them
            new_usage = {
                'input_tokens': self.usage_metadata.get('input_tokens', 0) + other.usage_metadata.get('input_tokens', 0),
                'output_tokens': self.usage_metadata.get('output_tokens', 0) + other.usage_metadata.get('output_tokens', 0),
                'total_tokens': self.usage_metadata.get('total_tokens', 0) + other.usage_metadata.get('total_tokens', 0),
            }
        
        return MockChunk(content=new_content, usage_metadata=new_usage)
    
    def __radd__(self, other):
        """Support reverse addition (None + chunk)."""
        if other is None:
            return self
        return self.__add__(other)


async def create_mock_stream(content: str, usage_metadata: dict | None = None):
    """Create an async generator that yields mock chunks with usage metadata in final chunk."""
    # Yield content character by character
    for i, char in enumerate(content):
        # Add usage_metadata only to the final chunk
        is_final = (i == len(content) - 1)
        yield MockChunk(char, usage_metadata=usage_metadata if is_final else None)


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

                # First 50 interactions: ALL FAIL (ensures first stage fails)
                # This accounts for LLM retries (up to 4-5 retries per iteration * 10 max iterations = 50 interactions)
                # We need to be absolutely sure we exhaust all 10 iterations with failed last interaction
                if total_interactions <= 50:
                    print(f"  ❌ FAILING LLM interaction #{total_interactions} (first stage)")
                    # Raise an exception to simulate LLM failure
                    raise Exception("Invalid request - simulated failure")

                # Later interactions (51+, stages 2, 3, etc.): SUCCEED
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
            from langchain_openai import ChatOpenAI
            from langchain_anthropic import ChatAnthropic
            from langchain_xai import ChatXAI
            from langchain_google_genai import ChatGoogleGenerativeAI
            
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
                    # Extended timeout for failure detection with retries (10 iterations * up to 4 seconds each = 40+ seconds)
                    session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                        e2e_test_client, max_wait_seconds=500, debug_logging=True
                    )

                    print("🔍 Step 3: Verifying failure detection results...")

                    # Verify session failed due to stage failure
                    assert session_id is not None, "Session ID missing"
                    assert final_status == "failed", f"Expected session to be 'failed', but got: {final_status}"
                    print(f"✅ Session correctly marked as FAILED: {session_id}")

                    # Get session details with retry logic for robustness
                    detail_data = E2ETestUtils.get_session_details(e2e_test_client, session_id, max_retries=5)
                    stages = detail_data.get("stages", [])
                    assert len(stages) == 3, f"Expected 3 stages, got {len(stages)}"

                    # Verify the created stage(s) failed with appropriate error messages
                    for stage in stages:
                        assert stage["status"] == "failed", f"Expected stage '{stage['stage_name']}' to be 'failed', got: {stage['status']}"
                        stage_error = stage.get("error_message", "")
                        # Verify that stages failed due to our new logic (either max iterations or LLM failure)
                        assert any(keyword in stage_error for keyword in ["reached maximum iterations", "failed", "error"]), f"Expected stage error to indicate failure, got: {stage_error}"
                        print(f"✅ Stage '{stage['stage_name']}' correctly marked as FAILED: {stage_error[:100]}...")

                    print(f"✅ NEW FAILURE DETECTION TEST PASSED!")
                    print(f"   📊 Summary: {len(stages)} stage(s) created and properly failed, Session=FAILED")

                    return
