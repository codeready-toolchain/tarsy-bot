"""
Conversion utilities for history models.

This package provides minimal converters for format differences between
existing dict structures and new type-safe models. Only includes conversions
where actual format differences exist - no preemptive conversions.
"""

from .session_converters import (
    alert_session_to_session_overview,
    sessions_list_to_paginated_sessions
)
from .timeline_converters import (
    session_timeline_to_detailed_session
)

__all__ = [
    "alert_session_to_session_overview",
    "sessions_list_to_paginated_sessions", 
    "session_timeline_to_detailed_session"
]
