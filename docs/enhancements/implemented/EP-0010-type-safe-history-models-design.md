# EP-0010: Type-Safe Data Models for History System

## Current State Analysis

### Dict Structures to Replace

**Repository Layer:**
```python
# get_session_timeline() returns:
{
    "session": {
        "session_id": str, "alert_id": str, "alert_data": dict,
        "agent_type": str, "alert_type": str, "status": str,
        "started_at_us": int, "completed_at_us": int, 
        "error_message": str, "final_analysis": str, "session_metadata": dict,
        # Chain fields
        "chain_id": str, "chain_definition": dict,
        "current_stage_index": int, "current_stage_id": str,
        # Pre-calculated counts
        "total_interactions": int, "llm_interaction_count": int, "mcp_communication_count": int
    },
    "chronological_timeline": [
        {
            "id": str,                    # Same as event_id
            "event_id": str,
            "timestamp_us": int,
            "type": "llm" | "mcp",
            "step_description": str,
            "duration_ms": int,
            "stage_execution_id": str,
            "details": {
                # For LLM events:
                "request_json": dict, "response_json": dict, "model_name": str,
                "tokens_used": dict, "temperature": float, "success": bool, "error_message": str
                # For MCP events:
                "tool_name": str, "server_name": str, "communication_type": str,
                "parameters": dict, "result": dict, "available_tools": dict, "success": bool
            }
        }
    ],
    "llm_interactions": [  # Simplified summary list
        {"interaction_id": str, "timestamp_us": int, "step_description": str, 
         "model_name": str, "duration_ms": int}
    ],
    "mcp_communications": [  # Simplified summary list
        {"communication_id": str, "timestamp_us": int, "step_description": str,
         "server_name": str, "tool_name": str, "success": bool, "duration_ms": int}
    ]
}

# get_alert_sessions() returns:
{
    "sessions": [AlertSession],  # List of SQLModel objects
    "interaction_counts": {      # session_id -> counts mapping
        "session_id": {"llm_interactions": int, "mcp_communications": int}
    },
    "pagination": {"page": int, "page_size": int, "total_pages": int, "total_items": int}
}

# get_session_with_stages() returns:
{
    "session": AlertSession.model_dump(),     # Dict from SQLModel
    "stages": [StageExecution.model_dump()]   # List of dicts from SQLModel
}

# get_stage_interaction_counts() returns:
{
    "execution_id": {"llm_interactions": int, "mcp_communications": int}
}
# NOTE: This method will be replaced by the new DetailedSession model structure

# get_filter_options() returns:
{
    "agent_types": List[str], "alert_types": List[str], "status_options": List[str],
    "time_ranges": [{"label": str, "value": str}]
}
```

**Service Layer:**
```python
# get_sessions() returns:
{
    "sessions": List[AlertSession],  # List of SQLModel objects
    "pagination": {"page": int, "page_size": int, "total_pages": int, "total_items": int},
    "interaction_counts": {      # session_id -> counts mapping (optional - not always present)
        "session_id": {"llm_interactions": int, "mcp_communications": int}
    }
}

# calculate_session_summary() returns:
{
    "total_interactions": int, "llm_interactions": int, "mcp_communications": int,
    "system_events": int, "errors_count": int, "total_duration_ms": int,
    "chain_statistics": {
        "total_stages": int, "completed_stages": int, "failed_stages": int,
        "stages_by_agent": dict
    }
}
```

**Controller Layer:**
```python
# get_session_summary() endpoint returns:
Dict[str, Any]  # Direct dictionary response to API (same structure as service calculate_session_summary)
# Contents:
{
    "total_interactions": int, "llm_interactions": int, "mcp_communications": int,
    "system_events": int, "errors_count": int, "total_duration_ms": int,
    "chain_statistics": {
        "total_stages": int, "completed_stages": int, "failed_stages": int,
        "stages_by_agent": dict
    }
}
```

## Target Model Hierarchy

### Core Domain Models

