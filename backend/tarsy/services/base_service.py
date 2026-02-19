"""
asdf
"""

from abc import ABC
import asyncio
import logging
from contextlib import asynccontextmanager, contextmanager, suppress
from typing import (
    AsyncGenerator,
    AsyncIterator,
    Callable,
    Generator,
    List,
    Optional,
    TypeVar,
)
from warnings import deprecated

from sqlmodel import Session

from tarsy.config.settings import Settings, get_settings
from tarsy.repositories.base_repository import DatabaseManager
from tarsy.repositories.retries import DatabaseRetries

logger = logging.getLogger(__name__)
R = TypeVar("R")  # repository type
T = TypeVar("T")  # type returned from a retried function


class BaseService[R](ABC):
    def __init__(self, repository_factory: Callable[[Session], R], non_retriable_ops: Optional[List[str]] = None):
        self.settings: Settings = get_settings()
        self.db_manager: Optional[DatabaseManager] = None
        self._initialization_attempted: bool = False
        self._is_healthy: bool = False
        self.max_retries: int = 3
        self.base_delay: float = 0.1
        self.max_delay: float = 2.0
        self.retries: Optional[DatabaseRetries] = None
        self._repository_factory = repository_factory
        self._non_retriable_ops=non_retriable_ops

    @deprecated("use _ready_for_testing instead")
    def _set_healthy_for_testing(self, is_healthy: bool = True) -> None:
        self._ready_for_testing(is_healthy)

    def _ready_for_testing(self, is_healthy: bool = True):
        """
        Set infrastructure health state for testing purposes.

        This method provides a clean interface for tests to configure the
        infrastructure state without directly accessing private attributes.
        Only use this in test code.

        Args:
            is_healthy: Whether to mark the infrastructure as healthy.
        """
        self._initialization_attempted = True
        self._is_healthy = is_healthy
        if self.retries is None:
            self.retries = DatabaseRetries(
                db_manager=self.db_manager,
                max_retries=self.max_retries,
                base_delay=self.base_delay,
                max_delay=self.max_delay,
                non_retriable_ops=self._non_retriable_ops
            )

    def _initialize(self):
        """Initialize database connection and schema."""
        if self._initialization_attempted:
            return self._is_healthy

        self._initialization_attempted = True

        try:
            self.db_manager = DatabaseManager(self.settings.database_url)
            self.db_manager.initialize()
            self.db_manager.create_tables()
            self.retries = DatabaseRetries(
                db_manager=self.db_manager,
                max_retries=self.max_retries,
                base_delay=self.base_delay,
                max_delay=self.max_delay,
                non_retriable_ops=self._non_retriable_ops,
            )
            self._is_healthy = True

        except Exception as e:
            self._is_healthy = False
            raise e

    @contextmanager
    def get_repository(self) -> Generator[Optional[R], None, None]:
        """Context manager for getting repository with error handling."""
        if not self._is_healthy:
            yield None
            return

        session = None
        repository = None
        try:
            if not self.db_manager:
                yield None
                return

            session = self.db_manager.get_session()
            repository = self._repository_factory(session)
            yield repository

        except Exception as e:
            logger.error(f"Repository error: {str(e)}")
            if session:
                with suppress(Exception):
                    session.rollback()

        finally:
            if session:
                try:
                    session.close()
                except Exception as e:
                    logger.error(f"Error closing database session: {str(e)}")

    def _retry_database_operation(
        self,
        operation_name: str,
        operation_func: Callable[[], T],
        *,
        treat_none_as_success: bool = False,
    ) -> Optional[T]:
        """Retry database operations with exponential backoff.

        Raises:
            RuntimeError: If service is not properly initialized (retries is None).
        """
        if self.retries is None:
            raise RuntimeError(
                f"Service not properly initialized: cannot perform '{operation_name}'. "
                f"Call initialize() or _ready_for_testing() first."
            )

        return self.retries.database_operation(
            operation_name,
            operation_func,
            treat_none_as_success=treat_none_as_success,
        )

    async def _retry_database_operation_async(
        self,
        operation_name: str,
        operation_func: Callable[[], T],
        *,
        treat_none_as_success: bool = False,
    ) -> Optional[T]:
        """Async retry database operations with exponential backoff.

        Raises:
            RuntimeError: If service is not properly initialized (retries is None).
        """
        if self.retries is None:
            raise RuntimeError(
                f"Service not properly initialized: cannot perform '{operation_name}'. "
                f"Call initialize() or _ready_for_testing() first."
            )

        async def f():
            return await asyncio.to_thread(operation_func)

        return await self.retries.async_database_operation(
            operation_name, f, treat_none_as_success=treat_none_as_success
        )
