"""
Unit tests for timeout utility functions.

Tests the helper functions used to generate detailed timeout error messages
with timing context for stages and interactions.
"""

import pytest
from unittest.mock import patch

from tarsy.utils.timeout_utils import (
    create_stage_timeout_message,
    create_interaction_timeout_message,
)


@pytest.mark.unit
class TestCreateStageTimeoutMessage:
    """Test create_stage_timeout_message function."""

    def test_creates_message_with_timing_context(self):
        """Test that message includes stage duration, offset, and session timeout."""
        # Session started at time 0, stage started 588s later, now is 600s (12s stage duration)
        session_started_at_us = 1_000_000_000_000  # Arbitrary timestamp
        stage_started_at_us = session_started_at_us + (588 * 1_000_000)
        current_time_us = session_started_at_us + (600 * 1_000_000)
        
        with patch('tarsy.utils.timeout_utils.now_us', return_value=current_time_us):
            message = create_stage_timeout_message(
                stage_name="synthesis",
                stage_started_at_us=stage_started_at_us,
                session_started_at_us=session_started_at_us,
                timeout_seconds=600
            )
        
        # Should include all timing components
        assert "synthesis stage timed out after 12.0s" in message
        assert "started at +588.0s into session" in message
        assert "session timeout: 600s" in message

    def test_handles_stage_started_immediately(self):
        """Test message when stage started at session start (offset 0)."""
        session_started_at_us = 1_000_000_000_000
        stage_started_at_us = session_started_at_us
        current_time_us = session_started_at_us + (10 * 1_000_000)
        
        with patch('tarsy.utils.timeout_utils.now_us', return_value=current_time_us):
            message = create_stage_timeout_message(
                stage_name="security-analysis",
                stage_started_at_us=stage_started_at_us,
                session_started_at_us=session_started_at_us,
                timeout_seconds=900
            )
        
        assert "security-analysis stage timed out after 10.0s" in message
        assert "started at +0.0s into session" in message
        assert "session timeout: 900s" in message

    def test_handles_fractional_seconds(self):
        """Test that fractional seconds are formatted correctly."""
        session_started_at_us = 1_000_000_000_000
        stage_started_at_us = session_started_at_us + (123_456_789)  # 123.456789s
        current_time_us = stage_started_at_us + (45_678_912)  # 45.678912s duration
        
        with patch('tarsy.utils.timeout_utils.now_us', return_value=current_time_us):
            message = create_stage_timeout_message(
                stage_name="analysis",
                stage_started_at_us=stage_started_at_us,
                session_started_at_us=session_started_at_us,
                timeout_seconds=900
            )
        
        # Should format to 1 decimal place
        assert "45.7s" in message or "45.6s" in message  # Rounding may vary
        assert "123.5s" in message or "123.4s" in message

    @pytest.mark.parametrize(
        "stage_name,timeout_seconds",
        [
            ("synthesis", 600),
            ("security-analysis", 900),
            ("root-cause-analysis", 1200),
            ("data-gathering", 300),
        ],
    )
    def test_includes_stage_name_and_timeout(self, stage_name: str, timeout_seconds: int):
        """Test that stage name and timeout value are included in message."""
        session_started_at_us = 1_000_000_000_000
        stage_started_at_us = session_started_at_us + (100 * 1_000_000)
        current_time_us = stage_started_at_us + (10 * 1_000_000)
        
        with patch('tarsy.utils.timeout_utils.now_us', return_value=current_time_us):
            message = create_stage_timeout_message(
                stage_name=stage_name,
                stage_started_at_us=stage_started_at_us,
                session_started_at_us=session_started_at_us,
                timeout_seconds=timeout_seconds
            )
        
        assert stage_name in message
        assert f"{timeout_seconds}s)" in message


@pytest.mark.unit
class TestCreateInteractionTimeoutMessage:
    """Test create_interaction_timeout_message function."""

    def test_creates_message_with_default_context(self):
        """Test message creation with default context."""
        message = create_interaction_timeout_message(
            operation_name="LLM request",
            duration_s=12.1
        )
        
        assert message == "LLM request timed out after 12.1s (session timeout reached)"

    def test_creates_message_with_custom_context(self):
        """Test message creation with custom context."""
        message = create_interaction_timeout_message(
            operation_name="MCP tool call",
            duration_s=5.3,
            context="exceeded tool execution timeout"
        )
        
        assert message == "MCP tool call timed out after 5.3s (exceeded tool execution timeout)"

    @pytest.mark.parametrize(
        "operation,duration,context,expected_pattern",
        [
            ("LLM request", 10.0, "session timeout", "LLM request timed out after 10.0s (session timeout)"),
            ("MCP call", 0.5, "quick timeout", "MCP call timed out after 0.5s (quick timeout)"),
            ("Database query", 120.7, "query limit", "Database query timed out after 120.7s (query limit)"),
            ("API request", 30.0, "connection timeout", "API request timed out after 30.0s (connection timeout)"),
        ],
    )
    def test_message_format_variations(
        self, operation: str, duration: float, context: str, expected_pattern: str
    ):
        """Test various operation names, durations, and contexts."""
        message = create_interaction_timeout_message(
            operation_name=operation,
            duration_s=duration,
            context=context
        )
        
        assert message == expected_pattern

    def test_handles_very_small_durations(self):
        """Test message with sub-second durations."""
        message = create_interaction_timeout_message(
            operation_name="Quick operation",
            duration_s=0.001
        )
        
        assert "0.0s" in message  # Should format to 1 decimal place

    def test_handles_very_large_durations(self):
        """Test message with large durations."""
        message = create_interaction_timeout_message(
            operation_name="Long operation",
            duration_s=3600.5
        )
        
        assert "3600.5s" in message
