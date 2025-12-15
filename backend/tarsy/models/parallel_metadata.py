"""Parallel execution metadata for streaming events."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ParallelExecutionMetadata:
    """
    Metadata about parallel execution for enriching streaming events.
    
    This allows the frontend to filter and display streaming content
    from the correct parallel agent without complex enrichment logic.
    """
    
    parent_stage_execution_id: Optional[str] = None
    """Parent stage execution ID for parallel child stages."""
    
    parallel_index: Optional[int] = None
    """Position in parallel group (1-N for parallel children, None for single stages)."""
    
    agent_name: Optional[str] = None
    """Agent name for this execution."""
    
    def is_parallel(self) -> bool:
        """Check if this represents a parallel execution."""
        return self.parallel_index is not None and self.parallel_index > 0

