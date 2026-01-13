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
    PAUSED = "paused"  # Waiting for user resume - active but not processing
    CANCELING = "canceling"  # Intermediate state - cancellation requested
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"  # Terminal state - cancellation completed
    TIMED_OUT = "timed_out"  # System timeout (session processing timeout)
    
    @classmethod
    def get_active_statuses(cls) -> List['AlertSessionStatus']:
        """Statuses that indicate session is still being processed."""
        return [cls.PENDING, cls.IN_PROGRESS, cls.PAUSED, cls.CANCELING]
    
    @classmethod
    def get_terminal_statuses(cls) -> List['AlertSessionStatus']:
        """Statuses that indicate session processing is finished."""
        return [cls.COMPLETED, cls.FAILED, cls.CANCELLED, cls.TIMED_OUT]
    
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
    PAUSED = "paused"  # Waiting for user resume
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"  # User-initiated cancellation only
    TIMED_OUT = "timed_out"  # System timeout (session/iteration timeout)
    PARTIAL = "partial"  # Some results but with warnings/issues
    
    def is_error(self) -> bool:
        """Check if this status represents an error/failure state."""
        return self in (StageStatus.FAILED, StageStatus.CANCELLED, StageStatus.TIMED_OUT)
    
    def is_terminal(self) -> bool:
        """Check if this status is terminal (stage processing is finished)."""
        return self in (StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.CANCELLED, StageStatus.TIMED_OUT)
    
    @classmethod
    def get_error_statuses(cls) -> List['StageStatus']:
        """Get all error/failure status values."""
        return [cls.FAILED, cls.CANCELLED, cls.TIMED_OUT]


class CancellationReason(str, Enum):
    """Standardized reasons for task/stage cancellation."""

    USER_CANCEL = "user_cancel"
    TIMEOUT = "timeout"
    SHUTDOWN = "shutdown"
    UNKNOWN = "unknown"


class ParallelType(str, Enum):
    """Types of parallel execution for stage executions (EP-0030)."""
    
    SINGLE = "single"  # Non-parallel (regular) stage execution
    MULTI_AGENT = "multi_agent"  # Different agents running in parallel
    REPLICA = "replica"  # Same agent running multiple times for redundancy
    
    @classmethod
    def values(cls) -> List[str]:
        """All parallel type values as strings."""
        return [ptype.value for ptype in cls]
    
    @classmethod
    def parallel_values(cls) -> List[str]:
        """Parallel execution type values (excluding SINGLE)."""
        return [cls.MULTI_AGENT.value, cls.REPLICA.value]


class SuccessPolicy(str, Enum):
    """Success policy for parallel stage execution (EP-0030).
    
    Determines success criteria when multiple agents run in parallel:
    - ALL: All agents must succeed for the stage to succeed (strict)
    - ANY: At least one agent must succeed for the stage to succeed (resilient, default)
    
    Note: Renamed from FailurePolicy for clarity. Old name still supported for backward compatibility.
    """
    ALL = "all"
    ANY = "any"


# Backward compatibility alias
FailurePolicy = SuccessPolicy


class ProgressPhase(str, Enum):
    """Progress phases for session processing status updates.
    
    These phases provide user-friendly status messages during alert processing.
    """
    INVESTIGATING = "investigating"   # Default phase - agents are investigating the issue
    GATHERING_INFO = "gathering_info" # MCP tool execution (collecting data from systems)
    SYNTHESIZING = "synthesizing"     # Synthesis agent is combining parallel results
    DISTILLING = "distilling"         # MCP tool result summarization (reduces large outputs)
    CONCLUDING = "concluding"         # Forced conclusion at iteration limit
    FINALIZING = "finalizing"         # Executive summary generation at chain completion


