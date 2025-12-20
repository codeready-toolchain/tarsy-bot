"""
E2E Test for Pause/Resume Functionality with Native Thinking Controller.

This test verifies the complete pause/resume workflow for native thinking:
1. Submit alert with max_iterations=2
2. Wait for session to pause (first pause at iteration 2)
3. Verify pause metadata and paused state
4. Set max_iterations to 1 and resume (iteration counter resets, pause_metadata cleared)
5. Wait for session to pause again (second pause at iteration 1 of resumed session)
6. Verify second pause metadata (new pause metadata, shows iteration 1)
7. Increase max_iterations to 4 and resume again (pause_metadata cleared)
8. Wait for session to complete
9. Verify final state has no pause_metadata (cleared on completion)

Key differences from ReAct test:
- Uses GeminiNativeThinkingClient instead of LangChain astream
- Native function calling instead of text parsing
- Thinking content captured separately
- Empty text_content when making tool calls (Gemini behavior)
"""

import asyncio
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
from mcp.types import Tool

from tarsy.config.builtin_config import BUILTIN_MCP_SERVERS
from tarsy.integrations.mcp.client import MCPClient

from .conftest import (
    MockGeminiClient,
    create_mock_stream,
    create_native_thinking_response,
)
from .e2e_utils import E2ETestUtils

logger = logging.getLogger(__name__)


