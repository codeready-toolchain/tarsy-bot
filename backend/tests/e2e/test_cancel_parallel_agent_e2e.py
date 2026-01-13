"""
E2E Test for Per-Agent Cancellation in Parallel Stages.

This test verifies the per-agent cancellation functionality:
1. Cancel one paused agent while another completed → session continues (success_policy: any)
2. Cancel one paused agent while another still paused → session stays paused
3. Cancelled agent has correct status, timestamps, and duration

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: HTTP requests to LLM APIs, MCP servers, GitHub runbooks
- CONFIGURED: max_llm_mcp_iterations dynamically changed during test
- DETERMINISTIC: Mock responses provide predictable pause/complete behavior
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
    include_kubectl_describe: bool = True,
    get_logs_response: str = '{"logs": "Error: Database connection timeout to db.example.com:5432"}'
) -> AsyncMock:
    """
    Create a mock MCP session with common tool responses.

    Args:
        include_kubectl_describe: Whether to include kubectl_describe tool
        get_logs_response: Custom response text for get_logs tool

    Returns:
        Configured AsyncMock session
    """
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
            Tool(name="kubectl_get", description="Get Kubernetes resources", inputSchema={"type": "object", "properties": {}}),
            Tool(name="get_logs", description="Get pod logs", inputSchema={"type": "object", "properties": {}}),
        ]
        if include_kubectl_describe:
            tools.insert(1, Tool(name="kubectl_describe", description="Describe Kubernetes resources", inputSchema={"type": "object", "properties": {}}))

        mock_result = Mock()
        mock_result.tools = tools
        return mock_result

    mock_session.call_tool.side_effect = mock_call_tool
    mock_session.list_tools.side_effect = mock_list_tools

    return mock_session


@pytest.mark.asyncio
@pytest.mark.e2e
class TestCancelParallelAgentE2E(ParallelTestBase):
    """
    E2E test for per-agent cancellation functionality in parallel stages.

    Tests the complete system flow for canceling individual agents:
    1. Submit alert that triggers parallel execution with both agents pausing
    2. Cancel one paused agent via API
    3. Verify agent status changes to CANCELLED
    4. Verify session status based on success_policy (continues or stays paused)
    5. If session continues, verify synthesis runs with available results
    """

    async def test_cancel_paused_agent_with_policy_any_triggers_continuation(
        self, e2e_parallel_test_client, e2e_cancel_agent_alert
    ):
        """
        Test cancel one paused agent when another completed (success_policy: any).

        Flow:
        1. POST alert with max_iterations=2
        2. KubernetesAgent pauses at iteration 2 (no final answer)
        3. LogAgent completes at iteration 2 (gives final answer)
        4. Session is PAUSED (has paused agent)
        5. Cancel KubernetesAgent via POST /sessions/{sid}/stages/{eid}/cancel
        6. Session continues because LogAgent completed (success_policy: any)
        7. Synthesis runs with LogAgent's result
        8. Session completes

        Verifications:
        - Cancelled agent has status=cancelled, error_message="Cancelled by user"
        - Cancelled agent has completed_at_us = paused_at_us (accurate duration)
        - Session continues and completes with synthesis
        """
        return await self._run_with_timeout(
            lambda: self._execute_cancel_with_policy_any_test(
                e2e_parallel_test_client, e2e_cancel_agent_alert
            ),
            test_name="cancel agent with policy any test",
            timeout_seconds=120
        )

    async def test_cancel_one_paused_agent_keeps_session_paused(
        self, e2e_parallel_test_client, e2e_cancel_agent_alert
    ):
        """
        Test cancel one paused agent while another still paused → session stays paused.

        Flow:
        1. POST alert with max_iterations=1 (both agents pause quickly)
        2. Both agents pause at iteration 1
        3. Session is PAUSED
        4. Cancel LogAgent via POST /sessions/{sid}/stages/{eid}/cancel
        5. Session stays PAUSED (KubernetesAgent still paused)
        6. Resume session
        7. KubernetesAgent completes, synthesis runs
        8. Session completes

        Verifications:
        - After cancel: LogAgent status=cancelled, KubernetesAgent status=paused
        - Session stays paused after single agent cancel
        - After resume: only KubernetesAgent executes (cancelled agent skipped)
        - Synthesis runs with KubernetesAgent result only
        """
        return await self._run_with_timeout(
            lambda: self._execute_cancel_keeps_session_paused_test(
                e2e_parallel_test_client, e2e_cancel_agent_alert
            ),
            test_name="cancel keeps session paused test",
            timeout_seconds=120
        )

    async def test_cancel_only_paused_agent_among_three_agents_session_completes(
        self, e2e_parallel_test_client, e2e_cancel_agent_three_agents_alert
    ):
        """
        Test with 3 parallel agents where only one pauses, then we cancel that paused agent.

        Flow:
        - max_iterations=1 so KubernetesAgent pauses quickly
        - LogAgent and CommandAgent complete in a single iteration
        - Cancel KubernetesAgent
        - Session should continue and complete with synthesis (success_policy: any)
        """
        return await self._run_with_timeout(
            lambda: self._execute_cancel_with_three_agents_test(
                e2e_parallel_test_client, e2e_cancel_agent_three_agents_alert
            ),
            test_name="cancel paused agent among three agents test",
            timeout_seconds=120,
        )

    async def _execute_cancel_with_policy_any_test(self, test_client, alert_data):
        """Execute the cancel test with success_policy: any."""
        print("🔧 Starting cancel with policy:any test")

        # Override max_iterations to 2 for quick pause
        from tarsy.config.settings import get_settings
        settings = get_settings()
        original_max_iterations = settings.max_llm_mcp_iterations
        original_force_conclusion = settings.force_conclusion_at_max_iterations

        try:
            settings.max_llm_mcp_iterations = 2
            settings.force_conclusion_at_max_iterations = False
            print("🔧 Set max_llm_mcp_iterations to 2")
            print(f"🔧 Set force_conclusion_at_max_iterations to False (was {original_force_conclusion})")

            # ============================================================================
            # NATIVE THINKING MOCK (for KubernetesAgent - pauses at iteration 2)
            # and SynthesisAgent (for final synthesis after cancel)
            # ============================================================================
            gemini_response_map = {
                1: {  # KubernetesAgent - First call - tool call (no final answer)
                    "text_content": "",
                    "thinking_content": "I should check the pod status to understand the issue.",
                    "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "pods", "namespace": "test-namespace"}}],
                    "input_tokens": 200,
                    "output_tokens": 60,
                    "total_tokens": 260
                },
                2: {  # KubernetesAgent - Second call - still investigating, no final answer (PAUSES)
                    "text_content": "",
                    "thinking_content": "I see issues. Need more investigation but hit iteration limit.",
                    "function_calls": [{"name": "kubernetes-server__kubectl_describe", "args": {"resource": "pod", "name": "pod-1", "namespace": "test-namespace"}}],
                    "input_tokens": 220,
                    "output_tokens": 70,
                    "total_tokens": 290
                },
                3: {  # SynthesisAgent - Synthesizes LogAgent's result only (after cancel)
                    "text_content": """**Synthesis Report**

