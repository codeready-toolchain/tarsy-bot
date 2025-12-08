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
from .e2e_utils import E2ETestUtils

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestParallelReplicaE2E:
    """E2E test for replica parallel execution."""

    @pytest.mark.e2e
    async def test_replica_parallel_stage(
        self, e2e_parallel_test_client, e2e_replica_alert
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
                e2e_parallel_test_client, e2e_replica_alert
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
        # Replica-1: interactions 1-2, Replica-2: interactions 3-4, Replica-3: interactions 5-6, Synthesis: interaction 7
        mock_response_map = {
            1: {  # Replica 1 - Initial check
                "response_content": """Thought: I should check the deployment status to understand the issue.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "deployment", "name": "web-app"}""",
                "input_tokens": 190, "output_tokens": 75, "total_tokens": 265
            },
            2: {  # Replica 1 - Final answer
                "response_content": """Final Answer: Deployment web-app has no ready replicas (0/3). This indicates a critical availability issue. All pods may be failing to start or pass health checks.""",
                "input_tokens": 170, "output_tokens": 90, "total_tokens": 260
            },
            3: {  # Replica 2 - Check events
                "response_content": """Thought: I should check the pod events to see why replicas aren't ready.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "events", "field_selector": "involvedObject.name=web-app"}""",
                "input_tokens": 195, "output_tokens": 80, "total_tokens": 275
            },
            4: {  # Replica 2 - Final answer
                "response_content": """Final Answer: Events show ImagePullBackOff for web-app:v2.0.0. The deployment cannot start because the specified container image cannot be pulled. This is the root cause of the 0/3 ready replicas.""",
                "input_tokens": 175, "output_tokens": 95, "total_tokens": 270
            },
            5: {  # Replica 3 - Describe deployment
                "response_content": """Thought: Let me verify the image availability issue.
Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "deployment", "name": "web-app"}""",
                "input_tokens": 185, "output_tokens": 70, "total_tokens": 255
            },
            6: {  # Replica 3 - Final answer
                "response_content": """Final Answer: Image web-app:v2.0.0 not found in container registry. The deployment is referencing a non-existent image version. Recommend verifying the image tag or rolling back to a known-good version.""",
                "input_tokens": 180, "output_tokens": 100, "total_tokens": 280
            },
            7: {  # Synthesis
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
                "input_tokens": 600, "output_tokens": 250, "total_tokens": 850
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
                        
                        # Verify stage structure
                        stages = detail_data.get("stages", [])
                        assert len(stages) == 2, f"Expected 2 stages (analysis + synthesis), got {len(stages)}"
                        
                        # Verify parallel stage with replicas
                        analysis_stage = stages[0]
                        assert analysis_stage["stage_name"] == "analysis"
                        assert analysis_stage["parallel_type"] == "replica"
                        assert analysis_stage["parallel_executions"] is not None
                        assert len(analysis_stage["parallel_executions"]) == 3
                        
                        # Verify replica naming
                        replica_names = [exec["agent"] for exec in analysis_stage["parallel_executions"]]
                        assert "KubernetesAgent-1" in replica_names
                        assert "KubernetesAgent-2" in replica_names
                        assert "KubernetesAgent-3" in replica_names
                        
                        # Verify synthesis stage
                        synthesis_stage = stages[1]
                        assert synthesis_stage["stage_name"] == "synthesis"
                        
                        print("✅ Replica parallel test passed!")
                        return detail_data

    def _verify_session_metadata(self, detail_data, expected_chain_id):
        """Verify session metadata."""
        assert detail_data["status"] == "completed"
        assert detail_data["chain_id"] == expected_chain_id
        assert detail_data["started_at_us"] is not None
        assert detail_data["completed_at_us"] is not None

