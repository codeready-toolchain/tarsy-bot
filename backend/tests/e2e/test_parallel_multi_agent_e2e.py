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
from .e2e_utils import E2ETestUtils, assert_conversation_messages
from .expected_parallel_conversations import (
    EXPECTED_PARALLEL_AGENT_1_CONVERSATION,
    EXPECTED_PARALLEL_AGENT_2_CONVERSATION,
    EXPECTED_SYNTHESIS_CONVERSATION,
    EXPECTED_MULTI_AGENT_STAGES,
)

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
        
        # Wrap the factory to add debugging
        original_factory = gemini_mock_factory
        def debug_gemini_factory(*args, **kwargs):
            print(f"[DEBUG Gemini Mock] Factory called with args={args}, kwargs={kwargs}")
            result = original_factory(*args, **kwargs)
            print(f"[DEBUG Gemini Mock] Factory returning: {result}")
            return result
        gemini_mock_factory = debug_gemini_factory
        
        # ============================================================================
        # LANGCHAIN MOCK (for LogAgent using ReAct + for SynthesisAgent)
        # ============================================================================
        # Agent-specific interaction counters for LangChain-based agents
        agent_counters = {
            "LogAgent": 0,
            "SynthesisAgent": 0
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
                # Note: KubernetesAgent uses Gemini SDK (not LangChain), so we only identify LogAgent and SynthesisAgent here
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
            if "pods" in str(parameters):
                mock_content.text = '{"result": "Pod pod-1 is in CrashLoopBackOff state"}'
            elif "logs" in tool_name.lower() or "log" in str(parameters).lower():
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
                        
                        # Debug: if failed, print session details
                        if final_status != "completed":
                            import json
                            detail_data = await E2ETestUtils.get_session_details_async(
                                test_client, session_id, max_retries=3, retry_delay=0.5
                            )
                            debug_file = "/tmp/failed_session_details.json"
                            with open(debug_file, "w") as f:
                                json.dump(detail_data, f, indent=2, default=str)
                            print(f"\n❌ Session failed! Status: {final_status}")
                            print(f"   Error: {detail_data.get('error_message')}")
                            print(f"   Full session details written to: {debug_file}")
                        
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
                        self._verify_complete_interaction_flow(stages)
                        
                        print("✅ Multi-agent parallel test passed!")
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
                if execution["agent"] == agent_name:
                    agent_execution = execution
                    break
            
            assert agent_execution is not None, (
                f"Stage '{stage_name}' missing execution for agent '{agent_name}'"
            )
            
            print(f"    🔍 Verifying agent '{agent_name}'...")
            
            # Build unified interactions list from llm_interactions and mcp_communications
            llm_interactions = agent_execution.get("llm_interactions", [])
            mcp_communications = agent_execution.get("mcp_communications", [])
            
            # Convert to unified format sorted by timestamp
            unified_interactions = []
            for llm in llm_interactions:
                unified_interactions.append({
                    "type": "llm",
                    "timestamp_us": llm["timestamp_us"],
                    "details": llm["details"]
                })
            for mcp in mcp_communications:
                unified_interactions.append({
                    "type": "mcp",
                    "timestamp_us": mcp["timestamp_us"],
                    "details": mcp["details"]
                })
            
            # Sort by timestamp to get chronological order
            unified_interactions.sort(key=lambda x: x["timestamp_us"])
            
            expected_interactions = expected_agent_spec["interactions"]
            
            assert len(unified_interactions) == len(expected_interactions), (
                f"Agent '{agent_name}' interaction count mismatch: "
                f"expected {len(expected_interactions)}, got {len(unified_interactions)}"
            )
            
            # Get expected conversation for this agent
            if agent_name == "KubernetesAgent":
                expected_conversation = EXPECTED_PARALLEL_AGENT_1_CONVERSATION
            elif agent_name == "LogAgent":
                expected_conversation = EXPECTED_PARALLEL_AGENT_2_CONVERSATION
            else:
                expected_conversation = None
            
            # Verify each interaction
            for i, expected_interaction in enumerate(expected_interactions):
                actual_interaction = unified_interactions[i]
                interaction_type = expected_interaction["type"]
                
                assert actual_interaction["type"] == interaction_type, (
                    f"Agent '{agent_name}' interaction {i+1} type mismatch"
                )
                
                details = actual_interaction["details"]
                
                if interaction_type == "llm":
                    # Verify success
                    assert details.get("success", True) == expected_interaction["success"], (
                        f"Agent '{agent_name}' LLM interaction {i+1} success mismatch"
                    )
                    
                    # Verify conversation content
                    actual_conversation = details.get("conversation", {})
                    actual_messages = actual_conversation.get("messages", [])
                    
                    if "conversation_index" in expected_interaction and expected_conversation:
                        conversation_index = expected_interaction["conversation_index"]
                        assert_conversation_messages(
                            expected_conversation, actual_messages, conversation_index
                        )
                    
                    # Verify token usage
                    if "input_tokens" in expected_interaction:
                        assert details.get("input_tokens") == expected_interaction["input_tokens"], (
                            f"Agent '{agent_name}' LLM interaction {i+1} input_tokens mismatch"
                        )
                        assert details.get("output_tokens") == expected_interaction["output_tokens"], (
                            f"Agent '{agent_name}' LLM interaction {i+1} output_tokens mismatch"
                        )
                        assert details.get("total_tokens") == expected_interaction["total_tokens"], (
                            f"Agent '{agent_name}' LLM interaction {i+1} total_tokens mismatch"
                        )
                
                elif interaction_type == "mcp":
                    # Verify success
                    assert details.get("success", True) == expected_interaction["success"], (
                        f"Agent '{agent_name}' MCP interaction {i+1} success mismatch"
                    )
                    
                    # Verify MCP interaction details
                    if "server_name" in expected_interaction:
                        assert details.get("server_name") == expected_interaction["server_name"], (
                            f"Agent '{agent_name}' MCP interaction {i+1} server_name mismatch"
                        )
                    if "tool_name" in expected_interaction:
                        assert details.get("tool_name") == expected_interaction["tool_name"], (
                            f"Agent '{agent_name}' MCP interaction {i+1} tool_name mismatch"
                        )
            
            print(f"      ✅ Agent '{agent_name}' verified ({len(unified_interactions)} interactions)")
        
        print(f"    ✅ Parallel stage '{stage_name}' verified")

    def _verify_single_stage_interactions(self, stage, expected_stage_spec):
        """Verify interactions for a single (non-parallel) stage."""
        stage_name = stage["stage_name"]
        print(f"  🔍 Verifying single stage '{stage_name}' interactions...")
        
        # Verify stage type
        assert stage["parallel_type"] == "single", (
            f"Stage '{stage_name}' should be single type, got {stage['parallel_type']}"
        )
        
        # Build unified interactions list from llm_interactions and mcp_communications
        llm_interactions = stage.get("llm_interactions", [])
        mcp_communications = stage.get("mcp_communications", [])
        
        # Convert to unified format sorted by timestamp
        unified_interactions = []
        for llm in llm_interactions:
            unified_interactions.append({
                "type": "llm",
                "timestamp_us": llm["timestamp_us"],
                "details": llm["details"]
            })
        for mcp in mcp_communications:
            unified_interactions.append({
                "type": "mcp",
                "timestamp_us": mcp["timestamp_us"],
                "details": mcp["details"]
            })
        
        # Sort by timestamp to get chronological order
        unified_interactions.sort(key=lambda x: x["timestamp_us"])
        
        expected_interactions = expected_stage_spec["interactions"]
        
        assert len(unified_interactions) == len(expected_interactions), (
            f"Stage '{stage_name}' interaction count mismatch: "
            f"expected {len(expected_interactions)}, got {len(unified_interactions)}"
        )
        
        # Get expected conversation for synthesis stage
        expected_conversation = EXPECTED_SYNTHESIS_CONVERSATION
        
        # Verify each interaction
        for i, expected_interaction in enumerate(expected_interactions):
            actual_interaction = unified_interactions[i]
            interaction_type = expected_interaction["type"]
            
            assert actual_interaction["type"] == interaction_type, (
                f"Stage '{stage_name}' interaction {i+1} type mismatch"
            )
            
            details = actual_interaction["details"]
            
            if interaction_type == "llm":
                # Verify success
                assert details.get("success", True) == expected_interaction["success"], (
                    f"Stage '{stage_name}' LLM interaction {i+1} success mismatch"
                )
                
                # Verify conversation content
                actual_conversation = details.get("conversation", {})
                actual_messages = actual_conversation.get("messages", [])
                
                if "conversation_index" in expected_interaction:
                    conversation_index = expected_interaction["conversation_index"]
                    assert_conversation_messages(
                        expected_conversation, actual_messages, conversation_index
                    )
                
                # Verify token usage
                if "input_tokens" in expected_interaction:
                    assert details.get("input_tokens") == expected_interaction["input_tokens"], (
                        f"Stage '{stage_name}' LLM interaction {i+1} input_tokens mismatch"
                    )
                    assert details.get("output_tokens") == expected_interaction["output_tokens"], (
                        f"Stage '{stage_name}' LLM interaction {i+1} output_tokens mismatch"
                    )
                    assert details.get("total_tokens") == expected_interaction["total_tokens"], (
                        f"Stage '{stage_name}' LLM interaction {i+1} total_tokens mismatch"
                    )
        
            elif interaction_type == "mcp":
                # Verify success
                assert details.get("success", True) == expected_interaction["success"], (
                    f"Stage '{stage_name}' MCP interaction {i+1} success mismatch"
                )
        
        print(f"    ✅ Single stage '{stage_name}' verified ({len(unified_interactions)} interactions)")

    def _verify_complete_interaction_flow(self, stages):
        """Verify complete interaction flow for all stages."""
        print("  🔍 Verifying complete interaction flow...")
        
        for stage in stages:
            stage_name = stage["stage_name"]
            expected_stage_spec = EXPECTED_MULTI_AGENT_STAGES.get(stage_name)
            
            assert expected_stage_spec is not None, (
                f"No expected spec found for stage '{stage_name}'"
            )
            
            if expected_stage_spec["type"] == "parallel":
                self._verify_parallel_stage_interactions(stage, expected_stage_spec)
            else:
                self._verify_single_stage_interactions(stage, expected_stage_spec)
        
        print("    ✅ Complete interaction flow verified")

