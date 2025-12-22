"""
E2E Test for Cancelling a PAUSED Session During a Parallel Stage.

This test covers cancelling the whole session (not an individual agent) when a parallel stage
is PAUSED. This uses the fast-path in `history_controller.cancel_session()`:

- Session is PAUSED (no active background task)
- Cancel should immediately mark the session CANCELLED
- All PAUSED stages (parallel parent + paused child executions) are marked CANCELLED
"""

import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import Tool

from tarsy.integrations.mcp.client import MCPClient

from .e2e_utils import E2ETestUtils
from .parallel_test_base import ParallelTestBase

logger = logging.getLogger(__name__)


def _create_mcp_session_mock(
    include_kubectl_describe: bool = False,
    get_logs_response: str = '{"logs": "Error: Connection timeout"}',
) -> AsyncMock:
    """Create a mock MCP session with common tool responses."""
    mock_session = AsyncMock()

    async def mock_call_tool(tool_name, _parameters):
        mock_result = Mock()
        mock_content = Mock()

        if "kubectl_get" in tool_name:
            mock_content.text = '{"result": "Pod pod-1 is in CrashLoopBackOff state"}'
        elif "kubectl_describe" in tool_name:
            mock_content.text = '{"result": "Pod pod-1 details: exit code 1, restart count 5"}'
        elif "get_logs" in tool_name or "log" in tool_name.lower():
            mock_content.text = get_logs_response
        else:
            mock_content.text = '{"result": "Mock response"}'

        mock_result.content = [mock_content]
        return mock_result

    async def mock_list_tools():
        tools = [
            Tool(
                name="kubectl_get",
                description="Get Kubernetes resources",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="get_logs",
                description="Get pod logs",
                inputSchema={"type": "object", "properties": {}},
            ),
        ]
        if include_kubectl_describe:
            tools.insert(
                1,
                Tool(
                    name="kubectl_describe",
                    description="Describe Kubernetes resources",
                    inputSchema={"type": "object", "properties": {}},
                ),
            )

        mock_result = Mock()
        mock_result.tools = tools
        return mock_result

    mock_session.call_tool.side_effect = mock_call_tool
    mock_session.list_tools.side_effect = mock_list_tools

    return mock_session


