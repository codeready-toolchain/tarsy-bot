"""
Simplified End-to-End Test with HTTP-level mocking.

This test uses the real FastAPI application with real internal services,
mocking only external HTTP dependencies at the network boundary.

Architecture:
- REAL: FastAPI app, AlertService, HistoryService, hook system, database
- MOCKED: HTTP requests to LLM APIs, MCP servers, GitHub runbooks
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
import respx
import httpx
from tarsy.integrations.mcp.client import MCPClient
from tarsy.config.builtin_config import BUILTIN_MCP_SERVERS

@pytest.mark.asyncio
@pytest.mark.e2e
class TestRealE2E:
    """
    Simplified E2E test using HTTP-level mocking.
    
    Tests the complete system flow:
    1. HTTP POST to /alerts endpoint
    2. Real alert processing through AlertService
    3. Real agent execution with real hook system
    4. Real database storage via HistoryService  
    5. HTTP GET from history APIs
    
    Mocks only external HTTP calls (LLM APIs, runbooks, MCP servers).
    """

    async def test_complete_alert_processing_flow(
        self,
        e2e_test_client,
        e2e_realistic_kubernetes_alert,
        isolated_e2e_settings,
        isolated_test_database
    ):
        """
        Simplified E2E test focusing on core functionality.
        
        Flow:
        1. POST alert to /alerts -> queued
        2. Wait for processing to complete
        3. Verify session was created and completed
        4. Verify basic structure (stages exist)
        
        This simplified test verifies:
        - Alert submission works
        - Processing completes without hanging
        - Session is created and marked as completed
        - Basic stage structure exists
        """
        
        # Wrap entire test in hardcore timeout to prevent hanging
        async def run_test():
            print("🚀 Starting test execution...")
            result = await self._execute_test(
                e2e_test_client,
                e2e_realistic_kubernetes_alert,
                isolated_e2e_settings,
                isolated_test_database
            )
            print("✅ Test execution completed!")
            return result
        
        try:
            # Use task-based timeout instead of wait_for to avoid cancellation issues
            task = asyncio.create_task(run_test())
            done, pending = await asyncio.wait({task}, timeout=10.0)
            
            if pending:
                # Timeout occurred
                for t in pending:
                    t.cancel()
                print("❌ HARDCORE TIMEOUT: Test exceeded 30 seconds!")
                print("Check for hanging in alert processing pipeline")
                raise AssertionError("Test exceeded hardcore timeout of 10 seconds")
            else:
                # Task completed
                return task.result()
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            raise
    
    async def _execute_test(
        self,
        e2e_test_client,
        e2e_realistic_kubernetes_alert,
        isolated_e2e_settings,
        isolated_test_database
    ):
        """Minimal test execution with maximum real infrastructure."""
        print("🔧 _execute_test started")
        
        # ONLY mock external network calls - use real internal services
        # Using respx for HTTP mocking and MCP SDK mocking for stdio communication
        
        # Simplified interaction tracking - focus on LLM calls only
        # (MCP interactions will be validated from API response)
        all_llm_interactions = []
        
        # Create HTTP response handlers for respx
        def create_llm_response_handler():
            """Create a handler that tracks LLM interactions and returns appropriate responses."""
            def llm_response_handler(request):
                try:
                    # Track the interaction for counting
                    request_data = request.content.decode() if hasattr(request, 'content') and request.content else "{}"
                    all_llm_interactions.append(request_data)
                    
                    # Determine response based on interaction count (simple pattern)
                    total_interactions = len(all_llm_interactions)
                    
                    if total_interactions <= 3:
                        # Data collection stage responses
                        if total_interactions == 1:
                            response_content = """Thought: I need to get namespace information first.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}"""
                        elif total_interactions == 2:
                            response_content = """Action: kubernetes-server.kubectl_describe