```python
from __future__ import annotations  # Deferred evaluation for forward references

from typing import List, Dict, Optional, Union, Literal, Any
from pydantic import BaseModel, Field, model_validator
from tarsy.models.history import AlertSession
from tarsy.models.unified_interactions import LLMMessage  # Core message model used throughout
# Note: We keep the SQLModel StageExecution for DB operations
# Our DetailedStage below replaces the API model StageExecution from api_models.py
from tarsy.models.constants import AlertSessionStatus, StageStatus, ChainStatus

# Define core shared models to avoid circular imports
class PaginationInfo(BaseModel):
    """Pagination information for paginated responses."""
    page: int
    page_size: int
    total_pages: int
    total_items: int

class TimeRangeOption(BaseModel):
    """Filter time range option"""
    label: str
    value: str

class FilterOptions(BaseModel):
    """Available filter options"""
    agent_types: List[str]
    alert_types: List[str] 
    status_options: List[str]  # String values for API consistency
    time_ranges: List[TimeRangeOption]

class LLMEventDetails(BaseModel):
    """LLM-specific event details with structured objects (absorbs useful parts of unused LLMRequest)"""
    messages: List[LLMMessage] = Field(default_factory=list)  # Structured message objects (from LLMRequest design)
    model_name: str  # Renamed from LLMRequest.model for clarity
    temperature: Optional[float] = None  # From LLMRequest
    success: bool
    error_message: Optional[str] = None
    tool_calls: Optional[dict] = None
    tool_results: Optional[dict] = None

class MCPEventDetails(BaseModel):
    """MCP-specific event details with structured objects"""
    tool_name: str
    server_name: str
    communication_type: str
    parameters: Dict[str, Any] = Field(default_factory=dict)  # tool_arguments (structured parameters, not serialized JSON)
    result: Dict[str, Any] = Field(default_factory=dict)      # tool_result (structured result, not serialized JSON)
    available_tools: Dict[str, Any] = Field(default_factory=dict)  # structured tools data, not serialized JSON
    success: bool

class BaseInteraction(BaseModel):
    """Base interaction model with common fields"""
    id: str                    # Same as event_id (legacy field)
    event_id: str
    timestamp_us: int
    step_description: str
    duration_ms: Optional[int] = None
    stage_execution_id: str

class LLMInteraction(BaseInteraction):
    """LLM interaction with type-specific details"""
    type: Literal["llm"] = "llm"
    details: LLMEventDetails
    
    @model_validator(mode='after')
    def validate_llm_details(self):
        """Validate LLM-specific details"""
        if not self.details.model_name:
            raise ValueError("LLM interactions require model_name in details")
        return self

class MCPInteraction(BaseInteraction):
    """MCP interaction with type-specific details"""
    type: Literal["mcp"] = "mcp"
    details: MCPEventDetails
    
    @model_validator(mode='after') 
    def validate_mcp_details(self):
        """Validate MCP-specific details"""
        if not self.details.server_name:
            raise ValueError("MCP interactions require server_name in details")
        if not self.details.tool_name:
            raise ValueError("MCP interactions require tool_name in details")
        return self

# Union type for timeline events
Interaction = Union[LLMInteraction, MCPInteraction]

class LLMInteractionSummary(BaseModel):
    """Simplified LLM interaction for summary lists"""
    interaction_id: str
    timestamp_us: int
    step_description: str
    model_name: str
    duration_ms: Optional[int] = None

class MCPCommunicationSummary(BaseModel):
    """Simplified MCP communication for summary lists"""
    communication_id: str
    timestamp_us: int
    step_description: str
    server_name: str
    tool_name: str
    success: bool
    duration_ms: Optional[int] = None

# =============================================================================
# PERFECT UNIFIED MODEL STRUCTURE
# Based on actual usage patterns from dashboard and API analysis
# =============================================================================

class SessionOverview(BaseModel):
    """Session overview for lists, filtering, and pagination - dashboard use (will eventually replace api_models.SessionSummary)"""
    # Core identification
    session_id: str
    alert_id: str
    alert_type: Optional[str] = None
    agent_type: str
    status: AlertSessionStatus
    
    # Timing info
    started_at_us: int
    completed_at_us: Optional[int] = None
    
    # Basic status info
    error_message: Optional[str] = None
    
    # Summary counts (for dashboard display)
    llm_interaction_count: int = 0
    mcp_communication_count: int = 0
    total_interactions: int = 0
    
    # Chain progress info (for dashboard filtering/display)
    chain_id: str
    total_stages: Optional[int] = None
    completed_stages: Optional[int] = None
    failed_stages: int = 0
    current_stage_index: Optional[int] = None  # Matches AlertSession field type
    
    # Calculated properties
    @property
    def duration_ms(self) -> Optional[int]:
        """Calculate session duration from start and completion times"""
        if self.started_at_us and self.completed_at_us:
            return (self.completed_at_us - self.started_at_us) // 1000
        return None


class DetailedStage(BaseModel):
    """Complete stage execution with all interactions - for detailed view (replaces api_models.StageExecution)"""
    # Stage identification
    execution_id: str
    session_id: str
    stage_id: str
    stage_index: int
    stage_name: str
    agent: str
    
    # Stage execution info
    status: StageStatus
    started_at_us: Optional[int] = None
    completed_at_us: Optional[int] = None
    duration_ms: Optional[int] = None
    stage_output: Optional[dict] = None  # Structured results produced by this stage (e.g. analysis findings, collected data) - used by subsequent stages in chain. None if stage failed/incomplete.
    error_message: Optional[str] = None
    
    # ALL interactions that happened during this stage (FULL objects with complete details)
    llm_interactions: List[LLMInteraction] = Field(default_factory=list)  # Complete LLM interactions with full details
    mcp_communications: List[MCPInteraction] = Field(default_factory=list)  # Complete MCP interactions with full details
    
    # Summary counts for this stage (replaces InteractionSummary)
    llm_interaction_count: int = 0
    mcp_communication_count: int = 0
    total_interactions: int = 0
    
    # Calculated properties (replaces InteractionSummary functionality)
    @property
    def stage_interactions_duration_ms(self) -> Optional[int]:
        """Calculate total duration from all interactions in this stage"""
        total = 0
        for interaction in self.llm_interactions + self.mcp_communications:
            if interaction.duration_ms:
                total += interaction.duration_ms
        return total if total > 0 else None

class DetailedSession(BaseModel):
    """Complete session with EVERYTHING - for detailed session page (replaces api_models.SessionDetailResponse and ChainExecution)"""
    # Core session data (everything from SessionOverview)
    session_id: str
    alert_id: str
    alert_type: Optional[str] = None
    agent_type: str
    status: AlertSessionStatus
    started_at_us: int
    completed_at_us: Optional[int] = None
    error_message: Optional[str] = None
    
    # Full session details
    alert_data: dict  # Complete alert information
    final_analysis: Optional[str] = None
    session_metadata: Optional[dict] = None
    
    # Chain execution details
    chain_id: str
    chain_definition: dict
    current_stage_index: Optional[int] = None  # Matches AlertSession field type
    current_stage_id: Optional[str] = None  # Matches AlertSession field type
    
    # Complete interaction data
    total_interactions: int = 0
    llm_interaction_count: int = 0
    mcp_communication_count: int = 0
    
    # Complete stage executions with all their interactions
    stages: List[DetailedStage] = Field(default_factory=list)  # Each stage contains its full interaction timeline
    
    # Calculated properties
    @property
    def duration_ms(self) -> Optional[int]:
        """Calculate session duration from start and completion times"""
        if self.started_at_us and self.completed_at_us:
            return (self.completed_at_us - self.started_at_us) // 1000
        return None

class SessionStats(BaseModel):
    """Lightweight statistics and metrics - for headers and quick stats (will eventually replace api_models.SessionSummary statistics functionality)"""
    # Basic counts
    total_interactions: int
    llm_interactions: int
    mcp_communications: int
    system_events: int = 0
    errors_count: int
    total_duration_ms: int
    
    # Chain progress (always present since all sessions are chains)
    chain_statistics: ChainStatistics

class PaginatedSessions(BaseModel):
    """Paginated session results for dashboard list view (replaces api_models.SessionsListResponse)"""
    sessions: List[SessionOverview]  # Session overviews for list display
    pagination: PaginationInfo
    filters_applied: Dict[str, Any] = Field(default_factory=dict)  # Applied filters for this query

class ChainStatistics(BaseModel):
    """Chain execution statistics"""
    total_stages: int
    completed_stages: int
    failed_stages: int
    stages_by_agent: Dict[str, int]
```

