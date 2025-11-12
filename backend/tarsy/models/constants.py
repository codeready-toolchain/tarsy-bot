"""
Constants for Tarsy application.

This module defines all constant values used throughout the application
to ensure consistency and reduce hardcoded values.
"""

from enum import Enum
from typing import List


class AlertSessionStatus(Enum):
    """Status values for AlertSession processing."""
    
    PENDING = "pending"
    IN_PROGRESS = "in_progress"  
    CANCELING = "canceling"  # Intermediate state - cancellation requested
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"  # Terminal state - cancellation completed
    
    @classmethod
    def get_active_statuses(cls) -> List['AlertSessionStatus']:
        """Statuses that indicate session is still being processed."""
        return [cls.PENDING, cls.IN_PROGRESS, cls.CANCELING]
    
    @classmethod
    def get_terminal_statuses(cls) -> List['AlertSessionStatus']:
        """Statuses that indicate session processing is finished."""
        return [cls.COMPLETED, cls.FAILED, cls.CANCELLED]
    
    @classmethod
    def get_all_statuses(cls) -> List['AlertSessionStatus']:
        """All valid status values."""
        return list(cls)
    
    # Clean helper methods for easy usage
    @classmethod
    def values(cls) -> List[str]:
        """All status values as strings."""
        return [status.value for status in cls]
    
    @classmethod
    def active_values(cls) -> List[str]:
        """Active status values as strings."""
        return [status.value for status in cls.get_active_statuses()]
    
    @classmethod
    def terminal_values(cls) -> List[str]:
        """Terminal status values as strings."""
        return [status.value for status in cls.get_terminal_statuses()]


class StageStatus(Enum):
    """Status values for individual stage execution within a chain."""
    
    PENDING = "pending"
    ACTIVE = "active" 
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # Some results but with warnings/issues


class ChainStatus(Enum):
    """Status values for overall chain execution progress (calculated from stage statuses)."""
    
    PENDING = "pending"        # All stages pending
    PROCESSING = "processing"  # At least one stage active
    COMPLETED = "completed"    # All stages completed successfully  
    FAILED = "failed"          # One or more stages failed, no active stages
    PARTIAL = "partial"        # Mix of completed and failed, no active stages


class SystemHealthStatus(Enum):
    """Status values for system health monitoring."""
    
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class IterationStrategy(str, Enum):
    """
    Available iteration strategies for agent processing.
    
    Each strategy implements a different approach to alert analysis:
    - REACT: Standard ReAct pattern with Think→Action→Observation cycles for complete analysis
    - REACT_STAGE: ReAct pattern for stage-specific analysis within multi-stage chains
    - REACT_FINAL_ANALYSIS: ReAct final analysis only, no tools, uses all accumulated data
    """
    REACT = "react"
    REACT_STAGE = "react-stage"           # ReAct pattern for stage-specific analysis
    REACT_FINAL_ANALYSIS = "react-final-analysis"   # ReAct final analysis only, no tools


class LLMInteractionType(str, Enum):
    """
    Types of LLM interactions for categorization and UI rendering.
    
    - INVESTIGATION: ReAct investigation/reasoning iterations (thought/action/observation loops)
    - SUMMARIZATION: MCP result summarization calls (reduce large tool outputs)
    - FINAL_ANALYSIS: Stage conclusion with "Final Answer:" (any stage, any strategy)
    """
    INVESTIGATION = "investigation"
    SUMMARIZATION = "summarization"
    FINAL_ANALYSIS = "final_analysis"


# Interaction types that should be included in chat context
# When adding a new LLMInteractionType, decide if it represents meaningful investigation
# context that should be shown to users in follow-up chats
CHAT_CONTEXT_INTERACTION_TYPES: frozenset[str] = frozenset({
    LLMInteractionType.INVESTIGATION.value,
    LLMInteractionType.FINAL_ANALYSIS.value,
    # SUMMARIZATION is excluded - it's internal tool result processing, not investigation context
})


class StreamingEventType(str, Enum):
    """
    Types of LLM streaming events for real-time WebSocket delivery.
    
    - THOUGHT: Complete "Thought:" section from ReAct pattern
    - FINAL_ANSWER: Complete "Final Answer:" section from ReAct pattern
    - SUMMARIZATION: Plain text summarization of tool results
    """
    THOUGHT = "thought"
    FINAL_ANSWER = "final_answer"
    SUMMARIZATION = "summarization"


# ==============================================================================
# LLM CONFIGURATION CONSTANTS
# ==============================================================================

# Default temperature for LLM interactions
# Lower temperature (0.1) ensures more deterministic and focused responses
DEFAULT_LLM_TEMPERATURE = 0.1

# Maximum size for LLM interaction message content before hook processing
MAX_LLM_MESSAGE_CONTENT_SIZE = 1048576  # 1MB