Action Input: {"resource": "namespace", "name": "stuck-namespace"}"""
                        else:
                            response_content = """Final Answer: Data collection completed. Found namespace 'stuck-namespace' in Terminating state with finalizers blocking deletion."""
                    
                    elif total_interactions <= 5:
                        # Verification stage responses
                        if total_interactions == 4:
                            response_content = """Thought: I need to verify the namespace status.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}"""
                        else:
                            response_content = """Final Answer: Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion."""
                    
                    else:
                        # Analysis stage response
                        response_content = """Based on previous stages, the namespace is stuck due to finalizers.
## Recommended Actions
1. Remove finalizers to allow deletion"""
                    
                    # Return HTTP response in the format expected by LangChain
                    return httpx.Response(
                        200,
                        json={
                            "choices": [{
                                "message": {
                                    "content": response_content,
                                    "role": "assistant"
                                },
                                "finish_reason": "stop"
                            }],
                            "model": "gpt-4",
                            "usage": {"total_tokens": 150}
                        }
                    )
                except Exception as e:
                    print(f"Error in LLM response handler: {e}")
                    # Fallback response
                    return httpx.Response(200, json={
                        "choices": [{"message": {"content": "Fallback response", "role": "assistant"}}]
                    })
            
            return llm_response_handler
        
        # Create MCP SDK mock functions  
        def create_mcp_session_mock():
            """Create a mock MCP session that provides kubectl tools."""
            mock_session = AsyncMock()
            
            async def mock_call_tool(tool_name, parameters):
                # Create mock result object with content attribute
                mock_result = Mock()
                
                if tool_name == 'kubectl_get':
                    resource = parameters.get('resource', 'pods')
                    name = parameters.get('name', '')
                    
                    if resource == 'namespaces' and name == 'stuck-namespace':
                        mock_content = Mock()
                        mock_content.text = 'stuck-namespace   Terminating   45m'
                        mock_result.content = [mock_content]
                    else:
                        mock_content = Mock()
                        mock_content.text = f"Mock kubectl get {resource} response"
                        mock_result.content = [mock_content]
                
                elif tool_name == 'kubectl_describe':
                    resource = parameters.get('resource', '')
                    name = parameters.get('name', '')
                    
                    if resource == 'namespace' and name == 'stuck-namespace':
                        mock_content = Mock()
                        mock_content.text = """Name:         stuck-namespace