@pytest.mark.asyncio
@pytest.mark.e2e
class TestCancelPausedSessionParallelE2E(ParallelTestBase):
    """E2E test for cancelling a paused session while in a parallel stage."""

    async def test_cancel_paused_parallel_session_cancels_all_paused_stages(
        self, e2e_parallel_test_client, e2e_cancel_agent_alert
    ):
        """
        Flow:
        1. Submit alert that triggers parallel execution where BOTH agents pause (max_iterations=1).
        2. Cancel the session via POST /api/v1/history/sessions/{session_id}/cancel.
        3. Verify session is CANCELLED and all paused executions are CANCELLED.
        """
        return await self._run_with_timeout(
            lambda: self._execute_cancel_paused_parallel_session_test(
                e2e_parallel_test_client, e2e_cancel_agent_alert
            ),
            test_name="cancel paused parallel session test",
            timeout_seconds=120,
        )

    async def _execute_cancel_paused_parallel_session_test(self, test_client, alert_data):
        print("🔧 Starting cancel paused parallel session test")

        from tarsy.config.settings import get_settings

        settings = get_settings()
        original_max_iterations = settings.max_llm_mcp_iterations

        try:
            settings.max_llm_mcp_iterations = 1
            print("🔧 Set max_llm_mcp_iterations to 1 (both agents will pause)")

            # KubernetesAgent pauses at iteration 1 (native thinking tool call)
            gemini_response_map = {
                1: {
                    "text_content": "",
                    "thinking_content": "I should check the pod status.",
                    "function_calls": [
                        {
                            "name": "kubernetes-server__kubectl_get",
                            "args": {"resource": "pods", "namespace": "test-namespace"},
                        }
                    ],
                    "input_tokens": 200,
                    "output_tokens": 60,
                    "total_tokens": 260,
                },
            }

            from .conftest import create_gemini_client_mock

            gemini_mock_factory = create_gemini_client_mock(gemini_response_map)

            # LogAgent pauses at iteration 1 (ReAct tool call, no final answer)
            agent_counters = {"LogAgent": 0}
            agent_responses = {
                "LogAgent": [
                    {
                        "response_content": """Thought: I should check application logs.
Action: kubernetes-server.get_logs
Action Input: {"namespace": "test-namespace", "pod": "pod-1"}""",
                        "input_tokens": 190,
                        "output_tokens": 55,
                        "total_tokens": 245,
                    }
                ]
            }

            agent_identifiers = {"LogAgent": "log analysis specialist"}
            streaming_mock = E2ETestUtils.create_agent_aware_streaming_mock(
                agent_counters, agent_responses, agent_identifiers
            )

            mock_k8s_session = _create_mcp_session_mock()
            mock_sessions = {"kubernetes-server": mock_k8s_session}
            mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(
                mock_sessions
            )

            with (
                self._create_llm_patch_context(gemini_mock_factory, streaming_mock),
                patch.object(MCPClient, "list_tools", mock_list_tools),
                patch.object(MCPClient, "call_tool", mock_call_tool),
                E2ETestUtils.setup_runbook_service_patching(
                    "# Cancel Paused Session Parallel Test Runbook"
                ),
            ):
                print("\n⏳ Phase 1: Submit alert (max_iterations=1)")
                session_id = E2ETestUtils.submit_alert(test_client, alert_data)

                print("⏳ Wait for session to pause...")
                paused_session_id, paused_status = (
                    await E2ETestUtils.wait_for_session_completion(
                        test_client, max_wait_seconds=20, debug_logging=True
                    )
                )
                assert paused_session_id == session_id
                assert paused_status == "paused", f"Expected 'paused', got '{paused_status}'"

                await E2ETestUtils.wait_for_parallel_execution_statuses(
                    test_client,
                    session_id,
                    stage_name="investigation",
                    expected_statuses={"KubernetesAgent": "paused", "LogAgent": "paused"},
                    max_wait_seconds=5.0,
                    poll_interval=0.1,
                )

                print("\n⏳ Phase 2: Cancel the PAUSED session")
                cancel_response = test_client.post(
                    f"/api/v1/history/sessions/{session_id}/cancel"
                )
                assert cancel_response.status_code == 200, cancel_response.text
                cancel_data = cancel_response.json()
                assert cancel_data.get("success") is True

                print("\n🔍 Phase 3: Verify CANCELLED session + stage states")
                detail_after_cancel = await E2ETestUtils.get_session_details_async(
                    test_client, session_id, max_retries=5, retry_delay=0.2
                )

                assert detail_after_cancel["status"] == "cancelled"
                assert detail_after_cancel.get("error_message") == "Session cancelled by user"

                stages = detail_after_cancel.get("stages", [])
                assert len(stages) == 1, f"Expected 1 stage, got {len(stages)}"
                investigation_stage = stages[0]
                assert investigation_stage["stage_name"] == "investigation"
                assert investigation_stage["status"] == "cancelled"

                parallel_execs = investigation_stage.get("parallel_executions", [])
                assert len(parallel_execs) == 2

                k8s_exec = next((e for e in parallel_execs if e["agent"] == "KubernetesAgent"), None)
                log_exec = next((e for e in parallel_execs if e["agent"] == "LogAgent"), None)
                assert k8s_exec is not None
                assert log_exec is not None

                assert k8s_exec["status"] == "cancelled"
                assert log_exec["status"] == "cancelled"
                assert k8s_exec.get("error_message") == "Cancelled by user"
                assert log_exec.get("error_message") == "Cancelled by user"

                print("✅ Cancel paused parallel session test passed!")

        finally:
            settings.max_llm_mcp_iterations = original_max_iterations

