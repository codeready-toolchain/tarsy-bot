"""
End-to-End Test for Parallel Stage Followed by Regular Stage.

This test verifies:
- Parallel stage followed by regular stage works
- No automatic synthesis when not final stage
- ParallelStageResult is passed to next stage
- Regular stage can reference parallel results

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: HTTP requests to LLM APIs, MCP servers, GitHub runbooks
"""

import logging
from unittest.mock import patch

import pytest

from .conftest import create_mock_stream
from .e2e_utils import E2ETestUtils
from .expected_parallel_conversations import (
    EXPECTED_PARALLEL_NO_SYNTHESIS_AGENT_1_CONVERSATION,
    EXPECTED_PARALLEL_NO_SYNTHESIS_AGENT_2_CONVERSATION,
    EXPECTED_REGULAR_AFTER_PARALLEL_CONVERSATION,
    EXPECTED_PARALLEL_REGULAR_STAGES,
)
from .parallel_test_base import ParallelTestBase

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestParallelThenRegularE2E(ParallelTestBase):
    """E2E test for parallel stage followed by regular stage."""

    @pytest.mark.e2e
    async def test_parallel_then_regular_stage(
        self, e2e_parallel_test_client, e2e_parallel_regular_alert
    ):
        """
        Test parallel stage followed by regular stage (no automatic synthesis).

        Flow:
        1. POST alert to /api/v1/alerts -> queued
        2. Wait for processing to complete
        3. Verify session was created and completed
        4. Verify parallel stage with 2 agents
        5. Verify regular stage follows (NO synthesis stage)
        6. Verify regular stage received ParallelStageResult

        This test verifies:
        - Parallel stage followed by regular stage works
        - No automatic synthesis when not final stage
        - ParallelStageResult is passed to next stage
        - Regular stage can reference parallel results
        """
        return await self._run_with_timeout(
            lambda: self._execute_parallel_regular_test(e2e_parallel_test_client, e2e_parallel_regular_alert),
            test_name="parallel + regular test"
        )

    async def _execute_parallel_regular_test(self, test_client, alert_data):
        """Execute parallel + regular stage test."""
        print("🔧 Starting parallel + regular stage test execution")

        # ============================================================================
        # NATIVE THINKING MOCK (for KubernetesAgent using Gemini)
        # ============================================================================
        # Gemini SDK responses for native thinking (function calling)
        gemini_response_map = {
            1: {  # First call - tool call with thinking
                "text_content": "",  # Empty for tool calls
                "thinking_content": "I should check the pod status in test-namespace to understand the issue.",
                "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "pods", "namespace": "test-namespace"}}],
                "input_tokens": 240,
                "output_tokens": 85,
                "total_tokens": 325
            },
            2: {  # Second call - final answer after tool result
                "text_content": "Investigation complete. Found pod-1 in CrashLoopBackOff state in test-namespace. This indicates the pod is repeatedly crashing and Kubernetes is backing off on restart attempts. Recommend checking pod logs and events for root cause.",
                "thinking_content": "I have identified the pod status. This provides enough information for initial analysis.",
                "function_calls": None,
                "input_tokens": 180,
                "output_tokens": 65,
                "total_tokens": 245
            }
        }
        
        # Import create_gemini_client_mock from conftest
        from .conftest import create_gemini_client_mock
        gemini_mock_factory = create_gemini_client_mock(gemini_response_map)
        
        # ============================================================================
        # LANGCHAIN MOCK (for LogAgent and CommandAgent using ReAct)
        # ============================================================================
        # Agent-specific interaction counters for LangChain-based agents
        agent_counters = {
            "LogAgent": 0,
            "CommandAgent": 0
        }
        
        # Define mock responses per LangChain agent (ReAct format)
        agent_responses = {
            "LogAgent": [
                {  # Interaction 1 - Log analysis with get_logs action
                    "response_content": """Thought: I should analyze the application logs to find error patterns.
Action: kubernetes-server.get_logs
Action Input: {"namespace": "test-namespace", "pod": "pod-1"}""",
                    "input_tokens": 200, "output_tokens": 75, "total_tokens": 275
                },
                {  # Interaction 2 - Final answer
                    "response_content": """Thought: I have analyzed the logs and found the root cause.
Final Answer: Log analysis reveals database connection timeout errors. The pod is failing because it cannot connect to the database at db.example.com:5432. This explains the CrashLoopBackOff. Recommend verifying database availability and network connectivity.""",
                    "input_tokens": 190, "output_tokens": 70, "total_tokens": 260
                }
            ],
            "CommandAgent": [
                {  # Interaction 1 - Command agent final answer
                    "response_content": """Final Answer: **Remediation Commands**

Based on parallel investigations showing database connectivity issues causing CrashLoopBackOff:

**Diagnostic Commands:**
```bash
# Verify database service
kubectl get service database -n test-namespace
kubectl describe service database -n test-namespace

# Check network policies
kubectl get networkpolicies -n test-namespace

# Test database connectivity from pod
kubectl exec -n test-namespace pod-1 -- nc -zv db.example.com 5432
```

**Resolution Steps:**
1. Verify database service endpoint is correct
2. Check database is running and accepting connections
3. Review network policies for connectivity restrictions
4. Validate database credentials in ConfigMap/Secret
5. If database is external, verify firewall/security group rules

**Rollback Option:**
```bash
# If needed, rollback to previous working version
kubectl rollout undo deployment/app -n test-namespace
```""",
                    "input_tokens": 400, "output_tokens": 170, "total_tokens": 570
                }
            ]
        }
        
        # ============================================================================
        # LANGCHAIN STREAMING MOCK CREATOR
        # ============================================================================
        
        # Create agent-aware streaming mock for LangChain agents
        agent_identifiers = {
            "LogAgent": "log analysis specialist",
            "CommandAgent": "command execution specialist"
        }
        
        streaming_mock = E2ETestUtils.create_agent_aware_streaming_mock(
            agent_counters, agent_responses, agent_identifiers
        )
        
        # Create MCP mocks
        mock_k8s_session = E2ETestUtils.create_generic_mcp_session_mock("Mock kubectl response")
        mock_log_session = E2ETestUtils.create_generic_mcp_session_mock("Mock log response")
        mock_sessions = {
            "kubernetes-server": mock_k8s_session,
            "log-server": mock_log_session
        }
        
        mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)
        
        # Patch LLM clients (both Gemini SDK and LangChain)
        with self._create_llm_patch_context(gemini_mock_factory, streaming_mock):
            with patch('tarsy.integrations.mcp.client.MCPClient.list_tools', mock_list_tools):
                with patch('tarsy.integrations.mcp.client.MCPClient.call_tool', mock_call_tool):
                    with E2ETestUtils.setup_runbook_service_patching("# Test Runbook\nThis is a test runbook for parallel execution testing."):
                        # Create conversation map for verification
                        conversation_map = {
                            "investigation": {
                                "KubernetesAgent": EXPECTED_PARALLEL_NO_SYNTHESIS_AGENT_1_CONVERSATION,
                                "LogAgent": EXPECTED_PARALLEL_NO_SYNTHESIS_AGENT_2_CONVERSATION
                            },
                            "command": EXPECTED_REGULAR_AFTER_PARALLEL_CONVERSATION
                        }
                        
                        # Execute standard test flow (increased timeout for parallel + regular stages)
                        detail_data = await self._execute_test_flow(
                            test_client, alert_data,
                            expected_chain_id="parallel-then-regular-chain",
                            expected_stages_spec=EXPECTED_PARALLEL_REGULAR_STAGES,
                            conversation_map=conversation_map,
                            max_wait_seconds=30
                        )
                        
                        print("✅ Parallel + regular stage test passed!")
                        return detail_data

