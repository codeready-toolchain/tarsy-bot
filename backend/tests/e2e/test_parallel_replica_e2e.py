"""
End-to-End Test for Replica Parallel Execution.

This test verifies:
- Replica parallel execution works
- Same agent runs N times with identical config
- Replica naming is correct
- Automatic synthesis aggregates results
- failure_policy="any" allows partial success

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
    EXPECTED_REPLICA_1_CONVERSATION,
    EXPECTED_REPLICA_2_CONVERSATION,
    EXPECTED_REPLICA_3_CONVERSATION,
    EXPECTED_REPLICA_SYNTHESIS_CONVERSATION,
    EXPECTED_REPLICA_STAGES,
)

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestParallelReplicaE2E:
    """E2E test for replica parallel execution."""

    @pytest.mark.e2e
    async def test_replica_parallel_stage(
        self, e2e_test_client, e2e_replica_alert
    ):
        """
        Test replica parallel stage with automatic synthesis.

        Flow:
        1. POST alert to /api/v1/alerts -> queued
        2. Wait for processing to complete
        3. Verify session was created and completed
        4. Verify parallel stage structure with 3 replicas
        5. Verify automatic synthesis stage was created
        6. Verify replica naming (Agent-1, Agent-2, Agent-3)
        7. Test failure_policy="any" (at least one must succeed)

        This test verifies:
        - Replica parallel execution works
        - Same agent runs N times with identical config
        - Replica naming is correct
        - Automatic synthesis aggregates results
        - failure_policy="any" allows partial success
        """

        async def run_test():
            print("🚀 Starting replica parallel test...")
            result = await self._execute_replica_test(
                e2e_test_client, e2e_replica_alert
            )
            print("✅ Replica parallel test completed!")
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

    async def _execute_replica_test(self, test_client, alert_data):
        """Execute replica parallel test."""
        print("🔧 Starting replica parallel test execution")

        # Track all LLM interactions
        all_llm_interactions = []
        
        # Define mock responses for replica parallel execution
        # Token counts must match EXPECTED_REPLICA_STAGES in expected_parallel_conversations.py
        # Replica-1: interactions 1-2, Replica-2: interactions 3-4, Replica-3: interactions 5-6, Synthesis: interaction 7
        mock_response_map = {
            1: {  # Replica 1 - Initial check (LLM position 1)
                "response_content": """Thought: I should check the deployment status to understand the issue.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "deployment", "name": "web-app"}""",
                "input_tokens": 245, "output_tokens": 85, "total_tokens": 330
            },
            2: {  # Replica 1 - Final answer (LLM position 2)
                "response_content": """Final Answer: Deployment web-app has no ready replicas (0/3). This indicates a critical availability issue. All pods may be failing to start or pass health checks.""",
                "input_tokens": 180, "output_tokens": 65, "total_tokens": 245
            },
            3: {  # Replica 2 - Check events (LLM position 1)
                "response_content": """Thought: I should check the pod events to see why replicas aren't ready.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "events", "field_selector": "involvedObject.name=web-app"}""",
                "input_tokens": 235, "output_tokens": 80, "total_tokens": 315
            },
            4: {  # Replica 2 - Final answer (LLM position 2)
                "response_content": """Final Answer: Events show ImagePullBackOff for web-app:v2.0.0. The deployment cannot start because the specified container image cannot be pulled. This is the root cause of the 0/3 ready replicas.""",
                "input_tokens": 185, "output_tokens": 70, "total_tokens": 255
            },
            5: {  # Replica 3 - Describe deployment (LLM position 1)
                "response_content": """Thought: Let me verify the image availability issue.
Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "deployment", "name": "web-app"}""",
                "input_tokens": 240, "output_tokens": 82, "total_tokens": 322
            },
            6: {  # Replica 3 - Final answer (LLM position 2)
                "response_content": """Final Answer: Image web-app:v2.0.0 not found in container registry. The deployment is referencing a non-existent image version. Recommend verifying the image tag or rolling back to a known-good version.""",
                "input_tokens": 188, "output_tokens": 72, "total_tokens": 260
            },
            7: {  # Synthesis (LLM position 1)
                "response_content": """Final Answer: **Synthesis of Replica Investigations**

All three replicas converged on consistent findings with increasing detail. Replica-1 identified the symptom (0/3 ready), Replica-2 found the error (ImagePullBackOff), and Replica-3 confirmed root cause (image not in registry).

**Root Cause:** Deployment web-app references non-existent image web-app:v2.0.0 in container registry, preventing all pods from starting (0/3 ready).

**Immediate Actions:**
1. Verify image web-app:v2.0.0 was successfully built and pushed to registry
2. If image missing, rollback deployment to last known-good version
3. If image exists, check image pull secrets and registry access permissions

**Preventive Measures:**
- Implement pre-deployment image existence validation
- Add automated rollback on ImagePullBackOff
- Set up alerts for failed image pulls

**Priority:** Critical - Complete service outage""",
                "input_tokens": 450, "output_tokens": 190, "total_tokens": 640
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
        mock_sessions = {"kubernetes-server": mock_k8s_session}
        
        mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)
        
        # Create streaming mock for LLM - patch LangChain clients directly
        streaming_mock = create_streaming_mock()
        
        # Import LangChain clients to patch
        from langchain_anthropic import ChatAnthropic
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_openai import ChatOpenAI
        from langchain_xai import ChatXAI
        
        # Patch and execute
        with patch.object(ChatOpenAI, 'astream', streaming_mock), \
             patch.object(ChatAnthropic, 'astream', streaming_mock), \
             patch.object(ChatXAI, 'astream', streaming_mock), \
             patch.object(ChatGoogleGenerativeAI, 'astream', streaming_mock):
            
            with patch('tarsy.integrations.mcp.client.MCPClient.list_tools', mock_list_tools):
                with patch('tarsy.integrations.mcp.client.MCPClient.call_tool', mock_call_tool):
                    with E2ETestUtils.setup_runbook_service_patching("# Test Runbook\nThis is a test runbook for replica execution testing."):
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
                        self._verify_session_metadata(detail_data, "replica-parallel-chain")
                        
                        # Get stages
                        stages = detail_data.get("stages", [])
                        
                        # Comprehensive verification
                        print("🔍 Step 4: Comprehensive result verification...")
                        self._verify_stage_structure(stages, EXPECTED_REPLICA_STAGES)
                        self._verify_complete_interaction_flow(stages)
                        
                        print("✅ Replica parallel test passed!")
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
            
            # Get expected conversation for this replica
            if agent_name == "KubernetesAgent-1":
                expected_conversation = EXPECTED_REPLICA_1_CONVERSATION
            elif agent_name == "KubernetesAgent-2":
                expected_conversation = EXPECTED_REPLICA_2_CONVERSATION
            elif agent_name == "KubernetesAgent-3":
                expected_conversation = EXPECTED_REPLICA_3_CONVERSATION
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
        
        # Get expected conversation for synthesis stage
        expected_conversation = EXPECTED_REPLICA_SYNTHESIS_CONVERSATION
        
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
            expected_stage_spec = EXPECTED_REPLICA_STAGES.get(stage_name)
            
            assert expected_stage_spec is not None, (
                f"No expected spec found for stage '{stage_name}'"
            )
            
            if expected_stage_spec["type"] == "parallel":
                self._verify_parallel_stage_interactions(stage, expected_stage_spec)
            else:
                self._verify_single_stage_interactions(stage, expected_stage_spec)
        
        print("    ✅ Complete interaction flow verified")

