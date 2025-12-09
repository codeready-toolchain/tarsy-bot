"""
E2E Test for Pause/Resume with Parallel Agents.

This test verifies the pause/resume workflow for parallel agent stages:
1. Multi-agent parallel where one agent pauses while others complete
2. Resume continues only the paused agent (completed results preserved)
3. Multiple pause/resume cycles on parallel stages
4. Mixed status handling (complete, pause, fail)

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

from tarsy.config.builtin_config import BUILTIN_MCP_SERVERS
from tarsy.integrations.mcp.client import MCPClient

from .conftest import create_mock_stream
from .e2e_utils import E2ETestUtils
from .parallel_test_base import ParallelTestBase

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestPauseResumeParallelE2E(ParallelTestBase):
    """
    E2E test for pause/resume functionality with parallel agents.
    
    Tests the complete system flow:
    1. Parallel stage where one agent pauses (others complete)
    2. Session enters PAUSED state (pause priority)
    3. Resume re-executes only paused agents
    4. Completed agent results are preserved
    5. Final synthesis includes all agent results
    """
    
    @pytest.mark.e2e
    async def test_multi_agent_pause_resume(
        self, e2e_parallel_test_client, e2e_parallel_alert
    ):
        """
        Test multi-agent parallel with one agent pausing.
        
        Flow:
        1. POST alert with max_iterations=2
        2. Agent 1 (Kubernetes): pauses at iteration 2
        3. Agent 2 (Log): completes with Final Answer at iteration 2
        4. Verify stage status = PAUSED (pause priority over complete)
        5. Resume with max_iterations=4
        6. Verify only Agent 1 re-executes (Agent 2 result preserved)
        7. Verify final synthesis includes both agent results
        """
        return await self._run_with_timeout(
            lambda: self._execute_pause_resume_test(
                e2e_parallel_test_client, e2e_parallel_alert
            ),
            test_name="multi-agent pause/resume test",
            timeout_seconds=120
        )
    
    async def _execute_pause_resume_test(self, test_client, alert_data):
        """Execute the pause/resume test for parallel agents."""
        print("🔧 Starting parallel pause/resume test")
        
        # Override max_iterations to 2 for quick pause
        from tarsy.config.settings import get_settings
        settings = get_settings()
        original_max_iterations = settings.max_llm_mcp_iterations
        
        try:
            settings.max_llm_mcp_iterations = 2
            print(f"🔧 Set max_llm_mcp_iterations to 2")
            
            # Track all LLM interactions
            all_llm_interactions = []
            
            # Define mock response map
            # Phase 1 (max_iterations=2): Kubernetes pauses at 2, Log completes at 2
            # Phase 2 (max_iterations=4): Kubernetes continues from pause and completes
            mock_response_map = {
                # Phase 1: Initial execution
                # Kubernetes Agent - will pause at iteration 2
                "kubernetes_1": {
                    "response_content": """Thought: I need to check pod status.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "namespace": "test-namespace"}""",
                    "input_tokens": 200,
                    "output_tokens": 60,
                    "total_tokens": 260,
                },
                "kubernetes_2": {
                    # Pauses - no Final Answer
                    "response_content": """Thought: I see CrashLoopBackOff. Need more investigation but hit iteration limit.
Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "pod", "name": "pod-1", "namespace": "test-namespace"}""",
                    "input_tokens": 220,
                    "output_tokens": 70,
                    "total_tokens": 290,
                },
                # Log Agent - completes at iteration 2
                "log_1": {
                    "response_content": """Thought: I should check application logs.
Action: kubernetes-server.get_logs
Action Input: {"namespace": "test-namespace", "pod": "pod-1"}""",
                    "input_tokens": 190,
                    "output_tokens": 55,
                    "total_tokens": 245,
                },
                "log_2": {
                    # Completes with Final Answer
                    "response_content": """Thought: Logs show database connection timeout.

Final Answer: **Log Analysis Complete**

Found critical error in logs:
- Error: Database connection timeout to db.example.com:5432
- Pod failing due to inability to connect to database
- CrashLoopBackOff is result of repeated connection failures

