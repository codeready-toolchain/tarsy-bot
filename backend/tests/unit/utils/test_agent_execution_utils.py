"""
Unit tests for agent execution utilities.
"""

import asyncio

import pytest

from tarsy.models.agent_execution_result import AgentExecutionResult, AgentExecutionMetadata
from tarsy.models.constants import CancellationReason, StageStatus
from tarsy.utils.agent_execution_utils import (
    build_agent_result_from_exception,
    extract_cancellation_reason,
    get_stage_agent_label,
)


@pytest.mark.unit
class TestBuildAgentResultFromException:
    """Tests for build_agent_result_from_exception function."""

    def test_build_result_from_regular_exception(self) -> None:
        """Test creating result from a regular exception."""
        exception = ValueError("Something went wrong")
        agent_started_at_us = 1000000

        result, metadata = build_agent_result_from_exception(
            exception=exception,
            agent_name="test-agent",
            stage_name="test-stage",
            llm_provider="openai",
            iteration_strategy="adaptive",
            agent_started_at_us=agent_started_at_us,
        )

        # Verify result
        assert isinstance(result, AgentExecutionResult)
        assert result.status == StageStatus.FAILED
        assert result.agent_name == "test-agent"
        assert result.stage_name == "test-stage"
        assert result.error_message == "Something went wrong"
        assert "Execution failed: Something went wrong" in result.result_summary
        assert result.timestamp_us > agent_started_at_us

        # Verify metadata
        assert isinstance(metadata, AgentExecutionMetadata)
        assert metadata.status == StageStatus.FAILED
        assert metadata.agent_name == "test-agent"
        assert metadata.llm_provider == "openai"
        assert metadata.iteration_strategy == "adaptive"
        assert metadata.started_at_us == agent_started_at_us
        assert metadata.completed_at_us > agent_started_at_us
        assert metadata.error_message == "Something went wrong"
        assert metadata.token_usage is None

    def test_build_result_from_cancelled_error_with_user_cancel_reason(self) -> None:
        """Test creating result from CancelledError with user_cancel reason."""
        exception = asyncio.CancelledError("user_cancel")
        agent_started_at_us = 2000000

        result, metadata = build_agent_result_from_exception(
            exception=exception,
            agent_name="cancelled-agent",
            stage_name="cancelled-stage",
            llm_provider="anthropic",
            iteration_strategy="fixed",
            agent_started_at_us=agent_started_at_us,
        )

        # Verify result - user cancellation should use CANCELLED status
        assert result.status == StageStatus.CANCELLED
        assert result.agent_name == "cancelled-agent"
        assert result.stage_name == "cancelled-stage"
        assert result.error_message == "user_cancel"
        assert "Execution cancelled: user_cancel" in result.result_summary

        # Verify metadata
        assert metadata.status == StageStatus.CANCELLED
        assert metadata.error_message == "user_cancel"

    def test_build_result_from_cancelled_error_with_timeout_reason(self) -> None:
        """Test creating result from CancelledError with timeout reason."""
        exception = asyncio.CancelledError("timeout")
        agent_started_at_us = 2000000

        result, metadata = build_agent_result_from_exception(
            exception=exception,
            agent_name="timed-out-agent",
            stage_name="timed-out-stage",
            llm_provider="anthropic",
            iteration_strategy="fixed",
            agent_started_at_us=agent_started_at_us,
        )

        # Verify result - timeout should use TIMED_OUT status
        assert result.status == StageStatus.TIMED_OUT
        assert result.agent_name == "timed-out-agent"
        assert result.stage_name == "timed-out-stage"
        assert result.error_message == "timeout"
        assert "Execution timed out: timeout" in result.result_summary

        # Verify metadata
        assert metadata.status == StageStatus.TIMED_OUT
        assert metadata.error_message == "timeout"

    def test_build_result_from_cancelled_error_without_reason(self) -> None:
        """Test creating result from CancelledError without explicit reason."""
        exception = asyncio.CancelledError()
        agent_started_at_us = 3000000

        result, metadata = build_agent_result_from_exception(
            exception=exception,
            agent_name="agent",
            stage_name="stage",
            llm_provider="openai",
            iteration_strategy="adaptive",
            agent_started_at_us=agent_started_at_us,
        )

        # Should use UNKNOWN as default
        assert result.status == StageStatus.CANCELLED
        assert result.error_message == CancellationReason.UNKNOWN.value
        assert metadata.error_message == CancellationReason.UNKNOWN.value

    def test_build_result_from_exception_without_message(self) -> None:
        """Test creating result from exception with no message (uses type name)."""

        class CustomError(Exception):
            pass

        exception = CustomError()
        agent_started_at_us = 4000000

        result, metadata = build_agent_result_from_exception(
            exception=exception,
            agent_name="agent",
            stage_name="stage",
            llm_provider="openai",
            iteration_strategy="adaptive",
            agent_started_at_us=agent_started_at_us,
        )

        # Should use exception type name when no message
        assert result.error_message == "CustomError"
        assert metadata.error_message == "CustomError"

    def test_build_result_timestamps_are_consistent(self) -> None:
        """Test that result and metadata timestamps are consistent."""
        exception = RuntimeError("test")
        agent_started_at_us = 5000000

        result, metadata = build_agent_result_from_exception(
            exception=exception,
            agent_name="agent",
            stage_name="stage",
            llm_provider="openai",
            iteration_strategy="adaptive",
            agent_started_at_us=agent_started_at_us,
        )

        # Result timestamp and metadata completed_at_us should match
        assert result.timestamp_us == metadata.completed_at_us
        assert metadata.completed_at_us >= metadata.started_at_us


