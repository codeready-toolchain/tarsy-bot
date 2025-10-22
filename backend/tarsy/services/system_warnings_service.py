"""
System-wide warning management service.

Provides a singleton service for tracking and retrieving non-fatal
system warnings that should be visible in the dashboard.
"""

import uuid
from typing import Dict, List, Optional

from tarsy.models.system_models import SystemWarning
from tarsy.utils.timestamp import now_us


class SystemWarningsService:
    """
    Singleton service for managing system warnings.

    Warnings are stored in-memory and not persisted. They represent
    critical (but non-fatal) errors that occurred during startup or runtime.
    """

    _instance: Optional["SystemWarningsService"] = None

    def __init__(self) -> None:
        """Initialize warnings storage."""
        self._warnings: Dict[str, SystemWarning] = {}

    @classmethod
    def get_instance(cls) -> "SystemWarningsService":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def add_warning(
        self,
        category: str,
        message: str,
        details: Optional[str] = None,
        server_id: Optional[str] = None,
    ) -> str:
        """
        Add a system warning.

        Args:
            category: Warning category (use WarningCategory constants)
            message: User-facing warning message
            details: Optional detailed error information
            server_id: Optional server ID for MCP-related warnings

        Returns:
            warning_id: Unique identifier for the warning
        """
        timestamp = now_us()
        warning_id = str(uuid.uuid4())

        # Create Pydantic model instance
        self._warnings[warning_id] = SystemWarning(
            warning_id=warning_id,
            category=category,
            message=message,
            details=details,
            timestamp=timestamp,
            server_id=server_id,
        )

        from tarsy.utils.logger import get_module_logger

        logger = get_module_logger(__name__)
        logger.warning(f"System warning added: [{category}] {message}")

        return warning_id

    def get_warnings(self) -> List[SystemWarning]:
        """Get all active warnings."""
        return list(self._warnings.values())

    def clear_warning(self, warning_id: str) -> bool:
        """
        Clear a specific warning.

        Used primarily in tests to reset state between test cases.

        Args:
            warning_id: ID of warning to clear

        Returns:
            True if warning was found and cleared
        """
        return self._warnings.pop(warning_id, None) is not None

    def clear_warning_by_server_id(
        self, category: str, server_id: str
    ) -> bool:
        """
        Clear warning matching category and server_id.
        Used to clear MCP warnings when servers recover.

        Args:
            category: Warning category (e.g., "mcp_initialization")
            server_id: Server ID (e.g., "kubernetes-server")

        Returns:
            True if warning was found and cleared
        """
        from tarsy.utils.logger import get_module_logger

        logger = get_module_logger(__name__)

        logger.info(
            f"clear_warning_by_server_id: category={category}, server_id={server_id}, "
            f"current_warnings={len(self._warnings)}"
        )

        for warning_id, warning in list(self._warnings.items()):
            logger.info(
                f"  Checking warning {warning_id}: category={warning.category}, "
                f"server_id={warning.server_id}, matches={warning.category == category and warning.server_id == server_id}"
            )
            if warning.category == category and warning.server_id == server_id:
                del self._warnings[warning_id]
                logger.info(f"✓ Cleared warning {warning_id} for server: {server_id}")
                return True

        logger.info(f"✗ No warning found for server: {server_id}")
        return False


def get_warnings_service() -> SystemWarningsService:
    """Get the singleton warnings service instance."""
    return SystemWarningsService.get_instance()
