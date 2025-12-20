"""
E2E Test for Pause/Resume Functionality with Multiple Cycles.

This test verifies the complete pause/resume workflow including multiple pause/resume cycles:
1. Submit alert with max_iterations=2
2. Wait for session to pause (first pause at iteration 2)
3. Verify pause metadata and paused state
4. Set max_iterations to 1 and resume (iteration counter resets, pause_metadata cleared)
5. Wait for session to pause again (second pause at iteration 1 of resumed session)
6. Verify second pause metadata (new pause metadata, shows iteration 1)
7. Increase max_iterations to 4 and resume again (pause_metadata cleared)
8. Wait for session to complete (deterministic - interaction 5 has Final Answer)
9. Verify final state has no pause_metadata (cleared on completion)

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: HTTP requests to LLM APIs, MCP servers, GitHub runbooks
- CONFIGURED: max_llm_mcp_iterations dynamically changed during test (2→1→4)
- DETERMINISTIC: Interaction 5 provides Final Answer → guaranteed completion
- CLEAN STATE: pause_metadata cleared when not paused (simpler model)
"""

import asyncio
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import Tool

from tarsy.config.builtin_config import BUILTIN_MCP_SERVERS
from tarsy.integrations.mcp.client import MCPClient

from .conftest import create_mock_stream
from .e2e_utils import E2ETestUtils
from .expected_pause_resume_conversations import EXPECTED_PAUSE_RESUME_STAGES

logger = logging.getLogger(__name__)


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
        
        # Ensure the stage_key mapping is correct (stage_key should match stage_name)
        assert stage_name == stage_key, (
            f"Stage key '{stage_key}' does not match actual stage_name '{stage_name}'. "
            f"This indicates a mismatch between EXPECTED_PAUSE_RESUME_STAGES keys and API data."
        )
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
            print("   🔍 Validating conversation history (proving restoration from pause)...")
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
                
                # Verify each message with full content matching
                for i, expected_msg in enumerate(expected_messages):
                    actual_msg = actual_messages[i]
                    
                    # Verify role
                    assert actual_msg['role'] == expected_msg['role'], \
                        f"Stage '{stage_name}' ({stage_key}) message {i+1} role mismatch: expected '{expected_msg['role']}', got '{actual_msg['role']}'"
                    
                    # Normalize and verify full content match
                    expected_content = E2ETestUtils.normalize_content(expected_msg['content'])
                    actual_content = E2ETestUtils.normalize_content(actual_msg['content'])
                    
                    assert expected_content == actual_content, \
                        f"Stage '{stage_name}' ({stage_key}) message {i+1} content mismatch: expected length {len(expected_content)}, got {len(actual_content)}"
                
                print(f"   ✅ Conversation validation passed! {len(actual_messages)} messages verified")
                print("      - Message 1 (system): Agent instructions preserved")
                print("      - Message 2 (user): Complete context restored:")
                print("        * Available tools (kubectl_get, kubectl_describe)")
                print("        * Alert metadata (type: test-kubernetes, severity: warning, env: production)")
                print("        * Alert data (namespace, cluster, finalizers)")
                print("        * Runbook content (Mock Runbook, Test runbook content)")
                print("        * Stage instructions (DATA-COLLECTION with specific tasks)")
                print("      - Messages 3-4: First iteration restored (kubectl_get + observation)")
                print("      - Messages 5-6: Second iteration restored (kubectl_describe + observation)")
                print("      - Message 7 (NEW): Completion after resume (Final Answer referencing history)")
                print("      ✅ PROVES: resume_paused_session() restored COMPLETE context, not just raw messages")
        
        print("   ✅ Stage validation passed!")
        print(f"   Total tokens: input={total_input_tokens}, output={total_output_tokens}, total={total_tokens}")

    @pytest.mark.e2e
    async def test_pause_and_resume_workflow(
        self, e2e_test_client, e2e_realistic_kubernetes_alert
    ):
        """
        Test complete pause and resume workflow with multiple pause/resume cycles.

        Flow:
        1. POST alert with max_iterations=2
        2. Wait for session to pause (first pause at iteration 2)
        3. Verify first pause metadata and state
        4. Set max_iterations to 1 and resume (first resume) - iteration counter resets
        5. Wait for session to pause again (second pause at iteration 1 of resumed session)
        6. Verify second pause metadata (overwrites first, shows iteration 1)
        7. Increase max_iterations to 4 and resume (second resume)
        8. Wait for session to complete (deterministic - interaction 5 has Final Answer)
        9. Verify final state has no pause_metadata (cleared on completion)
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

        try:
            settings.max_llm_mcp_iterations = 2
            print(f"🔧 Overrode max_llm_mcp_iterations from {original_max_iterations} to 2")
            # Track all LLM interactions
            all_llm_interactions = []

            # Define mock response map for LLM interactions
            # Each interaction gets a mock response to simulate ReAct pattern
            # DETERMINISTIC TEST FLOW WITH MULTIPLE PAUSE/RESUME:
            # Phase 1 (max_iterations=2): Interactions 1-2, then PAUSE #1 (at iteration 2)
            # Phase 2 (max_iterations=1): Resume + Interaction 3, then PAUSE #2 (at iteration 1 - counter resets)
            # Phase 3 (max_iterations=4): Resume + Interactions 4-5 (tool call + Final Answer) → COMPLETE
            mock_response_map = {
                1: {  # First iteration - initial analysis
                    "response_content": """Thought: I need to get namespace information to understand the issue.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}""",
                    "input_tokens": 200,
                    "output_tokens": 80,
                    "total_tokens": 280,
                },
                2: {  # Second iteration - will trigger FIRST pause
                    "response_content": """Thought: I see the namespace is in Terminating state. I need more information to continue the analysis, but I've reached the iteration limit.
Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "namespace", "name": "stuck-namespace"}""",
                    "input_tokens": 220,
                    "output_tokens": 90,
                    "total_tokens": 310,
                },
                3: {  # Third iteration - after first resume, makes additional tool call, will trigger SECOND pause
                    "response_content": """Thought: I've seen the namespace is stuck with finalizers. Let me check for related events to understand what's happening.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "events", "namespace": "stuck-namespace"}""",
                    "input_tokens": 240,
                    "output_tokens": 100,
                    "total_tokens": 340,
                },
                4: {  # Fourth iteration - after second resume, continues ReAct loop with tool call
                    "response_content": """Thought: I have good information about the namespace and events. Let me check pods to see if any are still running.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "pods", "namespace": "stuck-namespace"}""",
                    "input_tokens": 260,
                    "output_tokens": 100,
                    "total_tokens": 360,
                },
                5: {  # Fifth iteration - after second resume, completes data-collection stage with Final Answer
                    "response_content": """Thought: I've gathered comprehensive information. No pods are running, and the namespace is stuck due to finalizers. I can now provide the data collection summary.

