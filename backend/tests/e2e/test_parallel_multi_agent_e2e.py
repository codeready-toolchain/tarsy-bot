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
from .expected_parallel_conversations import (
    EXPECTED_PARALLEL_AGENT_1_CONVERSATION,
    EXPECTED_PARALLEL_AGENT_2_CONVERSATION,
    EXPECTED_SYNTHESIS_CONVERSATION,
    EXPECTED_MULTI_AGENT_STAGES,
    EXPECTED_PARALLEL_CHAT_MESSAGE_1_CONVERSATION,
    EXPECTED_PARALLEL_CHAT_MESSAGE_2_CONVERSATION,
    EXPECTED_PARALLEL_CHAT_INTERACTIONS,
)
from .parallel_test_base import ParallelTestBase

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.e2e
class TestParallelMultiAgentE2E(ParallelTestBase):
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

        # ============================================================================
        # NATIVE THINKING MOCK (for KubernetesAgent using Gemini)
        # ============================================================================
        # Gemini SDK responses for native thinking (function calling)
        gemini_response_map = {
            1: {  # First call - tool call with thinking
                "text_content": "",  # Empty for tool calls
                "thinking_content": "I should check the pod status in test-namespace to understand the issue.",
                "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "pods", "namespace": "test-namespace"}}],
                "input_tokens": 245,
                "output_tokens": 85,
                "total_tokens": 330
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
        # LANGCHAIN MOCK (for LogAgent using ReAct + for SynthesisAgent)
        # ============================================================================
        # Agent-specific interaction counters for LangChain-based agents
        agent_counters = {
            "LogAgent": 0,
            "SynthesisAgent": 0,
            "ChatAgent": 0
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
            "SynthesisAgent": [
                {  # Interaction 1 - Synthesis final answer  
                    "response_content": """Final Answer: **Synthesis of Parallel Investigations**

Both investigations provide complementary evidence. The Kubernetes agent identified the symptom (CrashLoopBackOff), while the log agent uncovered the root cause (database connection timeout).

**Root Cause:** Pod-1 in test-namespace is crashing due to inability to connect to database at db.example.com:5432, resulting in repeated restart attempts (CrashLoopBackOff).

**Recommended Actions:**
1. Verify database service is running and accessible
2. Check network policies and firewall rules for connectivity to db.example.com:5432
3. Validate database credentials in pod configuration
4. Review database connection timeout settings in application config

**Priority:** High - Application is currently non-functional""",
                    "input_tokens": 420, "output_tokens": 180, "total_tokens": 600
                }
            ],
            "ChatAgent": [
                {  # Chat Message 1 - Database service check
                    "response_content": """Thought: The user wants to verify database service status. I'll check the service in test-namespace.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "service", "name": "database", "namespace": "test-namespace"}""",
                    "input_tokens": 210, "output_tokens": 65, "total_tokens": 275
                },
                {  # Chat Message 1 - Final answer
                    "response_content": """Final Answer: Yes, the database service is running in test-namespace with ClusterIP 10.96.0.100. The service endpoint exists, so the issue is likely with the actual database pod or external database connectivity rather than the Kubernetes service configuration.""",
                    "input_tokens": 190, "output_tokens": 80, "total_tokens": 270
                },
                {  # Chat Message 2 - Database pod check
                    "response_content": """Thought: The user wants to check the database pod status. Let me get pod information.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "label_selector": "app=database", "namespace": "test-namespace"}""",
                    "input_tokens": 220, "output_tokens": 70, "total_tokens": 290
                },
                {  # Chat Message 2 - Final answer
                    "response_content": """Final Answer: The database pod (database-0) is running and ready (1/1) in test-namespace. Since both the service and pod are healthy, the issue is that pod-1 is trying to connect to the external address db.example.com:5432 instead of using the internal Kubernetes service. The application configuration likely needs to be updated to use the service name 'database' or 'database.test-namespace.svc.cluster.local' instead of the external address.""",
                    "input_tokens": 200, "output_tokens": 90, "total_tokens": 290
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
                # Note: KubernetesAgent uses Gemini SDK (not LangChain), so we only identify LogAgent, SynthesisAgent, and ChatAgent here
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
                            elif "Incident Commander synthesizing" in content:
                                agent_name = "SynthesisAgent"
                            elif "Chat Assistant Instructions" in content:
                                agent_name = "ChatAgent"
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
        
        # Create MCP mock for kubernetes server (shared by both agents)
        mock_k8s_session = AsyncMock()
        
        async def mock_k8s_call_tool(tool_name, parameters):
            mock_result = Mock()
            mock_content = Mock()
            # Check for chat-specific queries
            params_str = str(parameters)
            if "service" in params_str or "database" in params_str and "pods" not in params_str:
                # Chat message 1 - database service check
                mock_content.text = '{"result": "Service database is running with ClusterIP 10.96.0.100"}'
            elif "app=database" in params_str or ("pods" in params_str and "database" in params_str and "label_selector" in params_str):
                # Chat message 2 - database pod check
                mock_content.text = '{"result": "Pod database-0 is in Running state, ready 1/1"}'
            elif "pods" in params_str:
                # Original investigation - pod status
                mock_content.text = '{"result": "Pod pod-1 is in CrashLoopBackOff state"}'
            elif "logs" in tool_name.lower() or "log" in params_str.lower():
                # Original investigation - logs
                mock_content.text = '{"logs": "Error: Failed to connect to database at db.example.com:5432 - connection timeout"}'
            else:
                mock_content.text = '{"result": "Mock k8s response"}'
            mock_result.content = [mock_content]
            return mock_result
        
        async def mock_k8s_list_tools():
            # Return tools that both agents can use
            mock_tools = [
                Tool(
                name="kubectl_get",
                description="Get Kubernetes resources",
                inputSchema={"type": "object", "properties": {}}
                ),
                Tool(
                name="get_logs",
                    description="Get pod logs",
                inputSchema={"type": "object", "properties": {}}
            )
            ]
            mock_result = Mock()
            mock_result.tools = mock_tools
            return mock_result
        
        mock_k8s_session.call_tool.side_effect = mock_k8s_call_tool
        mock_k8s_session.list_tools.side_effect = mock_k8s_list_tools
        
        mock_sessions = {
            "kubernetes-server": mock_k8s_session
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
                        self._verify_session_metadata(detail_data, "multi-agent-parallel-chain")
                        
                        # Get stages
                        stages = detail_data.get("stages", [])
                        
                        # Comprehensive verification
                        print("🔍 Step 4: Comprehensive result verification...")
                        self._verify_stage_structure(stages, EXPECTED_MULTI_AGENT_STAGES)
                        
                        # Create conversation map
                        conversation_map = {
                            "investigation": {
                                "KubernetesAgent": EXPECTED_PARALLEL_AGENT_1_CONVERSATION,
                                "LogAgent": EXPECTED_PARALLEL_AGENT_2_CONVERSATION
                            },
                            "synthesis": EXPECTED_SYNTHESIS_CONVERSATION
                        }
                        
                        self._verify_complete_interaction_flow(stages, EXPECTED_MULTI_AGENT_STAGES, conversation_map)
                        
                        print("✅ Multi-agent parallel test passed!")
                        
                        # Test chat functionality
                        print("🔍 Step 5: Testing chat functionality...")
                        await self._test_chat_functionality(test_client, session_id)
                        print("✅ Chat functionality test passed!")
                        
                        return detail_data

    async def _test_chat_functionality(self, test_client, session_id: str):
        """Test chat functionality after parallel execution."""
        
        # Step 0: Check chat availability endpoint
        logger.info("Testing chat availability check...")
        
        availability_response = test_client.get(
            f"/api/v1/sessions/{session_id}/chat-available"
        )
        
        assert availability_response.status_code == 200, (
            f"Chat availability check failed with status {availability_response.status_code}: "
            f"{availability_response.text}"
        )
        
        availability_data = availability_response.json()
        assert availability_data.get("available") is True, (
            f"Chat should be available for completed session, but got: {availability_data}"
        )
        assert availability_data.get("chat_id") is None, (
            "Chat ID should be None before chat is created"
        )
        
        logger.info("Chat availability verified (available=True, no existing chat)")
        
        # Step 1: Create chat for the session
        logger.info("Testing chat creation...")
        
        create_chat_response = test_client.post(
            f"/api/v1/sessions/{session_id}/chat",
            headers={"X-Forwarded-User": "test-user@example.com"}
        )
        
        assert create_chat_response.status_code == 200, (
            f"Chat creation failed with status {create_chat_response.status_code}: "
            f"{create_chat_response.text}"
        )
        
        chat_data = create_chat_response.json()
        chat_id = chat_data.get("chat_id")
        
        assert chat_id is not None, "Chat ID missing from creation response"
        assert chat_data.get("session_id") == session_id, "Chat session_id mismatch"
        assert chat_data.get("created_by") == "test-user@example.com", (
            f"Chat created_by mismatch: expected 'test-user@example.com', "
            f"got '{chat_data.get('created_by')}'"
        )
        
        logger.info("Chat created successfully: %s", chat_id)
        
        # Track verified chat stages to avoid re-checking them
        verified_chat_stage_ids = set()
        
        # Step 2: Send first chat message and verify response
        logger.info("Sending first chat message...")
        
        message_1_stage = await self._send_and_wait_for_chat_message(
            test_client=test_client,
            session_id=session_id,
            chat_id=chat_id,
            content="Can you check if the database service is running?",
            message_label="Message 1",
            verified_stage_ids=verified_chat_stage_ids
        )
        
        logger.info("Verifying first chat response...")
        await self._verify_chat_response(
            chat_stage=message_1_stage,
            message_key='message_1',
            expected_conversation=EXPECTED_PARALLEL_CHAT_MESSAGE_1_CONVERSATION
        )
        verified_chat_stage_ids.add(message_1_stage.get("stage_id"))
        logger.info("First chat response verified")
        
        # Step 3: Send second chat message (follow-up) and verify response
        logger.info("Sending second chat message (follow-up)...")
        
        message_2_stage = await self._send_and_wait_for_chat_message(
            test_client=test_client,
            session_id=session_id,
            chat_id=chat_id,
            content="What about the database pod itself?",
            message_label="Message 2",
            verified_stage_ids=verified_chat_stage_ids
        )
        
        logger.info("Verifying second chat response...")
        await self._verify_chat_response(
            chat_stage=message_2_stage,
            message_key='message_2',
            expected_conversation=EXPECTED_PARALLEL_CHAT_MESSAGE_2_CONVERSATION
        )
        verified_chat_stage_ids.add(message_2_stage.get("stage_id"))
        logger.info("Second chat response verified")
        
        logger.info("Chat functionality test completed (2 messages)")

    async def _send_and_wait_for_chat_message(
        self,
        test_client,
        session_id: str,
        chat_id: str,
        content: str,
        message_label: str = "Message",
        verified_stage_ids: set = None
    ):
        """
        Send a chat message and wait for the response stage to complete.
        
        Args:
            verified_stage_ids: Set of stage IDs that have already been verified
                               to avoid matching them again
        
        Returns:
            The completed chat stage for verification
        """
        if verified_stage_ids is None:
            verified_stage_ids = set()
        
        # Get current chat stage count before sending message
        detail_data = await E2ETestUtils.get_session_details_async(test_client, session_id)
        stages_before = [s for s in detail_data.get("stages", []) 
                        if s.get("stage_id", "").startswith("chat-response")]
        num_stages_before = len(stages_before)
        
        # Send the message (author comes from auth header, not JSON body)
        send_message_response = test_client.post(
            f"/api/v1/chats/{chat_id}/messages",
            json={"content": content},
            headers={"X-Forwarded-User": "test-user@example.com"}
        )
        
        assert send_message_response.status_code == 200, (
            f"{message_label} failed with status {send_message_response.status_code}: "
            f"{send_message_response.text}"
        )
        
        message_data = send_message_response.json()
        message_id = message_data.get("message_id")
        
        assert message_id is not None, f"{message_label} ID missing from response"

        logger.info("%s sent: %s", message_label, message_id)

        # Wait for a NEW chat stage to appear and complete
        logger.info("Waiting for %s response...", message_label.lower())
        
        max_wait = 15  # seconds (increased for chat processing)
        poll_interval = 0.5  # seconds
        
        chat_stage = None
        for i in range(int(max_wait / poll_interval)):
            # Get session details to check chat execution
            detail_data = await E2ETestUtils.get_session_details_async(test_client, session_id)
            stages = detail_data.get("stages", [])
            
            # Look for NEW chat stages (not already verified)
            # Search from the end since newer stages are added last
            for stage in reversed(stages):
                stage_id = stage.get("stage_id", "")
                if (stage_id.startswith("chat-response") and
                    stage_id not in verified_stage_ids and
                    stage.get("chat_id") == chat_id):
                    chat_stage = stage
                    break
            
            if chat_stage:
                if chat_stage.get("status") == "completed":
                    logger.info("%s response completed in %.1fs", message_label, (i+1) * poll_interval)
                    break
                # If found but not completed, continue waiting
            
            await asyncio.sleep(poll_interval)
        else:
            # Provide more debug info on timeout
            detail_data = await E2ETestUtils.get_session_details_async(test_client, session_id)
            stages = detail_data.get("stages", [])
            chat_stages = [s for s in stages if s.get("stage_id", "").startswith("chat-response")]
            new_stages = [s for s in chat_stages if s.get("stage_id") not in verified_stage_ids]
            debug_info = []
            for cs in new_stages:
                debug_info.append(
                    f"stage_id={cs.get('stage_id')}, "
                    f"chat_id={cs.get('chat_id')}, "
                    f"status={cs.get('status')}"
                )
            raise AssertionError(
                f"{message_label} response did not complete within {max_wait}s. "
                f"Started with {num_stages_before} stages, now have {len(chat_stages)} total, "
                f"{len(new_stages)} new (unverified) stages: {debug_info}"
            )
        
        return chat_stage

    async def _verify_chat_response(
        self,
        chat_stage,
        message_key: str,
        expected_conversation: dict
    ):
        """
        Verify the structure of a chat response using the same pattern as stage verification.
        
        Args:
            chat_stage: The chat stage execution data from the API
            message_key: Key to look up expected interactions (e.g., 'message_1', 'message_2')
            expected_conversation: Expected conversation structure for this message
        """
        from .e2e_utils import assert_conversation_messages
        
        # Verify basic stage structure
        assert chat_stage is not None, "Chat stage not found"
        assert chat_stage.get("agent") == "ChatAgent", (
            f"Expected ChatAgent, got {chat_stage.get('agent')}"
        )
        assert chat_stage.get("status") == "completed", (
            f"Chat stage not completed: {chat_stage.get('status')}"
        )
        
        # Verify chat-specific fields
        assert chat_stage.get("chat_id") is not None, "Chat ID missing from stage"
        assert chat_stage.get("chat_user_message_id") is not None, (
            "Chat user message ID missing from stage"
        )
        
        # Verify embedded user message data
        chat_user_message = chat_stage.get("chat_user_message")
        assert chat_user_message is not None, (
            "Chat user message data missing from stage - should be embedded"
        )
        assert chat_user_message.get("message_id") is not None, "User message ID missing"
        assert chat_user_message.get("content") is not None, "User message content missing"
        assert chat_user_message.get("author") == "test-user@example.com", (
            f"User message author mismatch: expected 'test-user@example.com', "
            f"got '{chat_user_message.get('author')}'"
        )
        assert chat_user_message.get("created_at_us") > 0, "User message timestamp invalid"
        
        # Verify the content matches what we expect for each message
        expected_content_map = {
            'message_1': "Can you check if the database service is running?",
            'message_2': "What about the database pod itself?"
        }
        expected_content = expected_content_map.get(message_key)
        if expected_content:
            assert chat_user_message.get("content") == expected_content, (
                f"User message content mismatch for {message_key}: "
                f"expected '{expected_content}', got '{chat_user_message.get('content')}'"
            )
        
        # Get expected interactions for this message
        expected_chat = EXPECTED_PARALLEL_CHAT_INTERACTIONS[message_key]
        llm_interactions = chat_stage.get("llm_interactions", [])
        mcp_interactions = chat_stage.get("mcp_communications", [])
        
        # Verify interaction counts
        assert len(llm_interactions) == expected_chat["llm_count"], (
            f"Chat {message_key}: Expected {expected_chat['llm_count']} LLM interactions, "
            f"got {len(llm_interactions)}"
        )
        assert len(mcp_interactions) == expected_chat["mcp_count"], (
            f"Chat {message_key}: Expected {expected_chat['mcp_count']} MCP interactions, "
            f"got {len(mcp_interactions)}"
        )
        
        # Verify complete interaction flow in chronological order
        chronological_interactions = chat_stage.get("chronological_interactions", [])
        assert len(chronological_interactions) == len(expected_chat["interactions"]), (
            f"Chat {message_key} chronological interaction count mismatch: "
            f"expected {len(expected_chat['interactions'])}, got {len(chronological_interactions)}"
        )
        
        # Verify each interaction
        for i, expected_interaction in enumerate(expected_chat["interactions"]):
            actual_interaction = chronological_interactions[i]
            interaction_type = expected_interaction["type"]
            
            # Verify the type matches
            assert actual_interaction["type"] == interaction_type, (
                f"Chat {message_key} interaction {i+1} type mismatch: "
                f"expected {interaction_type}, got {actual_interaction['type']}"
            )
            
            details = actual_interaction["details"]
            assert details["success"] == expected_interaction["success"], (
                f"Chat {message_key} interaction {i+1} success mismatch"
            )
            
            if interaction_type == "llm":
                # Skip conversation content validation for chat (investigation history makes it complex)
                # Just verify structure
                actual_conversation = details.get("conversation")
                assert actual_conversation is not None, (
                    f"Chat {message_key} LLM interaction {i+1} missing conversation"
                )
                actual_messages = actual_conversation.get("messages", [])
                assert len(actual_messages) > 0, (
                    f"Chat {message_key} LLM interaction {i+1} has no messages"
                )
                
                # Verify token usage
                if "input_tokens" in expected_interaction:
                    assert details.get("input_tokens") == expected_interaction["input_tokens"], (
                        f"Chat {message_key} LLM interaction {i+1} input_tokens mismatch"
                    )
                    assert details.get("output_tokens") == expected_interaction["output_tokens"], (
                        f"Chat {message_key} LLM interaction {i+1} output_tokens mismatch"
                    )
                    assert details.get("total_tokens") == expected_interaction["total_tokens"], (
                        f"Chat {message_key} LLM interaction {i+1} total_tokens mismatch"
                    )
            
            elif interaction_type == "mcp":
                # Verify MCP interaction details
                if "server_name" in expected_interaction:
                    assert details.get("server_name") == expected_interaction["server_name"], (
                        f"Chat {message_key} MCP interaction {i+1} server_name mismatch"
                    )
                if "tool_name" in expected_interaction:
                    assert details.get("tool_name") == expected_interaction["tool_name"], (
                        f"Chat {message_key} MCP interaction {i+1} tool_name mismatch"
                    )

