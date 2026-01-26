"""
Parallel Stage Executor for multi-agent and replicated agent execution.

This module handles all parallel execution logic for alert processing chains,
including multi-agent parallelism, agent replication, pause/resume functionality,
and automatic synthesis of parallel results.
"""

import asyncio
from typing import TYPE_CHECKING, Any, Union

from tarsy.agents.exceptions import SessionPaused
from tarsy.config.settings import Settings
from tarsy.integrations.mcp.client import MCPClient
from tarsy.models.agent_execution_result import (
    AgentExecutionMetadata,
    AgentExecutionResult,
    ParallelStageMetadata,
    ParallelStageResult,
)
from tarsy.models.constants import SuccessPolicy, ParallelType, StageStatus, IterationStrategy  # FailurePolicy is backward compat alias
from tarsy.models.processing_context import ChainContext
from tarsy.services.execution_config_resolver import ExecutionConfigResolver
from tarsy.utils.agent_execution_utils import build_agent_result_from_exception
from tarsy.utils.logger import get_module_logger
from tarsy.utils.timestamp import now_us

if TYPE_CHECKING:
    from tarsy.models.agent_config import ChainConfigModel, ChainStageConfigModel
    from tarsy.models.db_models import StageExecution
    from tarsy.services.agent_factory import AgentFactory
    from tarsy.services.history_service import HistoryService
    from tarsy.services.stage_execution_manager import StageExecutionManager

logger = get_module_logger(__name__)