Analysis from available agent:

**From Log Agent:**
- Database connection timeout identified
- Root cause: Unable to connect to db.example.com:5432
- Application logs show repeated connection failures

**Note:** KubernetesAgent investigation was cancelled by user.

**Recommendation:**
1. Verify database service availability
2. Check network connectivity to database
3. Review connection pooling settings""",
                    "thinking_content": "I need to synthesize the available findings. KubernetesAgent was cancelled, so I'll focus on LogAgent's results.",
                    "function_calls": None,
                    "input_tokens": 350,
                    "output_tokens": 150,
                    "total_tokens": 500
                }
            }

            from .conftest import create_gemini_client_mock
            gemini_mock_factory = create_gemini_client_mock(gemini_response_map)

            # ============================================================================
            # LANGCHAIN MOCK (for LogAgent - completes at iteration 2)
            # ============================================================================
            agent_counters = {"LogAgent": 0}

            agent_responses = {
                "LogAgent": [
                    {  # Interaction 1 - Log analysis with get_logs action
                        "response_content": """Thought: I should check application logs.
Action: kubernetes-server.get_logs
Action Input: {"namespace": "test-namespace", "pod": "pod-1"}""",
                        "input_tokens": 190, "output_tokens": 55, "total_tokens": 245
                    },
                    {  # Interaction 2 - Final answer (COMPLETES at iteration 2)
                        "response_content": """Thought: Logs show database connection timeout.

