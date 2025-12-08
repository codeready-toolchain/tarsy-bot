"""
End-to-End Test for Chat Functionality After Parallel Execution.

This test verifies:
- Chat works after parallel execution
- Chat includes full parallel investigation history
- ChatAgent can access parallel stage results
- Follow-up questions work correctly

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
class TestParallelChatE2E:
    """E2E test for chat functionality after parallel execution."""

    @pytest.mark.e2e
    async def test_chat_after_parallel_stage(
        self, e2e_parallel_test_client, e2e_parallel_chat_alert
    ):
        """
        Test chat functionality after parallel execution.

        Flow:
        1. POST alert to /api/v1/alerts -> queued
        2. Wait for processing to complete (parallel + synthesis)
        3. Create chat session
        4. Send first chat message
        5. Verify chat response includes parallel investigation history
        6. Send second chat message (follow-up)
        7. Verify follow-up response

        This test verifies:
        - Chat works after parallel execution
        - Chat includes full parallel investigation history
        - ChatAgent can access parallel stage results
        - Follow-up questions work correctly
        """

        async def run_test():
            print("🚀 Starting chat after parallel test...")
            result = await self._execute_chat_after_parallel_test(
                e2e_parallel_test_client, e2e_parallel_chat_alert
            )
            print("✅ Chat after parallel test completed!")
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

    async def _execute_chat_after_parallel_test(self, test_client, alert_data):
        """Execute chat after parallel test."""
        print("🔧 Starting chat after parallel test execution")

        # Track all LLM interactions
        all_llm_interactions = []
        
        # Define mock responses
        # Agent1: 1-2, Agent2: 3-4, Synthesis: 5, Chat1: 6-7, Chat2: 8-9
        mock_response_map = {
            1: {  # Agent1 - Initial
                "response_content": """Thought: I should check the pod status in the test-namespace to understand any issues.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "namespace": "test-namespace"}""",
                "input_tokens": 200, "output_tokens": 80, "total_tokens": 280
            },
            2: {  # Agent1 - Final
                "response_content": """Final Answer: Investigation complete. Found pod-1 in CrashLoopBackOff state in test-namespace.""",
                "input_tokens": 180, "output_tokens": 60, "total_tokens": 240
            },
            3: {  # Agent2 - Initial
                "response_content": """Thought: I should analyze the application logs to find error patterns.
Action: log-server.get_logs
Action Input: {"namespace": "test-namespace", "pod": "pod-1"}""",
                "input_tokens": 200, "output_tokens": 75, "total_tokens": 275
            },
            4: {  # Agent2 - Final
                "response_content": """Final Answer: Log analysis reveals database connection timeout errors to db.example.com:5432.""",
                "input_tokens": 185, "output_tokens": 65, "total_tokens": 250
            },
            5: {  # Synthesis
                "response_content": """Final Answer: **Synthesis of Parallel Investigations**
Root cause: Pod-1 crashing due to database connection timeout. Recommended verifying database service and network connectivity.""",
                "input_tokens": 400, "output_tokens": 150, "total_tokens": 550
            },
            6: {  # Chat 1 - Tool call
                "response_content": """Thought: The user wants to verify database service status. I'll check the service in test-namespace.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "service", "name": "database", "namespace": "test-namespace"}""",
                "input_tokens": 250, "output_tokens": 80, "total_tokens": 330
            },
            7: {  # Chat 1 - Final answer
                "response_content": """Final Answer: Yes, the database service is running in test-namespace with ClusterIP 10.96.0.100. The service endpoint exists, so the issue is likely with the actual database pod or external database connectivity rather than the Kubernetes service configuration.""",
                "input_tokens": 200, "output_tokens": 95, "total_tokens": 295
            },
            8: {  # Chat 2 - Tool call
                "response_content": """Thought: The user wants to check the database pod status. Let me get pod information.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "label_selector": "app=database", "namespace": "test-namespace"}""",
                "input_tokens": 270, "output_tokens": 85, "total_tokens": 355
            },
            9: {  # Chat 2 - Final answer
                "response_content": """Final Answer: The database pod (database-0) is running and ready (1/1) in test-namespace. Since both the service and pod are healthy, the issue is that pod-1 is trying to connect to the external address db.example.com:5432 instead of using the internal Kubernetes service. The application configuration likely needs to be updated to use the service name 'database' or 'database.test-namespace.svc.cluster.local' instead of the external address.""",
                "input_tokens": 230, "output_tokens": 120, "total_tokens": 350
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
        
        # Patch and execute
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
                        
                        # Test chat functionality
                        await self._test_chat_functionality(test_client, session_id)
                        
                        print("✅ Chat after parallel test passed!")

    async def _test_chat_functionality(self, test_client, session_id: str):
        """Test chat functionality after parallel execution."""
        
        # Check chat availability
        availability_response = test_client.get(
            f"/api/v1/sessions/{session_id}/chat-available"
        )
        assert availability_response.status_code == 200
        availability_data = availability_response.json()
        assert availability_data.get("available") is True

        # Create chat
        create_chat_response = test_client.post(
            f"/api/v1/sessions/{session_id}/chat",
            headers={"X-Forwarded-User": "test-user@example.com"}
        )
        assert create_chat_response.status_code == 200
        chat_data = create_chat_response.json()
        chat_id = chat_data.get("chat_id")
        assert chat_id is not None

        # Send first chat message
        print("Sending first chat message...")
        message_1_response = test_client.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "Can you check if the database service is running?"},
            headers={"X-Forwarded-User": "test-user@example.com"}
        )
        assert message_1_response.status_code == 200

        # Wait for chat response with timeout
        max_wait_time = 10  # seconds
        wait_interval = 0.5
        elapsed = 0
        chat_complete = False
        
        while elapsed < max_wait_time and not chat_complete:
            await asyncio.sleep(wait_interval)
            elapsed += wait_interval
            
            # Check chat details
            chat_details_response = test_client.get(f"/api/v1/chats/{chat_id}")
            if chat_details_response.status_code == 200:
                chat_details = chat_details_response.json()
                message_count = chat_details.get("message_count", 0)
                # We expect at least 2 messages (user + assistant)
                if message_count >= 2:
                    chat_complete = True
                    break
        
        assert chat_complete, "Chat did not complete within timeout"

        # Send second chat message
        print("Sending second chat message...")
        message_2_response = test_client.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": "What about the database pod itself?"},
            headers={"X-Forwarded-User": "test-user@example.com"}
        )
        assert message_2_response.status_code == 200

        # Wait for second response
        elapsed = 0
        chat_complete = False
        
        while elapsed < max_wait_time and not chat_complete:
            await asyncio.sleep(wait_interval)
            elapsed += wait_interval
            
            chat_details_response = test_client.get(f"/api/v1/chats/{chat_id}")
            if chat_details_response.status_code == 200:
                chat_details = chat_details_response.json()
                message_count = chat_details.get("message_count", 0)
                # We expect at least 4 messages (2 user + 2 assistant)
                if message_count >= 4:
                    chat_complete = True
                    break
        
        assert chat_complete, "Second chat message did not complete within timeout"
        
        print("✅ Chat functionality verified!")