## Model Migration Plan

This section provides a comprehensive overview of all existing models in the codebase and defines exactly what will happen to each during the migration to type-safe models.

### Existing Models Inventory

#### **API Response Models** (`backend/tarsy/models/api_models.py`)
- `PaginationInfo` - Pagination information for API responses → **REPLACE** with new version to avoid circular imports
- `SessionSummary` - Session summary for list views → **REPLACE** with `SessionOverview` 
- `SessionsListResponse` - Response for sessions list endpoint → **REPLACE** with `PaginatedSessions`
- `InteractionSummary` - Summary statistics for stage interactions → **REPLACE** with fields/properties in `DetailedStage` (redundant - same data)
- `StageExecution` - API model for stage execution info → **REPLACE** with `DetailedStage`
- `ChainExecution` - Chain execution info within a session → **REPLACE** with chain fields in `DetailedSession`
- `TimelineEvent` - Single event in session timeline → **REPLACE** with `Interaction` union type
- `SessionDetailResponse` - Response for session detail endpoint → **REPLACE** with `DetailedSession`
- `HealthCheckResponse` - Health check endpoint response → **KEEP** (not history-related)
- `ErrorResponse` - Standard error response → **KEEP** (not history-related)

#### **Database Models** (`backend/tarsy/models/history.py`)
- `AlertSession` - SQLModel for alert processing sessions (DB table) → **KEEP** (core database model)
- `StageExecution` - SQLModel for stage executions (DB table) → **KEEP** (core database model)

