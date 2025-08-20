"""
Integration tests for multi-stage chain execution flow.

These tests verify that sequential agent chains work end-to-end with real
data flow between stages, complementing the comprehensive unit test coverage.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
from tarsy.models.constants import StageStatus
from tarsy.models.processing_context import ChainContext


@pytest.mark.asyncio
@pytest.mark.integration
class TestMultiStageChainExecution:
    """Integration tests for multi-stage chain execution - focused on data flow."""
    
    @pytest.fixture
    def simple_two_stage_chain(self):
        """Create a simple 2-stage chain for testing data flow."""
        return ChainConfigModel(
            chain_id="integration-test-chain",
            alert_types=["integration-test"],
            stages=[
                ChainStageConfigModel(
                    name="data-collection",
                    agent="DataCollectionAgent"
                ),
                ChainStageConfigModel(
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
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.constants import StageStatus
        
        data_collection_agent = AsyncMock()
        data_collection_agent.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="DataCollectionAgent",
            stage_name="data-collection",
            result_summary="Collected pod_info, events, logs data",
            timestamp_us=1234567890
        )
        data_collection_agent.set_current_stage_execution_id = Mock()
        
        # Second stage: Analysis Agent that uses data from first stage
        analysis_agent = AsyncMock()
        def mock_analysis(chain_context):
            # This is the key integration test: verify data flows between stages
            data_collection_result = chain_context.stage_outputs.get("data-collection")
            assert data_collection_result is not None, "Analysis stage should receive data collection results"
            assert data_collection_result.status == StageStatus.COMPLETED
            
            return AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="AnalysisAgent",
                stage_name="analysis",
                result_summary="Resource exhaustion detected from collected data",
                timestamp_us=1234567890
            )
        
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
        
        # Create initial chain context
        chain_context = ChainContext(
            alert_type="integration-test",
            alert_data={
                "severity": "high",
                "cluster": "test-cluster",
                "namespace": "default"
            },
            session_id="test-session-123",
            current_stage_name="analysis",
            runbook_content="Test runbook content"
        )
        
        session_id = "test-session-123"
        agents = mock_agents_with_data_flow
        
        # Simulate the chain execution flow that happens in AlertService._execute_chain_stages
        
        # Stage 1: Data Collection
        chain_context.set_chain_context(simple_two_stage_chain.chain_id, "data-collection")
        
        data_collection_agent = agents['DataCollectionAgent']
        stage1_result = await data_collection_agent.process_alert(chain_context)
        chain_context.add_stage_result("data-collection", stage1_result)
        
        # Stage 2: Analysis (should receive data from stage 1)
        chain_context.set_chain_context(simple_two_stage_chain.chain_id, "analysis")
        
        analysis_agent = agents['AnalysisAgent']
        stage2_result = await analysis_agent.process_alert(chain_context)
        chain_context.add_stage_result("analysis", stage2_result)
        
        # Verify the chain execution worked correctly
        
        # 1. Both agents were called
        data_collection_agent.process_alert.assert_called_once_with(chain_context)
        analysis_agent.process_alert.assert_called_once_with(chain_context)
        
        # 2. Data flowed between stages - stage 2 received stage 1 results
        analysis_result = chain_context.stage_outputs.get("analysis")
        assert analysis_result is not None
        assert analysis_result.status == StageStatus.COMPLETED
        assert "Resource exhaustion detected" in analysis_result.result_summary
        
        # 3. Chain context was maintained
        assert chain_context.chain_id == simple_two_stage_chain.chain_id
        assert chain_context.current_stage_name == "analysis"
        
        # 4. Both stage results are preserved
        assert "data-collection" in chain_context.stage_outputs
        assert "analysis" in chain_context.stage_outputs
        assert len(chain_context.stage_outputs) == 2
    
    async def test_stage_isolation_and_progression(self, simple_two_stage_chain, mock_agents_with_data_flow):
        """Test that stages are isolated but can access previous stage data."""
        chain_context = ChainContext(
            alert_type="integration-test",
            alert_data={"test": "isolation"},
            session_id="isolation-test-session",
            current_stage_name="data-collection"
        )
        
        session_id = "isolation-test-session"
        agents = mock_agents_with_data_flow
        
        # Execute stages sequentially (simulating AlertService behavior)
        for i, stage in enumerate(simple_two_stage_chain.stages):
            # Set stage context
            chain_context.current_stage_name = stage.name
            chain_context.chain_id = simple_two_stage_chain.chain_id
            
            # Get appropriate agent
            agent = agents[stage.agent]
            
            # Each agent should get a unique stage execution ID (simulated)
            stage_exec_id = f"exec_{i}_{stage.name}"
            agent.set_current_stage_execution_id(stage_exec_id)
            
            # Execute stage
            stage_result = await agent.process_alert(chain_context)
            chain_context.add_stage_result(stage.name, stage_result)
        
        # Verify stage isolation
        data_collection_agent = agents['DataCollectionAgent']
        analysis_agent = agents['AnalysisAgent']
        
        # Each agent got a unique execution ID
        data_collection_agent.set_current_stage_execution_id.assert_called_once_with("exec_0_data-collection")
        analysis_agent.set_current_stage_execution_id.assert_called_once_with("exec_1_analysis")
        
        # Both stages executed successfully
        data_collection_result = chain_context.stage_outputs.get("data-collection")
        analysis_result = chain_context.stage_outputs.get("analysis")
        assert data_collection_result is not None
        assert analysis_result is not None
        assert data_collection_result.status == StageStatus.COMPLETED
        assert analysis_result.status == StageStatus.COMPLETED


@pytest.mark.asyncio  
@pytest.mark.integration
class TestChainExecutionErrorHandling:
    """Integration tests for chain execution error scenarios."""
    
    async def test_chain_partial_execution_on_stage_failure(self):
        """Test that chain execution handles stage failures gracefully."""
        # Create chain with 2 stages where second stage will fail
        chain = ChainConfigModel(
            chain_id="failure-test-chain",
            alert_types=["failure-test"],
            stages=[
                ChainStageConfigModel(name="success-stage", agent="SuccessAgent"),
                ChainStageConfigModel(name="failure-stage", agent="FailureAgent")
            ]
        )
        
        # Create initial chain context
        chain_context = ChainContext(
            alert_type="failure-test",
            alert_data={"test": "failure scenario"},
            session_id="failure-test-session",
            current_stage_name="success-stage"
        )
        session_id = "failure-test-session"
        
        # Mock successful first agent
        from tarsy.models.agent_execution_result import AgentExecutionResult
        from tarsy.models.constants import StageStatus
        
        success_agent = AsyncMock()
        success_agent.process_alert.return_value = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="SuccessAgent",
            stage_name="success-stage",
            result_summary="first stage completed successfully",
            timestamp_us=1234567890
        )
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
            chain_context.set_chain_context(chain.chain_id, "success-stage")
            stage1_result = await success_agent.process_alert(chain_context)
            chain_context.add_stage_result("success-stage", stage1_result)
            successful_stages += 1
        except Exception:
            failed_stages += 1
        
        try:
            # Stage 2: Should fail
            chain_context.set_chain_context(chain.chain_id, "failure-stage")
            stage2_result = await failure_agent.process_alert(chain_context)
            chain_context.add_stage_result("failure-stage", stage2_result)
            successful_stages += 1
        except Exception as e:
            # This simulates how AlertService would handle the failure
            failed_stages += 1
            failure_message = str(e)
        
        # Verify partial execution behavior
        assert successful_stages == 1
        assert failed_stages == 1
        
        # Verify first stage completed successfully and data is preserved
        success_result = chain_context.stage_outputs.get("success-stage")
        assert success_result is not None
        assert success_result.status == StageStatus.COMPLETED
        assert "first stage completed successfully" in success_result.result_summary
        
        # Verify second stage failed and no result was stored
        failure_result = chain_context.stage_outputs.get("failure-stage")
        assert failure_result is None  # No result stored due to failure
        
        # Verify chain context reflects the failure point
        assert chain_context.current_stage_name == "failure-stage"
        
        # Verify both agents were called
        success_agent.process_alert.assert_called_once()
        failure_agent.process_alert.assert_called_once()
        
        # This demonstrates that the chain execution preserves successful stage results
        # even when later stages fail - which is important for debugging and recovery
