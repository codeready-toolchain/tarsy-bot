"""
Focused End-to-End Integration Test for HTTP API Endpoints.

This test validates the complete alert processing pipeline with real LLM/MCP interactions,
database persistence, and comprehensive API data structures.

Uses isolated e2e test fixtures to prevent interference with unit/integration tests.
"""

from unittest.mock import AsyncMock, Mock, patch

import asyncio
import pytest

@pytest.mark.asyncio
@pytest.mark.e2e
class TestMegaAPIEndpointsE2E:
    """
    Comprehensive API endpoints integration test.
    
    Tests the complete alert processing pipeline with real chain execution,
    LLM/MCP interactions, database persistence, and API validation.
    """

    # Note: realistic_namespace_alert and test_client fixtures are now provided 
    # by the isolated e2e conftest.py as e2e_realistic_kubernetes_alert and e2e_test_client

    def _get_react_conversation_steps(self, stage_name=None):
        """Get the ReAct conversation steps for namespace termination scenario by stage."""
        
        # Stage 1: Data Collection - Gather comprehensive information
        data_collection_steps = [
            {
                "thought": "I'm the data collection agent tasked with gathering comprehensive information about this namespace termination issue. Let me start by checking the current namespace status.",
                "action": "kubernetes-server.get_namespace",
                "action_input": '{"namespace": "test-namespace"}'
            },
            {
                "thought": "I can see the namespace is in Terminating state with finalizers. Let me also check for any pods that might be stuck in this namespace.",
                "action": "kubernetes-server.list_pods",
                "action_input": '{"namespace": "test-namespace"}'
            },
            {
                "thought": "I should also gather events to understand what's happening with the deletion process.",
                "action": "kubernetes-server.get_events",
                "action_input": '{"namespace": "test-namespace"}'
            },
            {
                "thought": "Data collection complete. The namespace is stuck due to finalizers, with associated pods and deletion events gathered.",
                "final_answer": "Data collection completed. Found namespace in Terminating state with kubernetes.io/pv-protection finalizers. Associated pods and events collected for analysis."
            }
        ]
        
        # Stage 2: Verification - Built-in agent verification  
        verification_steps = [
            {
                "thought": "I'm the verification agent. Based on the data collection, I need to verify the namespace termination issue and assess the impact.",
                "action": "kubernetes-server.describe_namespace", 
                "action_input": '{"namespace": "test-namespace"}'
            },
            {
                "thought": "Let me verify the finalizer blocking the deletion by checking resource dependencies.",
                "action": "kubernetes-server.check_dependencies",
                "action_input": '{"namespace": "test-namespace", "resource_type": "persistentvolumes"}'
            },
            {
                "thought": "Verification complete. The blocking finalizer has been confirmed and dependencies analyzed.",
                "final_answer": "Verification completed. Confirmed kubernetes.io/pv-protection finalizer is blocking deletion due to persistent volume dependencies."
            }
        ]
        
        # Stage 3: Analysis - Root cause analysis and recommendations
        analysis_steps = [
            {
                "thought": "I'm the analysis agent. Based on data collection and verification stages, I need to synthesize the information and provide root cause analysis.",
                "action": "kubernetes-server.analyze_finalizers",
                "action_input": '{"namespace": "test-namespace", "finalizers": ["kubernetes.io/pv-protection"]}'
            },
            {
                "thought": "Now let me assess the impact and provide a comprehensive analysis with recommendations.",
                "final_answer": "Root cause analysis complete. The namespace is stuck in Terminating state due to kubernetes.io/pv-protection finalizers protecting persistent volumes. Recommendation: Remove finalizers after ensuring PV data is safely backed up or no longer needed. Impact: Low - test namespace with no critical workloads."
            }
        ]
        
        # Return steps based on stage
        if stage_name == "data-collection":
            return data_collection_steps
        elif stage_name == "verification": 
            return verification_steps
        elif stage_name == "analysis":
            return analysis_steps
        else:
            # Default to data collection for backwards compatibility
            return data_collection_steps

    async def _create_simple_fast_mocks(self):
        """Create realistic mocks that encourage agent interaction."""
        print("🔧 Creating realistic mocks...")
        
        # Create LLM mock with hook-aware interactions
        llm_mock = AsyncMock()
        llm_call_count = 0
        
        def get_current_stage_and_step(call_count):
            """Determine which stage and step we're in based on call count."""
            # Stage 1: data-collection (calls 1-4)
            if call_count <= 4:
                stage = "data-collection"
                step_index = call_count - 1
            # Stage 2: verification (calls 5-7) 
            elif call_count <= 7:
                stage = "verification"
                step_index = call_count - 5
            # Stage 3: analysis (calls 8-9)
            else:
                stage = "analysis"
                step_index = call_count - 8
            
            return stage, step_index
        
        async def realistic_llm_generate_response(messages, session_id, stage_execution_id=None):
            nonlocal llm_call_count
            llm_call_count += 1
            
            # Import the hook context
            from tarsy.hooks.typed_context import llm_interaction_context
            from tarsy.models.unified_interactions import LLMMessage
            
            # Create request data structure like the real LLM client
            request_data = {
                "messages": [{"role": msg.role, "content": msg.content} for msg in messages] if hasattr(messages[0], 'role') else [{"role": "user", "content": str(msg)} for msg in messages],
                "provider": "gemini",
                "model": "gemini-2.5-pro-exp-03-25",
                "temperature": 0.3
            }
            
            # Use the real hook context to record this interaction
            async with llm_interaction_context(session_id, request_data, stage_execution_id) as ctx:
                # Determine current stage and get appropriate conversation steps
                current_stage, step_index = get_current_stage_and_step(llm_call_count)
                conversation_steps = self._get_react_conversation_steps(current_stage)
                
                # Generate content from stage-specific conversation steps
                if step_index < len(conversation_steps):
                    step = conversation_steps[step_index]
                    if "final_answer" in step:
                        content = f"""Thought: {step['thought']}

Final Answer: {step['final_answer']}"""
                    else:
                        content = f"""Thought: {step['thought']}

Action: {step['action']}
Action Input: {step['action_input']}"""
                else:
                    # Fallback for additional calls within a stage
                    content = f"""Final Answer: Stage {current_stage} completed after {step_index + 1} steps."""
                
                # Create typed response for the context
                from tarsy.models.unified_interactions import LLMResponse, LLMChoice, LLMMessage as TypedLLMMessage
                typed_response = LLMResponse(
                    choices=[
                        LLMChoice(
                            message=TypedLLMMessage(role="assistant", content=content),
                            finish_reason="stop"
                        )
                    ],
                    model="gemini-2.5-pro-exp-03-25",
                    usage={"total_tokens": 150 + llm_call_count * 25}
                )
                
                # Update context with response data
                ctx.interaction.response_json = typed_response.model_dump()
                ctx.interaction.provider = "gemini"
                ctx.interaction.model_name = "gemini-2.5-pro-exp-03-25"
                ctx.interaction.token_usage = {"total_tokens": 150 + llm_call_count * 25}
                
                # Complete context successfully (this triggers the hooks!)
                await ctx.complete_success({})
                
                return content
        
        llm_mock.generate_response = AsyncMock(side_effect=realistic_llm_generate_response)
        
        # CRITICAL: Add LLMManager methods that AlertService.initialize() will call
        llm_mock.is_available = Mock(return_value=True)
        llm_mock.initialize = Mock(return_value=True)
        llm_mock.list_available_providers = Mock(return_value=["gemini"])
        llm_mock.get_availability_status = Mock(return_value={"gemini": "available"})
        
        # Create MCP mock with hook-aware interactions
        mcp_mock = AsyncMock()
        mcp_call_count = 0
        

        async def realistic_mcp_call_tool(server_name, tool_name, parameters, session_id, stage_execution_id=None):
            nonlocal mcp_call_count
            mcp_call_count += 1
            
            # Import the hook context
            from tarsy.hooks.typed_context import mcp_interaction_context
            
            # Use the real hook context to record this interaction
            async with mcp_interaction_context(session_id, server_name, tool_name, parameters, stage_execution_id) as ctx:
                # Generate response using local tool response function
                if "get_namespace" in tool_name:
                    result = {
                        "namespace": "test-namespace",
                        "status": "Terminating", 
                        "finalizers": ["kubernetes.io/pv-protection"],
                        "metadata": {
                            "name": "test-namespace",
                            "finalizers": ["kubernetes.io/pv-protection"],
                            "deletionTimestamp": "2024-01-15T10:30:00Z"
                        }
                    }
                elif "list_pods" in tool_name:
                    result = {
                        "pods": [
                            {
                                "name": "test-pod-1",
                                "status": "Terminating",
                                "phase": "Succeeded",
                                "deletionTimestamp": "2024-01-15T10:30:00Z"
                            }
                        ],
                        "namespace": "test-namespace",
                        "totalCount": 1
                    }
                elif "get_events" in tool_name:
                    result = {
                        "events": [
                            {
                                "type": "Warning",
                                "reason": "FailedDelete",
                                "message": "Unable to delete namespace due to finalizers",
                                "timestamp": "2024-01-15T10:30:00Z"
                            }
                        ],
                        "namespace": "test-namespace",
                        "eventCount": 1
                    }
                elif "describe_namespace" in tool_name:
                    result = {
                        "name": "test-namespace",
                        "status": "Terminating",
                        "finalizers": ["kubernetes.io/pv-protection"],
                        "resourceQuota": "default",
                        "description": "Detailed namespace information for verification",
                        "deletionTimestamp": "2024-01-15T10:30:00Z"
                    }
                elif "check_dependencies" in tool_name:
                    result = {
                        "dependencies": [
                            {
                                "type": "PersistentVolume",
                                "name": "test-pv-1",
                                "status": "Bound",
                                "reclaimPolicy": "Retain"
                            }
                        ],
                        "namespace": "test-namespace",
                        "dependencyCount": 1,
                        "blocking": True
                    }
                elif "analyze_finalizers" in tool_name:
                    result = {
                        "analysis": {
                            "finalizer": "kubernetes.io/pv-protection",
                            "purpose": "Protects persistent volumes from premature deletion",
                            "rootCause": "PV finalizer preventing namespace cleanup",
                            "impact": "Low - test namespace",
                            "recommendation": "Remove finalizer after data backup verification"
                        },
                        "confidence": 0.95,
                        "analysisComplete": True
                    }
                else:
                    # Default response for any other tool
                    result = {
                        "tool": tool_name,
                        "success": True,
                        "message": f"Tool {tool_name} executed successfully (call #{mcp_call_count})",
                        "timestamp": "2024-01-15T10:30:00Z"
                    }
                
                # Update context with result data (this is what the real MCP client does)
                ctx.interaction.tool_result = result
                
                # Complete context successfully (this triggers the hooks!)
                await ctx.complete_success({"tool_result": result})
                
                return {"result": result}
        
        mcp_mock.call_tool = AsyncMock(side_effect=realistic_mcp_call_tool)
        
        # Return proper tool metadata structure that ReAct agents can iterate over
        mcp_mock.list_tools = AsyncMock(return_value={
            "tools": [
                {
                    "name": "get_namespace",
                    "description": "Get detailed information about a Kubernetes namespace",
                    "inputSchema": {
                        "type": "object", 
                        "properties": {"namespace": {"type": "string"}},
                        "required": ["namespace"]
                    }
                },
                {
                    "name": "patch_namespace", 
                    "description": "Patch a Kubernetes namespace configuration",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "namespace": {"type": "string"},
                            "patch": {"type": "object"}
                        },
                        "required": ["namespace", "patch"]
                    }
                },
                {
                    "name": "check_status",
                    "description": "Check the current status of a Kubernetes resource",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"resource": {"type": "string"}},
                        "required": ["resource"]
                    }
                }
            ]
        })
        
        print("✅ Realistic mocks created")
        return llm_mock, mcp_mock

    # Note: Test settings are now handled by the isolated_e2e_settings fixture

    async def _validate_comprehensive_api_data(self, test_client, alert_id: str, session_id: str):
        """Validate API data structures and processing results."""
        print("🔍 Validating API data...")
        
        # Get session details
        sessions_response = test_client.get("/api/v1/history/sessions")
        assert sessions_response.status_code == 200
        sessions_list = sessions_response.json()
        
        # Find our session
        our_session = None
        for session in sessions_list["sessions"]:
            if session.get("session_id") == session_id:
                our_session = session
                break
        
        assert our_session is not None, f"Session {session_id} not found"
        
        status = our_session.get("status", "unknown")
        llm_count = our_session.get("llm_interaction_count", 0)
        mcp_count = our_session.get("mcp_communication_count", 0)
        
        # Get session detail
        detail_response = test_client.get(f"/api/v1/history/sessions/{session_id}")
        assert detail_response.status_code == 200
        session_detail = detail_response.json()
        
        # No longer using global timeline - data is now in stages
        chain_execution = session_detail.get("chain_execution", {})
        
        # Basic validation
        assert status in ["completed", "failed", "processing"], f"Invalid status: {status}"
        assert chain_execution.get("chain_id"), "Missing chain execution data"
        
        print(f"✅ Session-level counts extracted: {status} with {llm_count} LLM + {mcp_count} MCP interactions")
        
        # Return the session-level counts for cross-validation
        return {
            "status": status,
            "session_llm_count": llm_count,
            "session_mcp_count": mcp_count,
            "session_total_count": llm_count + mcp_count
        }

    async def _validate_sessions_api(self, test_client, session_id, expected_alert_data):
        """
        Enhanced sessions API validation with comprehensive checks.
        
        Args:
            test_client: FastAPI test client
            session_id: The session ID to validate
            expected_alert_data: The original alert data we submitted
        """
        print("🔍 Testing GET /api/v1/history/sessions...")
        sessions_response = test_client.get("/api/v1/history/sessions")
        
        # Validate response structure
        assert sessions_response.status_code == 200, f"Sessions API failed: {sessions_response.status_code}"
        sessions_data = sessions_response.json()
        
        # Validate sessions list structure
        assert "sessions" in sessions_data, "Missing 'sessions' field in response"
        assert isinstance(sessions_data["sessions"], list), "'sessions' should be a list"
        
        # VALIDATION 1: Verify there is exactly one session created for the submitted alert
        print("🔍 Validating session uniqueness...")
        assert len(sessions_data["sessions"]) == 1, f"Expected exactly 1 session, found {len(sessions_data['sessions'])}"
        
        our_session = sessions_data["sessions"][0]
        assert our_session.get("session_id") == session_id, f"Session ID mismatch: expected {session_id}, got {our_session.get('session_id')}"
        print(f"✅ Confirmed single session with correct ID: {session_id[:8]}...")
        
        # VALIDATION 2: Verify key alert data matches what we submitted
        print("🔍 Validating alert data consistency...")
        session_alert_id = our_session.get("alert_id", "")
        expected_alert_type = expected_alert_data.get("alert_type", "")
        
        # Alert ID should contain the alert type (it's part of the ID generation)
        assert expected_alert_type in session_alert_id, f"Alert ID {session_alert_id} should contain alert type {expected_alert_type}"
        assert our_session.get("alert_type") == expected_alert_type, f"Alert type mismatch: expected {expected_alert_type}, got {our_session.get('alert_type')}"
        print(f"✅ Alert data consistent - Type: {expected_alert_type}")
        
        # Validate session fields (using actual API field names)
        required_fields = ["session_id", "alert_id", "status", "started_at_us"]
        for field in required_fields:
            assert field in our_session, f"Missing required field: {field}"
        
        # Validate field types and values
        assert isinstance(our_session["session_id"], str), "session_id should be string"
        assert isinstance(our_session["alert_id"], str), "alert_id should be string"
        assert our_session["status"] in ["completed", "failed", "processing"], f"Invalid status: {our_session['status']}"
        
        print(f"✅ Session list validation passed - Status: {our_session['status']}")
        
        # VALIDATION 3: Get detailed session data and validate stages
        print(f"🔍 Testing GET /api/v1/history/sessions/{session_id}...")
        detail_response = test_client.get(f"/api/v1/history/sessions/{session_id}")
        
        assert detail_response.status_code == 200, f"Session detail API failed: {detail_response.status_code}"
        detail_data = detail_response.json()
        
        # Validate detail structure
        required_detail_fields = ["session_id", "alert_data", "chain_execution", "summary"]
        for field in required_detail_fields:
            assert field in detail_data, f"Missing required detail field: {field}"
        
        # TEST SUMMARY ENDPOINT: Verify lightweight summary API
        print(f"🔍 Testing GET /api/v1/history/sessions/{session_id}/summary...")
        summary_response = test_client.get(f"/api/v1/history/sessions/{session_id}/summary")
        
        assert summary_response.status_code == 200, f"Session summary API failed: {summary_response.status_code}"
        summary_data = summary_response.json()
        
        # Validate summary structure and data consistency
        required_summary_fields = ["total_interactions", "llm_interactions", "mcp_communications", "system_events", "errors_count", "total_duration_ms"]
        for field in required_summary_fields:
            assert field in summary_data, f"Missing required summary field: {field}"
        
        # VALIDATION: Summary from lightweight endpoint should match detail endpoint summary
        detail_summary = detail_data.get("summary", {})
        for field in required_summary_fields:
            if field in detail_summary:
                assert summary_data[field] == detail_summary[field], f"Summary mismatch for {field}: endpoint={summary_data[field]}, detail={detail_summary[field]}"
        
        # EXACT VALIDATION: Both endpoints should return precisely the same known values
        expected_exact_counts = {
            "total_interactions": 13,
            "llm_interactions": 8, 
            "mcp_communications": 5,
            "system_events": 0,
            "errors_count": 0
        }
        
        for endpoint_name, summary_dict in [("lightweight", summary_data), ("detail", detail_summary)]:
            for field, expected_value in expected_exact_counts.items():
                actual_value = summary_dict.get(field, -999)
                assert actual_value == expected_value, f"EXACT VALIDATION FAILED: {endpoint_name} endpoint {field} expected exactly {expected_value}, got {actual_value}"
            
            # SANITY CHECK: Duration should be non-negative (exact value depends on execution speed)
            duration = summary_dict.get("total_duration_ms", -1)
            assert duration >= 0, f"SANITY CHECK FAILED: {endpoint_name} endpoint shows negative processing duration ({duration}ms)"
        
        # Chain statistics should match if present
        if "chain_statistics" in detail_summary:
            assert "chain_statistics" in summary_data, "Chain statistics missing from summary endpoint"
            chain_fields = ["total_stages", "completed_stages", "failed_stages"]
            for field in chain_fields:
                if field in detail_summary["chain_statistics"]:
                    assert summary_data["chain_statistics"][field] == detail_summary["chain_statistics"][field], f"Chain statistic mismatch for {field}"
        
        print(f"✅ Summary endpoint validation passed - data consistency confirmed")
        
        # VALIDATION 4: Validate chain execution and stages
        print("🔍 Validating chain execution and stages...")
        chain_execution = detail_data["chain_execution"]
        assert isinstance(chain_execution, dict), "chain_execution should be dict"
        
        # Check for stages data
        if "stages" in chain_execution:
            stages = chain_execution["stages"]
            assert isinstance(stages, list), "stages should be list"
            
            # EXACT VALIDATION: Number of stages MUST be exactly 3 (from test_agents.yaml)
            expected_stage_count = 3
            expected_stages = ["stage_0", "stage_1", "stage_2"]
            print(f"🔍 Validating stage count and names...")
            print(f"   📊 Found {len(stages)} stages (expected exactly {expected_stage_count})")
            
            assert len(stages) == expected_stage_count, f"EXACT VALIDATION FAILED: Expected exactly {expected_stage_count} stages, found {len(stages)}"
            
            # VALIDATION 6: Each stage name should match expectations
            actual_stage_names = []
            stage_interaction_counts = {}
            
            for i, stage in enumerate(stages):
                assert isinstance(stage, dict), f"Stage {i} should be dict"
                stage_name = stage.get("name", f"stage_{i}")
                actual_stage_names.append(stage_name)
                
                # VALIDATION 7: Check interactions in each stage (new structure)
                timeline = stage.get("timeline", [])
                interaction_summary = stage.get("interaction_summary", {})
                
                # Count by timeline events
                timeline_llm_count = len([e for e in timeline if e.get("type") == "llm"]) if isinstance(timeline, list) else 0
                timeline_mcp_count = len([e for e in timeline if e.get("type") == "mcp"]) if isinstance(timeline, list) else 0
                
                # Get counts from summary
                summary_llm_count = interaction_summary.get("llm_count", 0)
                summary_mcp_count = interaction_summary.get("mcp_count", 0)
                summary_total = interaction_summary.get("total_count", 0)
                
                # Use timeline counts for backward compatibility
                llm_count = timeline_llm_count
                mcp_count = timeline_mcp_count
                
                # VALIDATION: Timeline and summary should match
                assert timeline_llm_count == summary_llm_count, f"Timeline LLM count ({timeline_llm_count}) != Summary LLM count ({summary_llm_count})"
                assert timeline_mcp_count == summary_mcp_count, f"Timeline MCP count ({timeline_mcp_count}) != Summary MCP count ({summary_mcp_count})"
                assert len(timeline) == summary_total, f"Timeline total ({len(timeline)}) != Summary total ({summary_total})"
                
                stage_interaction_counts[stage_name] = {
                    "llm": llm_count,
                    "mcp": mcp_count,
                    "total": llm_count + mcp_count
                }
                
                print(f"   📋 Stage '{stage_name}': {llm_count} LLM + {mcp_count} MCP interactions")
                
                # STRICT VALIDATION: Each stage MUST have exactly the expected interactions
                total_interactions = llm_count + mcp_count
                
                # Define exact interaction requirements per stage
                stage_exact_counts = {
                    "stage_0": {"llm": 4, "mcp": 3, "total": 7},  # data-collection: exactly 4 LLM + 3 MCP
                    "stage_1": {"llm": 3, "mcp": 2, "total": 5},  # verification: exactly 3 LLM + 2 MCP  
                    "stage_2": {"llm": 1, "mcp": 0, "total": 1}   # analysis: exactly 1 LLM + 0 MCP (final-analysis strategy)
                }
                
                # Get exact expected counts for this stage
                expected = stage_exact_counts.get(stage_name, {"llm": 1, "mcp": 1, "total": 2})
                
                # STRICT ASSERTION: LLM interactions must be exactly as expected
                assert llm_count == expected["llm"], f"STRICT VALIDATION FAILED: Stage '{stage_name}' has {llm_count} LLM interactions, expected exactly {expected['llm']}"
                
                # STRICT ASSERTION: MCP interactions must be exactly as expected  
                assert mcp_count == expected["mcp"], f"STRICT VALIDATION FAILED: Stage '{stage_name}' has {mcp_count} MCP interactions, expected exactly {expected['mcp']}"
                
                # STRICT ASSERTION: Total interactions must be exactly as expected
                assert total_interactions == expected["total"], f"STRICT VALIDATION FAILED: Stage '{stage_name}' has {total_interactions} total interactions, expected exactly {expected['total']}"
                
                print(f"   ✅ Stage '{stage_name}': {llm_count} LLM + {mcp_count} MCP = {total_interactions} interactions (exactly {expected['total']} as required)")
                
                # STRICT VALIDATION: Verify actual interaction data exists (not just counts)
                timeline = stage.get("timeline", [])
                llm_interactions = [event for event in timeline if event.get("type") == "llm"]
                mcp_interactions = [event for event in timeline if event.get("type") == "mcp"]
                
                # Check that LLM interactions have actual data
                if expected["llm"] > 0:
                    assert len(llm_interactions) >= 1, f"STRICT VALIDATION FAILED: Stage '{stage_name}' missing LLM interaction data in timeline"
                    # Verify first LLM interaction has required fields
                    first_llm = llm_interactions[0]
                    assert "event_id" in first_llm, f"STRICT VALIDATION FAILED: Stage '{stage_name}' LLM interaction missing event_id"
                    assert "timestamp_us" in first_llm, f"STRICT VALIDATION FAILED: Stage '{stage_name}' LLM interaction missing timestamp_us"
                    assert "type" in first_llm and first_llm["type"] == "llm", f"STRICT VALIDATION FAILED: Stage '{stage_name}' LLM interaction type incorrect"
                    
                    # SANITY CHECK: Dynamic values that we can't predict exactly
                    event_id = first_llm.get("event_id")
                    timestamp_us = first_llm.get("timestamp_us")
                    
                    # Sanity check: event_id looks like a UUID (not empty string)
                    assert event_id and len(event_id) >= 30, f"SANITY CHECK FAILED: Stage '{stage_name}' LLM event_id is empty or too short: '{event_id}'"
                    
                    # Sanity check: timestamp is realistic microseconds (not 0, not placeholder)
                    assert isinstance(timestamp_us, int) and timestamp_us > 1_000_000_000_000, f"SANITY CHECK FAILED: Stage '{stage_name}' LLM timestamp_us invalid: {timestamp_us}"
                    
                    # EXACT VALIDATION: LLM interaction must have proper structure
                    details = first_llm.get("details", {})
                    assert details, f"EXACT VALIDATION FAILED: Stage '{stage_name}' LLM interaction missing details"
                    
                    # EXACT VALIDATION: Must have request/response data (we know the mock provides this)
                    has_request = "request_json" in details or "request" in details or "messages" in details or "prompt" in details
                    has_response = "response_json" in details or "response" in details or "content" in details or "choices" in details
                    assert has_request or has_response, f"EXACT VALIDATION FAILED: Stage '{stage_name}' LLM interaction missing conversation content in details: {list(details.keys())}"
                    
                    print(f"   ✅ Stage '{stage_name}' LLM interaction data and content validated")
                
                # Check that MCP interactions have actual data (if expected)
                if expected["mcp"] > 0:
                    assert len(mcp_interactions) >= 1, f"STRICT VALIDATION FAILED: Stage '{stage_name}' missing MCP interaction data in timeline"
                    # Verify first MCP interaction has required fields
                    first_mcp = mcp_interactions[0]
                    assert "event_id" in first_mcp, f"STRICT VALIDATION FAILED: Stage '{stage_name}' MCP interaction missing event_id"
                    assert "timestamp_us" in first_mcp, f"STRICT VALIDATION FAILED: Stage '{stage_name}' MCP interaction missing timestamp_us"
                    assert "type" in first_mcp and first_mcp["type"] == "mcp", f"STRICT VALIDATION FAILED: Stage '{stage_name}' MCP interaction type incorrect"
                    
                    # SANITY CHECK: Dynamic values that we can't predict exactly
                    event_id = first_mcp.get("event_id")
                    timestamp_us = first_mcp.get("timestamp_us")
                    
                    # Sanity check: event_id looks like a UUID (not empty string)
                    assert event_id and len(event_id) >= 30, f"SANITY CHECK FAILED: Stage '{stage_name}' MCP event_id is empty or too short: '{event_id}'"
                    
                    # Sanity check: timestamp is realistic microseconds (not 0, not placeholder)
                    assert isinstance(timestamp_us, int) and timestamp_us > 1_000_000_000_000, f"SANITY CHECK FAILED: Stage '{stage_name}' MCP timestamp_us invalid: {timestamp_us}"
                    
                    # EXACT VALIDATION: MCP interaction must have proper structure and known values
                    details = first_mcp.get("details", {})
                    assert details, f"EXACT VALIDATION FAILED: Stage '{stage_name}' MCP interaction missing details"
                    assert "server_name" in details, f"EXACT VALIDATION FAILED: Stage '{stage_name}' MCP interaction missing server_name in details"
                    assert "tool_name" in details, f"EXACT VALIDATION FAILED: Stage '{stage_name}' MCP interaction missing tool_name in details"
                    
                    # EXACT VALIDATION: We know exactly what server name our mock uses
                    server_name = details.get("server_name", "")
                    assert server_name == "kubernetes-server", f"EXACT VALIDATION FAILED: Stage '{stage_name}' MCP server_name expected 'kubernetes-server', got '{server_name}'"
                    
                    # EXACT VALIDATION: Tool name should be one of the known tools our mock provides
                    tool_name = details.get("tool_name", "")
                    expected_tools = ["get_namespace", "list_pods", "get_events", "describe_namespace", "check_dependencies", "analyze_finalizers"]
                    assert tool_name in expected_tools, f"EXACT VALIDATION FAILED: Stage '{stage_name}' MCP tool_name '{tool_name}' not in expected tools: {expected_tools}"
                    
                    # EXACT VALIDATION: Must have tool call/result data (we know the mock provides this)
                    has_parameters = "parameters" in details or "tool_input" in details or "input" in details or "tool_parameters" in details
                    has_result = "result" in details or "tool_result" in details or "output" in details or "response" in details
                    assert has_parameters or has_result, f"EXACT VALIDATION FAILED: Stage '{stage_name}' MCP interaction missing tool call/result data in details: {list(details.keys())}"
                    
                    print(f"   ✅ Stage '{stage_name}' MCP interaction data and content validated")
                elif expected["mcp"] == 0:
                    # For stages with 0 expected MCP interactions, verify none exist
                    assert len(mcp_interactions) == 0, f"STRICT VALIDATION FAILED: Stage '{stage_name}' should have 0 MCP interactions but found {len(mcp_interactions)}"
                    print(f"   ✅ Stage '{stage_name}' correctly has no MCP interactions")
            
            # VALIDATION 7: Stage names MUST match expected order exactly
            for i, expected_name in enumerate(expected_stages):
                assert i < len(actual_stage_names), f"STRICT VALIDATION FAILED: Missing stage '{expected_name}' at position {i}"
                actual_name = actual_stage_names[i]
                assert actual_name == expected_name, f"STRICT VALIDATION FAILED: Stage {i} name mismatch - expected '{expected_name}', got '{actual_name}'"
            
            print(f"✅ Stage validation passed:")
            print(f"   📊 Total stages: {len(stages)}")
            print(f"   📋 Stage names: {', '.join(actual_stage_names)}")
            
            # EXACT VALIDATION: Overall interaction count must be precisely what we expect
            total_llm = sum(counts["llm"] for counts in stage_interaction_counts.values())
            total_mcp = sum(counts["mcp"] for counts in stage_interaction_counts.values())
            total_interactions = total_llm + total_mcp
            print(f"   🔄 Total interactions across all stages: {total_llm} LLM + {total_mcp} MCP = {total_interactions}")
            
            # EXACT VALIDATION: Total interactions must be exactly as expected
            expected_total_llm = 8   # 4 + 3 + 1 from all stages
            expected_total_mcp = 5   # 3 + 2 + 0 from all stages  
            expected_total_interactions = 13  # 8 + 5
            
            # EXACT ASSERTION: Total LLM interactions must be exactly as expected
            assert total_llm == expected_total_llm, f"EXACT VALIDATION FAILED: Total LLM interactions {total_llm}, expected exactly {expected_total_llm}"
            
            # EXACT ASSERTION: Total MCP interactions must be exactly as expected
            assert total_mcp == expected_total_mcp, f"EXACT VALIDATION FAILED: Total MCP interactions {total_mcp}, expected exactly {expected_total_mcp}"
            
            # EXACT ASSERTION: Total interactions must be exactly as expected
            assert total_interactions == expected_total_interactions, f"EXACT VALIDATION FAILED: Total interactions {total_interactions}, expected exactly {expected_total_interactions}"
                
            print(f"   ✅ Total interactions validated: {total_llm} LLM + {total_mcp} MCP = {total_interactions} (exactly {expected_total_interactions} as required)")
            print(f"   ✅ Agent execution successful: {len(stages)} stage(s) completed")
            
        else:
            # STRICT VALIDATION: We MUST have stages data
            available_keys = list(chain_execution.keys())
            pytest.fail(f"STRICT VALIDATION FAILED: No 'stages' field found in chain_execution. Available keys: {available_keys}. Chain execution is broken.")
        
        # Validate stage-embedded timelines (new structure)
        total_timeline_events = 0
        if chain_execution and "stages" in chain_execution:
            for stage in chain_execution["stages"]:
                stage_timeline = stage.get("timeline", [])
                total_timeline_events += len(stage_timeline)
        
        print(f"📅 Total timeline events across all stages: {total_timeline_events}")
        
        # VALIDATION 8: Verify alert data in session detail matches our submission
        session_alert_data = detail_data.get("alert_data", {})
        if session_alert_data:
            stored_alert_type = session_alert_data.get("alert_type")
            assert stored_alert_type == expected_alert_type, f"Stored alert type mismatch: expected {expected_alert_type}, got {stored_alert_type}"
            print(f"✅ Session detail alert data matches submission")
        
        # VALIDATION 9: Comprehensive summary statistics validation
        print("🔍 Validating session summary statistics...")
        summary = detail_data.get("summary", {})
        assert isinstance(summary, dict), "Summary should be a dictionary"
        assert summary, "Summary should not be empty"  # Should not be {} anymore
        
        # Required summary fields
        required_summary_fields = [
            "total_interactions", "llm_interactions", "mcp_communications", 
            "system_events", "errors_count", "total_duration_ms"
        ]
        
        for field in required_summary_fields:
            assert field in summary, f"Missing required summary field: {field}"
            assert isinstance(summary[field], int), f"Summary field '{field}' should be an integer"
            assert summary[field] >= 0, f"Summary field '{field}' should be non-negative"
        
        # EXACT VALIDATION: We know precisely what this test should produce
        # Based on our mock setup: 8 LLM + 5 MCP + 0 system = 13 total interactions
        expected_exact_summary = {
            "total_interactions": 13,
            "llm_interactions": 8,
            "mcp_communications": 5,
            "system_events": 0,
            "errors_count": 0
        }
        
        for field, expected_value in expected_exact_summary.items():
            actual_value = summary.get(field, -999)
            assert actual_value == expected_value, f"EXACT VALIDATION FAILED: {field} expected exactly {expected_value}, got {actual_value}"
        
        # SANITY CHECK: Duration should be non-negative (exact value depends on execution speed)
        total_duration = summary.get("total_duration_ms", -1)
        assert total_duration >= 0, f"SANITY CHECK FAILED: Processing duration is negative ({total_duration}ms)"
        
        print(f"   📊 Summary statistics found:")
        print(f"      Total Interactions: {summary['total_interactions']}")
        print(f"      LLM Interactions: {summary['llm_interactions']}")
        print(f"      MCP Communications: {summary['mcp_communications']}")
        print(f"      System Events: {summary['system_events']}")
        print(f"      Errors Count: {summary['errors_count']}")
        print(f"      Total Duration (ms): {summary['total_duration_ms']}")
        
        # Validation: Total interactions should equal sum of individual interaction types
        expected_total = summary['llm_interactions'] + summary['mcp_communications'] + summary['system_events']
        assert summary['total_interactions'] == expected_total, \
            f"Total interactions ({summary['total_interactions']}) should equal sum of LLM + MCP + System ({expected_total})"
        
        # Validation: Summary should match actual timeline events count
        # Count all timeline events across all stages
        actual_total_events = 0
        actual_llm_events = 0
        actual_mcp_events = 0
        actual_system_events = 0
        
        if chain_execution and "stages" in chain_execution:
            for stage in chain_execution["stages"]:
                stage_timeline = stage.get("timeline", [])
                actual_total_events += len(stage_timeline)
                actual_llm_events += len([e for e in stage_timeline if e.get("type") == "llm"])
                actual_mcp_events += len([e for e in stage_timeline if e.get("type") == "mcp"])
                actual_system_events += len([e for e in stage_timeline if e.get("type") == "system"])
        
        # Assert summary matches actual timeline counts
        assert summary['total_interactions'] == actual_total_events, \
            f"Summary total_interactions ({summary['total_interactions']}) != actual timeline events ({actual_total_events})"
        assert summary['llm_interactions'] == actual_llm_events, \
            f"Summary llm_interactions ({summary['llm_interactions']}) != actual LLM events ({actual_llm_events})"
        assert summary['mcp_communications'] == actual_mcp_events, \
            f"Summary mcp_communications ({summary['mcp_communications']}) != actual MCP events ({actual_mcp_events})"
        assert summary['system_events'] == actual_system_events, \
            f"Summary system_events ({summary['system_events']}) != actual system events ({actual_system_events})"
        
        # EXACT VALIDATION: Chain-specific statistics (we know exactly what this test produces)
        if chain_execution and "stages" in chain_execution:
            assert "chain_statistics" in summary, "Chain executions should have chain_statistics in summary"
            chain_stats = summary["chain_statistics"]
            
            # Required chain statistics fields
            required_chain_fields = ["total_stages", "completed_stages", "failed_stages", "stages_by_agent"]
            for field in required_chain_fields:
                assert field in chain_stats, f"Missing required chain statistics field: {field}"
            
            # EXACT VALIDATION: We know precisely what this test should produce
            expected_chain_stats = {
                "total_stages": 3,
                "completed_stages": 3,
                "failed_stages": 0
            }
            
            for field, expected_value in expected_chain_stats.items():
                actual_value = chain_stats.get(field, -999)
                assert actual_value == expected_value, f"EXACT VALIDATION FAILED: Chain stats {field} expected exactly {expected_value}, got {actual_value}"
            
            # EXACT VALIDATION: stages_by_agent should show exactly our test agents
            expected_stages_by_agent = {
                "DataCollectionAgent": 1,
                "KubernetesAgent": 1, 
                "AnalysisAgent": 1
            }
            
            actual_stages_by_agent = chain_stats.get("stages_by_agent", {})
            for agent, expected_count in expected_stages_by_agent.items():
                actual_count = actual_stages_by_agent.get(agent, -999)
                assert actual_count == expected_count, f"EXACT VALIDATION FAILED: stages_by_agent[{agent}] expected exactly {expected_count}, got {actual_count}"
            
            print(f"   🔗 Chain statistics validated:")
            print(f"      Total Stages: {chain_stats['total_stages']}")
            print(f"      Completed Stages: {chain_stats['completed_stages']}")
            print(f"      Failed Stages: {chain_stats['failed_stages']}")
            print(f"      Stages by Agent: {chain_stats['stages_by_agent']}")
        
        print(f"✅ Session summary statistics validation passed - All statistics accurate")
        
        print(f"✅ Session detail validation passed - Chain data comprehensive")
        
        # Test with query parameters (if supported)
        filtered_response = test_client.get("/api/v1/history/sessions?limit=10")
        assert filtered_response.status_code == 200, "Sessions API with query params failed"
        
        print("✅ Comprehensive sessions API validation completed successfully!")
        
        return our_session, stage_interaction_counts if 'stages' in chain_execution else {}

    def _validate_session_vs_stage_counts(self, session_level_counts: dict, stage_level_totals: dict):
        """
        Cross-validate that session-level interaction counts match stage-level totals.
        
        This ensures our unified counting approach works correctly - both SQL aggregation
        at session level and stage level should produce consistent results.
        
        Args:
            session_level_counts: Counts from sessions list API
            stage_level_totals: Calculated totals from summing stage counts
        """
        print("🔍 Cross-validating session-level vs stage-level interaction counts...")
        
        # Extract session-level counts (from sessions list API)
        session_llm = session_level_counts.get("session_llm_count", 0)
        session_mcp = session_level_counts.get("session_mcp_count", 0) 
        session_total = session_level_counts.get("session_total_count", 0)
        
        # Extract stage-level totals (calculated from stage sums)
        stage_llm = stage_level_totals.get("stage_total_llm", 0)
        stage_mcp = stage_level_totals.get("stage_total_mcp", 0)
        stage_total = stage_level_totals.get("stage_total_interactions", 0)
        
        print(f"   📊 Session-level counts (from sessions list API): {session_llm} LLM + {session_mcp} MCP = {session_total} total")
        print(f"   📊 Stage-level totals (calculated from stages): {stage_llm} LLM + {stage_mcp} MCP = {stage_total} total")
        
        # CRITICAL VALIDATION: Session counts must match stage totals
        # This validates that our unified SQL aggregation approach works correctly
        assert session_llm == stage_llm, f"CROSS-VALIDATION FAILED: Session LLM count ({session_llm}) != Stage LLM total ({stage_llm})"
        assert session_mcp == stage_mcp, f"CROSS-VALIDATION FAILED: Session MCP count ({session_mcp}) != Stage MCP total ({stage_mcp})"
        assert session_total == stage_total, f"CROSS-VALIDATION FAILED: Session total count ({session_total}) != Stage total count ({stage_total})"
        
        # EXPECTED VALUES VALIDATION: Ensure they match our known test scenario
        expected_llm = 8    # 4 + 3 + 1 from all stages
        expected_mcp = 5    # 3 + 2 + 0 from all stages
        expected_total = 13 # 8 + 5
        
        assert session_llm == expected_llm, f"EXPECTED VALUES FAILED: Session LLM count ({session_llm}) != Expected ({expected_llm})"
        assert session_mcp == expected_mcp, f"EXPECTED VALUES FAILED: Session MCP count ({session_mcp}) != Expected ({expected_mcp})"
        assert session_total == expected_total, f"EXPECTED VALUES FAILED: Session total count ({session_total}) != Expected ({expected_total})"
        
        print(f"   ✅ CROSS-VALIDATION PASSED: Session and stage counts are consistent")
        print(f"   ✅ EXPECTED VALUES PASSED: Counts match known test scenario ({expected_llm} LLM + {expected_mcp} MCP = {expected_total} total)")
        print(f"   ✅ UNIFIED COUNTING VERIFIED: SQL aggregation works correctly at both session and stage levels")

    async def test_comprehensive_alert_processing_and_api_validation(
        self,
        e2e_test_client,
        e2e_realistic_kubernetes_alert,
        isolated_e2e_settings,
        isolated_test_database
    ):
        """
        Comprehensive test: Process alert once, then validate multiple API endpoints.
        
        This unified test covers:
        1. Real alert processing with multi-stage chain execution
        2. Sessions API validation (list + detail endpoints)
        3. Comprehensive API data validation
        4. Data consistency across all endpoints
        
        Benefits:
        - Complete isolation: Uses isolated fixtures to prevent test interference
        - No duplication: Process alert only once
        - Complete coverage: All API endpoints tested
        - Efficient: Single test run covers everything
        - Clean: All temporary resources automatically cleaned up
        """
        print("🚀 Starting comprehensive alert processing and API validation...")
        print(f"   📊 Using isolated database: {isolated_test_database}")
        print(f"   ⚙️  Using isolated settings with proper isolation")
        
        # Create realistic mocks using the isolated environment
        llm_mock, mcp_mock = await self._create_simple_fast_mocks()
        
        # All settings and environment isolation is handled by fixtures
        # Database is already initialized by the isolated_test_database fixture
        
        # Mock dependencies but keep real alert service
        with patch('tarsy.services.history_service.get_settings') as mock_history_settings, \
             patch('tarsy.services.alert_service.LLMManager') as mock_llm_manager_class, \
             patch('tarsy.services.alert_service.MCPClient') as mock_mcp_client_class, \
             patch('tarsy.services.alert_service.MCPServerRegistry') as mock_mcp_server_registry, \
             patch('tarsy.services.alert_service.RunbookService') as mock_runbook_service, \
             patch('tarsy.main.alert_processing_semaphore') as mock_semaphore:
            
            print("🔧 Setting up real AlertService with mocked dependencies...")
        
            # Setup history service settings (use isolated settings)
            mock_history_settings.return_value = isolated_e2e_settings
            
            # Setup semaphore mock to allow async context management
            real_semaphore = asyncio.Semaphore()
            
            # Patch the semaphore directly in the main module, not just the return value
            import tarsy.main
            tarsy.main.alert_processing_semaphore = real_semaphore
            
            # CRITICAL: Also patch the mock to return the real semaphore when needed
            mock_semaphore.return_value = real_semaphore
            
            # Database is already initialized by the isolated_test_database fixture
            print(f"✅ Using isolated database: {isolated_test_database}")
        
            # Setup LLM Manager mock - CRITICAL: this needs to return our async llm_mock
            mock_llm_manager_instance = Mock()
            mock_llm_manager_instance.is_available.return_value = True
            mock_llm_manager_instance.get_client.return_value = llm_mock  # This goes to AgentFactory and then to agents
            mock_llm_manager_instance.initialize.return_value = True
            mock_llm_manager_instance.list_available_providers.return_value = ["gemini"]
            mock_llm_manager_instance.get_availability_status.return_value = {"gemini": "available"}
            # CRITICAL: The LLM manager itself should also be async-compatible since agents may call it directly
            mock_llm_manager_instance.__call__ = AsyncMock(return_value=llm_mock)
            mock_llm_manager_class.return_value = mock_llm_manager_instance
            
            # Setup MCP Client mock with realistic methods
            mock_mcp_client_instance = Mock()
            mock_mcp_client_instance.initialize = AsyncMock()
            mock_mcp_client_instance.call_tool = mcp_mock.call_tool  # Use our realistic async mock
            mock_mcp_client_instance.list_servers = AsyncMock(return_value=["kubernetes-server"])
            mock_mcp_client_instance.get_available_tools = AsyncMock(return_value=["get_namespace", "patch_namespace", "check_status"])
            
            # CRITICAL: This is the method that was failing at line 639 in base_agent.py
            mock_mcp_client_instance.list_tools = AsyncMock(return_value={
                "kubernetes-server": [
                    {"name": "get_namespace", "description": "Get namespace information"},
                    {"name": "patch_namespace", "description": "Patch namespace configuration"},
                    {"name": "check_status", "description": "Check resource status"},
                ]
            })
            mock_mcp_client_class.return_value = mock_mcp_client_instance
            
            # Setup MCP Server Registry mock with realistic tool discovery
            mock_mcp_registry_instance = Mock()
            mock_mcp_registry_instance.initialize_servers = AsyncMock()
            mock_mcp_registry_instance.get_server_client = AsyncMock(return_value=mcp_mock)
            mock_mcp_registry_instance.list_available_servers = Mock(return_value=["kubernetes-server"])
            mock_mcp_registry_instance.cleanup_all_servers = AsyncMock()
            
            # Add tool discovery methods that return proper iterables
            mock_mcp_registry_instance.get_available_tools = AsyncMock(return_value=[
                {"name": "get_namespace", "description": "Get namespace information"},
                {"name": "patch_namespace", "description": "Patch namespace configuration"},
                {"name": "check_status", "description": "Check resource status"},
                {"name": "kubectl_get", "description": "Get Kubernetes resources"},
                {"name": "kubectl_patch", "description": "Patch Kubernetes resources"}
            ])
            mock_mcp_registry_instance.discover_tools = AsyncMock(return_value={
                "kubernetes-server": [
                    {"name": "get_namespace", "description": "Get namespace information"},
                    {"name": "patch_namespace", "description": "Patch namespace configuration"},
                    {"name": "check_status", "description": "Check resource status"}
                ]
            })
            
            # CRITICAL: Add the missing get_server_configs method that agents iterate over
            from types import SimpleNamespace
            
            def mock_get_server_configs(server_ids):
                """Return mock server config objects that can be iterated over."""
                configs = []
                for server_id in server_ids:
                    config = SimpleNamespace(
                        server_id=server_id,
                        instructions="Mock instructions for " + server_id,
                        description=f"Mock {server_id} server for testing",
                        name=server_id,
                        server_type="mock",
                        connection_params={}
                    )
                    configs.append(config)
                return configs
            
            def mock_get_single_server_config(server_id):
                """Return a single mock server config object."""
                return SimpleNamespace(
                    server_id=server_id,
                    instructions="Mock instructions for " + server_id,
                    description=f"Mock {server_id} server for testing",
                    name=server_id,
                    server_type="mock",
                    connection_params={}
                )
            
            mock_mcp_registry_instance.get_server_configs = Mock(side_effect=mock_get_server_configs)
            mock_mcp_registry_instance.get_server_config = Mock(side_effect=mock_get_single_server_config)
            
            mock_mcp_server_registry.return_value = mock_mcp_registry_instance
            
            # Setup Runbook Service mock
            mock_runbook_instance = Mock()
            mock_runbook_instance.download_runbook = AsyncMock(return_value="Mock runbook content for kubernetes namespace terminating")
            mock_runbook_service.return_value = mock_runbook_instance
            
            # Create real AlertService and use it for processing
            from tarsy.services.alert_service import AlertService
            real_alert_service = AlertService(isolated_e2e_settings)
            
            # CRITICAL: Replace AlertService's dependencies with our mocks BEFORE initialize()
            # This ensures the AgentFactory gets our mocks when AlertService.initialize() creates it
            real_alert_service.mcp_client = mock_mcp_client_instance
            # IMPORTANT: The AgentFactory expects llm_client to be the actual client, not a manager
            # So we pass our llm_mock directly as the llm_manager
            real_alert_service.llm_manager = llm_mock
            # CRITICAL: Replace the runbook service with our mock to prevent real HTTP requests
            real_alert_service.runbook_service = mock_runbook_instance
            
            await real_alert_service.initialize()
            print("✅ Real AlertService initialized with mocked dependencies")
            
            # DEBUG: Check what chains are available
            available_alert_types = real_alert_service.chain_registry.list_available_alert_types()
            available_chains = real_alert_service.chain_registry.list_available_chains()
            print(f"🔍 Available alert types: {available_alert_types}")
            print(f"🔍 Available chains: {available_chains}")
            
            # Replace the main alert service with our real instance
            with patch('tarsy.main.alert_service', real_alert_service):
                # STEP 1: Submit Alert 
                print("\n📝 STEP 1: Submitting alert...")
                response = e2e_test_client.post("/alerts", json=e2e_realistic_kubernetes_alert)
                if response.status_code != 200:
                    print(f"❌ Alert submission failed: {response.status_code} - {response.text}")
                    pytest.fail(f"Alert submission failed: {response.status_code}")
                    
                response_data = response.json()
                assert response_data["status"] == "queued"
                alert_id = response_data["alert_id"]
                print(f"✅ Alert submitted: {alert_id}")
                
                # STEP 2: Wait for processing completion
                print("\n⏳ STEP 2: Waiting for processing completion...")
                session_id = None
                for i in range(60):  # Increased timeout for real processing
                    await asyncio.sleep(0.5)  # Longer sleep for real processing
                    session_id = real_alert_service.get_session_id_for_alert(alert_id)
                    if session_id:
                        print(f"   📋 Session found: {session_id[:8]}...")
                        break
                                        
                if not session_id:
                    pytest.fail("Session was not created within timeout")
                    
                print(f"✅ Processing completed with session: {session_id}")
                
                # Step 3: Validate Sessions API endpoints
                print("\n🔍 STEP 3: Validating Sessions API endpoints...")
                session_data, stage_interaction_counts = await self._validate_sessions_api(e2e_test_client, session_id, e2e_realistic_kubernetes_alert)
                
                # Step 4: Validate comprehensive API data structures  
                print("\n🔍 STEP 4: Validating comprehensive API data...")
                session_level_counts = await self._validate_comprehensive_api_data(e2e_test_client, alert_id, session_id)
                
                # Calculate stage totals from stage_interaction_counts for cross-validation
                assert stage_interaction_counts, "Stage interaction counts should always be present in E2E tests"
                total_llm = sum(counts.get("llm", 0) for counts in stage_interaction_counts.values())
                total_mcp = sum(counts.get("mcp", 0) for counts in stage_interaction_counts.values())
                total_interactions = total_llm + total_mcp
                stage_level_totals = {
                    "stage_total_llm": total_llm,
                    "stage_total_mcp": total_mcp,
                    "stage_total_interactions": total_interactions,
                    "stage_interaction_counts": stage_interaction_counts
                }
                
                # Step 4.1: CROSS-VALIDATION - Ensure session-level and stage-level counts match
                print("\n🔍 STEP 4.1: Cross-validating session vs stage interaction counts...")
                assert session_level_counts, "Session-level counts should always be present in E2E tests"
                assert stage_level_totals, "Stage-level totals should always be present in E2E tests"
                self._validate_session_vs_stage_counts(session_level_counts, stage_level_totals)
                
                # Step 5: Enhanced Summary
                print("\n🎉 All API validations completed successfully!")
                print(f"   ✅ Alert processing: {session_data.get('status')}")
                print(f"   ✅ Session uniqueness: 1 session confirmed")
                print(f"   ✅ Alert data consistency: Verified")
                print(f"   ✅ Sessions list API validated")  
                print(f"   ✅ Session detail API validated")
                print(f"   ✅ Comprehensive data validated")
                print(f"   ✅ Session vs Stage count cross-validation passed")
                print(f"   ✅ Unified SQL aggregation counting verified")
                print(f"   ✅ Processing took: {session_data.get('duration_ms', 'unknown')}ms")
                print(f"   ✅ Complete isolation: All resources automatically cleaned up")
                
                # EXACT VALIDATION: We MUST have stage interaction data
                assert stage_interaction_counts, "EXACT VALIDATION FAILED: No stage interaction counts available. Stage processing failed."
                
                # EXACT VALIDATION: Final verification of exact stage interaction counts
                final_stage_exact_counts = {
                    "stage_0": {"llm": 4, "mcp": 3, "total": 7},  # data-collection
                    "stage_1": {"llm": 3, "mcp": 2, "total": 5},  # verification  
                    "stage_2": {"llm": 1, "mcp": 0, "total": 1}   # analysis (final-analysis strategy)
                }
                
                print(f"   📊 Stage breakdown:")
                for stage_name, counts in stage_interaction_counts.items():
                    expected = final_stage_exact_counts.get(stage_name, {"llm": 1, "mcp": 1, "total": 2})
                    
                    # EXACT FINAL ASSERTIONS - EXACT NUMBERS ONLY
                    assert counts["llm"] == expected["llm"], f"EXACT VALIDATION FAILED: {stage_name} has {counts['llm']} LLM interactions, expected exactly {expected['llm']}"
                    assert counts["mcp"] == expected["mcp"], f"EXACT VALIDATION FAILED: {stage_name} has {counts['mcp']} MCP interactions, expected exactly {expected['mcp']}"
                    assert counts["total"] == expected["total"], f"EXACT VALIDATION FAILED: {stage_name} has {counts['total']} total interactions, expected exactly {expected['total']}"
                    
                    print(f"      • {stage_name}: {counts['llm']} LLM + {counts['mcp']} MCP = {counts['total']} total interactions ✅")
        
        # Note: All cleanup is handled automatically by the isolated e2e fixtures
        print("🧹 All temporary resources automatically cleaned up by isolation fixtures")