class ChainStatus(Enum):
    """Status values for overall chain execution progress (calculated from stage statuses)."""
    
    PENDING = "pending"        # All stages pending
    PROCESSING = "processing"  # At least one stage active
    PAUSED = "paused"          # Execution paused, waiting for user action to resume
    COMPLETED = "completed"    # All stages completed successfully  
    FAILED = "failed"          # One or more stages failed, no active stages
    TIMED_OUT = "timed_out"    # One or more stages timed out, no active stages


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
    - NATIVE_THINKING: Gemini-specific native thinking with structured function calling (no text parsing)
    - SYNTHESIS: Generic synthesis strategy for parallel results (no tools, provider-agnostic)
    - SYNTHESIS_NATIVE_THINKING: Gemini synthesis with native thinking for deep reasoning
    """
    REACT = "react"
    REACT_STAGE = "react-stage"           # ReAct pattern for stage-specific analysis
    REACT_FINAL_ANALYSIS = "react-final-analysis"   # ReAct final analysis only, no tools
    NATIVE_THINKING = "native-thinking"   # Gemini native thinking + function calling
    SYNTHESIS = "synthesis"               # Generic synthesis (no tools)
    SYNTHESIS_NATIVE_THINKING = "synthesis-native-thinking"  # Gemini synthesis with thinking


class ScoringStatus(Enum):
    """Status values for session scoring operations."""

    PENDING = "pending"           # Scoring queued but not started
    IN_PROGRESS = "in_progress"   # LLM currently scoring the session
    COMPLETED = "completed"       # Scoring finished successfully
    FAILED = "failed"            # Scoring failed with error

    @classmethod
    def active_values(cls) -> List[str]:
        """Active status values (scoring in progress)."""
        return [cls.PENDING.value, cls.IN_PROGRESS.value]

    @classmethod
    def values(cls) -> List[str]:
        """All status values as strings."""
        return [status.value for status in cls]


class LLMInteractionType(str, Enum):
    """
    Types of LLM interactions for categorization and UI rendering.
    
    - INVESTIGATION: ReAct investigation/reasoning iterations (thought/action/observation loops)
    - SUMMARIZATION: MCP result summarization calls (reduce large tool outputs)
    - FINAL_ANALYSIS: Stage conclusion with "Final Answer:" (any stage, any strategy)
    - FORCED_CONCLUSION: Forced conclusion at max iterations (incomplete investigation)
    - FINAL_ANALYSIS_SUMMARY: Executive summary of final analysis (dashboard display, notifications)
    """
    INVESTIGATION = "investigation"
    SUMMARIZATION = "summarization"
    FINAL_ANALYSIS = "final_analysis"
    FORCED_CONCLUSION = "forced_conclusion"
    FINAL_ANALYSIS_SUMMARY = "final_analysis_summary"


# Interaction types that should be included in chat context
# When adding a new LLMInteractionType, decide if it represents meaningful investigation
# context that should be shown to users in follow-up chats
CHAT_CONTEXT_INTERACTION_TYPES: frozenset[str] = frozenset({
    LLMInteractionType.INVESTIGATION.value,
    LLMInteractionType.FINAL_ANALYSIS.value,
    LLMInteractionType.FORCED_CONCLUSION.value,
    # SUMMARIZATION is excluded - it's internal tool result processing, not investigation context
    # FINAL_ANALYSIS_SUMMARY excluded - it's a condensed summary, full analysis already included
})


class StreamingEventType(str, Enum):
    """
    Types of LLM streaming events for real-time WebSocket delivery.
    
    - THOUGHT: Complete "Thought:" section from ReAct pattern
    - FINAL_ANSWER: Complete "Final Answer:" section from ReAct pattern
    - INTERMEDIATE_RESPONSE: Assistant response during intermediate iterations (native thinking)
    - SUMMARIZATION: Plain text summarization of tool results
    - NATIVE_THINKING: Native thinking summaries from Gemini models (distinct from ReAct thoughts)
    """
    THOUGHT = "thought"
    FINAL_ANSWER = "final_answer"
    INTERMEDIATE_RESPONSE = "intermediate_response"
    SUMMARIZATION = "summarization"
    NATIVE_THINKING = "native_thinking"


# ==============================================================================
# LLM CONFIGURATION CONSTANTS
# ==============================================================================

# Maximum size for LLM interaction message content before hook processing
MAX_LLM_MESSAGE_CONTENT_SIZE = 1048576  # 1MB