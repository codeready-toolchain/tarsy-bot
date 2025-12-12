"""
End-to-End Tests for Single-Agent LLM Failure Handling.

This module tests that when LLM calls fail during single-agent stage execution:
- The system properly handles failures without crashing
- The session correctly transitions to FAILED status
- Error messages are properly captured and reported
- Works for both LangChain/ReAct and Gemini/Native-Thinking agents

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: HTTP requests to LLM APIs (configured to fail), MCP servers, GitHub runbooks
"""

import asyncio
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import Tool

from tarsy.config.builtin_config import BUILTIN_MCP_SERVERS
from tarsy.integrations.mcp.client import MCPClient

from .conftest import create_mock_stream
from .e2e_utils import E2ETestUtils

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestSingleAgentLangChainFailureE2E:
    """E2E tests for single-agent LangChain/ReAct LLM failure handling."""

    @pytest.mark.e2e
    async def test_langchain_react_agent_llm_failure(
        self, e2e_test_client, e2e_realistic_kubernetes_alert
    ):
        """
        Test single-agent (LangChain/ReAct) failure when ALL LLM calls fail.

        This uses the standard 3-stage chain (data-collection → verification → analysis)
        where all LangChain LLM calls fail.

        Flow:
        1. POST alert to /api/v1/alerts -> queued
        2. LangChain mock raises exceptions for all calls
        3. All stages should fail
        4. Session should be marked as FAILED
        5. Error messages properly captured

        This test verifies:
        - LangChain/ReAct agent failure is properly handled
        - Single-agent stages with stage_execution_id fail gracefully
        - Session transitions to FAILED status correctly
        - Error messages are captured
        """
        async def run_test():
            print("🚀 Starting LangChain/ReAct LLM failure test...")
            result = await self._execute_langchain_failure_test(
                e2e_test_client, e2e_realistic_kubernetes_alert
            )
            print("✅ LangChain/ReAct LLM failure test completed!")
            return result

        try:
            task = asyncio.create_task(run_test())
            _, pending = await asyncio.wait({task}, timeout=120.0)

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

    async def _execute_langchain_failure_test(self, test_client, alert_data):
        """Execute LangChain/ReAct failure test."""
        print("🔧 Starting LangChain/ReAct LLM failure test execution")

        # Track interactions
        interaction_count = {"total": 0}

        # ============================================================================
        # LANGCHAIN MOCK - Always fails
        # ============================================================================
        async def failing_streaming_mock(*args, **kwargs):
            """LangChain streaming mock that always raises an error."""
            interaction_count["total"] += 1
            print(f"🔍 LangChain call #{interaction_count['total']} - FAILING")
            raise Exception("Simulated LangChain API failure for testing")

        # ============================================================================
        # MCP MOCK - Basic setup (may not be reached)
        # ============================================================================
        k8s_config = E2ETestUtils.create_simple_kubernetes_mcp_config(
            command_args=["test"],
            instructions="Test server for LLM failure testing"
        )
        test_mcp_servers = E2ETestUtils.create_test_mcp_servers(BUILTIN_MCP_SERVERS, {
            "kubernetes-server": k8s_config
        })

        mock_session = E2ETestUtils.create_generic_mcp_session_mock()

        with patch("tarsy.config.builtin_config.BUILTIN_MCP_SERVERS", test_mcp_servers), \
             patch("tarsy.services.mcp_server_registry.MCPServerRegistry._DEFAULT_SERVERS", test_mcp_servers), \
             E2ETestUtils.setup_runbook_service_patching(content="# Test Runbook"):

            with E2ETestUtils.create_llm_patch_context(streaming_mock=failing_streaming_mock):
                mock_sessions = {"kubernetes-server": mock_session}
                mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

                async def mock_initialize(self):
                    """Mock initialization that bypasses real server startup."""
                    self.sessions = mock_sessions.copy()
                    self._initialized = True

                with patch.object(MCPClient, "initialize", mock_initialize), \
                     patch.object(MCPClient, "list_tools", mock_list_tools), \
                     patch.object(MCPClient, "call_tool", mock_call_tool):

                    # Submit alert
                    print("⏳ Step 1: Submitting alert...")
                    E2ETestUtils.submit_alert(test_client, alert_data)

                    # Wait for completion - expect FAILED status
                    print("⏳ Step 2: Waiting for processing (expect failure)...")
                    session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                        test_client, max_wait_seconds=60, debug_logging=True
                    )

                    # Verify session failed
                    print("🔍 Step 3: Verifying failure state...")
                    assert session_id is not None, "Session ID missing"
                    assert final_status == "failed", f"Expected 'failed' status, got '{final_status}'"
                    print(f"✅ Session correctly marked as FAILED: {session_id}")

                    # Get session details
                    detail_data = await E2ETestUtils.get_session_details_async(
                        test_client, session_id, max_retries=5
                    )

                    # Verify error is captured
                    error_message = detail_data.get("error_message", "")
                    print(f"📝 Error message: {error_message[:200]}...")
                    assert error_message, "Expected error message to be captured"

                    # Verify stages show failure
                    stages = detail_data.get("stages", [])
                    print(f"📊 Found {len(stages)} stage(s)")

                    # All stages should be failed
                    for stage in stages:
                        assert stage["status"] == "failed", (
                            f"Expected stage '{stage['stage_name']}' to be 'failed', got '{stage['status']}'"
                        )
                        print(f"   ✅ Stage '{stage['stage_name']}' correctly failed")

                    print(f"✅ LangChain/ReAct LLM failure test passed!")
                    print(f"   📊 Summary: Session=FAILED, {len(stages)} stage(s) failed")
                    print(f"   📝 Total LLM interaction attempts: {interaction_count['total']}")

                    return detail_data


