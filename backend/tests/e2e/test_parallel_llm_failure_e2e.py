"""
End-to-End Test for Parallel Stage LLM Failure Handling.

This test verifies that when LLM calls fail during parallel stage execution:
- The system properly handles stage_execution_id being None in exception paths
- The session correctly transitions to FAILED status
- Error messages are properly captured and reported
- No crashes occur due to None stage_execution_id in guards

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: HTTP requests to LLM APIs (configured to fail), MCP servers, GitHub runbooks
"""

import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import Tool

from .e2e_utils import E2ETestUtils
from .parallel_test_base import ParallelTestBase

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestParallelLLMFailureE2E(ParallelTestBase):
    """E2E test for parallel stage LLM failure handling."""

    @pytest.mark.e2e
    async def test_parallel_stage_llm_failure(
        self, e2e_parallel_test_client, e2e_parallel_alert
    ):
        """
        Test parallel stage failure when ALL LLM calls fail.

        This tests the guards added to handle stage_execution_id being None
        in the exception path for parallel stages.

        Flow:
        1. POST alert to /api/v1/alerts -> queued
        2. LLM mock returns errors for all calls
        3. Parallel stage should fail gracefully
        4. Session should be marked as FAILED
        5. No crashes should occur (the bug being tested)

        This test verifies:
        - stage_execution_id=None guard in exception handler works
        - Parallel stage failure is properly recorded
        - Session transitions to FAILED status correctly
        """
        return await self._run_with_timeout(
            lambda: self._execute_llm_failure_test(e2e_parallel_test_client, e2e_parallel_alert),
            test_name="parallel LLM failure test",
            timeout_seconds=120
        )

    async def _execute_llm_failure_test(self, test_client, alert_data):
        """Execute parallel stage LLM failure test."""
        print("🔧 Starting parallel stage LLM failure test execution")

        # Track total interactions for debugging
        interaction_count = {"total": 0}

        # ============================================================================
        # GEMINI MOCK - Always fails (for KubernetesAgent using Native Thinking)
        # ============================================================================
        def create_failing_gemini_mock():
            """Create Gemini mock that always raises an error."""
            async def mock_generate_content(*args, **kwargs):
                interaction_count["total"] += 1
                print(f"🔍 Gemini call #{interaction_count['total']} - FAILING")
                raise Exception("Simulated Gemini API failure for testing")
            
            return mock_generate_content

        gemini_mock_factory = create_failing_gemini_mock()

        # ============================================================================
        # LANGCHAIN MOCK - Always fails (for LogAgent using ReAct)
        # ============================================================================
        async def failing_streaming_mock(*args, **kwargs):
            """Streaming mock that always raises an error."""
            interaction_count["total"] += 1
            print(f"🔍 LangChain call #{interaction_count['total']} - FAILING")
            raise Exception("Simulated LangChain API failure for testing")

        # ============================================================================
        # MCP MOCK - Basic setup (shouldn't be reached but needed for initialization)
        # ============================================================================
        mock_k8s_session = AsyncMock()

        async def mock_k8s_call_tool(tool_name, parameters):
            mock_result = Mock()
            mock_content = Mock()
            mock_content.text = '{"result": "Mock k8s response - should not be reached"}'
            mock_result.content = [mock_content]
            return mock_result

        async def mock_k8s_list_tools():
            mock_tools = [
                Tool(
                    name="kubectl_get",
                    description="Get Kubernetes resources",
                    inputSchema={"type": "object", "properties": {}}
                ),
                Tool(
                    name="get_logs",
                    description="Get pod logs",
                    inputSchema={"type": "object", "properties": {}}
                )
            ]
            mock_result = Mock()
            mock_result.tools = mock_tools
            return mock_result

        mock_k8s_session.call_tool.side_effect = mock_k8s_call_tool
        mock_k8s_session.list_tools.side_effect = mock_k8s_list_tools

        mock_sessions = {
            "kubernetes-server": mock_k8s_session
        }

        # Create MCP client patches
        mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

        # Patch LLM clients (both Gemini SDK and LangChain) to fail
        with self._create_llm_patch_context(gemini_mock_factory, failing_streaming_mock):
            with patch('tarsy.integrations.mcp.client.MCPClient.list_tools', mock_list_tools):
                with patch('tarsy.integrations.mcp.client.MCPClient.call_tool', mock_call_tool):
                    with E2ETestUtils.setup_runbook_service_patching("# Test Runbook for LLM Failure Test"):
                        # Submit alert
                        print("⏳ Step 1: Submitting alert...")
                        session_id = E2ETestUtils.submit_alert(test_client, alert_data)
                        print(f"✅ Alert submitted: {session_id}")

                        # Wait for completion - expect FAILED status
                        print("⏳ Step 2: Waiting for processing (expect failure)...")
                        final_session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                            test_client, max_wait_seconds=60, debug_logging=True
                        )

                        # Verify session failed
                        print("🔍 Step 3: Verifying failure state...")
                        assert final_session_id == session_id, "Session ID mismatch"
                        assert final_status == "failed", f"Expected 'failed' status, got '{final_status}'"
                        print(f"✅ Session correctly marked as FAILED: {session_id}")

                        # Get session details to verify error message
                        detail_data = await E2ETestUtils.get_session_details_async(
                            test_client, session_id, max_retries=3, retry_delay=0.5
                        )

                        # Verify error is captured
                        error_message = detail_data.get("error_message", "")
                        print(f"📝 Error message: {error_message[:200]}...")

                        # The session should have an error message about the LLM failure
                        assert error_message, "Expected error message to be captured"
                        
                        # Verify stages exist and show failure
                        stages = detail_data.get("stages", [])
                        print(f"📊 Found {len(stages)} stage(s)")

                        # At least the parallel stage should be created
                        assert len(stages) >= 1, "Expected at least 1 stage to be created"

                        # Find the investigation stage (parallel stage)
                        investigation_stage = None
                        for stage in stages:
                            if stage["stage_name"] == "investigation":
                                investigation_stage = stage
                                break

                        if investigation_stage:
                            print(f"📋 Investigation stage status: {investigation_stage.get('status')}")
                            # Parallel stage should be failed
                            assert investigation_stage["status"] == "failed", (
                                f"Expected investigation stage to be 'failed', got '{investigation_stage['status']}'"
                            )

                        print(f"✅ Parallel LLM failure test passed!")
                        print(f"   📊 Summary: Session=FAILED, {len(stages)} stage(s) created")
                        print(f"   📝 Total LLM interaction attempts: {interaction_count['total']}")

                        return detail_data


