"""Unit tests for SystemWarningsService."""

import pytest

from tarsy.models.system_models import SystemWarning
from tarsy.services.system_warnings_service import (
    SystemWarningsService,
    get_warnings_service,
)


@pytest.mark.unit
class TestSystemWarningsService:
    """Test cases for SystemWarningsService."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self) -> None:
        """Reset singleton instance before each test."""
        SystemWarningsService._instance = None

    def test_singleton_pattern(self) -> None:
        """Test that service follows singleton pattern."""
        service1 = SystemWarningsService.get_instance()
        service2 = SystemWarningsService.get_instance()

        assert service1 is service2

    def test_get_warnings_service_helper(self) -> None:
        """Test get_warnings_service helper function."""
        service1 = get_warnings_service()
        service2 = get_warnings_service()

        assert service1 is service2
        assert isinstance(service1, SystemWarningsService)

    def test_add_warning_basic(self) -> None:
        """Test adding a basic warning."""
        service = SystemWarningsService()

        warning_id = service.add_warning(
            category="mcp_initialization",
            message="MCP Server 'kubernetes-server' failed to initialize",
        )

        assert warning_id.startswith("mcp_initialization_")
        warnings = service.get_warnings()
        assert len(warnings) == 1
        assert warnings[0].category == "mcp_initialization"
        assert (
            warnings[0].message
            == "MCP Server 'kubernetes-server' failed to initialize"
        )
        assert warnings[0].details is None

    def test_add_warning_with_details(self) -> None:
        """Test adding a warning with details."""
        service = SystemWarningsService()

        warning_id = service.add_warning(
            category="runbook_service",
            message="Runbook service disabled",
            details="Set GITHUB_TOKEN environment variable to enable",
        )

        warnings = service.get_warnings()
        assert len(warnings) == 1
        assert warnings[0].category == "runbook_service"
        assert warnings[0].message == "Runbook service disabled"
        assert (
            warnings[0].details == "Set GITHUB_TOKEN environment variable to enable"
        )
        assert warnings[0].warning_id == warning_id

    def test_add_multiple_warnings(self) -> None:
        """Test adding multiple warnings."""
        service = SystemWarningsService()

        id1 = service.add_warning("mcp_initialization", "MCP error 1")
        id2 = service.add_warning("runbook_service", "Runbook error")
        id3 = service.add_warning("mcp_initialization", "MCP error 2")

        warnings = service.get_warnings()
        assert len(warnings) == 3

        # Check that all warnings are present
        warning_ids = [w.warning_id for w in warnings]
        assert id1 in warning_ids
        assert id2 in warning_ids
        assert id3 in warning_ids

        # Check categories
        categories = [w.category for w in warnings]
        assert categories.count("mcp_initialization") == 2
        assert categories.count("runbook_service") == 1

    def test_get_warnings_empty(self) -> None:
        """Test getting warnings when none exist."""
        service = SystemWarningsService()
        warnings = service.get_warnings()

        assert warnings == []

    def test_warning_contains_timestamp(self) -> None:
        """Test that warnings include timestamps."""
        service = SystemWarningsService()

        service.add_warning("test_category", "test message")

        warnings = service.get_warnings()
        assert len(warnings) == 1
        assert warnings[0].timestamp > 0
        assert isinstance(warnings[0].timestamp, int)

    def test_warning_id_is_unique(self) -> None:
        """Test that each warning gets a unique ID."""
        service = SystemWarningsService()

        # Add same warning twice (should get different IDs due to timestamp)
        id1 = service.add_warning("test_category", "test message")
        id2 = service.add_warning("test_category", "test message")

        assert id1 != id2

        warnings = service.get_warnings()
        assert len(warnings) == 2

    def test_warnings_are_pydantic_models(self) -> None:
        """Test that returned warnings are SystemWarning instances."""
        service = SystemWarningsService()

        service.add_warning("test_category", "test message", "test details")

        warnings = service.get_warnings()
        assert len(warnings) == 1
        assert isinstance(warnings[0], SystemWarning)
        assert hasattr(warnings[0], "model_dump")

    def test_clear_warning(self) -> None:
        """Test clearing a specific warning."""
        service = SystemWarningsService()

        warning_id = service.add_warning("test_category", "test message")

        assert len(service.get_warnings()) == 1

        result = service.clear_warning(warning_id)
        assert result is True
        assert len(service.get_warnings()) == 0

    def test_clear_nonexistent_warning(self) -> None:
        """Test clearing a warning that doesn't exist."""
        service = SystemWarningsService()

        result = service.clear_warning("nonexistent_id")
        assert result is False

    def test_clear_warning_selective(self) -> None:
        """Test that clearing one warning doesn't affect others."""
        service = SystemWarningsService()

        id1 = service.add_warning("category1", "message1")
        id2 = service.add_warning("category2", "message2")
        id3 = service.add_warning("category3", "message3")

        assert len(service.get_warnings()) == 3

        result = service.clear_warning(id2)
        assert result is True

        remaining_warnings = service.get_warnings()
        assert len(remaining_warnings) == 2

        remaining_ids = [w.warning_id for w in remaining_warnings]
        assert id1 in remaining_ids
        assert id2 not in remaining_ids
        assert id3 in remaining_ids