@pytest.mark.asyncio
@pytest.mark.e2e
class TestSingleAgentGeminiNativeThinkingFailureE2E:
    """E2E tests for single-agent Gemini/Native-Thinking LLM failure handling."""

    @pytest.mark.e2e
    async def test_gemini_native_thinking_agent_llm_failure(
        self, e2e_native_thinking_test_client, e2e_native_thinking_alert
    ):
        """
        Test single-agent (Gemini/Native-Thinking) failure when ALL LLM calls fail.

        This uses the native thinking 3-stage chain where all Gemini SDK calls fail.

        Flow:
        1. POST alert to /api/v1/alerts -> queued
        2. Gemini SDK mock raises exceptions for all calls
        3. All stages should fail
        4. Session should be marked as FAILED
        5. Error messages properly captured

        This test verifies:
        - Gemini/Native-Thinking agent failure is properly handled
        - Single-agent stages with stage_execution_id fail gracefully
        - Session transitions to FAILED status correctly
        - Error messages are captured
        """
        async def run_test():
            print("🚀 Starting Gemini/Native-Thinking LLM failure test...")
            result = await self._execute_gemini_failure_test(
                e2e_native_thinking_test_client, e2e_native_thinking_alert
            )
            print("✅ Gemini/Native-Thinking LLM failure test completed!")
            return result

        try:
            task = asyncio.create_task(run_test())
            _, pending = await asyncio.wait({task}, timeout=120.0)

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

    async def _execute_gemini_failure_test(self, test_client, alert_data):
        """Execute Gemini/Native-Thinking failure test."""
        print("🔧 Starting Gemini/Native-Thinking LLM failure test execution")

        # Track interactions
        interaction_count = {"gemini": 0, "langchain": 0}

        # ============================================================================
        # GEMINI SDK MOCK - Always fails
        # ============================================================================
        def create_failing_gemini_mock():
            """Create Gemini mock that always raises an error."""
            async def mock_generate_content(*args, **kwargs):
                interaction_count["gemini"] += 1
                print(f"🔍 Gemini call #{interaction_count['gemini']} - FAILING")
                raise Exception("Simulated Gemini SDK failure for testing")
            
            return mock_generate_content

        gemini_mock_factory = create_failing_gemini_mock()

        # ============================================================================
        # LANGCHAIN MOCK - For summarization (also fails to be consistent)
        # ============================================================================
        async def failing_langchain_mock(*args, **kwargs):
            """LangChain mock that fails (used for summarization)."""
            interaction_count["langchain"] += 1
            print(f"🔍 LangChain call #{interaction_count['langchain']} - FAILING")
            raise Exception("Simulated LangChain API failure for testing")

        # ============================================================================
        # MCP MOCK
        # ============================================================================
        k8s_config = E2ETestUtils.create_simple_kubernetes_mcp_config(
            command_args=["test"],
            instructions="Test server for Gemini LLM failure testing"
        )
        test_mcp_servers = E2ETestUtils.create_test_mcp_servers(BUILTIN_MCP_SERVERS, {
            "kubernetes-server": k8s_config
        })

        mock_k8s_session = AsyncMock()

        async def mock_k8s_call_tool(tool_name, parameters):
            mock_result = Mock()
            mock_content = Mock()
            mock_content.text = '{"result": "Mock response - should not be reached"}'
            mock_result.content = [mock_content]
            return mock_result

        async def mock_k8s_list_tools():
            mock_tools = [
                Tool(
                    name="kubectl_get",
                    description="Get Kubernetes resources",
                    inputSchema={"type": "object", "properties": {}}
                )
            ]
            mock_result = Mock()
            mock_result.tools = mock_tools
            return mock_result

        mock_k8s_session.call_tool.side_effect = mock_k8s_call_tool
        mock_k8s_session.list_tools.side_effect = mock_k8s_list_tools

        with patch("tarsy.config.builtin_config.BUILTIN_MCP_SERVERS", test_mcp_servers), \
             patch("tarsy.services.mcp_server_registry.MCPServerRegistry._DEFAULT_SERVERS", test_mcp_servers), \
             E2ETestUtils.setup_runbook_service_patching(content="# Test Runbook"):

            with E2ETestUtils.create_llm_patch_context(
                gemini_mock_factory=gemini_mock_factory,
                streaming_mock=failing_langchain_mock
            ):
                mock_sessions = {"kubernetes-server": mock_k8s_session}
                mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

                async def mock_initialize(self):
                    """Mock initialization that bypasses real server startup."""
                    self.sessions = mock_sessions.copy()
                    self._initialized = True

                with patch.object(MCPClient, "initialize", mock_initialize), \
                     patch.object(MCPClient, "list_tools", mock_list_tools), \
                     patch.object(MCPClient, "call_tool", mock_call_tool):

                    # Submit alert
                    print("⏳ Step 1: Submitting alert...")
                    E2ETestUtils.submit_alert(test_client, alert_data)

                    # Wait for completion - expect FAILED status
                    print("⏳ Step 2: Waiting for processing (expect failure)...")
                    session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                        test_client, max_wait_seconds=60, debug_logging=True
                    )

                    # Verify session failed
                    print("🔍 Step 3: Verifying failure state...")
                    assert session_id is not None, "Session ID missing"
                    assert final_status == "failed", f"Expected 'failed' status, got '{final_status}'"
                    print(f"✅ Session correctly marked as FAILED: {session_id}")

                    # Get session details
                    detail_data = await E2ETestUtils.get_session_details_async(
                        test_client, session_id, max_retries=5
                    )

                    # Verify error is captured
                    error_message = detail_data.get("error_message", "")
                    print(f"📝 Error message: {error_message[:200]}...")
                    assert error_message, "Expected error message to be captured"

                    # Verify stages show failure
                    stages = detail_data.get("stages", [])
                    print(f"📊 Found {len(stages)} stage(s)")

                    # All stages should be failed
                    for stage in stages:
                        assert stage["status"] == "failed", (
                            f"Expected stage '{stage['stage_name']}' to be 'failed', got '{stage['status']}'"
                        )
                        print(f"   ✅ Stage '{stage['stage_name']}' correctly failed")

                    print(f"✅ Gemini/Native-Thinking LLM failure test passed!")
                    print(f"   📊 Summary: Session=FAILED, {len(stages)} stage(s) failed")
                    print(f"   📝 Gemini calls: {interaction_count['gemini']}, LangChain calls: {interaction_count['langchain']}")

                    return detail_data


