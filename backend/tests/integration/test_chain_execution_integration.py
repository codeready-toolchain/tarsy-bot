"""
Integration tests for multi-stage chain execution flow.

These tests verify that sequential agent chains work end-to-end with real
data flow between stages, complementing the comprehensive unit test coverage.
"""

import pytest
from unittest.mock import AsyncMock, Mock

from tarsy.models.alert_processing import AlertProcessingData
from tarsy.models.chains import ChainDefinitionModel, ChainStageModel


@pytest.mark.asyncio
@pytest.mark.integration
class TestMultiStageChainExecution:
    """Integration tests for multi-stage chain execution - focused on data flow."""
    
    @pytest.fixture
    def simple_two_stage_chain(self):
        """Create a simple 2-stage chain for testing data flow."""
        return ChainDefinitionModel(
            chain_id="integration-test-chain",
            alert_types=["integration-test"],
            stages=[
                ChainStageModel(
                    name="data-collection",
                    agent="DataCollectionAgent"
                ),
                ChainStageModel(
                    name="analysis", 
                    agent="AnalysisAgent"
                )
            ],
            description="Simple 2-stage chain for integration testing"
        )
    
    @pytest.fixture
    def mock_agents_with_data_flow(self):
        """Create mock agents that demonstrate realistic data flow."""
        # First stage: Data Collection Agent
        data_collection_agent = AsyncMock()
        data_collection_agent.process_alert.return_value = {
            "status": "success",
            "collected_data": ["pod_info", "events", "logs"],
            "data_count": 3,
            "stage": "data-collection",
            "mcp_results": {
                "kubernetes-server": [
                    {"type": "pods", "count": 5},
                    {"type": "events", "count": 12}
                ]
            }
        }
        data_collection_agent.set_current_stage_execution_id = Mock()
        
        # Second stage: Analysis Agent that uses data from first stage
        analysis_agent = AsyncMock()
        def mock_analysis(alert_data, session_id):
            # This is the key integration test: verify data flows between stages
            data_collection_result = alert_data.get_stage_result("data-collection")
            assert data_collection_result is not None, "Analysis stage should receive data collection results"
            assert data_collection_result["collected_data"] == ["pod_info", "events", "logs"]
            
            # Verify MCP results are accessible from previous stages
            all_mcp = alert_data.get_all_mcp_results()
            assert "kubernetes-server" in all_mcp
            assert len(all_mcp["kubernetes-server"]) == 2
            
            return {
                "status": "success", 
                "root_cause": "Resource exhaustion detected from collected data",
                "confidence": 0.92,
                "used_previous_data": len(data_collection_result["collected_data"]),
                "analysis_based_on_mcp_count": len(all_mcp["kubernetes-server"]),
                "stage": "analysis"
            }
        
        analysis_agent.process_alert.side_effect = mock_analysis
        analysis_agent.set_current_stage_execution_id = Mock()
        
        return {
            'DataCollectionAgent': data_collection_agent,
            'AnalysisAgent': analysis_agent
        }
    
    async def test_multi_stage_data_flow_integration(self, simple_two_stage_chain, mock_agents_with_data_flow):
        """Test that data flows correctly between stages in a multi-stage chain."""
        # This is a focused integration test that simulates the core chain execution logic
        # without the complexity of full AlertService initialization
        
        # Create initial alert data
        alert_data = AlertProcessingData(
            alert_type="integration-test",
            alert_data={
                "severity": "high",
                "cluster": "test-cluster",
                "namespace": "default"
            },
            runbook_url="https://example.com/test-runbook.md"
        )
        alert_data.set_runbook_content("Test runbook content")
        
        session_id = "test-session-123"
        agents = mock_agents_with_data_flow
        
        # Simulate the chain execution flow that happens in AlertService._execute_chain_stages
        
        # Stage 1: Data Collection
        alert_data.set_chain_context(simple_two_stage_chain.chain_id, "data-collection")
        
        data_collection_agent = agents['DataCollectionAgent']
        stage1_result = await data_collection_agent.process_alert(alert_data, session_id)
        alert_data.add_stage_result("data-collection", stage1_result)
        
        # Stage 2: Analysis (should receive data from stage 1)
        alert_data.set_chain_context(simple_two_stage_chain.chain_id, "analysis")
        
        analysis_agent = agents['AnalysisAgent']
        stage2_result = await analysis_agent.process_alert(alert_data, session_id)  
        alert_data.add_stage_result("analysis", stage2_result)
        
        # Verify the chain execution worked correctly
        
        # 1. Both agents were called
        data_collection_agent.process_alert.assert_called_once_with(alert_data, session_id)
        analysis_agent.process_alert.assert_called_once_with(alert_data, session_id)
        
        # 2. Data flowed between stages - stage 2 received stage 1 results
        analysis_result = alert_data.get_stage_result("analysis")
        assert analysis_result["used_previous_data"] == 3  # Used 3 items from data collection
        assert analysis_result["analysis_based_on_mcp_count"] == 2  # Used 2 MCP results
        
        # 3. MCP results were merged correctly across stages
        all_mcp = alert_data.get_all_mcp_results()
        assert "kubernetes-server" in all_mcp
        assert len(all_mcp["kubernetes-server"]) == 2
        
        # 4. Chain context was maintained
        assert alert_data.chain_id == "integration-test-chain"
        assert alert_data.current_stage_name == "analysis"
        
        # 5. Both stage results are preserved
        assert "data-collection" in alert_data.stage_outputs
        assert "analysis" in alert_data.stage_outputs
        assert len(alert_data.stage_outputs) == 2
    
    async def test_stage_isolation_and_progression(self, simple_two_stage_chain, mock_agents_with_data_flow):
        """Test that stages are isolated but can access previous stage data."""
        alert_data = AlertProcessingData(
            alert_type="integration-test",
            alert_data={"test": "isolation"}
        )
        
        session_id = "isolation-test-session"
        agents = mock_agents_with_data_flow
        
        # Execute stages sequentially (simulating AlertService behavior)
        for i, stage in enumerate(simple_two_stage_chain.stages):
            # Set stage context
            alert_data.set_chain_context(simple_two_stage_chain.chain_id, stage.name)
            
            # Get appropriate agent
            agent = agents[stage.agent]
            
            # Each agent should get a unique stage execution ID (simulated)
            stage_exec_id = f"exec_{i}_{stage.name}"
            agent.set_current_stage_execution_id(stage_exec_id)
            
            # Execute stage
            stage_result = await agent.process_alert(alert_data, session_id)
            alert_data.add_stage_result(stage.name, stage_result)
        
        # Verify stage isolation
        data_collection_agent = agents['DataCollectionAgent']
        analysis_agent = agents['AnalysisAgent']
        
        # Each agent got a unique execution ID
        data_collection_agent.set_current_stage_execution_id.assert_called_once_with("exec_0_data-collection")
        analysis_agent.set_current_stage_execution_id.assert_called_once_with("exec_1_analysis")
        
        # Both stages executed successfully
        assert alert_data.get_stage_result("data-collection")["status"] == "success"
        assert alert_data.get_stage_result("analysis")["status"] == "success"