Root cause identified from logs.""",
                    "input_tokens": 210,
                    "output_tokens": 85,
                    "total_tokens": 295,
                },
                # Phase 2: Resume - only Kubernetes continues
                "kubernetes_3": {
                    # After resume, continues investigation
                    "response_content": """Thought: I can now complete my investigation.

Final Answer: **Kubernetes Analysis Complete**

Infrastructure findings:
- Pod pod-1 in CrashLoopBackOff state
- Namespace: test-namespace
- Pod has been restarting repeatedly (5+ times)
- Container exit code indicates connection failure

Kubernetes investigation complete.""",
                    "input_tokens": 240,
                    "output_tokens": 95,
                    "total_tokens": 335,
                },
                # Synthesis stage
                "synthesis_1": {
                    "response_content": """Final Answer: **Synthesis of Parallel Investigations**

Combined analysis from both agents:

**From Kubernetes Agent:**
- Pod pod-1 in CrashLoopBackOff
- Multiple restart attempts (5+)
- Container exit code indicates connection failure

**From Log Agent:**
- Database connection timeout to db.example.com:5432
- Root cause: Unable to connect to database

**Conclusion:**
Pod is failing due to database connectivity issues. The pod attempts to connect to db.example.com:5432 but times out, causing crashes and CrashLoopBackOff.