@pytest.mark.asyncio
@pytest.mark.e2e
class TestSingleAgentIntermittentFailureE2E:
    """E2E tests for single-agent with intermittent LLM failures that eventually succeed."""

    @pytest.mark.e2e
    async def test_langchain_agent_retry_success(
        self, e2e_test_client, e2e_realistic_kubernetes_alert
    ):
        """
        Test single-agent (LangChain/ReAct) with intermittent failures that eventually succeed.

        This verifies that LLM retry logic works:
        - First few calls fail
        - Eventually succeeds
        - Session completes successfully

        Flow:
        1. POST alert to /api/v1/alerts -> queued
        2. LangChain mock fails first 3 calls, then succeeds
        3. Session should eventually complete
        4. Error recovery is verified

        This test verifies:
        - LLM retry mechanism works for LangChain
        - Intermittent failures don't cause permanent failure
        - Session eventually completes successfully
        """
        async def run_test():
            print("🚀 Starting LangChain/ReAct intermittent failure test...")
            result = await self._execute_retry_test(
                e2e_test_client, e2e_realistic_kubernetes_alert
            )
            print("✅ LangChain/ReAct intermittent failure test completed!")
            return result

        try:
            task = asyncio.create_task(run_test())
            _, pending = await asyncio.wait({task}, timeout=120.0)

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

    async def _execute_retry_test(self, test_client, alert_data):
        """Execute intermittent failure test."""
        print("🔧 Starting LangChain/ReAct intermittent failure test execution")

        # Track interactions
        call_count = {"total": 0}
        FAIL_UNTIL = 3  # Fail first 3 calls, then succeed

        # ============================================================================
        # LANGCHAIN MOCK - Fails first N calls, then succeeds
        # ============================================================================
        async def intermittent_streaming_mock(*args, **kwargs):
            """LangChain mock that fails first N calls, then succeeds."""
            call_count["total"] += 1
            call_num = call_count["total"]

            if call_num <= FAIL_UNTIL:
                print(f"🔍 LangChain call #{call_num} - FAILING (intentional)")
                raise Exception(f"Simulated intermittent failure #{call_num}")

            # After failures, provide Final Answer to complete
            print(f"🔍 LangChain call #{call_num} - SUCCESS")
            content = """Final Answer: Investigation complete. The issue has been identified and analyzed. 
            The namespace was stuck due to finalizer blocking deletion. 
            Root cause: orphaned PVC references preventing cleanup."""
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
        k8s_config = E2ETestUtils.create_simple_kubernetes_mcp_config(
            command_args=["test"],
            instructions="Test server for retry testing"
        )
        test_mcp_servers = E2ETestUtils.create_test_mcp_servers(BUILTIN_MCP_SERVERS, {
            "kubernetes-server": k8s_config
        })

        mock_session = E2ETestUtils.create_generic_mcp_session_mock()

        with patch("tarsy.config.builtin_config.BUILTIN_MCP_SERVERS", test_mcp_servers), \
             patch("tarsy.services.mcp_server_registry.MCPServerRegistry._DEFAULT_SERVERS", test_mcp_servers), \
             E2ETestUtils.setup_runbook_service_patching(content="# Test Runbook"):

            with E2ETestUtils.create_llm_patch_context(streaming_mock=intermittent_streaming_mock):
                mock_sessions = {"kubernetes-server": mock_session}
                mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

                async def mock_initialize(self):
                    """Mock initialization that bypasses real server startup."""
                    self.sessions = mock_sessions.copy()
                    self._initialized = True

                with patch.object(MCPClient, "initialize", mock_initialize), \
                     patch.object(MCPClient, "list_tools", mock_list_tools), \
                     patch.object(MCPClient, "call_tool", mock_call_tool):

                    # Submit alert
                    print("⏳ Step 1: Submitting alert...")
                    E2ETestUtils.submit_alert(test_client, alert_data)

                    # Wait for completion
                    print("⏳ Step 2: Waiting for processing...")
                    session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                        test_client, max_wait_seconds=60, debug_logging=True
                    )

                    # Verify session completed (retry worked)
                    print("🔍 Step 3: Verifying completion state...")
                    assert session_id is not None, "Session ID missing"
                    assert final_status == "completed", f"Expected 'completed' status, got '{final_status}'"
                    print(f"✅ Session correctly completed after retries: {session_id}")

                    # Get session details
                    detail_data = await E2ETestUtils.get_session_details_async(
                        test_client, session_id, max_retries=5
                    )

                    stages = detail_data.get("stages", [])
                    print(f"📊 Found {len(stages)} stage(s)")

                    # All stages should be completed
                    for stage in stages:
                        assert stage["status"] == "completed", (
                            f"Expected stage '{stage['stage_name']}' to be 'completed', got '{stage['status']}'"
                        )
                        print(f"   ✅ Stage '{stage['stage_name']}' completed")

                    print(f"✅ LangChain/ReAct intermittent failure test passed!")
                    print(f"   📊 Summary: Session=COMPLETED after {call_count['total']} LLM calls")
                    print(f"   📝 {FAIL_UNTIL} calls failed, then succeeded")

                    return detail_data

