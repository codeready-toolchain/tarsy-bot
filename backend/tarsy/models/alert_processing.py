"""
Pydantic models for internal alert processing data structures.

These models define the exact structure of data passed between different
layers of the application, providing type safety and validation.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .processing_context import ChainContext


class AlertKey(BaseModel):
    """
    Represents a unique alert key for concurrency control.
    
    This model encapsulates the logic for generating deterministic
    keys for alert deduplication and concurrency management.
    """
    model_config = ConfigDict(
        extra="forbid",
        frozen=True  # Immutable once created
    )
    
    alert_type: str = Field(..., description="Type of alert")
    content_hash: str = Field(..., description="Hash of alert content", min_length=1)
    
    @classmethod
    def from_chain_context(cls, context: 'ChainContext') -> 'AlertKey':
        """
        Generate an alert key from chain context.
        
        Args:
            context: Chain processing context
            
        Returns:
            AlertKey instance with deterministic hash
        """
        import json
        import hashlib
        
        # Generate deterministic hash from alert data (excluding timestamp for duplicate detection)
        alert_data_for_hash = context.alert_data.copy()
        alert_data_for_hash.pop('timestamp', None)  # Remove timestamp to allow duplicate detection
        
        data_json = json.dumps(alert_data_for_hash, sort_keys=True, separators=(',', ':'))
        content_hash = hashlib.sha256(data_json.encode('utf-8')).hexdigest()[:12]
        
        return cls(alert_type=context.alert_type, content_hash=content_hash)
    
    def __str__(self) -> str:
        """String representation used as the actual key."""
        return f"{self.alert_type}_{self.content_hash}"
    
    def __hash__(self) -> int:
        """Make the key hashable for use in sets/dicts."""
        return hash(str(self))