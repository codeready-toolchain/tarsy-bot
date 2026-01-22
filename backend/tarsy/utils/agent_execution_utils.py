"""
Utilities for agent execution result handling.

This module provides helpers for creating and manipulating agent execution
results and metadata, especially for error/exception scenarios.
"""

import asyncio
from typing import TYPE_CHECKING

from tarsy.models.agent_execution_result import AgentExecutionResult, AgentExecutionMetadata
from tarsy.models.constants import CancellationReason, StageStatus
from tarsy.utils.timestamp import now_us

if TYPE_CHECKING:
    from tarsy.models.agent_config import ChainStageConfigModel


def build_agent_result_from_exception(
    exception: BaseException,
    agent_name: str,
    stage_name: str,
    llm_provider: str,
    iteration_strategy: str,
    agent_started_at_us: int,
) -> tuple[AgentExecutionResult, AgentExecutionMetadata]:
    """
    Convert an exception to AgentExecutionResult and AgentExecutionMetadata.

    Handles both CancelledError (with reason extraction) and regular exceptions.
    For CancelledError, distinguishes between timeout (TIMED_OUT) and user cancellation (CANCELLED).

    Args:
        exception: The exception that occurred during agent execution
        agent_name: Name of the agent that failed
        stage_name: Name of the stage
        llm_provider: LLM provider used
        iteration_strategy: Iteration strategy used
        agent_started_at_us: Microsecond timestamp when agent started

    Returns:
        Tuple of (AgentExecutionResult, AgentExecutionMetadata)
    """
    # Determine status based on exception type and cancellation reason
    if isinstance(exception, asyncio.CancelledError):
        reason = extract_cancellation_reason(exception)
        if reason == CancellationReason.TIMEOUT.value:
            status = StageStatus.TIMED_OUT
            summary_prefix = "Execution timed out"
        else:
            status = StageStatus.CANCELLED
            summary_prefix = "Execution cancelled"
        error_message = reason
    else:
        status = StageStatus.FAILED
        error_message = str(exception) or type(exception).__name__
        summary_prefix = "Execution failed"

    agent_completed_at_us = now_us()

    result = AgentExecutionResult(
        status=status,
        agent_name=agent_name,
        stage_name=stage_name,
        timestamp_us=agent_completed_at_us,
        result_summary=f"{summary_prefix}: {error_message}",
        error_message=error_message,
    )

    metadata = AgentExecutionMetadata(
        agent_name=agent_name,
        llm_provider=llm_provider,
        iteration_strategy=iteration_strategy,
        started_at_us=agent_started_at_us,
        completed_at_us=agent_completed_at_us,
        status=status,
        error_message=error_message,
        token_usage=None,
    )

    return result, metadata


def get_stage_agent_label(stage: "ChainStageConfigModel") -> str:
    """
    Get a human-readable agent label for a stage.

    Handles both single-agent stages and parallel multi-agent stages.

    Args:
        stage: ChainStageConfigModel instance

    Returns:
        String label describing the agent(s) in the stage
    """
    if stage.agent:
        return stage.agent

    if stage.agents:
        parts: list[str] = []
        for agent in stage.agents:
            if isinstance(agent, str):
                parts.append(agent)
            else:
                parts.append(
                    getattr(agent, "agent", None) or getattr(agent, "name", None) or str(agent)
                )
        return ",".join(parts) if parts else "parallel_stage"

    return "parallel_stage"


def extract_cancellation_reason(exception: asyncio.CancelledError) -> str:
    """
    Extract cancellation reason from CancelledError.

    Args:
        exception: CancelledError instance

    Returns:
        Cancellation reason string (defaults to UNKNOWN if not found)
    """
    reason = str(exception.args[0]) if getattr(exception, "args", None) and exception.args else ""
    return reason or CancellationReason.UNKNOWN.value

