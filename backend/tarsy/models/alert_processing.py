"""
Pydantic models for internal alert processing data structures.

These models define the exact structure of data passed between different
layers of the application, providing type safety and validation.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, Any, Optional
from .agent_execution_result import ChainExecutionContext, AgentExecutionResult


class AlertProcessingData(BaseModel):
    """
    Unified alert processing model supporting both single-agent and chain processing.
    
    This model evolves throughout the processing pipeline:
    1. Initial creation: alert_type + alert_data + runbook URL
    2. After runbook download: runbook_content populated
    3. During chain execution: stage_outputs accumulated
    """
    model_config = ConfigDict(
        extra="forbid",
        frozen=False  # Allow modification during processing pipeline
    )
    
    # Core alert data (immutable after creation)
    alert_type: str = Field(..., description="Type of alert (kubernetes, aws, etc.)", min_length=1)
    alert_data: Dict[str, Any] = Field(..., description="Original alert payload", min_length=1)
    
    # Runbook processing (populated during pipeline)
    runbook_url: Optional[str] = Field(None, description="URL to runbook for this alert")
    runbook_content: Optional[str] = Field(None, description="Downloaded runbook content")
    
    # Chain execution tracking (populated during chain processing)
    stage_outputs: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, 
        description="Results from completed chain stages"
    )
    
    # Processing metadata
    chain_id: Optional[str] = Field(None, description="ID of chain processing this alert")
    current_stage_name: Optional[str] = Field(None, description="Currently executing stage")
    
    # Helper methods for type-safe data access
    def get_severity(self) -> str:
        """Helper to safely get severity from alert data."""
        return self.alert_data.get('severity', 'warning')
    
    def get_environment(self) -> str:
        """Helper to safely get environment from alert data."""
        return self.alert_data.get('environment', 'production')
    
    def get_runbook_url(self) -> Optional[str]:
        """Get runbook URL from either dedicated field or alert_data."""
        return self.runbook_url or self.alert_data.get('runbook')
    
    def get_runbook_content(self) -> str:
        """Get downloaded runbook content."""
        return self.runbook_content or ""
    
    def get_original_alert_data(self) -> Dict[str, Any]:
        """Get clean original alert data without processing artifacts."""
        return self.alert_data.copy()
    
    def get_stage_result(self, stage_name: str) -> Optional[Dict[str, Any]]:
        """Get results from a specific chain stage."""
        return self.stage_outputs.get(stage_name)
    
    def get_all_mcp_results(self) -> Dict[str, Any]:
        """Merge MCP results from all completed stages."""
        merged_mcp_data = {}
        for stage_name, stage_result in self.stage_outputs.items():
            if isinstance(stage_result, dict) and "mcp_results" in stage_result:
                for server_name, server_data in stage_result["mcp_results"].items():
                    if server_name not in merged_mcp_data:
                        merged_mcp_data[server_name] = []
                    if isinstance(server_data, list):
                        merged_mcp_data[server_name].extend(server_data)
                    else:
                        merged_mcp_data[server_name].append(server_data)
        return merged_mcp_data
    
    def get_stage_attributed_mcp_results(self) -> Dict[str, Any]:
        """Get MCP results with stage attribution preserved."""
        stage_attributed_data = {}
        for stage_name, stage_result in self.stage_outputs.items():
            if isinstance(stage_result, dict) and "mcp_results" in stage_result:
                # Only include stages that actually have MCP results
                if stage_result["mcp_results"]:
                    stage_attributed_data[stage_name] = stage_result["mcp_results"]
        return stage_attributed_data
    
    def add_stage_result(self, stage_name: str, result):
        """Add results from a completed stage."""
        self.stage_outputs[stage_name] = result
    
    def set_runbook_content(self, content: str):
        """Set the downloaded runbook content."""
        self.runbook_content = content
    
    def set_chain_context(self, chain_id: str, current_stage: Optional[str] = None):
        """Set chain processing context."""
        self.chain_id = chain_id
        self.current_stage_name = current_stage

    def get_chain_execution_context(self) -> ChainExecutionContext:
        """
        Create ChainExecutionContext from completed stage outputs.
        
        This converts the AgentExecutionResult objects in stage_outputs 
        into a format suitable for prompt building.
        """
        chain_context = ChainExecutionContext()
        
        for stage_name, stage_result in self.stage_outputs.items():
            if isinstance(stage_result, AgentExecutionResult):
                # Add completed AgentExecutionResult to chain context
                if stage_result.status.value == "completed":
                    chain_context.stage_results[stage_name] = stage_result
        
        return chain_context


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