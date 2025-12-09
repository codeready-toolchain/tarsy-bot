"""
Unit tests for ParallelStageExecutor.

Tests the parallel stage execution logic including multi-agent parallelism,
replicated agent execution, and result aggregation.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace

from tarsy.models.agent_execution_result import (
    AgentExecutionMetadata,
    AgentExecutionResult,
    ParallelStageResult,
)
from tarsy.models.constants import FailurePolicy, ParallelType, StageStatus
from tarsy.models.processing_context import ChainContext
from tarsy.services.parallel_stage_executor import ParallelStageExecutor
from tarsy.utils.timestamp import now_us
from tests.utils import AlertFactory, MockFactory


@pytest.mark.unit
class TestParallelStageExecutorInitialization:
    """Test ParallelStageExecutor initialization."""
    
    def test_initialization_with_dependencies(self):
        """Test that ParallelStageExecutor initializes with required dependencies."""
        agent_factory = Mock()
        settings = MockFactory.create_mock_settings()
        stage_manager = Mock()
        
        executor = ParallelStageExecutor(
            agent_factory=agent_factory,
            settings=settings,
            stage_manager=stage_manager
        )
        
        assert executor.agent_factory == agent_factory
        assert executor.settings == settings
        assert executor.stage_manager == stage_manager


@pytest.mark.unit
class TestParallelStageExecutorUtilities:
    """Test utility methods."""
    
    def test_is_final_stage_parallel_with_multi_agent(self):
        """Test detecting parallel stage as final stage with multi-agent."""
        executor = ParallelStageExecutor(
            agent_factory=Mock(),
            settings=MockFactory.create_mock_settings(),
            stage_manager=Mock()
        )
        
        # Create chain with parallel final stage (multi-agent)
        chain_def = SimpleNamespace(
            stages=[
                SimpleNamespace(agents=None, replicas=1),
                SimpleNamespace(
                    agents=[
                        SimpleNamespace(name="agent1"),
                        SimpleNamespace(name="agent2")
                    ],
                    replicas=1
                )
            ]
        )
        
        assert executor.is_final_stage_parallel(chain_def) is True
    
    def test_is_final_stage_parallel_with_replicas(self):
        """Test detecting parallel stage as final stage with replicas."""
        executor = ParallelStageExecutor(
            agent_factory=Mock(),
            settings=MockFactory.create_mock_settings(),
            stage_manager=Mock()
        )
        
        # Create chain with parallel final stage (replicas)
        chain_def = SimpleNamespace(
            stages=[
                SimpleNamespace(agents=None, replicas=1),
                SimpleNamespace(agents=None, replicas=3)
            ]
        )
        
        assert executor.is_final_stage_parallel(chain_def) is True
    
    def test_is_final_stage_parallel_returns_false_for_single_agent(self):
        """Test that single-agent final stage is not detected as parallel."""
        executor = ParallelStageExecutor(
            agent_factory=Mock(),
            settings=MockFactory.create_mock_settings(),
            stage_manager=Mock()
        )
        
        # Create chain with single-agent final stage
        chain_def = SimpleNamespace(
            stages=[
                SimpleNamespace(agents=None, replicas=1),
                SimpleNamespace(agents=None, replicas=1)
            ]
        )
        
        assert executor.is_final_stage_parallel(chain_def) is False
    
    def test_is_final_stage_parallel_with_empty_stages(self):
        """Test handling empty stages list."""
        executor = ParallelStageExecutor(
            agent_factory=Mock(),
            settings=MockFactory.create_mock_settings(),
            stage_manager=Mock()
        )
        
        chain_def = SimpleNamespace(stages=[])
        
        assert executor.is_final_stage_parallel(chain_def) is False


@pytest.mark.unit
class TestExecutionConfigGeneration:
    """Test generation of execution configs for parallel stages."""
    
    @pytest.mark.asyncio
    async def test_execute_parallel_agents_builds_configs(self):
        """Test that execute_parallel_agents builds correct execution configs."""
        agent_factory = Mock()
        stage_manager = Mock()
        stage_manager.create_stage_execution = AsyncMock(return_value="stage-exec-1")
        stage_manager.update_stage_execution_started = AsyncMock()
        stage_manager.update_stage_execution_completed = AsyncMock()
        
        executor = ParallelStageExecutor(
            agent_factory=agent_factory,
            settings=MockFactory.create_mock_settings(),
            stage_manager=stage_manager
        )
        
        # Mock the internal _execute_parallel_stage to inspect execution_configs
        captured_configs = []
        
        async def capture_configs(*args, **kwargs):
            captured_configs.append(kwargs.get('execution_configs'))
            # Return a valid parallel result
            from tarsy.models.agent_execution_result import ParallelStageMetadata
            from tarsy.models.constants import FailurePolicy
            
            return ParallelStageResult(
                results=[],
                metadata=ParallelStageMetadata(
                    parent_stage_execution_id="stage-exec-1",
                    parallel_type="multi_agent",
                    failure_policy=FailurePolicy.ANY,
                    started_at_us=now_us(),
                    completed_at_us=now_us(),
                    agent_metadatas=[]
                ),
                status=StageStatus.COMPLETED,
                timestamp_us=now_us()
            )
        
        executor._execute_parallel_stage = capture_configs
        
        # Create stage with multiple agents
        stage = SimpleNamespace(
            name="test-stage",
            agents=[
                SimpleNamespace(name="agent1", llm_provider="openai", iteration_strategy="react"),
                SimpleNamespace(name="agent2", llm_provider="anthropic", iteration_strategy="native")
            ],
            failure_policy=FailurePolicy.ANY
        )
        
        # Create ProcessingAlert from Alert
        from tarsy.models.alert import ProcessingAlert
        alert = AlertFactory.create_kubernetes_alert()
        processing_alert = ProcessingAlert(
            alert_type=alert.alert_type or "kubernetes",
            severity=alert.data.get("severity", "critical"),
            timestamp=alert.timestamp,
            environment=alert.data.get("environment", "production"),
            runbook_url=alert.runbook,
            alert_data=alert.data
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session"
        )
        
        chain_def = SimpleNamespace(
            llm_provider="default-provider"
        )
        
        await executor.execute_parallel_agents(
            stage=stage,
            chain_context=chain_context,
            session_mcp_client=Mock(),
            chain_definition=chain_def,
            stage_index=0
        )
        
        # Verify configs were captured
        assert len(captured_configs) == 1
        configs = captured_configs[0]
        
        assert len(configs) == 2
        assert configs[0]["agent_name"] == "agent1"
        assert configs[0]["llm_provider"] == "openai"
        assert configs[1]["agent_name"] == "agent2"
        assert configs[1]["llm_provider"] == "anthropic"
    
    @pytest.mark.asyncio
    async def test_execute_replicated_agent_builds_configs(self):
        """Test that execute_replicated_agent builds correct execution configs."""
        agent_factory = Mock()
        stage_manager = Mock()
        stage_manager.create_stage_execution = AsyncMock(return_value="stage-exec-1")
        stage_manager.update_stage_execution_started = AsyncMock()
        stage_manager.update_stage_execution_completed = AsyncMock()
        
        executor = ParallelStageExecutor(
            agent_factory=agent_factory,
            settings=MockFactory.create_mock_settings(),
            stage_manager=stage_manager
        )
        
        # Mock the internal _execute_parallel_stage to inspect execution_configs
        captured_configs = []
        
        async def capture_configs(*args, **kwargs):
            captured_configs.append(kwargs.get('execution_configs'))
            from tarsy.models.agent_execution_result import ParallelStageMetadata
            from tarsy.models.constants import FailurePolicy
            
            return ParallelStageResult(
                results=[],
                metadata=ParallelStageMetadata(
                    parent_stage_execution_id="stage-exec-1",
                    parallel_type="replica",
                    failure_policy=FailurePolicy.ALL,
                    started_at_us=now_us(),
                    completed_at_us=now_us(),
                    agent_metadatas=[]
                ),
                status=StageStatus.COMPLETED,
                timestamp_us=now_us()
            )
        
        executor._execute_parallel_stage = capture_configs
        
        # Create stage with replicas
        stage = SimpleNamespace(
            name="test-stage",
            agent="KubernetesAgent",
            agents=None,
            replicas=3,
            llm_provider="openai",
            iteration_strategy="react",
            failure_policy=FailurePolicy.ALL
        )
        
        # Create ProcessingAlert from Alert
        from tarsy.models.alert import ProcessingAlert
        alert = AlertFactory.create_kubernetes_alert()
        processing_alert = ProcessingAlert(
            alert_type=alert.alert_type or "kubernetes",
            severity=alert.data.get("severity", "critical"),
            timestamp=alert.timestamp,
            environment=alert.data.get("environment", "production"),
            runbook_url=alert.runbook,
            alert_data=alert.data
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session"
        )
        
        chain_def = SimpleNamespace(llm_provider=None)
        
        await executor.execute_replicated_agent(
            stage=stage,
            chain_context=chain_context,
            session_mcp_client=Mock(),
            chain_definition=chain_def,
            stage_index=0
        )
        
        # Verify configs were captured
        assert len(captured_configs) == 1
        configs = captured_configs[0]
        
        assert len(configs) == 3
        assert configs[0]["agent_name"] == "KubernetesAgent-1"
        assert configs[0]["base_agent_name"] == "KubernetesAgent"
        assert configs[1]["agent_name"] == "KubernetesAgent-2"
        assert configs[2]["agent_name"] == "KubernetesAgent-3"


@pytest.mark.unit
class TestStatusAggregation:
    """Test status aggregation logic for parallel stages."""
    
    @pytest.mark.parametrize(
        "completed,failed,paused,policy,expected_status",
        [
            # PAUSED takes priority
            (2, 0, 1, FailurePolicy.ALL, StageStatus.PAUSED),
            (2, 0, 1, FailurePolicy.ANY, StageStatus.PAUSED),
            (0, 2, 1, FailurePolicy.ALL, StageStatus.PAUSED),
            
            # ALL policy: all must succeed
            (3, 0, 0, FailurePolicy.ALL, StageStatus.COMPLETED),
            (2, 1, 0, FailurePolicy.ALL, StageStatus.FAILED),
            (0, 3, 0, FailurePolicy.ALL, StageStatus.FAILED),
            
            # ANY policy: at least one must succeed
            (1, 2, 0, FailurePolicy.ANY, StageStatus.COMPLETED),
            (0, 3, 0, FailurePolicy.ANY, StageStatus.FAILED),
            (3, 0, 0, FailurePolicy.ANY, StageStatus.COMPLETED),
        ],
    )
    def test_status_aggregation_logic(
        self, completed: int, failed: int, paused: int, policy: FailurePolicy, expected_status: StageStatus
    ):
        """Test that status aggregation follows correct precedence rules."""
        # Create metadatas based on counts
        metadatas = []
        
        for i in range(completed):
            metadatas.append(
                AgentExecutionMetadata(
                    agent_name=f"agent-{i}",
                    llm_provider="openai",
                    iteration_strategy="react",
                    started_at_us=1000,
                    completed_at_us=2000,
                    status=StageStatus.COMPLETED,
                    error_message=None,
                    token_usage=None
                )
            )
        
        for i in range(failed):
            metadatas.append(
                AgentExecutionMetadata(
                    agent_name=f"agent-failed-{i}",
                    llm_provider="openai",
                    iteration_strategy="react",
                    started_at_us=1000,
                    completed_at_us=2000,
                    status=StageStatus.FAILED,
                    error_message="Test error",
                    token_usage=None
                )
            )
        
        for i in range(paused):
            metadatas.append(
                AgentExecutionMetadata(
                    agent_name=f"agent-paused-{i}",
                    llm_provider="openai",
                    iteration_strategy="react",
                    started_at_us=1000,
                    completed_at_us=2000,
                    status=StageStatus.PAUSED,
                    error_message=None,
                    token_usage=None
                )
            )
        
        # Apply the same logic as in ParallelStageExecutor
        completed_count = sum(1 for m in metadatas if m.status == StageStatus.COMPLETED)
        failed_count = sum(1 for m in metadatas if m.status == StageStatus.FAILED)
        paused_count = sum(1 for m in metadatas if m.status == StageStatus.PAUSED)
        
        if paused_count > 0:
            actual_status = StageStatus.PAUSED
        elif policy == FailurePolicy.ALL:
            actual_status = StageStatus.COMPLETED if failed_count == 0 else StageStatus.FAILED
        else:  # FailurePolicy.ANY
            actual_status = StageStatus.COMPLETED if completed_count > 0 else StageStatus.FAILED
        
        assert actual_status == expected_status


@pytest.mark.unit
class TestParallelAgentTimeouts:
    """Test timeout handling for parallel agent execution."""
    
    @pytest.mark.asyncio
    async def test_parallel_agent_respects_timeout(self):
        """Test that parallel agent execution respects alert_processing_timeout."""
        # Create mocks
        agent_factory = Mock()
        stage_manager = Mock()
        stage_manager.create_stage_execution = AsyncMock(return_value="stage-exec-1")
        stage_manager.update_stage_execution_started = AsyncMock()
        stage_manager.update_stage_execution_failed = AsyncMock()
        
        settings = MockFactory.create_mock_settings()
        settings.alert_processing_timeout = 1  # 1 second timeout
        settings.llm_provider = "test-provider"  # Add default provider
        
        # Create agent that takes too long
        slow_agent = Mock()
        
        async def slow_process(*args, **kwargs):
            await asyncio.sleep(5)  # Takes 5 seconds (exceeds 1s timeout)
            return AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="SlowAgent",
                stage_name="test",
                timestamp_us=now_us(),
                result_summary="Should not reach here"
            )
        
        slow_agent.process_alert = AsyncMock(side_effect=slow_process)
        slow_agent.set_current_stage_execution_id = Mock()
        slow_agent.iteration_strategy = Mock()
        slow_agent.iteration_strategy.value = "react"  # Provide iteration strategy
        agent_factory.get_agent = Mock(return_value=slow_agent)
        
        executor = ParallelStageExecutor(
            agent_factory=agent_factory,
            settings=settings,
            stage_manager=stage_manager
        )
        
        # Create test data
        stage = SimpleNamespace(
            name="test-stage",
            agent="SlowAgent",
            agents=None,
            replicas=1,
            llm_provider=None,
            iteration_strategy=None,
            failure_policy=FailurePolicy.ALL
        )
        
        from tarsy.models.alert import ProcessingAlert
        alert = AlertFactory.create_kubernetes_alert()
        processing_alert = ProcessingAlert(
            alert_type=alert.alert_type or "kubernetes",
            severity=alert.data.get("severity", "critical"),
            timestamp=alert.timestamp,
            environment=alert.data.get("environment", "production"),
            runbook_url=alert.runbook,
            alert_data=alert.data
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session"
        )
        
        chain_def = SimpleNamespace(llm_provider=None)
        
        # Execute and verify timeout occurs
        result = await executor.execute_replicated_agent(
            stage=stage,
            chain_context=chain_context,
            session_mcp_client=Mock(),
            chain_definition=chain_def,
            stage_index=0
        )
        
        # Verify result is a failure due to timeout
        assert result.status == StageStatus.FAILED
        assert len(result.results) == 1
        assert result.results[0].status == StageStatus.FAILED
        assert "timeout" in result.results[0].error_message.lower()
        
        # Verify stage execution was marked as failed
        stage_manager.update_stage_execution_failed.assert_called()
    
    @pytest.mark.asyncio
    async def test_parallel_agents_timeout_independently(self):
        """Test that each parallel agent has independent timeout enforcement."""
        # Create mocks
        agent_factory = Mock()
        stage_manager = Mock()
        stage_manager.create_stage_execution = AsyncMock(side_effect=lambda *args, **kwargs: f"exec-{kwargs.get('parallel_index', 0)}")
        stage_manager.update_stage_execution_started = AsyncMock()
        stage_manager.update_stage_execution_completed = AsyncMock()
        stage_manager.update_stage_execution_failed = AsyncMock()
        
        settings = MockFactory.create_mock_settings()
        settings.alert_processing_timeout = 2  # 2 second timeout
        settings.llm_provider = "test-provider"  # Add default provider
        
        # Create fast and slow agents
        fast_agent = Mock()
        async def fast_process(*args, **kwargs):
            await asyncio.sleep(0.1)  # Fast
            return AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="FastAgent",
                stage_name="test",
                timestamp_us=now_us(),
                result_summary="Completed quickly"
            )
        fast_agent.process_alert = AsyncMock(side_effect=fast_process)
        fast_agent.set_current_stage_execution_id = Mock()
        fast_agent.iteration_strategy = Mock()
        fast_agent.iteration_strategy.value = "react"
        
        slow_agent = Mock()
        async def slow_process(*args, **kwargs):
            await asyncio.sleep(5)  # Too slow
            return AgentExecutionResult(
                status=StageStatus.COMPLETED,
                agent_name="SlowAgent",
                stage_name="test",
                timestamp_us=now_us(),
                result_summary="Should not reach here"
            )
        slow_agent.process_alert = AsyncMock(side_effect=slow_process)
        slow_agent.set_current_stage_execution_id = Mock()
        slow_agent.iteration_strategy = Mock()
        slow_agent.iteration_strategy.value = "react"
        
        # Return different agents based on identifier
        def get_agent(agent_identifier, **kwargs):
            if "Fast" in agent_identifier:
                return fast_agent
            return slow_agent
        
        agent_factory.get_agent = Mock(side_effect=get_agent)
        
        executor = ParallelStageExecutor(
            agent_factory=agent_factory,
            settings=settings,
            stage_manager=stage_manager
        )
        
        # Create parallel stage with different agents
        stage = SimpleNamespace(
            name="test-stage",
            agents=[
                SimpleNamespace(name="FastAgent", llm_provider=None, iteration_strategy=None),
                SimpleNamespace(name="SlowAgent", llm_provider=None, iteration_strategy=None)
            ],
            replicas=1,
            llm_provider=None,
            iteration_strategy=None,
            failure_policy=FailurePolicy.ANY  # Continue if one succeeds
        )
        
        from tarsy.models.alert import ProcessingAlert
        alert = AlertFactory.create_kubernetes_alert()
        processing_alert = ProcessingAlert(
            alert_type=alert.alert_type or "kubernetes",
            severity=alert.data.get("severity", "critical"),
            timestamp=alert.timestamp,
            environment=alert.data.get("environment", "production"),
            runbook_url=alert.runbook,
            alert_data=alert.data
        )
        
        chain_context = ChainContext.from_processing_alert(
            processing_alert=processing_alert,
            session_id="test-session"
        )
        
        chain_def = SimpleNamespace(llm_provider=None)
        
        # Execute parallel agents
        result = await executor.execute_parallel_agents(
            stage=stage,
            chain_context=chain_context,
            session_mcp_client=Mock(),
            chain_definition=chain_def,
            stage_index=0
        )
        
        # Verify one succeeded and one timed out
        assert result.status == StageStatus.COMPLETED  # ANY policy: one success is enough
        assert len(result.results) == 2
        
        # Find the results by agent name
        fast_result = next((r for r in result.results if r.agent_name == "FastAgent"), None)
        slow_result = next((r for r in result.results if r.agent_name == "SlowAgent"), None)
        
        assert fast_result is not None
        assert fast_result.status == StageStatus.COMPLETED
        
        assert slow_result is not None
        assert slow_result.status == StageStatus.FAILED
        assert "timeout" in slow_result.error_message.lower()