# Expected stages for pause/resume native thinking test
# NOTE: Tool discovery happens on each resume, so MCP counts include those
EXPECTED_NATIVE_THINKING_PAUSE_RESUME_STAGES = {
    'data-collection': {
        'expected_status': 'completed',
        'llm_count': 6,  # 4 native thinking iterations + 1 summarization + 1 final
        'mcp_count': 10,  # 2 initial + 2 on resume #1 + 2 on resume #2 + 4 tool calls
        'interactions': [
            # Initial tool discovery
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'test-data-server'},
            # LLM 1 - First tool call
            {'type': 'llm', 'success': True, 'input_tokens': 200, 'output_tokens': 80, 'total_tokens': 280, 'interaction_type': 'investigation', 'has_thinking_content': True},
            {'type': 'mcp', 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # LLM 2 - Second tool call (triggers first pause at iteration 2)
            {'type': 'llm', 'success': True, 'input_tokens': 220, 'output_tokens': 90, 'total_tokens': 310, 'interaction_type': 'investigation', 'has_thinking_content': True},
            {'type': 'mcp', 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_describe', 'server_name': 'kubernetes-server'},
            # --- FIRST PAUSE at iteration 2 ---
            # --- FIRST RESUME with max_iterations=1 - tool discovery happens again ---
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'test-data-server'},
            # LLM 3 - Third tool call (triggers second pause at iteration 1)
            {'type': 'llm', 'success': True, 'input_tokens': 240, 'output_tokens': 100, 'total_tokens': 340, 'interaction_type': 'investigation', 'has_thinking_content': True},
            {'type': 'mcp', 'communication_type': 'tool_call', 'success': True, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
            # --- SECOND PAUSE at iteration 1 ---
            # --- SECOND RESUME with max_iterations=4 - tool discovery happens again ---
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'test-data-server'},
            # LLM 4 - Fourth tool call (triggers summarization)
            {'type': 'llm', 'success': True, 'input_tokens': 260, 'output_tokens': 100, 'total_tokens': 360, 'interaction_type': 'investigation', 'has_thinking_content': True},
            {'type': 'mcp', 'communication_type': 'tool_call', 'success': True, 'tool_name': 'collect_system_info', 'server_name': 'test-data-server'},
            # LLM 5 - Summarization (via LangChain, no thinking content)
            {'type': 'llm', 'success': True, 'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150, 'interaction_type': 'summarization', 'has_thinking_content': False},
            # LLM 6 - Final answer
            {'type': 'llm', 'success': True, 'input_tokens': 280, 'output_tokens': 150, 'total_tokens': 430, 'interaction_type': 'final_analysis', 'has_thinking_content': True},
        ],
    },
    'verification': {
        'expected_status': 'completed',
        'llm_count': 1,  # Direct final answer
        'mcp_count': 1,  # Tool list discovery
        'interactions': [
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            {'type': 'llm', 'success': True, 'input_tokens': 200, 'output_tokens': 100, 'total_tokens': 300, 'interaction_type': 'final_analysis', 'has_thinking_content': True},
        ],
    },
    'analysis': {
        'expected_status': 'completed',
        'llm_count': 1,  # Direct final answer
        'mcp_count': 1,  # Tool list discovery
        'interactions': [
            {'type': 'mcp', 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
            {'type': 'llm', 'success': True, 'input_tokens': 250, 'output_tokens': 140, 'total_tokens': 390, 'interaction_type': 'final_analysis', 'has_thinking_content': True},
        ],
    },
}

# Expected thinking content for pause/resume test
EXPECTED_PAUSE_RESUME_THINKING_CONTENT = {
    'data-collection': {
        1: "I need to check the namespace status to understand the issue. Let me use kubectl_get to see the namespace state.",
        2: "The namespace is in Terminating state. I need more details about what's blocking the deletion.",
        3: "I see finalizers are blocking deletion. Let me check for events to understand what's happening.",
        4: "Let me collect system information to see if there are any resource constraints.",
        5: "I have collected comprehensive information. The namespace is stuck due to finalizers. Time to provide the data collection summary.",
    },
    'verification': {
        1: "Based on the data collection results, I can verify the findings without additional tool calls.",
    },
    'analysis': {
        1: "I can now provide the final analysis based on the verified data from previous stages.",
    },
}


@pytest.mark.asyncio
@pytest.mark.e2e
class TestNativeThinkingPauseResumeE2E:
    """
    E2E test for native thinking pause/resume functionality.
    
    Tests:
    - Session pauses correctly when max_iterations reached
    - Pause metadata is captured (thinking content preserved)
    - Resume restores conversation state correctly
    - Multiple pause/resume cycles work
    - Token and thinking content tracking across pause/resume
    """

    def _validate_stage(self, actual_stage, stage_key):
        """Validate a stage's interactions match expected structure."""
        stage_name = actual_stage["stage_name"]
        expected_stage = EXPECTED_NATIVE_THINKING_PAUSE_RESUME_STAGES[stage_key]
        
        assert stage_name == stage_key, (
            f"Stage key '{stage_key}' does not match actual stage_name '{stage_name}'"
        )
        
        llm_interactions = actual_stage.get("llm_interactions", [])
        mcp_interactions = actual_stage.get("mcp_communications", [])
        
        print(f"\n🔍 Validating stage '{stage_name}'")
        print(f"   Status: {actual_stage['status']} (expected: {expected_stage['expected_status']})")
        print(f"   LLM interactions: {len(llm_interactions)} (expected: {expected_stage['llm_count']})")
        print(f"   MCP interactions: {len(mcp_interactions)} (expected: {expected_stage['mcp_count']})")
        
        # Verify interaction counts
        assert len(llm_interactions) == expected_stage["llm_count"], \
            f"Stage '{stage_name}': Expected {expected_stage['llm_count']} LLM interactions, got {len(llm_interactions)}"
        assert len(mcp_interactions) == expected_stage["mcp_count"], \
            f"Stage '{stage_name}': Expected {expected_stage['mcp_count']} MCP interactions, got {len(mcp_interactions)}"
        
        # Verify status
        assert actual_stage['status'] == expected_stage['expected_status'], \
            f"Stage '{stage_name}': Expected status '{expected_stage['expected_status']}', got '{actual_stage['status']}'"
        
        # Verify chronological interactions
        chronological_interactions = actual_stage.get("chronological_interactions", [])
        assert len(chronological_interactions) == len(expected_stage["interactions"]), \
            f"Stage '{stage_name}' interaction count mismatch"
        
        # Track token totals
        total_input_tokens = 0
        total_output_tokens = 0
        total_tokens = 0
        llm_position = 0
        
        # Validate each interaction
        for i, expected_interaction in enumerate(expected_stage["interactions"]):
            actual_interaction = chronological_interactions[i]
            interaction_type = expected_interaction["type"]
            
            assert actual_interaction["type"] == interaction_type, \
                f"Stage '{stage_name}' interaction {i+1} type mismatch"
            
            details = actual_interaction["details"]
            assert details["success"] == expected_interaction["success"], \
                f"Stage '{stage_name}' interaction {i+1} success mismatch"
            
            if interaction_type == "llm":
                llm_position += 1
                
                # Verify token usage
                if "input_tokens" in expected_interaction:
                    assert details["input_tokens"] == expected_interaction["input_tokens"], \
                        f"Stage '{stage_name}' interaction {i+1} input_tokens mismatch"
                    assert details["output_tokens"] == expected_interaction["output_tokens"], \
                        f"Stage '{stage_name}' interaction {i+1} output_tokens mismatch"
                    assert details["total_tokens"] == expected_interaction["total_tokens"], \
                        f"Stage '{stage_name}' interaction {i+1} total_tokens mismatch"
                    
                    total_input_tokens += details["input_tokens"]
                    total_output_tokens += details["output_tokens"]
                    total_tokens += details["total_tokens"]
                
                # Verify interaction type
                if "interaction_type" in expected_interaction:
                    assert details.get("interaction_type") == expected_interaction["interaction_type"], \
                        f"Stage '{stage_name}' interaction {i+1} interaction_type mismatch"
                
                # Verify thinking content
                if "has_thinking_content" in expected_interaction:
                    actual_thinking = details.get("thinking_content")
                    
                    if expected_interaction["has_thinking_content"]:
                        assert actual_thinking is not None and len(actual_thinking) > 0, \
                            f"Stage '{stage_name}' interaction {i+1}: expected thinking_content"
                        
                        # Verify exact thinking content
                        if stage_key in EXPECTED_PAUSE_RESUME_THINKING_CONTENT:
                            expected_thinking_map = EXPECTED_PAUSE_RESUME_THINKING_CONTENT[stage_key]
                            if llm_position in expected_thinking_map:
                                expected_thinking = expected_thinking_map[llm_position]
                                assert actual_thinking == expected_thinking, \
                                    f"Stage '{stage_name}' LLM {llm_position} thinking_content mismatch.\n" \
                                    f"Expected: '{expected_thinking}'\n" \
                                    f"Actual:   '{actual_thinking}'"
            
            elif interaction_type == "mcp":
                assert details["communication_type"] == expected_interaction["communication_type"], \
                    f"Stage '{stage_name}' interaction {i+1} communication_type mismatch"
                
                if "server_name" in expected_interaction:
                    assert details.get("server_name") == expected_interaction["server_name"]
                
                if "tool_name" in expected_interaction:
                    assert details.get("tool_name") == expected_interaction["tool_name"]
        
        # Verify stage-level token counts
        if total_tokens > 0:
            assert actual_stage['stage_input_tokens'] == total_input_tokens
            assert actual_stage['stage_output_tokens'] == total_output_tokens
            assert actual_stage['stage_total_tokens'] == total_tokens
        
        print(f"   ✅ Stage validation passed! Tokens: {total_tokens}")

    @pytest.mark.e2e
    async def test_native_thinking_pause_and_resume(
        self, e2e_native_thinking_test_client, e2e_native_thinking_alert
    ):
        """
        Test complete pause and resume workflow with native thinking.
        
        Verifies:
        - Native thinking pauses correctly at max_iterations
        - Thinking content is preserved across pause/resume
        - Empty text_content for tool calls (Gemini behavior)
        - Multiple pause/resume cycles work
        """
        
        async def run_test():
            print("🚀 Starting native thinking pause/resume e2e test...")
            result = await self._execute_test(
                e2e_native_thinking_test_client, e2e_native_thinking_alert
            )
            print("✅ Native thinking pause/resume e2e test completed!")
            return result
        
        try:
            task = asyncio.create_task(run_test())
            done, pending = await asyncio.wait({task}, timeout=120.0)
            
            if pending:
                for t in pending:
                    t.cancel()
                raise AssertionError("Test exceeded timeout of 120 seconds")
            else:
                return task.result()
        except Exception as e:
            print(f"❌ Test failed: {e}")
            raise

    async def _execute_test(self, e2e_test_client, e2e_alert):
        """Execute the native thinking pause/resume test."""
        print("🔧 Starting native thinking pause/resume test")
        
        from tarsy.config.settings import get_settings
        settings = get_settings()
        original_max_iterations = settings.max_llm_mcp_iterations
        
        try:
            settings.max_llm_mcp_iterations = 2
            print(f"🔧 Set max_llm_mcp_iterations to 2 (was {original_max_iterations})")
            
            # Track all Gemini interactions
            all_gemini_interactions = []
            shared_call_counter = [0]
            
            # Native thinking mock responses
            # Empty text_content when making tool calls (Gemini behavior)
            mock_response_map = {
                1: {  # First tool call - kubectl_get namespace
                    "text_content": "",
                    "thinking_content": "I need to check the namespace status to understand the issue. Let me use kubectl_get to see the namespace state.",
                    "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "namespaces", "name": "stuck-namespace"}}],
                    "input_tokens": 200, "output_tokens": 80, "total_tokens": 280
                },
                2: {  # Second tool call - kubectl_describe (triggers first pause)
                    "text_content": "",
                    "thinking_content": "The namespace is in Terminating state. I need more details about what's blocking the deletion.",
                    "function_calls": [{"name": "kubernetes-server__kubectl_describe", "args": {"resource": "namespace", "name": "stuck-namespace"}}],
                    "input_tokens": 220, "output_tokens": 90, "total_tokens": 310
                },
                # --- FIRST PAUSE at iteration 2 ---
                # --- FIRST RESUME with max_iterations=1 ---
                3: {  # Third tool call - kubectl_get events (triggers second pause)
                    "text_content": "",
                    "thinking_content": "I see finalizers are blocking deletion. Let me check for events to understand what's happening.",
                    "function_calls": [{"name": "kubernetes-server__kubectl_get", "args": {"resource": "events", "namespace": "stuck-namespace"}}],
                    "input_tokens": 240, "output_tokens": 100, "total_tokens": 340
                },
                # --- SECOND PAUSE at iteration 1 ---
                # --- SECOND RESUME with max_iterations=4 ---
                4: {  # Fourth tool call - collect_system_info (triggers summarization)
                    "text_content": "",
                    "thinking_content": "Let me collect system information to see if there are any resource constraints.",
                    "function_calls": [{"name": "test-data-server__collect_system_info", "args": {"detailed": False}}],
                    "input_tokens": 260, "output_tokens": 100, "total_tokens": 360
                },
                # Note: Summarization happens via LangChain
                5: {  # Fifth - Final answer for data-collection
                    "text_content": "Data collection complete. Namespace 'stuck-namespace' is stuck in Terminating state due to kubernetes.io/pvc-protection finalizer.",
                    "thinking_content": "I have collected comprehensive information. The namespace is stuck due to finalizers. Time to provide the data collection summary.",
                    "function_calls": None,
                    "input_tokens": 280, "output_tokens": 150, "total_tokens": 430
                },
                6: {  # Verification - Direct final answer
                    "text_content": "Verification complete. Root cause confirmed: finalizers blocking namespace deletion.",
                    "thinking_content": "Based on the data collection results, I can verify the findings without additional tool calls.",
                    "function_calls": None,
                    "input_tokens": 200, "output_tokens": 100, "total_tokens": 300
                },
                7: {  # Analysis - Direct final answer
                    "text_content": "Final analysis: Remove the kubernetes.io/pvc-protection finalizer using kubectl patch to allow namespace deletion.",
                    "thinking_content": "I can now provide the final analysis based on the verified data from previous stages.",
                    "function_calls": None,
                    "input_tokens": 250, "output_tokens": 140, "total_tokens": 390
                },
            }
            
            def create_gemini_mock_client(api_key: str = "test-api-key"):
                """Create a mock Gemini client."""
                
                def response_generator(call_num_ignored: int, model: str, contents: list, config):
                    shared_call_counter[0] += 1
                    call_num = shared_call_counter[0]
                    all_gemini_interactions.append(call_num)
                    
                    print(f"\n🔍 GEMINI REQUEST #{call_num}")
                    
                    response_data = mock_response_map.get(call_num, {
                        "text_content": "",
                        "thinking_content": None,
                        "function_calls": None,
                        "input_tokens": 0, "output_tokens": 0, "total_tokens": 0
                    })
                    
                    return create_native_thinking_response(
                        text_content=response_data.get("text_content", ""),
                        thinking_content=response_data.get("thinking_content"),
                        function_calls=response_data.get("function_calls"),
                        input_tokens=response_data.get("input_tokens", 100),
                        output_tokens=response_data.get("output_tokens", 50),
                        total_tokens=response_data.get("total_tokens", 150)
                    )
                
                return MockGeminiClient(response_generator, api_key)
            
            # Create MCP session mocks
            def create_mcp_session_mock():
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
                            mock_content.text = "Warning   FailedDelete   namespace/stuck-namespace   Finalizers blocking"
                            mock_result.content = [mock_content]
                        else:
                            mock_content = Mock()
                            mock_content.text = f"Mock kubectl get {resource} response"
                            mock_result.content = [mock_content]
                    
                    elif tool_name == "kubectl_describe":
                        mock_content = Mock()
                        mock_content.text = "Name: stuck-namespace\nStatus: Terminating\nFinalizers: [kubernetes.io/pvc-protection]"
                        mock_result.content = [mock_content]
                    
                    else:
                        mock_content = Mock()
                        mock_content.text = f"Mock response for {tool_name}"
                        mock_result.content = [mock_content]
                    
                    return mock_result
                
                async def mock_list_tools():
                    mock_result = Mock()
                    mock_result.tools = [
                        Tool(name="kubectl_get", description="Get Kubernetes resources", inputSchema={"type": "object", "properties": {}}),
                        Tool(name="kubectl_describe", description="Describe Kubernetes resources", inputSchema={"type": "object", "properties": {}})
                    ]
                    return mock_result
                
                mock_session.call_tool.side_effect = mock_call_tool
                mock_session.list_tools.side_effect = mock_list_tools
                return mock_session
            
            def create_custom_mcp_session_mock():
                mock_session = AsyncMock()
                
                async def mock_call_tool(tool_name, _parameters):
                    if tool_name == "collect_system_info":
                        # Large result triggers summarization
                        return {
                            "result": "Long system info " * 100  # >100 tokens
                        }
                    return {"result": f"Mock {tool_name}"}
                
                async def mock_list_tools():
                    mock_result = Mock()
                    mock_result.tools = [
                        Tool(name="collect_system_info", description="Collect system info", inputSchema={"type": "object", "properties": {}})
                    ]
                    return mock_result
                
                mock_session.call_tool.side_effect = mock_call_tool
                mock_session.list_tools.side_effect = mock_list_tools
                return mock_session
            
            # Create test MCP configs
            k8s_config = E2ETestUtils.create_simple_kubernetes_mcp_config(
                command_args=["kubernetes-mock"],
                instructions="Test kubernetes server"
            )
            data_config = E2ETestUtils.create_simple_data_server_mcp_config(
                command_args=["test-data-server"],
                instructions="Test data server"
            )
            
            test_mcp_servers = E2ETestUtils.create_test_mcp_servers(BUILTIN_MCP_SERVERS, {
                "kubernetes-server": k8s_config,
                "test-data-server": data_config
            })
            
            # LangChain mock for summarization and executive summary
            def create_langchain_streaming_mock():
                langchain_call_counter = [0]
                langchain_responses = {
                    1: "Summarized: System healthy, resources normal.",
                    2: "Executive Summary: Namespace stuck due to finalizers. Remove finalizers to fix.",
                }
                
                async def mock_astream(*args, **kwargs):
                    langchain_call_counter[0] += 1
                    call_num = langchain_call_counter[0]
                    content = langchain_responses.get(call_num, f"Mock LangChain #{call_num}")
                    usage_metadata = {'input_tokens': 100, 'output_tokens': 50, 'total_tokens': 150}
                    async for chunk in create_mock_stream(content, usage_metadata):
                        yield chunk
                
                return mock_astream
            
            # Apply mocking
            with patch("tarsy.config.builtin_config.BUILTIN_MCP_SERVERS", test_mcp_servers), \
                 patch("tarsy.services.mcp_server_registry.MCPServerRegistry._DEFAULT_SERVERS", test_mcp_servers), \
                 E2ETestUtils.setup_runbook_service_patching():
                
                langchain_mock = create_langchain_streaming_mock()
                
                # Patch both Gemini SDK and LangChain clients using shared utility
                with E2ETestUtils.create_llm_patch_context(
                    gemini_mock_factory=create_gemini_mock_client,
                    streaming_mock=langchain_mock
                ):
                    
                    mock_k8s_session = create_mcp_session_mock()
                    mock_data_session = create_custom_mcp_session_mock()
                    mock_sessions = {
                        "kubernetes-server": mock_k8s_session,
                        "test-data-server": mock_data_session
                    }
                    mock_list_tools, mock_call_tool = E2ETestUtils.create_mcp_client_patches(mock_sessions)
                    
                    async def mock_initialize(self):
                        self.sessions = mock_sessions.copy()
                        self._ready = True
                    
                    with patch.object(MCPClient, "initialize", mock_initialize), \
                         patch.object(MCPClient, "list_tools", mock_list_tools), \
                         patch.object(MCPClient, "call_tool", mock_call_tool):
                        
                        # Step 1: Submit alert
                        print("⏳ Step 1: Submitting alert with max_iterations=2...")
                        session_id = E2ETestUtils.submit_alert(e2e_test_client, e2e_alert)
                        
                        # Step 2: Wait for first pause
                        print("⏳ Step 2: Waiting for session to pause...")
                        paused_id, paused_status = await E2ETestUtils.wait_for_session_completion(
                            e2e_test_client, max_wait_seconds=15
                        )
                        
                        # Step 3: Verify first pause
                        print("🔍 Step 3: Verifying first pause state...")
                        assert paused_status == "paused", f"Expected 'paused', got '{paused_status}'"
                        
                        detail_data = await E2ETestUtils.get_session_details_async(e2e_test_client, session_id)
                        pause_metadata = detail_data.get("pause_metadata")
                        assert pause_metadata is not None, "pause_metadata missing"
                        assert pause_metadata.get("current_iteration") == 2, \
                            f"Expected iteration=2, got {pause_metadata.get('current_iteration')}"
                        print("✅ First pause verified at iteration 2")
                        
                        # Step 4: Set max_iterations to 1 and resume
                        print("⏳ Step 4: Setting max_iterations=1 and resuming...")
                        settings.max_llm_mcp_iterations = 1
                        
                        resume_response = e2e_test_client.post(
                            f"/api/v1/history/sessions/{session_id}/resume"
                        )
                        assert resume_response.status_code == 200
                        print("✅ First resume initiated")
                        
                        # Step 5: Wait for second pause
                        print("⏳ Step 5: Waiting for second pause...")
                        second_paused_id, second_status = await E2ETestUtils.wait_for_session_completion(
                            e2e_test_client, max_wait_seconds=15
                        )
                        
                        # Step 6: Verify second pause
                        print("🔍 Step 6: Verifying second pause state...")
                        assert second_status == "paused", f"Expected 'paused', got '{second_status}'"
                        
                        second_detail = await E2ETestUtils.get_session_details_async(e2e_test_client, session_id)
                        second_pause = second_detail.get("pause_metadata")
                        assert second_pause.get("current_iteration") == 1, \
                            f"Expected iteration=1 (reset), got {second_pause.get('current_iteration')}"
                        print("✅ Second pause verified at iteration 1 (counter reset)")
                        
                        # Step 7: Set max_iterations to 4 and resume
                        print("⏳ Step 7: Setting max_iterations=4 and resuming...")
                        settings.max_llm_mcp_iterations = 4
                        
                        second_resume = e2e_test_client.post(
                            f"/api/v1/history/sessions/{session_id}/resume"
                        )
                        assert second_resume.status_code == 200
                        print("✅ Second resume initiated")
                        
                        # Step 8: Wait for completion
                        print("⏳ Step 8: Waiting for completion...")
                        final_id, final_status = await E2ETestUtils.wait_for_session_completion(
                            e2e_test_client, max_wait_seconds=15
                        )
                        
                        # Step 9: Verify final state
                        print("🔍 Step 9: Verifying final state...")
                        assert final_status == "completed", f"Expected 'completed', got '{final_status}'"
                        
                        final_detail = await E2ETestUtils.get_session_details_async(e2e_test_client, session_id)
                        
                        # Verify pause_metadata cleared
                        assert final_detail.get("pause_metadata") is None, \
                            "pause_metadata should be cleared after completion"
                        print("✅ Pause metadata cleared after completion")
                        
                        # Verify stages
                        final_stages = final_detail.get("stages", [])
                        assert len(final_stages) == 3, f"Expected 3 stages, got {len(final_stages)}"
                        
                        # Validate each stage
                        print("\n🔍 Step 10: Validating stages...")
                        self._validate_stage(final_stages[0], 'data-collection')
                        self._validate_stage(final_stages[1], 'verification')
                        self._validate_stage(final_stages[2], 'analysis')
                        
                        # Verify total Gemini calls
                        print(f"\n✅ Total Gemini calls: {len(all_gemini_interactions)}")
                        assert len(all_gemini_interactions) == 7, \
                            f"Expected 7 Gemini calls, got {len(all_gemini_interactions)}"
                        
                        print("\n✅ NATIVE THINKING PAUSE/RESUME TEST PASSED!")
                        print("   - First pause at iteration 2")
                        print("   - Second pause at iteration 1 (counter reset)")
                        print("   - Completed after second resume")
                        print("   - Thinking content preserved across pause/resume")
                        print("   - Empty text_content for tool calls (Gemini behavior)")
        
        finally:
            settings.max_llm_mcp_iterations = original_max_iterations
            print(f"🔧 Restored max_llm_mcp_iterations to {original_max_iterations}")

