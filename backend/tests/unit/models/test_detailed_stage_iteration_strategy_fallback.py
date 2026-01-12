"""
Tests for DetailedStage iteration_strategy backward compatibility fallback.

Verifies that DetailedStage properly falls back to reading iteration_strategy
from stage_output when the DB column is None (for records created before the migration).
"""

import pytest

from tarsy.models.constants import StageStatus
from tarsy.models.history_models import DetailedStage


@pytest.fixture
def base_stage_kwargs() -> dict:
    """Base keyword arguments for creating DetailedStage instances."""
    return {
        "execution_id": "exec-1",
        "session_id": "session-1",
        "stage_id": "stage-1",
        "stage_index": 0,
        "stage_name": "Test Stage",
        "agent": "TestAgent",
        "status": StageStatus.COMPLETED,
        "llm_interactions": [],
        "mcp_communications": [],
        "llm_interaction_count": 0,
        "mcp_communication_count": 0,
        "total_interactions": 0,
    }


class TestDetailedStageIterationStrategyFallback:
    """Test backward compatibility for iteration_strategy field."""

    @pytest.mark.unit
    def test_iteration_strategy_from_db_column(self, base_stage_kwargs: dict) -> None:
        """Test that iteration_strategy is read from DB column when present."""
        stage = DetailedStage(
            **base_stage_kwargs,
            iteration_strategy="react",  # DB column populated
            stage_output={"iteration_strategy": "native-thinking"},  # Different value in stage_output
        )
        
        # Should prefer DB column value
        assert stage.iteration_strategy == "react"

    @pytest.mark.unit
    def test_iteration_strategy_fallback_to_stage_output(self, base_stage_kwargs: dict) -> None:
        """Test that iteration_strategy falls back to stage_output when DB column is None."""
        stage = DetailedStage(
            **base_stage_kwargs,
            iteration_strategy=None,  # DB column not populated (old record)
            stage_output={"iteration_strategy": "native-thinking"},  # Fallback value
        )
        
        # Should use stage_output value
        assert stage.iteration_strategy == "native-thinking"

    @pytest.mark.unit
    def test_iteration_strategy_none_when_both_missing(self, base_stage_kwargs: dict) -> None:
        """Test that iteration_strategy is None when both DB column and stage_output are missing."""
        stage = DetailedStage(
            **base_stage_kwargs,
            iteration_strategy=None,  # DB column not populated
            stage_output=None,  # No stage_output
        )
        
        # Should be None
        assert stage.iteration_strategy is None

    @pytest.mark.unit
    def test_iteration_strategy_none_when_not_in_stage_output(self, base_stage_kwargs: dict) -> None:
        """Test that iteration_strategy is None when stage_output exists but doesn't contain it."""
        stage = DetailedStage(
            **base_stage_kwargs,
            iteration_strategy=None,  # DB column not populated
            stage_output={"other_field": "value"},  # stage_output exists but no iteration_strategy
        )
        
        # Should be None
        assert stage.iteration_strategy is None

    @pytest.mark.unit
    def test_iteration_strategy_with_various_values(self, base_stage_kwargs: dict) -> None:
        """Test iteration_strategy fallback with various strategy values."""
        strategies = [
            "react",
            "native-thinking",
            "react-stage",
            "synthesis-native-thinking"
        ]
        
        for strategy in strategies:
            # Test DB column
            stage_db = DetailedStage(
                **base_stage_kwargs,
                iteration_strategy=strategy,
            )
            assert stage_db.iteration_strategy == strategy
            
            # Test fallback
            stage_fallback = DetailedStage(
                **base_stage_kwargs,
                iteration_strategy=None,
                stage_output={"iteration_strategy": strategy},
            )
            assert stage_fallback.iteration_strategy == strategy

    @pytest.mark.unit
    def test_iteration_strategy_fallback_with_complex_stage_output(self, base_stage_kwargs: dict) -> None:
        """Test that fallback works correctly with complex stage_output structures."""
        stage = DetailedStage(
            **base_stage_kwargs,
            iteration_strategy=None,
            stage_output={
                "status": "completed",
                "agent_name": "TestAgent",
                "result_summary": "Analysis complete",
                "iteration_strategy": "react-stage",  # Nested in complex structure
                "llm_provider": "openai",
                "timestamp_us": 1234567890
            },
        )
        
        assert stage.iteration_strategy == "react-stage"
