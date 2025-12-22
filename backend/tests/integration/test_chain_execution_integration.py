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
        async def mock_analysis(chain_context):
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
    
    @pytest.mark.asyncio
    async def test_multi_stage_data_flow_integration(self, simple_two_stage_chain, mock_agents_with_data_flow):
        """Test that data flows correctly between stages in a multi-stage chain."""
        # This is a focused integration test that simulates the core chain execution logic
        # without the complexity of full AlertService initialization
        
        # Create initial chain context
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="integration-test",
            severity="high",
            timestamp=now_us(),
            environment="production",
            alert_data={
                "severity": "high",
                "cluster": "test-cluster",
                "namespace": "default"
            }
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session-123",
            current_stage_name="analysis"
        )
        chain_context.runbook_content = "Test runbook content"
        
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
    
    @pytest.mark.asyncio
    async def test_stage_isolation_and_progression(self, simple_two_stage_chain, mock_agents_with_data_flow):
        """Test that stages are isolated but can access previous stage data."""
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="integration-test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "isolation"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
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
    
    @pytest.mark.asyncio
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
        from tarsy.models.alert import ProcessingAlert
        from tarsy.utils.timestamp import now_us
        
        processing_alert = ProcessingAlert(
            alert_type="failure-test",
            severity="warning",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "failure scenario"}
        )
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
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


