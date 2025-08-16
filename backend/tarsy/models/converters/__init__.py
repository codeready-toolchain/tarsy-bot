"""
Conversion utilities for history models.

This package provides minimal converters for format differences between
existing dict structures and new type-safe models. Only includes conversions
where actual format differences exist - no preemptive conversions.
"""

from .session_converters import (
    alert_session_to_session_overview,
)

__all__ = [
    "alert_session_to_session_overview",
]
