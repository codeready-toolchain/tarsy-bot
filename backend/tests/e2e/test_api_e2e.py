"""
Simplified End-to-End Test with HTTP-level mocking.

This test uses the real FastAPI application with real internal services,
mocking only external HTTP dependencies at the network boundary.

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: HTTP requests to LLM APIs, MCP servers, GitHub runbooks
"""

import asyncio
import json
import re
import random
import string
from unittest.mock import AsyncMock, Mock, patch
from mcp.types import Tool

import httpx
import pytest
import respx

from tarsy.config.builtin_config import BUILTIN_MCP_SERVERS
from tarsy.integrations.mcp.client import MCPClient
from .e2e_utils import E2ETestUtils

from .expected_conversations import (
    EXPECTED_ANALYSIS_CONVERSATION,
    EXPECTED_DATA_COLLECTION_CONVERSATION,
    EXPECTED_STAGES,
    EXPECTED_VERIFICATION_CONVERSATION,
)


def normalize_content(content: str) -> str:
    """Normalize dynamic content in messages for stable comparison."""
    # Normalize timestamps (microsecond precision)
    content = re.sub(r"\*\*Timestamp:\*\* \d+", "**Timestamp:** {TIMESTAMP}", content)
    content = re.sub(r"Timestamp:\*\* \d+", "Timestamp:** {TIMESTAMP}", content)

    # Normalize alert IDs and session IDs (UUIDs)
    content = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{UUID}",
        content,
    )

    # Normalize specific test-generated data keys
    content = re.sub(
        r"test-kubernetes_[a-f0-9]+_\d+", "test-kubernetes_{DATA_KEY}", content
    )

    return content


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
        expected_content = normalize_content(expected_msg.get("content", ""))
        actual_content = normalize_content(actual_msg.get("content", ""))
        assert (
            expected_content == actual_content
        ), f"Content mismatch: expected {expected_content}, got {actual_content}"


@pytest.mark.asyncio
@pytest.mark.e2e
class TestRealE2E:
    """
    Simplified E2E test using HTTP-level mocking.

    Tests the complete system flow:
    1. HTTP POST to /alerts endpoint
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
        1. POST alert to /alerts -> queued
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
                print("❌ HARDCORE TIMEOUT: Test exceeded 30 seconds!")
                print("Check for hanging in alert processing pipeline")
                raise AssertionError("Test exceeded hardcore timeout of 10 seconds")
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
        # Using respx for HTTP mocking and MCP SDK mocking for stdio communication

        # Simplified interaction tracking - focus on LLM calls only
        # (MCP interactions will be validated from API response)
        all_llm_interactions = []
        captured_llm_requests = {}  # Store full LLM request content by interaction number

        # Create HTTP response handlers for respx
        def create_llm_response_handler():
            """Create a handler that tracks LLM interactions and returns appropriate responses."""

            def llm_response_handler(request):
                try:
                    # Track the interaction for counting
                    request_data = (
                        request.content.decode()
                        if hasattr(request, "content") and request.content
                        else "{}"
                    )
                    all_llm_interactions.append(request_data)

                    # Parse and store the request content for exact verification
                    try:
                        parsed_request = json.loads(request_data)
                        messages = parsed_request.get("messages", [])

                        # Store the full messages for later exact verification
                        captured_llm_requests[len(all_llm_interactions)] = {
                            "messages": messages,
                            "interaction_number": len(all_llm_interactions),
                        }

                        print(f"\n🔍 LLM REQUEST #{len(all_llm_interactions)}:")
                        for i, msg in enumerate(messages):
                            print(f"  Message {i+1} ({msg.get('role', 'unknown')}):")
                            content = msg.get("content", "")
                            # Print abbreviated content for debugging
                            print(
                                f"    Content: {content[:200]}...{content[-100:] if len(content) > 300 else ''}"
                            )
                        print("=" * 80)
                    except json.JSONDecodeError:
                        print(
                            f"\n🔍 LLM REQUEST #{len(all_llm_interactions)}: Could not parse JSON"
                        )
                        print(f"Raw content: {request_data}")
                        print("=" * 80)
                    except Exception as e:
                        print(
                            f"\n🔍 LLM REQUEST #{len(all_llm_interactions)}: Parse error: {e}"
                        )
                        print("=" * 80)

                    # Determine response based on interaction count (simple pattern)
                    total_interactions = len(all_llm_interactions)

                    # Define mock response content and token usage for each interaction
                    # These values are used to test llm interaction, token tracking at interaction, stage, and session levels
                    # Expected stage token usage totals: data-collection=1310(regular)+150(summarization)=1460, verification=650, analysis=600
                    # Expected session tolen usage total: 2710 tokens (1950 input + 760 output)
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
                        4: { # Data collection - Tool result summarization
                            "response_content": """Summarized: System healthy, CPU 45%, Memory 33%, Disk 76%, Network OK.""",
                            "input_tokens": 100, "output_tokens": 50, "total_tokens": 150
                           },
                        5: { # Data collection - Final analysis
                            "response_content": """Final Answer: Data collection completed. Found namespace 'stuck-namespace' in Terminating state with finalizers blocking deletion.""",
                            "input_tokens": 315, "output_tokens": 125, "total_tokens": 440
                           },
                        6: { # Verification - Check
                            "response_content": """Thought: I need to verify the namespace status.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}""",
                            "input_tokens": 190, "output_tokens": 70, "total_tokens": 260
                           },
                        7: { # Verification - Summary
                            "response_content": """Final Answer: Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion.""",
                            "input_tokens": 280, "output_tokens": 110, "total_tokens": 390
                           },
                        8: { # Analysis - Final
                            "response_content": """Based on previous stages, the namespace is stuck due to finalizers.""",
                            "input_tokens": 420, "output_tokens": 180, "total_tokens": 600
                           },
                    }

                    # Get mock response for this interaction
                    mock_response = mock_response_map.get(total_interactions, {"response_content": "", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0})

                    # Return HTTP response in the format expected by LangChain
                    return httpx.Response(
                        200,
                        json={
                            "choices": [
                                {
                                    "message": {
                                        "content": mock_response["response_content"],
                                        "role": "assistant",
                                    },
                                    "finish_reason": "stop",
                                }
                            ],
                            "model": "gpt-4",
                            "usage": { # Use correct OpenAI API field names: prompt_tokens, completion_tokens, total_tokens
                                "prompt_tokens": mock_response["input_tokens"],
                                "completion_tokens": mock_response["output_tokens"], 
                                "total_tokens": mock_response["total_tokens"]
                            },
                        },
                    )
                except Exception as e:
                    print(f"Error in LLM response handler: {e}")
                    # Fallback response
                    return httpx.Response(
                        200,
                        json={
                            "choices": [
                                {
                                    "message": {
                                        "content": "Fallback response",
                                        "role": "assistant",
                                    }
                                }
                            ]
                        },
                    )

            return llm_response_handler

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

                    if resource == "namespaces" and name == "stuck-namespace":
                        mock_content = Mock()
                        mock_content.text = "stuck-namespace   Terminating   45m"
                        mock_result.content = [mock_content]
                    else:
                        mock_content = Mock()
                        mock_content.text = f"Mock kubectl get {resource} response"
                        mock_result.content = [mock_content]

                elif tool_name == "kubectl_describe":
                    resource = _parameters.get("resource", "")
                    name = _parameters.get("name", "")

                    if resource == "namespace" and name == "stuck-namespace":
                        mock_content = Mock()
                        mock_content.text = """Name:         stuck-namespace
