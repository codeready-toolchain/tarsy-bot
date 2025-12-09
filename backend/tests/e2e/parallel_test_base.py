"""
Base class for parallel agent E2E tests.

This module provides reusable verification methods for all parallel execution E2E tests,
reducing duplication and improving maintainability.
"""

from .e2e_utils import assert_conversation_messages


class ParallelTestBase:
    """Base class with common verification methods for parallel execution E2E tests."""

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

    def _verify_parallel_stage_interactions(self, stage, expected_stage_spec, conversation_map=None):
        """
        Verify interactions for a parallel stage.
        
        Args:
            stage: The actual stage data from API
            expected_stage_spec: The expected stage specification
            conversation_map: Optional dict mapping agent names to their expected conversations
        """
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
                # Check both 'agent' and 'agent_name' keys for compatibility
                execution_agent_name = execution.get("agent") or execution.get("agent_name")
                if execution_agent_name == agent_name:
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
            
            # Get expected conversation for this agent (if provided)
            expected_conversation = None
            if conversation_map:
                expected_conversation = conversation_map.get(agent_name)
            
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
                    
                    # Verify conversation content if conversation expected and conversation_index provided
                    if expected_conversation and "conversation_index" in expected_interaction:
                        actual_conversation = details.get("conversation", {})
                        actual_messages = actual_conversation.get("messages", [])
                        
                        conversation_index = expected_interaction["conversation_index"]
                        assert_conversation_messages(
                            expected_conversation, actual_messages, conversation_index
                        )
                    
                    # Verify token usage
                    if "input_tokens" in expected_interaction:
                        actual_input = details.get("input_tokens")
                        expected_input = expected_interaction["input_tokens"]
                        assert actual_input == expected_input, (
                            f"Agent '{agent_name}' LLM interaction {i+1} input_tokens mismatch: expected {expected_input}, got {actual_input}"
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

    def _verify_single_stage_interactions(self, stage, expected_stage_spec, expected_conversation=None):
        """
        Verify interactions for a single (non-parallel) stage.
        
        Args:
            stage: The actual stage data from API
            expected_stage_spec: The expected stage specification
            expected_conversation: Optional expected conversation for this stage
        """
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
                
                # Verify conversation content if conversation expected and conversation_index provided
                if expected_conversation and "conversation_index" in expected_interaction:
                    actual_conversation = details.get("conversation", {})
                    actual_messages = actual_conversation.get("messages", [])
                    
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

    def _verify_complete_interaction_flow(self, stages, expected_stages_spec, conversation_map=None):
        """
        Verify complete interaction flow for all stages.
        
        Args:
            stages: List of actual stages from API
            expected_stages_spec: Dict mapping stage names to their expected specifications
            conversation_map: Optional dict mapping stage/agent names to expected conversations
        """
        print("  🔍 Verifying complete interaction flow...")
        
        for stage in stages:
            stage_name = stage["stage_name"]
            expected_stage_spec = expected_stages_spec.get(stage_name)
            
            assert expected_stage_spec is not None, (
                f"No expected spec found for stage '{stage_name}'"
            )
            
            if expected_stage_spec["type"] == "parallel":
                # Get agent conversation map if provided
                agent_conv_map = None
                if conversation_map and stage_name in conversation_map:
                    agent_conv_map = conversation_map[stage_name]
                
                self._verify_parallel_stage_interactions(stage, expected_stage_spec, agent_conv_map)
            else:
                # Get expected conversation for this stage if provided
                expected_conversation = None
                if conversation_map and stage_name in conversation_map:
                    expected_conversation = conversation_map[stage_name]
                
                self._verify_single_stage_interactions(stage, expected_stage_spec, expected_conversation)
        
        print("    ✅ Complete interaction flow verified")