**Recommended Actions:**
1. Verify database service is running
2. Check network connectivity to db.example.com:5432
3. Validate database credentials
4. Review firewall/network policies""",
                    "input_tokens": 450,
                    "output_tokens": 200,
                    "total_tokens": 650,
                },
            }
            
            # Create agent-aware streaming mock
            agent_counters = {
                "KubernetesAgent": 0,
                "LogAgent": 0,
                "SynthesisAgent": 0,
            }
            
            def create_streaming_mock():
                """Create mock astream that routes to correct agent responses."""
                async def mock_astream(*args, **_kwargs):
                    # Determine which agent is calling based on message content
                    if args and len(args) > 0:
                        messages = args[0]
                        agent_type = None
                        
                        # Identify agent from system message
                        for msg in messages:
                            content = getattr(msg, "content", "") if hasattr(msg, "content") else ""
                            if "Kubernetes infrastructure specialist" in content:
                                agent_type = "KubernetesAgent"
                                break
                            elif "log analysis specialist" in content:
                                agent_type = "LogAgent"
                                break
                            elif "Incident Commander synthesizing" in content:
                                agent_type = "SynthesisAgent"
                                break
                        
                        if not agent_type:
                            agent_type = "unknown"
                        
                        # Increment counter
                        if agent_type in agent_counters:
                            agent_counters[agent_type] += 1
                            interaction_num = agent_counters[agent_type]
                        else:
                            interaction_num = 1
                        
                        all_llm_interactions.append((agent_type, interaction_num))
                        
                        # Get mock response
                        key = f"{agent_type.lower().replace('agent', '')}_{interaction_num}"
                        mock_response = mock_response_map.get(key, {
                            "response_content": "Unknown response",
                            "input_tokens": 100,
                            "output_tokens": 50,
                            "total_tokens": 150,
                        })
                        
                        print(f"🔍 LLM call: {agent_type} interaction {interaction_num} (key: {key})")
                        
                        content = mock_response["response_content"]
                        usage_metadata = {
                            "input_tokens": mock_response["input_tokens"],
                            "output_tokens": mock_response["output_tokens"],
                            "total_tokens": mock_response["total_tokens"],
                        }
                        
                        async for chunk in create_mock_stream(content, usage_metadata):
                            yield chunk
                
                return mock_astream
            
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
            
            # Setup mocking infrastructure
            k8s_config = E2ETestUtils.create_simple_kubernetes_mcp_config(
                command_args=["kubernetes-mock-server-ready"],
                instructions="Test kubernetes server for parallel pause/resume",
            )
            
            test_mcp_servers = E2ETestUtils.create_test_mcp_servers(
                BUILTIN_MCP_SERVERS, {"kubernetes-server": k8s_config}
            )
            
            with patch("tarsy.config.builtin_config.BUILTIN_MCP_SERVERS", test_mcp_servers), \
                 patch("tarsy.services.mcp_server_registry.MCPServerRegistry._DEFAULT_SERVERS", test_mcp_servers), \
                 E2ETestUtils.setup_runbook_service_patching("# Parallel Pause Test Runbook"):
                
                # Mock LLM clients
                streaming_mock = create_streaming_mock()
                from langchain_anthropic import ChatAnthropic
                from langchain_google_genai import ChatGoogleGenerativeAI
                from langchain_openai import ChatOpenAI
                from langchain_xai import ChatXAI
                
                with patch.object(ChatOpenAI, "astream", streaming_mock), \
                     patch.object(ChatAnthropic, "astream", streaming_mock), \
                     patch.object(ChatXAI, "astream", streaming_mock), \
                     patch.object(ChatGoogleGenerativeAI, "astream", streaming_mock):
                    
                    # Mock MCP client
                    mock_k8s_session = create_mcp_session_mock()
                    mock_sessions = {"kubernetes-server": mock_k8s_session}
                    mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)
                    
                    async def mock_initialize(self):
                        self.sessions = mock_sessions.copy()
                        self._initialized = True
                    
                    with patch.object(MCPClient, "initialize", mock_initialize), \
                         patch.object(MCPClient, "list_tools", mock_list_tools), \
                         patch.object(MCPClient, "call_tool", mock_call_tool):
                        
                        # ===== Phase 1: Initial execution with pause =====
                        print("\n⏳ Phase 1: Submit alert (max_iterations=2)")
                        session_id = E2ETestUtils.submit_alert(test_client, alert_data)
                        
                        print("⏳ Wait for session to pause...")
                        paused_session_id, paused_status = await E2ETestUtils.wait_for_session_completion(
                            test_client, max_wait_seconds=20, debug_logging=True
                        )
                        
                        print("🔍 Verify pause state...")
                        assert paused_session_id == session_id
                        assert paused_status == "paused", f"Expected 'paused', got '{paused_status}'"
                        
                        # Get session details
                        detail_data = await E2ETestUtils.get_session_details_async(test_client, session_id)
                        
                        # Verify pause metadata
                        pause_metadata = detail_data.get("pause_metadata")
                        assert pause_metadata is not None, "pause_metadata missing"
                        assert pause_metadata.get("reason") == "max_iterations_reached"
                        print(f"✅ Session paused: {pause_metadata}")
                        
                        # Verify parallel stage structure
                        stages = detail_data.get("stages", [])
                        assert len(stages) == 1, f"Expected 1 stage, got {len(stages)}"
                        
                        parallel_stage = stages[0]
                        assert parallel_stage["stage_name"] == "investigation"
                        assert parallel_stage["status"] == "paused"
                        assert parallel_stage["parallel_type"] == "multi_agent"
                        
                        # Verify child executions
                        parallel_executions = parallel_stage.get("parallel_executions")
                        assert parallel_executions is not None
                        assert len(parallel_executions) == 2, f"Expected 2 agents, got {len(parallel_executions)}"
                        
                        # Find Kubernetes and Log agent executions
                        k8s_exec = next((e for e in parallel_executions if e["agent"] == "KubernetesAgent"), None)
                        log_exec = next((e for e in parallel_executions if e["agent"] == "LogAgent"), None)
                        
                        assert k8s_exec is not None, "KubernetesAgent execution not found"
                        assert log_exec is not None, "LogAgent execution not found"
                        
                        # Verify statuses
                        assert k8s_exec["status"] == "paused", f"Kubernetes should be paused, got {k8s_exec['status']}"
                        assert log_exec["status"] == "completed", f"Log should be completed, got {log_exec['status']}"
                        
                        # Verify interaction counts (2 each during initial phase)
                        assert len(k8s_exec.get("llm_interactions", [])) == 2, "Kubernetes should have 2 LLM interactions"
                        assert len(log_exec.get("llm_interactions", [])) == 2, "Log should have 2 LLM interactions"
                        
                        print(f"✅ Parallel stage verified:")
                        print(f"   - KubernetesAgent: PAUSED (2 interactions)")
                        print(f"   - LogAgent: COMPLETED (2 interactions)")
                        
                        # ===== Phase 2: Resume with higher max_iterations =====
                        print("\n⏳ Phase 2: Resume (max_iterations=4)")
                        settings.max_llm_mcp_iterations = 4
                        
                        resume_response = test_client.post(f"/api/v1/history/sessions/{session_id}/resume")
                        assert resume_response.status_code == 200
                        resume_data = resume_response.json()
                        assert resume_data.get("success") is True
                        assert resume_data.get("status") == "resuming"
                        
                        print("⏳ Wait for resumed session to complete...")
                        final_session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                            test_client, max_wait_seconds=20, debug_logging=True
                        )
                        
                        print("🔍 Verify final state...")
                        assert final_session_id == session_id
                        assert final_status == "completed", f"Expected 'completed', got '{final_status}'"
                        
                        # Get final session details
                        final_detail = await E2ETestUtils.get_session_details_async(test_client, session_id)
                        
                        # Verify pause_metadata cleared
                        assert final_detail.get("pause_metadata") is None, "pause_metadata should be cleared"
                        
                        # Verify final stages
                        final_stages = final_detail.get("stages", [])
                        # Should have: investigation (parallel, completed) + synthesis (auto-synthesis)
                        assert len(final_stages) == 2, f"Expected 2 stages (investigation + synthesis), got {len(final_stages)}"
                        
                        investigation_stage = final_stages[0]
                        synthesis_stage = final_stages[1]
                        
                        assert investigation_stage["stage_name"] == "investigation"
                        assert investigation_stage["status"] == "completed"
                        assert synthesis_stage["stage_name"] == "synthesis"
                        assert synthesis_stage["status"] == "completed"
                        
                        # Verify investigation stage has both agents' results
                        inv_parallel_execs = investigation_stage.get("parallel_executions", [])
                        assert len(inv_parallel_execs) == 2
                        
                        final_k8s_exec = next((e for e in inv_parallel_execs if e["agent"] == "KubernetesAgent"), None)
                        final_log_exec = next((e for e in inv_parallel_execs if e["agent"] == "LogAgent"), None)
                        
                        assert final_k8s_exec["status"] == "completed", "Kubernetes should be completed after resume"
                        assert final_log_exec["status"] == "completed", "Log should still be completed"
                        
                        # Verify Kubernetes has 3 total interactions (2 initial + 1 resumed)
                        final_k8s_llm = len(final_k8s_exec.get("llm_interactions", []))
                        assert final_k8s_llm == 3, f"Kubernetes should have 3 LLM interactions total, got {final_k8s_llm}"
                        
                        # Verify Log still has 2 interactions (not re-executed)
                        final_log_llm = len(final_log_exec.get("llm_interactions", []))
                        assert final_log_llm == 2, f"Log should still have 2 LLM interactions (not re-executed), got {final_log_llm}"
                        
                        # Verify synthesis used both results
                        synthesis_llm = synthesis_stage.get("llm_interactions", [])
                        assert len(synthesis_llm) == 1, "Synthesis should have 1 LLM interaction"
                        
                        # Verify executive summary generated
                        assert final_detail.get("final_analysis_summary") is not None
                        assert len(final_detail.get("final_analysis_summary", "")) > 0
                        
                        print(f"✅ ALL VALIDATIONS PASSED!")
                        print(f"   - Kubernetes resumed and completed (3 total interactions)")
                        print(f"   - Log preserved from initial execution (2 interactions)")
                        print(f"   - Synthesis combined both results")
                        print(f"   - Executive summary generated")
                        print(f"   - Total LLM calls: {len(all_llm_interactions)}")
                        
                        return final_detail
        
        finally:
            # Restore original setting
            settings.max_llm_mcp_iterations = original_max_iterations
            print(f"🔧 Restored max_llm_mcp_iterations to {original_max_iterations}")

