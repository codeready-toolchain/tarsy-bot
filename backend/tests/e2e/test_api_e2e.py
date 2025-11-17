"""
Simplified End-to-End Test with HTTP-level mocking.

This test uses the real FastAPI application with real internal services,
mocking only external HTTP dependencies at the network boundary.

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: HTTP requests to LLM APIs, MCP servers, GitHub runbooks
"""

import asyncio
import logging
import os
from unittest.mock import AsyncMock, Mock, patch
from mcp.types import Tool

import pytest

from tarsy.config.builtin_config import BUILTIN_MCP_SERVERS
from tarsy.integrations.mcp.client import MCPClient
from .e2e_utils import E2ETestUtils

from .expected_conversations import (
    EXPECTED_ANALYSIS_CONVERSATION,
    EXPECTED_CHAT_INTERACTIONS,
    EXPECTED_CHAT_MESSAGE_1_CONVERSATION,
    EXPECTED_CHAT_MESSAGE_2_CONVERSATION,
    EXPECTED_DATA_COLLECTION_CONVERSATION,
    EXPECTED_STAGES,
    EXPECTED_VERIFICATION_CONVERSATION,
)

from .conftest import create_mock_stream

logger = logging.getLogger(__name__)


def assert_conversation_messages(
    expected_conversation: dict, actual_messages: list, n: int
):
    """
    Get the first N messages from expected_conversation['messages'] and compare with actual_messages.

    Args:
        expected_conversation: Dictionary with 'messages' key containing expected message list
        actual_messages: List of actual messages from the LLM interaction
        n: Number of messages to compare (a count)
    """
    expected_messages = expected_conversation.get("messages", [])
    assert (
        len(actual_messages) == n
    ), f"Actual messages count mismatch: expected {n}, got {len(actual_messages)}"

    # Extract first N messages
    first_n_expected = expected_messages[:n]

    # Compare each message
    for i in range(len(first_n_expected)):
        assert (
            i < len(actual_messages)
        ), f"Missing actual message: Expected {len(first_n_expected)} messages, got {len(actual_messages)}"

        expected_msg = first_n_expected[i]
        actual_msg = actual_messages[i]

        # Compare role
        expected_role = expected_msg.get("role", "")
        actual_role = actual_msg.get("role", "")
        assert (
            expected_role == actual_role
        ), f"Role mismatch: expected {expected_role}, got {actual_role}"

        # Normalize content for comparison
        expected_content = E2ETestUtils.normalize_content(expected_msg.get("content", ""))
        actual_content = E2ETestUtils.normalize_content(actual_msg.get("content", ""))
        
        assert (
            expected_content == actual_content
        ), f"Content mismatch in message {i}: expected length {len(expected_content)}, got {len(actual_content)}"