Status:       Terminating
Finalizers:   kubernetes.io/pv-protection
Annotations:  contact=admin@company.com
              api-key=sk_test_1234567890abcdef1234567890abcdef
              certificate-authority-data: LS0tLS1CRUdJTi1DRVJUSUZJQ0FURS0tLS0tCk1JSUREakNDQWZZQ0NRQ1dFamxNOW9zPQ==
Labels:       environment=production"""
                        mock_result.content = [mock_content]
                    else:
                        mock_content = Mock()
                        mock_content.text = (
                            f"Mock kubectl describe {resource} {name} response"
                        )
                        mock_result.content = [mock_content]

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

        # Create mock MCP sessions for both servers
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
        with respx.mock() as respx_mock, patch(
            "tarsy.config.builtin_config.BUILTIN_MCP_SERVERS", test_mcp_servers
        ):
            # 1. Mock LLM API calls (preserves LLM hooks!)
            llm_handler = create_llm_response_handler()

            # Mock all major LLM provider endpoints (covers openai, anthropic, etc.)
            respx_mock.post(
                url__regex=r".*(openai\.com|anthropic\.com|api\.x\.ai|generativelanguage\.googleapis\.com|googleapis\.com).*"
            ).mock(side_effect=llm_handler)

            # 2. Mock runbook HTTP calls using shared utility
            E2ETestUtils.setup_runbook_mocking(respx_mock)

            # 3. Mock MCP client using shared utility with custom sessions
            mock_sessions = {
                "kubernetes-server": mock_kubernetes_session,
                "test-data-server": mock_custom_session,
            }
            mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

            with patch.object(MCPClient, "list_tools", mock_list_tools), patch.object(
                MCPClient, "call_tool", mock_call_tool
            ):
                print(
                    "🔧 Using the real AlertService with test MCP server config and mocking..."
                )
                # All internal services are real, hooks work perfectly!
                # HTTP calls (LLM, runbooks) are mocked via respx
                # MCP server config replaced with test config to avoid external NPM packages
                # MCP calls handled by mock session that provides kubectl tools

                print("⏳ Step 1: Submitting alert...")
                E2ETestUtils.submit_alert(e2e_test_client, e2e_realistic_kubernetes_alert)

                print("⏳ Step 2: Waiting for processing...")
                session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                    e2e_test_client, max_wait_seconds=8, debug_logging=False
                )

                print("🔍 Step 3: Verifying results...")

                # Basic verification
                assert session_id is not None, "Session ID missing"
                print(f"✅ Session found: {session_id}, final status: {final_status}")

                # Verify session completed successfully
                assert (
                    final_status == "completed"
                ), f"Expected session to be completed, but got: {final_status}"
                print("✅ Session completed successfully!")

                # Get session details to verify stages structure
                detail_data = E2ETestUtils.get_session_details(e2e_test_client, session_id)
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

                return

    async def _verify_session_metadata(self, session_data, original_alert):
        """Verify session metadata matches expectations."""
        print("  📋 Verifying session metadata...")

        # Required session fields
        required_fields = [
            "session_id",
            "alert_id",
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

        # Processing duration should be reasonable (< 30 seconds in microseconds)
        processing_duration_ms = (completed_at - started_at) / 1000
        assert (
            processing_duration_ms < 30000
        ), f"Processing took too long: {processing_duration_ms}ms"

        # Verify session-level token usage totals (sum of all stages)
        # Expected totals: data-collection(1060+400=1460) + verification(470+180=650) + analysis(420+180=600)
        expected_session_input_tokens = 1950  # 1060 + 470 + 420
        expected_session_output_tokens = 760   # 400 + 180 + 180  
        expected_session_total_tokens = 2710   # 1460 + 650 + 600
        
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

        print(
            f"    ✅ Stage '{stage_name}': Complete interaction flow verified ({len(llm_interactions)} LLM, {len(mcp_interactions)} MCP)"
        )