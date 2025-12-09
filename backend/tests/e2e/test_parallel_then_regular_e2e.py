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

        async def run_test():
            print("🚀 Starting parallel + regular test...")
            result = await self._execute_parallel_regular_test(
                e2e_parallel_test_client, e2e_parallel_regular_alert
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
        
        # Create agent-aware streaming mock for LLM client
        def create_streaming_mock():
            """Create a mock astream function that identifies the agent and returns appropriate responses."""
            async def mock_astream(*args, **kwargs):
                # Identify which agent is calling by inspecting the conversation
                agent_name = "Unknown"
                
                # Extract messages from args
                # When patching instance methods, args[0] is 'self', args[1] is the messages
                messages = []
                if args and len(args) > 1:
                    messages = args[1] if isinstance(args[1], list) else []
                elif args and len(args) > 0 and isinstance(args[0], list):
                    # Fallback: if args[0] is a list, use it (shouldn't happen with patch.object)
                    messages = args[0]
                
                # Look for agent-specific instructions in the system message
                # Note: KubernetesAgent uses Gemini SDK (not LangChain), so we only identify LogAgent and CommandAgent here
                for msg in messages:
                        # Handle both dict and Message object formats
                        content = ""
                        msg_type = ""
                        
                        if isinstance(msg, dict):
                            content = msg.get("content", "")
                            msg_type = msg.get("role", "") or msg.get("type", "")
                        elif hasattr(msg, "content"):
                            content = msg.content if isinstance(msg.content, str) else str(msg.content)
                            msg_type = getattr(msg, "type", "") or msg.__class__.__name__.lower().replace("message", "")
                        
                        # Check if this is a system message  
                        if msg_type in ["system", "systemmessage"]:
                            if "log analysis specialist" in content:
                                agent_name = "LogAgent"
                            elif "command execution specialist" in content:
                                agent_name = "CommandAgent"
                            break
                
                # Get the next response for this agent
                if agent_name in agent_counters:
                    agent_interaction_num = agent_counters[agent_name]
                    agent_counters[agent_name] += 1
                
                    print(f"\n🔍 LLM REQUEST from {agent_name} (interaction #{agent_interaction_num + 1})")
                
                    # Get response for this agent's interaction
                    agent_response_list = agent_responses.get(agent_name, [])
                    if agent_interaction_num < len(agent_response_list):
                        response_data = agent_response_list[agent_interaction_num]
                    else:
                        response_data = {
                            "response_content": f"Default response for {agent_name}",
                            "input_tokens": 100,
                            "output_tokens": 50,
                            "total_tokens": 150
                        }
                else:
                    response_data = {
                    "response_content": "Default response",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150
                    }
                
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
        
        # Patch both Gemini SDK (for native thinking) and LangChain clients (for ReAct)
        # IMPORTANT: Patch where genai.Client is USED, not where it's defined
        with patch("tarsy.integrations.llm.gemini_client.genai.Client", gemini_mock_factory), \
             patch.object(ChatOpenAI, 'astream', streaming_mock), \
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
                        
                        # Create conversation map
                        conversation_map = {
                            "investigation": {
                                "KubernetesAgent": EXPECTED_PARALLEL_NO_SYNTHESIS_AGENT_1_CONVERSATION,
                                "LogAgent": EXPECTED_PARALLEL_NO_SYNTHESIS_AGENT_2_CONVERSATION
                            },
                            "command": EXPECTED_REGULAR_AFTER_PARALLEL_CONVERSATION
                        }
                        
                        self._verify_complete_interaction_flow(stages, EXPECTED_PARALLEL_REGULAR_STAGES, conversation_map)
                        
                        print("✅ Parallel + regular stage test passed!")
                        return detail_data