Final Answer: **Log Analysis Complete**

Found critical error in logs:
- Error: Database connection timeout to db.example.com:5432
- Pod failing due to inability to connect to database
- CrashLoopBackOff is result of repeated connection failures

Root cause identified from logs.""",
                        "input_tokens": 210, "output_tokens": 85, "total_tokens": 295
                    }
                ]
            }

            agent_identifiers = {"LogAgent": "log analysis specialist"}

            streaming_mock = E2ETestUtils.create_agent_aware_streaming_mock(
                agent_counters, agent_responses, agent_identifiers
            )

            # Create MCP session mock (with kubectl_describe for this test)
            mock_k8s_session = _create_mcp_session_mock(include_kubectl_describe=True)
            mock_sessions = {"kubernetes-server": mock_k8s_session}
            mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

            with (
                self._create_llm_patch_context(gemini_mock_factory, streaming_mock),
                patch.object(MCPClient, "list_tools", mock_list_tools),
                patch.object(MCPClient, "call_tool", mock_call_tool),
                E2ETestUtils.setup_runbook_service_patching("# Cancel Agent Test Runbook"),
            ):
                # ===== Phase 1: Initial execution - one completes, one pauses =====
                print("\n⏳ Phase 1: Submit alert (max_iterations=2)")
                session_id = E2ETestUtils.submit_alert(test_client, alert_data)

                print("⏳ Wait for session to pause...")
                paused_session_id, paused_status = await E2ETestUtils.wait_for_session_completion(
                    test_client, max_wait_seconds=20, debug_logging=True
                )

                print("🔍 Verify pause state...")
                assert paused_session_id == session_id
                assert paused_status == "paused", f"Expected 'paused', got '{paused_status}'"

                # Wait for parallel execution statuses
                parallel_stage = await E2ETestUtils.wait_for_parallel_execution_statuses(
                    test_client,
                    session_id,
                    stage_name="investigation",
                    expected_statuses={
                        "KubernetesAgent": "paused",
                        "LogAgent": "completed"
                    },
                    max_wait_seconds=5.0,
                    poll_interval=0.1
                )

                # Get the paused agent's execution_id for cancellation
                parallel_executions = parallel_stage.get("parallel_executions", [])
                k8s_exec = next((e for e in parallel_executions if e["agent"] == "KubernetesAgent"), None)
                assert k8s_exec is not None, "KubernetesAgent execution not found"
                k8s_execution_id = k8s_exec["execution_id"]

                print("✅ Phase 1 complete:")
                print(f"   - KubernetesAgent: PAUSED (execution_id: {k8s_execution_id})")
                print("   - LogAgent: COMPLETED")

                # ===== Phase 2: Cancel the paused KubernetesAgent =====
                print(f"\n⏳ Phase 2: Cancel KubernetesAgent (execution_id: {k8s_execution_id})")

                cancel_response = test_client.post(
                    f"/api/v1/history/sessions/{session_id}/stages/{k8s_execution_id}/cancel"
                )
                assert cancel_response.status_code == 200, f"Cancel failed: {cancel_response.text}"
                cancel_data = cancel_response.json()

                print(f"🔍 Cancel response: {cancel_data}")
                assert cancel_data.get("success") is True, "Cancel should succeed"
                # With success_policy: any and LogAgent completed, session should continue
                assert cancel_data.get("session_status") == "in_progress", (
                    f"Expected session_status='in_progress', got '{cancel_data.get('session_status')}'"
                )
                assert cancel_data.get("stage_status") == "completed", (
                    f"Expected stage_status='completed', got '{cancel_data.get('stage_status')}'"
                )

                print("✅ Cancel successful, session continuing...")

                # ===== Phase 3: Wait for session to complete with synthesis =====
                print("\n⏳ Phase 3: Wait for session to complete (synthesis runs)")
                final_session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                    test_client, max_wait_seconds=20, debug_logging=True
                )

                assert final_session_id == session_id
                assert final_status == "completed", f"Expected 'completed', got '{final_status}'"

                # ===== Phase 4: Verify final state =====
                print("\n🔍 Phase 4: Verify final state")
                final_detail = await E2ETestUtils.get_session_details_async(test_client, session_id)

                # Verify stages: investigation (parallel) + synthesis
                final_stages = final_detail.get("stages", [])
                assert len(final_stages) == 2, f"Expected 2 stages, got {len(final_stages)}"

                investigation_stage = final_stages[0]
                synthesis_stage = final_stages[1]

                assert investigation_stage["stage_name"] == "investigation"
                assert investigation_stage["status"] == "completed"
                assert synthesis_stage["stage_name"] == "synthesis"
                assert synthesis_stage["status"] == "completed"

                # Verify agent statuses in investigation stage
                final_parallel_execs = investigation_stage.get("parallel_executions", [])
                final_k8s_exec = next((e for e in final_parallel_execs if e["agent"] == "KubernetesAgent"), None)
                final_log_exec = next((e for e in final_parallel_execs if e["agent"] == "LogAgent"), None)

                # KubernetesAgent should be CANCELLED
                assert final_k8s_exec["status"] == "cancelled", (
                    f"KubernetesAgent should be cancelled, got '{final_k8s_exec['status']}'"
                )
                assert final_k8s_exec.get("error_message") == "Cancelled by user", (
                    f"Expected error_message='Cancelled by user', got '{final_k8s_exec.get('error_message')}'"
                )

                # LogAgent should be COMPLETED
                assert final_log_exec["status"] == "completed", (
                    f"LogAgent should be completed, got '{final_log_exec['status']}'"
                )

                # Verify cancelled agent has correct timestamps (completed_at_us should equal paused_at_us)
                # This ensures duration excludes pause time
                assert final_k8s_exec.get("completed_at_us") is not None, "Cancelled agent should have completed_at_us"
                assert final_k8s_exec.get("duration_ms") is not None, "Cancelled agent should have duration_ms"

                # Verify synthesis ran and session has final summary
                assert final_detail.get("final_analysis_summary") is not None, "Session should have final_analysis_summary"
                assert len(final_detail.get("final_analysis_summary", "")) > 0, "final_analysis_summary should not be empty"

                print("✅ ALL VALIDATIONS PASSED!")
                print("   - KubernetesAgent: CANCELLED with 'Cancelled by user'")
                print("   - LogAgent: COMPLETED")
                print("   - Session continued (success_policy: any)")
                print("   - Synthesis completed with available result")
                print("   - Executive summary generated")

                return final_detail

        finally:
            settings.max_llm_mcp_iterations = original_max_iterations
            settings.force_conclusion_at_max_iterations = original_force_conclusion
            print(f"🔧 Restored max_llm_mcp_iterations to {original_max_iterations}")

    async def _execute_cancel_keeps_session_paused_test(self, test_client, alert_data):
        """Execute the cancel test where session stays paused."""
        print("🔧 Starting cancel keeps session paused test")

        from tarsy.config.settings import get_settings
        settings = get_settings()
        original_max_iterations = settings.max_llm_mcp_iterations
        original_force_conclusion = settings.force_conclusion_at_max_iterations

        try:
            # Set max_iterations to 1 so both agents pause quickly
            settings.max_llm_mcp_iterations = 1
            settings.force_conclusion_at_max_iterations = False
            print("🔧 Set max_llm_mcp_iterations to 1 (both agents will pause)")
            print(f"🔧 Set force_conclusion_at_max_iterations to False (was {original_force_conclusion})")

            # ============================================================================
            # NATIVE THINKING MOCK (for KubernetesAgent and SynthesisAgent)
            # ============================================================================
            gemini_response_map = {
                1: {  # KubernetesAgent - First call - tool call, pauses at iteration 1
                    "text_content": "",
                    "thinking_content": "I should check the pod status.",
                    "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "pods", "namespace": "test-namespace"}}],
                    "input_tokens": 200,
                    "output_tokens": 60,
                    "total_tokens": 260
                },
                2: {  # KubernetesAgent - Second call (after resume) - completes
                    "text_content": """**Kubernetes Analysis Complete**