Status:       Terminating
Finalizers:   kubernetes.io/pv-protection"""
                        mock_result.content = [mock_content]
                    else:
                        mock_content = Mock()
                        mock_content.text = f"Mock kubectl describe {resource} {name} response"
                        mock_result.content = [mock_content]
                
                else:
                    mock_content = Mock()
                    mock_content.text = f"Mock response for tool: {tool_name}"
                    mock_result.content = [mock_content]
                
                return mock_result
            
            async def mock_list_tools():
                return [
                    {
                        "name": "kubectl_get",
                        "description": "Get Kubernetes resources",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "resource": {"type": "string"},
                                "namespace": {"type": "string"},
                                "name": {"type": "string"}
                            }
                        }
                    },
                    {
                        "name": "kubectl_describe",
                        "description": "Describe Kubernetes resources",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "resource": {"type": "string"},
                                "namespace": {"type": "string"},
                                "name": {"type": "string"}
                            }
                        }
                    }
                ]
            
            mock_session.call_tool.side_effect = mock_call_tool
            mock_session.list_tools.side_effect = mock_list_tools
            
            return mock_session
        
        # Create the mock MCP session
        mock_mcp_session = create_mcp_session_mock()
        
        # Create test MCP server configuration that doesn't launch external processes
        test_mcp_servers = BUILTIN_MCP_SERVERS.copy()
        test_mcp_servers['kubernetes-server'] = {
            "server_id": "kubernetes-server",
            "server_type": "test",
            "enabled": True,
            "connection_params": {
                "command": "echo",  # Safe command that won't fail
                "args": ["test-response"]
            },
            "instructions": "Test kubernetes server for e2e testing",
            "data_masking": {"enabled": False}
        }
        
        # Apply comprehensive mocking with test MCP server config
        with respx.mock() as respx_mock, \
             patch('tarsy.config.builtin_config.BUILTIN_MCP_SERVERS', test_mcp_servers):
            
            # 1. Mock LLM API calls (preserves LLM hooks!)
            llm_handler = create_llm_response_handler()
            
            # Mock all major LLM provider endpoints (covers openai, anthropic, etc.)
            respx_mock.post(url__regex=r".*(openai\.com|anthropic\.com|api\.x\.ai|generativelanguage\.googleapis\.com|googleapis\.com).*").mock(side_effect=llm_handler)
            
            # 2. Mock runbook HTTP calls (various sources)
            respx_mock.get(url__regex=r".*(github\.com|runbooks\.example\.com).*").mock(
                return_value=httpx.Response(200, text="# Mock Runbook\nTest runbook content")
            )
            
            # 3. Mock MCP client initialization to use test server and mock session
            def mock_mcp_init(self, *args, **kwargs):
                self.settings = args[0] if args else Mock()
                self.mcp_registry = Mock()
                self.data_masking_service = None
                self.sessions = {'kubernetes-server': mock_mcp_session}
                self._initialized = True
                self.exit_stack = Mock()
            
            async def mock_initialize():
                # Don't actually try to launch external processes
                pass
            
            with patch.object(MCPClient, '__init__', mock_mcp_init), \
                 patch.object(MCPClient, 'initialize', mock_initialize):
            
                print("🔧 Using the real AlertService with test MCP server config and mocking...")
                # All internal services are real, hooks work perfectly!
                # HTTP calls (LLM, runbooks) are mocked via respx
                # MCP server config replaced with test config to avoid external NPM packages
                # MCP calls handled by mock session that provides kubectl tools
            
                # STEP 1: Submit alert
                print("🚀 Step 1: Submitting alert")
                response = e2e_test_client.post("/alerts", json=e2e_realistic_kubernetes_alert)
                assert response.status_code == 200
                
                response_data = response.json()
                assert response_data["status"] == "queued"
                alert_id = response_data["alert_id"]
                print(f"✅ Alert submitted: {alert_id}")
                
                # STEP 2: Wait for processing with robust polling
                print("⏳ Step 2: Waiting for processing...")
                session_id, final_status = await self._wait_for_session_completion(e2e_test_client, max_wait_seconds=8)
                
                # STEP 3: Verify results
                print("🔍 Step 3: Verifying results...")
                
                # Basic verification
                assert session_id is not None, "Session ID missing"
                print(f"✅ Session found: {session_id}, final status: {final_status}")
                
                # Verify session completed successfully
                assert final_status == "completed", f"Expected session to be completed, but got: {final_status}"
                print("✅ Session completed successfully!")
                
                # Get session details to verify stages structure
                session_detail_response = e2e_test_client.get(f"/api/v1/history/sessions/{session_id}")
                assert session_detail_response.status_code == 200, f"Failed to get session details: {session_detail_response.status_code}"
                
                detail_data = session_detail_response.json()
                stages = detail_data.get("stages", [])
                print(f"Found {len(stages)} stages in completed session")
                
                # Assert that stages exist and verify basic structure
                assert len(stages) > 0, "Session completed but no stages found - invalid session structure"
                print("✅ Session has stages - basic structure verified")
                
                # STEP 4: Comprehensive result data verification
                print("🔍 Step 4: Comprehensive result verification...")
                await self._verify_session_metadata(detail_data, e2e_realistic_kubernetes_alert)
                await self._verify_stage_structure(stages)
                await self._verify_complete_interaction_flow(stages)
                
                print("✅ COMPREHENSIVE VERIFICATION PASSED!")
                
                return

    async def _wait_for_session_completion(self, e2e_test_client, max_wait_seconds: int = 8):
        """
        Robust polling logic to wait for session completion.
        
        Args:
            e2e_test_client: Test client for making API calls
            max_wait_seconds: Maximum time to wait in seconds
            
        Returns:
            Tuple of (session_id, final_status)
            
        Raises:
            AssertionError: If no session found or polling times out
        """
        print(f"⏱️ Starting robust polling (max {max_wait_seconds}s)...")
        
        start_time = asyncio.get_event_loop().time()
        poll_interval = 0.2  # Poll every 200ms for responsiveness
        attempts = 0
        
        while True:
            attempts += 1
            elapsed_time = asyncio.get_event_loop().time() - start_time
            
            # Check for timeout
            if elapsed_time >= max_wait_seconds:
                print(f"❌ Polling timeout after {elapsed_time:.1f}s ({attempts} attempts)")
                raise AssertionError(f"Session completion polling timed out after {max_wait_seconds}s")
            
            # Get current sessions
            sessions_response = e2e_test_client.get("/api/v1/history/sessions")
            if sessions_response.status_code != 200:
                print(f"⚠️ Failed to get sessions: {sessions_response.status_code}")
                await asyncio.sleep(poll_interval)
                continue
            
            sessions_data = sessions_response.json()
            sessions = sessions_data.get('sessions', [])
            
            if not sessions:
                print(f"⏳ No sessions yet (attempt {attempts}, {elapsed_time:.1f}s)")
                await asyncio.sleep(poll_interval)
                continue
            
            # Check the most recent session (first in list)
            session = sessions[0]
            session_id = session.get("session_id")
            status = session.get("status")
            
            print(f"⏳ Polling: {session_id} -> {status} (attempt {attempts}, {elapsed_time:.1f}s)")
            
            # Check if session is in a final state
            if status in ["completed", "failed"]:
                print(f"✅ Session reached final state: {status} in {elapsed_time:.1f}s ({attempts} attempts)")
                return session_id, status
            
            # Session exists but not complete yet, continue polling
            await asyncio.sleep(poll_interval)

    async def _verify_session_metadata(self, session_data, original_alert):
        """Verify session metadata matches expectations."""
        print("  📋 Verifying session metadata...")
        
        # Required session fields
        required_fields = ['session_id', 'alert_id', 'alert_type', 'status', 'started_at_us', 'completed_at_us']
        for field in required_fields:
            assert field in session_data, f"Missing required session field: {field}"
        
        # Verify alert type matches
        assert session_data['alert_type'] == original_alert['alert_type'], \
            f"Alert type mismatch: expected {original_alert['alert_type']}, got {session_data['alert_type']}"
        
        # Verify chain information
        assert 'chain_id' in session_data, "Missing chain_id in session data"
        assert session_data['chain_id'] == 'kubernetes-namespace-terminating-chain', \
            f"Unexpected chain_id: {session_data['chain_id']}"
        
        # Verify timestamps are reasonable
        started_at = session_data['started_at_us']
        completed_at = session_data['completed_at_us']
        assert started_at > 0, "Invalid started_at timestamp"
        assert completed_at > started_at, "completed_at should be after started_at"
        
        # Processing duration should be reasonable (< 30 seconds in microseconds)
        processing_duration_ms = (completed_at - started_at) / 1000
        assert processing_duration_ms < 30000, f"Processing took too long: {processing_duration_ms}ms"
        
        print(f"    ✅ Session metadata verified (chain: {session_data['chain_id']}, duration: {processing_duration_ms:.1f}ms)")

    async def _verify_stage_structure(self, stages):
        """Verify stage structure and count."""
        print("  🏗️ Verifying stage structure...")
        
        # Expected stages for kubernetes-namespace-terminating-chain
        expected_stages = ['data-collection', 'verification', 'analysis']
        
        assert len(stages) == len(expected_stages), \
            f"Expected {len(expected_stages)} stages, got {len(stages)}"
        
        # Verify each stage has required structure
        for i, stage in enumerate(stages):
            required_stage_fields = ['stage_id', 'stage_name', 'agent', 'status', 'stage_index']
            for field in required_stage_fields:
                assert field in stage, f"Stage {i} missing required field: {field}"
            
            # Verify stage order and names
            assert stage['stage_name'] == expected_stages[i], \
                f"Stage {i} name mismatch: expected {expected_stages[i]}, got {stage['stage_name']}"
            
            # Verify stage index
            assert stage['stage_index'] == i, \
                f"Stage {i} index mismatch: expected {i}, got {stage['stage_index']}"
            
            # Verify all stages completed successfully
            assert stage['status'] == 'completed', \
                f"Stage {i} ({stage['stage_name']}) not completed: {stage['status']}"
        
        print(f"    ✅ Stage structure verified ({len(stages)} stages in correct order)")

    async def _verify_complete_interaction_flow(self, stages):
        """Verify complete interaction flow with all objects in exact order per stage."""
        print("  🔄 Verifying complete interaction flow...")
        
        # Expected complete interaction structure per stage (from actual test run data)
        expected_stages = {
            'data-collection': {
                'llm_count': 3,
                'mcp_count': 3,
                'interactions': [
                    # MCP 1 - Tool list discovery (first interaction)
                    {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
                    # LLM 1 - Initial ReAct iteration
                    {'type': 'llm', 'position': 1, 'success': True, 'final_message_role': 'assistant'},
                    # MCP 2 - Failed kubectl_get attempt
                    {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': False, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
                    # LLM 2 - Second ReAct iteration  
                    {'type': 'llm', 'position': 2, 'success': True, 'final_message_role': 'assistant'},
                    # MCP 3 - Failed kubectl_describe attempt  
                    {'type': 'mcp', 'position': 3, 'communication_type': 'tool_call', 'success': False, 'tool_name': 'kubectl_describe', 'server_name': 'kubernetes-server'},
                    # LLM 3 - Final answer
                    {'type': 'llm', 'position': 3, 'success': True, 'final_message_role': 'assistant',
                     'expected_final_response': "Final Answer: Data collection completed. Found namespace 'stuck-namespace' in Terminating state with finalizers blocking deletion."}
                ]
            },
            'verification': {
                'llm_count': 2,
                'mcp_count': 2,
                'interactions': [
                    # MCP 1 - Tool list discovery (first interaction)
                    {'type': 'mcp', 'position': 1, 'communication_type': 'tool_list', 'success': True, 'server_name': 'kubernetes-server'},
                    # LLM 1 - Initial ReAct iteration
                    {'type': 'llm', 'position': 1, 'success': True, 'final_message_role': 'assistant'},
                    # MCP 2 - Failed kubectl_get attempt
                    {'type': 'mcp', 'position': 2, 'communication_type': 'tool_call', 'success': False, 'tool_name': 'kubectl_get', 'server_name': 'kubernetes-server'},
                    # LLM 2 - Final answer
                    {'type': 'llm', 'position': 2, 'success': True, 'final_message_role': 'assistant',
                     'expected_final_response': "Final Answer: Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion."}
                ]
            },
            'analysis': {
                'llm_count': 1,
                'mcp_count': 0,
                'interactions': [
                    # LLM 1 - Final analysis (no tool discovery)
                    {'type': 'llm', 'position': 1, 'success': True, 'final_message_role': 'assistant',
                     'expected_final_response': """Based on previous stages, the namespace is stuck due to finalizers.
