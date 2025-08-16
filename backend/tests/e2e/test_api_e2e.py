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
        """Validate API data structures and processing results (Phase 5: Updated for new Pydantic models)."""
        print("🔍 Validating API data...")
        
        # Get session details (Phase 5: PaginatedSessions response)
        sessions_response = test_client.get("/api/v1/history/sessions")
        assert sessions_response.status_code == 200
        sessions_list = sessions_response.json()
        
        # Find our session (Phase 5: sessions are now in PaginatedSessions.sessions)
        our_session = None
        for session in sessions_list["sessions"]:
            if session.get("session_id") == session_id:
                our_session = session
                break
        
        assert our_session is not None, f"Session {session_id} not found"
        
        status = our_session.get("status", "unknown")
        llm_count = our_session.get("llm_interaction_count", 0)
        mcp_count = our_session.get("mcp_communication_count", 0)
        
        # Get session detail (Phase 5: DetailedSession response - different structure)
        detail_response = test_client.get(f"/api/v1/history/sessions/{session_id}")
        assert detail_response.status_code == 200
        session_detail = detail_response.json()
        
        # Basic validation (Phase 5: Updated field validation)
        assert status in ["completed", "failed", "processing"], f"Invalid status: {status}"
        assert session_detail.get("chain_id"), "Missing chain_id in session detail"
        
        print(f"✅ Session-level counts extracted: {status} with {llm_count} LLM + {mcp_count} MCP interactions")
        
        # Return the session-level counts for cross-validation
        return {
            "status": status,
            "session_llm_count": llm_count,
            "session_mcp_count": mcp_count,
            "session_total_count": llm_count + mcp_count
        }

    def _validate_stage_timeline_chronological(self, stage, stage_name):
        """Validate that all interactions in a stage are in chronological order"""
        llm_interactions = stage.get("llm_interactions", [])
        mcp_interactions = stage.get("mcp_communications", [])
        
        # Validate that LLM interactions are internally chronologically sorted
        llm_timestamps = [i.get("timestamp_us") for i in llm_interactions if i.get("timestamp_us") is not None]
        if len(llm_timestamps) > 1:
            sorted_llm_timestamps = sorted(llm_timestamps)
            assert llm_timestamps == sorted_llm_timestamps, \
                f"TIMELINE VALIDATION FAILED: Stage '{stage_name}' LLM interactions not chronologically sorted within type. " \
                f"Expected: {sorted_llm_timestamps}, Got: {llm_timestamps}"
        
        # Validate that MCP interactions are internally chronologically sorted  
        mcp_timestamps = [i.get("timestamp_us") for i in mcp_interactions if i.get("timestamp_us") is not None]
        if len(mcp_timestamps) > 1:
            sorted_mcp_timestamps = sorted(mcp_timestamps)
            assert mcp_timestamps == sorted_mcp_timestamps, \
                f"TIMELINE VALIDATION FAILED: Stage '{stage_name}' MCP interactions not chronologically sorted within type. " \
                f"Expected: {sorted_mcp_timestamps}, Got: {mcp_timestamps}"
        
        # Validate chronological_interactions property (now available in API response!)
        chronological_interactions = stage.get("chronological_interactions", [])
        if len(chronological_interactions) > 1:
            timestamps = [i.get("timestamp_us") for i in chronological_interactions if i.get("timestamp_us") is not None]
            assert timestamps == sorted(timestamps), \
                f"CHRONOLOGICAL ORDERING FAILED: Stage '{stage_name}' chronological_interactions not properly sorted. " \
                f"Expected: {sorted(timestamps)}, Got: {timestamps}"
            
            # Validate that chronological_interactions combines both types correctly
            llm_count_in_chrono = sum(1 for i in chronological_interactions if i.get("type") == "llm")
            mcp_count_in_chrono = sum(1 for i in chronological_interactions if i.get("type") == "mcp")
            
            assert llm_count_in_chrono == len(llm_timestamps), \
                f"LLM count mismatch in chronological_interactions: expected {len(llm_timestamps)}, got {llm_count_in_chrono}"
            assert mcp_count_in_chrono == len(mcp_timestamps), \
                f"MCP count mismatch in chronological_interactions: expected {len(mcp_timestamps)}, got {mcp_count_in_chrono}"
            
            # Deep validate ALL interactions in chronological_interactions list
            for chrono_index, chrono_interaction in enumerate(chronological_interactions):
                interaction_type = chrono_interaction.get("type")
                if interaction_type == "llm":
                    self._validate_llm_interaction_deep(chrono_interaction, stage_name, f"chrono[{chrono_index}]")
                elif interaction_type == "mcp":
                    self._validate_mcp_interaction_deep(chrono_interaction, stage_name, f"chrono[{chrono_index}]")
                else:
                    assert False, f"CHRONOLOGICAL VALIDATION FAILED: Stage '{stage_name}' chronological_interactions[{chrono_index}] has unknown type: {interaction_type}"
            
            print(f"   ✅ Stage '{stage_name}' chronological_interactions validated: {len(chronological_interactions)} interactions in proper chronological order with deep validation")
        elif len(chronological_interactions) == 1:
            # Deep validate the single interaction
            chrono_interaction = chronological_interactions[0]
            interaction_type = chrono_interaction.get("type")
            if interaction_type == "llm":
                self._validate_llm_interaction_deep(chrono_interaction, stage_name, "chrono[0]")
            elif interaction_type == "mcp":
                self._validate_mcp_interaction_deep(chrono_interaction, stage_name, "chrono[0]")
            else:
                assert False, f"CHRONOLOGICAL VALIDATION FAILED: Stage '{stage_name}' chronological_interactions[0] has unknown type: {interaction_type}"
            
            print(f"   ✅ Stage '{stage_name}' chronological_interactions: 1 interaction validated (type: {interaction_type})")
        else:
            print(f"   ✅ Stage '{stage_name}' chronological_interactions: empty (no interactions to validate)")
        
        total_interactions = len(llm_timestamps) + len(mcp_timestamps)
        print(f"   ✅ Stage '{stage_name}' timeline validated: LLM({len(llm_timestamps)}) and MCP({len(mcp_timestamps)}) interactions chronologically sorted within types, total timeline has {total_interactions} interactions")

    def _validate_stage_timing_and_status(self, stage, stage_name):
        """Validate stage timing and status make sense"""
        status = stage.get("status")
        started_at_us = stage.get("started_at_us")
        completed_at_us = stage.get("completed_at_us") 
        duration_ms = stage.get("duration_ms")
        
        # Status validation
        expected_status = "completed"  # For successful e2e test
        assert status == expected_status, f"TIMING VALIDATION FAILED: Stage '{stage_name}' status is '{status}', expected '{expected_status}'"
        
        # Timing presence validation
        assert started_at_us is not None, f"TIMING VALIDATION FAILED: Stage '{stage_name}' missing started_at_us"
        assert completed_at_us is not None, f"TIMING VALIDATION FAILED: Stage '{stage_name}' missing completed_at_us"
        assert duration_ms is not None, f"TIMING VALIDATION FAILED: Stage '{stage_name}' missing duration_ms"
        
        # Timing sanity checks
        assert isinstance(started_at_us, int), f"TIMING VALIDATION FAILED: Stage '{stage_name}' started_at_us not integer"
        assert isinstance(completed_at_us, int), f"TIMING VALIDATION FAILED: Stage '{stage_name}' completed_at_us not integer"
        assert isinstance(duration_ms, (int, float)), f"TIMING VALIDATION FAILED: Stage '{stage_name}' duration_ms not numeric"
        
        assert completed_at_us >= started_at_us, f"TIMING VALIDATION FAILED: Stage '{stage_name}' completed before started"
        assert duration_ms >= 0, f"TIMING VALIDATION FAILED: Stage '{stage_name}' negative duration: {duration_ms}ms"
        
        # Realistic timing bounds (stages should take some time but not too long)
        assert duration_ms < 30000, f"TIMING VALIDATION FAILED: Stage '{stage_name}' took too long: {duration_ms}ms (>30s)"
        assert duration_ms > 0, f"TIMING VALIDATION FAILED: Stage '{stage_name}' completed too fast: {duration_ms}ms"
        
        print(f"   ✅ Stage '{stage_name}' timing validated: {duration_ms}ms duration, status='{status}'")

    def _validate_llm_interaction_deep(self, interaction, stage_name, interaction_index):
        """Deep validation of a single LLM interaction"""
        event_id = interaction.get("event_id")
        timestamp_us = interaction.get("timestamp_us") 
        interaction_type = interaction.get("type")
        step_description = interaction.get("step_description")
        details = interaction.get("details", {})
        
        # Basic structure (already validated but double-check)
        assert event_id, f"DEEP VALIDATION FAILED: Stage '{stage_name}' LLM[{interaction_index}] missing event_id"
        assert timestamp_us is not None, f"DEEP VALIDATION FAILED: Stage '{stage_name}' LLM[{interaction_index}] missing timestamp_us"
        assert interaction_type == "llm", f"DEEP VALIDATION FAILED: Stage '{stage_name}' LLM[{interaction_index}] wrong type: {interaction_type}"
        
        # Deep content validation
        assert step_description, f"DEEP VALIDATION FAILED: Stage '{stage_name}' LLM[{interaction_index}] missing step_description"
        assert isinstance(details, dict), f"DEEP VALIDATION FAILED: Stage '{stage_name}' LLM[{interaction_index}] details not dict"
        
        # LLM-specific details
        model_name = details.get("model_name")
        assert model_name, f"DEEP VALIDATION FAILED: Stage '{stage_name}' LLM[{interaction_index}] missing model_name in details"
        
        # Validate request/response structure if present
        if "request" in details:
            request = details["request"]
            assert isinstance(request, dict), f"DEEP VALIDATION FAILED: Stage '{stage_name}' LLM[{interaction_index}] request not dict"
        
        if "response" in details:
            response = details["response"] 
            assert isinstance(response, dict), f"DEEP VALIDATION FAILED: Stage '{stage_name}' LLM[{interaction_index}] response not dict"
        
        print(f"   ✅ Stage '{stage_name}' LLM interaction [{interaction_index}] deeply validated (model: {model_name})")

    def _validate_mcp_sequence_pattern(self, mcp_interactions, stage_name):
        """
        Validate MCP interaction sequence pattern: should include both tool_list and tool_call interactions.
        
        Expected pattern for stages that use tools:
        - First interaction: tool_list (tool discovery)
        - Subsequent interactions: tool_call (actual tool execution)
        
        For analysis stage: no MCP interactions (empty list)
        """
        if len(mcp_interactions) == 0:
            print(f"   ✅ Stage '{stage_name}' MCP sequence: empty (no tools used)")
            return
            
        # Validate sequence pattern based on stage
        if stage_name in ["data-collection", "verification"]:
            # These stages should start with tool_list, then have tool_call interactions
            assert len(mcp_interactions) >= 1, f"MCP SEQUENCE VALIDATION FAILED: Stage '{stage_name}' should have at least 1 interaction"
            
            # First interaction should be tool_list (tool discovery)
            first_interaction = mcp_interactions[0]
            first_details = first_interaction.get("details", {})
            first_comm_type = first_details.get("communication_type", "unknown")
            
            assert first_comm_type == "tool_list", \
                f"MCP SEQUENCE VALIDATION FAILED: Stage '{stage_name}' MCP[0] should be tool_list, got: {first_comm_type}"
            print(f"   ✅ Stage '{stage_name}' MCP sequence: interaction[0] is tool_list as expected")
            
            # Subsequent interactions should be tool_call
            for i in range(1, len(mcp_interactions)):
                interaction = mcp_interactions[i]
                details = interaction.get("details", {})
                communication_type = details.get("communication_type", "unknown")
                
                assert communication_type == "tool_call", \
                    f"MCP SEQUENCE VALIDATION FAILED: Stage '{stage_name}' MCP[{i}] should be tool_call, got: {communication_type}"
                print(f"   ✅ Stage '{stage_name}' MCP sequence: interaction[{i}] is tool_call as expected")
        else:
            # For other stages, just validate that interactions are valid types
            for i, interaction in enumerate(mcp_interactions):
                details = interaction.get("details", {})
                communication_type = details.get("communication_type", "unknown")
                
                assert communication_type in ["tool_list", "tool_call"], \
                    f"MCP SEQUENCE VALIDATION FAILED: Stage '{stage_name}' MCP[{i}] has invalid communication_type: {communication_type}"
                print(f"   ✅ Stage '{stage_name}' MCP sequence: interaction[{i}] has valid type: {communication_type}")

    def _validate_mcp_interaction_deep(self, interaction, stage_name, interaction_index):
        """Deep validation of a single MCP interaction with enhanced MCP protocol checks"""
        event_id = interaction.get("event_id")
        timestamp_us = interaction.get("timestamp_us")
        interaction_type = interaction.get("type") 
        step_description = interaction.get("step_description")
        details = interaction.get("details", {})
        
        # Basic structure
        assert event_id, f"DEEP VALIDATION FAILED: Stage '{stage_name}' MCP[{interaction_index}] missing event_id"
        assert timestamp_us is not None, f"DEEP VALIDATION FAILED: Stage '{stage_name}' MCP[{interaction_index}] missing timestamp_us"
        assert interaction_type == "mcp", f"DEEP VALIDATION FAILED: Stage '{stage_name}' MCP[{interaction_index}] wrong type: {interaction_type}"
        
        # Deep content validation
        assert step_description, f"DEEP VALIDATION FAILED: Stage '{stage_name}' MCP[{interaction_index}] missing step_description"
        assert isinstance(details, dict), f"DEEP VALIDATION FAILED: Stage '{stage_name}' MCP[{interaction_index}] details not dict"
        
        # MCP-specific details
        server_name = details.get("server_name")
        tool_name = details.get("tool_name")
        communication_type = details.get("communication_type")
        
        assert server_name, f"DEEP VALIDATION FAILED: Stage '{stage_name}' MCP[{interaction_index}] missing server_name in details"
        assert communication_type, f"DEEP VALIDATION FAILED: Stage '{stage_name}' MCP[{interaction_index}] missing communication_type in details"
        
        # tool_name is only required for tool_call interactions, not tool_list
        if communication_type == "tool_call":
            assert tool_name, f"DEEP VALIDATION FAILED: Stage '{stage_name}' MCP[{interaction_index}] missing tool_name for tool_call interaction"
        
        # Validate communication_type is either tool_list or tool_call
        assert communication_type in ["tool_list", "tool_call"], \
            f"DEEP VALIDATION FAILED: Stage '{stage_name}' MCP[{interaction_index}] invalid communication_type: {communication_type}, expected: tool_list or tool_call"
        
        # Validate tool call structure if present
        if "tool_input" in details:
            tool_input = details["tool_input"]
            assert isinstance(tool_input, dict), f"DEEP VALIDATION FAILED: Stage '{stage_name}' MCP[{interaction_index}] tool_input not dict"
        
        if "tool_result" in details:
            tool_result = details["tool_result"]
            # tool_result can be various types depending on the tool
            assert tool_result is not None, f"DEEP VALIDATION FAILED: Stage '{stage_name}' MCP[{interaction_index}] tool_result is None"
        
        print(f"   ✅ Stage '{stage_name}' MCP interaction [{interaction_index}] deeply validated (server: {server_name}, tool: {tool_name}, type: {communication_type})")

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
        
        # VALIDATION 3: Get detailed session data and validate stages (Phase 5: Updated structure)
        print(f"🔍 Testing GET /api/v1/history/sessions/{session_id}...")
        detail_response = test_client.get(f"/api/v1/history/sessions/{session_id}")
        
        assert detail_response.status_code == 200, f"Session detail API failed: {detail_response.status_code}"
        detail_data = detail_response.json()
        
        # Phase 5: Validate updated DetailedSession structure - fields are now at root level
        required_detail_fields = ["session_id", "alert_data", "chain_id", "stages"]
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
        
        # Phase 5: DetailedSession no longer has a separate "summary" field - summary data is embedded
        # We can still validate the standalone summary endpoint against derived values from detail session
        detail_total_interactions = detail_data.get("total_interactions", 0)
        detail_llm_interactions = detail_data.get("llm_interaction_count", 0)
        detail_mcp_communications = detail_data.get("mcp_communication_count", 0)
        
        # Basic consistency check for core counts
        assert summary_data["total_interactions"] == detail_total_interactions, f"Total interactions mismatch: summary={summary_data['total_interactions']}, detail={detail_total_interactions}"
        assert summary_data["llm_interactions"] == detail_llm_interactions, f"LLM interactions mismatch: summary={summary_data['llm_interactions']}, detail={detail_llm_interactions}"
        assert summary_data["mcp_communications"] == detail_mcp_communications, f"MCP communications mismatch: summary={summary_data['mcp_communications']}, detail={detail_mcp_communications}"
        
        # EXACT VALIDATION: Both endpoints should return precisely the same known values
        # Updated counts now include tool_list interactions (1 per data-collection and verification stage)
        expected_exact_counts = {
            "total_interactions": 15,  # 13 + 2 tool_list interactions (data-collection + verification)
            "llm_interactions": 8,     # 4+3+1 = 8 LLM interactions (unchanged)
            "mcp_communications": 7,   # 5 tool_call + 2 tool_list interactions
            "system_events": 0,
            "errors_count": 0
        }
        
        # EXACT VALIDATION: Validate exact counts for summary endpoint (Phase 5: Only summary endpoint now)
        for field, expected_value in expected_exact_counts.items():
            actual_value = summary_data.get(field, -999)
            assert actual_value == expected_value, f"EXACT VALIDATION FAILED: summary endpoint {field} expected exactly {expected_value}, got {actual_value}"
        
        # SANITY CHECK: Duration should be non-negative (exact value depends on execution speed)
        duration = summary_data.get("total_duration_ms", -1)
        assert duration >= 0, f"SANITY CHECK FAILED: summary endpoint shows negative processing duration ({duration}ms)"
        
        # Phase 5: Chain statistics validation - now nested in SessionStats
        assert "chain_statistics" in summary_data, "Chain statistics missing from summary endpoint"
        chain_stats = summary_data["chain_statistics"]
        chain_fields = ["total_stages", "completed_stages", "failed_stages"]
        for field in chain_fields:
            assert field in chain_stats, f"Chain statistics missing field: {field}"
        
        print(f"✅ Summary endpoint validation passed - data consistency confirmed")
        
        # VALIDATION 4: Validate chain execution and stages (Phase 5: Updated structure)
        print("🔍 Validating chain execution and stages...")
        
        # Phase 5: stages are now directly at root level in DetailedSession
        stages = detail_data["stages"]
        assert isinstance(stages, list), "stages should be list"
        
        # EXACT VALIDATION: Number of stages MUST be exactly 3 (from test_agents.yaml)
        expected_stage_count = 3
        expected_stages = ["data-collection", "verification", "analysis"]  # Actual stage names from YAML config
        print(f"🔍 Validating stage count and names...")
        print(f"   📊 Found {len(stages)} stages (expected exactly {expected_stage_count})")
        
        assert len(stages) == expected_stage_count, f"EXACT VALIDATION FAILED: Expected exactly {expected_stage_count} stages, found {len(stages)}"
        
        # VALIDATION 6: Each stage name should match expectations (Phase 5: Updated stage structure)
        actual_stage_names = []
        stage_interaction_counts = {}
        
        for i, stage in enumerate(stages):
            assert isinstance(stage, dict), f"Stage {i} should be dict"
            stage_name = stage.get("stage_name", f"stage_{i}")  # Phase 5: DetailedStage uses "stage_name"
            actual_stage_names.append(stage_name)
            
            # Phase 5: DetailedStage has direct interaction lists, not nested timeline/summary
            llm_interactions = stage.get("llm_interactions", [])
            mcp_communications = stage.get("mcp_communications", [])
            
            # Phase 5: Count from the direct interaction lists
            llm_count = len(llm_interactions)
            mcp_count = len(mcp_communications)
            
            # Phase 5: Validate against the summary counts in DetailedStage
            stage_llm_count = stage.get("llm_interaction_count", 0)
            stage_mcp_count = stage.get("mcp_communication_count", 0)
            stage_total_count = stage.get("total_interactions", 0)
            
            # VALIDATION: Stage lists and counts should match
            assert llm_count == stage_llm_count, f"Stage {stage_name} LLM list count ({llm_count}) != Stage count field ({stage_llm_count})"
            assert mcp_count == stage_mcp_count, f"Stage {stage_name} MCP list count ({mcp_count}) != Stage count field ({stage_mcp_count})"
            assert llm_count + mcp_count == stage_total_count, f"Stage {stage_name} total count mismatch"
            
            stage_interaction_counts[stage_name] = {
                "llm": llm_count,
                "mcp": mcp_count,
                "total": llm_count + mcp_count
            }
            
            print(f"   📋 Stage '{stage_name}': {llm_count} LLM + {mcp_count} MCP interactions")
            
            # STRICT VALIDATION: Each stage MUST have exactly the expected interactions
            total_interactions = llm_count + mcp_count
            
            # Define exact interaction requirements per stage (updated to include tool_list interactions)
            stage_exact_counts = {
                "data-collection": {"llm": 4, "mcp": 4, "total": 8},  # ReAct: 4 LLM calls + 1 tool_list + 3 MCP tool calls 
                "verification": {"llm": 3, "mcp": 3, "total": 6},     # ReAct: 3 LLM calls + 1 tool_list + 2 MCP tool calls
                "analysis": {"llm": 1, "mcp": 0, "total": 1}          # react-final-analysis: 1 LLM call + 0 MCP (no tools executed)
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
            
            # COMPREHENSIVE VALIDATION: Enhanced validation with timing, timeline, and deep content checks
            
            # 1. Stage timing and status validation
            self._validate_stage_timing_and_status(stage, stage_name)
            
            # 2. Timeline chronological validation
            self._validate_stage_timeline_chronological(stage, stage_name)
            
            # 3. Deep interaction validation (COMPREHENSIVE approach - validate ALL interactions)
            llm_interaction_objects = stage.get("llm_interactions", [])
            mcp_interaction_objects = stage.get("mcp_communications", [])
            
            # Validate ALL LLM interactions per stage (if expected)
            if expected["llm"] > 0:
                assert len(llm_interaction_objects) >= 1, f"COMPREHENSIVE VALIDATION FAILED: Stage '{stage_name}' missing LLM interaction data"
                
                # Deep validate ALL LLM interactions (comprehensive validation)
                for interaction_index, llm_interaction in enumerate(llm_interaction_objects):
                    self._validate_llm_interaction_deep(llm_interaction, stage_name, interaction_index)
            
            # Validate ALL MCP interactions per stage (if expected) + MCP tool validation
            if expected["mcp"] > 0:
                assert len(mcp_interaction_objects) >= 1, f"COMPREHENSIVE VALIDATION FAILED: Stage '{stage_name}' missing MCP interaction data"
                
                # Deep validate ALL MCP interactions (comprehensive validation)
                for interaction_index, mcp_interaction in enumerate(mcp_interaction_objects):
                    self._validate_mcp_interaction_deep(mcp_interaction, stage_name, interaction_index)
                
                # MCP SEQUENCE VALIDATION: Validate proper MCP protocol pattern (tool_list first, then tool_call)
                self._validate_mcp_sequence_pattern(mcp_interaction_objects, stage_name)
                    
                # MCP TOOL VALIDATION: Ensure we have variety of MCP tools being used
                unique_tools = set()
                unique_servers = set()
                for mcp_interaction in mcp_interaction_objects:
                    details = mcp_interaction.get("details", {})
                    server_name = details.get("server_name")
                    tool_name = details.get("tool_name") 
                    if server_name:
                        unique_servers.add(server_name)
                    if tool_name:
                        unique_tools.add(tool_name)
                
                print(f"   ✅ Stage '{stage_name}' MCP tool diversity: {len(unique_servers)} servers, {len(unique_tools)} tools ({', '.join(unique_tools)})")
                
            elif expected["mcp"] == 0:
                # For stages with 0 expected MCP interactions, verify none exist
                assert len(mcp_interaction_objects) == 0, f"COMPREHENSIVE VALIDATION FAILED: Stage '{stage_name}' should have 0 MCP interactions but found {len(mcp_interaction_objects)}"
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
        
        # EXACT VALIDATION: Total interactions must be exactly as expected (updated for tool_list)
        expected_total_llm = 8   # 4 + 3 + 1 from all stages (unchanged)
        expected_total_mcp = 7   # 4 + 3 + 0 from all stages (includes tool_list interactions)
        expected_total_interactions = 15  # 8 + 7
        
        # EXACT ASSERTION: Total LLM interactions must be exactly as expected
        assert total_llm == expected_total_llm, f"EXACT VALIDATION FAILED: Total LLM interactions {total_llm}, expected exactly {expected_total_llm}"
        
        # EXACT ASSERTION: Total MCP interactions must be exactly as expected
        assert total_mcp == expected_total_mcp, f"EXACT VALIDATION FAILED: Total MCP interactions {total_mcp}, expected exactly {expected_total_mcp}"
        
        # EXACT ASSERTION: Total interactions must be exactly as expected
        assert total_interactions == expected_total_interactions, f"EXACT VALIDATION FAILED: Total interactions {total_interactions}, expected exactly {expected_total_interactions}"
            
        print(f"   ✅ Total interactions validated: {total_llm} LLM + {total_mcp} MCP = {total_interactions} (exactly {expected_total_interactions} as required)")
        print(f"   ✅ Agent execution successful: {len(stages)} stage(s) completed")
        
        # Phase 5: Calculate total interaction events from all stages
        total_timeline_events = 0
        for stage in stages:
            stage_interactions = stage.get("llm_interactions", []) + stage.get("mcp_communications", [])
            total_timeline_events += len(stage_interactions)
        
        print(f"📅 Total interaction events across all stages: {total_timeline_events}")
        
        # VALIDATION 8: Verify alert data in session detail matches our submission
        session_alert_data = detail_data.get("alert_data", {})
        if session_alert_data:
            stored_alert_type = session_alert_data.get("alert_type")
            assert stored_alert_type == expected_alert_type, f"Stored alert type mismatch: expected {expected_alert_type}, got {stored_alert_type}"
            print(f"✅ Session detail alert data matches submission")
        
        # Phase 5: VALIDATION 9 - Summary data is now embedded in DetailedSession, validate via summary endpoint
        print("🔍 Validating session summary statistics via dedicated endpoint...")
        # We already validated the summary endpoint earlier, so we can refer to that data
        # Just validate that DetailedSession has the core count fields
        
        # Phase 5: Required fields are now directly in DetailedSession
        required_detail_count_fields = ["total_interactions", "llm_interaction_count", "mcp_communication_count"]
        
        for field in required_detail_count_fields:
            assert field in detail_data, f"Missing required count field in DetailedSession: {field}"
            assert isinstance(detail_data[field], int), f"DetailedSession field '{field}' should be an integer"
            assert detail_data[field] >= 0, f"DetailedSession field '{field}' should be non-negative"
        
        # Phase 5: EXACT VALIDATION - Validate DetailedSession count fields match expected values (updated for tool_list)
        expected_detail_counts = {
            "total_interactions": 15,  # 8 LLM + 7 MCP (includes 2 tool_list)
            "llm_interaction_count": 8,
            "mcp_communication_count": 7  # 5 tool_call + 2 tool_list
        }
        
        for field, expected_value in expected_detail_counts.items():
            actual_value = detail_data.get(field, -999)
            assert actual_value == expected_value, f"EXACT VALIDATION FAILED: DetailedSession {field} expected exactly {expected_value}, got {actual_value}"
        
        print(f"   📊 DetailedSession count fields validated:")
        print(f"      Total Interactions: {detail_data['total_interactions']}")
        print(f"      LLM Interactions: {detail_data['llm_interaction_count']}")
        print(f"      MCP Communications: {detail_data['mcp_communication_count']}")
        
        # Phase 5: Validation - DetailedSession counts should match actual stage interaction counts
        calculated_total_events = 0
        calculated_llm_events = 0
        calculated_mcp_events = 0
        
        for stage in stages:
            stage_interactions = stage.get("llm_interactions", []) + stage.get("mcp_communications", [])
            calculated_total_events += len(stage_interactions)
            calculated_llm_events += len(stage.get("llm_interactions", []))
            calculated_mcp_events += len(stage.get("mcp_communications", []))
        
        # Assert DetailedSession counts match calculated stage counts
        assert detail_data['total_interactions'] == calculated_total_events, \
            f"DetailedSession total_interactions ({detail_data['total_interactions']}) != calculated events ({calculated_total_events})"
        assert detail_data['llm_interaction_count'] == calculated_llm_events, \
            f"DetailedSession llm_interaction_count ({detail_data['llm_interaction_count']}) != calculated LLM events ({calculated_llm_events})"
        assert detail_data['mcp_communication_count'] == calculated_mcp_events, \
            f"DetailedSession mcp_communication_count ({detail_data['mcp_communication_count']}) != calculated MCP events ({calculated_mcp_events})"
        
        # Phase 5: Chain statistics validation is done via the summary endpoint (already validated above)
        # DetailedSession doesn't have embedded chain statistics - they're only in SessionStats from summary endpoint
        print(f"✅ DetailedSession count validation passed - All counts accurate")
        
        print(f"✅ Session detail validation passed - Chain data comprehensive")
        
        # Test with query parameters (if supported)
        filtered_response = test_client.get("/api/v1/history/sessions?limit=10")
        assert filtered_response.status_code == 200, "Sessions API with query params failed"
        
        print("✅ Comprehensive sessions API validation completed successfully!")
        
        return our_session, stage_interaction_counts if stages else {}

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
        
        # EXPECTED VALUES VALIDATION: Ensure they match our known test scenario (updated for tool_list)
        expected_llm = 8    # 4 + 3 + 1 from all stages (unchanged)
        expected_mcp = 7    # 4 + 3 + 0 from all stages (includes tool_list interactions)
        expected_total = 15 # 8 + 7
        
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
            
            # CRITICAL: Hook-aware list_tools implementation that triggers tool_list interactions
            async def hook_aware_list_tools(session_id: str, server_name: str = None, stage_execution_id: str = None):
                # Import the real hook context
                from tarsy.hooks.typed_context import mcp_list_context
                
                # Use the real hook context to record this tool discovery interaction
                async with mcp_list_context(session_id, server_name, stage_execution_id) as ctx:
                    # Generate tool list data like the real implementation
                    tools_data = {
                        "kubernetes-server": [
                            {"name": "get_namespace", "description": "Get namespace information"},
                            {"name": "patch_namespace", "description": "Patch namespace configuration"}, 
                            {"name": "check_status", "description": "Check resource status"},
                        ]
                    }
                    
                    # Update context with tool data (like the real MCP client does)
                    ctx.interaction.available_tools = tools_data
                    
                    # Complete context successfully (this triggers the hooks!)
                    await ctx.complete_success({})
                    
                    return tools_data
            
            mock_mcp_client_instance.list_tools = AsyncMock(side_effect=hook_aware_list_tools)
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
                
                # EXACT VALIDATION: Final verification of exact stage interaction counts (updated for tool_list)
                final_stage_exact_counts = {
                    "data-collection": {"llm": 4, "mcp": 4, "total": 8},  # ReAct: 4 LLM + 1 tool_list + 3 MCP tool calls
                    "verification": {"llm": 3, "mcp": 3, "total": 6},     # ReAct: 3 LLM + 1 tool_list + 2 MCP tool calls  
                    "analysis": {"llm": 1, "mcp": 0, "total": 1}          # react-final-analysis: 1 LLM + 0 MCP (no tools executed)
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