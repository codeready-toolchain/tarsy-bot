"""
Response Formatter for alert processing responses.

This module provides formatting utilities for alert processing responses,
including success responses, chain responses, and error responses.
"""

from typing import Any, Dict, Optional, TYPE_CHECKING

from tarsy.utils.timestamp import now_us

if TYPE_CHECKING:
    from tarsy.models.agent_config import ChainConfigModel
    from tarsy.models.processing_context import ChainContext


# ============================================================================
# Helper Functions
# ============================================================================

def _format_alert_severity(alert_data: Dict[str, Any]) -> str:
    """Format alert severity for API responses."""
    return alert_data.get('severity', 'warning')


def _format_alert_environment(alert_data: Dict[str, Any]) -> str:
    """Format alert environment for API responses."""
    return alert_data.get('environment', 'production')


# ============================================================================
# Main Formatting Functions
# ============================================================================

def format_success_response(
    chain_context: "ChainContext",
    agent_name: str,
    analysis: str,
    iterations: int,
    timestamp_us: Optional[int] = None
) -> str:
    """
    Format successful analysis response for single-agent processing.
    
    Args:
        chain_context: The alert processing data with validated structure
        agent_name: Name of the agent that processed the alert
        analysis: Analysis result from the agent
        iterations: Number of iterations performed
        timestamp_us: Processing timestamp in microseconds since epoch UTC
        
    Returns:
        Formatted response string
    """
    # Convert unix timestamp to string for display
    if timestamp_us:
        timestamp_str = f"{timestamp_us}"  # Keep as unix timestamp for consistency
    else:
        timestamp_str = f"{now_us()}"  # Current unix timestamp
    
    response_parts = [
        "# Alert Analysis Report",
        "",
        f"**Alert Type:** {chain_context.processing_alert.alert_type}",
        f"**Processing Agent:** {agent_name}",
        f"**Environment:** {_format_alert_environment(chain_context.processing_alert.alert_data)}",
        f"**Severity:** {_format_alert_severity(chain_context.processing_alert.alert_data)}",
        f"**Timestamp:** {timestamp_str}",
        "",
        "## Analysis",
        "",
        analysis,
        "",
        "---",
        f"*Processed by {agent_name} in {iterations} iterations*"
    ]
    
    return "\n".join(response_parts)


def format_chain_success_response(
    chain_context: "ChainContext",
    chain_definition: "ChainConfigModel",
    analysis: str,
    timestamp_us: Optional[int] = None
) -> str:
    """
    Format successful analysis response for chain processing.
    
    Args:
        chain_context: The alert processing data with validated structure
        chain_definition: Chain definition that was executed
        analysis: Combined analysis result from all stages
        timestamp_us: Processing timestamp in microseconds since epoch UTC
        
    Returns:
        Formatted response string
    """
    # Convert unix timestamp to string for display
    if timestamp_us:
        timestamp_str = f"{timestamp_us}"  # Keep as unix timestamp for consistency
    else:
        timestamp_str = f"{now_us()}"  # Current unix timestamp
    
    response_parts = [
        "# Alert Analysis Report",
        "",
        f"**Alert Type:** {chain_context.processing_alert.alert_type}",
        f"**Processing Chain:** {chain_definition.chain_id}",
        f"**Stages:** {len(chain_definition.stages)}",
        f"**Environment:** {_format_alert_environment(chain_context.processing_alert.alert_data)}",
        f"**Severity:** {_format_alert_severity(chain_context.processing_alert.alert_data)}",
        f"**Timestamp:** {timestamp_str}",
        "",
        "## Analysis",
        "",
        analysis,
        "",
        "---",
        f"*Processed through {len(chain_definition.stages)} stages*"
    ]
    
    return "\n".join(response_parts)


def format_error_response(
    chain_context: "ChainContext",
    error: str,
    agent_name: Optional[str] = None
) -> str:
    """
    Format error response for alert data.
    
    Args:
        chain_context: The alert processing data with validated structure
        error: Error message
        agent_name: Name of the agent if known
        
    Returns:
        Formatted error response string
    """
    response_parts = [
        "# Alert Processing Error",
        "",
        f"**Alert Type:** {chain_context.processing_alert.alert_type}",
        f"**Environment:** {_format_alert_environment(chain_context.processing_alert.alert_data)}",
        f"**Error:** {error}",
    ]
    
    if agent_name:
        response_parts.append(f"**Failed Agent:** {agent_name}")
    
    response_parts.extend([
        "",
        "## Troubleshooting",
        "",
        "1. Check that the alert type is supported",
        "2. Verify agent configuration in settings",
        "3. Ensure all required services are available",
        "4. Review logs for detailed error information"
    ])
    
    return "\n".join(response_parts)