#### **Unified Interaction Models** (`backend/tarsy/models/unified_interactions.py`)
- `LLMMessage` - SQLModel message for structured operations → **INTEGRATE** (becomes core part of new history models)
- `LLMRequest` - LLM request structure → **REMOVE** (dead code - never used, absorbed into LLMEventDetails)
- `LLMChoice` - LLM response choice → **MOVE** (internal to LLM client, move to client.py)
- `LLMUsage` - LLM token usage → **MOVE** (internal to LLM client, move to client.py)
- `LLMResponse` - LLM response structure → **MOVE** (internal to LLM client, move to client.py)
- `LLMInteraction` - Unified LLM interaction model (DB table) → **MOVE TO REPO** (becomes pure database model, clean up runtime fields)
- `MCPInteraction` - Unified MCP interaction model (DB table) → **MOVE TO REPO** (becomes pure database model, clean up runtime fields)

#### **WebSocket Models** (`backend/tarsy/models/websocket_models.py`)
- `WebSocketMessage` - Base websocket message → **KEEP** (WebSocket communication)
- `SubscriptionMessage` - Subscription/unsubscription message → **KEEP** (WebSocket communication)
- `SubscriptionResponse` - Subscription response → **KEEP** (WebSocket communication)
- `ConnectionEstablished` - Connection confirmation → **KEEP** (WebSocket communication)
- `ErrorMessage` - WebSocket error message → **KEEP** (WebSocket communication)
- `DashboardUpdate` - Dashboard update message → **KEEP** (WebSocket communication)
- `SessionUpdate` - Session update message → **KEEP** (WebSocket communication)
- `ChainProgressUpdate` - Chain progress update → **KEEP** (WebSocket communication)
- `StageProgressUpdate` - Stage progress update → **KEEP** (WebSocket communication)
- `SystemHealthUpdate` - System health update → **KEEP** (WebSocket communication)
- `ChannelType` - Channel type constants → **KEEP** (WebSocket communication)

#### **Constants and Enums** (`backend/tarsy/models/constants.py`)
- `AlertSessionStatus` - Enum for alert session statuses → **KEEP** (core enum, used by new models)
- `StageStatus` - Enum for stage statuses → **KEEP** (core enum, used by new models)
- `ChainStatus` - Enum for chain statuses → **KEEP** (core enum, used by new models)
- `SystemHealthStatus` - Enum for system health → **KEEP** (not history-related)