@pytest.mark.asyncio
@pytest.mark.e2e
class TestRealE2E:
    """
    Simplified E2E test using HTTP-level mocking.

    Tests the complete system flow:
    1. HTTP POST to /api/v1/alerts endpoint
    2. Real alert processing through AlertService
    3. Real agent execution with real hook system
    4. Real database storage via HistoryService
    5. HTTP GET from history APIs

    Mocks only external HTTP calls (LLM APIs, runbooks, MCP servers).
    """

    @pytest.mark.e2e
    async def test_complete_alert_processing_flow(
        self, e2e_test_client, e2e_realistic_kubernetes_alert
    ):
        """
        Simplified E2E test focusing on core functionality.

        Flow:
        1. POST alert to /api/v1/alerts -> queued
        2. Wait for processing to complete
        3. Verify session was created and completed
        4. Verify basic structure (stages exist)

        This simplified test verifies:
        - Alert submission works
        - Processing completes without hanging
        - Session is created and marked as completed
        - Basic stage structure exists
        """

        # Wrap entire test in hardcore timeout to prevent hanging
        async def run_test():
            print("🚀 Starting test execution...")
            result = await self._execute_test(
                e2e_test_client, e2e_realistic_kubernetes_alert
            )
            print("✅ Test execution completed!")
            return result

        try:
            # Use task-based timeout instead of wait_for to avoid cancellation issues
            task = asyncio.create_task(run_test())
            done, pending = await asyncio.wait({task}, timeout=500.0)

            if pending:
                # Timeout occurred
                for t in pending:
                    t.cancel()
                print("❌ HARDCORE TIMEOUT: Test exceeded 500 seconds!")
                print("Check for hanging in alert processing pipeline")
                raise AssertionError("Test exceeded hardcore timeout of 500 seconds")
            else:
                # Task completed
                return task.result()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            raise

    async def _execute_test(self, e2e_test_client, e2e_realistic_kubernetes_alert):
        """Minimal test execution with maximum real infrastructure."""
        print("🔧 _execute_test started")

        # ONLY mock external network calls - use real internal services
        # Using streaming mocks for LLM and MCP SDK mocking for stdio communication

        # Simplified interaction tracking - focus on LLM calls only
        # (MCP interactions will be validated from API response)
        all_llm_interactions = []
        
        # Define mock response content and token usage for each interaction
        # These values are used to test llm interaction, token tracking at interaction, stage, and session levels
        # Expected stage token usage totals: data-collection=1570(regular)+150(summarization)=1720, verification=650, analysis=600
        # Expected session token usage total: 2970 tokens (2150 input + 820 output)
        mock_response_map = {
            1: { # Data collection - Initial analysis
                "response_content": """Thought: I need to get namespace information first.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}""",
               "input_tokens": 245, "output_tokens": 85, "total_tokens": 330
               },
            2: { # Data collection - kubectl describe
                "response_content": """Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "namespace", "name": "stuck-namespace"}""",
                "input_tokens": 180, "output_tokens": 65, "total_tokens": 245
               },
            3: { # Data collection - System info
                "response_content": """Thought: Let me also collect system information to understand resource constraints.
Action: test-data-server.collect_system_info
Action Input: {"detailed": false}""",
                "input_tokens": 220, "output_tokens": 75, "total_tokens": 295
               },
            4: { # Data collection - Tool result summarization (happens right after collect_system_info)
                "response_content": """Summarized: System healthy, CPU 45%, Memory 33%, Disk 76%, Network OK.""",
                "input_tokens": 100, "output_tokens": 50, "total_tokens": 150
               },
            5: { # Data collection - Additional investigation (continues after summarization)
                "response_content": """Thought: Let me gather more information about the current state.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "events", "namespace": "test-namespace"}""",
                "input_tokens": 200, "output_tokens": 60, "total_tokens": 260
            },
            6: { # Data collection - Final analysis
                "response_content": """Final Answer: Data collection completed. Found namespace 'stuck-namespace' in Terminating state with finalizers blocking deletion.""",
                "input_tokens": 315, "output_tokens": 125, "total_tokens": 440
               },
            7: { # Verification - Check
                "response_content": """Thought: I need to verify the namespace status.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}""",
                "input_tokens": 190, "output_tokens": 70, "total_tokens": 260
               },
            8: { # Verification - Summary
                "response_content": """Final Answer: Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion.""",
                "input_tokens": 280, "output_tokens": 110, "total_tokens": 390
               },
            9: { # Analysis - Final
                "response_content": """Based on previous stages, the namespace is stuck due to finalizers.""",
                "input_tokens": 420, "output_tokens": 180, "total_tokens": 600
               },
            10: { # Chat - First ReAct iteration
                "response_content": """Thought: The user wants to see the pods in stuck-namespace. I'll use kubectl_get to list them.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "namespace": "stuck-namespace"}""",
                "input_tokens": 150, "output_tokens": 60, "total_tokens": 210
               },
            11: { # Chat Message 1 - Final answer
                "response_content": """Final Answer: I checked the pods in stuck-namespace and found no pods are currently running. This is consistent with the namespace being stuck in Terminating state - all pods have likely been deleted already, but the namespace can't complete deletion due to the finalizers mentioned in the original investigation.""",
                "input_tokens": 180, "output_tokens": 90, "total_tokens": 270
               },
            12: { # Chat Message 2 - ReAct iteration (check namespace status again)
                "response_content": """Thought: The user wants to know if the namespace still exists. Let me check its current status.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}""",
                "input_tokens": 200, "output_tokens": 70, "total_tokens": 270
               },
            13: { # Chat Message 2 - Final answer
                "response_content": """Final Answer: Yes, the namespace still exists and remains in Terminating state. Based on the investigation history, the namespace is blocked by finalizers (kubernetes.io/pvc-protection). To resolve this, you would need to manually remove the finalizers using kubectl patch or edit the namespace resource directly.""",
                "input_tokens": 220, "output_tokens": 95, "total_tokens": 315
               },
        }
        
        # Create streaming mock for LLM client
        def create_streaming_mock():
            """Create a mock astream function that returns streaming responses."""
            async def mock_astream(*args, **kwargs):
                # Track this interaction
                interaction_num = len(all_llm_interactions) + 1
                all_llm_interactions.append(interaction_num)
                
                print(f"\n🔍 LLM REQUEST #{interaction_num}:")
                # Extract messages from args
                if args and len(args) > 0:
                    messages = args[0]
                    for i, msg in enumerate(messages):
                        role = getattr(msg, 'type', 'unknown') if hasattr(msg, 'type') else 'unknown'
                        content = getattr(msg, 'content', '') if hasattr(msg, 'content') else ''
                        print(f"  Message {i+1} ({role}):")
                        print(f"    Content: {content[:200]}...{content[-100:] if len(content) > 300 else ''}")
                print("=" * 80)
                
                # Get mock response for this interaction
                mock_response = mock_response_map.get(interaction_num, {
                    "response_content": "", 
                    "input_tokens": 0, 
                    "output_tokens": 0, 
                    "total_tokens": 0
                })
                
                # Create async generator that yields chunks
                content = mock_response["response_content"]
                usage_metadata = {
                    'input_tokens': mock_response["input_tokens"],
                    'output_tokens': mock_response["output_tokens"],
                    'total_tokens': mock_response["total_tokens"]
                }
                
                # Use our mock stream generator
                async for chunk in create_mock_stream(content, usage_metadata):
                    yield chunk
            
            return mock_astream

        # Create MCP SDK mock functions
        def create_mcp_session_mock():
            """Create a mock MCP session that provides kubectl tools.

            Note: This mock has intentional tool call failures to simulate MCP server issues.
            The mock_list_tools provides tools but mock_call_tool simulates that the tools
            aren't found when called. This tests the system's error handling for MCP failures.
            These errors are expected and part of the test design to verify that agents
            can handle MCP tool failures gracefully and still provide meaningful analysis.
            """
            mock_session = AsyncMock()

            async def mock_call_tool(tool_name, _parameters):
                # Create mock result object with content attribute
                mock_result = Mock()

                if tool_name == "kubectl_get":
                    resource = _parameters.get("resource", "pods")
                    name = _parameters.get("name", "")
                    namespace = _parameters.get("namespace", "")

                    if resource == "namespaces" and name == "stuck-namespace":
                        mock_content = Mock()
                        mock_content.text = "stuck-namespace   Terminating   45m"
                        mock_result.content = [mock_content]
                    elif resource == "pods" and namespace == "stuck-namespace":
                        # Chat query for pods in stuck-namespace
                        mock_content = Mock()
                        mock_content.text = "No pods found in namespace stuck-namespace"
                        mock_result.content = [mock_content]
                    else:
                        mock_content = Mock()
                        mock_content.text = f"Mock kubectl get {resource} response"
                        mock_result.content = [mock_content]

                elif tool_name == "kubectl_describe":
                    # Create a custom exception that mimics the exact MCP error structure
                    # The extract_error_details function will format it as: Type=McpError | Message=... | error=ErrorData(...)
                    class MockErrorData:
                        def __init__(self):
                            self.code = -32602
                            self.message = "tool 'kubectl_describe' not found: tool not found"
                            self.data = None
                            
                        def __repr__(self):
                            return f"ErrorData(code={self.code}, message=\"{self.message}\", data={self.data})"
                    
                    class MockMcpError(Exception):
                        def __init__(self, message):
                            # Only store the error attribute (not message to avoid duplication)
                            self.error = MockErrorData()
                            super().__init__(message)
                        
                        def __str__(self):
                            return "tool 'kubectl_describe' not found: tool not found"
                    
                    # Make the error appear as if it's an MCP error by setting the type name
                    MockMcpError.__name__ = "McpError"
                    raise MockMcpError("tool 'kubectl_describe' not found: tool not found")

                else:
                    mock_content = Mock()
                    mock_content.text = f"Mock response for tool: {tool_name}"
                    mock_result.content = [mock_content]

                return mock_result

            async def mock_list_tools():
                # Create proper Tool objects (not Mock objects)
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
                    }
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
                    }
                )

                # Return object with .tools attribute (matching MCP SDK API)
                mock_result = Mock()
                mock_result.tools = [mock_tool1, mock_tool2]
                return mock_result

            mock_session.call_tool.side_effect = mock_call_tool
            mock_session.list_tools.side_effect = mock_list_tools

            return mock_session

        def create_custom_mcp_session_mock():
            """Create a mock MCP session for the custom test-data-server."""
            mock_session = AsyncMock()

            async def mock_call_tool(tool_name, _parameters):
                # Create mock result object with content attribute - this must return the exact structure
                # that MCPClient.call_tool expects after processing
                if tool_name == "collect_system_info":
                    # Return a large result that exceeds the summarization threshold (100 tokens)
                    # This will trigger MCP result summarization
                    large_system_info = """Long System Information Report - more than 100 tokens
8wHXXQkrjqtaYwXb3KdmeOapEKU27hMiaYvzT25SI4MexrI2SC9gFLsKie0eDxH5WEVV7TvDCWjOrD2egFSykp2eRP2u9jVwUqzgOVULB6WAnTKol7vmIii9F7gCWoKMXnJsh12fppgIWJAbFw5vYuv7JIQMargw3vxFZO699z3t0hiYPtcLyeSXyyIf0lIxl8lOmKLsYA4TBZiSwZ6V5NV1cZ2VQeMxDOLN4F6kjTaqCtTc7zGCYzvHlv9BaCVB4SXo26yfg3r2G7sCRjexj0EvKGxnYecJiJoEtqD01pCCBrlQC8esGoG15NaMlFCWIsbdJmADZOR0WUYOcOhNk0WOtASqzHJBIfnGVYYxGMq0A5DkPGbUe4UXYPNEnD0xZ7YcEYGKAmdYmx2F2BgMi2NYXcelZ1Ym1Ukx2zGZoiKVmBdutnWr2ManM0PnChDLj0SyIZGdmhZhOn5R9uB3HpbCXsKzw4gUYiU9EvwW2m22pe6zKTSCpyhI4rVG5fFwrehWEbuB8nTbI3eawqQQevCbal42ko0GBG1sjE2GIDn7jmwJEBImlxRkuHoyWvMqfLDn9RbGXzhtnlO7sKZEb9He"""
                    return {
                        "result": large_system_info.strip()
                    }
                else:
                    return {"result": f"Mock response for custom tool: {tool_name}"}

            async def mock_list_tools():
                # Create proper Tool object (not Mock object)
                mock_tool = Tool(
                    name="collect_system_info",
                    description="Collect basic system information like CPU, memory, and disk usage",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "detailed": {
                                "type": "boolean",
                                "description": "Whether to return detailed system info",
                            }
                        },
                    }
                )

                # Return object with .tools attribute (matching MCP SDK API)
                mock_result = Mock()
                mock_result.tools = [mock_tool]
                return mock_result

            mock_session.call_tool.side_effect = mock_call_tool
            mock_session.list_tools.side_effect = mock_list_tools

            return mock_session

        # Create mock MCP sessions for all servers
        mock_kubernetes_session = create_mcp_session_mock()
        mock_custom_session = create_custom_mcp_session_mock()

        # Create test MCP server configurations using shared utilities
        k8s_config = E2ETestUtils.create_simple_kubernetes_mcp_config(
            command_args=["kubernetes-mock-server-ready"],
            instructions="Test kubernetes server for e2e testing"
        )
        data_config = E2ETestUtils.create_simple_data_server_mcp_config(
            command_args=["test-data-server-ready"],
            instructions="Test data collection server for e2e testing"
        )

        test_mcp_servers = E2ETestUtils.create_test_mcp_servers(BUILTIN_MCP_SERVERS, {
            "kubernetes-server": k8s_config,
            "test-data-server": data_config
        })

        # Apply comprehensive mocking with test MCP server config
        # Patch both the original constant and the registry's stored reference
        with patch("tarsy.config.builtin_config.BUILTIN_MCP_SERVERS", test_mcp_servers), \
             patch("tarsy.services.mcp_server_registry.MCPServerRegistry._DEFAULT_SERVERS", test_mcp_servers), \
             patch.dict(os.environ, {}, clear=True), \
             E2ETestUtils.setup_runbook_service_patching():  # Patch runbook service for consistent behavior
            
            # 1. Mock LLM streaming (preserves LLM hooks!)
            streaming_mock = create_streaming_mock()
            
            # Import LangChain clients to patch
            from langchain_openai import ChatOpenAI
            from langchain_anthropic import ChatAnthropic
            from langchain_xai import ChatXAI
            from langchain_google_genai import ChatGoogleGenerativeAI
            
            # Patch the astream method on all LangChain client classes
            # This works because the method will be called on instances
            with patch.object(ChatOpenAI, 'astream', streaming_mock), \
                 patch.object(ChatAnthropic, 'astream', streaming_mock), \
                 patch.object(ChatXAI, 'astream', streaming_mock), \
                 patch.object(ChatGoogleGenerativeAI, 'astream', streaming_mock):
                
                # 2. Mock MCP client using shared utility with custom sessions
                mock_sessions = {
                    "kubernetes-server": mock_kubernetes_session,
                    "test-data-server": mock_custom_session,
                }
                mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

                # Create a mock initialize method that sets up mock sessions without real server processes
                async def mock_initialize(self):
                    """Mock initialization that bypasses real server startup."""
                    self.sessions = mock_sessions.copy()
                    self._initialized = True
                    
                with patch.object(MCPClient, "initialize", mock_initialize), \
                     patch.object(MCPClient, "list_tools", mock_list_tools), \
                     patch.object(MCPClient, "call_tool", mock_call_tool):
                    print(
                        "🔧 Using the real AlertService with test MCP server config and streaming mocks..."
                    )
                    # All internal services are real, hooks work perfectly!
                    # LLM streaming is mocked by patching LangChain client astream methods
                    # Runbook service is patched directly for consistent behavior
                    # MCP server config replaced with test config to avoid external NPM packages
                    # MCP calls handled by mock session that provides kubectl tools

                    print("⏳ Step 1: Submitting alert...")
                    E2ETestUtils.submit_alert(e2e_test_client, e2e_realistic_kubernetes_alert)

                    print("⏳ Step 2: Waiting for processing...")
                    session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                        e2e_test_client, max_wait_seconds=15, debug_logging=False
                    )

                    print("🔍 Step 3: Verifying results...")

                    # Basic verification
                    assert session_id is not None, "Session ID missing"
                    print(f"✅ Session found: {session_id}, final status: {final_status}")

                    # Verify session completed successfully
                    if final_status != "completed":
                        # Get detailed error info
                        detail_data = await E2ETestUtils.get_session_details_async(e2e_test_client, session_id)
                        error_msg = detail_data.get("error_message", "No error message")
                        print(f"❌ Session failed with error: {error_msg}")
                    assert (
                        final_status == "completed"
                    ), f"Expected session to be completed, but got: {final_status}"
                    print("✅ Session completed successfully!")

                    # Get session details to verify stages structure
                    detail_data = await E2ETestUtils.get_session_details_async(e2e_test_client, session_id)
                    stages = detail_data.get("stages", [])
                    print(f"Found {len(stages)} stages in completed session")

                    # Assert that stages exist and verify basic structure
                    assert (
                        len(stages) > 0
                    ), "Session completed but no stages found - invalid session structure"
                    print("✅ Session has stages - basic structure verified")

                    print("🔍 Step 4: Comprehensive result verification...")
                    await self._verify_session_metadata(
                        detail_data, e2e_realistic_kubernetes_alert
                    )
                    await self._verify_stage_structure(stages)
                    await self._verify_complete_interaction_flow(stages)

                    print("✅ COMPREHENSIVE VERIFICATION PASSED!")

                    print("🔍 Step 5: Testing chat functionality...")
                    await self._test_chat_functionality(e2e_test_client, session_id)

                    print("✅ CHAT FUNCTIONALITY TEST PASSED!")

                    return

    async def _verify_session_metadata(self, session_data, original_alert):
        """Verify session metadata matches expectations."""
        print("  📋 Verifying session metadata...")

        required_fields = [
            "session_id",
            "alert_type",
            "status",
            "started_at_us",
            "completed_at_us",
        ]
        for field in required_fields:
            assert field in session_data, f"Missing required session field: {field}"

        # Verify alert type matches
        assert (
            session_data["alert_type"] == original_alert["alert_type"]
        ), f"Alert type mismatch: expected {original_alert['alert_type']}, got {session_data['alert_type']}"

        # Verify chain information
        assert "chain_id" in session_data, "Missing chain_id in session data"
        assert (
            session_data["chain_id"] == "kubernetes-namespace-terminating-chain"
        ), f"Unexpected chain_id: {session_data['chain_id']}"

        # Verify timestamps are reasonable
        started_at = session_data["started_at_us"]
        completed_at = session_data["completed_at_us"]
        assert started_at > 0, "Invalid started_at timestamp"
        assert completed_at > started_at, "completed_at should be after started_at"

        # Processing duration should be reasonable (< 10 seconds with mocked calls)
        # All LLM and MCP calls are mocked, so processing should be nearly instantaneous
        processing_duration_ms = (completed_at - started_at) / 1000
        assert (
            processing_duration_ms < 10000
        ), f"Processing took too long: {processing_duration_ms}ms (should be <10s with mocked calls)"

        # Verify session-level token usage totals (sum of all stages)
        # Expected totals: data-collection(1260+460=1720) + verification(470+180=650) + analysis(420+180=600)
        expected_session_input_tokens = 2150  # 1260 + 470 + 420
        expected_session_output_tokens = 820   # 460 + 180 + 180  
        expected_session_total_tokens = 2970   # 1720 + 650 + 600
        
        actual_session_input_tokens = session_data.get("session_input_tokens")
        actual_session_output_tokens = session_data.get("session_output_tokens")
        actual_session_total_tokens = session_data.get("session_total_tokens")
        
        assert (
            actual_session_input_tokens == expected_session_input_tokens
        ), f"Session input_tokens mismatch: expected {expected_session_input_tokens}, got {actual_session_input_tokens}"
        assert (
            actual_session_output_tokens == expected_session_output_tokens
        ), f"Session output_tokens mismatch: expected {expected_session_output_tokens}, got {actual_session_output_tokens}"
        assert (
            actual_session_total_tokens == expected_session_total_tokens
        ), f"Session total_tokens mismatch: expected {expected_session_total_tokens}, got {actual_session_total_tokens}"

        print(
            f"    ✅ Session metadata verified (chain: {session_data['chain_id']}, duration: {processing_duration_ms:.1f}ms)"
        )

    async def _verify_stage_structure(self, stages):
        """Verify stage structure and count."""
        print("  🏗️ Verifying stage structure...")

        # Expected stages for kubernetes-namespace-terminating-chain (multi-stage)
        expected_stages = ["data-collection", "verification", "analysis"]

        assert len(stages) == len(
            expected_stages
        ), f"Expected {len(expected_stages)} stages, got {len(stages)}"

        # Verify each stage has required structure
        for i, stage in enumerate(stages):
            required_stage_fields = [
                "stage_id",
                "stage_name",
                "agent",
                "status",
                "stage_index",
            ]
            for field in required_stage_fields:
                assert field in stage, f"Stage {i} missing required field: {field}"

            # Verify stage order and names
            assert (
                stage["stage_name"] == expected_stages[i]
            ), f"Stage {i} name mismatch: expected {expected_stages[i]}, got {stage['stage_name']}"

            # Verify stage index
            assert (
                stage["stage_index"] == i
            ), f"Stage {i} index mismatch: expected {i}, got {stage['stage_index']}"

            # Verify all stages completed successfully
            assert (
                stage["status"] == "completed"
            ), f"Stage {i} ({stage['stage_name']}) not completed: {stage['status']}"
        print(
            f"    ✅ Stage structure verified ({len(stages)} stages in correct order)"
        )

    async def _verify_complete_interaction_flow(self, stages):
        """Verify complete interaction flow using progressive conversation format."""
        print(
            "  🔄 Verifying complete interaction flow with conversation validation..."
        )

        await self._validate_stage(stages[0], EXPECTED_DATA_COLLECTION_CONVERSATION)
        print(
            "    ✅ Stage 'data-collection': Progressive conversation structure validated"
        )
        await self._validate_stage(stages[1], EXPECTED_VERIFICATION_CONVERSATION)
        print(
            "    ✅ Stage 'verification': Progressive conversation structure validated"
        )
        await self._validate_stage(stages[2], EXPECTED_ANALYSIS_CONVERSATION)
        print("    ✅ Stage 'analysis': Progressive conversation structure validated")

        print("  ✅ All stages validated with EP-0014 progressive conversation format")

    async def _validate_stage(self, actual_stage, expected_conversation):
        """
        Validate data collection stage using expected conversation structure.

        This stage focuses on gathering comprehensive information using
        DataCollectionAgent with ReAct pattern and tool calls.
        """
        stage_name = actual_stage["stage_name"]
        expected_stage = EXPECTED_STAGES[stage_name]
        llm_interactions = actual_stage.get("llm_interactions", [])
        mcp_interactions = actual_stage.get(
            "mcp_communications", []
        )  # Fixed: use mcp_communications not mcp_interactions

        assert (
            len(llm_interactions) == expected_stage["llm_count"]
        ), f"Stage '{stage_name}': Expected {expected_stage['llm_count']} LLM interactions, got {len(llm_interactions)}"
        assert (
            len(mcp_interactions) == expected_stage["mcp_count"]
        ), f"Stage '{stage_name}': Expected {expected_stage['mcp_count']} MCP interactions, got {len(mcp_interactions)}"

        # Verify complete interaction flow in chronological order
        # Get chronological interactions from API (mixed LLM and MCP in actual order)
        chronological_interactions = actual_stage.get("chronological_interactions", [])
        assert (
            len(chronological_interactions) == len(expected_stage["interactions"])
        ), f"Stage '{stage_name}' chronological interaction count mismatch: expected {len(expected_stage['interactions'])}, got {len(chronological_interactions)}"

        # Track token totals for the stage
        expected_input_tokens = 0
        expected_output_tokens = 0
        expected_total_tokens = 0

        for i, expected_interaction in enumerate(expected_stage["interactions"]):
            actual_interaction = chronological_interactions[i]
            interaction_type = expected_interaction["type"]

            # Verify the type matches
            assert (
                actual_interaction["type"] == interaction_type
            ), f"Stage '{stage_name}' interaction {i+1} type mismatch: expected {interaction_type}, got {actual_interaction['type']}"

            # Verify basic interaction structure
            assert (
                "details" in actual_interaction
            ), f"Stage '{stage_name}' interaction {i+1} missing details"
            details = actual_interaction["details"]
            assert (
                details["success"] == expected_interaction["success"]
            ), f"Stage '{stage_name}' interaction {i+1} success mismatch"

            if interaction_type == "llm":
                # Verify the actual conversation matches the expected conversation
                actual_conversation = details["conversation"]
                actual_messages = actual_conversation["messages"]
                
                if "conversation_index" in expected_interaction:
                    # Use conversation_index to slice from the expected conversation
                    expected_conversation_index = expected_interaction["conversation_index"]
                    assert_conversation_messages(
                        expected_conversation, actual_messages, expected_conversation_index
                    )
                elif "conversation" in expected_interaction:
                    # Use the provided conversation directly (e.g., for summarization)
                    expected_conversation_for_interaction = expected_interaction["conversation"]
                    expected_message_count = len(expected_conversation_for_interaction["messages"])
                    assert_conversation_messages(
                        expected_conversation_for_interaction, actual_messages, expected_message_count
                    )
                else:
                    raise AssertionError(f"Stage '{stage_name}' interaction {i+1} missing both 'conversation_index' and 'conversation' fields")
                
                # Verify interaction_type
                if "interaction_type" in expected_interaction:
                    assert (
                        details.get("interaction_type") == expected_interaction["interaction_type"]
                    ), f"Stage '{stage_name}' interaction {i+1} interaction_type mismatch: expected '{expected_interaction['interaction_type']}', got '{details.get('interaction_type')}'"
                
                # Verify token usage
                if "input_tokens" in expected_interaction:
                    assert (
                        details["input_tokens"] == expected_interaction["input_tokens"]
                    ), f"Stage '{stage_name}' interaction {i+1} input_tokens mismatch: expected {expected_interaction['input_tokens']}, got {details['input_tokens']}"
                    assert (
                        details["output_tokens"] == expected_interaction["output_tokens"]
                    ), f"Stage '{stage_name}' interaction {i+1} output_tokens mismatch: expected {expected_interaction['output_tokens']}, got {details['output_tokens']}"
                    assert (
                        details["total_tokens"] == expected_interaction["total_tokens"]
                    ), f"Stage '{stage_name}' interaction {i+1} total_tokens mismatch: expected {expected_interaction['total_tokens']}, got {details['total_tokens']}"
                    
                    # Accumulate token totals for stage validation
                    expected_input_tokens += expected_interaction["input_tokens"]
                    expected_output_tokens += expected_interaction["output_tokens"]
                    expected_total_tokens += expected_interaction["total_tokens"]
            elif interaction_type == "mcp":
                assert (
                    details["communication_type"]
                    == expected_interaction["communication_type"]
                ), f"Stage '{stage_name}' interaction {i+1} communication_type mismatch"

                assert (
                    details["server_name"] == expected_interaction["server_name"]
                ), f"Stage '{stage_name}' interaction {i+1} server_name mismatch"

                # Verify tool name for tool_call interactions
                if expected_interaction["communication_type"] == "tool_call":
                    assert (
                        details["tool_name"] == expected_interaction["tool_name"]
                    ), f"Stage '{stage_name}' interaction {i+1} tool_name mismatch"
                    
                    # Verify error message for failed interactions
                    if not expected_interaction["success"]:
                        expected_error_message = expected_interaction.get("error_message")
                        actual_error_message = details.get("error_message")
                        assert expected_error_message is not None, f"Stage '{stage_name}' interaction {i+1} expected error but no expected_error_message defined"
                        assert actual_error_message is not None, f"Stage '{stage_name}' interaction {i+1} expected error but no error_message in API response"
                        assert (
                            actual_error_message == expected_error_message
                        ), f"Stage '{stage_name}' interaction {i+1} error_message mismatch: expected '{expected_error_message}', got '{actual_error_message}'"
                        print(f"    ✅ MCP Error message verified: {actual_error_message[:80]}...")

                # Verify tool_list has available_tools
                elif expected_interaction["communication_type"] == "tool_list":
                    assert (
                        "available_tools" in details
                    ), f"Stage '{stage_name}' interaction {i+1} tool_list missing available_tools"
                    assert (
                        len(details["available_tools"]) > 0
                    ), f"Stage '{stage_name}' interaction {i+1} tool_list has no available_tools"

        # Validate stage-level token totals
        actual_stage_input_tokens = actual_stage.get("stage_input_tokens")
        actual_stage_output_tokens = actual_stage.get("stage_output_tokens")
        actual_stage_total_tokens = actual_stage.get("stage_total_tokens")
        
        assert (
            actual_stage_input_tokens == expected_input_tokens
        ), f"Stage '{stage_name}' input_tokens total mismatch: expected {expected_input_tokens}, got {actual_stage_input_tokens}"
        assert (
            actual_stage_output_tokens == expected_output_tokens
        ), f"Stage '{stage_name}' output_tokens total mismatch: expected {expected_output_tokens}, got {actual_stage_output_tokens}"
        assert (
            actual_stage_total_tokens == expected_total_tokens
        ), f"Stage '{stage_name}' total_tokens total mismatch: expected {expected_total_tokens}, got {actual_stage_total_tokens}"

        logger.info(
            "Stage '%s': Complete interaction flow verified (%d LLM, %d MCP)",
            stage_name, len(llm_interactions), len(mcp_interactions)
        )

    async def _test_chat_functionality(self, test_client, session_id: str):
        """Test chat functionality by creating a chat and sending multiple messages."""

        # Step 0: Check chat availability endpoint
        logger.info("Testing chat availability check...")
        
        availability_response = test_client.get(
            f"/api/v1/sessions/{session_id}/chat-available"
        )
        
        assert availability_response.status_code == 200, (
            f"Chat availability check failed with status {availability_response.status_code}: "
            f"{availability_response.text}"
        )
        
        availability_data = availability_response.json()
        assert availability_data.get("available") is True, (
            f"Chat should be available for completed session, but got: {availability_data}"
        )
        assert availability_data.get("chat_id") is None, (
            "Chat ID should be None before chat is created"
        )

        logger.info("Chat availability verified (available=True, no existing chat)")

        # Step 1: Create chat for the session
        logger.info("Testing chat creation...")
        
        create_chat_response = test_client.post(
            f"/api/v1/sessions/{session_id}/chat",
            headers={"X-Forwarded-User": "test-user@example.com"}
        )
        
        assert create_chat_response.status_code == 200, (
            f"Chat creation failed with status {create_chat_response.status_code}: "
            f"{create_chat_response.text}"
        )
        
        chat_data = create_chat_response.json()
        chat_id = chat_data.get("chat_id")
        
        assert chat_id is not None, "Chat ID missing from creation response"
        assert chat_data.get("session_id") == session_id, "Chat session_id mismatch"
        assert chat_data.get("created_by") == "test-user@example.com", (
            f"Chat created_by mismatch: expected 'test-user@example.com', "
            f"got '{chat_data.get('created_by')}'"
        )
        
        logger.info("Chat created successfully: %s", chat_id)

        # Step 1b: Verify chat availability now returns existing chat_id
        logger.info("Re-checking chat availability after creation...")
        
        availability_response2 = test_client.get(
            f"/api/v1/sessions/{session_id}/chat-available"
        )
        
        assert availability_response2.status_code == 200, (
            f"Chat availability check failed after creation: {availability_response2.text}"
        )
        
        availability_data2 = availability_response2.json()
        assert availability_data2.get("available") is True, (
            "Chat should still be available after creation"
        )
        assert availability_data2.get("chat_id") == chat_id, (
            f"Chat availability should return existing chat_id={chat_id}, "
            f"got {availability_data2.get('chat_id')}"
        )
        
        logger.info("Chat availability updated (available=True, chat_id=%s)", chat_id)

        # Step 1c: Test GET /api/v1/chats/{chat_id} endpoint
        logger.info("Testing get chat details endpoint...")
        
        get_chat_response = test_client.get(f"/api/v1/chats/{chat_id}")
        
        assert get_chat_response.status_code == 200, (
            f"Get chat details failed with status {get_chat_response.status_code}: "
            f"{get_chat_response.text}"
        )
        
        get_chat_data = get_chat_response.json()
        assert get_chat_data.get("chat_id") == chat_id, "Chat ID mismatch"
        assert get_chat_data.get("session_id") == session_id, "Session ID mismatch"
        assert get_chat_data.get("message_count") == 0, "Initial message count should be 0"

        logger.info("Chat details retrieved (message_count=0)")

        # Track verified chat stages to avoid re-checking them
        verified_chat_stage_ids = set()

        # Step 2: Send first chat message and verify response
        logger.info("Sending first chat message...")
        
        message_1_stage = await self._send_and_wait_for_chat_message(
            test_client=test_client,
            session_id=session_id,
            chat_id=chat_id,
            content="Can you check the pods in the stuck-namespace?",
            message_label="Message 1",
            verified_stage_ids=verified_chat_stage_ids
        )
        
        logger.info("Verifying first chat response...")
        await self._verify_chat_response(
            chat_stage=message_1_stage,
            message_key='message_1',
            expected_conversation=EXPECTED_CHAT_MESSAGE_1_CONVERSATION
        )
        verified_chat_stage_ids.add(message_1_stage.get("stage_id"))
        logger.info("First chat response verified")

        # Step 3: Send second chat message (follow-up) and verify response
        logger.info("Sending second chat message (follow-up)...")
        
        message_2_stage = await self._send_and_wait_for_chat_message(
            test_client=test_client,
            session_id=session_id,
            chat_id=chat_id,
            content="Does the namespace still exist?",
            message_label="Message 2",
            verified_stage_ids=verified_chat_stage_ids
        )
        
        logger.info("Verifying second chat response...")
        await self._verify_chat_response(
            chat_stage=message_2_stage,
            message_key='message_2',
            expected_conversation=EXPECTED_CHAT_MESSAGE_2_CONVERSATION
        )
        verified_chat_stage_ids.add(message_2_stage.get("stage_id"))
        logger.info("Second chat response verified")

        # Step 4: Test GET /api/v1/chats/{chat_id}/messages endpoint
        logger.info("Testing get chat message history endpoint...")
        
        messages_response = test_client.get(
            f"/api/v1/chats/{chat_id}/messages?limit=10&offset=0"
        )
        
        assert messages_response.status_code == 200, (
            f"Get chat messages failed with status {messages_response.status_code}: "
            f"{messages_response.text}"
        )
        
        messages_data = messages_response.json()
        assert messages_data.get("chat_id") == chat_id, "Chat ID mismatch in messages response"
        assert messages_data.get("total_count") == 2, (
            f"Expected 2 messages in history, got {messages_data.get('total_count')}"
        )
        
        messages = messages_data.get("messages", [])
        assert len(messages) == 2, f"Expected 2 messages in response, got {len(messages)}"
        
        # Verify first message content
        assert messages[0].get("content") == "Can you check the pods in the stuck-namespace?", (
            "First message content mismatch"
        )
        assert messages[0].get("author") == "test-user@example.com", "First message author mismatch"
        
        # Verify second message content
        assert messages[1].get("content") == "Does the namespace still exist?", (
            "Second message content mismatch"
        )
        assert messages[1].get("author") == "test-user@example.com", "Second message author mismatch"

        logger.info("Chat message history retrieved (2 messages)")

        # Step 5: Verify chat_message_count appears in sessions list
        logger.info("Testing chat_message_count in sessions list...")
        
        sessions_response = test_client.get("/api/v1/history/sessions?page=1&page_size=50")
        
        assert sessions_response.status_code == 200, (
            f"Get sessions failed with status {sessions_response.status_code}: "
            f"{sessions_response.text}"
        )
        
        sessions_data = sessions_response.json()
        sessions = sessions_data.get("sessions", [])
        
        # Find our session in the list
        our_session = None
        for session in sessions:
            if session.get("session_id") == session_id:
                our_session = session
                break
        
        assert our_session is not None, f"Session {session_id} not found in sessions list"
        assert our_session.get("chat_message_count") == 2, (
            f"Expected chat_message_count=2 for session with 2 messages, "
            f"got {our_session.get('chat_message_count')}"
        )

        logger.info("Sessions list includes chat_message_count=2")

        logger.info("Chat functionality test completed (2 messages, all endpoints tested)")
    
    async def _send_and_wait_for_chat_message(
        self,
        test_client,
        session_id: str,
        chat_id: str,
        content: str,
        message_label: str = "Message",
        verified_stage_ids: set = None
    ):
        """
        Send a chat message and wait for the response stage to complete.
        
        Args:
            verified_stage_ids: Set of stage IDs that have already been verified
                               to avoid matching them again
        
        Returns:
            The completed chat stage for verification
        """
        if verified_stage_ids is None:
            verified_stage_ids = set()
        
        # Get current chat stage count before sending message
        detail_data = await E2ETestUtils.get_session_details_async(test_client, session_id)
        stages_before = [s for s in detail_data.get("stages", []) 
                        if s.get("stage_id", "").startswith("chat-response")]
        num_stages_before = len(stages_before)
        
        # Send the message (author comes from auth header, not JSON body)
        send_message_response = test_client.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": content},
            headers={"X-Forwarded-User": "test-user@example.com"}
        )
        
        assert send_message_response.status_code == 200, (
            f"{message_label} failed with status {send_message_response.status_code}: "
            f"{send_message_response.text}"
        )
        
        message_data = send_message_response.json()
        message_id = message_data.get("message_id")
        
        assert message_id is not None, f"{message_label} ID missing from response"

        logger.info("%s sent: %s", message_label, message_id)

        # Wait for a NEW chat stage to appear and complete
        logger.info("Waiting for %s response...", message_label.lower())
        
        max_wait = 15  # seconds (increased for chat processing)
        poll_interval = 0.5  # seconds
        
        chat_stage = None
        for i in range(int(max_wait / poll_interval)):
            # Get session details to check chat execution
            detail_data = await E2ETestUtils.get_session_details_async(test_client, session_id)
            stages = detail_data.get("stages", [])
            
            # Look for NEW chat stages (not already verified)
            # Search from the end since newer stages are added last
            for stage in reversed(stages):
                stage_id = stage.get("stage_id", "")
                if (stage_id.startswith("chat-response") and
                    stage_id not in verified_stage_ids and
                    stage.get("chat_id") == chat_id):
                    chat_stage = stage
                    break
            
            if chat_stage:
                if chat_stage.get("status") == "completed":
                    logger.info("%s response completed in %.1fs", message_label, (i+1) * poll_interval)
                    break
                # If found but not completed, continue waiting
            
            await asyncio.sleep(poll_interval)
        else:
            # Provide more debug info on timeout
            detail_data = await E2ETestUtils.get_session_details_async(test_client, session_id)
            stages = detail_data.get("stages", [])
            chat_stages = [s for s in stages if s.get("stage_id", "").startswith("chat-response")]
            new_stages = [s for s in chat_stages if s.get("stage_id") not in verified_stage_ids]
            debug_info = []
            for cs in new_stages:
                debug_info.append(
                    f"stage_id={cs.get('stage_id')}, "
                    f"chat_id={cs.get('chat_id')}, "
                    f"status={cs.get('status')}"
                )
            raise AssertionError(
                f"{message_label} response did not complete within {max_wait}s. "
                f"Started with {num_stages_before} stages, now have {len(chat_stages)} total, "
                f"{len(new_stages)} new (unverified) stages: {debug_info}"
            )
        
        return chat_stage

    async def _verify_chat_response(
        self,
        chat_stage,
        message_key: str,
        expected_conversation: dict
    ):
        """
        Verify the structure of a chat response using the same pattern as stage verification.
        
        Args:
            chat_stage: The chat stage execution data from the API
            message_key: Key to look up expected interactions (e.g., 'message_1', 'message_2')
            expected_conversation: Expected conversation structure for this message
        """
        # Verify basic stage structure
        assert chat_stage is not None, "Chat stage not found"
        assert chat_stage.get("agent") == "ChatAgent", (
            f"Expected ChatAgent, got {chat_stage.get('agent')}"
        )
        assert chat_stage.get("status") == "completed", (
            f"Chat stage not completed: {chat_stage.get('status')}"
        )
        
        # Verify chat-specific fields
        assert chat_stage.get("chat_id") is not None, "Chat ID missing from stage"
        assert chat_stage.get("chat_user_message_id") is not None, (
            "Chat user message ID missing from stage"
        )
        
        # Verify embedded user message data (added in user message display feature)
        chat_user_message = chat_stage.get("chat_user_message")
        assert chat_user_message is not None, (
            "Chat user message data missing from stage - should be embedded"
        )
        assert chat_user_message.get("message_id") is not None, "User message ID missing"
        assert chat_user_message.get("content") is not None, "User message content missing"
        assert chat_user_message.get("author") == "test-user@example.com", (
            f"User message author mismatch: expected 'test-user@example.com', "
            f"got '{chat_user_message.get('author')}'"
        )
        assert chat_user_message.get("created_at_us") > 0, "User message timestamp invalid"
        
        # Verify the content matches what we expect for each message
        expected_content_map = {
            'message_1': "Can you check the pods in the stuck-namespace?",
            'message_2': "Does the namespace still exist?"
        }
        expected_content = expected_content_map.get(message_key)
        if expected_content:
            assert chat_user_message.get("content") == expected_content, (
                f"User message content mismatch for {message_key}: "
                f"expected '{expected_content}', got '{chat_user_message.get('content')}'"
            )
        
        # Get expected interactions for this message
        expected_chat = EXPECTED_CHAT_INTERACTIONS[message_key]
        llm_interactions = chat_stage.get("llm_interactions", [])
        mcp_interactions = chat_stage.get("mcp_communications", [])
        
        # Verify interaction counts
        assert len(llm_interactions) == expected_chat["llm_count"], (
            f"Chat {message_key}: Expected {expected_chat['llm_count']} LLM interactions, "
            f"got {len(llm_interactions)}"
        )
        assert len(mcp_interactions) == expected_chat["mcp_count"], (
            f"Chat {message_key}: Expected {expected_chat['mcp_count']} MCP interactions, "
            f"got {len(mcp_interactions)}"
        )
        
        # Verify complete interaction flow in chronological order
        chronological_interactions = chat_stage.get("chronological_interactions", [])
        assert len(chronological_interactions) == len(expected_chat["interactions"]), (
            f"Chat {message_key} chronological interaction count mismatch: "
            f"expected {len(expected_chat['interactions'])}, got {len(chronological_interactions)}"
        )
        
        # Track token totals
        expected_input_tokens = 0
        expected_output_tokens = 0
        expected_total_tokens = 0
        
        for i, expected_interaction in enumerate(expected_chat["interactions"]):
            actual_interaction = chronological_interactions[i]
            interaction_type = expected_interaction["type"]
            
            # Verify the type matches
            assert actual_interaction["type"] == interaction_type, (
                f"Chat {message_key} interaction {i+1} type mismatch: "
                f"expected {interaction_type}, got {actual_interaction['type']}"
            )
            
            details = actual_interaction["details"]
            assert details["success"] == expected_interaction["success"], (
                f"Chat {message_key} interaction {i+1} success mismatch"
            )
            
            if interaction_type == "llm":
                # Verify the actual conversation matches the expected conversation
                actual_conversation = details["conversation"]
                actual_messages = actual_conversation["messages"]
                
                if "conversation_index" in expected_interaction:
                    # Use conversation_index to slice from the expected conversation
                    expected_conversation_index = expected_interaction["conversation_index"]
                    assert_conversation_messages(
                        expected_conversation, actual_messages, expected_conversation_index
                    )
                elif "conversation" in expected_interaction:
                    # Use the provided conversation directly
                    expected_conversation_for_interaction = expected_interaction["conversation"]
                    expected_message_count = len(expected_conversation_for_interaction["messages"])
                    assert_conversation_messages(
                        expected_conversation_for_interaction, actual_messages, expected_message_count
                    )
                else:
                    raise AssertionError(
                        f"Chat {message_key} interaction {i+1} missing both "
                        "'conversation_index' and 'conversation' fields"
                    )
                
                # Verify token usage
                if "input_tokens" in expected_interaction:
                    assert details["input_tokens"] == expected_interaction["input_tokens"], (
                        f"Chat {message_key} interaction {i+1} input_tokens mismatch: "
                        f"expected {expected_interaction['input_tokens']}, got {details['input_tokens']}"
                    )
                    assert details["output_tokens"] == expected_interaction["output_tokens"], (
                        f"Chat {message_key} interaction {i+1} output_tokens mismatch: "
                        f"expected {expected_interaction['output_tokens']}, got {details['output_tokens']}"
                    )
                    assert details["total_tokens"] == expected_interaction["total_tokens"], (
                        f"Chat {message_key} interaction {i+1} total_tokens mismatch: "
                        f"expected {expected_interaction['total_tokens']}, got {details['total_tokens']}"
                    )
                    
                    # Accumulate token totals
                    expected_input_tokens += expected_interaction["input_tokens"]
                    expected_output_tokens += expected_interaction["output_tokens"]
                    expected_total_tokens += expected_interaction["total_tokens"]
                    
            elif interaction_type == "mcp":
                assert details["communication_type"] == expected_interaction["communication_type"], (
                    f"Chat {message_key} interaction {i+1} communication_type mismatch"
                )
                assert details["server_name"] == expected_interaction["server_name"], (
                    f"Chat {message_key} interaction {i+1} server_name mismatch"
                )
                
                # Verify tool name for tool_call interactions
                if expected_interaction["communication_type"] == "tool_call":
                    assert details["tool_name"] == expected_interaction["tool_name"], (
                        f"Chat {message_key} interaction {i+1} tool_name mismatch"
                    )
        
        # Validate stage-level token totals
        actual_stage_input_tokens = chat_stage.get("stage_input_tokens")
        actual_stage_output_tokens = chat_stage.get("stage_output_tokens")
        actual_stage_total_tokens = chat_stage.get("stage_total_tokens")
        
        assert actual_stage_input_tokens == expected_input_tokens, (
            f"Chat {message_key} input_tokens total mismatch: "
            f"expected {expected_input_tokens}, got {actual_stage_input_tokens}"
        )
        assert actual_stage_output_tokens == expected_output_tokens, (
            f"Chat {message_key} output_tokens total mismatch: "
            f"expected {expected_output_tokens}, got {actual_stage_output_tokens}"
        )
        assert actual_stage_total_tokens == expected_total_tokens, (
            f"Chat {message_key} total_tokens total mismatch: "
            f"expected {expected_total_tokens}, got {actual_stage_total_tokens}"
        )
        
        print(
            f"    ✅ Chat {message_key} validated: {len(llm_interactions)} LLM, "
            f"{len(mcp_interactions)} MCP interactions"
        )