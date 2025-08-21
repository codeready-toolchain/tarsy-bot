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
        
        # 1. Mock external runbook HTTP calls
        async def mock_runbook_get(url, **kwargs):
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "# Mock Runbook\nTest runbook content"
            mock_response.raise_for_status = Mock()
            return mock_response
        
        # Store interactions by stage for precise verification
        stage_interactions = {
            'data-collection': {'llm': [], 'mcp': []},
            'verification': {'llm': [], 'mcp': []},
            'analysis': {'llm': [], 'mcp': []}
        }
        current_stage = 'data-collection'  # Start with first stage
        
        # Store ALL interactions for total count verification  
        all_llm_interactions = []
        all_mcp_interactions = []
        
        # 2. Mock external LLM API calls with realistic ReAct responses
        async def mock_llm_generate(*args, **kwargs):
            nonlocal current_stage
            
            # Store all interactions in order
            request_str = str(kwargs.get('messages', args[0] if args else ''))
            interaction_data = {
                'request': request_str,
                'response': None  # Will be filled below
            }
            all_llm_interactions.append(interaction_data)
            
            # Update stage based on total interaction counts (deterministic)
            total_llm_interactions = len(all_llm_interactions)
            
            # Determine current stage based on exact interaction counts
            if total_llm_interactions <= 3:
                current_stage = 'data-collection'
            elif total_llm_interactions <= 5:  # 3 + 2
                current_stage = 'verification'
            else:  # 6+ (3 + 2 + 1+)
                current_stage = 'analysis'
            
            # Store interaction for current stage
            stage_interactions[current_stage]['llm'].append(interaction_data)
            
            # Generate simplified, predictable responses
            response = None
            
            # Count interactions for current stage to determine response type
            current_stage_llm_count = len(stage_interactions[current_stage]['llm'])
            
            if current_stage == 'data-collection':
                if current_stage_llm_count == 1:  # First LLM call - use first tool
                    response = """Thought: I need to get namespace information first.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}"""
                elif current_stage_llm_count == 2:  # Second LLM call - use second tool
                    response = """Action: kubernetes-server.kubectl_describe  
Action Input: {"resource": "namespace", "name": "stuck-namespace"}"""
                else:  # Third LLM call - final analysis
                    response = """Final Answer: Data collection completed. Found namespace 'stuck-namespace' in Terminating state with finalizers blocking deletion."""
            
            elif current_stage == 'verification':
                if current_stage_llm_count == 1:  # First LLM call - use tool
                    response = """Thought: I need to verify the namespace status.
Action: kubernetes-server.kubectl_get
Action Input: {"resource": "namespaces", "name": "stuck-namespace"}"""
                else:  # Second LLM call - final analysis
                    response = """Final Answer: Verification completed. Root cause identified: namespace stuck due to finalizers preventing deletion."""
            
            elif current_stage == 'analysis':
                # Only one LLM call - just analysis, no tools
                response = """Based on previous stages, the namespace is stuck due to finalizers. 
## Recommended Actions
1. Remove finalizers to allow deletion
"""
            
            else:
                # Fallback for any other prompts
                response = "Final Answer: Analysis completed successfully."
            
            # Store the response in the latest interaction
            if all_llm_interactions:
                all_llm_interactions[-1]['response'] = response
            
            return response
        
        # 3. Mock external MCP server calls with realistic Kubernetes data
        async def mock_mcp_call_tool(*args, **kwargs):
            tool_name = kwargs.get('name', args[1] if len(args) > 1 else 'unknown')
            tool_arguments = kwargs.get('arguments', args[2] if len(args) > 2 else {})
            
            # Capture MCP interaction
            mcp_interaction = {
                'tool_name': tool_name,
                'arguments': tool_arguments,
                'response': None  # Will be filled below
            }
            all_mcp_interactions.append(mcp_interaction)
            
            # Store interaction for current stage
            stage_interactions[current_stage]['mcp'].append(mcp_interaction)
            
            # Simplified MCP tool responses
            response = None
            if tool_name == 'kubectl_get':
                resource = tool_arguments.get('resource', 'pods')
                name = tool_arguments.get('name', '')
                
                if resource == 'namespaces' and name == 'stuck-namespace':
                    response = {
                        "content": [
                            {
                                "type": "text",
                                "text": 'stuck-namespace   Terminating   45m'
                            }
                        ]
                    }
                else:
                    response = {
                        "content": [
                            {
                                "type": "text", 
                                "text": f"Mock kubectl get {resource} response"
                            }
                        ]
                    }
            
            elif tool_name == 'kubectl_describe':
                resource = tool_arguments.get('resource', '')
                name = tool_arguments.get('name', '')
                
                if resource == 'namespace' and name == 'stuck-namespace':
                    response = {
                        "content": [
                            {
                                "type": "text",
                                "text": """Name:         stuck-namespace
Status:       Terminating
Finalizers:   kubernetes.io/pv-protection"""
                            }
                        ]
                    }
                else:
                    response = {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Mock kubectl describe {resource} {name} response"
                            }
                        ]
                    }
            
            else:
                response = {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Mock response for tool: {tool_name}"
                        }
                    ]
                }
            
            # Store the response in the latest MCP interaction
            if all_mcp_interactions:
                all_mcp_interactions[-1]['response'] = response
            
            return response
        
        # Mock MCP client list_tools with correct format expected by BaseAgent
        async def mock_mcp_list_tools(*args, **kwargs):
            """Mock MCP client list_tools - returns server_name -> list of tools format."""
            
            # Record this list_tools call as an MCP interaction
            list_tools_interaction = {
                'tool_name': 'list_tools',
                'server_name': kwargs.get('server_name', 'kubernetes-server'),
                'arguments': {},
                'response': None  # Will be filled below
            }
            all_mcp_interactions.append(list_tools_interaction)
            
            # Store interaction for current stage
            stage_interactions[current_stage]['mcp'].append(list_tools_interaction)
            
            # BaseAgent calls: server_tools = await self.mcp_client.list_tools(...)
            # Then accesses: server_tools[server_name] to get list of tools
            response = {
                "kubernetes-server": [
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
            }
            
            # Store the response in our recorded interaction
            if all_mcp_interactions:
                all_mcp_interactions[-1]['response'] = response
            
            return response
        
        # Apply ONLY external mocks - let everything else be real
        with patch('httpx.AsyncClient.get', side_effect=mock_runbook_get), \
             patch('tarsy.integrations.llm.client.LLMManager.generate_response', side_effect=mock_llm_generate), \
             patch('tarsy.integrations.mcp.client.MCPClient.call_tool', side_effect=mock_mcp_call_tool), \
             patch('tarsy.integrations.mcp.client.MCPClient.list_tools', side_effect=mock_mcp_list_tools), \
             patch('tarsy.integrations.mcp.client.MCPClient.initialize', new_callable=AsyncMock):
            
            print("🔧 Using the real AlertService from the app...")
            # Use the actual AlertService from the app - no mocking of internal services!
            
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
            await self._verify_stage_execution_details(stages)
            await self._verify_processing_flow(detail_data)
            
            # DEBUG: Compare API interactions vs our recorded interactions
            await self._debug_interaction_comparison(stages, stage_interactions, all_llm_interactions, all_mcp_interactions)
            
            await self._verify_stage_interactions(stage_interactions)
            await self._verify_total_interactions(all_llm_interactions, all_mcp_interactions)
            
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

    async def _verify_stage_execution_details(self, stages):
        """Verify detailed stage execution data."""
        print("  ⚙️ Verifying stage execution details...")
        
        for i, stage in enumerate(stages):
            stage_name = stage['stage_name']
            
            # Verify timestamps
            if 'started_at_us' in stage and 'completed_at_us' in stage:
                started_at = stage['started_at_us']
                completed_at = stage['completed_at_us']
                if started_at and completed_at:
                    assert completed_at > started_at, \
                        f"Stage {stage_name} completed_at should be after started_at"
                    
                    duration_ms = (completed_at - started_at) / 1000
                    assert duration_ms >= 0, f"Stage {stage_name} has negative duration"
                    assert duration_ms < 10000, f"Stage {stage_name} took too long: {duration_ms}ms"
            
            # Verify execution results exist
            if 'stage_output' in stage and stage['stage_output']:
                stage_output = stage['stage_output']
                
                # Basic output structure validation
                if isinstance(stage_output, dict):
                    assert 'status' in stage_output, f"Stage {stage_name} output missing status"
                    assert 'agent_name' in stage_output, f"Stage {stage_name} output missing agent_name"
                    assert 'timestamp_us' in stage_output, f"Stage {stage_name} output missing timestamp"
                    
                    # Final analysis stage should have final_analysis content
                    if stage_name == 'analysis':
                        assert 'final_analysis' in stage_output, \
                            f"Final analysis stage missing final_analysis content"
                        assert stage_output['final_analysis'], \
                            f"Final analysis content is empty"
        
        print(f"    ✅ Stage execution details verified")

    async def _verify_processing_flow(self, session_data):
        """Verify overall processing flow and data integrity."""
        print("  🔄 Verifying processing flow...")
        
        # Verify session has final analysis
        assert 'final_analysis' in session_data, "Session missing final_analysis"
        assert session_data['final_analysis'], "Session final_analysis is empty"
        
        # Verify final analysis contains expected content structure
        final_analysis = session_data['final_analysis']
        expected_analysis_markers = ['Alert Analysis Report', 'Alert Type', 'Processing Chain']
        
        for marker in expected_analysis_markers:
            assert marker in final_analysis, \
                f"Final analysis missing expected content marker: {marker}"
        
        # Verify chain information is in final analysis
        assert 'kubernetes-namespace-terminating-chain' in final_analysis, \
            "Final analysis should mention the processing chain"
        
        # Verify processing metadata
        if 'processing_metadata' in session_data:
            metadata = session_data['processing_metadata']
            if 'total_stages' in metadata:
                assert metadata['total_stages'] == 3, \
                    f"Expected 3 total stages, got {metadata['total_stages']}"
        
        print(f"    ✅ Processing flow verified (final analysis: {len(final_analysis)} chars)")

    async def _verify_stage_interactions(self, stage_interactions):
        """Verify exact stage-specific interaction patterns."""
        print("  🎯 Verifying stage-specific interactions...")
        
        # Expected interaction counts per stage - based on typical ReAct iterations
        # data-collection and verification: use MCP servers (list_tools + kubectl_get calls)
        # analysis: NO MCP servers defined, only LLM processing for final analysis
        # Updated expectations including list_tools calls in our mock recordings
        expected_stage_counts = {
            'data-collection': {'llm': 3, 'mcp': 3},   # 1 list_tools + 2 tool calls, 3 LLM iterations
            'verification': {'llm': 2, 'mcp': 2},      # 1 list_tools + 1 tool call, 2 LLM iterations  
            'analysis': {'llm': 1, 'mcp': 0}           # Only final analysis, no MCP tools
        }
        
        for stage_name, interactions in stage_interactions.items():
            print(f"    🎭 Verifying stage '{stage_name}':")
            
            llm_count = len(interactions['llm'])
            mcp_count = len(interactions['mcp'])
            
            expected_llm = expected_stage_counts[stage_name]['llm']
            expected_mcp = expected_stage_counts[stage_name]['mcp']
            
            print(f"        📊 LLM interactions: {llm_count} (expected: {expected_llm})")
            print(f"        🔧 MCP interactions: {mcp_count} (expected: {expected_mcp})")
            
            # EXACT count verification per stage
            assert llm_count == expected_llm, f"Stage '{stage_name}': expected exactly {expected_llm} LLM interactions, got {llm_count}"
            assert mcp_count == expected_mcp, f"Stage '{stage_name}': expected exactly {expected_mcp} MCP interactions, got {mcp_count}"
            
            # Log MCP interaction types for debugging (list_tools happens during discovery, not execution)
            if mcp_count > 0:
                first_mcp = interactions['mcp'][0]
                print(f"        📋 First MCP interaction: {first_mcp['tool_name']}")
                print(f"        ✅ MCP interactions captured correctly (tool discovery separate from execution)")
            elif expected_mcp == 0:
                print(f"        ✅ No MCP interactions expected (stage has no MCP servers)")
            else:
                print(f"        ⚠️ Expected MCP interactions but found none")
            
            # Verify last LLM interaction has exact expected strings
            if llm_count > 0:
                last_llm = interactions['llm'][-1]
                await self._verify_last_llm_interaction(stage_name, last_llm)
            
            print(f"        ✅ Stage '{stage_name}' verification completed")
        
        print(f"    ✅ All stage interactions verified")

    async def _verify_total_interactions(self, all_llm_interactions, all_mcp_interactions):
        """Verify total interaction counts match expectations."""
        print("  📊 Verifying total interaction counts...")
        
        llm_total = len(all_llm_interactions)
        mcp_total = len(all_mcp_interactions)
        
        expected_llm_total = 6  # 3 + 2 + 1
        expected_mcp_total = 5  # 3 + 2 + 0 (now including list_tools calls)
        
        print(f"    📊 Total LLM interactions: {llm_total} (expected: {expected_llm_total})")
        print(f"    🔧 Total MCP interactions: {mcp_total} (expected: {expected_mcp_total})")
        
        assert llm_total == expected_llm_total, f"Expected {expected_llm_total} total LLM interactions, got {llm_total}"
        assert mcp_total == expected_mcp_total, f"Expected {expected_mcp_total} total MCP interactions, got {mcp_total}"
        
        print(f"    ✅ Total interaction counts verified")

    async def _debug_interaction_comparison(self, stages, stage_interactions, all_llm_interactions, all_mcp_interactions):
        """DEBUG: Compare API returned interactions vs our mock recorded interactions."""
        print("  🐛 DEBUG: Comparing API interactions vs Mock recordings...")
        
        print("\n  📊 MOCK RECORDED INTERACTIONS:")
        print(f"    🤖 Total LLM (mock): {len(all_llm_interactions)}")
        print(f"    🔧 Total MCP (mock): {len(all_mcp_interactions)}")
        
        # Extract actual interactions from API response
        api_llm_total = 0
        api_mcp_total = 0
        
        print("\n  📊 API RETURNED INTERACTIONS:")
        for i, stage in enumerate(stages):
            stage_name = stage.get('stage_name', f'stage-{i}')
            
            # DEBUG: Print actual JSON structure to understand the real format
            print(f"    🎭 Stage '{stage_name}' - RAW FIELDS:")
            print(f"        Available keys: {list(stage.keys())}")
            
            # Try different possible field names
            api_llm_count = len(stage.get('llm_interactions', []))
            api_mcp_count = len(stage.get('mcp_communications', []))
            
            # Also check summary counts
            llm_count_summary = stage.get('llm_interaction_count', 0)
            mcp_count_summary = stage.get('mcp_communication_count', 0)
            total_count_summary = stage.get('total_interactions', 0)
            
            print(f"        🤖 LLM arrays: {api_llm_count}")
            print(f"        🔧 MCP arrays: {api_mcp_count}")
            print(f"        📊 LLM count: {llm_count_summary}")
            print(f"        📊 MCP count: {mcp_count_summary}")  
            print(f"        📊 Total count: {total_count_summary}")
            
            # Show what types of MCP interactions the API reports
            mcp_communications = stage.get('mcp_communications', [])
            if mcp_communications:
                print(f"        📋 MCP interaction types:")
                for mcp in mcp_communications:
                    comm_type = mcp.get('communication_type', 'unknown')
                    tool_name = mcp.get('tool_name', 'unknown')
                    print(f"          - {comm_type}: {tool_name}")
            
            # Use the count fields (which are computed from arrays) for totals
            api_llm_total += llm_count_summary
            api_mcp_total += mcp_count_summary
        
        print(f"\n  📊 COMPARISON SUMMARY:")
        print(f"    🤖 LLM - Mock: {len(all_llm_interactions)}, API: {api_llm_total}")
        print(f"    🔧 MCP - Mock: {len(all_mcp_interactions)}, API: {api_mcp_total}")
        
        # Check if list_tools is missing from API but present in mocks
        mock_list_tools_count = sum(1 for mcp in all_mcp_interactions if mcp.get('tool_name') == 'list_tools')
        print(f"    📋 list_tools in mocks: {mock_list_tools_count}")
        
        if mock_list_tools_count > 0 and api_mcp_total != len(all_mcp_interactions):
            print(f"    ⚠️  POTENTIAL BUG: list_tools calls missing from API response!")
            print(f"    ⚠️  This suggests the system is not properly reporting tool discovery interactions")

    async def _verify_last_llm_interaction(self, stage_name, last_llm_interaction):
        """Verify exact request and response strings for the last LLM interaction in each stage."""