#### **Configuration Models** (`backend/tarsy/models/agent_config.py`)
- `AgentConfigModel` - Configuration for single agent → **KEEP** (agent configuration)
- `MCPServerConfigModel` - Configuration for MCP server → **KEEP** (MCP configuration)
- `ChainConfigModel` - Configuration for processing chains → **KEEP** (chain configuration)
- `CombinedConfigModel` - Combined agent configuration → **KEEP** (agent configuration)
- **INCOMING**: `MCPServerConfig` (from `mcp_config.py`) → **CONSOLIDATED** (unified MCP configuration)
- **INCOMING**: `MaskingPattern` (from `masking_config.py`) → **CONSOLIDATED** (unified security configuration)  
- **INCOMING**: `MaskingConfig` (from `masking_config.py`) → **CONSOLIDATED** (unified security configuration)
- **INCOMING**: `ChainStageModel` (from `chains.py`) → **CONSOLIDATED** (unified chain configuration)
- **INCOMING**: `ChainDefinitionModel` (from `chains.py`) → **CONSOLIDATED** (unified chain configuration)

**Note**: Chain models are currently exported from `models/__init__.py` - imports will need to be updated from `tarsy.models` to `tarsy.models.agent_config`

#### **Processing Models** (`backend/tarsy/models/alert_processing.py`)
- `AlertProcessingData` - Unified alert processing model → **KEEP** (central processing context that carries alert data through the entire pipeline: API → runbook download → chain execution → agent processing. Evolves by accumulating stage results. Separate from history models - this is processing-time mutable state, not storage-time immutable audit trail)

#### **Alert Models** (`backend/tarsy/models/alert.py`)
- `Alert` - Flexible alert model for API input → **KEEP** (API input model)
- `AlertResponse` - Response model for alert submission → **KEEP** (API response model)

#### **Security Models** (`backend/tarsy/models/masking_config.py`)
- `MaskingPattern` - Single masking pattern config → **MOVE** (relocate to `agent_config.py` for consolidated configuration)
- `MaskingConfig` - Complete masking configuration → **MOVE** (relocate to `agent_config.py` for consolidated configuration)

#### **MCP Configuration Models** (`backend/tarsy/models/mcp_config.py`)
- `MCPServerConfig` - Configuration for MCP server instance → **MOVE** (relocate to `agent_config.py` for consolidated configuration)

#### **Legacy LLM Models** (`backend/tarsy/models/llm.py`)
- `LLMMessage` - Simple message model for agent-LLM communication → **CONSOLIDATE** (replace with SQLModel version that becomes core to history models)

#### **Chain Definition Models** (`backend/tarsy/models/chains.py`)
- `ChainStageModel` - Single stage in processing chain (dataclass) → **MOVE** (relocate to `agent_config.py` for consolidated configuration)
- `ChainDefinitionModel` - Complete chain definition (dataclass) → **MOVE** (relocate to `agent_config.py` for consolidated configuration)

## Migration Implementation Plan

### Overview

This migration follows a **pragmatic, incremental approach** that structures existing dict-based data flows into type-safe models without changing database schemas or fundamental system architecture. The goal is to replace dict structures with validated Pydantic models while maintaining backward compatibility throughout the process.

**Key Principles:**
- No database schema changes required
- Minimal conversion overhead - only create converters where format differences actually exist
- Layer-by-layer migration starting from repository (data) layer up to API layer
- Maintain backward compatibility until final cleanup phase
- Focus on type safety and code maintainability over complex optimizations

### Phase 1: Foundation
**Goal**: Create new type-safe models and minimal conversion infrastructure

**Tasks:**
- **1.1**: Create new models in `backend/tarsy/models/history_models.py`
  - All models from Target Model Hierarchy section
  - Use `core_models.py` approach to avoid circular imports if needed
  - Import existing enums from `constants.py`
  - Import and integrate `LLMMessage` from `unified_interactions.py`

