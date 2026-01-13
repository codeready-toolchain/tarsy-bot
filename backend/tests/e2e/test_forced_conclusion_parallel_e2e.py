"""
E2E Test for Forced Conclusion with Parallel Agents.

This test verifies the forced conclusion workflow for parallel agent stages:
1. Multi-agent parallel where both agents reach max iterations
2. Both agents force conclusion with available data (no pause)
3. Synthesis runs with forced conclusion results
4. Mixed iteration strategies: Native Thinking + ReAct

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: HTTP requests to LLM APIs, MCP servers, GitHub runbooks
- CONFIGURED: max_llm_mcp_iterations=2, force_conclusion_at_max_iterations=True
- DETERMINISTIC: Mock responses provide predictable forced conclusion behavior
"""

import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import Tool

from tarsy.integrations.mcp.client import MCPClient

from .e2e_utils import E2ETestUtils, assert_conversation_messages
from .expected_forced_conclusion_conversations import (
    EXPECTED_FORCED_CONCLUSION_INTERACTIONS,
    EXPECTED_K8S_FORCED_CONCLUSION_CONVERSATION,
    EXPECTED_LOG_FORCED_CONCLUSION_CONVERSATION,
    EXPECTED_SESSION_TOTALS,
    EXPECTED_SYNTHESIS_FORCED_CONCLUSION_CONVERSATION,
)
from .parallel_test_base import ParallelTestBase

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestForcedConclusionParallelE2E(ParallelTestBase):
    """
    E2E test for forced conclusion functionality with parallel agents.
    
    Tests the complete system flow:
    1. Parallel stage where both agents reach max iterations
    2. Both agents force conclusion with available data (no pause)
    3. Forced conclusion interactions logged with FORCED_CONCLUSION type
    4. Final synthesis includes both forced conclusion results
    5. Mixed iteration strategies work correctly (Native Thinking + ReAct)
    """
    
    @pytest.mark.e2e
    async def test_parallel_agents_forced_conclusion(
        self, e2e_parallel_test_client, e2e_forced_conclusion_parallel_alert
    ):
        """
        Test multi-agent parallel with forced conclusion at max iterations.
        
        Flow:
        1. POST alert with max_iterations=2, force_conclusion=True
        2. Agent 1 (KubernetesAgent, Native Thinking): reaches iteration 2, forces conclusion
        3. Agent 2 (LogAgent, ReAct): reaches iteration 2, forces conclusion
        4. Verify both agents have FORCED_CONCLUSION interaction type
        5. Verify final synthesis includes both forced conclusion results
        6. Verify session completes successfully (not paused)
        """
        return await self._run_with_timeout(
            lambda: self._execute_forced_conclusion_test(
                e2e_parallel_test_client, e2e_forced_conclusion_parallel_alert
            ),
            test_name="parallel forced conclusion test",
            timeout_seconds=120
        )
    
    async def _execute_forced_conclusion_test(self, test_client, alert_data):
        """Execute the forced conclusion test for parallel agents."""
        print("🔧 Starting parallel forced conclusion test")
        
        # Override max_iterations to 2 for quick forced conclusion
        from tarsy.config.settings import get_settings
        settings = get_settings()
        original_max_iterations = settings.max_llm_mcp_iterations
        original_force_conclusion = settings.force_conclusion_at_max_iterations
        
        try:
            settings.max_llm_mcp_iterations = 2
            settings.force_conclusion_at_max_iterations = True
            print("🔧 Set max_llm_mcp_iterations to 2")
            print("🔧 Set force_conclusion_at_max_iterations to True")
            
            # ============================================================================
            # NATIVE THINKING MOCK (for KubernetesAgent and SynthesisAgent using Gemini)
            # ============================================================================
            # Gemini SDK responses for native thinking (function calling)
            # Note: The mock uses a simple counter, so responses are ordered by call sequence
            gemini_response_map = {
                1: {  # KubernetesAgent - First call - tool call with thinking
                    "text_content": "",  # Empty for tool calls
                    "thinking_content": "I should check the pod status in test-namespace to understand the issue.",
                    "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "pods", "namespace": "test-namespace"}}],
                    "input_tokens": 200,
                    "output_tokens": 60,
                    "total_tokens": 260
                },
                2: {  # KubernetesAgent - Second call - still investigating (reaches max iterations)
                    "text_content": "",  # Empty for tool calls
                    "thinking_content": "I see CrashLoopBackOff. Need to describe the pod for more details.",
                    "function_calls": [{"name": "kubernetes-server__kubectl_describe", "args": {"resource": "pod", "name": "pod-1", "namespace": "test-namespace"}}],
                    "input_tokens": 220,
                    "output_tokens": 70,
                    "total_tokens": 290
                },
                3: {  # KubernetesAgent - Forced conclusion call (no tools, just final answer)
                    "text_content": """**Forced Conclusion - Kubernetes Analysis**

Based on the investigation so far:

**Findings:**
- Pod pod-1 is in CrashLoopBackOff state in test-namespace
- Pod has been restarting repeatedly
- Container exit code indicates failure

**Limitations:**
Investigation reached iteration limit. Full root cause analysis incomplete, but initial findings suggest pod stability issues.

**Recommendations:**
1. Check pod logs for specific error messages
2. Review pod events for additional context
3. Verify resource limits and requests
4. Check for configuration issues

Further investigation needed for complete root cause analysis.""",
                    "thinking_content": "I've reached the iteration limit. I need to provide a conclusion based on what I've discovered so far.",
                    "function_calls": None,  # No tools in forced conclusion
                    "input_tokens": 250,
                    "output_tokens": 120,
                    "total_tokens": 370
                },
                4: {  # SynthesisAgent - Single call for synthesis (no tools, just thinking + final answer)
                    "text_content": """**Synthesis of Parallel Investigations (Forced Conclusions)**

Combined analysis from both agents (note: both reached iteration limits):

**From Kubernetes Agent (Forced Conclusion):**
- Pod pod-1 in CrashLoopBackOff state
- Multiple restart attempts observed
- Container exit code indicates failure
- Investigation incomplete due to iteration limit

**From Log Agent (Forced Conclusion):**
- Database connection timeout to db.example.com:5432
- Root cause: Unable to connect to database
- Investigation incomplete due to iteration limit

**Preliminary Conclusion:**
Pod is likely failing due to database connectivity issues. The pod attempts to connect to db.example.com:5432 but times out, causing crashes and CrashLoopBackOff.

**Note:** Both agents reached iteration limits and provided forced conclusions. Recommendations are based on available data.

**Recommended Actions:**
1. Verify database service is running and accessible
2. Check network connectivity to db.example.com:5432
3. Validate database credentials in pod configuration
4. Review firewall/network policies
5. Consider increasing timeout values if appropriate

**Follow-up:** Additional investigation may be needed for complete root cause analysis.""",
                    "thinking_content": "I need to synthesize the forced conclusions from both parallel investigations into a coherent analysis, noting that both reached iteration limits.",
                    "function_calls": None,  # Synthesis doesn't use tools
                    "input_tokens": 500,
                    "output_tokens": 220,
                    "total_tokens": 720
                }
            }
            
            # Create Gemini mock factory
            from .conftest import create_gemini_client_mock
            gemini_mock_factory = create_gemini_client_mock(gemini_response_map)
            
            # ============================================================================
            # LANGCHAIN MOCK (for LogAgent using ReAct only)
            # ============================================================================
            # Agent-specific interaction counters for LangChain-based agents
            agent_counters = {
                "LogAgent": 0,
            }
            
            # Define mock responses per LangChain agent (ReAct format)
            agent_responses = {
                "LogAgent": [
                    {  # Interaction 1 - Log analysis with get_logs action
                        "response_content": """Thought: I should check application logs to understand the failure.
Action: kubernetes-server.get_logs
Action Input: {"namespace": "test-namespace", "pod": "pod-1"}""",
                        "input_tokens": 190, "output_tokens": 55, "total_tokens": 245
                    },
                    {  # Interaction 2 - Still investigating (reaches max iterations)
                        "response_content": """Thought: Logs show database connection timeout. Need to investigate further but reached iteration limit.
Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "pod", "name": "pod-1", "namespace": "test-namespace"}""",
                        "input_tokens": 210, "output_tokens": 65, "total_tokens": 275
                    },
                    {  # Interaction 3 - Forced conclusion (no Action, just Thought + Final Answer)
                        "response_content": """Thought: I've reached the iteration limit. Based on the logs I've analyzed, I can provide a preliminary conclusion about the database connectivity issue.

Final Answer: **Forced Conclusion - Log Analysis**

Based on available log data:

**Findings:**
- Error: Database connection timeout to db.example.com:5432
- Pod failing due to inability to connect to database
- CrashLoopBackOff is result of repeated connection failures

**Limitations:**
Investigation reached iteration limit. Complete log analysis not performed, but critical error identified.

**Preliminary Root Cause:**
Database connectivity issue causing pod crashes.

**Recommendations:**
1. Verify database service availability
2. Check network connectivity from pod to database
3. Review database credentials
4. Examine connection timeout settings

Further investigation recommended for comprehensive analysis.""",
                        "input_tokens": 230, "output_tokens": 115, "total_tokens": 345
                    }
                ]
            }
            
            # ============================================================================
            # LANGCHAIN STREAMING MOCK CREATOR
            # ============================================================================
            
            # Create agent-aware streaming mock for LangChain agents (only LogAgent)
            agent_identifiers = {
                "LogAgent": "log analysis specialist"
            }
            
            streaming_mock = E2ETestUtils.create_agent_aware_streaming_mock(
                agent_counters, agent_responses, agent_identifiers
            )
            
            # ============================================================================
            # MCP CLIENT MOCKS
            # ============================================================================
            
            # Create MCP session mock
            def create_mcp_session_mock():
                mock_session = AsyncMock()
                
                async def mock_call_tool(tool_name, _parameters):
                    mock_result = Mock()
                    mock_content = Mock()
                    
                    if "kubectl_get" in tool_name:
                        mock_content.text = '{"result": "Pod pod-1 is in CrashLoopBackOff state"}'
                    elif "kubectl_describe" in tool_name:
                        mock_content.text = '{"result": "Pod pod-1 details: exit code 1, restart count 5"}'
                    elif "get_logs" in tool_name or "log" in tool_name.lower():
                        mock_content.text = '{"logs": "Error: Database connection timeout to db.example.com:5432"}'
                    else:
                        mock_content.text = '{"result": "Mock response"}'
                    
                    mock_result.content = [mock_content]
                    return mock_result
                
                async def mock_list_tools():
                    tools = [
                        Tool(
                            name="kubectl_get",
                            description="Get Kubernetes resources",
                            inputSchema={"type": "object", "properties": {}}
                        ),
                        Tool(
                            name="kubectl_describe",
                            description="Describe Kubernetes resources",
                            inputSchema={"type": "object", "properties": {}}
                        ),
                        Tool(
                            name="get_logs",
                            description="Get pod logs",
                            inputSchema={"type": "object", "properties": {}}
                        ),
                    ]
                    mock_result = Mock()
                    mock_result.tools = tools
                    return mock_result
                
                mock_session.call_tool.side_effect = mock_call_tool
                mock_session.list_tools.side_effect = mock_list_tools
                
                return mock_session
            
            # Create MCP client patches
            mock_k8s_session = create_mcp_session_mock()
            mock_sessions = {"kubernetes-server": mock_k8s_session}
            mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)
            
            # ============================================================================
            # APPLY MOCKS AND RUN TEST
            # ============================================================================
            
            # Patch LLM clients (both Gemini SDK and LangChain)
            with self._create_llm_patch_context(gemini_mock_factory, streaming_mock):
                with patch.object(MCPClient, "list_tools", mock_list_tools), \
                     patch.object(MCPClient, "call_tool", mock_call_tool):
                    with E2ETestUtils.setup_runbook_service_patching("# Test Runbook\nThis is a test runbook for forced conclusion testing."):
                        # ============================================================================
                        # STEP 1: Submit alert
                        # ============================================================================
                        print("🔧 Step 1: Submitting alert...")
                        session_id = E2ETestUtils.submit_alert(test_client, alert_data)
                        print(f"  ✅ Alert submitted, session_id: {session_id}")
                        
                        # ============================================================================
                        # STEP 2: Wait for completion (should complete, not pause)
                        # ============================================================================
                        print("🔧 Step 2: Waiting for session completion...")
                        session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                            test_client, max_wait_seconds=20
                        )
                        
                        # If session failed, get detailed error info before asserting
                        if final_status == "failed":
                            try:
                                detail_response = test_client.get(f"/api/v1/history/sessions/{session_id}")
                                if detail_response.status_code == 200:
                                    detail_data_temp = detail_response.json()
                                    error_message = detail_data_temp.get("error_message", "No error message")
                                    print(f"❌ Session failed with error: {error_message}")
                                    raise AssertionError(f"Session failed with status: {final_status}, error: {error_message}")
                            except Exception as e:
                                print(f"❌ Failed to get error details: {e}")
                        
                        # Session should complete successfully (not pause)
                        assert final_status == "completed", f"Session should complete with forced conclusions, got: {final_status}"
                        print(f"  ✅ Session completed with status: {final_status}")
                        
                        # ============================================================================
                        # STEP 3: Get session details
                        # ============================================================================
                        print("🔧 Step 3: Retrieving session details...")
                        detail_data = await E2ETestUtils.get_session_details_async(
                            test_client, session_id, max_retries=3, retry_delay=0.5
                        )
                        
                        # Verify session metadata
                        assert detail_data["status"] == "completed"
                        assert detail_data["chain_id"] == "multi-agent-forced-conclusion-chain"
                        assert detail_data["started_at_us"] is not None
                        assert detail_data["completed_at_us"] is not None
                        print("  ✅ Session metadata verified")
                        
                        # ============================================================================
                        # STEP 4: Verify stage structure
                        # ============================================================================
                        print("🔧 Step 4: Verifying stage structure...")
                        stages = detail_data.get("stages", [])
                        
                        # Should have 2 stages: investigation (parallel) + synthesis
                        assert len(stages) == 2, f"Expected 2 stages, got {len(stages)}"
                        
                        investigation_stage = stages[0]
                        synthesis_stage = stages[1]
                        
                        assert investigation_stage["stage_name"] == "investigation"
                        assert investigation_stage["parallel_type"] == "multi_agent"
                        assert investigation_stage["status"] == "completed"
                        
                        assert synthesis_stage["stage_name"] == "synthesis"
                        assert synthesis_stage["parallel_type"] == "single"
                        assert synthesis_stage["status"] == "completed"
                        print("  ✅ Stage structure verified")
                        
                        # ============================================================================
                        # STEP 5: Verify parallel agent executions
                        # ============================================================================
                        print("🔧 Step 5: Verifying parallel agent executions...")
                        parallel_executions = investigation_stage.get("parallel_executions", [])
                        assert len(parallel_executions) == 2, f"Expected 2 parallel executions, got {len(parallel_executions)}"
                        
                        # Find KubernetesAgent and LogAgent executions
                        k8s_execution = None
                        log_execution = None
                        
                        for execution in parallel_executions:
                            agent_name = execution.get("agent") or execution.get("agent_name")
                            if agent_name == "KubernetesAgent":
                                k8s_execution = execution
                            elif agent_name == "LogAgent":
                                log_execution = execution
                        
                        assert k8s_execution is not None, "KubernetesAgent execution not found"
                        assert log_execution is not None, "LogAgent execution not found"
                        
                        # Both should be completed (not paused)
                        assert k8s_execution["status"] == "completed", f"KubernetesAgent should complete, got: {k8s_execution['status']}"
                        assert log_execution["status"] == "completed", f"LogAgent should complete, got: {log_execution['status']}"
                        print("  ✅ Both agents completed successfully")
                        
                        # ============================================================================
                        # STEP 6: Verify KubernetesAgent forced conclusion
                        # ============================================================================
                        print("🔧 Step 6: Verifying KubernetesAgent forced conclusion...")
                        k8s_interactions = k8s_execution.get("llm_interactions", [])
                        
                        # Should have 3 LLM interactions: 2 regular + 1 forced conclusion
                        assert len(k8s_interactions) == 3, f"Expected 3 LLM interactions for KubernetesAgent, got {len(k8s_interactions)}"
                        
                        # Verify first two are investigation type
                        assert k8s_interactions[0]["details"]["interaction_type"] == "investigation"
                        assert k8s_interactions[1]["details"]["interaction_type"] == "investigation"
                        
                        # Verify third is forced conclusion type
                        forced_conclusion_interaction = k8s_interactions[2]
                        assert forced_conclusion_interaction["details"]["interaction_type"] == "forced_conclusion", \
                            f"Expected forced_conclusion interaction type, got: {forced_conclusion_interaction['details']['interaction_type']}"
                        
                        # Verify forced conclusion content
                        k8s_conversation = forced_conclusion_interaction["details"]["conversation"]
                        k8s_messages = k8s_conversation["messages"]
                        
                        # Verify complete conversation structure matches expected
                        expected_k8s_messages_count = len(EXPECTED_K8S_FORCED_CONCLUSION_CONVERSATION["messages"])
                        assert_conversation_messages(
                            EXPECTED_K8S_FORCED_CONCLUSION_CONVERSATION,
                            k8s_messages,
                            expected_k8s_messages_count
                        )
                        
                        # Verify exact token counts
                        expected_k8s_spec = EXPECTED_FORCED_CONCLUSION_INTERACTIONS['k8s_agent']
                        assert len(k8s_interactions) == expected_k8s_spec['llm_count']
                        
                        # Verify all 3 LLM interactions with exact token counts
                        for i, expected_interaction in enumerate(expected_k8s_spec['interactions']):
                            actual_interaction = k8s_interactions[i]
                            actual_details = actual_interaction["details"]
                            
                            assert actual_details["input_tokens"] == expected_interaction["input_tokens"], \
                                f"K8s interaction {i+1} input_tokens mismatch: expected {expected_interaction['input_tokens']}, got {actual_details['input_tokens']}"
                            assert actual_details["output_tokens"] == expected_interaction["output_tokens"], \
                                f"K8s interaction {i+1} output_tokens mismatch: expected {expected_interaction['output_tokens']}, got {actual_details['output_tokens']}"
                            assert actual_details["total_tokens"] == expected_interaction["total_tokens"], \
                                f"K8s interaction {i+1} total_tokens mismatch: expected {expected_interaction['total_tokens']}, got {actual_details['total_tokens']}"
                        
                        print("  ✅ KubernetesAgent forced conclusion verified with exact token counts")
                        
                        # ============================================================================
                        # STEP 7: Verify LogAgent forced conclusion
                        # ============================================================================
                        print("🔧 Step 7: Verifying LogAgent forced conclusion...")
                        log_interactions = log_execution.get("llm_interactions", [])
                        
                        # Should have 3 LLM interactions: 2 regular + 1 forced conclusion
                        assert len(log_interactions) == 3, f"Expected 3 LLM interactions for LogAgent, got {len(log_interactions)}"
                        
                        # Verify first two are investigation type
                        assert log_interactions[0]["details"]["interaction_type"] == "investigation"
                        assert log_interactions[1]["details"]["interaction_type"] == "investigation"
                        
                        # Verify third is forced conclusion type
                        log_forced_conclusion = log_interactions[2]
                        assert log_forced_conclusion["details"]["interaction_type"] == "forced_conclusion", \
                            f"Expected forced_conclusion interaction type, got: {log_forced_conclusion['details']['interaction_type']}"
                        
                        # Verify forced conclusion content (ReAct format with Final Answer)
                        log_conversation = log_forced_conclusion["details"]["conversation"]
                        log_messages = log_conversation["messages"]
                        
                        # Verify the forced conclusion prompt was sent
                        # Verify complete conversation structure matches expected (ReAct format)
                        expected_log_messages_count = len(EXPECTED_LOG_FORCED_CONCLUSION_CONVERSATION["messages"])
                        assert_conversation_messages(
                            EXPECTED_LOG_FORCED_CONCLUSION_CONVERSATION,
                            log_messages,
                            expected_log_messages_count
                        )
                        
                        # Verify exact token counts for LogAgent
                        expected_log_spec = EXPECTED_FORCED_CONCLUSION_INTERACTIONS['log_agent']
                        assert len(log_interactions) == expected_log_spec['llm_count']
                        
                        # Verify all 3 LLM interactions with exact token counts
                        for i, expected_interaction in enumerate(expected_log_spec['interactions']):
                            actual_interaction = log_interactions[i]
                            actual_details = actual_interaction["details"]
                            
                            assert actual_details["input_tokens"] == expected_interaction["input_tokens"], \
                                f"Log interaction {i+1} input_tokens mismatch: expected {expected_interaction['input_tokens']}, got {actual_details['input_tokens']}"
                            assert actual_details["output_tokens"] == expected_interaction["output_tokens"], \
                                f"Log interaction {i+1} output_tokens mismatch: expected {expected_interaction['output_tokens']}, got {actual_details['output_tokens']}"
                            assert actual_details["total_tokens"] == expected_interaction["total_tokens"], \
                                f"Log interaction {i+1} total_tokens mismatch: expected {expected_interaction['total_tokens']}, got {actual_details['total_tokens']}"
                        
                        print("  ✅ LogAgent forced conclusion verified with exact token counts")
                        
                        # ============================================================================
                        # STEP 8: Verify MCP tool calls
                        # ============================================================================
                        print("🔧 Step 8: Verifying MCP tool calls...")
                        
                        # KubernetesAgent should have MCP calls (tool_list + actual tool calls)
                        k8s_mcp = k8s_execution.get("mcp_communications", [])
                        # Filter to only tool_call type (exclude tool_list)
                        k8s_tool_calls = [mcp for mcp in k8s_mcp if mcp["details"].get("communication_type") == "tool_call"]
                        assert len(k8s_tool_calls) == 2, f"Expected 2 tool calls for KubernetesAgent, got {len(k8s_tool_calls)}"
                        assert k8s_tool_calls[0]["details"]["tool_name"] == "kubectl_get"
                        assert k8s_tool_calls[1]["details"]["tool_name"] == "kubectl_describe"
                        
                        # LogAgent should have MCP calls (tool_list + actual tool calls)
                        log_mcp = log_execution.get("mcp_communications", [])
                        # Filter to only tool_call type (exclude tool_list)
                        log_tool_calls = [mcp for mcp in log_mcp if mcp["details"].get("communication_type") == "tool_call"]
                        assert len(log_tool_calls) == 2, f"Expected 2 tool calls for LogAgent, got {len(log_tool_calls)}"
                        assert log_tool_calls[0]["details"]["tool_name"] == "get_logs"
                        assert log_tool_calls[1]["details"]["tool_name"] == "kubectl_describe"
                        print("  ✅ MCP tool calls verified")
                        
                        # ============================================================================
                        # STEP 9: Verify synthesis stage
                        # ============================================================================
                        print("🔧 Step 9: Verifying synthesis stage...")
                        synthesis_interactions = synthesis_stage.get("llm_interactions", [])
                        
                        # Should have 1 synthesis interaction
                        assert len(synthesis_interactions) == 1, f"Expected 1 synthesis interaction, got {len(synthesis_interactions)}"
                        
                        synthesis_interaction = synthesis_interactions[0]
                        assert synthesis_interaction["details"]["interaction_type"] == "final_analysis"
                        
                        # Verify synthesis conversation structure matches expected
                        synthesis_conversation = synthesis_interaction["details"]["conversation"]
                        synthesis_messages = synthesis_conversation["messages"]
                        
                        expected_synthesis_messages_count = len(EXPECTED_SYNTHESIS_FORCED_CONCLUSION_CONVERSATION["messages"])
                        assert_conversation_messages(
                            EXPECTED_SYNTHESIS_FORCED_CONCLUSION_CONVERSATION,
                            synthesis_messages,
                            expected_synthesis_messages_count
                        )
                        
                        # Verify exact token counts for synthesis
                        expected_synthesis_spec = EXPECTED_FORCED_CONCLUSION_INTERACTIONS['synthesis']
                        assert len(synthesis_interactions) == expected_synthesis_spec['llm_count']
                        
                        expected_synth_interaction = expected_synthesis_spec['interactions'][0]
                        assert synthesis_interaction["details"]["input_tokens"] == expected_synth_interaction["input_tokens"], \
                            f"Synthesis input_tokens mismatch: expected {expected_synth_interaction['input_tokens']}, got {synthesis_interaction['details']['input_tokens']}"
                        assert synthesis_interaction["details"]["output_tokens"] == expected_synth_interaction["output_tokens"], \
                            f"Synthesis output_tokens mismatch: expected {expected_synth_interaction['output_tokens']}, got {synthesis_interaction['details']['output_tokens']}"
                        assert synthesis_interaction["details"]["total_tokens"] == expected_synth_interaction["total_tokens"], \
                            f"Synthesis total_tokens mismatch: expected {expected_synth_interaction['total_tokens']}, got {synthesis_interaction['details']['total_tokens']}"
                        
                        print("  ✅ Synthesis stage verified with exact token counts")
                        
                        # ============================================================================
                        # STEP 10: Verify session-level token aggregation
                        # ============================================================================
                        print("🔧 Step 10: Verifying session-level token aggregation...")
                        
                        # Verify session-level token aggregation with exact expected totals
                        actual_input = detail_data.get("session_input_tokens")
                        actual_output = detail_data.get("session_output_tokens")
                        actual_total = detail_data.get("session_total_tokens")
                        
                        expected_input = EXPECTED_SESSION_TOTALS['input_tokens']
                        expected_output = EXPECTED_SESSION_TOTALS['output_tokens']
                        expected_total = EXPECTED_SESSION_TOTALS['total_tokens']
                        
                        assert actual_input == expected_input, \
                            f"Session input_tokens mismatch: expected {expected_input}, got {actual_input}"
                        assert actual_output == expected_output, \
                            f"Session output_tokens mismatch: expected {expected_output}, got {actual_output}"
                        assert actual_total == expected_total, \
                            f"Session total_tokens mismatch: expected {expected_total}, got {actual_total}"
                        assert actual_total == actual_input + actual_output, "Token totals don't add up correctly"
                        
                        print(f"  ✅ Session tokens verified: {actual_input} input + {actual_output} output = {actual_total} total (exact match)")
                        
                        print("✅ All verifications passed!")
        
        finally:
            # Restore original settings
            settings.max_llm_mcp_iterations = original_max_iterations
            settings.force_conclusion_at_max_iterations = original_force_conclusion
            print(f"🔧 Restored max_llm_mcp_iterations to {original_max_iterations}")
            print(f"🔧 Restored force_conclusion_at_max_iterations to {original_force_conclusion}")
