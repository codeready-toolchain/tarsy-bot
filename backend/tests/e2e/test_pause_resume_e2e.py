"""
E2E Test for Pause/Resume Functionality.

This test verifies the complete pause/resume workflow:
1. Submit alert with max_iterations=2
2. Wait for session to pause (max iterations reached after 2 iterations)
3. Verify pause metadata and paused state
4. Increase max_iterations to 4 to allow completion after resume
5. Resume the paused session
6. Wait for session to complete (deterministic - iteration 3 has Final Answer)
7. Verify final state and audit trail

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: HTTP requests to LLM APIs, MCP servers, GitHub runbooks
- CONFIGURED: max_llm_mcp_iterations dynamically changed during test (2→4)
- DETERMINISTIC: Iteration 3 provides Final Answer → guaranteed completion
"""

import asyncio
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.config.builtin_config import BUILTIN_MCP_SERVERS
from tarsy.integrations.mcp.client import MCPClient
from mcp.types import Tool

from .e2e_utils import E2ETestUtils
from .conftest import create_mock_stream

logger = logging.getLogger(__name__)


# Expected conversation for resumed data-collection stage
# This proves conversation history was restored when resuming
EXPECTED_RESUMED_DATA_COLLECTION_CONVERSATION = {
    "messages": [
        # System message (same as original)
        {
            "role": "system",
            "content_contains": [
                "## General SRE Agent Instructions",
                "You are an expert Site Reliability Engineer",
                "## Agent-Specific Instructions",
                "You are a Kubernetes data collection specialist"
            ]
        },
        # Initial user question (restored from pause)
        # This proves resume_paused_session() restored COMPLETE context, not just messages
        {
            "role": "user",
            "content_contains": [
                # Question header
                "Question: Investigate this test-kubernetes alert",
                
                # Available tools - proves tool discovery context was restored
                "Available tools:",
                "kubernetes-server.kubectl_get",
                "kubernetes-server.kubectl_describe",
                
                # Alert metadata - proves alert context was restored
                "## Alert Details",
                "**Alert Type:** test-kubernetes",
                "**Severity:** warning",
                "**Environment:** production",
                
                # Alert data - proves detailed alert information was restored
                '"namespace": "test-namespace"',
                '"description": "Namespace stuck in Terminating state"',
                '"cluster": "test-cluster"',
                '"finalizers": "kubernetes.io/pv-protection"',
                
                # Runbook content - CRITICAL: proves runbook was included in restored context
                "## Runbook Content",
                "# Mock Runbook",
                "Test runbook content",
                
                # Previous stage data notice - proves stage chain context was restored
                "## Previous Stage Data",
                "No previous stage data is available",
                "This is the first stage of analysis",
                
                # Stage-specific instructions - proves stage context was restored
                "## Your Task: DATA-COLLECTION STAGE",
                "Use available tools to:",
                "Collect additional data relevant to this stage",
                "Analyze findings in the context of this specific stage",
                "Provide stage-specific insights and recommendations",
                
                # Final instruction
                "Begin!"
            ]
        },
        # Assistant iteration 1 (restored from pause)
        {
            "role": "assistant",
            "content_contains": [
                "Thought:",
                "namespace",
                "Action: kubernetes-server.kubectl_get",
                "Action Input:",
                "stuck-namespace"
            ]
        },
        # Observation 1 (restored from pause)
        # Proves tool execution results were preserved
        {
            "role": "user",
            "content_contains": [
                "Observation:",
                "kubernetes-server.kubectl_get",
                "stuck-namespace",
                "Terminating",
                "45m"
            ]
        },
        # Assistant iteration 2 (restored from pause)
        # Proves agent reasoning was preserved (references previous observation)
        {
            "role": "assistant",
            "content_contains": [
                "Thought:",
                "Terminating",  # References previous observation
                "Action: kubernetes-server.kubectl_describe",
                "Action Input:",
                "namespace"
            ]
        },
        # Observation 2 (restored from pause)
        # Proves second tool execution result was preserved
        {
            "role": "user",
            "content_contains": [
                "Observation:",
                "kubernetes-server.kubectl_describe",
                "stuck-namespace",
                "Terminating",
                "Finalizers",
                "kubernetes.io/pvc-protection"
            ]
        },
        # NEW: Iteration 3 (after resume) - completes the stage
        # This proves the agent can reference previous observations after resume
        {
            "role": "assistant",
            "content_contains": [
                "Thought:",
                "gathered enough information",  # Shows agent reviewed history
                "Final Answer:",
                "Data Collection",
                "Complete",
                "stuck-namespace",  # References previous observations
                "Terminating",  # References previous observations
                "Finalizers",  # References kubectl_describe result
                "blocking deletion"  # Shows understanding of the issue
            ]
        }
    ]
}

