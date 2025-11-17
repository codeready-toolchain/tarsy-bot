"""
Unit tests for PauseMetadata model.

Tests the pause metadata model serialization and validation.
"""

import pytest
from pydantic import ValidationError

from tarsy.models.pause_metadata import PauseMetadata, PauseReason


@pytest.mark.unit
class TestPauseReasonEnum:
    """Test suite for PauseReason enum."""
    
    def test_pause_reason_values(self) -> None:
        """Test that PauseReason enum has expected values."""
        assert PauseReason.MAX_ITERATIONS_REACHED.value == "max_iterations_reached"
    
    def test_pause_reason_values_method(self) -> None:
        """Test that values() method returns all enum values as strings."""
        values = PauseReason.values()
        assert isinstance(values, list)
        assert "max_iterations_reached" in values


@pytest.mark.unit
class TestPauseMetadata:
    """Test suite for PauseMetadata model."""
    
    def test_create_pause_metadata_with_all_fields(self) -> None:
        """Test creating PauseMetadata with all required fields."""
        metadata = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=30,
            message="Paused after 30 iterations",
            paused_at_us=1234567890
        )
        
        assert metadata.reason == PauseReason.MAX_ITERATIONS_REACHED
        assert metadata.current_iteration == 30
        assert metadata.message == "Paused after 30 iterations"
        assert metadata.paused_at_us == 1234567890
    
    def test_create_pause_metadata_without_optional_fields(self) -> None:
        """Test creating PauseMetadata without optional current_iteration."""
        metadata = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            message="Paused for unknown reason",
            paused_at_us=1234567890
        )
        
        assert metadata.reason == PauseReason.MAX_ITERATIONS_REACHED
        assert metadata.current_iteration is None
        assert metadata.message == "Paused for unknown reason"
    
    def test_pause_metadata_serialization_to_dict(self) -> None:
        """Test that PauseMetadata serializes correctly to dict."""
        metadata = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=30,
            message="Paused after 30 iterations",
            paused_at_us=1234567890
        )
        
        # Use model_dump with mode='json' to get JSON-compatible dict
        data = metadata.model_dump(mode='json')
        
        assert data["reason"] == "max_iterations_reached"  # Enum serialized as string
        assert data["current_iteration"] == 30
        assert data["message"] == "Paused after 30 iterations"
        assert data["paused_at_us"] == 1234567890
    
    def test_pause_metadata_deserialization_from_dict(self) -> None:
        """Test that PauseMetadata deserializes correctly from dict."""
        data = {
            "reason": "max_iterations_reached",
            "current_iteration": 30,
            "message": "Paused after 30 iterations",
            "paused_at_us": 1234567890
        }
        
        metadata = PauseMetadata.model_validate(data)
        
        assert metadata.reason == PauseReason.MAX_ITERATIONS_REACHED
        assert metadata.current_iteration == 30
        assert metadata.message == "Paused after 30 iterations"
        assert metadata.paused_at_us == 1234567890
    
    def test_pause_metadata_roundtrip(self) -> None:
        """Test that PauseMetadata can roundtrip through serialization."""
        original = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=30,
            message="Paused after 30 iterations",
            paused_at_us=1234567890
        )
        
        # Serialize to dict (JSON mode)
        data = original.model_dump(mode='json')
        
        # Deserialize back
        restored = PauseMetadata.model_validate(data)
        
        assert restored.reason == original.reason
        assert restored.current_iteration == original.current_iteration
        assert restored.message == original.message
        assert restored.paused_at_us == original.paused_at_us
    
    def test_pause_metadata_missing_required_field_raises_error(self) -> None:
        """Test that missing required fields raise validation error."""
        with pytest.raises(ValidationError):
            PauseMetadata(
                reason=PauseReason.MAX_ITERATIONS_REACHED,
                # missing message and paused_at_us
            )
    
    def test_pause_metadata_invalid_reason_raises_error(self) -> None:
        """Test that invalid pause reason raises validation error."""
        with pytest.raises(ValidationError):
            PauseMetadata.model_validate({
                "reason": "invalid_reason",
                "message": "Test",
                "paused_at_us": 1234567890
            })
    
    def test_pause_metadata_json_serialization(self) -> None:
        """Test that PauseMetadata can be JSON serialized."""
        import json
        
        metadata = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=30,
            message="Paused after 30 iterations",
            paused_at_us=1234567890
        )
        
        # Convert to JSON string
        json_str = metadata.model_dump_json()
        
        # Parse back
        data = json.loads(json_str)
        
        assert data["reason"] == "max_iterations_reached"
        assert data["current_iteration"] == 30
    
    def test_pause_metadata_with_none_iteration(self) -> None:
        """Test that current_iteration can be None."""
        metadata = PauseMetadata(
            reason=PauseReason.MAX_ITERATIONS_REACHED,
            current_iteration=None,
            message="Paused",
            paused_at_us=1234567890
        )
        
        assert metadata.current_iteration is None
        
        # Verify serialization handles None correctly
        data = metadata.model_dump(mode='json')
        assert data["current_iteration"] is None