@pytest.mark.asyncio
@pytest.mark.integration
class TestParallelStageChainExecution:
    """Integration tests for chains with parallel stages."""
    
    @pytest.fixture
    def parallel_stage_followed_by_single_chain(self):
        """Create chain with parallel stage followed by single-agent stage."""
        from tarsy.models.agent_config import ParallelAgentConfig
        
        return ChainConfigModel(
            chain_id="parallel-then-single-chain",
            alert_types=["parallel-integration"],
            stages=[
                ChainStageConfigModel(
                    name="investigation",
                    agents=[
                        ParallelAgentConfig(name="InvestigatorAgent1"),
                        ParallelAgentConfig(name="InvestigatorAgent2")
                    ]
                ),
                ChainStageConfigModel(
                    name="synthesis",
                    agent="SynthesisAgent"
                )
            ]
        )
    
    @pytest.fixture
    def parallel_stage_as_final_chain(self):
        """Create chain with parallel stage as final stage (auto-synthesis)."""
        from tarsy.models.agent_config import ParallelAgentConfig
        
        return ChainConfigModel(
            chain_id="parallel-final-chain",
            alert_types=["parallel-final"],
            stages=[
                ChainStageConfigModel(
                    name="investigation",
                    agents=[
                        ParallelAgentConfig(name="Agent1"),
                        ParallelAgentConfig(name="Agent2")
                    ]
                )
            ]
        )
    
    @pytest.fixture
    def mixed_single_and_parallel_chain(self):
        """Create chain mixing single-agent and parallel stages."""
        from tarsy.models.agent_config import ParallelAgentConfig
        
        return ChainConfigModel(
            chain_id="mixed-chain",
            alert_types=["mixed-test"],
            stages=[
                ChainStageConfigModel(
                    name="data-collection",
                    agent="DataCollectorAgent"
                ),
                ChainStageConfigModel(
                    name="parallel-analysis",
                    agents=[
                        ParallelAgentConfig(name="Analyzer1"),
                        ParallelAgentConfig(name="Analyzer2")
                    ]
                ),
                ChainStageConfigModel(
                    name="reporting",
                    agent="ReportAgent"
                )
            ]
        )
    
    @pytest.mark.asyncio
    async def test_chain_with_parallel_stage_followed_by_single_stage(
        self, parallel_stage_followed_by_single_chain
    ) -> None:
        """Test chain with parallel stage followed by single-agent stage."""
        from tarsy.models.agent_execution_result import (
            AgentExecutionMetadata,
            AgentExecutionResult,
            ParallelStageMetadata,
            ParallelStageResult,
        )
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.constants import SuccessPolicy, StageStatus
        from tarsy.utils.timestamp import now_us
        
        # Validate chain structure from fixture
        chain = parallel_stage_followed_by_single_chain
        assert len(chain.stages) == 2
        assert chain.stages[0].name == "investigation"
        assert chain.stages[0].agents is not None  # Parallel stage
        assert chain.stages[1].name == "synthesis"
        assert chain.stages[1].agent == "SynthesisAgent"  # Single agent
        
        processing_alert = ProcessingAlert(
            alert_type="parallel-integration",
            severity="high",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"}
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-parallel-session",
            current_stage_name=chain.stages[0].name  # Use fixture's stage name
        )
        
        timestamp = now_us()
        
        # Create parallel result for first stage using fixture's stage name
        parallel_result = ParallelStageResult(
            stage_name=chain.stages[0].name,  # "investigation"
            results=[
                AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="InvestigatorAgent1",
                    stage_name=chain.stages[0].name,
                    timestamp_us=timestamp,
                    result_summary="Investigation 1 completed"
                ),
                AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="InvestigatorAgent2",
                    stage_name=chain.stages[0].name,
                    timestamp_us=timestamp,
                    result_summary="Investigation 2 completed"
                )
            ],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="exec-parallel",
                parallel_type="multi_agent",
                success_policy=SuccessPolicy.ALL,
                started_at_us=timestamp - 5_000_000,
                completed_at_us=timestamp,
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="InvestigatorAgent1",
                        llm_provider="openai",
                        iteration_strategy="react",
                        started_at_us=timestamp - 5_000_000,
                        completed_at_us=timestamp,
                        status=StageStatus.COMPLETED
                    ),
                    AgentExecutionMetadata(
                        agent_name="InvestigatorAgent2",
                        llm_provider="anthropic",
                        iteration_strategy="react",
                        started_at_us=timestamp - 5_000_000,
                        completed_at_us=timestamp,
                        status=StageStatus.COMPLETED
                    )
                ]
            ),
            status=StageStatus.COMPLETED,
            timestamp_us=timestamp
        )
        
        chain_context.add_stage_result(chain.stages[0].name, parallel_result)
        
        # Verify parallel stage results and context
        assert chain_context.is_parallel_stage(chain.stages[0].name)
        assert len(chain_context.stage_outputs) == 1
        
        # Simulate moving to synthesis stage (second stage in chain)
        chain_context.current_stage_name = chain.stages[1].name
        
        # get_previous_stage_results() returns ALL completed stages (not stage-aware)
        # At this point, we have 1 completed stage ("investigation")
        previous_results = chain_context.get_previous_stage_results()
        assert len(previous_results) == 1
        
        # Convert to dict for order-independent assertions
        results_dict = {stage_name: result for stage_name, result in previous_results}
        
        # Verify the investigation stage result
        assert chain.stages[0].name in results_dict
        investigation_result = results_dict[chain.stages[0].name]
        assert isinstance(investigation_result, ParallelStageResult)
        
        # Verify per-agent results have stage_name set
        assert len(investigation_result.results) == 2
        for agent_result in investigation_result.results:
            assert isinstance(agent_result, AgentExecutionResult)
            assert agent_result.stage_name == chain.stages[0].name
    
    @pytest.mark.asyncio
    async def test_chain_with_parallel_stage_as_final(
        self, parallel_stage_as_final_chain
    ) -> None:
        """Test chain with parallel stage as final stage (requires auto-synthesis)."""
        from tarsy.models.agent_execution_result import (
            AgentExecutionMetadata,
            AgentExecutionResult,
            ParallelStageMetadata,
            ParallelStageResult,
        )
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.constants import SuccessPolicy, StageStatus
        from tarsy.utils.timestamp import now_us
        
        # Validate chain structure from fixture
        chain = parallel_stage_as_final_chain
        assert len(chain.stages) == 1
        assert chain.stages[0].name == "investigation"
        assert chain.stages[0].agents is not None  # Parallel stage as final
        
        processing_alert = ProcessingAlert(
            alert_type="parallel-final",
            severity="high",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"}
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-final-parallel",
            current_stage_name=chain.stages[0].name  # Use fixture's stage name
        )
        
        timestamp = now_us()
        
        # Create parallel result using fixture's stage name
        parallel_result = ParallelStageResult(
            stage_name=chain.stages[0].name,  # "investigation"
            results=[
                AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="Agent1",
                    stage_name=chain.stages[0].name,
                    timestamp_us=timestamp,
                    result_summary="Agent1 analysis"
                ),
                AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="Agent2",
                    stage_name=chain.stages[0].name,
                    timestamp_us=timestamp,
                    result_summary="Agent2 analysis"
                )
            ],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="exec-final",
                parallel_type="multi_agent",
                success_policy=SuccessPolicy.ALL,
                started_at_us=timestamp - 5_000_000,
                completed_at_us=timestamp,
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="Agent1",
                        llm_provider="openai",
                        iteration_strategy="react",
                        started_at_us=timestamp - 5_000_000,
                        completed_at_us=timestamp,
                        status=StageStatus.COMPLETED
                    ),
                    AgentExecutionMetadata(
                        agent_name="Agent2",
                        llm_provider="anthropic",
                        iteration_strategy="react",
                        started_at_us=timestamp - 5_000_000,
                        completed_at_us=timestamp,
                        status=StageStatus.COMPLETED
                    )
                ]
            ),
            status=StageStatus.COMPLETED,
            timestamp_us=timestamp
        )
        
        chain_context.add_stage_result(chain.stages[0].name, parallel_result)
        
        # Verify this is a parallel stage as final stage (requires auto-synthesis)
        last_result = chain_context.get_last_stage_result()
        assert isinstance(last_result, ParallelStageResult)
        assert last_result.stage_name == chain.stages[0].name
        assert last_result.metadata.parallel_type == "multi_agent"
    
    @pytest.mark.asyncio
    async def test_chain_mixing_single_and_parallel_stages(
        self, mixed_single_and_parallel_chain
    ) -> None:
        """Test chain with both single-agent and parallel stages."""
        from tarsy.models.agent_execution_result import (
            AgentExecutionMetadata,
            AgentExecutionResult,
            ParallelStageMetadata,
            ParallelStageResult,
        )
        from tarsy.models.alert import ProcessingAlert
        from tarsy.models.constants import SuccessPolicy, StageStatus
        from tarsy.utils.timestamp import now_us
        
        # Validate chain structure from fixture
        chain = mixed_single_and_parallel_chain
        assert len(chain.stages) == 3
        assert chain.stages[0].name == "data-collection"
        assert chain.stages[0].agent == "DataCollectorAgent"  # Single agent
        assert chain.stages[1].name == "parallel-analysis"
        assert chain.stages[1].agents is not None  # Parallel stage
        assert chain.stages[2].name == "reporting"
        assert chain.stages[2].agent == "ReportAgent"  # Single agent
        
        processing_alert = ProcessingAlert(
            alert_type="mixed-test",
            severity="high",
            timestamp=now_us(),
            environment="production",
            alert_data={"test": "data"}
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-mixed-session",
            current_stage_name=chain.stages[0].name  # Use fixture's stage name
        )
        
        timestamp = now_us()
        
        # Stage 1: Single-agent data collection
        single_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="DataCollectorAgent",
            stage_name=chain.stages[0].name,
            timestamp_us=timestamp,
            result_summary="Data collected"
        )
        chain_context.add_stage_result(chain.stages[0].name, single_result)
        
        # Stage 2: Parallel analysis
        parallel_result = ParallelStageResult(
            stage_name=chain.stages[1].name,  # "parallel-analysis"
            results=[
                AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="Analyzer1",
                    stage_name=chain.stages[1].name,
                    timestamp_us=timestamp,
                    result_summary="Analysis 1"
                ),
                AgentExecutionResult(
                    status=StageStatus.COMPLETED,
                    agent_name="Analyzer2",
                    stage_name=chain.stages[1].name,
                    timestamp_us=timestamp,
                    result_summary="Analysis 2"
                )
            ],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="exec-parallel-analysis",
                parallel_type="multi_agent",
                success_policy=SuccessPolicy.ALL,
                started_at_us=timestamp - 5_000_000,
                completed_at_us=timestamp,
                agent_metadatas=[
                    AgentExecutionMetadata(
                        agent_name="Analyzer1",
                        llm_provider="openai",
                        iteration_strategy="react",
                        started_at_us=timestamp - 5_000_000,
                        completed_at_us=timestamp,
                        status=StageStatus.COMPLETED
                    ),
                    AgentExecutionMetadata(
                        agent_name="Analyzer2",
                        llm_provider="anthropic",
                        iteration_strategy="react",
                        started_at_us=timestamp - 5_000_000,
                        completed_at_us=timestamp,
                        status=StageStatus.COMPLETED
                    )
                ]
            ),
            status=StageStatus.COMPLETED,
            timestamp_us=timestamp
        )
        chain_context.add_stage_result(chain.stages[1].name, parallel_result)
        
        # Stage 3: Single-agent reporting
        final_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="ReportAgent",
            stage_name=chain.stages[2].name,
            timestamp_us=timestamp,
            result_summary="Report generated"
        )
        chain_context.add_stage_result(chain.stages[2].name, final_result)
        
        # Verify mixed chain structure
        assert len(chain_context.stage_outputs) == 3
        assert not chain_context.is_parallel_stage(chain.stages[0].name)  # single
        assert chain_context.is_parallel_stage(chain.stages[1].name)  # parallel
        assert not chain_context.is_parallel_stage(chain.stages[2].name)  # single
        
        # Simulate moving to reporting stage to check previous results
        chain_context.current_stage_name = chain.stages[2].name
        
        # get_previous_stage_results() returns ALL completed stages (not stage-aware)
        # At this point, we have all 3 stages completed
        previous_results = chain_context.get_previous_stage_results()
        assert len(previous_results) == 3
        
        # Convert to dict for order-independent assertions
        results_dict = {stage_name: result for stage_name, result in previous_results}
        
        # Verify all stages are present
        assert chain.stages[0].name in results_dict  # data-collection
        assert chain.stages[1].name in results_dict  # parallel-analysis
        assert chain.stages[2].name in results_dict  # reporting
        
        # Verify data-collection is single-agent result
        assert isinstance(results_dict[chain.stages[0].name], AgentExecutionResult)
        
        # Verify parallel-analysis is ParallelStageResult with stage_name on per-agent results
        parallel_stage_result = results_dict[chain.stages[1].name]
        assert isinstance(parallel_stage_result, ParallelStageResult)
        assert len(parallel_stage_result.results) == 2
        for agent_result in parallel_stage_result.results:
            assert isinstance(agent_result, AgentExecutionResult)
            assert agent_result.stage_name == chain.stages[1].name
        
        # Verify reporting is single-agent result
        assert isinstance(results_dict[chain.stages[2].name], AgentExecutionResult)