# Expected stage definitions for pause/resume flow
# These prove that resume continues from where we paused, not from scratch
EXPECTED_PAUSE_RESUME_STAGES = {
    'paused_data-collection': {
        'llm_count': 2,  # 2 LLM interactions before pause
        'mcp_count': 4,  # 2 tool_list (k8s + test-data) + 2 tool_call (only k8s provides tools)
        'expected_status': 'active',  # Paused stage shows as "active" in DB
        'interactions': [
            # Both servers are discovered (tool_list), but only kubernetes-server provides tools (we don't mock the second MCP server for simplisity)
            {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            {'type': 'mcp', 'position': 2, 'communication_type': 'tool_list', 'success': True, 'server_name': 'test-data-server'},
            {'type': 'llm', 'position': 1, 'success': True, 'input_tokens': 200, 'output_tokens': 80, 'total_tokens': 280},
            {'type': 'mcp', 'position': 3, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get'},
            {'type': 'llm', 'position': 2, 'success': True, 'input_tokens': 220, 'output_tokens': 90, 'total_tokens': 310},
            {'type': 'mcp', 'position': 4, 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_describe'},
        ]
    },
    'resumed_data-collection': {
        'llm_count': 1,  # 1 additional LLM interaction to complete
        'mcp_count': 2,  # 2 tool_list (k8s + test-data rediscovered, no new tool calls - just completes)
        'expected_status': 'completed',
        'expected_conversation': EXPECTED_RESUMED_DATA_COLLECTION_CONVERSATION,  # Verify conversation history was restored
        'interactions': [
            # Both servers rediscovered after resume (tool_list)
            {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            {'type': 'mcp', 'position': 2, 'communication_type': 'tool_list', 'success': True, 'server_name': 'test-data-server'},
            {'type': 'llm', 'position': 1, 'success': True, 'input_tokens': 240, 'output_tokens': 120, 'total_tokens': 360, 'interaction_type': 'final_analysis'},
        ]
    },
    'verification': {
        'llm_count': 1,
        'mcp_count': 1,
        'expected_status': 'completed',
        'interactions': [
            {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            {'type': 'llm', 'position': 1, 'success': True, 'input_tokens': 200, 'output_tokens': 100, 'total_tokens': 300, 'interaction_type': 'final_analysis'},
        ]
    },
    'analysis': {
        'llm_count': 1,
        'mcp_count': 0,
        'expected_status': 'completed',
        'interactions': [
            {'type': 'llm', 'position': 1, 'success': True, 'input_tokens': 250, 'output_tokens': 140, 'total_tokens': 390, 'interaction_type': 'final_analysis'},
        ]
    }
}


@pytest.mark.asyncio
@pytest.mark.e2e
class TestPauseResumeE2E:
    """
    E2E test for pause/resume functionality.

    Tests the complete system flow:
    1. HTTP POST to /api/v1/alerts endpoint with low max_iterations
    2. Real alert processing through AlertService
    3. Session pauses when max_iterations is reached
    4. HTTP POST to /api/v1/sessions/{session_id}/resume endpoint
    5. Session resumes and continues processing
    6. Verification of pause metadata and state transitions
    """

    def _validate_stage(self, actual_stage, stage_key):
        """
        Validate a stage's interactions match expected structure.
        
        This validates that:
        - The correct number of LLM/MCP interactions occurred
        - Token counts match (proving no extra work was done)
        - Interaction types and success status match
        - For resumed stages: proves conversation history was restored
        """
        stage_name = actual_stage["stage_name"]
        expected_stage = EXPECTED_PAUSE_RESUME_STAGES[stage_key]
        llm_interactions = actual_stage.get("llm_interactions", [])
        mcp_interactions = actual_stage.get("mcp_communications", [])
        
        print(f"\n🔍 Validating stage '{stage_name}' (key: {stage_key})")
        print(f"   Status: {actual_stage['status']} (expected: {expected_stage['expected_status']})")
        print(f"   LLM interactions: {len(llm_interactions)} (expected: {expected_stage['llm_count']})")
        print(f"   MCP interactions: {len(mcp_interactions)} (expected: {expected_stage['mcp_count']})")
        
        # Verify interaction counts
        assert len(llm_interactions) == expected_stage["llm_count"], \
            f"Stage '{stage_name}' ({stage_key}): Expected {expected_stage['llm_count']} LLM interactions, got {len(llm_interactions)}"
        assert len(mcp_interactions) == expected_stage["mcp_count"], \
            f"Stage '{stage_name}' ({stage_key}): Expected {expected_stage['mcp_count']} MCP interactions, got {len(mcp_interactions)}"
        
        # Verify status
        assert actual_stage['status'] == expected_stage['expected_status'], \
            f"Stage '{stage_name}' ({stage_key}): Expected status '{expected_stage['expected_status']}', got '{actual_stage['status']}'"
        
        # Verify chronological interaction flow
        chronological_interactions = actual_stage.get("chronological_interactions", [])
        assert len(chronological_interactions) == len(expected_stage["interactions"]), \
            f"Stage '{stage_name}' ({stage_key}) chronological interaction count mismatch: expected {len(expected_stage['interactions'])}, got {len(chronological_interactions)}"
        
        # Track token totals for the stage
        total_input_tokens = 0
        total_output_tokens = 0
        total_tokens = 0
        
        # Validate each interaction
        for i, expected_interaction in enumerate(expected_stage["interactions"]):
            actual_interaction = chronological_interactions[i]
            interaction_type = expected_interaction["type"]
            
            assert actual_interaction["type"] == interaction_type, \
                f"Stage '{stage_name}' ({stage_key}) interaction {i+1} type mismatch: expected {interaction_type}, got {actual_interaction['type']}"
            
            details = actual_interaction["details"]
            assert details["success"] == expected_interaction["success"], \
                f"Stage '{stage_name}' ({stage_key}) interaction {i+1} success mismatch"
            
            if interaction_type == "llm":
                # Verify token usage matches (proves no extra work was done)
                if "input_tokens" in expected_interaction:
                    assert details["input_tokens"] == expected_interaction["input_tokens"], \
                        f"Stage '{stage_name}' ({stage_key}) interaction {i+1} input_tokens mismatch: expected {expected_interaction['input_tokens']}, got {details['input_tokens']}"
                    assert details["output_tokens"] == expected_interaction["output_tokens"], \
                        f"Stage '{stage_name}' ({stage_key}) interaction {i+1} output_tokens mismatch: expected {expected_interaction['output_tokens']}, got {details['output_tokens']}"
                    assert details["total_tokens"] == expected_interaction["total_tokens"], \
                        f"Stage '{stage_name}' ({stage_key}) interaction {i+1} total_tokens mismatch: expected {expected_interaction['total_tokens']}, got {details['total_tokens']}"
                    
                    total_input_tokens += details["input_tokens"]
                    total_output_tokens += details["output_tokens"]
                    total_tokens += details["total_tokens"]
                
                # Verify interaction type
                if "interaction_type" in expected_interaction:
                    assert details.get("interaction_type") == expected_interaction["interaction_type"], \
                        f"Stage '{stage_name}' ({stage_key}) interaction {i+1} interaction_type mismatch: expected '{expected_interaction['interaction_type']}', got '{details.get('interaction_type')}'"
            
            elif interaction_type == "mcp":
                assert details["communication_type"] == expected_interaction["communication_type"], \
                    f"Stage '{stage_name}' ({stage_key}) interaction {i+1} communication_type mismatch"
                
                if "server_name" in expected_interaction:
                    assert details.get("server_name") == expected_interaction["server_name"], \
                        f"Stage '{stage_name}' ({stage_key}) interaction {i+1} server_name mismatch: expected '{expected_interaction['server_name']}', got '{details.get('server_name')}'"
                
                if "tool_name" in expected_interaction:
                    assert details.get("tool_name") == expected_interaction["tool_name"], \
                        f"Stage '{stage_name}' ({stage_key}) interaction {i+1} tool_name mismatch: expected '{expected_interaction['tool_name']}', got '{details.get('tool_name')}'"
        
        # Verify stage-level token counts
        if total_tokens > 0:
            assert actual_stage['stage_input_tokens'] == total_input_tokens, \
                f"Stage '{stage_name}' ({stage_key}) stage_input_tokens mismatch: expected {total_input_tokens}, got {actual_stage['stage_input_tokens']}"
            assert actual_stage['stage_output_tokens'] == total_output_tokens, \
                f"Stage '{stage_name}' ({stage_key}) stage_output_tokens mismatch: expected {total_output_tokens}, got {actual_stage['stage_output_tokens']}"
            assert actual_stage['stage_total_tokens'] == total_tokens, \
                f"Stage '{stage_name}' ({stage_key}) stage_total_tokens mismatch: expected {total_tokens}, got {actual_stage['stage_total_tokens']}"
        
        # Verify conversation structure if expected
        if 'expected_conversation' in expected_stage:
            print(f"   🔍 Validating conversation history (proving restoration from pause)...")
            expected_conversation = expected_stage['expected_conversation']
            
            # Get the last LLM interaction's conversation (should contain full history)
            if llm_interactions:
                last_llm_interaction = llm_interactions[-1]
                actual_conversation = last_llm_interaction['details']['conversation']
                actual_messages = actual_conversation['messages']
                expected_messages = expected_conversation['messages']
                
                # Verify message count
                assert len(actual_messages) == len(expected_messages), \
                    f"Stage '{stage_name}' ({stage_key}) conversation message count mismatch: expected {len(expected_messages)}, got {len(actual_messages)}"
                
                # Verify each message
                for i, expected_msg in enumerate(expected_messages):
                    actual_msg = actual_messages[i]
                    
                    # Verify role
                    assert actual_msg['role'] == expected_msg['role'], \
                        f"Stage '{stage_name}' ({stage_key}) message {i+1} role mismatch: expected '{expected_msg['role']}', got '{actual_msg['role']}'"
                    
                    # Verify content contains expected strings
                    if 'content_contains' in expected_msg:
                        for expected_str in expected_msg['content_contains']:
                            assert expected_str in actual_msg['content'], \
                                f"Stage '{stage_name}' ({stage_key}) message {i+1} missing expected content: '{expected_str}'"
                
                print(f"   ✅ Conversation validation passed! {len(actual_messages)} messages verified")
                print(f"      - Message 1 (system): Agent instructions preserved")
                print(f"      - Message 2 (user): Complete context restored:")
                print(f"        * Available tools (kubectl_get, kubectl_describe)")
                print(f"        * Alert metadata (type: test-kubernetes, severity: warning, env: production)")
                print(f"        * Alert data (namespace, cluster, finalizers)")
                print(f"        * Runbook content (Mock Runbook, Test runbook content)")
                print(f"        * Stage instructions (DATA-COLLECTION with specific tasks)")
                print(f"      - Messages 3-4: First iteration restored (kubectl_get + observation)")
                print(f"      - Messages 5-6: Second iteration restored (kubectl_describe + observation)")
                print(f"      - Message 7 (NEW): Completion after resume (Final Answer referencing history)")
                print(f"      ✅ PROVES: resume_paused_session() restored COMPLETE context, not just raw messages")
        
        print(f"   ✅ Stage validation passed!")
        print(f"   Total tokens: input={total_input_tokens}, output={total_output_tokens}, total={total_tokens}")

    @pytest.mark.e2e
    async def test_pause_and_resume_workflow(
        self, e2e_test_client, e2e_realistic_kubernetes_alert
    ):
        """
        Test complete pause and resume workflow.

        Flow:
        1. POST alert with max_iterations=2
        2. Wait for session to pause (max iterations reached after 2 iterations)
        3. Verify pause metadata and state
        4. Increase max_iterations to 4 to allow completion
        5. POST to resume endpoint
        6. Wait for session to complete (deterministic - iteration 3 has Final Answer)
        7. Verify final state and audit trail
        """

        # Wrap entire test in timeout to prevent hanging
        async def run_test():
            print("🚀 Starting pause/resume e2e test...")
            result = await self._execute_test(
                e2e_test_client, e2e_realistic_kubernetes_alert
            )
            print("✅ Pause/resume e2e test completed!")
            return result

        try:
            task = asyncio.create_task(run_test())
            done, pending = await asyncio.wait({task}, timeout=120.0)

            if pending:
                for t in pending:
                    t.cancel()
                print("❌ TIMEOUT: Test exceeded 120 seconds!")
                raise AssertionError("Test exceeded timeout of 120 seconds")
            else:
                return task.result()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            raise

    async def _execute_test(self, e2e_test_client, e2e_realistic_kubernetes_alert):
        """Execute the pause/resume test with mocked external dependencies."""
        print("🔧 _execute_test started")

        # Override max_iterations to 2 for quick pause
        from tarsy.config.settings import get_settings
        settings = get_settings()
        original_max_iterations = settings.max_llm_mcp_iterations
        settings.max_llm_mcp_iterations = 2
        print(f"🔧 Overrode max_llm_mcp_iterations from {original_max_iterations} to 2")

        # Track all LLM interactions
        all_llm_interactions = []

        # Define mock response map for LLM interactions
        # Each interaction gets a mock response to simulate ReAct pattern
        # DETERMINISTIC TEST FLOW:
        # Phase 1 (max_iterations=2): Interactions 1-2, then PAUSE
        # Phase 2 (max_iterations=4): Resume + Interaction 3 with Final Answer → COMPLETE
        mock_response_map = {
            1: {  # First iteration - initial analysis
                "response_content": """Thought: I need to get namespace information to understand the issue.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}""",
                "input_tokens": 200,
                "output_tokens": 80,
                "total_tokens": 280,
            },
            2: {  # Second iteration - will trigger pause
                "response_content": """Thought: I see the namespace is in Terminating state. I need more information to continue the analysis, but I've reached the iteration limit.
Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "namespace", "name": "stuck-namespace"}""",
                "input_tokens": 220,
                "output_tokens": 90,
                "total_tokens": 310,
            },
            3: {  # Third iteration - after resume, completes data-collection stage
                "response_content": """Thought: I've gathered enough information from the namespace describe showing finalizers. I can now provide the data collection summary.

Final Answer: **Data Collection Complete**

Collected the following information:
- Namespace: stuck-namespace is in Terminating state (45m)
- Finalizers: kubernetes.io/pvc-protection is blocking deletion
- Status: Namespace is stuck and cannot complete termination

Data collection stage is now complete. The gathered information shows finalizers are preventing namespace deletion.""",
                "input_tokens": 240,
                "output_tokens": 120,
                "total_tokens": 360,
            },
            4: {  # Verification stage - iteration 1, immediate Final Answer
                "response_content": """Thought: Based on the data collection results, I can verify the findings.

Final Answer: **Verification Complete**

Verified the root cause:
- Namespace stuck in Terminating state is confirmed
- Finalizers (kubernetes.io/pvc-protection) are preventing deletion
- This is a common issue when PVCs are not properly cleaned up

Verification confirms the data collection findings are accurate.""",
                "input_tokens": 200,
                "output_tokens": 100,
                "total_tokens": 300,
            },
            5: {  # Analysis stage - iteration 1, immediate Final Answer
                "response_content": """Thought: I can now provide the final analysis based on previous stages.

Final Answer: **Final Analysis**

**Root Cause:** Namespace 'stuck-namespace' cannot complete termination due to the kubernetes.io/pvc-protection finalizer remaining after resource cleanup.

**Resolution Steps:**
1. Remove the finalizer manually: `kubectl patch namespace stuck-namespace -p '{"spec":{"finalizers":null}}' --type=merge`
2. Verify deletion: `kubectl get namespace stuck-namespace`

**Prevention:** Ensure PVCs are deleted before namespace deletion to allow proper finalizer cleanup.

Analysis complete after successful resume from pause.""",
                "input_tokens": 250,
                "output_tokens": 140,
                "total_tokens": 390,
            },
        }

        # Create streaming mock for LLM client
        def create_streaming_mock():
            """Create a mock astream function that returns streaming responses."""

            async def mock_astream(*args, **kwargs):
                interaction_num = len(all_llm_interactions) + 1
                all_llm_interactions.append(interaction_num)

                print(f"\n🔍 LLM REQUEST #{interaction_num}:")
                if args and len(args) > 0:
                    messages = args[0]
                    for i, msg in enumerate(messages):
                        role = getattr(msg, "type", "unknown") if hasattr(msg, "type") else "unknown"
                        content = getattr(msg, "content", "") if hasattr(msg, "content") else ""
                        print(f"  Message {i+1} ({role}): {content[:100]}...")

                # Get mock response for this interaction
                mock_response = mock_response_map.get(
                    interaction_num,
                    {"response_content": "", "input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                )

                content = mock_response["response_content"]
                usage_metadata = {
                    "input_tokens": mock_response["input_tokens"],
                    "output_tokens": mock_response["output_tokens"],
                    "total_tokens": mock_response["total_tokens"],
                }

                async for chunk in create_mock_stream(content, usage_metadata):
                    yield chunk

            return mock_astream

        # Create MCP session mock
        def create_mcp_session_mock():
            """Create a mock MCP session that provides kubectl tools."""
            mock_session = AsyncMock()

            async def mock_call_tool(tool_name, _parameters):
                mock_result = Mock()

                if tool_name == "kubectl_get":
                    resource = _parameters.get("resource", "pods")
                    name = _parameters.get("name", "")
                    namespace = _parameters.get("namespace", "")

                    if resource == "namespaces" and name == "stuck-namespace":
                        mock_content = Mock()
                        mock_content.text = "stuck-namespace   Terminating   45m"
                        mock_result.content = [mock_content]
                    elif resource == "events":
                        mock_content = Mock()
                        mock_content.text = "LAST SEEN   TYPE      REASON      OBJECT                MESSAGE\n5m          Warning   FailedDelete namespace/stuck-namespace   Finalizers blocking deletion"
                        mock_result.content = [mock_content]
                    else:
                        mock_content = Mock()
                        mock_content.text = f"Mock kubectl get {resource} response"
                        mock_result.content = [mock_content]

                elif tool_name == "kubectl_describe":
                    # Simulate a kubectl describe response
                    mock_content = Mock()
                    mock_content.text = """Name:         stuck-namespace
Status:       Terminating
Finalizers:   [kubernetes.io/pvc-protection]
"""
                    mock_result.content = [mock_content]
                else:
                    mock_content = Mock()
                    mock_content.text = f"Mock response for tool: {tool_name}"
                    mock_result.content = [mock_content]

                return mock_result

            async def mock_list_tools():
                mock_tool1 = Tool(
                    name="kubectl_get",
                    description="Get Kubernetes resources",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "resource": {"type": "string"},
                            "namespace": {"type": "string"},
                            "name": {"type": "string"},
                        },
                    },
                )

                mock_tool2 = Tool(
                    name="kubectl_describe",
                    description="Describe Kubernetes resources",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "resource": {"type": "string"},
                            "namespace": {"type": "string"},
                            "name": {"type": "string"},
                        },
                    },
                )

                mock_result = Mock()
                mock_result.tools = [mock_tool1, mock_tool2]
                return mock_result

            mock_session.call_tool.side_effect = mock_call_tool
            mock_session.list_tools.side_effect = mock_list_tools

            return mock_session

        # Create test MCP server configurations
        k8s_config = E2ETestUtils.create_simple_kubernetes_mcp_config(
            command_args=["kubernetes-mock-server-ready"],
            instructions="Test kubernetes server for pause/resume e2e testing",
        )

        test_mcp_servers = E2ETestUtils.create_test_mcp_servers(
            BUILTIN_MCP_SERVERS, {"kubernetes-server": k8s_config}
        )

        # Apply comprehensive mocking
        with patch("tarsy.config.builtin_config.BUILTIN_MCP_SERVERS", test_mcp_servers), \
             patch("tarsy.services.mcp_server_registry.MCPServerRegistry._DEFAULT_SERVERS", test_mcp_servers), \
             E2ETestUtils.setup_runbook_service_patching():

                # Mock LLM streaming
                streaming_mock = create_streaming_mock()

                from langchain_openai import ChatOpenAI
                from langchain_anthropic import ChatAnthropic
                from langchain_xai import ChatXAI
                from langchain_google_genai import ChatGoogleGenerativeAI

                with patch.object(ChatOpenAI, "astream", streaming_mock), \
                     patch.object(ChatAnthropic, "astream", streaming_mock), \
                     patch.object(ChatXAI, "astream", streaming_mock), \
                     patch.object(ChatGoogleGenerativeAI, "astream", streaming_mock):

                    # Mock MCP client
                    mock_kubernetes_session = create_mcp_session_mock()
                    mock_sessions = {"kubernetes-server": mock_kubernetes_session}
                    mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

                    async def mock_initialize(self):
                        """Mock initialization that sets up mock sessions."""
                        self.sessions = mock_sessions.copy()
                        self._initialized = True

                    with patch.object(MCPClient, "initialize", mock_initialize), \
                         patch.object(MCPClient, "list_tools", mock_list_tools), \
                         patch.object(MCPClient, "call_tool", mock_call_tool):

                        print("⏳ Step 1: Submitting alert with max_iterations=2...")
                        session_id = E2ETestUtils.submit_alert(
                            e2e_test_client, e2e_realistic_kubernetes_alert
                        )

                        print("⏳ Step 2: Waiting for session to pause...")
                        paused_session_id, paused_status = await E2ETestUtils.wait_for_session_completion(
                            e2e_test_client, max_wait_seconds=15, debug_logging=True
                        )

                        print("🔍 Step 3: Verifying pause state...")
                        assert paused_session_id == session_id, "Session ID mismatch"
                        assert paused_status == "paused", f"Expected status 'paused', got '{paused_status}'"
                        print(f"✅ Session paused: {session_id}")

                        # Get session details to verify pause metadata
                        detail_data = E2ETestUtils.get_session_details(e2e_test_client, session_id)
                        
                        # Verify pause metadata exists
                        pause_metadata = detail_data.get("pause_metadata")
                        assert pause_metadata is not None, "pause_metadata missing from paused session"
                        assert pause_metadata.get("reason") == "max_iterations_reached", \
                            f"Expected pause reason 'max_iterations_reached', got '{pause_metadata.get('reason')}'"
                        assert pause_metadata.get("current_iteration") == 2, \
                            f"Expected current_iteration=2, got {pause_metadata.get('current_iteration')}"
                        assert "message" in pause_metadata, "pause_metadata missing 'message' field"
                        assert "paused_at_us" in pause_metadata, "pause_metadata missing 'paused_at_us' field"
                        print(f"✅ Pause metadata verified: {pause_metadata}")

                        # Verify stages exist and last stage is paused
                        stages = detail_data.get("stages", [])
                        assert len(stages) > 0, "No stages found in paused session"
                        
                        # Find the paused stage
                        paused_stage = None
                        for stage in stages:
                            if stage.get("status") == "paused":
                                paused_stage = stage
                                break
                        
                        assert paused_stage is not None, "No paused stage found"
                        # Note: current_iteration is stored in DB but not exposed in API DetailedStage model
                        # The iteration information is available in pause_metadata at session level
                        print(f"✅ Paused stage verified: {paused_stage.get('stage_name')}")

                        print("⏳ Step 4: Increasing max_iterations to allow completion after resume...")
                        # Increase max_iterations to 4 so the session can complete after resume
                        # Mock responses 3 and 4 will execute, with 4 providing the Final Answer
                        settings.max_llm_mcp_iterations = 4
                        print(f"🔧 Increased max_llm_mcp_iterations to 4")

                        print("⏳ Step 5: Resuming paused session...")
                        resume_response = e2e_test_client.post(
                            f"/api/v1/history/sessions/{session_id}/resume"
                        )
                        assert resume_response.status_code == 200, \
                            f"Resume failed with status {resume_response.status_code}: {resume_response.text}"
                        
                        resume_data = resume_response.json()
                        assert resume_data.get("success") is True, "Resume response indicates failure"
                        assert resume_data.get("status") == "resuming", \
                            f"Expected status 'resuming', got '{resume_data.get('status')}'"
                        print(f"✅ Resume initiated: {resume_data}")

                        print("⏳ Step 6: Waiting for resumed session to complete...")
                        # With max_iterations=4 and mock response 4 providing Final Answer,
                        # the session MUST complete (not pause again)
                        final_session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                            e2e_test_client, max_wait_seconds=15, debug_logging=True
                        )

                        print("🔍 Step 7: Verifying final state...")
                        assert final_session_id == session_id, "Session ID mismatch after resume"
                        # With our mock setup, session MUST complete (not pause again)
                        assert final_status == "completed", \
                            f"Expected status 'completed' after resume, got '{final_status}'"
                        print(f"✅ Final status: {final_status}")

                        # Verify audit trail
                        final_detail_data = E2ETestUtils.get_session_details(e2e_test_client, session_id)
                        
                        # Verify session-level timestamps
                        assert final_detail_data.get("started_at_us") > 0, "started_at_us missing"
                        assert final_detail_data.get("completed_at_us") > 0, "completed_at_us missing"
                        assert final_detail_data.get("completed_at_us") > final_detail_data.get("started_at_us"), \
                            "completed_at_us should be after started_at_us"
                        
                        # Verify stages structure after resume
                        # After pause/resume, we have 4 stage executions:
                        # 1. data-collection (active/paused - the initial execution that paused)
                        # 2. data-collection (completed - the resumed execution)
                        # 3. verification (completed)
                        # 4. analysis (completed)
                        final_stages = final_detail_data.get("stages", [])
                        
                        # Extract stage info for verification
                        stage_info = [(s.get("stage_name"), s.get("status")) for s in final_stages]
                        print(f"📊 Actual stages found: {stage_info}")
                        
                        # We expect exactly 4 stage executions
                        assert len(final_stages) == 4, \
                            f"Expected 4 stage executions (paused data-collection + completed data-collection + verification + analysis), got {len(final_stages)}"
                        
                        # Verify stage order and statuses
                        assert final_stages[0].get("stage_name") == "data-collection", "First stage should be data-collection"
                        assert final_stages[0].get("status") in ["active", "paused"], \
                            f"First data-collection should be active/paused, got {final_stages[0].get('status')}"
                        
                        assert final_stages[1].get("stage_name") == "data-collection", "Second stage should be data-collection"
                        assert final_stages[1].get("status") == "completed", "Second data-collection should be completed"
                        
                        assert final_stages[2].get("stage_name") == "verification", "Third stage should be verification"
                        assert final_stages[2].get("status") == "completed", "Verification should be completed"
                        
                        assert final_stages[3].get("stage_name") == "analysis", "Fourth stage should be analysis"
                        assert final_stages[3].get("status") == "completed", "Analysis should be completed"
                        
                        print(f"✅ All 4 stage executions verified: paused data-collection, completed data-collection, verification, analysis")

                        # Verify LLM interactions match our mock setup
                        # Mock interactions: 1,2 (pause) → 3 (data-collection) → 4 (verification) → 5 (analysis)
                        # Total: 5 interactions
                        total_llm_interactions = sum(
                            len(stage.get("llm_interactions", [])) for stage in final_stages
                        )
                        print(f"✅ Total LLM interactions: {total_llm_interactions}")
                        assert total_llm_interactions == 5, \
                            f"Expected exactly 5 LLM interactions (2 before pause + 3 after resume), got {total_llm_interactions}"

                        print("\n🔍 Step 8: Comprehensive stage validation (proving resume from pause, not restart)...")
                        
                        # Validate paused data-collection stage (first execution - paused at iteration 2)
                        self._validate_stage(final_stages[0], 'paused_data-collection')
                        
                        # Validate resumed data-collection stage (second execution - completed with iteration 3)
                        # This proves we resumed from where we paused, not restarted
                        self._validate_stage(final_stages[1], 'resumed_data-collection')
                        
                        # Validate verification stage (ran after data-collection completed)
                        self._validate_stage(final_stages[2], 'verification')
                        
                        # Validate analysis stage (final stage)
                        self._validate_stage(final_stages[3], 'analysis')
                        
                        print("\n✅ ALL VALIDATIONS PASSED!")
                        print("   - Paused stage has exactly 2 LLM interactions (proving it stopped)")
                        print("   - Resumed stage has exactly 1 LLM interaction (proving it continued, not restarted)")
                        print("   - Token counts match expected (proving no extra work)")
                        print("   - Timeline is correct (paused → resumed → verification → analysis)")

                        print("\n✅ PAUSE/RESUME E2E TEST PASSED!")
                        
                        # Restore original max_iterations
                        settings.max_llm_mcp_iterations = original_max_iterations
                        print(f"🔧 Restored max_llm_mcp_iterations to {original_max_iterations}")
                        return