class ParallelStageExecutor:
    """
    Executes parallel stages (multi-agent and replicated) in agent chains.
    
    This class handles:
    - Multi-agent parallel execution (different agents investigating in parallel)
    - Replicated agent execution (same agent running multiple times for redundancy)
    - Pause/resume functionality for parallel stages
    - Automatic synthesis of parallel results using SynthesisAgent
    """
    
    def __init__(
        self,
        agent_factory: "AgentFactory",
        settings: Settings,
        stage_manager: "StageExecutionManager"
    ):
        """
        Initialize the parallel stage executor.
        
        Args:
            agent_factory: Factory for creating agent instances
            settings: Application settings
            stage_manager: Manager for stage execution lifecycle
        """
        self.agent_factory = agent_factory
        self.settings = settings
        self.stage_manager = stage_manager
    
    @staticmethod
    def _normalize_iteration_strategy(strategy: Union[str, IterationStrategy, None]) -> str:
        """
        Normalize iteration strategy to string representation.
        
        Converts IterationStrategy enum values to their string representation
        to prevent Enum leakage into database and metadata.
        
        Args:
            strategy: Either a string, IterationStrategy enum value, or None
            
        Returns:
            String representation of the strategy (returns "unknown" for None)
        """
        if strategy is None:
            return "unknown"
        return getattr(strategy, "value", strategy)
    
    async def _handle_stage_cancellation(
        self,
        session_id: str,
        stage_execution_id: str,
        description: str,
    ) -> tuple[str, str]:
        """
        Handle stage cancellation by checking tracker and updating stage status.
        
        Determines whether cancellation was user-initiated or due to timeout,
        updates the stage execution status accordingly, and logs the result.
        
        Args:
            session_id: Session ID to check in cancellation tracker
            stage_execution_id: Stage execution ID to update
            description: Human-readable description (e.g., "Agent 'KubernetesAgent'")
            
        Returns:
            Tuple of (reason, error_msg) where reason is the CancellationReason value
            and error_msg is the descriptive message stored in the database.
        """
        from tarsy.services.cancellation_tracker import is_user_cancel
        from tarsy.models.constants import CancellationReason
        
        if is_user_cancel(session_id):
            reason = CancellationReason.USER_CANCEL.value
            error_msg = f"{description} cancelled by user"
            await self.stage_manager.update_stage_execution_cancelled(stage_execution_id, error_msg)
        else:
            reason = CancellationReason.TIMEOUT.value
            error_msg = f"{description} timed out"
            await self.stage_manager.update_stage_execution_timed_out(stage_execution_id, error_msg)
        
        logger.warning(error_msg)
        return reason, error_msg
    
    async def execute_parallel_agents(
        self,
        stage: "ChainStageConfigModel",
        chain_context: ChainContext,
        session_mcp_client: MCPClient,
        chain_definition: "ChainConfigModel",
        stage_index: int
    ) -> ParallelStageResult:
        """Execute multiple different agents in parallel for independent domain investigation."""
        if not stage.agents:
            raise ValueError(f"Stage '{stage.name}' requires 'agents' list for parallel execution")
        
        logger.info(f"Executing parallel stage '{stage.name}' with {len(stage.agents)} agents")
        
        # Build execution configs for each agent using unified resolver
        execution_configs = []
        for agent_config in stage.agents:
            # Get agent definition if it exists
            agent_def = self.agent_factory.agent_configs.get(agent_config.name) if self.agent_factory.agent_configs else None
            
            # Resolve unified execution config from hierarchy
            exec_config = ExecutionConfigResolver.resolve_config(
                system_settings=self.settings,
                agent_config=agent_def,
                chain_config=chain_definition,
                stage_config=stage,
                parallel_agent_config=agent_config
            )
            
            execution_configs.append({
                "agent_name": agent_config.name,
                "execution_config": exec_config,
                "iteration_strategy_original": agent_config.iteration_strategy,  # Keep original for Pydantic validation
            })
        
        return await self._execute_parallel_stage(
            stage=stage,
            chain_context=chain_context,
            session_mcp_client=session_mcp_client,
            stage_index=stage_index,
            execution_configs=execution_configs,
            parallel_type=ParallelType.MULTI_AGENT.value
        )
    
    async def execute_replicated_agent(
        self,
        stage: "ChainStageConfigModel",
        chain_context: ChainContext,
        session_mcp_client: MCPClient,
        chain_definition: "ChainConfigModel",
        stage_index: int
    ) -> ParallelStageResult:
        """Run same agent N times with identical configuration for accuracy via redundancy."""
        if not stage.agent:
            raise ValueError(f"Stage '{stage.name}' requires 'agent' field for replicated execution")
        
        logger.info(f"Executing replicated stage '{stage.name}' with {stage.replicas} replicas of agent '{stage.agent}'")
        
        # Resolve unified execution configuration from hierarchy (same for all replicas)
        # Get agent definition if it exists
        agent_def = self.agent_factory.agent_configs.get(stage.agent) if self.agent_factory.agent_configs else None
        
        # Resolve unified execution config (replicas don't have parallel_agent_config)
        execution_config = ExecutionConfigResolver.resolve_config(
            system_settings=self.settings,
            agent_config=agent_def,
            chain_config=chain_definition,
            stage_config=stage,
            parallel_agent_config=None  # Replicas don't have individual config
        )
        
        # Build execution configs for each replica (all share the same execution_config)
        execution_configs = [
            {
                "agent_name": f"{stage.agent}-{idx + 1}",  # Replica naming
                "base_agent_name": stage.agent,  # Original agent name
                "execution_config": execution_config,
                "iteration_strategy_original": stage.iteration_strategy,  # Keep original for Pydantic validation
            }
            for idx in range(stage.replicas)
        ]
        
        return await self._execute_parallel_stage(
            stage=stage,
            chain_context=chain_context,
            session_mcp_client=session_mcp_client,
            stage_index=stage_index,
            execution_configs=execution_configs,
            parallel_type=ParallelType.REPLICA.value
        )
    
    def aggregate_status(
        self,
        metadatas: list[AgentExecutionMetadata],
        success_policy: SuccessPolicy
    ) -> StageStatus:
        """
        Aggregate individual agent statuses into overall stage status.
        
        Priority order:
        1. PAUSED: If any agent paused, whole stage is paused (enables resume)
        2. SuccessPolicy evaluation: Treat TIMED_OUT/CANCELLED/FAILED as non-successes
        3. Failure status selection: Use TIMED_OUT only when it's the dominant failure reason
        
        Args:
            metadatas: List of agent execution metadata
            success_policy: Policy for success criteria (ALL or ANY)
            
        Returns:
            Aggregated stage status (COMPLETED, FAILED, TIMED_OUT, CANCELLED, or PAUSED)
        """
        # Count by status
        completed_count = sum(1 for m in metadatas if m.status == StageStatus.COMPLETED)
        failed_count = sum(1 for m in metadatas if m.status == StageStatus.FAILED)
        cancelled_count = sum(1 for m in metadatas if m.status == StageStatus.CANCELLED)
        timed_out_count = sum(1 for m in metadatas if m.status == StageStatus.TIMED_OUT)
        paused_count = sum(1 for m in metadatas if m.status == StageStatus.PAUSED)
        
        # PAUSED takes priority over everything - if any agent paused, whole stage is paused
        if paused_count > 0:
            return StageStatus.PAUSED
        
        # Treat CANCELLED and TIMED_OUT same as FAILED for success_policy evaluation
        non_success_count = failed_count + cancelled_count + timed_out_count
        
        # Apply success policy to determine if stage succeeded or failed
        if success_policy == SuccessPolicy.ALL:
            # ALL policy: all must succeed
            if non_success_count == 0:
                return StageStatus.COMPLETED
            # Stage failed - use specific status only if ALL failures are of the same type
            # This provides better error messaging while treating all failures equally in logic
            if non_success_count == timed_out_count:
                return StageStatus.TIMED_OUT
            if non_success_count == cancelled_count:
                return StageStatus.CANCELLED
            # Mixed or regular failures - use generic FAILED status
            return StageStatus.FAILED
        else:  # SuccessPolicy.ANY
            # ANY policy: at least one must succeed
            if completed_count > 0:
                return StageStatus.COMPLETED
            # No agent succeeded - use specific status only if ALL failures are of the same type
            if non_success_count == timed_out_count:
                return StageStatus.TIMED_OUT
            if non_success_count == cancelled_count:
                return StageStatus.CANCELLED
            # Mixed or regular failures - use generic FAILED status
            return StageStatus.FAILED
    
    def _aggregate_parallel_stage_errors(
        self,
        metadatas: list[AgentExecutionMetadata],
        parallel_type: str,
        success_policy: SuccessPolicy
    ) -> str:
        """
        Aggregate error messages from failed/cancelled/timed-out agents in a parallel stage.
        
        Creates a detailed error message listing each failed/cancelled/timed-out agent with their specific error.
        
        Args:
            metadatas: List of agent execution metadata
            parallel_type: Type of parallel execution (e.g., "multi_agent", "replica")
            success_policy: Success policy that was applied
            
        Returns:
            Detailed error message with individual agent failures
        """
        failed_agents = []
        cancelled_agents = []
        timed_out_agents = []
        
        for metadata in metadatas:
            agent_name = metadata.agent_name or 'unknown'
            error_msg = metadata.error_message or 'No error message'
            
            if metadata.status == StageStatus.FAILED:
                failed_agents.append(f"  - {agent_name} (failed): {error_msg}")
            elif metadata.status == StageStatus.CANCELLED:
                cancelled_agents.append(f"  - {agent_name} (cancelled): {error_msg}")
            elif metadata.status == StageStatus.TIMED_OUT:
                timed_out_agents.append(f"  - {agent_name} (timed out): {error_msg}")
        
        # Count totals
        failed_count = len(failed_agents)
        cancelled_count = len(cancelled_agents)
        timed_out_count = len(timed_out_agents)
        total_agents = len(metadatas)
        
        # Build header
        error_parts = [
            f"{parallel_type.capitalize()} stage failed: {failed_count + cancelled_count + timed_out_count}/{total_agents} executions failed (policy: {success_policy})"
        ]
        
        # Add detailed agent errors
        if failed_agents:
            error_parts.append("\nFailed agents:")
            error_parts.extend(failed_agents)
        
        if cancelled_agents:
            error_parts.append("\nCancelled agents:")
            error_parts.extend(cancelled_agents)
        
        if timed_out_agents:
            error_parts.append("\nTimed out agents:")
            error_parts.extend(timed_out_agents)
        
        return "\n".join(error_parts)
    
    
    async def _execute_parallel_stage(
        self,
        stage: "ChainStageConfigModel",
        chain_context: ChainContext,
        session_mcp_client: MCPClient,
        stage_index: int,
        execution_configs: list[dict[str, Any]],
        parallel_type: str
    ) -> ParallelStageResult:
        """
        Common execution logic for parallel stages (multi-agent or replica).
        
        Args:
            stage: Stage configuration
            chain_context: Chain context for this session
            session_mcp_client: Session-scoped MCP client
            stage_index: Index of this stage in the chain
            execution_configs: List of dicts with agent_name, llm_provider, iteration_strategy (and optionally base_agent_name)
            parallel_type: "multi_agent" or "replica"
            
        Returns:
            ParallelStageResult with aggregated results and metadata
        """
        stage_started_at_us = now_us()
        
        # Create a synthetic stage object for parent stage creation
        # Parent stages need an agent value for the database schema (NOT NULL constraint)
        from tarsy.models.agent_config import ChainStageConfigModel
        parent_stage = ChainStageConfigModel(
            name=stage.name,
            agent=f"parallel-{parallel_type}",  # Synthetic agent name for parent record
            iteration_strategy=stage.iteration_strategy  # Keep original value (Enum or None) for Pydantic validation
        )
        
        # Create parent stage execution record with parallel_type and expected count
        parent_stage_execution_id = await self.stage_manager.create_stage_execution(
            chain_context.session_id,
            parent_stage,
            stage_index,
            parent_stage_execution_id=None,  # This is the parent
            parallel_index=0,  # Parent is always index 0
            parallel_type=parallel_type,  # "multi_agent" or "replica"
            expected_parallel_count=len(execution_configs),  # Number of parallel agents
        )
        await self.stage_manager.update_stage_execution_started(parent_stage_execution_id)
        
        # Prepare parallel executions
        async def execute_single(config: dict[str, Any], idx: int):
            """Execute a single agent/replica and return (result, metadata) tuple."""
            agent_started_at_us = now_us()
            agent_name = config["agent_name"]
            base_agent = config.get("base_agent_name", agent_name)  # For replicas
            
            # Get execution config (unified configuration object)
            execution_config = config["execution_config"]
            
            # Get original (non-normalized) iteration_strategy for Pydantic validation
            # For ChainStageConfigModel, we need the original value (Enum or None), not the normalized string
            child_strategy_original = config.get("iteration_strategy_original")
            
            # Create a child stage config for child stage creation
            from tarsy.models.agent_config import ChainStageConfigModel
            child_stage = ChainStageConfigModel(
                name=f"{stage.name} - {agent_name}",
                agent=agent_name,
                iteration_strategy=child_strategy_original  # Keep original value (Enum or None) for Pydantic validation
            )
            
            # Create child stage execution record
            child_execution_id = await self.stage_manager.create_stage_execution(
                session_id=chain_context.session_id,
                stage=child_stage,
                stage_index=stage_index,
                parent_stage_execution_id=parent_stage_execution_id,
                parallel_index=idx + 1,  # 1-based indexing for children
                parallel_type=parallel_type,
            )
            # IMPORTANT: Await the status update to ensure proper state ordering.
            # Previously used fire-and-forget which caused race conditions where the
            # 'started' update could commit AFTER the 'completed' update, leaving
            # the status stuck at 'active'. The slight serialization delay is
            # acceptable for correctness.
            await self.stage_manager.update_stage_execution_started(child_execution_id)
            
            try:
                logger.debug(f"Executing {parallel_type} {idx+1}/{len(execution_configs)}: '{agent_name}'")
                
                # Get agent instance from factory with unified execution config
                agent = self.agent_factory.get_agent_with_config(
                    agent_identifier=base_agent,
                    mcp_client=session_mcp_client,
                    execution_config=execution_config
                )
                
                # Set current stage execution ID for interaction tagging (hooks need this!)
                agent.set_current_stage_execution_id(child_execution_id)
                
                # Set parallel execution metadata for streaming events
                from tarsy.models.parallel_metadata import ParallelExecutionMetadata
                agent.set_parallel_execution_metadata(
                    ParallelExecutionMetadata(
                        parent_stage_execution_id=parent_stage_execution_id,
                        parallel_index=idx + 1,  # 1-indexed for display
                        agent_name=agent_name
                    )
                )
                
                # Execute agent (timeout protection is built into BaseAgent.process_alert)
                # Create isolated context copy to prevent concurrent mutation across parallel agents
                agent_context = chain_context.model_copy(deep=True)
                result = await agent.process_alert(agent_context)
                
                # Override agent_name for replicas
                if parallel_type == "replica":
                    result.agent_name = agent_name
                
                # Update child stage execution with result based on status
                if result.status == StageStatus.COMPLETED:
                    await self.stage_manager.update_stage_execution_completed(child_execution_id, result)
                elif result.status == StageStatus.PAUSED:
                    # Agent paused normally (not via exception) - this shouldn't happen 
                    # because agents raise SessionPaused exception, but handle it just in case
                    # Extract iteration from result if available, default to 0
                    iteration = getattr(result, 'current_iteration', 0)
                    await self.stage_manager.update_stage_execution_paused(child_execution_id, iteration, result)
                elif result.status == StageStatus.TIMED_OUT:
                    # Timeout - use specific timed_out status
                    await self.stage_manager.update_stage_execution_timed_out(
                        child_execution_id,
                        result.error_message or "Execution timed out"
                    )
                else:
                    # FAILED or other status
                    await self.stage_manager.update_stage_execution_failed(
                        child_execution_id,
                        result.error_message or "Execution failed"
                    )
                
                # Create metadata (use normalized string from config)
                agent_completed_at_us = now_us()
                metadata = AgentExecutionMetadata(
                    agent_name=agent_name,
                    llm_provider=execution_config.llm_provider or self.settings.llm_provider,
                    iteration_strategy=execution_config.iteration_strategy or "unknown",
                    started_at_us=agent_started_at_us,
                    completed_at_us=agent_completed_at_us,
                    status=result.status,
                    error_message=result.error_message,
                    token_usage=None
                )
                
                return (result, metadata)
                
            except asyncio.CancelledError:
                # Cancellation can happen if the agent task is cancelled mid-flight (e.g. shutdown,
                # upstream cancellation, or nested wait_for interactions). Treat it as a terminal
                # result so the child stage doesn't stay "running" forever in the UI.
                reason, _ = await self._handle_stage_cancellation(
                    session_id=chain_context.session_id,
                    stage_execution_id=child_execution_id,
                    description=f"{parallel_type} '{agent_name}'",
                )

                # Create exception with correct reason for build_agent_result_from_exception
                result, metadata = build_agent_result_from_exception(
                    exception=asyncio.CancelledError(reason),
                    agent_name=agent_name,
                    stage_name=stage.name,
                    llm_provider=execution_config.llm_provider or self.settings.llm_provider,
                    iteration_strategy=execution_config.iteration_strategy or "unknown",
                    agent_started_at_us=agent_started_at_us,
                )

                return (result, metadata)

            except SessionPaused as e:
                # Special handling for pause signal (not an error!)
                logger.info(f"{parallel_type} '{agent_name}' paused at iteration {e.iteration}")
                
                # Create paused result with conversation state for resume
                paused_result = AgentExecutionResult(
                    status=StageStatus.PAUSED,
                    agent_name=agent_name,
                    stage_name=stage.name,
                    timestamp_us=now_us(),
                    result_summary=f"Paused at iteration {e.iteration}",
                    paused_conversation_state=e.conversation.model_dump() if e.conversation else None,
                    error_message=None
                )
                
                # Update child stage as PAUSED (not failed!)
                await self.stage_manager.update_stage_execution_paused(child_execution_id, e.iteration, paused_result)
                
                # Create metadata with PAUSED status (use normalized string)
                agent_completed_at_us = now_us()
                metadata = AgentExecutionMetadata(
                    agent_name=agent_name,
                    llm_provider=execution_config.llm_provider or self.settings.llm_provider,
                    iteration_strategy=execution_config.iteration_strategy or "unknown",
                    started_at_us=agent_started_at_us,
                    completed_at_us=agent_completed_at_us,
                    status=StageStatus.PAUSED,
                    error_message=None,
                    token_usage=None
                )
                
                return (paused_result, metadata)
                
            except Exception as e:
                # All other exceptions are failures
                logger.error(f"{parallel_type} '{agent_name}' failed: {e}", exc_info=True)
                
                agent_completed_at_us = now_us()
                
                # Update child stage execution with failure
                await self.stage_manager.update_stage_execution_failed(child_execution_id, str(e))
                
                # Create failed result
                error_result = AgentExecutionResult(
                    status=StageStatus.FAILED,
                    agent_name=agent_name,
                    stage_name=stage.name,
                    timestamp_us=agent_completed_at_us,
                    result_summary=f"Execution failed: {str(e)}",
                    error_message=str(e)
                )
                
                # Create metadata for failed execution (use normalized string)
                metadata = AgentExecutionMetadata(
                    agent_name=agent_name,
                    llm_provider=execution_config.llm_provider or self.settings.llm_provider,
                    iteration_strategy=execution_config.iteration_strategy or "unknown",
                    started_at_us=agent_started_at_us,
                    completed_at_us=agent_completed_at_us,
                    status=StageStatus.FAILED,
                    error_message=str(e),
                    token_usage=None
                )
                
                return (error_result, metadata)
        
        # Execute all concurrently
        tasks = [execute_single(config, idx) for idx, config in enumerate(execution_configs)]
        results_and_metadata = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Separate results and metadata, handling exceptions
        results = []
        metadatas = []
        
        for idx, item in enumerate(results_and_metadata):
            # NOTE: asyncio.CancelledError inherits from BaseException (not Exception) on Python 3.13.
            if isinstance(item, BaseException):
                logger.error(f"Unexpected exception in {parallel_type} {idx+1}: {item}")
                agent_name = execution_configs[idx].get("agent_name") or f"{parallel_type}-{idx+1}"
                
                error_result, error_metadata = build_agent_result_from_exception(
                    exception=item,
                    agent_name=agent_name,
                    stage_name=stage.name,
                    llm_provider=execution_configs[idx]["execution_config"].llm_provider or self.settings.llm_provider,
                    iteration_strategy=execution_configs[idx]["execution_config"].iteration_strategy or "unknown",
                    agent_started_at_us=stage_started_at_us,
                )
                results.append(error_result)
                metadatas.append(error_metadata)
            else:
                result, metadata = item
                results.append(result)
                metadatas.append(metadata)
        
        # Check if any task was cancelled by user - if so, re-raise to stop the entire session
        # Note: Individual tasks catch CancelledError and return CANCELLED status, so we check metadata
        from tarsy.services.cancellation_tracker import is_user_cancel
        if is_user_cancel(chain_context.session_id):
            cancelled_count = sum(1 for m in metadatas if m.status == StageStatus.CANCELLED)
            if cancelled_count > 0:
                from tarsy.models.constants import CancellationReason
                logger.info(f"User cancelled session {chain_context.session_id} - re-raising to stop execution")
                raise asyncio.CancelledError(CancellationReason.USER_CANCEL.value)
        
        # Create stage metadata
        stage_completed_at_us = now_us()
        stage_metadata = ParallelStageMetadata(
            parent_stage_execution_id=parent_stage_execution_id,
            parallel_type=parallel_type,
            success_policy=stage.success_policy,
            started_at_us=stage_started_at_us,
            completed_at_us=stage_completed_at_us,
            agent_metadatas=metadatas
        )
        
        # Determine overall stage status using aggregation logic
        overall_status = self.aggregate_status(metadatas, stage.success_policy)
        
        # Log aggregation results
        completed_count = sum(1 for m in metadatas if m.status == StageStatus.COMPLETED)
        failed_count = sum(1 for m in metadatas if m.status == StageStatus.FAILED)
        paused_count = sum(1 for m in metadatas if m.status == StageStatus.PAUSED)
        
        if overall_status == StageStatus.PAUSED:
            logger.info(
                f"{parallel_type.capitalize()} stage '{stage.name}': "
                f"{completed_count} completed, {failed_count} failed, {paused_count} paused "
                f"-> Overall status: PAUSED"
            )
        else:
            logger.info(
                f"{parallel_type.capitalize()} stage '{stage.name}' completed: {completed_count}/{len(metadatas)} succeeded, "
                f"policy={stage.success_policy}, status={overall_status.value}"
            )
        
        # Build error message for error/failure states
        error_msg = None
        if overall_status.is_error():
            error_msg = self._aggregate_parallel_stage_errors(
                metadatas=metadatas,
                parallel_type=parallel_type,
                success_policy=stage.success_policy
            )
        
        # Create parallel stage result with error message
        parallel_result = ParallelStageResult(
            stage_name=stage.name,
            results=results,
            metadata=stage_metadata,
            status=overall_status,
            timestamp_us=stage_metadata.completed_at_us,
            error_message=error_msg
        )
        
        # Update parent stage execution with result
        if overall_status == StageStatus.COMPLETED:
            await self.stage_manager.update_stage_execution_completed(parent_stage_execution_id, parallel_result)
        elif overall_status == StageStatus.PAUSED:
            # Handle paused parallel stage
            # Use a representative iteration count (timestamp as proxy since we don't track iteration in metadata)
            # Note: Individual child iterations are stored in their own stage_execution records
            representative_iteration = max(
                m.completed_at_us for m in metadatas if m.status == StageStatus.PAUSED
            ) // 1000  # Use timestamp as proxy since iteration not in metadata
            
            # Save parallel_result in parent stage (contains ALL agent results including paused ones)
            await self.stage_manager.update_stage_execution_paused(
                parent_stage_execution_id, 
                representative_iteration,
                parallel_result  # This preserves all agent results for resume
            )
            
            logger.info(
                f"Parallel stage '{stage.name}' paused: "
                f"{paused_count} agents paused, {completed_count} completed, {failed_count} failed"
            )
        else:  # FAILED, TIMED_OUT, or CANCELLED
            # Preserve the specific error status in the database
            if overall_status == StageStatus.TIMED_OUT:
                await self.stage_manager.update_stage_execution_timed_out(parent_stage_execution_id, error_msg)
            elif overall_status == StageStatus.CANCELLED:
                await self.stage_manager.update_stage_execution_cancelled(parent_stage_execution_id, error_msg)
            else:
                await self.stage_manager.update_stage_execution_failed(parent_stage_execution_id, error_msg)
        
        return parallel_result
    
    async def resume_parallel_stage(
        self,
        paused_parent_stage: 'StageExecution',
        chain_context: ChainContext,
        session_mcp_client: MCPClient,
        chain_definition: "ChainConfigModel",
        stage_index: int,
        history_service: "HistoryService"
    ) -> ParallelStageResult:
        """
        Resume a paused parallel stage by re-executing only paused children.
        
        Completed and failed children are preserved from the original execution.
        Only agents in PAUSED status are re-executed.
        
        Args:
            paused_parent_stage: Parent stage execution that was paused
            chain_context: Chain context for session
            session_mcp_client: Session-scoped MCP client
            chain_definition: Full chain definition
            stage_index: Index of this stage in chain
            history_service: History service for loading child stage executions
            
        Returns:
            ParallelStageResult with merged results (completed + resumed)
        """
        logger.info(f"Resuming parallel stage '{paused_parent_stage.stage_name}'")
        
        # 1. Load all child stage executions
        children = await history_service.get_parallel_stage_children(
            paused_parent_stage.execution_id
        )
        
        # 2. Separate children by status
        completed_children = [c for c in children if c.status == StageStatus.COMPLETED.value]
        paused_children = [c for c in children if c.status == StageStatus.PAUSED.value]
        failed_children = [c for c in children if c.status == StageStatus.FAILED.value]
        
        # Sort paused children by their parallel_index to ensure stable order during resume
        # This preserves original indices when streaming metadata and execution
        paused_children.sort(key=lambda c: c.parallel_index)
        
        logger.info(
            f"Parallel stage resume: {len(completed_children)} completed, "
            f"{len(paused_children)} paused, {len(failed_children)} failed"
        )
        
        if not paused_children:
            raise ValueError(
                f"No paused children found for parallel stage {paused_parent_stage.stage_name}"
            )
        
        # 3. Load original stage configuration from chain definition
        stage_config = chain_definition.stages[stage_index]
        
        # 4. Reconstruct completed results from database
        completed_results = []
        completed_metadatas = []
        
        for child in completed_children:
            if child.stage_output:
                result = AgentExecutionResult.model_validate(child.stage_output)
                completed_results.append(result)
                
                # Reconstruct metadata for completed child
                metadata = AgentExecutionMetadata(
                    agent_name=child.agent,
                    llm_provider="unknown",  # Not stored, will be recalculated
                    iteration_strategy="unknown",  # Not stored
                    started_at_us=child.started_at_us or 0,
                    completed_at_us=child.completed_at_us or 0,
                    status=StageStatus.COMPLETED,
                    error_message=None,
                    token_usage=None
                )
                completed_metadatas.append(metadata)
        
        # 5. Reconstruct failed results from database (preserve failures)
        failed_results = []
        failed_metadatas = []
        
        for child in failed_children:
            # Create failed result
            failed_result = AgentExecutionResult(
                status=StageStatus.FAILED,
                agent_name=child.agent,
                stage_name=child.stage_name,
                timestamp_us=child.completed_at_us or now_us(),
                result_summary=f"Failed: {child.error_message or 'Unknown error'}",
                error_message=child.error_message
            )
            failed_results.append(failed_result)
            
            # Reconstruct metadata
            metadata = AgentExecutionMetadata(
                agent_name=child.agent,
                llm_provider="unknown",
                iteration_strategy="unknown",
                started_at_us=child.started_at_us or 0,
                completed_at_us=child.completed_at_us or now_us(),
                status=StageStatus.FAILED,
                error_message=child.error_message,
                token_usage=None
            )
            failed_metadatas.append(metadata)
        
        # 6. Build execution configs for ONLY paused children
        execution_configs = []
        
        for child in paused_children:
            # Determine agent configuration
            # For multi-agent: look up in stage.agents list
            # For replica: reconstruct from naming pattern
            
            if paused_parent_stage.parallel_type == ParallelType.MULTI_AGENT.value:
                # Find matching agent config in stage definition
                agent_config = next(
                    (a for a in stage_config.agents if a.name == child.agent),
                    None
                )
                if not agent_config:
                    raise ValueError(f"Agent config not found for {child.agent}")
                
                # Get agent definition if it exists
                agent_def = (
                    self.agent_factory.agent_configs.get(agent_config.name)
                    if getattr(self.agent_factory, "agent_configs", None)
                    else None
                )
                
                # Resolve unified execution config from hierarchy (same as normal execution)
                execution_config = ExecutionConfigResolver.resolve_config(
                    system_settings=self.settings,
                    agent_config=agent_def,
                    chain_config=chain_definition,
                    stage_config=stage_config,
                    parallel_agent_config=agent_config,
                )
                
                config = {
                    "agent_name": child.agent,
                    "execution_config": execution_config,
                    "iteration_strategy_original": agent_config.iteration_strategy,  # Keep original for Pydantic validation
                }
            else:  # REPLICA
                # Extract base agent name (e.g., "KubernetesAgent-1" -> "KubernetesAgent")
                base_agent = stage_config.agent
                
                # Get agent definition if it exists
                agent_def = (
                    self.agent_factory.agent_configs.get(base_agent)
                    if getattr(self.agent_factory, "agent_configs", None)
                    else None
                )
                
                # Resolve unified execution config from hierarchy (replicas don't have parallel_agent_config)
                execution_config = ExecutionConfigResolver.resolve_config(
                    system_settings=self.settings,
                    agent_config=agent_def,
                    chain_config=chain_definition,
                    stage_config=stage_config,
                    parallel_agent_config=None,  # Replicas don't have individual config
                )
                
                config = {
                    "agent_name": child.agent,  # Keep replica name
                    "base_agent_name": base_agent,
                    "execution_config": execution_config,
                    "iteration_strategy_original": stage_config.iteration_strategy,  # Keep original for Pydantic validation
                }
            
            execution_configs.append(config)
            
            # 7. Restore paused conversation state to chain_context
            if child.stage_output:
                paused_result = AgentExecutionResult.model_validate(child.stage_output)
                # Add to context so agent can resume from paused state
                # CRITICAL: Use execution_id as the SOLE key to avoid any naming mismatches
                # The child.stage_name includes agent name ("investigation - KubernetesAgent")
                # but context.stage_name during lookup is just parent name ("investigation")
                # Using only execution_id guarantees correct lookup
                chain_context.add_stage_result(child.execution_id, paused_result)
                logger.info(f"Restored paused state for {child.agent} with key {child.execution_id}")
        
        # 8. Execute ONLY paused children directly (without creating new parent stage)
        logger.info(f"Re-executing {len(paused_children)} paused agents")
        
        # Get parent execution ID for metadata
        parent_execution_id = paused_parent_stage.execution_id
        
        # Execute paused agents concurrently
        async def execute_single_child(config: dict[str, Any], idx: int):
            """Execute a single resumed agent/replica and return (result, metadata) tuple."""
            agent_started_at_us = now_us()
            agent_name = config["agent_name"]
            base_agent = config.get("base_agent_name", agent_name)
            
            # Get execution config (unified configuration object)
            execution_config = config["execution_config"]
            
            # Find the existing paused child stage execution to reuse
            paused_child = paused_children[idx]
            child_execution_id = paused_child.execution_id
            
            # Update the existing child stage to ACTIVE (from PAUSED)
            # IMPORTANT: Await the status update to ensure proper state ordering.
            # Previously used fire-and-forget which caused race conditions where the
            # 'started' update could commit AFTER the 'completed' update, leaving
            # the status stuck at 'active'.
            await self.stage_manager.update_stage_execution_started(child_execution_id)
            
            try:
                logger.debug(f"Resuming paused agent {idx+1}/{len(execution_configs)}: '{agent_name}'")
                
                # Get agent instance from factory with unified execution config
                agent = self.agent_factory.get_agent_with_config(
                    agent_identifier=base_agent,
                    mcp_client=session_mcp_client,
                    execution_config=execution_config
                )
                
                # Set current stage execution ID for interaction tagging (hooks need this!)
                agent.set_current_stage_execution_id(child_execution_id)
                
                # Set parallel execution metadata for streaming events
                # Use the original paused child's parallel_index to preserve numbering
                # when only a subset of agents were paused (e.g., agents 2 and 4 out of 1-4)
                from tarsy.models.parallel_metadata import ParallelExecutionMetadata
                agent.set_parallel_execution_metadata(
                    ParallelExecutionMetadata(
                        parent_stage_execution_id=parent_execution_id,
                        parallel_index=paused_child.parallel_index,  # Preserve original index
                        agent_name=agent_name
                    )
                )
                
                # Execute agent (timeout protection is built into BaseAgent.process_alert)
                # Create isolated context copy to prevent concurrent mutation across parallel agents
                agent_context = chain_context.model_copy(deep=True)
                result = await agent.process_alert(agent_context)
                
                # Override agent_name for replicas
                if paused_parent_stage.parallel_type == "replica":
                    result.agent_name = agent_name
                
                # Update child stage execution with appropriate status
                if result.status == StageStatus.COMPLETED:
                    await self.stage_manager.update_stage_execution_completed(child_execution_id, result)
                elif result.status == StageStatus.TIMED_OUT:
                    error_msg = result.error_message or f"Agent '{agent_name}' timed out"
                    await self.stage_manager.update_stage_execution_timed_out(child_execution_id, error_msg)
                else:  # FAILED or other error status
                    error_msg = result.error_message or f"Agent '{agent_name}' failed"
                    await self.stage_manager.update_stage_execution_failed(child_execution_id, error_msg)
                
                # Create metadata (use actual result status)
                agent_completed_at_us = now_us()
                metadata = AgentExecutionMetadata(
                    agent_name=agent_name,
                    llm_provider=execution_config.llm_provider or self.settings.llm_provider,
                    iteration_strategy=execution_config.iteration_strategy or "unknown",
                    started_at_us=agent_started_at_us,
                    completed_at_us=agent_completed_at_us,
                    status=result.status,  # Use actual status from result
                    error_message=result.error_message,
                    token_usage=None
                )
                
                return (result, metadata)
            
            except SessionPaused as e:
                logger.info(f"Agent '{agent_name}' paused again at iteration {e.iteration}")
                
                # Create paused result
                paused_result = AgentExecutionResult(
                    status=StageStatus.PAUSED,
                    agent_name=agent_name,
                    stage_name=stage_config.name,
                    timestamp_us=now_us(),
                    result_summary=f"Paused at iteration {e.iteration}",
                    paused_conversation_state=e.conversation.model_dump() if e.conversation else None,
                    error_message=None
                )
                
                await self.stage_manager.update_stage_execution_paused(child_execution_id, e.iteration, paused_result)
                
                # Create metadata (use normalized string)
                agent_completed_at_us = now_us()
                metadata = AgentExecutionMetadata(
                    agent_name=agent_name,
                    llm_provider=execution_config.llm_provider or self.settings.llm_provider,
                    iteration_strategy=execution_config.iteration_strategy or "unknown",
                    started_at_us=agent_started_at_us,
                    completed_at_us=agent_completed_at_us,
                    status=StageStatus.PAUSED,
                    error_message=None,
                    token_usage=None
                )
                
                return (paused_result, metadata)
            
            except asyncio.CancelledError:
                # Cancellation (timeout or user-requested) - mark stage appropriately
                reason, _ = await self._handle_stage_cancellation(
                    session_id=chain_context.session_id,
                    stage_execution_id=child_execution_id,
                    description=f"Agent '{agent_name}'",
                )
                
                # Create exception with correct reason for build_agent_result_from_exception
                result, metadata = build_agent_result_from_exception(
                    exception=asyncio.CancelledError(reason),
                    agent_name=agent_name,
                    stage_name=stage_config.name,
                    llm_provider=execution_config.llm_provider or self.settings.llm_provider,
                    iteration_strategy=execution_config.iteration_strategy or "unknown",
                    agent_started_at_us=agent_started_at_us,
                )
                
                return (result, metadata)
            
            except Exception as e:
                logger.error(f"Agent '{agent_name}' failed: {e}", exc_info=True)
                
                await self.stage_manager.update_stage_execution_failed(child_execution_id, str(e))
                
                error_result = AgentExecutionResult(
                    status=StageStatus.FAILED,
                    agent_name=agent_name,
                    stage_name=stage_config.name,
                    timestamp_us=now_us(),
                    result_summary=f"Execution failed: {str(e)}",
                    error_message=str(e)
                )
                
                # Create metadata (use normalized string)
                agent_completed_at_us = now_us()
                metadata = AgentExecutionMetadata(
                    agent_name=agent_name,
                    llm_provider=execution_config.llm_provider or self.settings.llm_provider,
                    iteration_strategy=execution_config.iteration_strategy or "unknown",
                    started_at_us=agent_started_at_us,
                    completed_at_us=agent_completed_at_us,
                    status=StageStatus.FAILED,
                    error_message=str(e),
                    token_usage=None
                )
                
                return (error_result, metadata)
        
        # Execute all paused children concurrently
        tasks = [execute_single_child(config, idx) for idx, config in enumerate(execution_configs)]
        resumed_results_and_metadata = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Extract results and metadata
        resumed_results = []
        resumed_metadatas = []
        
        for item in resumed_results_and_metadata:
            if isinstance(item, BaseException):
                logger.error(f"Unexpected exception during resume: {item}")
                # Create error result
                error_result, error_metadata = build_agent_result_from_exception(
                    exception=item,
                    agent_name="unknown",
                    stage_name=stage_config.name,
                    llm_provider=self.settings.llm_provider,
                    iteration_strategy="unknown",
                    agent_started_at_us=now_us(),
                )
                resumed_results.append(error_result)
                resumed_metadatas.append(error_metadata)
            else:
                result, metadata = item
                resumed_results.append(result)
                resumed_metadatas.append(metadata)
        
        # Check if any resumed task was cancelled by user - if so, re-raise to stop the session
        from tarsy.services.cancellation_tracker import is_user_cancel
        if is_user_cancel(chain_context.session_id):
            resumed_cancelled_count = sum(1 for m in resumed_metadatas if m.status == StageStatus.CANCELLED)
            if resumed_cancelled_count > 0:
                from tarsy.models.constants import CancellationReason
                logger.info(f"User cancelled session {chain_context.session_id} during resume - re-raising")
                raise asyncio.CancelledError(CancellationReason.USER_CANCEL.value)
        
        # 9. Merge all results: completed + failed + resumed
        all_results = completed_results + failed_results + resumed_results
        all_metadatas = completed_metadatas + failed_metadatas + resumed_metadatas
        
        # 10. Create final merged metadata
        merged_metadata = ParallelStageMetadata(
            parent_stage_execution_id=paused_parent_stage.execution_id,
            parallel_type=paused_parent_stage.parallel_type,
            success_policy=stage_config.success_policy,
            started_at_us=paused_parent_stage.started_at_us or now_us(),
            completed_at_us=now_us(),
            agent_metadatas=all_metadatas
        )
        
        # 11. Determine final status using aggregate_status (same logic as initial execution)
        final_status = self.aggregate_status(all_metadatas, stage_config.success_policy)
        
        completed_count = sum(1 for m in all_metadatas if m.status == StageStatus.COMPLETED)
        failed_count = sum(1 for m in all_metadatas if m.status == StageStatus.FAILED)
        paused_count = sum(1 for m in all_metadatas if m.status == StageStatus.PAUSED)
        
        if final_status == StageStatus.PAUSED:
            logger.warning(f"Parallel stage paused again: {paused_count} agents still paused")
        
        # Build error message for error/failure states
        error_msg = None
        if final_status.is_error():
            error_msg = self._aggregate_parallel_stage_errors(
                metadatas=all_metadatas,
                parallel_type=paused_parent_stage.parallel_type,
                success_policy=stage_config.success_policy
            )
        
        # 12. Create final merged result with error message
        merged_result = ParallelStageResult(
            stage_name=paused_parent_stage.stage_name,
            results=all_results,
            metadata=merged_metadata,
            status=final_status,
            timestamp_us=merged_metadata.completed_at_us,
            error_message=error_msg
        )
        
        # 13. Update parent stage with final result
        if final_status == StageStatus.COMPLETED:
            await self.stage_manager.update_stage_execution_completed(
                paused_parent_stage.execution_id, 
                merged_result
            )
        elif final_status == StageStatus.PAUSED:
            # Paused again - update with new pause state
            await self.stage_manager.update_stage_execution_paused(
                paused_parent_stage.execution_id,
                0,  # Iteration not meaningful for parallel stage
                merged_result
            )
        else:  # FAILED, TIMED_OUT, or CANCELLED
            # Preserve the specific error status in the database
            if final_status == StageStatus.TIMED_OUT:
                await self.stage_manager.update_stage_execution_timed_out(
                    paused_parent_stage.execution_id,
                    error_msg
                )
            elif final_status == StageStatus.CANCELLED:
                await self.stage_manager.update_stage_execution_cancelled(
                    paused_parent_stage.execution_id,
                    error_msg
                )
            else:
                await self.stage_manager.update_stage_execution_failed(
                    paused_parent_stage.execution_id,
                    error_msg
                )
        
        logger.info(
            f"Parallel stage resume complete: {completed_count} completed, "
            f"{failed_count} failed, {paused_count} paused -> {final_status.value}"
        )
        
        return merged_result
    
    def is_final_stage_parallel(self, chain_definition: "ChainConfigModel") -> bool:
        """
        Check if the last stage in the chain is a parallel stage.
        
        Args:
            chain_definition: Chain definition to check
            
        Returns:
            True if the last stage is parallel, False otherwise
        """
        if not chain_definition.stages:
            return False
        
        last_stage = chain_definition.stages[-1]
        return last_stage.agents is not None or last_stage.replicas > 1
    
    async def synthesize_parallel_results(
        self,
        parallel_result: ParallelStageResult,
        chain_context: ChainContext,
        session_mcp_client: MCPClient,
        stage_config: "ChainStageConfigModel",
        chain_definition: "ChainConfigModel",
        current_stage_index: int
    ) -> tuple[str, AgentExecutionResult]:
        """
        Automatically invoke synthesis agent to synthesize parallel results.
        
        ALWAYS called immediately after any parallel stage completes successfully.
        This ensures parallel results are synthesized into a coherent analysis
        before being passed to subsequent stages or used as final output.
        
        Synthesis configuration is optional - if not provided in stage config,
        defaults are used (SynthesisAgent with 'synthesis' iteration strategy).
        
        Args:
            parallel_result: The parallel stage result to synthesize
            chain_context: Chain context for this session
            session_mcp_client: Session-scoped MCP client
            stage_config: Stage configuration (may contain optional synthesis config)
            chain_definition: Full chain definition
            current_stage_index: Stage index to use for synthesis (accounts for all executed stages so far)
            
        Returns:
            Synthesized AgentExecutionResult from synthesis agent
        """
        logger.info("Invoking automatic synthesis for parallel stage")
        
        # Get synthesis configuration with defaults
        from tarsy.models.agent_config import SynthesisConfig
        synthesis_config = stage_config.synthesis or SynthesisConfig()
        
        # Create synthetic stage for synthesis agent
        from tarsy.models.agent_config import ChainStageConfigModel
        
        synthesis_stage = ChainStageConfigModel(
            name="synthesis",
            agent=synthesis_config.agent,
            llm_provider=synthesis_config.llm_provider or stage_config.llm_provider or chain_definition.llm_provider
        )
        
        # Create stage execution record for synthesis
        # Use the provided stage index (which accounts for previously executed stages including other synthesis stages)
        synthesis_stage_execution_id = await self.stage_manager.create_stage_execution(
            chain_context.session_id,
            synthesis_stage,
            current_stage_index  # This is the actual executed stage count
        )
        
        try:
            # Mark synthesis stage as started
            await self.stage_manager.update_stage_execution_started(synthesis_stage_execution_id)
            
            # Resolve unified execution configuration for synthesis agent
            # Get agent definition if it exists
            agent_def = self.agent_factory.agent_configs.get(synthesis_config.agent) if self.agent_factory.agent_configs else None
            
            # Create a temporary stage config with synthesis settings for resolution
            # This ensures synthesis config overrides are properly applied
            from tarsy.models.agent_config import ChainStageConfigModel as TempStageModel
            synthesis_temp_stage = TempStageModel(
                name="synthesis-temp",
                agent=synthesis_config.agent,
                iteration_strategy=synthesis_config.iteration_strategy,
                llm_provider=synthesis_config.llm_provider or stage_config.llm_provider,
                mcp_servers=None  # Synthesis doesn't use tools/MCP servers
            )
            
            # Resolve unified execution config (synthesis doesn't have parallel_agent_config)
            execution_config = ExecutionConfigResolver.resolve_config(
                system_settings=self.settings,
                agent_config=agent_def,
                chain_config=chain_definition,
                stage_config=synthesis_temp_stage,
                parallel_agent_config=None  # Synthesis doesn't have parallel config
            )
            
            # Get synthesis agent from factory with unified config (configurable!)
            synthesis_agent = self.agent_factory.get_agent_with_config(
                agent_identifier=synthesis_config.agent,
                mcp_client=session_mcp_client,
                execution_config=execution_config
            )
            
            # Set stage execution ID for interaction tagging
            synthesis_agent.set_current_stage_execution_id(synthesis_stage_execution_id)
            
            # Update chain context to reflect synthesis stage
            original_stage = chain_context.current_stage_name
            chain_context.current_stage_name = "synthesis"
            
            # Execute synthesis agent (timeout protection is built into BaseAgent.process_alert)
            logger.info(f"Executing {synthesis_config.agent} with {synthesis_config.iteration_strategy} strategy to synthesize parallel investigation results")
            synthesis_result = await synthesis_agent.process_alert(chain_context)
            
            # Restore original stage name (for proper context)
            chain_context.current_stage_name = original_stage
            
            # Update synthesis stage execution with appropriate status
            if synthesis_result.status == StageStatus.COMPLETED:
                await self.stage_manager.update_stage_execution_completed(synthesis_stage_execution_id, synthesis_result)
                logger.info(f"{synthesis_config.agent} synthesis completed successfully")
            elif synthesis_result.status == StageStatus.TIMED_OUT:
                error_msg = synthesis_result.error_message or f"{synthesis_config.agent} synthesis timed out"
                await self.stage_manager.update_stage_execution_timed_out(synthesis_stage_execution_id, error_msg)
                logger.warning(f"{synthesis_config.agent} synthesis timed out: {error_msg}")
            else:  # FAILED or other error status
                error_msg = synthesis_result.error_message or f"{synthesis_config.agent} synthesis failed"
                await self.stage_manager.update_stage_execution_failed(synthesis_stage_execution_id, error_msg)
                logger.error(f"{synthesis_config.agent} synthesis failed: {error_msg}")
            
            return (synthesis_stage_execution_id, synthesis_result)
            
        except asyncio.CancelledError:
            # Cancellation (timeout or user-requested) - mark stage appropriately
            await self._handle_stage_cancellation(
                session_id=chain_context.session_id,
                stage_execution_id=synthesis_stage_execution_id,
                description=f"{synthesis_config.agent} synthesis",
            )
            
            # Re-raise so the session-level timeout handler can process it
            # and set the correct session status (TIMED_OUT or CANCELLED)
            raise
            
        except Exception as e:
            error_msg = f"{synthesis_config.agent} synthesis failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            # Update synthesis stage as failed
            await self.stage_manager.update_stage_execution_failed(synthesis_stage_execution_id, error_msg)
            
            # Create error result
            error_result = AgentExecutionResult(
                status=StageStatus.FAILED,
                agent_name=synthesis_config.agent,
                stage_name="synthesis",
                timestamp_us=now_us(),
                result_summary=f"Synthesis failed: {str(e)}",
                error_message=error_msg
            )
            
            return (synthesis_stage_execution_id, error_result)