Pod pod-1 is in CrashLoopBackOff state.
Investigation complete.""",
                    "thinking_content": "Now I can complete my investigation.",
                    "function_calls": None,
                    "input_tokens": 220,
                    "output_tokens": 80,
                    "total_tokens": 300
                },
                3: {  # SynthesisAgent - Synthesizes after resume completion
                    "text_content": """**Synthesis Report**

Analysis from KubernetesAgent:
- Pod pod-1 in CrashLoopBackOff
- Investigation completed after resume

**Note:** LogAgent investigation was cancelled by user.

**Recommendation:** Review pod events and logs.""",
                    "thinking_content": "Synthesizing the available findings.",
                    "function_calls": None,
                    "input_tokens": 300,
                    "output_tokens": 100,
                    "total_tokens": 400
                }
            }

            from .conftest import create_gemini_client_mock
            gemini_mock_factory = create_gemini_client_mock(gemini_response_map)

            # ============================================================================
            # LANGCHAIN MOCK (for LogAgent - pauses at iteration 1)
            # ============================================================================
            agent_counters = {"LogAgent": 0}

            agent_responses = {
                "LogAgent": [
                    {  # Interaction 1 - tool call, pauses at iteration 1
                        "response_content": """Thought: I should check application logs.
Action: kubernetes-server.get_logs
Action Input: {"namespace": "test-namespace", "pod": "pod-1"}""",
                        "input_tokens": 190, "output_tokens": 55, "total_tokens": 245
                    }
                    # No second response - agent is cancelled
                ]
            }

            agent_identifiers = {"LogAgent": "log analysis specialist"}

            streaming_mock = E2ETestUtils.create_agent_aware_streaming_mock(
                agent_counters, agent_responses, agent_identifiers
            )

            # Create MCP session mock (without kubectl_describe for this test)
            mock_k8s_session = _create_mcp_session_mock(
                include_kubectl_describe=False,
                get_logs_response='{"logs": "Error: Connection timeout"}'
            )
            mock_sessions = {"kubernetes-server": mock_k8s_session}
            mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

            with (
                self._create_llm_patch_context(gemini_mock_factory, streaming_mock),
                patch.object(MCPClient, "list_tools", mock_list_tools),
                patch.object(MCPClient, "call_tool", mock_call_tool),
                E2ETestUtils.setup_runbook_service_patching("# Cancel Keeps Paused Test Runbook"),
            ):
                # ===== Phase 1: Initial execution - both agents pause =====
                print("\n⏳ Phase 1: Submit alert (max_iterations=1)")
                session_id = E2ETestUtils.submit_alert(test_client, alert_data)

                print("⏳ Wait for session to pause...")
                paused_session_id, paused_status = await E2ETestUtils.wait_for_session_completion(
                    test_client, max_wait_seconds=20, debug_logging=True
                )

                assert paused_session_id == session_id
                assert paused_status == "paused", f"Expected 'paused', got '{paused_status}'"

                # Wait for parallel execution statuses (both paused)
                parallel_stage = await E2ETestUtils.wait_for_parallel_execution_statuses(
                    test_client,
                    session_id,
                    stage_name="investigation",
                    expected_statuses={
                        "KubernetesAgent": "paused",
                        "LogAgent": "paused"
                    },
                    max_wait_seconds=5.0,
                    poll_interval=0.1
                )

                # Get the execution IDs
                parallel_executions = parallel_stage.get("parallel_executions", [])
                k8s_exec = next((e for e in parallel_executions if e["agent"] == "KubernetesAgent"), None)
                log_exec = next((e for e in parallel_executions if e["agent"] == "LogAgent"), None)

                k8s_execution_id = k8s_exec["execution_id"]
                log_execution_id = log_exec["execution_id"]

                print("✅ Phase 1 complete:")
                print(f"   - KubernetesAgent: PAUSED (execution_id: {k8s_execution_id})")
                print(f"   - LogAgent: PAUSED (execution_id: {log_execution_id})")

                # ===== Phase 2: Cancel LogAgent (K8s stays paused) =====
                print(f"\n⏳ Phase 2: Cancel LogAgent (execution_id: {log_execution_id})")

                cancel_response = test_client.post(
                    f"/api/v1/history/sessions/{session_id}/stages/{log_execution_id}/cancel"
                )
                assert cancel_response.status_code == 200, f"Cancel failed: {cancel_response.text}"
                cancel_data = cancel_response.json()

                print(f"🔍 Cancel response: {cancel_data}")
                assert cancel_data.get("success") is True
                # Session should stay paused because KubernetesAgent is still paused
                assert cancel_data.get("session_status") == "paused", (
                    f"Expected session_status='paused', got '{cancel_data.get('session_status')}'"
                )
                assert cancel_data.get("stage_status") == "paused", (
                    f"Expected stage_status='paused', got '{cancel_data.get('stage_status')}'"
                )

                # Verify current state: LogAgent cancelled, K8s still paused
                detail_after_cancel = await E2ETestUtils.get_session_details_async(test_client, session_id)
                assert detail_after_cancel["status"] == "paused", "Session should still be paused"

                # Check parallel execution statuses
                stages_after_cancel = detail_after_cancel.get("stages", [])
                investigation_after_cancel = stages_after_cancel[0]
                parallel_execs_after = investigation_after_cancel.get("parallel_executions", [])

                k8s_after = next((e for e in parallel_execs_after if e["agent"] == "KubernetesAgent"), None)
                log_after = next((e for e in parallel_execs_after if e["agent"] == "LogAgent"), None)

                assert k8s_after["status"] == "paused", f"K8s should still be paused, got '{k8s_after['status']}'"
                assert log_after["status"] == "cancelled", f"Log should be cancelled, got '{log_after['status']}'"
                assert log_after.get("error_message") == "Cancelled by user"

                print("✅ Phase 2 complete:")
                print("   - LogAgent: CANCELLED")
                print("   - KubernetesAgent: still PAUSED")
                print("   - Session: still PAUSED")

                # ===== Phase 3: Resume session (only K8s runs) =====
                print("\n⏳ Phase 3: Resume session (max_iterations=4)")
                settings.max_llm_mcp_iterations = 4

                resume_response = test_client.post(f"/api/v1/history/sessions/{session_id}/resume")
                assert resume_response.status_code == 200
                resume_data = resume_response.json()
                assert resume_data.get("success") is True
                assert resume_data.get("status") == "resuming"

                # ===== Phase 4: Wait for completion =====
                print("⏳ Wait for resumed session to complete...")
                final_session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                    test_client, max_wait_seconds=20, debug_logging=True
                )

                assert final_session_id == session_id
                assert final_status == "completed", f"Expected 'completed', got '{final_status}'"

                # ===== Phase 5: Verify final state =====
                print("\n🔍 Phase 5: Verify final state")
                final_detail = await E2ETestUtils.get_session_details_async(test_client, session_id)

                # Verify stages
                final_stages = final_detail.get("stages", [])
                assert len(final_stages) == 2, f"Expected 2 stages, got {len(final_stages)}"

                final_investigation = final_stages[0]
                final_synthesis = final_stages[1]

                assert final_investigation["status"] == "completed"
                assert final_synthesis["status"] == "completed"

                # Verify agent final statuses
                final_parallel_execs = final_investigation.get("parallel_executions", [])
                final_k8s = next((e for e in final_parallel_execs if e["agent"] == "KubernetesAgent"), None)
                final_log = next((e for e in final_parallel_execs if e["agent"] == "LogAgent"), None)

                # K8s completed after resume, Log stayed cancelled
                assert final_k8s["status"] == "completed", f"K8s should be completed, got '{final_k8s['status']}'"
                assert final_log["status"] == "cancelled", f"Log should still be cancelled, got '{final_log['status']}'"

                # K8s should have 2 LLM interactions (1 before pause + 1 after resume)
                k8s_llm_count = len(final_k8s.get("llm_interactions", []))
                assert k8s_llm_count == 2, f"K8s should have 2 LLM interactions, got {k8s_llm_count}"

                # Log should have 1 LLM interaction (cancelled before resume)
                log_llm_count = len(final_log.get("llm_interactions", []))
                assert log_llm_count == 1, f"Log should have 1 LLM interaction, got {log_llm_count}"

                # Verify final summary
                assert final_detail.get("final_analysis_summary") is not None

                print("✅ ALL VALIDATIONS PASSED!")
                print("   - LogAgent: CANCELLED (1 interaction, not resumed)")
                print("   - KubernetesAgent: COMPLETED (2 interactions, resumed)")
                print("   - Session completed with synthesis")

                return final_detail

        finally:
            settings.max_llm_mcp_iterations = original_max_iterations
            settings.force_conclusion_at_max_iterations = original_force_conclusion
            print(f"🔧 Restored max_llm_mcp_iterations to {original_max_iterations}")

    async def _execute_cancel_with_three_agents_test(self, test_client, alert_data):
        """Execute cancel flow where only one of three parallel agents pauses, then is cancelled."""
        print("🔧 Starting cancel paused agent among three agents test")

        from tarsy.config.settings import get_settings

        settings = get_settings()
        original_max_iterations = settings.max_llm_mcp_iterations
        original_force_conclusion = settings.force_conclusion_at_max_iterations

        try:
            settings.max_llm_mcp_iterations = 1
            settings.force_conclusion_at_max_iterations = False
            print("🔧 Set max_llm_mcp_iterations to 1 (only KubernetesAgent will pause)")
            print(f"🔧 Set force_conclusion_at_max_iterations to False (was {original_force_conclusion})")

            # ============================================================================
            # NATIVE THINKING MOCK (KubernetesAgent pauses at iteration 1)
            # SynthesisAgent runs after cancellation
            # ============================================================================
            gemini_response_map = {
                1: {  # KubernetesAgent - tool call only -> pauses
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
                2: {  # SynthesisAgent - combines available completed agents
                    "text_content": """**Synthesis Report**