Final Answer: **Data Collection Complete**

Collected the following information:
- Namespace: stuck-namespace is in Terminating state (45m)
- Finalizers: kubernetes.io/pvc-protection is blocking deletion
- Events: FailedDelete warning shows finalizers blocking deletion
- Pods: No pods running in the namespace
- Status: Namespace is stuck and cannot complete termination due to finalizers

Data collection stage is now complete. The gathered information shows finalizers are preventing namespace deletion.""",
                    "input_tokens": 280,
                    "output_tokens": 150,
                    "total_tokens": 430,
                },
                6: {  # Verification stage - iteration 1, immediate Final Answer
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
                7: {  # Analysis stage - iteration 1, immediate Final Answer
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
                8: {  # Executive summary generation after analysis completes
                    "response_content": """Executive Summary: Namespace 'stuck-namespace' is stuck in Terminating state due to finalizers. Remove finalizers manually to complete deletion.""",
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                },
            }

            # Create streaming mock for LLM client
            def create_streaming_mock():
                """Create a mock astream function that returns streaming responses."""

                async def mock_astream(*args, **_kwargs):
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

                        if resource == "namespaces" and name == "stuck-namespace":
                            mock_content = Mock()
                            mock_content.text = "stuck-namespace   Terminating   45m"
                            mock_result.content = [mock_content]
                        elif resource == "events":
                            mock_content = Mock()
                            mock_content.text = "LAST SEEN   TYPE      REASON      OBJECT                MESSAGE\n5m          Warning   FailedDelete namespace/stuck-namespace   Finalizers blocking deletion"
                            mock_result.content = [mock_content]
                        elif resource == "pods":
                            mock_content = Mock()
                            mock_content.text = "No resources found in stuck-namespace namespace."
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

                    # Patch LangChain clients using shared utility
                    with E2ETestUtils.create_llm_patch_context(streaming_mock=streaming_mock):
                        # Mock MCP client
                        mock_kubernetes_session = create_mcp_session_mock()
                        mock_sessions = {"kubernetes-server": mock_kubernetes_session}
                        mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)

                        async def mock_initialize(self):
                            """Mock initialization that sets up mock sessions."""
                            self.sessions = mock_sessions.copy()
                            self._ready = True

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
                            detail_data = await E2ETestUtils.get_session_details_async(e2e_test_client, session_id)
                            
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

                            print("⏳ Step 4: Setting max_iterations to 1 (will cause second pause after 1 iteration)...")
                            # Set max_iterations to 1 - this will allow exactly one more iteration then pause again
                            # Note: iteration counter resets on resume, so this allows 1 iteration from resumed state
                            settings.max_llm_mcp_iterations = 1
                            print("🔧 Set max_llm_mcp_iterations to 1")

                            print("⏳ Step 5: Resuming paused session (first resume)...")
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

                            print("⏳ Step 6: Waiting for resumed session to pause again (second pause)...")
                            # With max_iterations=1, session will pause again after interaction 1
                            second_paused_session_id, second_paused_status = await E2ETestUtils.wait_for_session_completion(
                                e2e_test_client, max_wait_seconds=15, debug_logging=True
                            )
                            
                            print("🔍 Step 7: Verifying second pause state...")
                            assert second_paused_session_id == session_id, "Session ID mismatch after first resume"
                            assert second_paused_status == "paused", f"Expected status 'paused' after first resume, got '{second_paused_status}'"
                            print(f"✅ Second pause verified: {session_id}")
                            
                            # Get session details to verify second pause metadata
                            second_pause_detail = await E2ETestUtils.get_session_details_async(e2e_test_client, session_id)
                            second_pause_metadata = second_pause_detail.get("pause_metadata")
                            assert second_pause_metadata is not None, "pause_metadata missing from second paused session"
                            assert second_pause_metadata.get("reason") == "max_iterations_reached"
                            assert second_pause_metadata.get("current_iteration") == 1, \
                                f"Expected current_iteration=1 for second pause (resets on resume), got {second_pause_metadata.get('current_iteration')}"
                            print(f"✅ Second pause metadata verified: {second_pause_metadata}")

                            print("⏳ Step 8: Increasing max_iterations to 4 to allow final completion...")
                            settings.max_llm_mcp_iterations = 4
                            print("🔧 Increased max_llm_mcp_iterations to 4")

                            print("⏳ Step 9: Resuming paused session (second resume)...")
                            second_resume_response = e2e_test_client.post(
                                f"/api/v1/history/sessions/{session_id}/resume"
                            )
                            assert second_resume_response.status_code == 200, \
                                f"Second resume failed with status {second_resume_response.status_code}: {second_resume_response.text}"
                            print("✅ Second resume initiated")

                            print("⏳ Step 10: Waiting for resumed session to complete...")
                            # With max_iterations=4 and mock response 5 providing Final Answer,
                            # the session MUST complete (not pause again)
                            final_session_id, final_status = await E2ETestUtils.wait_for_session_completion(
                                e2e_test_client, max_wait_seconds=15, debug_logging=True
                            )

                            print("🔍 Step 11: Verifying final state after multiple pause/resume cycles...")
                            assert final_session_id == session_id, "Session ID mismatch after second resume"
                            assert final_status == "completed", \
                                f"Expected status 'completed' after second resume, got '{final_status}'"
                            print(f"✅ Final status: {final_status}")

                            # Verify clean state
                            final_detail_data = await E2ETestUtils.get_session_details_async(e2e_test_client, session_id)
                            
                            # Verify pause_metadata is cleared after completion (keep it clean)
                            final_pause_metadata = final_detail_data.get("pause_metadata")
                            assert final_pause_metadata is None, \
                                "pause_metadata should be cleared after completion (not paused = no pause_metadata)"
                            print("✅ Pause metadata cleared after completion (clean state)")
                            
                            # Verify executive summary was generated
                            final_analysis_summary = final_detail_data.get("final_analysis_summary")
                            assert final_analysis_summary is not None, \
                                "final_analysis_summary should be generated for completed resumed sessions"
                            assert len(final_analysis_summary) > 0, \
                                "final_analysis_summary should not be empty"
                            print(f"✅ Executive summary generated: {len(final_analysis_summary)} chars")
                            
                            # Verify session-level timestamps
                            assert final_detail_data.get("started_at_us") > 0, "started_at_us missing"
                            assert final_detail_data.get("completed_at_us") > 0, "completed_at_us missing"
                            assert final_detail_data.get("completed_at_us") > final_detail_data.get("started_at_us"), \
                                "completed_at_us should be after started_at_us"
                            
                            # Verify stages structure after resume
                            # After pause/resume, we have 3 stage executions:
                            # 1. data-collection (completed - reused from paused execution)
                            # 2. verification (completed)
                            # 3. analysis (completed)
                            final_stages = final_detail_data.get("stages", [])
                            
                            # Extract stage info for verification
                            stage_info = [(s.get("stage_name"), s.get("status")) for s in final_stages]
                            print(f"📊 Actual stages found: {stage_info}")
                            
                            # We expect exactly 3 stage executions
                            assert len(final_stages) == 3, \
                                f"Expected 3 stage executions (data-collection reused + verification + analysis), got {len(final_stages)}"
                            
                            # Verify stage order and statuses
                            assert final_stages[0].get("stage_name") == "data-collection", "First stage should be data-collection"
                            assert final_stages[0].get("status") == "completed", \
                                f"Data-collection should be completed (reused from paused), got {final_stages[0].get('status')}"
                            
                            assert final_stages[1].get("stage_name") == "verification", "Second stage should be verification"
                            assert final_stages[1].get("status") == "completed", "Verification should be completed"
                            
                            assert final_stages[2].get("stage_name") == "analysis", "Third stage should be analysis"
                            assert final_stages[2].get("status") == "completed", "Analysis should be completed"
                            
                            print("✅ All 3 stage executions verified: data-collection (reused), verification, analysis")

                            # Verify LLM interactions match our mock setup
                            # Mock interactions: 
                            # - 1,2 (pause #1 at iteration 2) 
                            # - 3 (pause #2 at iteration 1 after resume/reset) 
                            # - 4,5 (data-collection complete after second resume) 
                            # - 6 (verification) 
                            # - 7 (analysis)
                            # - 8 (executive summary generation after completion)
                            # Total: 8 interactions (7 for stages + 1 for summary)
                            total_llm_interactions = sum(
                                len(stage.get("llm_interactions", [])) for stage in final_stages
                            )
                            print(f"✅ Total stage LLM interactions: {total_llm_interactions}")
                            # Note: The 8th interaction (executive summary) happens outside stage execution
                            # so it's not counted in stage LLM interactions, but it still happens
                            assert total_llm_interactions == 7, \
                                f"Expected exactly 7 stage LLM interactions (2 before first pause + 1 before second pause + 2 after second resume + 2 for other stages), got {total_llm_interactions}"
                            
                            # Verify the mock was called 8 times total (7 stage + 1 summary)
                            print(f"✅ Total LLM calls (including summary): {len(all_llm_interactions)}")
                            assert len(all_llm_interactions) == 8, \
                                f"Expected 8 total LLM calls (7 for stages + 1 for executive summary), got {len(all_llm_interactions)}"

                            print("\n🔍 Step 12: Comprehensive stage validation (proving multiple pause/resume cycles work)...")
                            
                            # Validate data-collection stage (reused: 2 interactions before pause + 2 after resume)
                            # This proves we resumed the same stage execution, not created a new one
                            self._validate_stage(final_stages[0], 'data-collection')
                            
                            # Validate verification stage (ran after data-collection completed)
                            self._validate_stage(final_stages[1], 'verification')
                            
                            # Validate analysis stage (final stage)
                            self._validate_stage(final_stages[2], 'analysis')
                            
                            print("\n✅ ALL VALIDATIONS PASSED!")
                            print("   - Data-collection stage has exactly 5 LLM interactions")
                            print("   - Multiple pause/resume cycles worked correctly:")
                            print("     * First pause at iteration 2 (global: interactions 1-2)")
                            print("     * Second pause at iteration 1 (global: interaction 3, counter resets)")  
                            print("     * Completed after second resume at iteration 2 (global: interactions 4-5)")
                            print("     * PROVES: Agent can do full ReAct loops after second resume (interaction 4: tool call)")
                            print("   - Single stage execution was reused (no duplicate stage created)")
                            print("   - Token counts match expected (proving no extra work)")
                            print("   - pause_metadata cleared after completion (clean state)")
                            print("   - Timeline is correct (data-collection → verification → analysis)")

                            print("\n✅ MULTIPLE PAUSE/RESUME E2E TEST PASSED!")
        finally:
            # Always restore original value, even on failure
            settings.max_llm_mcp_iterations = original_max_iterations
            print(f"🔧 Restored max_llm_mcp_iterations to {original_max_iterations}")

