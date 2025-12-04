"""
End-to-End Test for Native Thinking Controller (Gemini SDK).

This test uses the real FastAPI application with real internal services,
mocking only external dependencies at the network boundary.

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: Google Gemini SDK (native thinking API), MCP servers, GitHub runbooks

Key Differences from ReAct Tests:
- Uses GeminiNativeThinkingClient instead of LangChain astream
- Native function calling (structured) instead of text parsing
- Thinking content captured separately from response
- Different system prompts (no ReAct format instructions)
"""

import asyncio
import logging
import os
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import Tool

from tarsy.config.builtin_config import BUILTIN_MCP_SERVERS
from tarsy.integrations.mcp.client import MCPClient

from .conftest import create_native_thinking_response, MockGeminiClient
from .e2e_utils import E2ETestUtils
from .expected_native_thinking_conversations import (
    EXPECTED_NATIVE_THINKING_CHAT_INTERACTIONS,
    EXPECTED_NATIVE_THINKING_CHAT_MESSAGE_1_CONVERSATION,
    EXPECTED_NATIVE_THINKING_CHAT_MESSAGE_2_CONVERSATION,
    EXPECTED_NATIVE_THINKING_DATA_COLLECTION_CONVERSATION,
    EXPECTED_NATIVE_THINKING_EXECUTIVE_SUMMARY_CONVERSATION,
    EXPECTED_NATIVE_THINKING_SESSION_LEVEL_INTERACTIONS,
    EXPECTED_NATIVE_THINKING_STAGES,
    EXPECTED_NATIVE_THINKING_ANALYSIS_CONVERSATION,
    EXPECTED_NATIVE_THINKING_VERIFICATION_CONVERSATION,
    EXPECTED_THINKING_CONTENT,
)

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
class TestNativeThinkingE2E:
    """
    E2E test for native thinking controller using Gemini SDK.

    Tests the complete system flow:
    1. HTTP POST to /api/v1/alerts endpoint
    2. Real alert processing through AlertService
    3. Real agent execution with native thinking controller
    4. Real database storage via HistoryService
    5. HTTP GET from history APIs

    Mocks only external calls (Gemini SDK, runbooks, MCP servers).
    """

    @pytest.mark.e2e
    async def test_complete_native_thinking_flow(
        self, e2e_native_thinking_test_client, e2e_native_thinking_alert
    ):
        """
        Complete E2E test for native thinking controller.

        Flow:
        1. POST alert to /api/v1/alerts -> queued
        2. Wait for processing to complete
        3. Verify session was created and completed
        4. Verify stage structure and interactions
        5. Test chat functionality
        6. Test final-analysis endpoint

        This test verifies:
        - Native thinking controller works end-to-end
        - Thinking content is captured correctly
        - Native function calling works
        - Token tracking is accurate
        - Chat with native thinking works
        """

        # Wrap entire test in timeout to prevent hanging
        async def run_test():
            print("🚀 Starting native thinking E2E test...")
            result = await self._execute_test(
                e2e_native_thinking_test_client, e2e_native_thinking_alert
            )
            print("✅ Native thinking E2E test completed!")
            return result

        try:
            task = asyncio.create_task(run_test())
            done, pending = await asyncio.wait({task}, timeout=500.0)

            if pending:
                for t in pending:
                    t.cancel()
                print("❌ HARDCORE TIMEOUT: Test exceeded 500 seconds!")
                raise AssertionError("Test exceeded hardcore timeout of 500 seconds")
            else:
                return task.result()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            raise

    async def _execute_test(self, e2e_test_client, e2e_native_thinking_alert):
        """Execute test with mocked Gemini SDK and MCP."""
        print("🔧 _execute_test started (native thinking)")

        # Track all Gemini API interactions
        all_gemini_interactions = []

        # Define mock response map for Gemini native thinking
        # Each response includes: text_content, thinking_content, function_calls
        # 
        # IMPORTANT: In real Gemini behavior:
        # - When making a tool call: text_content is EMPTY, function_calls present, thinking_content present
        # - When providing final answer: text_content has content, NO function_calls, thinking_content present
        # - Thinking content is ALWAYS present (it's the internal reasoning)
        # 
        # The flow is:
        # Data collection: 1 (tool) -> 2 (tool) -> [LangChain summarization] -> 3 (tool) -> 4 (final)
        # Verification: 5 (tool) -> 6 (final)
        # Analysis: 7 (final, no tools)
        # [LangChain executive summary]
        # Chat 1: 8 (tool) -> 9 (final)
        # Chat 2: 10 (tool) -> 11 (final)
        mock_response_map = {
            1: {  # Data collection - Initial tool call (NO text_content when calling tools)
                "text_content": "",  # Empty when making tool calls - matches real Gemini behavior
                "thinking_content": "The alert mentions a namespace stuck in Terminating state. I should first check the namespace status using kubectl_get to understand its current state.",
                "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "namespaces", "name": "stuck-namespace"}}],
                "input_tokens": 245, "output_tokens": 85, "total_tokens": 330
            },
            2: {  # Data collection - Second tool call (collect system info)
                "text_content": "",  # Empty when making tool calls
                "thinking_content": "The namespace is in Terminating state for 45 minutes - that's quite long. I should collect more information about the system to understand if there are resource constraints affecting the cleanup.",
                "function_calls": [{"name": "test-data-server__collect_system_info", "args": {"detailed": False}}],
                "input_tokens": 180, "output_tokens": 65, "total_tokens": 245
            },
            # Note: Summarization happens via LangChain (separate mock), not Gemini
            3: {  # Data collection - Third tool call (events) after summarization
                "text_content": "",  # Empty when making tool calls
                "thinking_content": "System resources are fine - CPU, memory and disk look healthy. The issue must be with the namespace itself, possibly finalizers. Let me check events to see what's blocking the deletion.",
                "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "events", "namespace": "test-namespace"}}],
                "input_tokens": 200, "output_tokens": 60, "total_tokens": 260
            },
            4: {  # Data collection - Final answer (text_content present, NO function_calls)
                "text_content": "Based on the collected data, namespace 'stuck-namespace' is stuck in Terminating state due to finalizers blocking deletion.",
                "thinking_content": "I have gathered enough information. The namespace is stuck due to finalizers (kubernetes.io/pv-protection). I can now provide the final analysis for this data collection stage.",
                "function_calls": None,
                "input_tokens": 315, "output_tokens": 125, "total_tokens": 440
            },
            5: {  # Verification - Tool call
                "text_content": "",  # Empty when making tool calls
                "thinking_content": "I need to verify the findings from the data collection stage by checking the current namespace status. This will confirm whether the namespace is still in Terminating state.",
                "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "namespaces", "name": "stuck-namespace"}}],
                "input_tokens": 190, "output_tokens": 70, "total_tokens": 260
            },
            6: {  # Verification - Final answer
                "text_content": "Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion.",
                "thinking_content": "The namespace is still in Terminating state after 45 minutes, confirming our findings. The finalizers (kubernetes.io/pv-protection) are indeed blocking the namespace deletion.",
                "function_calls": None,
                "input_tokens": 280, "output_tokens": 110, "total_tokens": 390
            },
            7: {  # Analysis - Final (no tools)
                "text_content": "Based on previous stages, the namespace is stuck due to finalizers.",
                "thinking_content": "Synthesizing all the data from the data-collection and verification stages. The root cause is clear: kubernetes.io/pv-protection finalizers are blocking namespace deletion. The namespace has been stuck for 45 minutes.",
                "function_calls": None,
                "input_tokens": 420, "output_tokens": 180, "total_tokens": 600
            },
            # Note: Executive summary happens via LangChain (separate mock), not Gemini
            8: {  # Chat message 1 - Tool call
                "text_content": "",  # Empty when making tool calls
                "thinking_content": "User wants to see pods in the stuck-namespace. I'll use kubectl_get to list the pods and see what's running there.",
                "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "pods", "namespace": "stuck-namespace"}}],
                "input_tokens": 150, "output_tokens": 60, "total_tokens": 210
            },
            9: {  # Chat message 1 - Final answer
                "text_content": "I checked the pods in stuck-namespace and found no pods are currently running. This is consistent with the namespace being stuck in Terminating state - all pods have likely been deleted already, but the namespace can't complete deletion due to the finalizers mentioned in the original investigation.",
                "thinking_content": "No pods found in the namespace. This makes sense - the namespace is terminating and all workload pods have been cleaned up already. The finalizers are what's blocking the final deletion of the namespace itself.",
                "function_calls": None,
                "input_tokens": 180, "output_tokens": 90, "total_tokens": 270
            },
            10: {  # Chat message 2 - Tool call
                "text_content": "",  # Empty when making tool calls
                "thinking_content": "User wants to know if the namespace still exists. I'll check its current status to see if it's still in Terminating or has been deleted.",
                "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "namespaces", "name": "stuck-namespace"}}],
                "input_tokens": 200, "output_tokens": 70, "total_tokens": 270
            },
            11: {  # Chat message 2 - Final answer
                "text_content": "Yes, the namespace still exists and remains in Terminating state. Based on the investigation history, the namespace is blocked by finalizers (kubernetes.io/pvc-protection). To resolve this, you would need to manually remove the finalizers using kubectl patch or edit the namespace resource directly.",
                "thinking_content": "The namespace still exists and is stuck in Terminating state, just as expected. I should explain the resolution steps to help the user fix this issue.",
                "function_calls": None,
                "input_tokens": 220, "output_tokens": 95, "total_tokens": 315
            },
        }

        # Use a shared counter so all client instances increment the same counter
        shared_call_counter = [0]  # Use list to allow mutation in nested function
        
        def create_gemini_mock_client(api_key: str = "test-api-key"):
            """Create a mock Gemini client that returns our test responses."""
            
            def response_generator(call_num_ignored: int, model: str, contents: list, config):
                """Generate response based on shared call number."""
                # Use shared counter instead of per-client counter
                shared_call_counter[0] += 1
                call_num = shared_call_counter[0]
                all_gemini_interactions.append(call_num)
                
                print(f"\n🔍 GEMINI REQUEST #{call_num}:")
                if contents:
                    for i, content in enumerate(contents[:3]):  # Show first 3
                        role = getattr(content, 'role', 'unknown')
                        parts = getattr(content, 'parts', [])
                        text = parts[0].text[:100] if parts and hasattr(parts[0], 'text') else "..."
                        print(f"  Content {i+1} ({role}): {text}...")
                print("=" * 80)
                
                response_data = mock_response_map.get(call_num, {
                    "text_content": "",
                    "thinking_content": None,
                    "function_calls": None,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0
                })
                
                return create_native_thinking_response(
                    text_content=response_data.get("text_content", ""),
                    thinking_content=response_data.get("thinking_content"),
                    function_calls=response_data.get("function_calls"),
                    thought_signature=response_data.get("thought_signature"),
                    input_tokens=response_data.get("input_tokens", 100),
                    output_tokens=response_data.get("output_tokens", 50),
                    total_tokens=response_data.get("total_tokens", 150)
                )
            
            return MockGeminiClient(response_generator, api_key)

        # Create MCP session mocks
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
                    elif resource == "pods" and namespace == "stuck-namespace":
                        mock_content = Mock()
                        mock_content.text = "No pods found in namespace stuck-namespace"
                        mock_result.content = [mock_content]
                    elif resource == "events":
                        mock_content = Mock()
                        mock_content.text = "Mock kubectl get events response"
                        mock_result.content = [mock_content]
                    else:
                        mock_content = Mock()
                        mock_content.text = f"Mock kubectl get {resource} response"
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
                if tool_name == "collect_system_info":
                    # Return a large result that exceeds summarization threshold
                    large_system_info = """Long System Information Report - more than 100 tokens
8wHXXQkrjqtaYwXb3KdmeOapEKU27hMiaYvzT25SI4MexrI2SC9gFLsKie0eDxH5WEVV7TvDCWjOrD2egFSykp2eRP2u9jVwUqzgOVULB6WAnTKol7vmIii9F7gCWoKMXnJsh12fppgIWJAbFw5vYuv7JIQMargw3vxFZO699z3t0hiYPtcLyeSXyyIf0lIxl8lOmKLsYA4TBZiSwZ6V5NV1cZ2VQeMxDOLN4F6kjTaqCtTc7zGCYzvHlv9BaCVB4SXo26yfg3r2G7sCRjexj0EvKGxnYecJiJoEtqD01pCCBrlQC8esGoG15NaMlFCWIsbdJmADZOR0WUYOcOhNk0WOtASqzHJBIfnGVYYxGMq0A5DkPGbUe4UXYPNEnD0xZ7YcEYGKAmdYmx2F2BgMi2NYXcelZ1Ym1Ukx2zGZoiKVmBdutnWr2ManM0PnChDLj0SyIZGdmhZhOn5R9uB3HpbCXsKzw4gUYiU9EvwW2m22pe6zKTSCpyhI4rVG5fFwrehWEbuB8nTbI3eawqQQevCbal42ko0GBG1sjE2GIDn7jmwJEBImlxRkuHoyWvMqfLDn9RbGXzhtnlO7sKZEb9He"""
                    return {
                        "result": large_system_info.strip()
                    }
                else:
                    return {"result": f"Mock response for custom tool: {tool_name}"}

            async def mock_list_tools():
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

                mock_result = Mock()
                mock_result.tools = [mock_tool]
                return mock_result

            mock_session.call_tool.side_effect = mock_call_tool
            mock_session.list_tools.side_effect = mock_list_tools

            return mock_session

        # Create mock MCP sessions
        mock_kubernetes_session = create_mcp_session_mock()
        mock_custom_session = create_custom_mcp_session_mock()

        # Create test MCP server configurations
        k8s_config = E2ETestUtils.create_simple_kubernetes_mcp_config(
            command_args=["kubernetes-mock-server-ready"],
            instructions="Test kubernetes server for native thinking e2e testing"
        )
        data_config = E2ETestUtils.create_simple_data_server_mcp_config(
            command_args=["test-data-server-ready"],
            instructions="Simple data collection server for testing - provides system information gathering tools"
        )

        test_mcp_servers = E2ETestUtils.create_test_mcp_servers(BUILTIN_MCP_SERVERS, {
            "kubernetes-server": k8s_config,
            "test-data-server": data_config
        })

        # Create streaming mock for LangChain clients (used by summarizer and executive summary)
        from .conftest import create_mock_stream
        
        def create_langchain_streaming_mock():
            """Create a mock astream function for LangChain clients."""
            langchain_call_counter = [0]
            
            # LangChain responses: 1st call = summarization, 2nd call = executive summary
            langchain_responses = {
                1: "Summarized: System healthy, CPU 45%, Memory 33%, Disk 76%, Network OK.",
                2: "The namespace stuck-namespace is in Terminating state due to finalizers blocking deletion.",
            }
            
            async def mock_astream(*args, **kwargs):
                langchain_call_counter[0] += 1
                call_num = langchain_call_counter[0]
                
                # Get appropriate response based on call number
                content = langchain_responses.get(call_num, f"Mock LangChain response #{call_num}")
                usage_metadata = {
                    'input_tokens': 100,
                    'output_tokens': 50,
                    'total_tokens': 150
                }
                
                async for chunk in create_mock_stream(content, usage_metadata):
                    yield chunk
            
            return mock_astream

        # Apply comprehensive mocking
        with patch("tarsy.config.builtin_config.BUILTIN_MCP_SERVERS", test_mcp_servers), \
             patch("tarsy.services.mcp_server_registry.MCPServerRegistry._DEFAULT_SERVERS", test_mcp_servers), \
             patch.dict(os.environ, {}, clear=True), \
             E2ETestUtils.setup_runbook_service_patching():

            # Mock LangChain streaming (used by summarizer)
            langchain_streaming_mock = create_langchain_streaming_mock()
            
            # Import LangChain clients to patch
            from langchain_anthropic import ChatAnthropic
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_openai import ChatOpenAI
            from langchain_xai import ChatXAI

            # Mock Gemini SDK - patch the genai.Client constructor
            with patch("google.genai.Client", create_gemini_mock_client), \
                 patch.object(ChatOpenAI, 'astream', langchain_streaming_mock), \
                 patch.object(ChatAnthropic, 'astream', langchain_streaming_mock), \
                 patch.object(ChatXAI, 'astream', langchain_streaming_mock), \
                 patch.object(ChatGoogleGenerativeAI, 'astream', langchain_streaming_mock):
                
                # Mock MCP client
                mock_sessions = {
                    "kubernetes-server": mock_kubernetes_session,
                    "test-data-server": mock_custom_session,
                }
                mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

                async def mock_initialize(self):
                    """Mock initialization that bypasses real server startup."""
                    self.sessions = mock_sessions.copy()
                    self._initialized = True

                with patch.object(MCPClient, "initialize", mock_initialize), \
                     patch.object(MCPClient, "list_tools", mock_list_tools), \
                     patch.object(MCPClient, "call_tool", mock_call_tool):
                    
                    print("🔧 Using native thinking with mocked Gemini SDK...")

                    print("⏳ Step 1: Submitting alert...")
                    E2ETestUtils.submit_alert(e2e_test_client, e2e_native_thinking_alert)

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

                    # Assert that stages exist
                    assert (
                        len(stages) > 0
                    ), "Session completed but no stages found"
                    print("✅ Session has stages - basic structure verified")

                    print("🔍 Step 4: Comprehensive result verification...")
                    await self._verify_session_metadata(
                        detail_data, e2e_native_thinking_alert
                    )
                    await self._verify_session_level_interactions(detail_data)
                    await self._verify_stage_structure(stages)
                    await self._verify_complete_interaction_flow(stages)

                    print("✅ COMPREHENSIVE VERIFICATION PASSED!")

                    print("🔍 Step 5: Testing chat functionality...")
                    await self._test_chat_functionality(e2e_test_client, session_id)

                    print("✅ CHAT FUNCTIONALITY TEST PASSED!")

                    print("🔍 Step 6: Testing final-analysis endpoint...")
                    await self._test_final_analysis_endpoint(e2e_test_client, session_id)

                    print("✅ FINAL ANALYSIS ENDPOINT TEST PASSED!")

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
            session_data["chain_id"] == "native-thinking-kubernetes-chain"
        ), f"Unexpected chain_id: {session_data['chain_id']}"

        # Verify timestamps are reasonable
        started_at = session_data["started_at_us"]
        completed_at = session_data["completed_at_us"]
        assert started_at > 0, "Invalid started_at timestamp"
        assert completed_at > started_at, "completed_at should be after started_at"

        # Processing duration should be reasonable
        processing_duration_ms = (completed_at - started_at) / 1000
        assert (
            processing_duration_ms < 10000
        ), f"Processing took too long: {processing_duration_ms}ms"

        # Verify session-level token usage totals
        # Calculated from mock responses: 7 Gemini calls + 2 LangChain calls (summarization + executive)
        # Gemini: 245+180+200+315+190+280+420 = 1830 input, 85+65+60+125+70+110+180 = 695 output
        # LangChain: 100+100 = 200 input, 50+50 = 100 output
        # Total: 2030 input, 795 output, 2825 total
        expected_session_input_tokens = 2030
        expected_session_output_tokens = 795
        expected_session_total_tokens = 2825
        
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

    def _verify_interactions(
        self,
        interactions: list,
        expected_spec: dict,
        context_label: str,
        expected_conversation: dict = None,
        stage_name: str = None
    ) -> tuple[int, int, int]:
        """
        Verify a list of interactions (LLM and MCP) against expected specification.
        
        Args:
            interactions: Actual interactions from session data
            expected_spec: Expected interaction specification
            context_label: Label for error messages
            expected_conversation: Expected conversation structure
            stage_name: Stage name for thinking content verification
        
        Returns:
            Tuple of (input_tokens, output_tokens, total_tokens) accumulated from LLM interactions
        """
        expected_input_tokens = 0
        expected_output_tokens = 0
        expected_total_tokens = 0
        
        llm_position_counter = 0  # Track LLM position for thinking content lookup
        
        for i, expected_interaction in enumerate(expected_spec["interactions"]):
            actual_interaction = interactions[i]
            interaction_type = expected_interaction["type"]
            
            # Verify the type matches
            assert actual_interaction["type"] == interaction_type, (
                f"{context_label} interaction {i+1} type mismatch: expected {interaction_type}, "
                f"got {actual_interaction['type']}"
            )
            
            # Verify basic interaction structure
            assert "details" in actual_interaction, (
                f"{context_label} interaction {i+1} missing details"
            )
            details = actual_interaction["details"]
            assert details["success"] == expected_interaction["success"], (
                f"{context_label} interaction {i+1} success mismatch"
            )
            
            if interaction_type == "llm":
                llm_position_counter += 1
                
                # Verify the actual conversation matches expected
                actual_conversation = details["conversation"]
                actual_messages = actual_conversation["messages"]
                
                if "conversation_index" in expected_interaction:
                    assert expected_conversation is not None, (
                        f"{context_label} interaction {i+1} has conversation_index but no expected_conversation"
                    )
                    expected_conversation_index = expected_interaction["conversation_index"]
                    assert_conversation_messages(
                        expected_conversation, actual_messages, expected_conversation_index
                    )
                elif expected_interaction.get("conversation") == "SUMMARIZATION":
                    # Skip conversation verification for summarization (different format)
                    pass
                elif "conversation" in expected_interaction:
                    expected_conversation_for_interaction = expected_interaction["conversation"]
                    expected_message_count = len(expected_conversation_for_interaction["messages"])
                    assert_conversation_messages(
                        expected_conversation_for_interaction, actual_messages, expected_message_count
                    )
                
                # Verify interaction_type
                if "interaction_type" in expected_interaction:
                    assert details.get("interaction_type") == expected_interaction["interaction_type"], (
                        f"{context_label} interaction {i+1} interaction_type mismatch: "
                        f"expected '{expected_interaction['interaction_type']}', "
                        f"got '{details.get('interaction_type')}'"
                    )
                
                # Verify thinking content presence (native thinking specific)
                if "has_thinking_content" in expected_interaction:
                    actual_thinking_content = details.get("thinking_content")
                    expected_has_thinking = expected_interaction["has_thinking_content"]
                    
                    if expected_has_thinking:
                        assert actual_thinking_content is not None and len(actual_thinking_content) > 0, (
                            f"{context_label} interaction {i+1} (LLM {llm_position_counter}): "
                            f"expected thinking_content but got None or empty"
                        )
                        
                        # Verify thinking content matches exactly
                        if stage_name and stage_name in EXPECTED_THINKING_CONTENT:
                            expected_thinking_patterns = EXPECTED_THINKING_CONTENT[stage_name]
                            if llm_position_counter in expected_thinking_patterns:
                                expected_thinking = expected_thinking_patterns[llm_position_counter]
                                assert actual_thinking_content == expected_thinking, (
                                    f"{context_label} interaction {i+1} (LLM {llm_position_counter}): "
                                    f"thinking_content mismatch.\n"
                                    f"Expected: '{expected_thinking}'\n"
                                    f"Actual:   '{actual_thinking_content}'"
                                )
                    else:
                        # LangChain summarization doesn't have thinking content
                        # No assertion needed - thinking_content may or may not be present
                        pass
                
                # Verify token usage
                if "input_tokens" in expected_interaction:
                    assert details["input_tokens"] == expected_interaction["input_tokens"], (
                        f"{context_label} interaction {i+1} input_tokens mismatch"
                    )
                    assert details["output_tokens"] == expected_interaction["output_tokens"], (
                        f"{context_label} interaction {i+1} output_tokens mismatch"
                    )
                    assert details["total_tokens"] == expected_interaction["total_tokens"], (
                        f"{context_label} interaction {i+1} total_tokens mismatch"
                    )
                    
                    expected_input_tokens += expected_interaction["input_tokens"]
                    expected_output_tokens += expected_interaction["output_tokens"]
                    expected_total_tokens += expected_interaction["total_tokens"]
                    
            elif interaction_type == "mcp":
                assert details["communication_type"] == expected_interaction["communication_type"], (
                    f"{context_label} interaction {i+1} communication_type mismatch"
                )
                assert details["server_name"] == expected_interaction["server_name"], (
                    f"{context_label} interaction {i+1} server_name mismatch"
                )
                
                if expected_interaction["communication_type"] == "tool_call":
                    assert details["tool_name"] == expected_interaction["tool_name"], (
                        f"{context_label} interaction {i+1} tool_name mismatch"
                    )
                
                elif expected_interaction["communication_type"] == "tool_list":
                    assert "available_tools" in details, (
                        f"{context_label} interaction {i+1} tool_list missing available_tools"
                    )
        
        return expected_input_tokens, expected_output_tokens, expected_total_tokens

    async def _verify_session_level_interactions(self, session_data):
        """Verify session-level interactions."""
        print("  📝 Verifying session-level interactions...")
        
        session_level_interactions = session_data.get("session_level_interactions", [])
        expected = EXPECTED_NATIVE_THINKING_SESSION_LEVEL_INTERACTIONS
        
        llm_interactions = [i for i in session_level_interactions if i.get("type") == "llm"]
        mcp_interactions = [i for i in session_level_interactions if i.get("type") == "mcp"]
        
        assert len(llm_interactions) == expected["llm_count"], (
            f"Session-level: Expected {expected['llm_count']} LLM interactions, got {len(llm_interactions)}"
        )
        assert len(mcp_interactions) == expected["mcp_count"], (
            f"Session-level: Expected {expected['mcp_count']} MCP interactions, got {len(mcp_interactions)}"
        )
        
        assert len(session_level_interactions) == len(expected["interactions"]), (
            f"Session-level interaction count mismatch"
        )
        
        _, _, expected_total_tokens = self._verify_interactions(
            interactions=session_level_interactions,
            expected_spec=expected,
            context_label="Session-level",
            expected_conversation=EXPECTED_NATIVE_THINKING_EXECUTIVE_SUMMARY_CONVERSATION
        )
        
        print(
            f"    ✅ Session-level interactions verified ({len(llm_interactions)} LLM, "
            f"{len(mcp_interactions)} MCP, {expected_total_tokens} tokens)"
        )

    async def _verify_stage_structure(self, stages):
        """Verify stage structure and count."""
        print("  🏗️ Verifying stage structure...")

        expected_stages = ["data-collection", "verification", "analysis"]

        assert len(stages) == len(
            expected_stages
        ), f"Expected {len(expected_stages)} stages, got {len(stages)}"

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

            assert (
                stage["stage_name"] == expected_stages[i]
            ), f"Stage {i} name mismatch"

            assert (
                stage["stage_index"] == i
            ), f"Stage {i} index mismatch"

            assert (
                stage["status"] == "completed"
            ), f"Stage {i} not completed"
            
        print(
            f"    ✅ Stage structure verified ({len(stages)} stages)"
        )

    async def _verify_complete_interaction_flow(self, stages):
        """Verify complete interaction flow."""
        print("  🔄 Verifying complete interaction flow...")

        await self._validate_stage(stages[0], EXPECTED_NATIVE_THINKING_DATA_COLLECTION_CONVERSATION)
        print("    ✅ Stage 'data-collection': Validated")
        
        await self._validate_stage(stages[1], EXPECTED_NATIVE_THINKING_VERIFICATION_CONVERSATION)
        print("    ✅ Stage 'verification': Validated")
        
        await self._validate_stage(stages[2], EXPECTED_NATIVE_THINKING_ANALYSIS_CONVERSATION)
        print("    ✅ Stage 'analysis': Validated")

        print("  ✅ All stages validated with native thinking format")

    async def _validate_stage(self, actual_stage, expected_conversation):
        """Validate a stage using expected conversation structure."""
        stage_name = actual_stage["stage_name"]
        expected_stage = EXPECTED_NATIVE_THINKING_STAGES[stage_name]
        llm_interactions = actual_stage.get("llm_interactions", [])
        mcp_interactions = actual_stage.get("mcp_communications", [])

        assert (
            len(llm_interactions) == expected_stage["llm_count"]
        ), f"Stage '{stage_name}': LLM count mismatch"
        assert (
            len(mcp_interactions) == expected_stage["mcp_count"]
        ), f"Stage '{stage_name}': MCP count mismatch"

        chronological_interactions = actual_stage.get("chronological_interactions", [])
        assert (
            len(chronological_interactions) == len(expected_stage["interactions"])
        ), f"Stage '{stage_name}' chronological interaction count mismatch"

        expected_input_tokens, expected_output_tokens, expected_total_tokens = self._verify_interactions(
            interactions=chronological_interactions,
            expected_spec=expected_stage,
            context_label=f"Stage '{stage_name}'",
            expected_conversation=expected_conversation,
            stage_name=stage_name  # Pass stage name for thinking content verification
        )

        # Validate stage-level token totals
        assert actual_stage.get("stage_input_tokens") == expected_input_tokens, (
            f"Stage '{stage_name}' input_tokens total mismatch"
        )
        assert actual_stage.get("stage_output_tokens") == expected_output_tokens, (
            f"Stage '{stage_name}' output_tokens total mismatch"
        )
        assert actual_stage.get("stage_total_tokens") == expected_total_tokens, (
            f"Stage '{stage_name}' total_tokens total mismatch"
        )

    async def _test_chat_functionality(self, test_client, session_id: str):
        """Test chat functionality with native thinking."""
        
        # Check chat availability
        availability_response = test_client.get(
            f"/api/v1/sessions/{session_id}/chat-available"
        )
        assert availability_response.status_code == 200
        availability_data = availability_response.json()
        assert availability_data.get("available") is True

        # Create chat
        create_chat_response = test_client.post(
            f"/api/v1/sessions/{session_id}/chat",
            headers={"X-Forwarded-User": "test-user@example.com"}
        )
        assert create_chat_response.status_code == 200
        chat_data = create_chat_response.json()
        chat_id = chat_data.get("chat_id")
        assert chat_id is not None

        verified_chat_stage_ids = set()

        # Send first message
        message_1_stage = await self._send_and_wait_for_chat_message(
            test_client=test_client,
            session_id=session_id,
            chat_id=chat_id,
            content="Can you check the pods in the stuck-namespace?",
            message_label="Message 1",
            verified_stage_ids=verified_chat_stage_ids
        )
        
        await self._verify_chat_response(
            chat_stage=message_1_stage,
            message_key='message_1',
            expected_conversation=EXPECTED_NATIVE_THINKING_CHAT_MESSAGE_1_CONVERSATION
        )
        verified_chat_stage_ids.add(message_1_stage.get("stage_id"))

        # Send second message
        message_2_stage = await self._send_and_wait_for_chat_message(
            test_client=test_client,
            session_id=session_id,
            chat_id=chat_id,
            content="Does the namespace still exist?",
            message_label="Message 2",
            verified_stage_ids=verified_chat_stage_ids
        )
        
        await self._verify_chat_response(
            chat_stage=message_2_stage,
            message_key='message_2',
            expected_conversation=EXPECTED_NATIVE_THINKING_CHAT_MESSAGE_2_CONVERSATION
        )

        # Verify message history
        messages_response = test_client.get(
            f"/api/v1/chats/{chat_id}/messages?limit=10&offset=0"
        )
        assert messages_response.status_code == 200
        messages_data = messages_response.json()
        assert messages_data.get("total_count") == 2

        logger.info("Chat functionality test completed (2 messages)")

    async def _send_and_wait_for_chat_message(
        self,
        test_client,
        session_id: str,
        chat_id: str,
        content: str,
        message_label: str = "Message",
        verified_stage_ids: set = None
    ):
        """Send a chat message and wait for completion."""
        if verified_stage_ids is None:
            verified_stage_ids = set()
        
        # Send message
        send_message_response = test_client.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": content},
            headers={"X-Forwarded-User": "test-user@example.com"}
        )
        assert send_message_response.status_code == 200

        # Wait for response
        max_wait = 15
        poll_interval = 0.5
        
        chat_stage = None
        for i in range(int(max_wait / poll_interval)):
            detail_data = await E2ETestUtils.get_session_details_async(test_client, session_id)
            stages = detail_data.get("stages", [])
            
            for stage in reversed(stages):
                stage_id = stage.get("stage_id", "")
                if (stage_id.startswith("chat-response") and
                    stage_id not in verified_stage_ids and
                    stage.get("chat_id") == chat_id):
                    chat_stage = stage
                    break
            
            if chat_stage and chat_stage.get("status") == "completed":
                break
            
            await asyncio.sleep(poll_interval)
        else:
            raise AssertionError(f"{message_label} response did not complete")
        
        return chat_stage

    async def _verify_chat_response(
        self,
        chat_stage,
        message_key: str,
        expected_conversation: dict
    ):
        """Verify chat response structure."""
        assert chat_stage is not None
        assert chat_stage.get("agent") == "ChatAgent"
        assert chat_stage.get("status") == "completed"
        
        expected_chat = EXPECTED_NATIVE_THINKING_CHAT_INTERACTIONS[message_key]
        llm_interactions = chat_stage.get("llm_interactions", [])
        mcp_interactions = chat_stage.get("mcp_communications", [])
        
        assert len(llm_interactions) == expected_chat["llm_count"]
        assert len(mcp_interactions) == expected_chat["mcp_count"]
        
        chronological_interactions = chat_stage.get("chronological_interactions", [])
        assert len(chronological_interactions) == len(expected_chat["interactions"])

        print(f"    ✅ Chat {message_key} validated")

    async def _test_final_analysis_endpoint(self, test_client, session_id: str):
        """Test the final-analysis endpoint."""
        
        # Test with LLM conversation only
        response_llm_only = test_client.get(
            f"/api/v1/history/sessions/{session_id}/final-analysis"
            "?include_conversation=true"
        )
        assert response_llm_only.status_code == 200
        
        actual_llm_only = self._normalize_final_analysis_response(response_llm_only.json())
        # Verify key fields match (full comparison would require exact expected values)
        assert actual_llm_only["status"] == "completed"
        assert actual_llm_only["session_id"] == "{SESSION_ID}"
        
        logger.info("LLM conversation only response verified")

        # Test with chat conversation
        response_full = test_client.get(
            f"/api/v1/history/sessions/{session_id}/final-analysis"
            "?include_conversation=true&include_chat_conversation=true"
        )
        assert response_full.status_code == 200
        
        actual_full = self._normalize_final_analysis_response(response_full.json())
        assert actual_full["status"] == "completed"
        assert actual_full["chat_conversation"] is not None
        
        logger.info("Full conversation response verified")
        print("    ✅ Final analysis endpoint verified")

    def _normalize_final_analysis_response(self, response: dict) -> dict:
        """Normalize final analysis response for comparison."""
        normalized = response.copy()
        
        normalized["session_id"] = "{SESSION_ID}"
        
        if normalized.get("final_analysis"):
            normalized["final_analysis"] = E2ETestUtils.normalize_content(
                normalized["final_analysis"]
            )
        
        if normalized.get("llm_conversation"):
            normalized["llm_conversation"] = self._normalize_conversation(
                normalized["llm_conversation"]
            )
        
        if normalized.get("chat_conversation"):
            normalized["chat_conversation"] = self._normalize_conversation(
                normalized["chat_conversation"]
            )
        
        return normalized

    def _normalize_conversation(self, conversation: dict) -> dict:
        """Normalize a conversation object."""
        normalized = conversation.copy()
        normalized["timestamp_us"] = "{TIMESTAMP_US}"
        
        if "messages" in normalized:
            normalized["messages"] = [
                {
                    "role": msg["role"],
                    "content": E2ETestUtils.normalize_content(msg["content"])
                }
                for msg in normalized["messages"]
            ]
        
        return normalized

