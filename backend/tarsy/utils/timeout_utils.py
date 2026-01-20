"""
Utilities for timeout handling and error message generation.

This module provides helper functions to create detailed, contextual error messages
when stages or interactions time out, making it easy to diagnose whether a component
legitimately took too long or didn't have enough time due to session timeout.
"""

from tarsy.utils.timestamp import now_us


def create_stage_timeout_message(
    stage_name: str,
    stage_started_at_us: int,
    session_started_at_us: int,
    timeout_seconds: int
) -> str:
    """
    Create a detailed timeout error message for a stage.
    
    Includes timing context to help diagnose whether the stage legitimately
    took too long, or didn't have enough time due to earlier stages consuming
    most of the session timeout budget.
    
    Args:
        stage_name: Name of the stage that timed out (e.g., "synthesis")
        stage_started_at_us: When the stage started (microseconds since epoch)
        session_started_at_us: When the session started (microseconds since epoch)
        timeout_seconds: Total session timeout in seconds
        
    Returns:
        Formatted error message with timing context
        
    Example:
        >>> create_stage_timeout_message("synthesis", 1768927469090903, 1768926881059833, 600)
        "synthesis stage timed out after 12.2s (started at +588.0s into session, session timeout: 600s)"
    """
    current_time_us = now_us()
    
    # Calculate durations
    stage_duration_s = (current_time_us - stage_started_at_us) / 1_000_000
    stage_start_offset_s = (stage_started_at_us - session_started_at_us) / 1_000_000
    
    # Create descriptive message with full timing context
    message = (
        f"{stage_name} stage timed out after {stage_duration_s:.1f}s "
        f"(started at +{stage_start_offset_s:.1f}s into session, "
        f"session timeout: {timeout_seconds}s)"
    )
    
    return message


def create_interaction_timeout_message(
    operation_name: str,
    duration_s: float,
    context: str = "session timeout reached"
) -> str:
    """
    Create a timeout error message for an LLM/MCP interaction.
    
    Args:
        operation_name: Name of the operation (e.g., "LLM request", "MCP tool call")
        duration_s: How long the operation ran before timing out
        context: Additional context (default: "session timeout reached")
        
    Returns:
        Formatted error message
        
    Example:
        >>> create_interaction_timeout_message("LLM request", 12.1)
        "LLM request timed out after 12.1s (session timeout reached)"
    """
    return f"{operation_name} timed out after {duration_s:.1f}s ({context})"