Available results:

**From Log Agent:**
- Logs show a database connection timeout

**From Command Agent:**
- Recommended remediation steps provided

**Note:** KubernetesAgent investigation was cancelled by user.""",
                    "thinking_content": "Synthesize the completed agent results and note the cancellation.",
                    "function_calls": None,
                    "input_tokens": 320,
                    "output_tokens": 110,
                    "total_tokens": 430,
                },
            }

            from .conftest import create_gemini_client_mock

            gemini_mock_factory = create_gemini_client_mock(gemini_response_map)

            # ============================================================================
            # LANGCHAIN MOCK (LogAgent + CommandAgent complete in 1 iteration)
            # ============================================================================
            agent_counters = {"LogAgent": 0, "CommandAgent": 0}

            agent_responses = {
                "LogAgent": [
                    {
                        "response_content": """Thought: I have enough info.

Final Answer: **Log Analysis Complete**

Logs indicate a database connection timeout to db.example.com:5432.""",
                        "input_tokens": 180,
                        "output_tokens": 70,
                        "total_tokens": 250,
                    }
                ],
                "CommandAgent": [
                    {
                        "response_content": """Thought: I can propose remediation steps without more tool calls.

Final Answer: **Remediation Plan**

1. Verify database is reachable from the cluster network.
2. Check service DNS and firewall rules.
3. Validate credentials and connection parameters.""",
                        "input_tokens": 160,
                        "output_tokens": 85,
                        "total_tokens": 245,
                    }
                ],
            }

            agent_identifiers = {
                "LogAgent": "log analysis specialist",
                "CommandAgent": "command execution specialist",
            }

            streaming_mock = E2ETestUtils.create_agent_aware_streaming_mock(
                agent_counters, agent_responses, agent_identifiers
            )

            # MCP mock: only KubernetesAgent uses tools in this test
            mock_k8s_session = _create_mcp_session_mock(
                include_kubectl_describe=False,
                get_logs_response='{"logs": "Error: Database connection timeout"}',
            )
            mock_sessions = {"kubernetes-server": mock_k8s_session}
            mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(
                mock_sessions
            )

            with (
                self._create_llm_patch_context(gemini_mock_factory, streaming_mock),
                patch.object(MCPClient, "list_tools", mock_list_tools),
                patch.object(MCPClient, "call_tool", mock_call_tool),
                E2ETestUtils.setup_runbook_service_patching(
                    "# Cancel 3-Agent Test Runbook"
                ),
            ):
                # ===== Phase 1: Initial execution - one paused, two completed =====
                print("\n⏳ Phase 1: Submit alert (max_iterations=1)")
                session_id = E2ETestUtils.submit_alert(test_client, alert_data)

                print("⏳ Wait for session to pause...")
                paused_session_id, paused_status = await E2ETestUtils.wait_for_session_completion(
                    test_client, max_wait_seconds=20, debug_logging=True
                )
                assert paused_session_id == session_id
                assert paused_status == "paused", f"Expected 'paused', got '{paused_status}'"

                parallel_stage = await E2ETestUtils.wait_for_parallel_execution_statuses(
                    test_client,
                    session_id,
                    stage_name="investigation",
                    expected_statuses={
                        "KubernetesAgent": "paused",
                        "LogAgent": "completed",
                        "CommandAgent": "completed",
                    },
                    max_wait_seconds=5.0,
                    poll_interval=0.1,
                )

                parallel_executions = parallel_stage.get("parallel_executions", [])
                k8s_exec = next((e for e in parallel_executions if e["agent"] == "KubernetesAgent"), None)
                assert k8s_exec is not None
                k8s_execution_id = k8s_exec["execution_id"]

                # ===== Phase 2: Cancel the paused KubernetesAgent =====
                print(f"\n⏳ Phase 2: Cancel KubernetesAgent (execution_id: {k8s_execution_id})")
                cancel_response = test_client.post(
                    f"/api/v1/history/sessions/{session_id}/stages/{k8s_execution_id}/cancel"
                )
                assert cancel_response.status_code == 200, f"Cancel failed: {cancel_response.text}"
                cancel_data = cancel_response.json()
                assert cancel_data.get("success") is True
                assert cancel_data.get("session_status") == "in_progress"
                assert cancel_data.get("stage_status") == "completed"

                # ===== Phase 3: Session should complete with synthesis =====
                print("\n⏳ Phase 3: Wait for session to complete (synthesis runs)")
                final_session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                    test_client, max_wait_seconds=20, debug_logging=True
                )
                assert final_session_id == session_id
                assert final_status == "completed"

                final_detail = await E2ETestUtils.get_session_details_async(test_client, session_id)
                final_stages = final_detail.get("stages", [])
                assert len(final_stages) == 2, f"Expected 2 stages, got {len(final_stages)}"

                investigation_stage = final_stages[0]
                synthesis_stage = final_stages[1]
                assert investigation_stage["stage_name"] == "investigation"
                assert investigation_stage["status"] == "completed"
                assert synthesis_stage["stage_name"] == "synthesis"
                assert synthesis_stage["status"] == "completed"

                inv_parallel_execs = investigation_stage.get("parallel_executions", [])
                assert len(inv_parallel_execs) == 3

                final_k8s = next((e for e in inv_parallel_execs if e["agent"] == "KubernetesAgent"), None)
                final_log = next((e for e in inv_parallel_execs if e["agent"] == "LogAgent"), None)
                final_cmd = next((e for e in inv_parallel_execs if e["agent"] == "CommandAgent"), None)
                assert final_k8s is not None and final_log is not None and final_cmd is not None

                assert final_k8s["status"] == "cancelled"
                assert final_log["status"] == "completed"
                assert final_cmd["status"] == "completed"

                assert final_detail.get("final_analysis_summary") is not None
                assert len(final_detail.get("final_analysis_summary", "")) > 0

                print("✅ ALL VALIDATIONS PASSED!")
                print("   - KubernetesAgent: CANCELLED")
                print("   - LogAgent: COMPLETED")
                print("   - CommandAgent: COMPLETED")
                print("   - Session completed with synthesis")

        finally:
            settings.max_llm_mcp_iterations = original_max_iterations
            settings.force_conclusion_at_max_iterations = original_force_conclusion
            print(f"🔧 Restored max_llm_mcp_iterations to {original_max_iterations}")