## Recommended Actions
1. Remove finalizers to allow deletion"""}
                ]
            }
        }
        
        for stage in stages:
            stage_name = stage['stage_name']
            expected_stage = expected_stages.get(stage_name)
            
            if not expected_stage:
                continue  # Skip verification for unexpected stages
                
            # Verify interaction counts match
            llm_interactions = stage.get('llm_interactions', [])
            mcp_interactions = stage.get('mcp_communications', [])
            
            assert len(llm_interactions) == expected_stage['llm_count'], \
                f"Stage '{stage_name}' LLM count mismatch: expected {expected_stage['llm_count']}, got {len(llm_interactions)}"
            
            assert len(mcp_interactions) == expected_stage['mcp_count'], \
                f"Stage '{stage_name}' MCP count mismatch: expected {expected_stage['mcp_count']}, got {len(mcp_interactions)}"
            
            # Verify complete interaction flow in chronological order
            # Get chronological interactions from API (mixed LLM and MCP in actual order)
            chronological_interactions = stage.get('chronological_interactions', [])
            assert len(chronological_interactions) == len(expected_stage['interactions']), \
                f"Stage '{stage_name}' chronological interaction count mismatch: expected {len(expected_stage['interactions'])}, got {len(chronological_interactions)}"
            
            llm_counter = 0
            mcp_counter = 0
            
            for i, expected_interaction in enumerate(expected_stage['interactions']):
                actual_interaction = chronological_interactions[i]
                interaction_type = expected_interaction['type']
                
                # Verify the type matches
                assert actual_interaction['type'] == interaction_type, \
                    f"Stage '{stage_name}' interaction {i+1} type mismatch: expected {interaction_type}, got {actual_interaction['type']}"
                
                if interaction_type == 'llm':
                    llm_counter += 1
                    # Verify basic LLM interaction structure
                    assert 'details' in actual_interaction, f"Stage '{stage_name}' LLM {llm_counter} missing details"
                    details = actual_interaction['details']
                    
                    assert details['success'] == expected_interaction['success'], \
                        f"Stage '{stage_name}' LLM {llm_counter} success mismatch"
                    
                    # Check final message has expected role
                    messages = details.get('messages', [])
                    assert len(messages) > 0, f"Stage '{stage_name}' LLM {llm_counter} has no messages"
                    final_message = messages[-1]
                    assert final_message.get('role') == expected_interaction['final_message_role'], \
                        f"Stage '{stage_name}' LLM {llm_counter} final message role mismatch"
                    
                    # Verify final response content if specified
                    if 'expected_final_response' in expected_interaction:
                        actual_response = final_message.get('content', '').strip()
                        expected_response = expected_interaction['expected_final_response'].strip()
                        assert actual_response == expected_response, \
                            f"Stage '{stage_name}' LLM {llm_counter} response mismatch:\nExpected: {repr(expected_response)}\nActual: {repr(actual_response)}"
                    
                elif interaction_type == 'mcp':
                    mcp_counter += 1
                    # Verify basic MCP interaction structure
                    assert 'details' in actual_interaction, f"Stage '{stage_name}' MCP {mcp_counter} missing details"
                    details = actual_interaction['details']
                    
                    assert details['success'] == expected_interaction['success'], \
                        f"Stage '{stage_name}' MCP {mcp_counter} success mismatch"
                    
                    assert details['communication_type'] == expected_interaction['communication_type'], \
                        f"Stage '{stage_name}' MCP {mcp_counter} communication_type mismatch"
                    
                    assert details['server_name'] == expected_interaction['server_name'], \
                        f"Stage '{stage_name}' MCP {mcp_counter} server_name mismatch"
                    
                    # Verify tool name for tool_call interactions
                    if expected_interaction['communication_type'] == 'tool_call':
                        assert details['tool_name'] == expected_interaction['tool_name'], \
                            f"Stage '{stage_name}' MCP {mcp_counter} tool_name mismatch"
                    
                    # Verify tool_list has available_tools
                    elif expected_interaction['communication_type'] == 'tool_list':
                        assert 'available_tools' in details, \
                            f"Stage '{stage_name}' MCP {mcp_counter} tool_list missing available_tools"
                        assert len(details['available_tools']) > 0, \
                            f"Stage '{stage_name}' MCP {mcp_counter} tool_list has no available_tools"
            
            print(f"    ✅ Stage '{stage_name}': Complete interaction flow verified ({len(llm_interactions)} LLM, {len(mcp_interactions)} MCP)")
        
        print("  ✅ Complete interaction flow verified for all stages")