@pytest.mark.asyncio  
@pytest.mark.integration
class TestChainExecutionErrorHandling:
    """Integration tests for chain execution error scenarios."""
    
    async def test_chain_partial_execution_on_stage_failure(self):
        """Test that chain execution handles stage failures gracefully."""
        # Create chain with 2 stages where second stage will fail
        chain = ChainDefinitionModel(
            chain_id="failure-test-chain",
            alert_types=["failure-test"],
            stages=[
                ChainStageModel(name="success-stage", agent="SuccessAgent"),
                ChainStageModel(name="failure-stage", agent="FailureAgent")
            ]
        )
        
        # Create initial alert data
        alert_data = AlertProcessingData(
            alert_type="failure-test",
            alert_data={"test": "failure scenario"}
        )
        session_id = "failure-test-session"
        
        # Mock successful first agent
        success_agent = AsyncMock()
        success_agent.process_alert.return_value = {
            "status": "success",
            "result": "first stage completed successfully",
            "data_collected": ["item1", "item2"]
        }
        success_agent.set_current_stage_execution_id = Mock()
        
        # Mock failing second agent
        failure_agent = AsyncMock()
        failure_agent.process_alert.side_effect = Exception("Stage execution failed")
        failure_agent.set_current_stage_execution_id = Mock()
        
        # Simulate chain execution with failure handling
        successful_stages = 0
        failed_stages = 0
        
        try:
            # Stage 1: Should succeed
            alert_data.set_chain_context(chain.chain_id, "success-stage")
            stage1_result = await success_agent.process_alert(alert_data, session_id)
            alert_data.add_stage_result("success-stage", stage1_result)
            successful_stages += 1
        except Exception:
            failed_stages += 1
        
        try:
            # Stage 2: Should fail
            alert_data.set_chain_context(chain.chain_id, "failure-stage")
            stage2_result = await failure_agent.process_alert(alert_data, session_id)
            alert_data.add_stage_result("failure-stage", stage2_result)
            successful_stages += 1
        except Exception as e:
            # This simulates how AlertService would handle the failure
            failed_stages += 1
            failure_message = str(e)
        
        # Verify partial execution behavior
        assert successful_stages == 1
        assert failed_stages == 1
        
        # Verify first stage completed successfully and data is preserved
        success_result = alert_data.get_stage_result("success-stage")
        assert success_result is not None
        assert success_result["status"] == "success"
        assert success_result["result"] == "first stage completed successfully"
        
        # Verify second stage failed and no result was stored
        failure_result = alert_data.get_stage_result("failure-stage")
        assert failure_result is None  # No result stored due to failure
        
        # Verify chain context reflects the failure point
        assert alert_data.current_stage_name == "failure-stage"
        
        # Verify both agents were called
        success_agent.process_alert.assert_called_once()
        failure_agent.process_alert.assert_called_once()
        
        # This demonstrates that the chain execution preserves successful stage results
        # even when later stages fail - which is important for debugging and recovery
