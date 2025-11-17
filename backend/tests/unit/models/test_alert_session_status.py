"""
Unit tests for AlertSessionStatus enum.

Tests the status classification methods to ensure CANCELING and CANCELLED
are properly categorized as active and terminal statuses respectively.
"""

import pytest

from tarsy.models.constants import AlertSessionStatus


class TestAlertSessionStatus:
    """Test suite for AlertSessionStatus enum classification methods."""
    
    @pytest.mark.unit
    @pytest.mark.parametrize(
        "status,is_active,is_terminal",
        [
            (AlertSessionStatus.PENDING, True, False),
            (AlertSessionStatus.IN_PROGRESS, True, False),
            (AlertSessionStatus.PAUSED, True, False),
            (AlertSessionStatus.CANCELING, True, False),
            (AlertSessionStatus.COMPLETED, False, True),
            (AlertSessionStatus.FAILED, False, True),
            (AlertSessionStatus.CANCELLED, False, True),
        ],
    )
    def test_status_classification(
        self, status: AlertSessionStatus, is_active: bool, is_terminal: bool
    ) -> None:
        """Test that each status is correctly classified as active or terminal."""
        active_statuses = AlertSessionStatus.get_active_statuses()
        terminal_statuses = AlertSessionStatus.get_terminal_statuses()
        
        if is_active:
            assert status in active_statuses, f"{status} should be in active statuses"
            assert status not in terminal_statuses, f"{status} should not be in terminal statuses"
        
        if is_terminal:
            assert status in terminal_statuses, f"{status} should be in terminal statuses"
            assert status not in active_statuses, f"{status} should not be in active statuses"
    
    @pytest.mark.unit
    def test_canceling_is_active_not_terminal(self) -> None:
        """Test that CANCELING status is active but not terminal."""
        assert AlertSessionStatus.CANCELING in AlertSessionStatus.get_active_statuses()
        assert AlertSessionStatus.CANCELING not in AlertSessionStatus.get_terminal_statuses()
    
    @pytest.mark.unit
    def test_cancelled_is_terminal_not_active(self) -> None:
        """Test that CANCELLED status is terminal but not active."""
        assert AlertSessionStatus.CANCELLED in AlertSessionStatus.get_terminal_statuses()
        assert AlertSessionStatus.CANCELLED not in AlertSessionStatus.get_active_statuses()
    
    @pytest.mark.unit
    def test_paused_is_active_not_terminal(self) -> None:
        """Test that PAUSED status is active but not terminal."""
        assert AlertSessionStatus.PAUSED in AlertSessionStatus.get_active_statuses()
        assert AlertSessionStatus.PAUSED not in AlertSessionStatus.get_terminal_statuses()
    
    @pytest.mark.unit
    def test_active_and_terminal_are_mutually_exclusive(self) -> None:
        """Test that no status can be both active and terminal."""
        active_statuses = set(AlertSessionStatus.get_active_statuses())
        terminal_statuses = set(AlertSessionStatus.get_terminal_statuses())
        
        overlap = active_statuses & terminal_statuses
        assert len(overlap) == 0, f"Statuses cannot be both active and terminal: {overlap}"
    
    @pytest.mark.unit
    def test_all_statuses_are_classified(self) -> None:
        """Test that every status is classified as either active or terminal."""
        all_statuses = set(AlertSessionStatus.get_all_statuses())
        active_statuses = set(AlertSessionStatus.get_active_statuses())
        terminal_statuses = set(AlertSessionStatus.get_terminal_statuses())
        
        classified = active_statuses | terminal_statuses
        assert all_statuses == classified, "All statuses must be either active or terminal"
    
    @pytest.mark.unit
    def test_active_values_returns_strings(self) -> None:
        """Test that active_values returns string values."""
        active_values = AlertSessionStatus.active_values()
        
        assert isinstance(active_values, list)
        assert all(isinstance(v, str) for v in active_values)
        assert "paused" in active_values
        assert "canceling" in active_values
        assert "cancelled" not in active_values
    
    @pytest.mark.unit
    def test_terminal_values_returns_strings(self) -> None:
        """Test that terminal_values returns string values."""
        terminal_values = AlertSessionStatus.terminal_values()
        
        assert isinstance(terminal_values, list)
        assert all(isinstance(v, str) for v in terminal_values)
        assert "cancelled" in terminal_values
        assert "canceling" not in terminal_values

