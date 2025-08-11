"""
Pydantic models for internal alert processing data structures.

These models define the exact structure of data passed between different
layers of the application, providing type safety and validation.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any, Optional


class AlertProcessingData(BaseModel):
    """
    Internal alert data structure used for processing.
    
    This model defines the exact structure that AlertService expects,
    preventing data structure mismatches and providing type safety.
    """
    model_config = ConfigDict(
        extra="forbid",  # Prevent typos in field names
        frozen=False     # Allow modification during processing
    )
    
    alert_type: str = Field(
        ..., 
        description="Type of alert (kubernetes, aws, etc.)",
        min_length=1
    )
    
    alert_data: Dict[str, Any] = Field(
        ..., 
        description="Actual alert payload with all normalized data",
        min_length=1
    )
    
    def get_severity(self) -> str:
        """Helper to safely get severity from alert data."""
        return self.alert_data.get('severity', 'warning')
    
    def get_environment(self) -> str:
        """Helper to safely get environment from alert data."""
        return self.alert_data.get('environment', 'production')
    
    def get_runbook(self) -> Optional[str]:
        """Helper to safely get runbook from alert data."""
        return self.alert_data.get('runbook')


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
    def from_alert_data(cls, alert: AlertProcessingData) -> 'AlertKey':
        """
        Generate an alert key from alert processing data.
        
        Args:
            alert: Alert processing data
            
        Returns:
            AlertKey instance with deterministic hash
        """
        import json
        import hashlib
        
        # Generate deterministic hash from alert data (excluding timestamp for duplicate detection)
        alert_data_for_hash = alert.alert_data.copy()
        alert_data_for_hash.pop('timestamp', None)  # Remove timestamp to allow duplicate detection
        
        data_json = json.dumps(alert_data_for_hash, sort_keys=True, separators=(',', ':'))
        content_hash = hashlib.sha256(data_json.encode('utf-8')).hexdigest()[:12]
        
        return cls(alert_type=alert.alert_type, content_hash=content_hash)
    
    def __str__(self) -> str:
        """String representation used as the actual key."""
        return f"{self.alert_type}_{self.content_hash}"
    
    def __hash__(self) -> int:
        """Make the key hashable for use in sets/dicts."""
        return hash(str(self))