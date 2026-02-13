import asyncio
import logging
import random
import time
from typing import Awaitable, Callable, Final, List, Optional, TypeVar

from sqlalchemy.exc import DBAPIError

from tarsy.repositories.base_repository import DatabaseManager

T = TypeVar("T")
logger = logging.getLogger(__name__)

# SQLite retryable error keywords
SQLITE_RETRYABLE_KEYWORDS: Final[tuple[str, ...]] = (
    "database is locked",
    "database disk image is malformed",
    "sqlite3.operationalerror",
    "database table is locked",
)

# PostgreSQL retryable error keywords (fallback when SQLSTATE unavailable)
POSTGRESQL_RETRYABLE_KEYWORDS: Final[tuple[str, ...]] = (
    "serialization failure",
    "deadlock detected",
    "could not obtain lock",
    "too many connections",
    "could not connect",
    "connection refused",
    "server closed the connection",
    "connection timed out",
    "connection reset",
)

# Common retryable error keywords (both SQLite and PostgreSQL)
COMMON_RETRYABLE_KEYWORDS: Final[tuple[str, ...]] = (
    "connection timeout",
    "connection pool",
    "connection closed",
)

# PostgreSQL SQLSTATE codes that indicate retryable transient errors
# 40001: serialization_failure
# 40P01: deadlock_detected
# 55P03: lock_not_available
# 53300: too_many_connections
# 57014: query_canceled
# Class 08: connection exceptions (08000, 08003, 08006, etc.)
POSTGRESQL_RETRYABLE_SQLSTATES: Final[frozenset[str]] = frozenset(
    {
        "40001",  # serialization_failure
        "40P01",  # deadlock_detected
        "55P03",  # lock_not_available
        "53300",  # too_many_connections
        "57014",  # query_canceled
    }
)

POSTGRESQL_RETRYABLE_SQLSTATE_CLASS: Final[str] = "08"  # Connection exception class


class DatabaseRetries:
    def __init__(
        self,
        *,
        db_manager: DatabaseManager,
        max_retries: int,
        base_delay: float,
        max_delay: float,
        non_retriable_ops: Optional[List[str]] = None,
    ):
        self.db_manager = db_manager
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        if non_retriable_ops is None:
            self._non_retriable_ops = []
        else:
            self._non_retriable_ops = non_retriable_ops

    def database_operation(
        self,
        operation_name: str,
        operation_func: Callable[[], T],
        *,
        treat_none_as_success: bool = False,
    ) -> Optional[T]:
        """Retry database operations with exponential backoff."""
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                result = operation_func()
                if result is not None:
                    return result
                if treat_none_as_success:
                    return None
                logger.warning(
                    f"Database operation '{operation_name}' returned None on attempt {attempt + 1}"
                )

            except Exception as e:
                last_exception = e
                is_retryable = self._is_retryable_error(e)

                if operation_name in self._non_retriable_ops:
                    logger.warning(
                        f"Not retrying {operation_name} after database error: {str(e)}"
                    )
                    return None

                if not is_retryable or attempt == self.max_retries:
                    logger.error(
                        f"Database operation '{operation_name}' failed after {attempt + 1} attempts: {str(e)}"
                    )
                    return None

                delay = min(self.base_delay * (2**attempt), self.max_delay)
                jitter = random.uniform(0, delay * 0.1)
                total_delay = delay + jitter

                logger.warning(
                    f"Database operation '{operation_name}' failed on attempt {attempt + 1}, retrying in {total_delay:.2f}s: {str(e)}"
                )
                time.sleep(total_delay)

        logger.error(
            f"Database operation '{operation_name}' failed after all retries. Last error: {str(last_exception)}"
        )
        return None

    async def async_database_operation(
        self,
        operation_name: str,
        operation_func: Callable[[], Awaitable[T]],
        *,
        treat_none_as_success: bool = False,
    ) -> Optional[T]:
        """Async retry database operations with exponential backoff."""
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                result = await operation_func()
                if result is not None:
                    return result
                if treat_none_as_success:
                    return None
                logger.warning(
                    f"Database operation '{operation_name}' returned None on attempt {attempt + 1}"
                )
            except Exception as e:
                last_exception = e
                is_retryable = self._is_retryable_error(e)
                if operation_name in self._non_retriable_ops:
                    logger.warning(
                        "Not retrying {operation_name} after database error: %s",
                        str(e),
                    )
                    return None
                if not is_retryable or attempt == self.max_retries:
                    logger.error(
                        "Database operation '%s' failed after %d attempts: %s",
                        operation_name,
                        attempt + 1,
                        str(e),
                    )
                    return None
                delay = min(self.base_delay * (2**attempt), self.max_delay)
                jitter = random.uniform(0, delay * 0.1)
                await asyncio.sleep(delay + jitter)
        logger.error(
            "Database operation '%s' failed after all retries. Last error: %s",
            operation_name,
            str(last_exception),
        )
        return None

    def _is_postgresql(self) -> bool:
        """Check if the database backend is PostgreSQL."""
        if not self.db_manager or not self.db_manager.database_url:
            return False
        url = self.db_manager.database_url.lower()
        return url.startswith("postgresql") or url.startswith("postgres")

    def _get_sqlstate(self, exc: Exception) -> Optional[str]:
        """
        Extract SQLSTATE code from a database exception.

        For PostgreSQL via psycopg2/psycopg, the SQLSTATE is available in
        orig.pgcode. Returns None if SQLSTATE cannot be extracted.
        """
        # SQLAlchemy wraps DBAPI errors in DBAPIError
        if isinstance(exc, DBAPIError) and exc.orig is not None:
            orig = exc.orig
            # psycopg2/psycopg3 provide pgcode attribute
            if hasattr(orig, "pgcode") and orig.pgcode:
                return str(orig.pgcode)
            # Some drivers provide sqlstate attribute
            if hasattr(orig, "sqlstate") and orig.sqlstate:
                return str(orig.sqlstate)
        return None

    def _is_retryable_error(self, exc: Exception) -> bool:
        """
        Determine if a database error is transient and worth retrying.

        For PostgreSQL:
            - First checks SQLSTATE codes (40001, 40P01, 55P03, 53300, 57014, class 08*)
            - Falls back to message pattern matching if SQLSTATE unavailable

        For SQLite:
            - Uses message pattern matching for locking and operational errors

        Common patterns (connection issues) are checked for both backends.
        """
        error_msg = str(exc).lower()

        # Check common retryable patterns (both backends)
        if any(keyword in error_msg for keyword in COMMON_RETRYABLE_KEYWORDS):
            return True

        if self._is_postgresql():
            # PostgreSQL: Check SQLSTATE first
            sqlstate = self._get_sqlstate(exc)
            if sqlstate:
                # Check specific SQLSTATE codes
                if sqlstate in POSTGRESQL_RETRYABLE_SQLSTATES:
                    logger.debug(f"Retryable PostgreSQL SQLSTATE: {sqlstate}")
                    return True
                # Check SQLSTATE class 08 (connection exceptions)
                if sqlstate.startswith(POSTGRESQL_RETRYABLE_SQLSTATE_CLASS):
                    logger.debug(
                        f"Retryable PostgreSQL connection SQLSTATE: {sqlstate}"
                    )
                    return True

            # PostgreSQL: Fall back to message patterns if SQLSTATE unavailable
            if any(keyword in error_msg for keyword in POSTGRESQL_RETRYABLE_KEYWORDS):
                return True
        else:
            # SQLite: Use message pattern matching
            if any(keyword in error_msg for keyword in SQLITE_RETRYABLE_KEYWORDS):
                return True

        return False