@pytest.mark.unit
class TestExtractCancellationReason:
    """Tests for extract_cancellation_reason function."""

    def test_extract_reason_with_explicit_reason(self) -> None:
        """Test extracting reason from CancelledError with explicit reason."""
        error = asyncio.CancelledError("timeout")
        reason = extract_cancellation_reason(error)
        assert reason == "timeout"

    def test_extract_reason_without_args(self) -> None:
        """Test extracting reason from CancelledError without args."""
        error = asyncio.CancelledError()
        reason = extract_cancellation_reason(error)
        assert reason == CancellationReason.UNKNOWN.value

    def test_extract_reason_with_empty_string(self) -> None:
        """Test extracting reason when arg is empty string."""
        error = asyncio.CancelledError("")
        reason = extract_cancellation_reason(error)
        # Empty string should fallback to UNKNOWN
        assert reason == CancellationReason.UNKNOWN.value

    def test_extract_reason_preserves_standard_reasons(self) -> None:
        """Test that standard cancellation reasons are preserved."""
        for standard_reason in [
            CancellationReason.USER_CANCEL.value,
            CancellationReason.TIMEOUT.value,
            CancellationReason.SHUTDOWN.value,
        ]:
            error = asyncio.CancelledError(standard_reason)
            reason = extract_cancellation_reason(error)
            assert reason == standard_reason


@pytest.mark.unit
class TestGetStageAgentLabel:
    """Tests for get_stage_agent_label function."""

    def test_get_label_from_single_agent_stage(self) -> None:
        """Test getting label from stage with single agent."""
        from tarsy.models.agent_config import ChainStageConfigModel

        stage = ChainStageConfigModel(
            name="test-stage",
            agent="kubernetes-investigator",
        )

        label = get_stage_agent_label(stage)
        assert label == "kubernetes-investigator"

    def test_get_label_from_parallel_stage_with_agent_configs(self) -> None:
        """Test getting label from parallel stage with ParallelAgentConfig objects."""
        from tarsy.models.agent_config import ChainStageConfigModel, ParallelAgentConfig

        stage = ChainStageConfigModel(
            name="parallel-stage",
            agents=[
                ParallelAgentConfig(name="agent1"),
                ParallelAgentConfig(name="agent2"),
                ParallelAgentConfig(name="agent3"),
            ],
        )

        label = get_stage_agent_label(stage)
        assert label == "agent1,agent2,agent3"

    def test_get_label_from_replicated_agent_stage(self) -> None:
        """Test getting label from replicated agent stage (single agent with replicas > 1)."""
        from tarsy.models.agent_config import ChainStageConfigModel

        stage = ChainStageConfigModel(
            name="replicated-stage",
            agent="database-investigator",
            replicas=3,
        )

        label = get_stage_agent_label(stage)
        # Replicated agent stages use single agent field
        assert label == "database-investigator"

    def test_get_label_handles_agent_attribute_extraction(self) -> None:
        """Test getting label when ParallelAgentConfig has only 'name' attribute."""
        from tarsy.models.agent_config import ChainStageConfigModel, ParallelAgentConfig

        stage = ChainStageConfigModel(
            name="parallel-stage",
            agents=[
                ParallelAgentConfig(name="kubernetes-agent"),
                ParallelAgentConfig(name="database-agent"),
            ],
        )

        label = get_stage_agent_label(stage)
        # Should extract from 'name' attribute
        assert label == "kubernetes-agent,database-agent"

