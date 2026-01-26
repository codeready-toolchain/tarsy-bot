"""
Unit tests for StageStatus and ChainStatus helper methods.

Tests the new helper methods added to enum classes for better code readability.
"""

import pytest

from tarsy.models.constants import ChainStatus, StageStatus


@pytest.mark.unit
class TestStageStatusHelperMethods:
    """Test StageStatus helper methods."""

    @pytest.mark.parametrize(
        "status,expected",
        [
            (StageStatus.FAILED, True),
            (StageStatus.CANCELLED, True),
            (StageStatus.TIMED_OUT, True),
            (StageStatus.COMPLETED, False),
            (StageStatus.PENDING, False),
            (StageStatus.ACTIVE, False),
            (StageStatus.PAUSED, False),
            (StageStatus.PARTIAL, False),
        ],
    )
    def test_is_error(self, status: StageStatus, expected: bool) -> None:
        """Test is_error() correctly identifies error statuses."""
        assert status.is_error() == expected

    @pytest.mark.parametrize(
        "status,expected",
        [
            (StageStatus.COMPLETED, True),
            (StageStatus.FAILED, True),
            (StageStatus.CANCELLED, True),
            (StageStatus.TIMED_OUT, True),
            (StageStatus.PENDING, False),
            (StageStatus.ACTIVE, False),
            (StageStatus.PAUSED, False),
            (StageStatus.PARTIAL, False),
        ],
    )
    def test_is_terminal(self, status: StageStatus, expected: bool) -> None:
        """Test is_terminal() correctly identifies terminal statuses."""
        assert status.is_terminal() == expected

    def test_get_error_statuses(self) -> None:
        """Test get_error_statuses() returns all error status values."""
        error_statuses = StageStatus.get_error_statuses()
        
        assert len(error_statuses) == 3
        assert StageStatus.FAILED in error_statuses
        assert StageStatus.CANCELLED in error_statuses
        assert StageStatus.TIMED_OUT in error_statuses
        
        # Ensure non-error statuses are not included
        assert StageStatus.COMPLETED not in error_statuses
        assert StageStatus.PENDING not in error_statuses
        assert StageStatus.PAUSED not in error_statuses

    def test_is_error_matches_get_error_statuses(self) -> None:
        """Test that is_error() is consistent with get_error_statuses()."""
        error_statuses = StageStatus.get_error_statuses()
        
        for status in StageStatus:
            if status in error_statuses:
                assert status.is_error(), f"{status} should be an error status"
            else:
                assert not status.is_error(), f"{status} should not be an error status"


@pytest.mark.unit
class TestChainStatusEnum:
    """Test ChainStatus enum values."""

    def test_chain_status_has_timed_out(self) -> None:
        """Test that ChainStatus includes TIMED_OUT status."""
        assert hasattr(ChainStatus, 'TIMED_OUT')
        assert ChainStatus.TIMED_OUT.value == "timed_out"

    def test_all_chain_statuses_are_unique(self) -> None:
        """Test that all ChainStatus values are unique."""
        status_values = [status.value for status in ChainStatus]
        assert len(status_values) == len(set(status_values))
