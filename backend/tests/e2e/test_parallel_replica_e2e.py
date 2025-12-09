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
from typing import Any
from unittest.mock import patch

import pytest

from .conftest import create_mock_stream
from .e2e_utils import E2ETestUtils
from .expected_parallel_conversations import (
    EXPECTED_REPLICA_1_CONVERSATION,
    EXPECTED_REPLICA_2_CONVERSATION,
    EXPECTED_REPLICA_3_CONVERSATION,
    EXPECTED_REPLICA_SYNTHESIS_CONVERSATION,
    EXPECTED_REPLICA_STAGES,
)
from .parallel_test_base import ParallelTestBase

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestParallelReplicaE2E(ParallelTestBase):
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

        # ============================================================================
        # STAGE EXECUTION TRACKING for mapping stage_execution_id → agent_name
        # ============================================================================
        # We need to track which stage_execution_id belongs to which agent so the mock
        # can return the correct response based on the agent name
        import contextvars
        import threading
        
        # Shared mapping: stage_execution_id → agent_name
        stage_to_agent_map = {}
        map_lock = threading.Lock()
        
        # Context variable to track current stage_execution_id in the LLM call
        _current_stage_execution_id = contextvars.ContextVar('current_stage_execution_id', default=None)
        
        # ============================================================================
        # NATIVE THINKING MOCK (for KubernetesAgent replicas using Gemini)
        # ============================================================================
        # Gemini SDK responses for native thinking (function calling) - all replicas
        # Each replica uses UNIQUE tool parameters (with replica-id) to make them distinguishable
        gemini_response_map = {
            # Replica 1 - checks deployment with replica-id=1
            "replica-1-call-1": {
                "text_content": "",
                "thinking_content": "I should check the deployment status to understand the issue.",
                "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "deployment", "name": "web-app", "replica_id": "1"}}],
                "input_tokens": 240,
                "output_tokens": 85,
                "total_tokens": 325
            },
            "replica-1-call-2": {
                "text_content": "Deployment web-app has no ready replicas (0/3). This indicates a critical availability issue. All pods may be failing to start or pass health checks.",
                "thinking_content": "I have identified the deployment status issue.",
                "function_calls": None,
                "input_tokens": 180,
                "output_tokens": 65,
                "total_tokens": 245
            },
            # Replica 2 - checks events with replica-id=2
            "replica-2-call-1": {
                "text_content": "",
                "thinking_content": "I should check the pod events to see why replicas aren't ready.",
                "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "events", "field_selector": "involvedObject.name=web-app", "replica_id": "2"}}],
                "input_tokens": 240,
                "output_tokens": 80,
                "total_tokens": 320
            },
            "replica-2-call-2": {
                "text_content": "Events show ImagePullBackOff for web-app:v2.0.0. The deployment cannot start because the specified container image cannot be pulled. This is the root cause of the 0/3 ready replicas.",
                "thinking_content": "I have found the specific error causing the issue.",
                "function_calls": None,
                "input_tokens": 185,
                "output_tokens": 70,
                "total_tokens": 255
            },
            # Replica 3 - describes deployment with replica-id=3
            "replica-3-call-1": {
                "text_content": "",
                "thinking_content": "Let me verify the image availability issue.",
                "function_calls": [{"name": "kubernetes-server__kubectl_describe", "args": {"resource": "deployment", "name": "web-app", "replica_id": "3"}}],
                "input_tokens": 240,
                "output_tokens": 82,
                "total_tokens": 322
            },
            "replica-3-call-2": {
                "text_content": "Image web-app:v2.0.0 not found in container registry. The deployment is referencing a non-existent image version. Recommend verifying the image tag or rolling back to a known-good version.",
                "thinking_content": "I have confirmed the root cause is the missing image.",
                "function_calls": None,
                "input_tokens": 188,
                "output_tokens": 72,
                "total_tokens": 260
            }
        }
        
        # Create an agent-aware Gemini mock that uses stage_execution_id to identify agents
        from .conftest import create_native_thinking_response
        
        def create_agent_aware_gemini_mock(response_map: dict, stage_to_agent_map: dict, stage_id_contextvar):
            """Create an agent-aware Gemini mock that identifies replicas by their stage_execution_id."""
            # Track call counts per agent
            agent_call_counts = {}
            
            def response_generator(call_num: int, model: str, contents: list, config: Any):
                # Get current stage_execution_id from context
                stage_execution_id = stage_id_contextvar.get()
                
                # Look up agent name from stage_execution_id
                with map_lock:
                    agent_name = stage_to_agent_map.get(stage_execution_id, "unknown")
                
                # Track call count for this agent
                if agent_name not in agent_call_counts:
                    agent_call_counts[agent_name] = 0
                agent_call_counts[agent_name] += 1
                
                call_num_for_agent = agent_call_counts[agent_name]
                
                # Extract replica number from agent name (e.g., "KubernetesAgent-1" → 1)
                replica_num = 1
                if '-' in agent_name:
                    try:
                        replica_num = int(agent_name.split('-')[-1])
                    except ValueError:
                        pass
                
                # Build response key
                response_key = f"replica-{replica_num}-call-{call_num_for_agent}"
                
                response_data = response_map.get(response_key, {
                    "text_content": f"Fallback response for {response_key}",
                    "thinking_content": None,
                    "function_calls": None,
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150
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
            
            def client_factory(api_key: str = "test-api-key"):
                from .conftest import MockGeminiClient
                return MockGeminiClient(response_generator=response_generator)
            
            return client_factory
        
        gemini_mock_factory = create_agent_aware_gemini_mock(
            gemini_response_map, 
            stage_to_agent_map,
            _current_stage_execution_id
        )
        
        # ============================================================================
        # LANGCHAIN MOCK (for SynthesisAgent using ReAct)
        # ============================================================================
        # Synthesis agent responses
        synthesis_response = {
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
            "input_tokens": 450,
            "output_tokens": 190,
            "total_tokens": 640
        }
        
        # Create streaming mock for synthesis agent
        def create_streaming_mock():
            async def mock_astream(*args, **kwargs):
                print(f"\n🔍 LLM REQUEST for SynthesisAgent")
                
                content = synthesis_response["response_content"]
                usage_metadata = {
                    "input_tokens": synthesis_response["input_tokens"],
                    "output_tokens": synthesis_response["output_tokens"],
                    "total_tokens": synthesis_response["total_tokens"]
                }
                
                # Yield chunks from the mock stream - must be an async generator
                async for chunk in create_mock_stream(content, usage_metadata):
                    yield chunk
            
            return mock_astream
        
        # Create MCP session mock with replica-aware responses
        # We create a custom session that returns different results based on replica_id
        from unittest.mock import AsyncMock, Mock
        
        mock_k8s_session = AsyncMock()
        
        async def mock_session_call_tool(tool_name, parameters):
            """Mock MCP session call_tool with replica-aware responses."""
            # Extract replica_id to determine which response to return
            replica_id = parameters.get("replica_id", "1")
            
            if replica_id == "1":
                result_text = "Deployment web-app has 0/3 replicas ready"
            elif replica_id == "2":
                result_text = "Warning: ImagePullBackOff - Failed to pull image 'web-app:v2.0.0'"
            elif replica_id == "3":
                result_text = "Image: web-app:v2.0.0, Status: ErrImagePull - Image not found in registry"
            else:
                result_text = "Mock kubectl response"
            
            # Return in MCP SDK format (with .content attribute)
            mock_result = Mock()
            mock_content = Mock()
            mock_content.text = result_text
            mock_result.content = [mock_content]
            return mock_result
        
        async def mock_list_tools():
            return []  # Empty list for tool discovery
        
        mock_k8s_session.call_tool = mock_session_call_tool
        mock_k8s_session.list_tools = mock_list_tools
        
        # Create sessions dict and MCP client patches
        mock_sessions = {"kubernetes-server": mock_k8s_session}
        from .e2e_utils import E2ETestUtils
        mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)
        
        # Create streaming mock for LLM - patch LangChain clients directly
        streaming_mock = create_streaming_mock()
        
        # Import LangChain clients to patch
        from langchain_anthropic import ChatAnthropic
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_openai import ChatOpenAI
        from langchain_xai import ChatXAI
        
        # Patch llm_interaction_context to set the contextvar
        from tarsy.hooks.hook_context import llm_interaction_context as original_llm_context
        from contextlib import asynccontextmanager
        
        @asynccontextmanager
        async def patched_llm_context(session_id, request_data, stage_execution_id=None, native_tools_config=None):
            """Patched version that sets the contextvar for test access."""
            # Set the contextvar so the mock can access it
            token = _current_stage_execution_id.set(stage_execution_id)
            try:
                # Call original context manager
                async with original_llm_context(session_id, request_data, stage_execution_id, native_tools_config) as ctx:
                    yield ctx
            finally:
                # Reset contextvar
                _current_stage_execution_id.reset(token)
        
        # Patch AlertService._create_stage_execution to capture the mapping
        from tarsy.services.alert_service import AlertService
        original_create_stage = AlertService._create_stage_execution
        
        async def patched_create_stage(self, session_id, stage, stage_index, parent_stage_execution_id=None, parallel_index=None, parallel_type=None):
            """Patched version that captures stage_execution_id → agent_name mapping."""
            # Call original to get the execution_id
            execution_id = await original_create_stage(self, session_id, stage, stage_index, parent_stage_execution_id, parallel_index, parallel_type)
            
            # Capture the mapping for parallel stages (they have agent names with replica suffix)
            if hasattr(stage, 'agent'):
                agent_name = stage.agent
                with map_lock:
                    stage_to_agent_map[execution_id] = agent_name
            
            return execution_id
        
        # Patch both Gemini SDK (for native thinking replicas) and LangChain clients (for synthesis)
        with patch("tarsy.integrations.llm.gemini_client.genai.Client", gemini_mock_factory), \
             patch.object(ChatOpenAI, 'astream', streaming_mock), \
             patch.object(ChatAnthropic, 'astream', streaming_mock), \
             patch.object(ChatXAI, 'astream', streaming_mock), \
             patch.object(ChatGoogleGenerativeAI, 'astream', streaming_mock), \
             patch("tarsy.integrations.llm.gemini_client.llm_interaction_context", patched_llm_context), \
             patch.object(AlertService, '_create_stage_execution', patched_create_stage):
            
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
                        
                        # Get stages for verification
                        stages = detail_data.get("stages", [])
                        
                        # Comprehensive verification
                        print("🔍 Step 4: Comprehensive result verification...")
                        self._verify_stage_structure(stages, EXPECTED_REPLICA_STAGES)
                        
                        # Create conversation map
                        conversation_map = {
                            "analysis": {
                                "KubernetesAgent-1": EXPECTED_REPLICA_1_CONVERSATION,
                                "KubernetesAgent-2": EXPECTED_REPLICA_2_CONVERSATION,
                                "KubernetesAgent-3": EXPECTED_REPLICA_3_CONVERSATION
                            },
                            "synthesis": EXPECTED_REPLICA_SYNTHESIS_CONVERSATION
                        }
                        
                        self._verify_complete_interaction_flow(stages, EXPECTED_REPLICA_STAGES, conversation_map)
                        
                        print("✅ Replica parallel test passed!")
                        return detail_data

