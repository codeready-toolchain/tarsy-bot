"""
Unit tests for ParallelStageExecutor.

Tests the parallel stage execution logic including multi-agent parallelism,
replicated agent execution, and result aggregation.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tarsy.models.agent_execution_result import (
    AgentExecutionMetadata,
    AgentExecutionResult,
    ParallelStageResult,
)
from tarsy.models.constants import SuccessPolicy, StageStatus, IterationStrategy
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
    
    def test_normalize_iteration_strategy_with_none(self):
        """Test that _normalize_iteration_strategy returns 'unknown' for None input."""
        result = ParallelStageExecutor._normalize_iteration_strategy(None)
        assert result == "unknown"
    
    def test_normalize_iteration_strategy_with_string(self):
        """Test that _normalize_iteration_strategy returns string as-is."""
        result = ParallelStageExecutor._normalize_iteration_strategy("react")
        assert result == "react"
    
    def test_normalize_iteration_strategy_with_enum(self):
        """Test that _normalize_iteration_strategy extracts .value from IterationStrategy enum."""
        result = ParallelStageExecutor._normalize_iteration_strategy(IterationStrategy.REACT)
        assert result == "react"
    
    def test_normalize_iteration_strategy_with_native_thinking_enum(self):
        """Test that _normalize_iteration_strategy extracts .value from NATIVE_THINKING enum."""
        result = ParallelStageExecutor._normalize_iteration_strategy(IterationStrategy.NATIVE_THINKING)
        assert result == "native-thinking"


@pytest.mark.unit
class TestOptionalFieldGuards:
    """Test that optional field guards prevent runtime errors."""
    
    @pytest.mark.asyncio
    async def test_execute_parallel_agents_raises_when_agents_is_none(self):
        """Test that execute_parallel_agents raises ValueError when stage.agents is None."""
        agent_factory = Mock()
        stage_manager = Mock()
        
        executor = ParallelStageExecutor(
            agent_factory=agent_factory,
            settings=MockFactory.create_mock_settings(),
            stage_manager=stage_manager
        )
        
        # Create stage with None agents (invalid for multi-agent execution)
        stage = SimpleNamespace(
            name="test-stage",
            agents=None,
            agent="some-agent",
            success_policy=SuccessPolicy.ANY
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
        
        chain_def = SimpleNamespace(llm_provider="default-provider")
        
        with pytest.raises(ValueError) as exc_info:
            await executor.execute_parallel_agents(
                stage=stage,
                chain_context=chain_context,
                session_mcp_client=Mock(),
                chain_definition=chain_def,
                stage_index=0
            )
        
        assert "requires 'agents' list" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_execute_replicated_agent_raises_when_agent_is_none(self):
        """Test that execute_replicated_agent raises ValueError when stage.agent is None."""
        agent_factory = Mock()
        stage_manager = Mock()
        
        executor = ParallelStageExecutor(
            agent_factory=agent_factory,
            settings=MockFactory.create_mock_settings(),
            stage_manager=stage_manager
        )
        
        # Create stage with None agent (invalid for replicated execution)
        stage = SimpleNamespace(
            name="test-stage",
            agent=None,
            agents=[SimpleNamespace(name="agent1")],
            replicas=3,
            success_policy=SuccessPolicy.ALL
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
        
        chain_def = SimpleNamespace(llm_provider="default-provider")
        
        with pytest.raises(ValueError) as exc_info:
            await executor.execute_replicated_agent(
                stage=stage,
                chain_context=chain_context,
                session_mcp_client=Mock(),
                chain_definition=chain_def,
                stage_index=0
            )
        
        assert "requires 'agent' field" in str(exc_info.value)


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
            from tarsy.models.constants import SuccessPolicy
            
            return ParallelStageResult(
                stage_name="investigation",
                results=[],
                metadata=ParallelStageMetadata(
                    parent_stage_execution_id="stage-exec-1",
                    parallel_type="multi_agent",
                    success_policy=SuccessPolicy.ANY,
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
                SimpleNamespace(name="agent1", llm_provider="openai", iteration_strategy="react", max_iterations=None, force_conclusion_at_max_iterations=None, mcp_servers=None),
                SimpleNamespace(name="agent2", llm_provider="anthropic", iteration_strategy="native-thinking", max_iterations=None, force_conclusion_at_max_iterations=None, mcp_servers=None)
            ],
            success_policy=SuccessPolicy.ANY,
            llm_provider=None,
            iteration_strategy=None,
            max_iterations=None,
            force_conclusion_at_max_iterations=None,
            mcp_servers=None
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
            llm_provider="default-provider",
            max_iterations=None,
            force_conclusion_at_max_iterations=None,
            mcp_servers=None
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
        assert configs[0]["execution_config"].llm_provider == "openai"
        assert configs[1]["agent_name"] == "agent2"
        assert configs[1]["execution_config"].llm_provider == "anthropic"
    
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
            from tarsy.models.constants import SuccessPolicy
            
            return ParallelStageResult(
                stage_name="investigation",
                results=[],
                metadata=ParallelStageMetadata(
                    parent_stage_execution_id="stage-exec-1",
                    parallel_type="replica",
                    success_policy=SuccessPolicy.ALL,
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
            success_policy=SuccessPolicy.ALL,
            max_iterations=None,
            force_conclusion_at_max_iterations=None,
            mcp_servers=None
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
            llm_provider=None,
            max_iterations=None,
            force_conclusion_at_max_iterations=None,
            mcp_servers=None
        )
        
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
class TestSynthesisParallelResultsCancellationHandling:
    """Test CancelledError handling in synthesize_parallel_results (invoke_synthesis)."""

    @pytest.mark.asyncio
    async def test_synthesis_handles_cancelled_error_with_timeout_reason(self) -> None:
        """Test that synthesis cancellation with timeout reason is handled correctly."""
        stage_manager = Mock()
        stage_manager.create_stage_execution = AsyncMock(return_value="synthesis-exec-1")
        stage_manager.update_stage_execution_started = AsyncMock()
        stage_manager.update_stage_execution_cancelled = AsyncMock()
        stage_manager.update_stage_execution_timed_out = AsyncMock()
        stage_manager.update_stage_execution_failed = AsyncMock()

        settings = MockFactory.create_mock_settings()

        # Create mock agent that raises CancelledError with timeout reason
        synthesis_agent = Mock()
        synthesis_agent.process_alert = AsyncMock(side_effect=asyncio.CancelledError("timeout"))
        synthesis_agent.set_current_stage_execution_id = Mock()

        agent_factory = Mock()
        agent_factory.get_agent_with_config = Mock(return_value=synthesis_agent)
        agent_factory.agent_configs = {}

        executor = ParallelStageExecutor(
            agent_factory=agent_factory,
            settings=settings,
            stage_manager=stage_manager,
        )

        # Build minimal parallel result
        from tarsy.models.agent_execution_result import ParallelStageMetadata
        from tarsy.models.constants import SuccessPolicy

        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="parent-exec-1",
                parallel_type="multi_agent",
                success_policy=SuccessPolicy.ANY,
                started_at_us=now_us(),
                completed_at_us=now_us(),
                agent_metadatas=[]
            ),
            status=StageStatus.COMPLETED,
            timestamp_us=now_us()
        )

        # Build chain context
        from tarsy.models.alert import ProcessingAlert
        alert = AlertFactory.create_kubernetes_alert()
        processing_alert = ProcessingAlert(
            alert_type=alert.alert_type or "kubernetes",
            severity=alert.data.get("severity", "critical"),
            timestamp=alert.timestamp,
            environment=alert.data.get("environment", "production"),
            runbook_url=alert.runbook,
            alert_data=alert.data,
        )
        chain_context = ChainContext.from_processing_alert(processing_alert=processing_alert, session_id="test-session")

        # Stage config with synthesis
        stage_config = SimpleNamespace(
            name="investigation",
            synthesis=None,  # Use defaults
            llm_provider=None,
            iteration_strategy=None,
            success_policy=SuccessPolicy.ANY
        )

        chain_def = SimpleNamespace(
            llm_provider="openai",
            max_iterations=None,
            force_conclusion_at_max_iterations=None,
            mcp_servers=None
        )

        # Mock the cancellation tracker to indicate timeout (not user cancellation)
        # This ensures deterministic test behavior regardless of shared state
        with patch('tarsy.services.cancellation_tracker.is_user_cancel', return_value=False):
            # Execute synthesis - should raise CancelledError
            with pytest.raises(asyncio.CancelledError):
                exec_id, result = await executor.synthesize_parallel_results(
                    parallel_result=parallel_result,
                    chain_context=chain_context,
                    session_mcp_client=Mock(),
                    stage_config=stage_config,
                    chain_definition=chain_def,
                    current_stage_index=1
                )

        # Verify stage was marked as timed out with formatted error message
        stage_manager.update_stage_execution_timed_out.assert_called_once_with(
            "synthesis-exec-1",
            "SynthesisAgent synthesis timed out"
        )

    @pytest.mark.asyncio
    async def test_synthesis_handles_cancelled_error_with_user_cancel_reason(self) -> None:
        """Test that synthesis cancellation with user_cancel reason is handled correctly."""
        stage_manager = Mock()
        stage_manager.create_stage_execution = AsyncMock(return_value="synthesis-exec-1")
        stage_manager.update_stage_execution_started = AsyncMock()
        stage_manager.update_stage_execution_cancelled = AsyncMock()
        stage_manager.update_stage_execution_timed_out = AsyncMock()
        stage_manager.update_stage_execution_failed = AsyncMock()

        settings = MockFactory.create_mock_settings()

        # Create mock agent that raises CancelledError with user_cancel reason
        synthesis_agent = Mock()
        synthesis_agent.process_alert = AsyncMock(side_effect=asyncio.CancelledError("user_cancel"))
        synthesis_agent.set_current_stage_execution_id = Mock()

        agent_factory = Mock()
        agent_factory.get_agent_with_config = Mock(return_value=synthesis_agent)
        agent_factory.agent_configs = {}

        executor = ParallelStageExecutor(
            agent_factory=agent_factory,
            settings=settings,
            stage_manager=stage_manager,
        )

        # Build minimal parallel result
        from tarsy.models.agent_execution_result import ParallelStageMetadata
        from tarsy.models.constants import SuccessPolicy

        parallel_result = ParallelStageResult(
            stage_name="investigation",
            results=[],
            metadata=ParallelStageMetadata(
                parent_stage_execution_id="parent-exec-1",
                parallel_type="multi_agent",
                success_policy=SuccessPolicy.ANY,
                started_at_us=now_us(),
                completed_at_us=now_us(),
                agent_metadatas=[]
            ),
            status=StageStatus.COMPLETED,
            timestamp_us=now_us()
        )

        # Build chain context
        from tarsy.models.alert import ProcessingAlert
        alert = AlertFactory.create_kubernetes_alert()
        processing_alert = ProcessingAlert(
            alert_type=alert.alert_type or "kubernetes",
            severity=alert.data.get("severity", "critical"),
            timestamp=alert.timestamp,
            environment=alert.data.get("environment", "production"),
            runbook_url=alert.runbook,
            alert_data=alert.data,
        )
        chain_context = ChainContext.from_processing_alert(processing_alert=processing_alert, session_id="test-session")

        stage_config = SimpleNamespace(
            name="investigation",
            synthesis=None,
            llm_provider=None,
            iteration_strategy=None,
            success_policy=SuccessPolicy.ANY
        )

        chain_def = SimpleNamespace(
            llm_provider="openai",
            max_iterations=None,
            force_conclusion_at_max_iterations=None,
            mcp_servers=None
        )

        # Mock the cancellation tracker to indicate user cancellation
        from unittest.mock import patch
        with patch('tarsy.services.cancellation_tracker.is_user_cancel', return_value=True), pytest.raises(asyncio.CancelledError):
            await executor.synthesize_parallel_results(
                parallel_result=parallel_result,
                chain_context=chain_context,
                session_mcp_client=Mock(),
                stage_config=stage_config,
                chain_definition=chain_def,
                current_stage_index=1
            )

        # Verify stage was marked as cancelled with formatted error message
        stage_manager.update_stage_execution_cancelled.assert_called_once_with(
            "synthesis-exec-1",
            "SynthesisAgent synthesis cancelled by user"
        )


@pytest.mark.unit
class TestParallelStageExecutorCancellationHandling:
    """Test CancelledError handling during parallel execution."""

    @pytest.mark.asyncio
    async def test_parallel_stage_handles_cancelled_error_from_gather(self) -> None:
        """Cancelled agents should not crash the stage; they should be marked TIMED_OUT (no user cancel) and not stay running."""
        stage_manager = Mock()
        stage_manager.create_stage_execution = AsyncMock(side_effect=["parent-exec", "child-exec-1", "child-exec-2"])
        stage_manager.update_stage_execution_started = AsyncMock()
        stage_manager.update_stage_execution_completed = AsyncMock()
        stage_manager.update_stage_execution_failed = AsyncMock()
        stage_manager.update_stage_execution_cancelled = AsyncMock()
        stage_manager.update_stage_execution_timed_out = AsyncMock()
        stage_manager.update_stage_execution_paused = AsyncMock()

        settings = MockFactory.create_mock_settings()

        # One agent will be cancelled, the other will complete successfully.
        completed_result = AgentExecutionResult(
            status=StageStatus.COMPLETED,
            agent_name="agent-2",
            stage_name="test-stage",
            timestamp_us=now_us(),
            result_summary="ok",
            error_message=None,
        )

        agent_ok = Mock()
        agent_ok.process_alert = AsyncMock(return_value=completed_result)
        agent_ok.set_current_stage_execution_id = Mock()
        agent_ok.set_parallel_execution_metadata = Mock()
        agent_ok.iteration_strategy = SimpleNamespace(value="react")

        agent_cancel = Mock()
        agent_cancel.process_alert = AsyncMock(side_effect=asyncio.CancelledError())
        agent_cancel.set_current_stage_execution_id = Mock()
        agent_cancel.set_parallel_execution_metadata = Mock()
        agent_cancel.iteration_strategy = SimpleNamespace(value="react")

        agent_factory = Mock()
        def _get_agent(*, agent_identifier, **_kwargs):  # noqa: ANN001
            return agent_cancel if agent_identifier == "agent-1" else agent_ok

        agent_factory.get_agent_with_config = Mock(side_effect=_get_agent)

        executor = ParallelStageExecutor(
            agent_factory=agent_factory,
            settings=settings,
            stage_manager=stage_manager,
        )

        # Build a minimal chain context
        from tarsy.models.alert import ProcessingAlert
        alert = AlertFactory.create_kubernetes_alert()
        processing_alert = ProcessingAlert(
            alert_type=alert.alert_type or "kubernetes",
            severity=alert.data.get("severity", "critical"),
            timestamp=alert.timestamp,
            environment=alert.data.get("environment", "production"),
            runbook_url=alert.runbook,
            alert_data=alert.data,
        )
        chain_context = ChainContext.from_processing_alert(processing_alert=processing_alert, session_id="test-session")

        stage = SimpleNamespace(name="test-stage", success_policy=SuccessPolicy.ANY, iteration_strategy="react")

        from tarsy.models.agent_execution_config import AgentExecutionConfig
        execution_configs = [
            {
                "agent_name": "agent-1",
                "execution_config": AgentExecutionConfig(
                    llm_provider="openai",
                    iteration_strategy="react",
                    max_iterations=None,
                    force_conclusion=None,
                    mcp_servers=None
                ),
                "iteration_strategy_original": "react"
            },
            {
                "agent_name": "agent-2",
                "execution_config": AgentExecutionConfig(
                    llm_provider="openai",
                    iteration_strategy="react",
                    max_iterations=None,
                    force_conclusion=None,
                    mcp_servers=None
                ),
                "iteration_strategy_original": "react"
            },
        ]

        result = await executor._execute_parallel_stage(
            stage=stage,
            chain_context=chain_context,
            session_mcp_client=Mock(),
            stage_index=0,
            execution_configs=execution_configs,
            parallel_type="multi_agent",
        )

        assert isinstance(result, ParallelStageResult)
        assert any(r.status == StageStatus.TIMED_OUT for r in result.results)
        assert any(r.status == StageStatus.COMPLETED for r in result.results)
        # Verify timed out agent was marked appropriately (error message contains "timed out")
        calls = stage_manager.update_stage_execution_timed_out.call_args_list
        assert len(calls) == 1
        assert calls[0][0][0] == "child-exec-1"
        assert "timed out" in calls[0][0][1].lower()


@pytest.mark.unit
class TestStatusAggregation:
    """Test status aggregation logic for parallel stages."""
    
    @pytest.mark.parametrize(
        "completed,failed,paused,policy,expected_status",
        [
            # PAUSED takes priority
            (2, 0, 1, SuccessPolicy.ALL, StageStatus.PAUSED),
            (2, 0, 1, SuccessPolicy.ANY, StageStatus.PAUSED),
            (0, 2, 1, SuccessPolicy.ALL, StageStatus.PAUSED),
            
            # ALL policy: all must succeed
            (3, 0, 0, SuccessPolicy.ALL, StageStatus.COMPLETED),
            (2, 1, 0, SuccessPolicy.ALL, StageStatus.FAILED),
            (0, 3, 0, SuccessPolicy.ALL, StageStatus.FAILED),
            
            # ANY policy: at least one must succeed
            (1, 2, 0, SuccessPolicy.ANY, StageStatus.COMPLETED),
            (0, 3, 0, SuccessPolicy.ANY, StageStatus.FAILED),
            (3, 0, 0, SuccessPolicy.ANY, StageStatus.COMPLETED),
        ],
    )
    def test_status_aggregation_logic(
        self, completed: int, failed: int, paused: int, policy: SuccessPolicy, expected_status: StageStatus
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
        
        # Call the actual aggregation method from ParallelStageExecutor
        executor = ParallelStageExecutor(
            agent_factory=Mock(),
            settings=MockFactory.create_mock_settings(),
            stage_manager=Mock()
        )
        actual_status = executor.aggregate_status(metadatas, policy)
        
        assert actual_status == expected_status
    
    @pytest.mark.parametrize(
        "completed,failed,cancelled,paused,policy,expected_status",
        [
            # CANCELLED treated like FAILED for success_policy evaluation
            # ANY policy with some CANCELLED
            (1, 0, 1, 0, SuccessPolicy.ANY, StageStatus.COMPLETED),  # 1 success is enough
            (0, 0, 3, 0, SuccessPolicy.ANY, StageStatus.FAILED),     # All cancelled = failed
            (1, 1, 1, 0, SuccessPolicy.ANY, StageStatus.COMPLETED),  # Mixed but has success
            
            # ALL policy with CANCELLED
            (2, 0, 1, 0, SuccessPolicy.ALL, StageStatus.FAILED),     # Any cancel = failed
            (0, 1, 2, 0, SuccessPolicy.ALL, StageStatus.FAILED),     # Mixed failed+cancelled
            
            # PAUSED still takes priority over CANCELLED
            (1, 0, 1, 1, SuccessPolicy.ANY, StageStatus.PAUSED),
            (0, 1, 1, 1, SuccessPolicy.ALL, StageStatus.PAUSED),
            
            # Edge case: all types present
            (1, 1, 1, 1, SuccessPolicy.ANY, StageStatus.PAUSED),  # Paused takes priority
        ],
    )
    def test_status_aggregation_with_cancelled(
        self, 
        completed: int, 
        failed: int, 
        cancelled: int,
        paused: int, 
        policy: SuccessPolicy, 
        expected_status: StageStatus
    ):
        """Test status aggregation with CANCELLED status included."""
        metadatas = []
        
        for i in range(completed):
            metadatas.append(
                AgentExecutionMetadata(
                    agent_name=f"agent-completed-{i}",
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
        
        for i in range(cancelled):
            metadatas.append(
                AgentExecutionMetadata(
                    agent_name=f"agent-cancelled-{i}",
                    llm_provider="openai",
                    iteration_strategy="react",
                    started_at_us=1000,
                    completed_at_us=2000,
                    status=StageStatus.CANCELLED,
                    error_message="Cancelled by user",
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
        
        executor = ParallelStageExecutor(
            agent_factory=Mock(),
            settings=MockFactory.create_mock_settings(),
            stage_manager=Mock()
        )
        actual_status = executor.aggregate_status(metadatas, policy)
        
        assert actual_status == expected_status

