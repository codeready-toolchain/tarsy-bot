"""
Constants for Tarsy application.

This module defines all constant values used throughout the application
to ensure consistency and reduce hardcoded values.
"""

from typing import List


class AlertSessionStatus:
    """Constants for AlertSession status values."""
    
    PENDING = "pending"
    IN_PROGRESS = "in_progress"  
    COMPLETED = "completed"
    FAILED = "failed"
    
    # Helper lists for common use cases
    ACTIVE_STATUSES: List[str] = [PENDING, IN_PROGRESS]
    TERMINAL_STATUSES: List[str] = [COMPLETED, FAILED]
    ALL_STATUSES: List[str] = [PENDING, IN_PROGRESS, COMPLETED, FAILED]