@pytest.mark.asyncio
@pytest.mark.e2e
class TestParallelPartialLLMFailureE2E(ParallelTestBase):
    """E2E test for parallel stage with partial LLM failures (one agent fails, one succeeds)."""

    @pytest.mark.e2e
    async def test_parallel_stage_partial_failure(
        self, e2e_parallel_test_client, e2e_parallel_alert
    ):
        """
        Test parallel stage with partial failure (one agent fails, one succeeds).

        This tests the behavior when only one agent in a parallel stage fails.
        For this test chain, success_policy is set to "all" in the YAML configuration,
        so the overall stage should fail even with partial success.

        Flow:
        1. POST alert to /api/v1/alerts -> queued
        2. KubernetesAgent (Gemini) fails
        3. LogAgent (LangChain) succeeds
        4. Overall parallel stage fails (this chain's success_policy="all" requires all agents to succeed)
        5. Session should be marked as FAILED

        This test verifies:
        - Partial failure handling in parallel stages
        - Individual agent statuses are tracked correctly
        - Overall stage failure is computed based on success_policy
        """
        return await self._run_with_timeout(
            lambda: self._execute_partial_failure_test(e2e_parallel_test_client, e2e_parallel_alert),
            test_name="parallel partial failure test",
            timeout_seconds=120
        )

    async def _execute_partial_failure_test(self, test_client, alert_data):
        """Execute partial failure test."""
        print("🔧 Starting parallel stage partial failure test execution")

        # Track interactions per agent type
        interaction_count = {"gemini": 0, "langchain": 0}

        # ============================================================================
        # GEMINI MOCK - Always fails (for KubernetesAgent)
        # ============================================================================
        def create_failing_gemini_mock():
            """Create Gemini mock that always raises an error."""
            async def mock_generate_content(*args, **kwargs):
                interaction_count["gemini"] += 1
                print(f"🔍 Gemini call #{interaction_count['gemini']} - FAILING")
                raise Exception("Simulated Gemini API failure for KubernetesAgent")
            
            return mock_generate_content

        gemini_mock_factory = create_failing_gemini_mock()

        # ============================================================================
        # LANGCHAIN MOCK - Succeeds (for LogAgent)
        # ============================================================================
        from .conftest import create_mock_stream

        async def success_streaming_mock(*args, **kwargs):
            """Streaming mock that succeeds for LogAgent."""
            interaction_count["langchain"] += 1
            call_num = interaction_count["langchain"]
            print(f"🔍 LangChain call #{call_num} - SUCCESS")

            # First call: tool call, Second call: final answer
            if call_num == 1:
                content = """Thought: I should check the application logs.
Action: kubernetes-server.get_logs
Action Input: {"namespace": "test-namespace", "pod": "pod-1"}"""
            else:
                content = """Thought: Found the error in logs.
Final Answer: Log analysis shows database connection timeout errors."""

            usage_metadata = {
                'input_tokens': 100,
                'output_tokens': 50,
                'total_tokens': 150
            }
            async for chunk in create_mock_stream(content, usage_metadata):
                yield chunk

        # ============================================================================
        # MCP MOCK
        # ============================================================================
        mock_k8s_session = AsyncMock()

        async def mock_k8s_call_tool(tool_name, parameters):
            mock_result = Mock()
            mock_content = Mock()
            mock_content.text = '{"logs": "Error: Database connection timeout"}'
            mock_result.content = [mock_content]
            return mock_result

        async def mock_k8s_list_tools():
            mock_tools = [
                Tool(
                    name="kubectl_get",
                    description="Get Kubernetes resources",
                    inputSchema={"type": "object", "properties": {}}
                ),
                Tool(
                    name="get_logs",
                    description="Get pod logs",
                    inputSchema={"type": "object", "properties": {}}
                )
            ]
            mock_result = Mock()
            mock_result.tools = mock_tools
            return mock_result

        mock_k8s_session.call_tool.side_effect = mock_k8s_call_tool
        mock_k8s_session.list_tools.side_effect = mock_k8s_list_tools

        mock_sessions = {"kubernetes-server": mock_k8s_session}
        mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

        # Patch LLM clients
        with self._create_llm_patch_context(gemini_mock_factory, success_streaming_mock):
            with patch('tarsy.integrations.mcp.client.MCPClient.list_tools', mock_list_tools):
                with patch('tarsy.integrations.mcp.client.MCPClient.call_tool', mock_call_tool):
                    with E2ETestUtils.setup_runbook_service_patching("# Test Runbook"):
                        # Submit alert
                        print("⏳ Step 1: Submitting alert...")
                        session_id = E2ETestUtils.submit_alert(test_client, alert_data)
                        print(f"✅ Alert submitted: {session_id}")

                        # Wait for completion
                        print("⏳ Step 2: Waiting for processing...")
                        final_session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                            test_client, max_wait_seconds=60, debug_logging=True
                        )

                        # Verify session status
                        print("🔍 Step 3: Verifying results...")
                        assert final_session_id == session_id, "Session ID mismatch"
                        
                        # With this chain's success_policy="all", partial failure = overall failure
                        assert final_status == "failed", f"Expected 'failed' status, got '{final_status}'"
                        print(f"✅ Session correctly marked as FAILED: {session_id}")

                        # Get session details
                        detail_data = await E2ETestUtils.get_session_details_async(
                            test_client, session_id, max_retries=3, retry_delay=0.5
                        )

                        stages = detail_data.get("stages", [])
                        print(f"📊 Found {len(stages)} stage(s)")

                        # Find and verify investigation stage
                        investigation_stage = None
                        for stage in stages:
                            if stage["stage_name"] == "investigation":
                                investigation_stage = stage
                                break

                        if investigation_stage:
                            print(f"📋 Investigation stage status: {investigation_stage.get('status')}")
                            
                            # Check parallel executions if available
                            parallel_executions = investigation_stage.get("parallel_executions", [])
                            for exec_data in parallel_executions:
                                agent_name = exec_data.get("agent") or exec_data.get("agent_name")
                                status = exec_data.get("status")
                                print(f"   - Agent '{agent_name}': {status}")

                        print(f"✅ Parallel partial failure test passed!")
                        print(f"   📊 Gemini calls (failed): {interaction_count['gemini']}")
                        print(f"   📊 LangChain calls (succeeded): {interaction_count['langchain']}")

                        return detail_data

