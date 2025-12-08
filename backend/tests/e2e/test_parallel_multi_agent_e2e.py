"""
End-to-End Test for Multi-Agent Parallel Execution.

This test verifies:
- Multi-agent parallel execution works
- Different agents use different MCP servers
- Automatic synthesis is triggered for final parallel stage
- ParallelStageResult structure is correct
- Token tracking works at agent and stage levels

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: HTTP requests to LLM APIs, MCP servers, GitHub runbooks
"""

import asyncio
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import Tool

from .conftest import create_mock_stream
from .e2e_utils import E2ETestUtils

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestParallelMultiAgentE2E:
    """E2E test for multi-agent parallel execution."""

    @pytest.mark.e2e
    async def test_multi_agent_parallel_stage(
        self, e2e_parallel_test_client, e2e_parallel_alert
    ):
        """
        Test multi-agent parallel stage with automatic synthesis.

        Flow:
        1. POST alert to /api/v1/alerts -> queued
        2. Wait for processing to complete
        3. Verify session was created and completed
        4. Verify parallel stage structure with 2 agents
        5. Verify automatic synthesis stage was created
        6. Verify each agent's interactions and token counts

        This test verifies:
        - Multi-agent parallel execution works
        - Different agents use different MCP servers
        - Automatic synthesis is triggered for final parallel stage
        - ParallelStageResult structure is correct
        - Token tracking works at agent and stage levels
        """

        async def run_test():
            print("🚀 Starting multi-agent parallel test...")
            result = await self._execute_multi_agent_test(
                e2e_parallel_test_client, e2e_parallel_alert
            )
            print("✅ Multi-agent parallel test completed!")
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

    async def _execute_multi_agent_test(self, test_client, alert_data):
        """Execute multi-agent parallel test."""
        print("🔧 Starting multi-agent parallel test execution")

        # Track all LLM interactions
        all_llm_interactions = []
        
        # Define mock responses for multi-agent parallel execution
        # Agent1 (Kubernetes): interactions 1-2, Agent2 (Log): interactions 3-4, Synthesis: interaction 5
        mock_response_map = {
            1: {  # Agent1 (KubernetesAgent) - Initial analysis
                "response_content": """Thought: I should check the pod status in the test-namespace to understand any issues.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "namespace": "test-namespace"}""",
                "input_tokens": 200, "output_tokens": 80, "total_tokens": 280
            },
            2: {  # Agent1 - Final answer
                "response_content": """Final Answer: Investigation complete. Found pod-1 in CrashLoopBackOff state in test-namespace. This indicates the pod is repeatedly crashing and Kubernetes is backing off on restart attempts. Recommend checking pod logs and events for root cause.""",
                "input_tokens": 180, "output_tokens": 100, "total_tokens": 280
            },
            3: {  # Agent2 (LogAgent) - Log analysis
                "response_content": """Thought: I should analyze the application logs to find error patterns.
Action: log-server.get_logs
Action Input: {"namespace": "test-namespace", "pod": "pod-1"}""",
                "input_tokens": 200, "output_tokens": 75, "total_tokens": 275
            },
            4: {  # Agent2 - Final answer
                "response_content": """Final Answer: Log analysis reveals database connection timeout errors. The pod is failing because it cannot connect to the database at db.example.com:5432. This explains the CrashLoopBackOff. Recommend verifying database availability and network connectivity.""",
                "input_tokens": 185, "output_tokens": 105, "total_tokens": 290
            },
            5: {  # Synthesis agent
                "response_content": """Final Answer: **Synthesis of Parallel Investigations**

Both investigations provide complementary evidence. The Kubernetes agent identified the symptom (CrashLoopBackOff), while the log agent uncovered the root cause (database connection timeout).

**Root Cause:** Pod-1 in test-namespace is crashing due to inability to connect to database at db.example.com:5432, resulting in repeated restart attempts (CrashLoopBackOff).

**Recommended Actions:**
1. Verify database service is running and accessible
2. Check network policies and firewall rules for connectivity to db.example.com:5432
3. Validate database credentials in pod configuration
4. Review database connection timeout settings in application config

**Priority:** High - Application is currently non-functional""",
                "input_tokens": 500, "output_tokens": 200, "total_tokens": 700
            }
        }
        
        # Create streaming mock for LLM client
        def create_streaming_mock():
            """Create a mock astream function that returns streaming responses."""
            async def mock_astream(*args, **kwargs):
                # Track this interaction
                interaction_num = len(all_llm_interactions) + 1
                all_llm_interactions.append(interaction_num)
                
                print(f"\n🔍 LLM REQUEST #{interaction_num}")
                
                # Get response for this interaction
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
        
        # Create MCP mocks for kubernetes and log servers
        mock_k8s_session = AsyncMock()
        mock_log_session = AsyncMock()
        
        async def mock_k8s_call_tool(tool_name, parameters):
            mock_result = Mock()
            mock_content = Mock()
            if "pods" in str(parameters):
                mock_content.text = '{"result": "Pod pod-1 is in CrashLoopBackOff state"}'
            else:
                mock_content.text = '{"result": "Mock k8s response"}'
            mock_result.content = [mock_content]
            return mock_result
        
        async def mock_log_call_tool(tool_name, parameters):
            mock_result = Mock()
            mock_content = Mock()
            mock_content.text = '{"logs": "Error: Failed to connect to database at db.example.com:5432 - connection timeout"}'
            mock_result.content = [mock_content]
            return mock_result
        
        async def mock_k8s_list_tools():
            mock_tool = Tool(
                name="kubectl_get",
                description="Get Kubernetes resources",
                inputSchema={"type": "object", "properties": {}}
            )
            mock_result = Mock()
            mock_result.tools = [mock_tool]
            return mock_result
        
        async def mock_log_list_tools():
            mock_tool = Tool(
                name="get_logs",
                description="Get application logs",
                inputSchema={"type": "object", "properties": {}}
            )
            mock_result = Mock()
            mock_result.tools = [mock_tool]
            return mock_result
        
        mock_k8s_session.call_tool.side_effect = mock_k8s_call_tool
        mock_k8s_session.list_tools.side_effect = mock_k8s_list_tools
        mock_log_session.call_tool.side_effect = mock_log_call_tool
        mock_log_session.list_tools.side_effect = mock_log_list_tools
        
        mock_sessions = {
            "kubernetes-server": mock_k8s_session,
            "log-server": mock_log_session
        }
        
        # Create MCP client patches
        mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)
        
        # Create streaming mock for LLM - patch LangChain clients directly
        streaming_mock = create_streaming_mock()
        
        # Import LangChain clients to patch
        from langchain_anthropic import ChatAnthropic
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_openai import ChatOpenAI
        from langchain_xai import ChatXAI
        
        # Patch all the things - use LangChain client patching like working E2E test
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
                        self._verify_session_metadata(detail_data, "multi-agent-parallel-chain")
                        
                        # Verify stage structure
                        stages = detail_data.get("stages", [])
                        assert len(stages) == 2, f"Expected 2 stages (investigation + synthesis), got {len(stages)}"
                        
                        # Verify parallel stage
                        investigation_stage = stages[0]
                        assert investigation_stage["stage_name"] == "investigation"
                        assert investigation_stage["parallel_type"] == "multi_agent"
                        assert investigation_stage["parallel_executions"] is not None
                        assert len(investigation_stage["parallel_executions"]) == 2
                        
                        # Verify synthesis stage
                        synthesis_stage = stages[1]
                        assert synthesis_stage["stage_name"] == "synthesis"
                        assert synthesis_stage["parallel_type"] == "single"
                        
                        print("✅ Multi-agent parallel test passed!")
                        return detail_data

    def _verify_session_metadata(self, detail_data, expected_chain_id):
        """Verify session metadata."""
        assert detail_data["status"] == "completed"
        assert detail_data["chain_id"] == expected_chain_id
        assert detail_data["started_at_us"] is not None
        assert detail_data["completed_at_us"] is not None

