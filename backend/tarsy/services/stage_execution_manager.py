"""
Stage Execution Manager for stage lifecycle management.

This module handles all stage execution lifecycle operations including:
- Creating stage execution records
- Updating stage execution status transitions
- Triggering stage execution hooks for history and dashboard updates
- Verifying stage execution persistence
"""

from typing import Optional, TYPE_CHECKING, Union

from tarsy.models.agent_execution_result import AgentExecutionResult, ParallelStageResult
from tarsy.models.constants import ParallelType, StageStatus
from tarsy.utils.logger import get_module_logger
from tarsy.utils.timestamp import now_us

if TYPE_CHECKING:
    from tarsy.models.agent_config import ChainStageConfigModel
    from tarsy.services.history_service import HistoryService
else:
    # Import for runtime use
    from tarsy.models.agent_config import ChainStageConfigModel

logger = get_module_logger(__name__)


class StageExecutionManager:
    """
    Manages stage execution lifecycle for agent chains.
    
    This class handles:
    - Creating stage execution records in the database
    - Status transitions (pending→active→completed/failed/paused)
    - Triggering hooks for history and dashboard updates
    - Verifying database persistence
    """
    
    def __init__(self, history_service: "HistoryService"):
        """
        Initialize the stage execution manager.
        
        Args:
            history_service: History service for database operations
        """
        self.history_service = history_service
    
    async def create_stage_execution(
        self,
        session_id: str,
        stage: ChainStageConfigModel,
        stage_index: int,
        parent_stage_execution_id: Optional[str] = None,
        parallel_index: int = 0,
        parallel_type: Union[ParallelType, str] = ParallelType.SINGLE.value,
        expected_parallel_count: Optional[int] = None,
    ) -> str:
        """
        Create a stage execution record with optional parallel execution tracking.
        
        Args:
            session_id: Session ID
            stage: Stage configuration model
            stage_index: Stage index in chain
            parent_stage_execution_id: Parent stage execution ID for parallel child stages
            parallel_index: Position in parallel group (0 for single/parent, 1-N for children)
            parallel_type: Execution type (ParallelType.SINGLE, MULTI_AGENT, or REPLICA)
            expected_parallel_count: Expected number of parallel children (only for parent stages)
            
        Returns:
            Stage execution ID
            
        Raises:
            RuntimeError: If stage execution record cannot be created
        """
        if not self.history_service:
            raise RuntimeError(
                f"Cannot create stage execution for '{stage.name}': History service is unavailable. "
                "All alert processing must be done as chains with proper stage tracking."
            )
        
        from tarsy.models.db_models import StageExecution
        stage_execution = StageExecution(
            session_id=session_id,
            stage_id=f"{stage.name}_{stage_index}",
            stage_index=stage_index,
            stage_name=stage.name,
            agent=stage.agent,
            status=StageStatus.PENDING.value,
            parent_stage_execution_id=parent_stage_execution_id,
            parallel_index=parallel_index,
            parallel_type=parallel_type,
            expected_parallel_count=expected_parallel_count,
            iteration_strategy=stage.iteration_strategy,
        )
        
        # Trigger stage execution hooks (history + dashboard) via context manager
        try:
            from tarsy.hooks.hook_context import stage_execution_context
            async with stage_execution_context(stage_execution):
                # Context automatically triggers hooks when exiting
                # History hook will create DB record and set execution_id on the model
                pass
            logger.debug(f"Successfully triggered hooks for stage execution {stage_index}: {stage.name}")
        except Exception as e:
            logger.error(f"Critical failure creating stage execution for '{stage.name}': {str(e)}")
            raise RuntimeError(
                f"Failed to create stage execution record for stage '{stage.name}' (index {stage_index}). "
                f"Chain processing cannot continue without proper stage tracking. Error: {str(e)}"
            ) from e
        
        # Verify the execution_id was properly set by the history hook
        if not hasattr(stage_execution, 'execution_id') or not stage_execution.execution_id:
            raise RuntimeError(
                f"Stage execution record for '{stage.name}' was created but execution_id is missing. "
                "This indicates a critical bug in the history service or database layer."
            )
        
        # CRITICAL: Verify the stage execution was actually created in the database
        # The hooks use safe_execute which catches exceptions and returns False instead of propagating
        # We need to explicitly verify the record exists in the database
        try:
            # Use the history service's proper method to verify the record exists
            verified_stage = await self.history_service.get_stage_execution(stage_execution.execution_id)
            
            if not verified_stage:
                raise RuntimeError(
                    f"Stage execution {stage_execution.execution_id} for '{stage.name}' was not found in database after creation. "
                    "The history hook may have failed silently. Check history service logs for errors."
                )
                
            logger.debug(f"Verified stage execution {stage_execution.execution_id} exists in database")
            
        except Exception as e:
            logger.error(f"Failed to verify stage execution in database: {e}")
            raise RuntimeError(
                f"Cannot verify stage execution {stage_execution.execution_id} was created in database. "
                f"Chain processing cannot continue without confirmation. Error: {str(e)}"
            ) from e
        
        return stage_execution.execution_id
    
    async def update_session_current_stage(self, session_id: str, stage_index: int, stage_execution_id: str) -> None:
        """
        Update the current stage information for a session.
        
        Args:
            session_id: Session ID
            stage_index: Current stage index
            stage_execution_id: Current stage execution ID
            
        Raises:
            RuntimeError: If session current stage cannot be updated
        """
        if not self.history_service:
            raise RuntimeError(
                f"Cannot update session current stage for '{session_id}': History service is unavailable. "
                "All alert processing must be done with proper stage tracking."
            )
        
        try:
            await self.history_service.update_session_current_stage(
                session_id=session_id,
                current_stage_index=stage_index,
                current_stage_id=stage_execution_id
            )
            
        except Exception as e:
            logger.error(f"Failed to update session current stage: {str(e)}")
            raise RuntimeError(
                f"Cannot update current stage information for session {session_id}. "
                f"Database persistence is required for stage tracking. Error: {str(e)}"
            ) from e
    
    async def update_stage_execution_completed(
        self, 
        stage_execution_id: str, 
        stage_result: Union[AgentExecutionResult, ParallelStageResult]
    ) -> None:
        """
        Update stage execution as completed.
        
        Args:
            stage_execution_id: Stage execution ID
            stage_result: Stage processing result (AgentExecutionResult or ParallelStageResult)
            
        Raises:
            RuntimeError: If stage execution cannot be updated to completed status
        """
        if not self.history_service:
            raise RuntimeError(
                f"Cannot update stage execution {stage_execution_id} as completed: History service is unavailable. "
                "All alert processing must be done with proper stage tracking."
            )
        
        try:
            # Get the existing stage execution record
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                raise RuntimeError(
                    f"Stage execution {stage_execution_id} not found in database for completion update. "
                    "This indicates a critical bug in stage lifecycle management."
                )
            
            # Update only the completion-related fields
            existing_stage.status = stage_result.status.value
            existing_stage.completed_at_us = stage_result.timestamp_us
            # Serialize result to JSON-compatible dict for database storage
            existing_stage.stage_output = stage_result.model_dump(mode='json')
            existing_stage.error_message = None
            
            # Calculate duration if we have started_at_us
            if existing_stage.started_at_us and existing_stage.completed_at_us:
                existing_stage.duration_ms = int((existing_stage.completed_at_us - existing_stage.started_at_us) / 1000)
            
            # Trigger stage execution hooks (history + dashboard) via context manager
            from tarsy.hooks.hook_context import stage_execution_context
            async with stage_execution_context(existing_stage):
                # Context automatically triggers hooks when exiting
                pass
            logger.debug(f"Triggered stage hooks for stage completion {existing_stage.stage_index}: {existing_stage.stage_id}")
            
        except Exception as e:
            logger.error(f"Failed to update stage execution as completed: {str(e)}")
            raise RuntimeError(
                f"Cannot update stage execution {stage_execution_id} to completed status. "
                f"Database persistence is required for audit trail. Error: {str(e)}"
            ) from e
    
    async def _update_stage_execution_terminal(
        self,
        stage_execution_id: str,
        status: StageStatus,
        error_message: str,
        operation_name: str,
    ) -> None:
        """
        Common logic for updating stage execution to terminal status (failed/cancelled).

        Args:
            stage_execution_id: Stage execution ID
            status: Terminal status (FAILED or CANCELLED)
            error_message: Error message or cancellation reason
            operation_name: Operation name for logging ("failed" or "cancelled")

        Raises:
            RuntimeError: If stage execution cannot be updated to terminal status
        """
        if not self.history_service:
            raise RuntimeError(
                f"Cannot update stage execution {stage_execution_id} as {operation_name}: History service is unavailable. "
                "All alert processing must be done with proper stage tracking."
            )

        try:
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                raise RuntimeError(
                    f"Stage execution {stage_execution_id} not found in database for {operation_name} update. "
                    "This indicates a critical bug in stage lifecycle management."
                )

            existing_stage.status = status.value
            existing_stage.completed_at_us = now_us()
            existing_stage.stage_output = None
            existing_stage.error_message = error_message

            if existing_stage.started_at_us and existing_stage.completed_at_us:
                existing_stage.duration_ms = int(
                    (existing_stage.completed_at_us - existing_stage.started_at_us) / 1000
                )

            from tarsy.hooks.hook_context import stage_execution_context

            async with stage_execution_context(existing_stage):
                pass
            logger.debug(
                "Triggered stage hooks for stage %s %s: %s",
                operation_name,
                existing_stage.stage_index,
                existing_stage.stage_id,
            )

        except Exception as e:
            logger.error(f"Failed to update stage execution as {operation_name}: {str(e)}")
            raise RuntimeError(
                f"Cannot update stage execution {stage_execution_id} to {operation_name} status. "
                f"Database persistence is required for audit trail. Error: {str(e)}"
            ) from e

    async def update_stage_execution_failed(self, stage_execution_id: str, error_message: str) -> None:
        """
        Update stage execution as failed.

        Args:
            stage_execution_id: Stage execution ID
            error_message: Error message

        Raises:
            RuntimeError: If stage execution cannot be updated to failed status
        """
        await self._update_stage_execution_terminal(
            stage_execution_id, StageStatus.FAILED, error_message, "failed"
        )

    async def update_stage_execution_cancelled(self, stage_execution_id: str, reason: str) -> None:
        """
        Update stage execution as cancelled.

        Args:
            stage_execution_id: Stage execution ID
            reason: Cancellation reason (e.g. "user_cancel", "shutdown", "timeout", "unknown")

        Raises:
            RuntimeError: If stage execution cannot be updated to cancelled status
        """
        await self._update_stage_execution_terminal(
            stage_execution_id, StageStatus.CANCELLED, reason, "cancelled"
        )
    
    async def update_stage_execution_paused(
        self, 
        stage_execution_id: str, 
        iteration: int, 
        paused_result: Optional[Union[AgentExecutionResult, ParallelStageResult]] = None
    ) -> None:
        """
        Update stage execution as paused.
        
        Args:
            stage_execution_id: Stage execution ID
            iteration: Current iteration number when paused
            paused_result: Optional partial result with conversation history (AgentExecutionResult or ParallelStageResult)
            
        Raises:
            RuntimeError: If stage execution cannot be updated to paused status
        """
        if not self.history_service:
            raise RuntimeError(
                f"Cannot update stage execution {stage_execution_id} as paused: History service is unavailable. "
                "All alert processing must be done with proper stage tracking."
            )
        
        try:
            # Get the existing stage execution record
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                raise RuntimeError(
                    f"Stage execution {stage_execution_id} not found in database for pause update. "
                    "This indicates a critical bug in stage lifecycle management."
                )
            
            # Update to paused status with iteration count
            existing_stage.status = StageStatus.PAUSED.value
            existing_stage.current_iteration = iteration
            existing_stage.paused_at_us = now_us()  # Track when paused for accurate duration calculation
            # Don't set completed_at_us - stage is not complete
            # IMPORTANT: Save conversation state so resume can continue from where it left off
            if paused_result:
                existing_stage.stage_output = paused_result.model_dump(mode='json')
                logger.info(f"Saved conversation state for paused stage {existing_stage.stage_name}")
            else:
                existing_stage.stage_output = None
            existing_stage.error_message = None
            
            # Trigger stage execution hooks (history + dashboard) via context manager
            from tarsy.hooks.hook_context import stage_execution_context
            async with stage_execution_context(existing_stage):
                # Context automatically triggers hooks when exiting
                pass
            logger.debug(f"Triggered stage hooks for stage pause {existing_stage.stage_index}: {existing_stage.stage_id}")
            
        except Exception as e:
            logger.error(f"Failed to update stage execution as paused: {str(e)}")
            raise RuntimeError(
                f"Cannot update stage execution {stage_execution_id} to paused status. "
                f"Database persistence is required for conversation state preservation. Error: {str(e)}"
            ) from e
    
    async def update_stage_execution_started(self, stage_execution_id: str) -> None:
        """
        Update stage execution as started.
        
        Handles PAUSED→ACTIVE transition for resumed sessions and initial PENDING→ACTIVE
        transition for new stages. Clears current_iteration for both cases to ensure
        consistent state management.
        
        Args:
            stage_execution_id: Stage execution ID
            
        Raises:
            RuntimeError: If stage execution cannot be updated to started status
        """
        if not self.history_service:
            raise RuntimeError(
                f"Cannot update stage execution {stage_execution_id} as started: History service is unavailable. "
                "All alert processing must be done with proper stage tracking."
            )
        
        try:
            # Get the existing stage execution record
            existing_stage = await self.history_service.get_stage_execution(stage_execution_id)
            if not existing_stage:
                raise RuntimeError(
                    f"Stage execution {stage_execution_id} not found in database for start update. "
                    "This indicates a critical bug in stage lifecycle management."
                )
            
            # Capture previous status before mutating for proper start time handling
            previous_status = existing_stage.status
            
            # Update to active status
            existing_stage.status = StageStatus.ACTIVE.value
            
            # Set started_at_us ONLY for new starts (PENDING→ACTIVE or no start time yet)
            # For PAUSED→ACTIVE (resumed), preserve original start time for accurate duration tracking
            if previous_status == StageStatus.PENDING.value or existing_stage.started_at_us is None:
                existing_stage.started_at_us = now_us()
            
            # Clear current_iteration for both new and resumed executions
            # Agent will set this during execution
            existing_stage.current_iteration = None
            
            # Trigger stage execution hooks (history + dashboard) via context manager
            from tarsy.hooks.hook_context import stage_execution_context
            async with stage_execution_context(existing_stage):
                # Context automatically triggers hooks when exiting
                # History hook will update DB record and dashboard hook will broadcast
                pass
            logger.debug(f"Triggered stage hooks for stage start {existing_stage.stage_index}: {existing_stage.stage_id}")
            
        except Exception as e:
            logger.error(f"Failed to update stage execution as started: {str(e)}")
            raise RuntimeError(
                f"Cannot update stage execution {stage_execution_id} to started status. "
                f"Database persistence is required for stage tracking. Error: {str(e)}"
            ) from e

