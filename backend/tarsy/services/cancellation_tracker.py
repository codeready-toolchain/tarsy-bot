"""
Cancellation Tracker - tracks user-initiated cancellation requests.

The ONLY reliable way to know a session was cancelled by user is when
the cancel endpoint is called. Everything else is a timeout.

Logic:
- When user calls cancel endpoint → mark session in this tracker
- When catching any exception → check tracker:
  - If session is marked → it's user cancellation (CANCELLED)
  - If session is NOT marked → it's a timeout (TIMED_OUT)
"""

import threading

from tarsy.utils.logger import get_module_logger

logger = get_module_logger(__name__)

# Sessions that have received a cancellation request from user
_cancelled_sessions: set[str] = set()
_lock = threading.Lock()


def mark_cancelled(session_id: str) -> None:
    """
    Mark a session as being cancelled by user.
    Call this from the cancel endpoint ONLY.
    """
    with _lock:
        _cancelled_sessions.add(session_id)
        logger.debug(f"Marked session {session_id} as user-cancelled")


def is_user_cancel(session_id: str) -> bool:
    """
    Check if session was cancelled by user.
    If True → use CANCELLED status
    If False → use TIMED_OUT status
    """
    with _lock:
        return session_id in _cancelled_sessions


def clear(session_id: str) -> None:
    """Clear the tracking for a session."""
    with _lock:
        _cancelled_sessions.discard(session_id)
