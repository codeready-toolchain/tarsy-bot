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
    COMPLETED = "completed"
    FAILED = "failed"
    
    @classmethod
    def get_active_statuses(cls) -> List['AlertSessionStatus']:
        """Statuses that indicate session is still being processed."""
        return [cls.PENDING, cls.IN_PROGRESS]
    
    @classmethod
    def get_terminal_statuses(cls) -> List['AlertSessionStatus']:
        """Statuses that indicate session processing is finished."""
        return [cls.COMPLETED, cls.FAILED]
    
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
    - REGULAR: Simple tool iteration without reasoning overhead
    - REACT: Standard ReAct pattern with Think→Action→Observation cycles
    - REACT_TOOLS: ReAct pattern focused on data collection only, no analysis
    - REACT_TOOLS_PARTIAL: ReAct + tools + partial analysis for incremental insights
    - REACT_FINAL_ANALYSIS: ReAct final analysis only, no tools, uses all accumulated data
    """
    REGULAR = "regular"
    REACT = "react"
    
    # NEW: Tool-focused strategies (data collection only)
    REACT_TOOLS = "react-tools"           # ReAct pattern, tools only, no analysis
    
    # NEW: Analysis-focused strategies  
    REACT_TOOLS_PARTIAL = "react-tools-partial"     # ReAct + tools + partial analysis
    REACT_FINAL_ANALYSIS = "react-final-analysis"   # ReAct final analysis only, no tools