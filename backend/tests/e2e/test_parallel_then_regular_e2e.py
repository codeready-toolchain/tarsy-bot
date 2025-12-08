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

import asyncio
import logging
from unittest.mock import patch

import pytest

from .conftest import create_mock_stream
from .e2e_utils import E2ETestUtils, assert_conversation_messages
from .expected_parallel_conversations import (
    EXPECTED_PARALLEL_NO_SYNTHESIS_AGENT_1_CONVERSATION,
    EXPECTED_PARALLEL_NO_SYNTHESIS_AGENT_2_CONVERSATION,
    EXPECTED_REGULAR_AFTER_PARALLEL_CONVERSATION,
    EXPECTED_PARALLEL_REGULAR_STAGES,
)

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestParallelThenRegularE2E:
    """E2E test for parallel stage followed by regular stage."""

    @pytest.mark.e2e
    async def test_parallel_then_regular_stage(
        self, e2e_test_client, e2e_parallel_regular_alert
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

        async def run_test():
            print("🚀 Starting parallel + regular test...")
            result = await self._execute_parallel_regular_test(
                e2e_test_client, e2e_parallel_regular_alert
            )
            print("✅ Parallel + regular test completed!")
            return result

        try:
            task = asyncio.create_task(run_test())
            done, pending = await asyncio.wait({task}, timeout=500.0)

            if pending:
                for t in pending:
                    t.cancel()
                print("❌ TIMEOUT: Test exceeded 500 seconds!")
                raise AssertionError("Test exceeded timeout of 500 seconds")
            else:
                return task.result()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            raise

    async def _execute_parallel_regular_test(self, test_client, alert_data):
        """Execute parallel + regular stage test."""
        print("🔧 Starting parallel + regular stage test execution")

        # Track all LLM interactions
        all_llm_interactions = []
        
        # Define mock responses
        # Token counts must match EXPECTED_PARALLEL_REGULAR_STAGES in expected_parallel_conversations.py
        # Agent1: interactions 1-2, Agent2: interactions 3-4, Command stage: interaction 5
        mock_response_map = {
            1: {  # Agent1 (KubernetesAgent) - Initial analysis (LLM position 1)
                "response_content": """Thought: I should check the pod status in the test-namespace to understand any issues.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "namespace": "test-namespace"}""",
                "input_tokens": 245, "output_tokens": 85, "total_tokens": 330
            },
            2: {  # Agent1 - Final answer (LLM position 2)
                "response_content": """Final Answer: Investigation complete. Found pod-1 in CrashLoopBackOff state in test-namespace. This indicates the pod is repeatedly crashing and Kubernetes is backing off on restart attempts. Recommend checking pod logs and events for root cause.""",
                "input_tokens": 180, "output_tokens": 65, "total_tokens": 245
            },
            3: {  # Agent2 (LogAgent) - Log analysis (LLM position 1)
                "response_content": """Thought: I should analyze the application logs to find error patterns.
Action: log-server.get_logs
Action Input: {"namespace": "test-namespace", "pod": "pod-1"}""",
                "input_tokens": 200, "output_tokens": 75, "total_tokens": 275
            },
            4: {  # Agent2 - Final answer (LLM position 2)
                "response_content": """Final Answer: Log analysis reveals database connection timeout errors. The pod is failing because it cannot connect to the database at db.example.com:5432. This explains the CrashLoopBackOff. Recommend verifying database availability and network connectivity.""",
                "input_tokens": 190, "output_tokens": 70, "total_tokens": 260
            },
            5: {  # Command agent (uses parallel results) (LLM position 1)
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
        }
        
        # Create streaming mock
        def create_streaming_mock():
            async def mock_astream(*args, **kwargs):
                interaction_num = len(all_llm_interactions) + 1
                all_llm_interactions.append(interaction_num)
                
                print(f"\n🔍 LLM REQUEST #{interaction_num}")
                
                response_data = mock_response_map.get(interaction_num, {
                    "response_content": "Default response",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150
                })
                
                content = response_data["response_content"]
                usage_metadata = {
                    "input_tokens": response_data["input_tokens"],
                    "output_tokens": response_data["output_tokens"],
                    "total_tokens": response_data["total_tokens"]
                }
                
                # Yield chunks from the mock stream - must be an async generator
                async for chunk in create_mock_stream(content, usage_metadata):
                    yield chunk
            
            return mock_astream
        
        # Create MCP mocks
        mock_k8s_session = E2ETestUtils.create_generic_mcp_session_mock("Mock kubectl response")
        mock_log_session = E2ETestUtils.create_generic_mcp_session_mock("Mock log response")
        mock_sessions = {
            "kubernetes-server": mock_k8s_session,
            "log-server": mock_log_session
        }
        
        mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)
        
        # Create streaming mock for LLM - patch LangChain clients directly
        streaming_mock = create_streaming_mock()
        
        # Import LangChain clients to patch
        from langchain_anthropic import ChatAnthropic
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_openai import ChatOpenAI
        from langchain_xai import ChatXAI
        
        # Patch and execute - Note: Using parallel-then-regular-chain config
        with patch.object(ChatOpenAI, 'astream', streaming_mock), \
             patch.object(ChatAnthropic, 'astream', streaming_mock), \
             patch.object(ChatXAI, 'astream', streaming_mock), \
             patch.object(ChatGoogleGenerativeAI, 'astream', streaming_mock):
            
            with patch('tarsy.integrations.mcp.client.MCPClient.list_tools', mock_list_tools):
                with patch('tarsy.integrations.mcp.client.MCPClient.call_tool', mock_call_tool):
                    with E2ETestUtils.setup_runbook_service_patching("# Test Runbook\nThis is a test runbook for parallel execution testing."):
                        # Submit alert
                        session_id = E2ETestUtils.submit_alert(test_client, alert_data)
                        
                        # Wait for completion
                        session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                            test_client, max_wait_seconds=20
                        )
                        
                        assert final_status == "completed", f"Session failed with status: {final_status}"
                        
                        # Get session details
                        detail_data = await E2ETestUtils.get_session_details_async(
                            test_client, session_id, max_retries=3, retry_delay=0.5
                        )
                        
                        # Verify session metadata
                        self._verify_session_metadata(detail_data, "parallel-then-regular-chain")
                        
                        # Get stages
                        stages = detail_data.get("stages", [])
                        
                        # Comprehensive verification
                        print("🔍 Step 4: Comprehensive result verification...")
                        self._verify_stage_structure(stages, EXPECTED_PARALLEL_REGULAR_STAGES)
                        self._verify_complete_interaction_flow(stages)
                        
                        print("✅ Parallel + regular stage test passed!")
                        return detail_data

    def _verify_session_metadata(self, detail_data, expected_chain_id):
        """Verify session metadata."""
        assert detail_data["status"] == "completed"
        assert detail_data["chain_id"] == expected_chain_id
        assert detail_data["started_at_us"] is not None
        assert detail_data["completed_at_us"] is not None

    def _verify_stage_structure(self, stages, expected_stages_spec):
        """Verify the structure of stages matches expectations."""
        print("  📋 Verifying stage structure...")
        
        expected_stage_names = list(expected_stages_spec.keys())
        actual_stage_names = [stage["stage_name"] for stage in stages]
        
        assert len(stages) == len(expected_stage_names), (
            f"Stage count mismatch: expected {len(expected_stage_names)}, got {len(stages)}"
        )
        
        for expected_name, actual_name in zip(expected_stage_names, actual_stage_names):
            assert actual_name == expected_name, (
                f"Stage name mismatch: expected '{expected_name}', got '{actual_name}'"
            )
        
        print(f"    ✅ Stage structure verified ({len(stages)} stages)")

    def _verify_parallel_stage_interactions(self, stage, expected_stage_spec):
        """Verify interactions for a parallel stage."""
        stage_name = stage["stage_name"]
        print(f"  🔍 Verifying parallel stage '{stage_name}' interactions...")
        
        # Verify parallel type
        assert stage["parallel_type"] == expected_stage_spec["parallel_type"], (
            f"Stage '{stage_name}' parallel_type mismatch"
        )
        
        # Verify parallel executions exist
        parallel_executions = stage.get("parallel_executions")
        assert parallel_executions is not None, f"Stage '{stage_name}' missing parallel_executions"
        
        expected_agents = expected_stage_spec["agents"]
        assert len(parallel_executions) == expected_stage_spec["agent_count"], (
            f"Stage '{stage_name}' agent count mismatch: expected {expected_stage_spec['agent_count']}, "
            f"got {len(parallel_executions)}"
        )
        
        # Verify each agent's execution
        for agent_name, expected_agent_spec in expected_agents.items():
            # Find the matching parallel execution
            agent_execution = None
            for execution in parallel_executions:
                if execution["agent_name"] == agent_name:
                    agent_execution = execution
                    break
            
            assert agent_execution is not None, (
                f"Stage '{stage_name}' missing execution for agent '{agent_name}'"
            )
            
            print(f"    🔍 Verifying agent '{agent_name}'...")
            
            # Verify interactions for this agent
            interactions = agent_execution.get("interactions", [])
            expected_interactions = expected_agent_spec["interactions"]
            
            assert len(interactions) == len(expected_interactions), (
                f"Agent '{agent_name}' interaction count mismatch: "
                f"expected {len(expected_interactions)}, got {len(interactions)}"
            )
            
            # Get expected conversation for this agent
            if agent_name == "KubernetesAgent":
                expected_conversation = EXPECTED_PARALLEL_NO_SYNTHESIS_AGENT_1_CONVERSATION
            elif agent_name == "LogAgent":
                expected_conversation = EXPECTED_PARALLEL_NO_SYNTHESIS_AGENT_2_CONVERSATION
            else:
                expected_conversation = None
            
            # Verify each interaction
            for i, expected_interaction in enumerate(expected_interactions):
                actual_interaction = interactions[i]
                interaction_type = expected_interaction["type"]
                
                assert actual_interaction["type"] == interaction_type, (
                    f"Agent '{agent_name}' interaction {i+1} type mismatch"
                )
                
                details = actual_interaction["details"]
                assert details["success"] == expected_interaction["success"], (
                    f"Agent '{agent_name}' interaction {i+1} success mismatch"
                )
                
                if interaction_type == "llm":
                    # Verify conversation content
                    actual_conversation = details["conversation"]
                    actual_messages = actual_conversation["messages"]
                    
                    if "conversation_index" in expected_interaction:
                        conversation_index = expected_interaction["conversation_index"]
                        assert_conversation_messages(
                            expected_conversation, actual_messages, conversation_index
                        )
                    
                    # Verify token usage
                    if "input_tokens" in expected_interaction:
                        assert details["input_tokens"] == expected_interaction["input_tokens"], (
                            f"Agent '{agent_name}' LLM interaction {i+1} input_tokens mismatch"
                        )
                        assert details["output_tokens"] == expected_interaction["output_tokens"], (
                            f"Agent '{agent_name}' LLM interaction {i+1} output_tokens mismatch"
                        )
                        assert details["total_tokens"] == expected_interaction["total_tokens"], (
                            f"Agent '{agent_name}' LLM interaction {i+1} total_tokens mismatch"
                        )
                
                elif interaction_type == "mcp":
                    # Verify MCP interaction details
                    if "server_name" in expected_interaction:
                        assert details.get("server_name") == expected_interaction["server_name"], (
                            f"Agent '{agent_name}' MCP interaction {i+1} server_name mismatch"
                        )
                    if "tool_name" in expected_interaction:
                        assert details.get("tool_name") == expected_interaction["tool_name"], (
                            f"Agent '{agent_name}' MCP interaction {i+1} tool_name mismatch"
                        )
            
            print(f"      ✅ Agent '{agent_name}' verified ({len(interactions)} interactions)")
        
        print(f"    ✅ Parallel stage '{stage_name}' verified")

    def _verify_single_stage_interactions(self, stage, expected_stage_spec):
        """Verify interactions for a single (non-parallel) stage."""
        stage_name = stage["stage_name"]
        print(f"  🔍 Verifying single stage '{stage_name}' interactions...")
        
        # Verify stage type
        assert stage["parallel_type"] == "single", (
            f"Stage '{stage_name}' should be single type, got {stage['parallel_type']}"
        )
        
        # Get interactions
        interactions = stage.get("interactions", [])
        expected_interactions = expected_stage_spec["interactions"]
        
        assert len(interactions) == len(expected_interactions), (
            f"Stage '{stage_name}' interaction count mismatch: "
            f"expected {len(expected_interactions)}, got {len(interactions)}"
        )
        
        # Get expected conversation for command stage
        expected_conversation = EXPECTED_REGULAR_AFTER_PARALLEL_CONVERSATION
        
        # Verify each interaction
        for i, expected_interaction in enumerate(expected_interactions):
            actual_interaction = interactions[i]
            interaction_type = expected_interaction["type"]
            
            assert actual_interaction["type"] == interaction_type, (
                f"Stage '{stage_name}' interaction {i+1} type mismatch"
            )
            
            details = actual_interaction["details"]
            assert details["success"] == expected_interaction["success"], (
                f"Stage '{stage_name}' interaction {i+1} success mismatch"
            )
            
            if interaction_type == "llm":
                # Verify conversation content
                actual_conversation = details["conversation"]
                actual_messages = actual_conversation["messages"]
                
                if "conversation_index" in expected_interaction:
                    conversation_index = expected_interaction["conversation_index"]
                    assert_conversation_messages(
                        expected_conversation, actual_messages, conversation_index
                    )
                
                # Verify token usage
                if "input_tokens" in expected_interaction:
                    assert details["input_tokens"] == expected_interaction["input_tokens"], (
                        f"Stage '{stage_name}' LLM interaction {i+1} input_tokens mismatch"
                    )
                    assert details["output_tokens"] == expected_interaction["output_tokens"], (
                        f"Stage '{stage_name}' LLM interaction {i+1} output_tokens mismatch"
                    )
                    assert details["total_tokens"] == expected_interaction["total_tokens"], (
                        f"Stage '{stage_name}' LLM interaction {i+1} total_tokens mismatch"
                    )
        
        print(f"    ✅ Single stage '{stage_name}' verified ({len(interactions)} interactions)")

    def _verify_complete_interaction_flow(self, stages):
        """Verify complete interaction flow for all stages."""
        print("  🔍 Verifying complete interaction flow...")
        
        for stage in stages:
            stage_name = stage["stage_name"]
            expected_stage_spec = EXPECTED_PARALLEL_REGULAR_STAGES.get(stage_name)
            
            assert expected_stage_spec is not None, (
                f"No expected spec found for stage '{stage_name}'"
            )
            
            if expected_stage_spec["type"] == "parallel":
                self._verify_parallel_stage_interactions(stage, expected_stage_spec)
            else:
                self._verify_single_stage_interactions(stage, expected_stage_spec)
        
        print("    ✅ Complete interaction flow verified")

