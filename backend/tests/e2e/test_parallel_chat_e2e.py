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
from .e2e_utils import E2ETestUtils, assert_conversation_messages
from .expected_parallel_conversations import (
    EXPECTED_PARALLEL_AGENT_1_CONVERSATION,
    EXPECTED_PARALLEL_AGENT_2_CONVERSATION,
    EXPECTED_SYNTHESIS_CONVERSATION,
    EXPECTED_PARALLEL_CHAT_STAGES,
    EXPECTED_PARALLEL_CHAT_MESSAGE_1_CONVERSATION,
    EXPECTED_PARALLEL_CHAT_MESSAGE_2_CONVERSATION,
    EXPECTED_PARALLEL_CHAT_MESSAGE_1_INTERACTIONS,
    EXPECTED_PARALLEL_CHAT_MESSAGE_2_INTERACTIONS,
)
from .parallel_test_base import ParallelTestBase

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestParallelChatE2E(ParallelTestBase):
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
        # Token counts must match EXPECTED_PARALLEL_CHAT_STAGES and chat interaction specs
        # Agent1: 1-2, Agent2: 3-4, Synthesis: 5, Chat1: 6-7, Chat2: 8-9
        mock_response_map = {
            1: {  # Agent1 - Initial (LLM position 1)
                "response_content": """Thought: I should check the pod status in the test-namespace to understand any issues.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "namespace": "test-namespace"}""",
                "input_tokens": 245, "output_tokens": 85, "total_tokens": 330
            },
            2: {  # Agent1 - Final (LLM position 2)
                "response_content": """Final Answer: Investigation complete. Found pod-1 in CrashLoopBackOff state in test-namespace.""",
                "input_tokens": 180, "output_tokens": 65, "total_tokens": 245
            },
            3: {  # Agent2 - Initial (LLM position 1)
                "response_content": """Thought: I should analyze the application logs to find error patterns.
Action: log-server.get_logs
Action Input: {"namespace": "test-namespace", "pod": "pod-1"}""",
                "input_tokens": 200, "output_tokens": 75, "total_tokens": 275
            },
            4: {  # Agent2 - Final (LLM position 2)
                "response_content": """Final Answer: Log analysis reveals database connection timeout errors to db.example.com:5432.""",
                "input_tokens": 190, "output_tokens": 70, "total_tokens": 260
            },
            5: {  # Synthesis (LLM position 1)
                "response_content": """Final Answer: **Synthesis of Parallel Investigations**
Root cause: Pod-1 crashing due to database connection timeout. Recommended verifying database service and network connectivity.""",
                "input_tokens": 420, "output_tokens": 180, "total_tokens": 600
            },
            6: {  # Chat 1 - Tool call (LLM position 1)
                "response_content": """Thought: The user wants to verify database service status. I'll check the service in test-namespace.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "service", "name": "database", "namespace": "test-namespace"}""",
                "input_tokens": 210, "output_tokens": 75, "total_tokens": 285
            },
            7: {  # Chat 1 - Final answer (LLM position 2)
                "response_content": """Final Answer: Yes, the database service is running in test-namespace with ClusterIP 10.96.0.100. The service endpoint exists, so the issue is likely with the actual database pod or external database connectivity rather than the Kubernetes service configuration.""",
                "input_tokens": 195, "output_tokens": 68, "total_tokens": 263
            },
            8: {  # Chat 2 - Tool call (LLM position 1)
                "response_content": """Thought: The user wants to check the database pod status. Let me get pod information.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "label_selector": "app=database", "namespace": "test-namespace"}""",
                "input_tokens": 220, "output_tokens": 78, "total_tokens": 298
            },
            9: {  # Chat 2 - Final answer (LLM position 2)
                "response_content": """Final Answer: The database pod (database-0) is running and ready (1/1) in test-namespace. Since both the service and pod are healthy, the issue is that pod-1 is trying to connect to the external address db.example.com:5432 instead of using the internal Kubernetes service. The application configuration likely needs to be updated to use the service name 'database' or 'database.test-namespace.svc.cluster.local' instead of the external address.""",
                "input_tokens": 205, "output_tokens": 72, "total_tokens": 277
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
                        
                        # Get session details and verify parallel stages
                        detail_data = await E2ETestUtils.get_session_details_async(
                            test_client, session_id, max_retries=3, retry_delay=0.5
                        )
                        
                        # Verify session metadata
                        self._verify_session_metadata(detail_data, "multi-agent-parallel-chain")
                        
                        # Get stages
                        stages = detail_data.get("stages", [])
                        
                        # Comprehensive verification of parallel stages
                        print("🔍 Step 4: Verifying parallel stages...")
                        self._verify_stage_structure(stages, EXPECTED_PARALLEL_CHAT_STAGES)
                        
                        # Create conversation map
                        conversation_map = {
                            "investigation": {
                                "KubernetesAgent": EXPECTED_PARALLEL_AGENT_1_CONVERSATION,
                                "LogAgent": EXPECTED_PARALLEL_AGENT_2_CONVERSATION
                            },
                            "synthesis": EXPECTED_SYNTHESIS_CONVERSATION
                        }
                        
                        self._verify_complete_interaction_flow(stages, EXPECTED_PARALLEL_CHAT_STAGES, conversation_map)
                        
                        # Test chat functionality with comprehensive verification
                        print("🔍 Step 5: Testing chat functionality with verification...")
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
        
        # Get chat details for comprehensive verification
        chat_details_response = test_client.get(f"/api/v1/chats/{chat_id}")
        assert chat_details_response.status_code == 200
        chat_details = chat_details_response.json()
        
        # Verify chat has expected number of messages
        assert chat_details.get("message_count", 0) >= 4, "Expected at least 4 chat messages"
        
        # Get message details for verification
        messages = chat_details.get("messages", [])
        
        # Find assistant messages (skip user messages)
        assistant_messages = [msg for msg in messages if msg.get("role") == "assistant"]
        assert len(assistant_messages) >= 2, f"Expected at least 2 assistant messages, got {len(assistant_messages)}"
        
        # Verify first assistant message has interactions
        first_assistant_msg = assistant_messages[0]
        first_interactions = first_assistant_msg.get("interactions", [])
        self._verify_chat_message_interactions(first_interactions, EXPECTED_PARALLEL_CHAT_MESSAGE_1_INTERACTIONS, "Chat Message 1")
        
        # Verify second assistant message has interactions
        second_assistant_msg = assistant_messages[1]
        second_interactions = second_assistant_msg.get("interactions", [])
        self._verify_chat_message_interactions(second_interactions, EXPECTED_PARALLEL_CHAT_MESSAGE_2_INTERACTIONS, "Chat Message 2")
        
        print("✅ Chat functionality verified!")

    def _verify_chat_message_interactions(self, interactions, expected_interactions_spec, context_label):
        """Verify interactions for a chat message."""
        print(f"  🔍 Verifying {context_label} interactions...")
        
        expected_interactions = expected_interactions_spec["interactions"]
        
        assert len(interactions) == len(expected_interactions), (
            f"{context_label} interaction count mismatch: "
            f"expected {len(expected_interactions)}, got {len(interactions)}"
        )
        
        # Get expected conversation for chat messages
        if "1" in context_label:
            expected_conversation = EXPECTED_PARALLEL_CHAT_MESSAGE_1_CONVERSATION
        else:
            expected_conversation = EXPECTED_PARALLEL_CHAT_MESSAGE_2_CONVERSATION
        
        # Verify each interaction
        for i, expected_interaction in enumerate(expected_interactions):
            actual_interaction = interactions[i]
            interaction_type = expected_interaction["type"]
            
            assert actual_interaction["type"] == interaction_type, (
                f"{context_label} interaction {i+1} type mismatch"
            )
            
            details = actual_interaction["details"]
            assert details["success"] == expected_interaction["success"], (
                f"{context_label} interaction {i+1} success mismatch"
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
                        f"{context_label} LLM interaction {i+1} input_tokens mismatch"
                    )
                    assert details["output_tokens"] == expected_interaction["output_tokens"], (
                        f"{context_label} LLM interaction {i+1} output_tokens mismatch"
                    )
                    assert details["total_tokens"] == expected_interaction["total_tokens"], (
                        f"{context_label} LLM interaction {i+1} total_tokens mismatch"
                    )
            
            elif interaction_type == "mcp":
                # Verify MCP interaction details
                if "server_name" in expected_interaction:
                    assert details.get("server_name") == expected_interaction["server_name"], (
                        f"{context_label} MCP interaction {i+1} server_name mismatch"
                    )
                if "tool_name" in expected_interaction:
                    assert details.get("tool_name") == expected_interaction["tool_name"], (
                        f"{context_label} MCP interaction {i+1} tool_name mismatch"
                    )
        
        print(f"    ✅ {context_label} verified ({len(interactions)} interactions)")

