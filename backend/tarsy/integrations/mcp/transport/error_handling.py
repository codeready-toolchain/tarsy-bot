"""
Shared error handling utilities for MCP transports.

Provides helpers for detecting and classifying transport-level errors
that can be safely suppressed during teardown operations.
"""

import httpx


_CANCEL_SCOPE_MISMATCH_MESSAGE = "Attempted to exit cancel scope in a different task than it was entered in"


def is_cancel_scope_mismatch_error(exc: BaseException) -> bool:
    """
    Detect the known AnyIO cancel-scope cleanup bug.

    This error occurs when async generator-based context managers are
    finalized in a different task than they were created in. Safe to
    suppress during transport teardown.

    Args:
        exc: Exception to check

    Returns:
        True if this is the known cancel scope mismatch error
    """
    return isinstance(exc, RuntimeError) and _CANCEL_SCOPE_MISMATCH_MESSAGE in str(exc)


def is_safe_teardown_error(exc: BaseException) -> bool:
    """
    Determine if an exception during transport teardown is safe to suppress.

    We only suppress:
    - The known AnyIO cancel-scope mismatch RuntimeError
    - Expected connection/stream shutdown errors from MCP SDK task groups
    - BaseExceptionGroups where all sub-exceptions are safe

    Args:
        exc: Exception raised during teardown

    Returns:
        True if safe to suppress, False if it should be re-raised
    """
    if is_cancel_scope_mismatch_error(exc):
        return True

    if isinstance(exc, BaseExceptionGroup):
        return all(is_safe_teardown_error(e) for e in exc.exceptions)

    if isinstance(exc, (httpx.ConnectError, httpx.TransportError, GeneratorExit)):
        return True

    return False