- **1.2**: Create conversion utilities (only where needed)
  - Audit existing dict structures vs new model fields
  - Create converters ONLY where format differences exist (don't assume - verify first!)
  - Focus on bidirectional conversion: `new_model ↔ existing_dict`
  - Place in `backend/tarsy/models/converters/` if needed

- **1.3**: Basic model validation tests
  - Unit tests for all new models
  - Validation tests for required fields and constraints
  - Conversion accuracy tests (if converters created in 1.2)

**Deliverables:**
- ✅ New type-safe models ready for use
- ✅ Minimal conversion infrastructure
- ✅ Model validation test suite

### Phase 2: Repository Layer Migration
**Goal**: Repository methods return new models internally while maintaining dict APIs externally

**Tasks:**
- **2.1**: Refactor repository to use new models internally
  - Update `HistoryRepository` methods to build and return new model instances
  - Keep existing method signatures unchanged initially
  - Repository logic works with typed models instead of assembling dicts

- **2.2**: Add conversion wrappers to maintain current APIs
  - Wrap repository methods to convert new models back to expected dict formats
  - Existing service/controller code continues to receive dicts unchanged
  - Create `_internal` versions of methods that return new models for future use

- **2.3**: Repository integration testing
  - Verify all repository methods return expected dict structures
  - Sanity check: ensure database query patterns remain efficient

**Deliverables:**
- ✅ Repository internally uses type-safe models
- ✅ External repository API unchanged (still returns dicts)
- ✅ Repository integration tests pass

### Phase 3: Service Layer Migration  
**Goal**: Services work with new models internally while maintaining dict APIs

**Tasks:**
- **3.1**: Update services to use new models internally
  - Modify `HistoryService` to work with typed models from repository
  - Service business logic operates on structured models instead of dicts
  - Access to repository `_internal` methods that return models directly

- **3.2**: Maintain dict APIs at service boundaries
  - Service methods still return dicts to controllers
  - Convert models to dicts at service method boundaries
  - Controllers continue to receive expected dict structures

- **3.3**: Service integration testing
  - Verify all service methods return expected dict structures
  - Confirm business logic correctness unchanged
  - Test service-to-service interactions if applicable

**Deliverables:**
- ✅ Services internally use type-safe models
- ✅ External service API unchanged (still returns dicts)
- ✅ Business logic validation tests pass

### Phase 4: Controller/API Migration
**Goal**: Controllers use new models and evaluate API contract changes

**Tasks:**
- **4.1**: Update controllers to use new models
  - Modify `HistoryController` endpoints to work with typed models from services  
  - Access to service `_internal` methods that return models directly
  - Controller logic operates on structured models

- **4.2**: Evaluate API contract migration
  - Check if existing API responses match new model structures
  - **Only create conversions if actual format differences exist** 
  - Verify WebSocket messages don't need conversion (likely they won't!)
  - Consider gradual API migration vs maintaining current response format

- **4.3**: API integration testing
  - End-to-end API tests with new model pipeline
  - Verify API contracts maintained or properly versioned
  - Test WebSocket real-time updates still work correctly

**Deliverables:**
- ✅ Controllers use type-safe models internally
- ✅ API responses validated and consistent
- ✅ End-to-end API tests pass

### Phase 5: Cleanup and Consolidation
**Goal**: Remove temporary code and reorganize models per migration plan

**Tasks:**
- **5.1**: Remove conversion layers bottom-up
  - Remove dict conversion wrappers from controllers first
  - Remove dict conversion wrappers from services  
  - Remove dict conversion wrappers from repositories
  - Delete unused converter utilities

- **5.2**: Delete unused models per migration plan
  - Remove models marked for deletion in "Existing Models Inventory"
  - Update imports throughout codebase
  - Verify no dead code remains

- **5.3**: Move and consolidate models per migration plan  
  - Move models marked for relocation to appropriate files
  - Consolidate configuration models in `agent_config.py`
  - Update all import statements throughout codebase
  - Clean up `models/__init__.py` exports

**Deliverables:**
- ✅ Clean, type-safe codebase with no temporary conversion code
- ✅ Proper model organization per architectural plan
- ✅ All tests passing with new model structure

### Success Criteria

**After Phase 1**: New models validated and ready for integration
**After Phase 2**: Repository layer type-safe but externally compatible  
**After Phase 3**: Service layer type-safe but externally compatible
**After Phase 4**: Full pipeline type-safe with validated API contracts
**After Phase 5**: Clean, maintainable codebase with proper model organization

**Final State**: 
- All history-related data flows use validated Pydantic models
- No dict-based data structures in history system
- Type safety from database to API response  
- Improved code maintainability and developer experience
- No performance degradation or functional changes
