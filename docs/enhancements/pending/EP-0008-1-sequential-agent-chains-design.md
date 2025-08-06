# EP-0008-1: Sequential Agent Chains - Design Document

**Status:** Draft  
**Created:** 2025-08-05  
**Requirements:** `docs/enhancements/pending/EP-0008-1-sequential-agent-chains-requirements.md`

---

## Design Principles

**Core Guidelines:**
- **Unified Architecture**: Replace single-agent processing with unified chain execution - all agents execute through chains (single agents become 1-stage chains)
- **Clean Interface Design**: Break and improve BaseAgent interface for accumulated data flow, enabling sophisticated multi-stage workflows
- **Maintainability**: Clear separation between chain orchestration (ChainOrchestrator) and individual agent execution logic (BaseAgent)
- **Strategic Breaking Changes**: Accept necessary breaking changes for cleaner long-term architecture - prioritize dashboard/backend over dev UI compatibility

---

## Implementation Strategy

**Approach**: Unified execution architecture where ChainRegistry replaces AgentRegistry, and BaseAgent interface is enhanced for accumulated data flow across stages. Single agents become 1-stage chains.

### Component Changes

**Components to Replace:**
- `backend/tarsy/services/agent_registry.py`: Replaced entirely by ChainRegistry
- `BUILTIN_AGENT_MAPPINGS` in `builtin_config.py`: Deleted, replaced by BUILTIN_CHAIN_DEFINITIONS
- BaseAgent interface: Breaking change to process_alert() method signature

**Components to Extend:** 
- `backend/tarsy/config/builtin_config.py`: Add built-in chain definitions (including single agents as 1-stage chains)
- `backend/tarsy/config/agent_config.py`: Extend ConfigurationLoader to parse agent_chains section from YAML
- `backend/tarsy/services/alert_service.py`: Simplify to use unified chain execution path for all processing

**New Components:**
- `backend/tarsy/services/chain_registry.py`: Registry for both built-in and configurable chain definitions
- `backend/tarsy/services/chain_orchestrator.py`: Sequential execution engine for agent chains
- `backend/tarsy/models/chain_models.py`: Pydantic models for chain definitions and execution state

### Breaking Changes Strategy
- **External API**: Breaking changes to WebSocket message format (remove progress field, add chain fields) - dashboard updated accordingly, dev UI simplified
- **Database**: Fresh database approach - delete existing DB data for cleaner schema with stage-level tracking
- **Configuration**: Clean slate - remove BUILTIN_AGENT_MAPPINGS, add BUILTIN_CHAIN_DEFINITIONS and agent_chains section

---

## Technical Design

### Data Structures

**Core Data Models (Phase 1 Focus):**
```python
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class AccumulatedAlertData(BaseModel):
    """Accumulated alert data structure passed to agents throughout chain execution."""
    original_alert: Dict[str, Any] = Field(description="Original alert data including runbook content")
    stage_outputs: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Results from previous stages (empty for single-stage chains)")
    
    def get_runbook(self) -> str:
        """Extract runbook content from original alert."""
        return self.original_alert.get("runbook", "")
    
    def get_original_data(self) -> Dict[str, Any]:
        """Get original alert data without runbook."""
        data = self.original_alert.copy()
        data.pop("runbook", None)
        return data
    
    def get_stage_result(self, stage_id: str) -> Optional[Dict[str, Any]]:
        """Get results from a specific previous stage."""
        return self.stage_outputs.get(stage_id)

class ChainStageModel(BaseModel):
    """Individual stage within an agent chain. Single agent per stage."""
    name: str = Field(description="Human-readable stage name")
    agent: str = Field(description="Agent identifier (built-in class name or 'ConfigurableAgent:agent-name')")
    
class ChainDefinitionModel(BaseModel):
    """Complete agent chain definition. Sequential stages only."""
    chain_id: str = Field(description="Unique chain identifier")
    alert_types: List[str] = Field(description="Alert types this chain handles")
    stages: List[ChainStageModel] = Field(min_items=1, description="Sequential stages in the chain (1 stage = single agent, 2+ stages = multi-agent chain)")
    description: Optional[str] = Field(default=None, description="Human-readable chain description")

# No ChainExecutionState needed - database-driven execution using AlertSession and StageExecution tables
# All execution state persisted in database for reliability, debugging, and audit trail
```

**Configuration Models:**
```python
class ConfigurableChainModel(BaseModel):
    """YAML-configurable chain definition. Simple sequential chains."""
    alert_types: List[str] = Field(min_items=1, description="Alert types handled by this chain")
    stages: List[Dict[str, str]] = Field(min_items=1, description="Sequential stages - YAML list order preserved for execution (1 stage = single agent)")
    description: Optional[str] = Field(default=None, description="Chain description")

class AgentConfigModel(BaseModel):
    """Individual agent configuration. Agents are pure processing components."""
    mcp_servers: List[str] = Field(min_items=1, description="MCP servers this agent uses")
    custom_instructions: str = Field(description="Agent-specific instructions")
    # Removed: alert_types (now only in chains)

class CombinedConfigModel(BaseModel):
    """Extended configuration model. Agents are pure components, chains map alert types."""
    agents: Dict[str, AgentConfigModel] = Field(default_factory=dict, description="Reusable processing components")
    mcp_servers: Dict[str, MCPServerConfigModel] = Field(default_factory=dict)
    agent_chains: Dict[str, ConfigurableChainModel] = Field(default_factory=dict, description="Alert type to workflow mappings")
```

**API Enhancement Models (Clean, Extensible Design):**
```python
class ChainNode(BaseModel):
    """Individual node/stage in the chain with current status."""
    id: str = Field(description="Node identifier (e.g., 'initial-analysis')")
    agent: str = Field(description="Agent name for this node")
    status: str = Field(description="Node status: pending|active|completed|failed|skipped")

class ChainInfo(BaseModel):
    """Complete chain structure and current execution state."""
    id: str = Field(description="Chain identifier")
    type: str = Field(default="sequential", description="Chain type: sequential")
    nodes: List[ChainNode] = Field(description="All nodes in the chain with current status")
```

### Configuration Design

**Built-in Chain Definitions (Clean New Design):**
```python
# backend/tarsy/config/builtin_config.py

# REMOVE LEGACY MAPPINGS - Clean slate approach
# DELETE: BUILTIN_AGENT_MAPPINGS = {...}  # Remove entirely

# Built-in chain definitions - ONLY source of truth for alert type mappings
BUILTIN_CHAIN_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # Convert existing single-agent mappings to 1-stage chains
    "kubernetes-agent-chain": {
        "alert_types": ["kubernetes", "NamespaceTerminating"], 
        "stages": [
            {"name": "analysis", "agent": "KubernetesAgent"}
        ],
        "description": "Single-stage Kubernetes analysis"
    },
    
    # Multi-agent chains (new workflow capabilities)
    "kubernetes-troubleshooting-chain": {
        "alert_types": ["KubernetesIssue", "PodFailure"],
        "stages": [
            {"name": "data-collection", "agent": "KubernetesAgent"},
            {"name": "root-cause-analysis", "agent": "KubernetesAgent"}
        ],
        "description": "Multi-stage Kubernetes troubleshooting workflow"
    }
}

# ChainRegistry builds alert_type mappings dynamically from BUILTIN_CHAIN_DEFINITIONS only
# No legacy conversion needed - clean new design
```

**YAML Configuration Structure:**
```yaml
# Simple sequential chains in existing config/agents.yaml structure
mcp_servers:
  # MCP server definitions (unchanged)
  
agents:
  # Individual agents are now pure processing components (no alert_types)
  data-collector-agent:
    mcp_servers: ["kubernetes-server"]
    custom_instructions: "Collect data for next stage. Do not analyze."
    
  analysis-agent:
    mcp_servers: ["kubernetes-server"]
    custom_instructions: "Analyze data from previous stage."

agent_chains:
  # Simple sequential chains only
  security-incident-chain:
    alert_types: ["SecurityBreach"]
    stages:  # YAML list preserves order - stage execution follows YAML order
      - name: "data-collection"    # Executes first
        agent: "data-collector-agent"
      - name: "analysis"           # Executes second
        agent: "analysis-agent"
    description: "Simple 2-stage security workflow"
```

### API Design

**Core Service APIs:**
```python
class ChainRegistry:
    """Unified registry. Simple chain lookup, single agents as 1-stage chains."""
    
    def get_chain_for_alert_type(self, alert_type: str) -> ChainDefinitionModel:
        """Always returns a chain. Builds alert_type mappings dynamically from chain definitions."""
        
    def _build_alert_type_mappings(self) -> Dict[str, str]:
        """Build alert_type -> chain_id mappings from chain definitions (no separate mapping needed)."""
        
    def list_available_chains(self) -> List[str]:
        """List all chain IDs from built-in and YAML sources."""

class ChainOrchestrator:
    """Simple sequential execution only."""
    
    async def execute_chain(
        self, 
        chain_def: ChainDefinitionModel, 
        alert_data: Dict[str, Any],
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Execute stages sequentially, one after another."""
        
    async def _execute_stage(
        self,
        stage: ChainStageModel,
        enriched_alert_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Phase 1: Execute single agent in stage, enrich data for next stage."""
        
    # Phase 2/3: Will add execute_parallel_stage(), evaluate_routing_conditions(), etc.
```

**Simple Alert API (No Changes for Phase 1):**
```python
# Keep existing simple responses for alert submission endpoints
class AlertResponse(BaseModel):
    alert_id: str
    status: str 
    message: str
    # No chain info - keep it simple for basic alert submission

class ProcessingStatus(BaseModel):
    alert_id: str
    status: str
    progress: int  # 0-100
    message: str
    # No chain info - basic progress tracking only

# Simple alert endpoints remain unchanged
@app.post("/alerts")  # Basic alert submission
@app.get("/processing-status/{alert_id}")  # Basic progress tracking
```
- **Purpose**: Simple alert submission and basic progress tracking
- **Users**: Dev UI, external alert systems, basic integrations
- **Philosophy**: Keep it minimal - rich data available through dashboard API

**Simple Alert API Examples:**
```bash
# Simple alert submission (unchanged from current)
curl POST /alerts -d '{"alert_type":"kubernetes","runbook":"...","data":{...}}'
# Response: {
#   "alert_id":"123",
#   "status":"queued", 
#   "message":"Alert queued for processing"
# }

# Simple progress tracking (unchanged from current)
curl GET /processing-status/123
# Response: {
#   "alert_id":"123",
#   "status":"processing",
#   "progress":45,
#   "message":"Processing alert..."
# }

# For rich chain visualization and monitoring, use the dashboard API:
# GET /api/v1/history/sessions - complete chain structure and progress
# GET /api/v1/history/sessions/{session_id} - detailed stage breakdown
```

**API Architecture Summary:**
```
┌─────────────────────────────────────────────────────────────────┐
│                     CLEAN API SEPARATION                        │
├─────────────────────────────────────────────────────────────────┤
│  Simple Alert APIs          │  Rich Dashboard APIs              │
│  (No Changes)               │  (Enhanced for Chains)            │
│                             │                                   │
│  POST /alerts               │  GET /api/v1/history/sessions     │
│  GET /processing-status/*   │  GET /api/v1/history/sessions/*   │
│                             │                                   │
│  • Basic progress           │  • Complete chain visualization   │
│  • Minimal data             │  • Stage-by-stage breakdown       │
│  • Dev UI, external systems │  • Dashboard, power users         │
└─────────────────────────────────────────────────────────────────┘
```

**Benefits:**
- **No Breaking Changes**: Alert submission APIs remain exactly as-is
- **Rich Where Needed**: Dashboard gets complete chain visualization
- **Clean Separation**: Simple use cases stay simple, complex use cases get rich data
- **Future Migration**: Can unify APIs later when needed without disruption

### Dashboard API Enhancement

**Enhanced Session API for Rich Chain Visualization:**
```python
# Enhanced models for dashboard rich visualization
class StageExecution(BaseModel):
    """Detailed execution information for a single stage - extensible for all phases."""
    stage_id: str = Field(description="Stage identifier (e.g., 'initial-analysis')")
    status: str = Field(description="Stage status: pending|active|completed|failed|skipped")
    started_at_us: Optional[int] = Field(description="Stage start timestamp (microseconds since epoch UTC)")
    completed_at_us: Optional[int] = Field(description="Stage completion timestamp (microseconds since epoch UTC)")
    duration_ms: Optional[int] = Field(description="Stage execution duration in milliseconds")
    llm_interaction_count: int = Field(default=0, description="Number of LLM interactions in this stage")
    mcp_communication_count: int = Field(default=0, description="Number of MCP communications in this stage")
    stage_output: Optional[Dict[str, Any]] = Field(description="Enriched data produced by this stage")
    error_message: Optional[str] = Field(description="Error message if stage failed")
    
    # Extensible execution model (Phase 1: simple, Phase 2/3: rich)
    execution_type: str = Field(default="sequential", description="Execution type: sequential|parallel|conditional")
    agent: Optional[str] = Field(description="Single agent for this stage (Phase 1: all stages have one agent)")
    agents: Optional[List[str]] = Field(description="Multiple agents for parallel execution (Phase 2: some stages may have multiple agents)")
    
    # Phase 2/3 Future Extensions (not populated in Phase 1)
    parallel_results: Optional[List[Dict[str, Any]]] = Field(description="Individual results from parallel agents")
    routing_decision: Optional[Dict[str, Any]] = Field(description="Conditional routing decision details")
    execution_path: Optional[List[str]] = Field(description="Actual execution path taken (Phase 3: conditional)")

# No ExecutionSummary model needed - all progress info derived from ChainInfo.nodes
# Frontend can calculate: total = nodes.length, completed = nodes.filter(n => n.status === 'completed').length, etc.

# Enhanced session models for dashboard
class DashboardSessionSummary(BaseModel):
    """Rich session summary for dashboard list view."""
    session_id: str = Field(description="Unique session identifier")
    alert_id: str = Field(description="Alert identifier that triggered this session")
    alert_type: Optional[str] = Field(description="Type/category of the alert")
    status: str = Field(description="Overall session status")
    started_at_us: int = Field(description="Session start timestamp (microseconds since epoch UTC)")
    completed_at_us: Optional[int] = Field(description="Session completion timestamp (microseconds since epoch UTC)")
    duration_ms: Optional[int] = Field(description="Total session duration in milliseconds")
    error_message: Optional[str] = Field(description="Error message if session failed")
    
    # Rich chain information for dashboard visualization
    chain: ChainInfo = Field(description="Complete chain structure with current node statuses - progress derived from node statuses")

class DashboardSessionDetail(BaseModel):
    """Complete session details for dashboard detail view."""
    session_id: str = Field(description="Unique session identifier")
    alert_id: str = Field(description="Alert identifier that triggered this session")
    alert_data: Dict[str, Any] = Field(description="Original alert data")
    alert_type: Optional[str] = Field(description="Type/category of the alert")
    status: str = Field(description="Overall session status")
    started_at_us: int = Field(description="Session start timestamp (microseconds since epoch UTC)")
    completed_at_us: Optional[int] = Field(description="Session completion timestamp (microseconds since epoch UTC)")
    duration_ms: Optional[int] = Field(description="Total session duration in milliseconds")
    final_analysis: Optional[str] = Field(description="Final analysis result if completed successfully")
    error_message: Optional[str] = Field(description="Error message if session failed")
    
    # Rich chain execution data for dashboard
    chain: ChainInfo = Field(description="Complete chain structure with final node statuses")
    stage_executions: List[StageExecution] = Field(description="Detailed execution info for each stage")
    chronological_timeline: List[TimelineEvent] = Field(description="All events with stage context")
    # No execution_summary - all statistics derived from chain.nodes and stage_executions

# Enhanced timeline events with extensible stage context
class TimelineEvent(BaseModel):
    """Timeline event with rich stage context - extensible for all phases."""
    event_id: str = Field(description="Unique event identifier")
    type: str = Field(description="Event type: llm_interaction|mcp_communication|stage_start|stage_complete|parallel_start|parallel_complete|routing_decision")
    timestamp_us: int = Field(description="Event timestamp (microseconds since epoch UTC)")
    step_description: str = Field(description="Human-readable description")
    duration_ms: Optional[int] = Field(description="Event duration in milliseconds")
    
    # Extensible stage context for dashboard visualization
    stage_context: Optional[Dict[str, Any]] = Field(description="Rich stage context: stage_id, agent(s), execution_type, routing_path, parallel_group")
    details: Dict[str, Any] = Field(description="Event-specific details")
    
    # Phase 2/3 Future Extensions (not populated in Phase 1)
    parallel_context: Optional[Dict[str, Any]] = Field(description="Parallel execution context: agent_group, parallel_index")
    routing_context: Optional[Dict[str, Any]] = Field(description="Conditional routing context: decision_point, chosen_path, skipped_paths")
```

**Dashboard API Endpoints (Breaking Changes):**
```python
# Enhanced session list for dashboard
@app.get("/api/v1/history/sessions", response_model=DashboardSessionsListResponse)
async def list_sessions_for_dashboard(
    # ... existing filter parameters
) -> DashboardSessionsListResponse:
    """List sessions with rich chain information for dashboard visualization."""

# Enhanced session detail for dashboard  
@app.get("/api/v1/history/sessions/{session_id}", response_model=DashboardSessionDetail)
async def get_session_detail_for_dashboard(
    session_id: str
) -> DashboardSessionDetail:
    """Get complete session details with stage-by-stage breakdown for dashboard."""
```

**Dashboard API Examples:**
```bash
# Dashboard session list - rich chain info for visualization
curl GET /api/v1/history/sessions?page=1&page_size=10
# Response: {
#   "sessions": [
#     {
#       "session_id": "sess_123",
#       "alert_id": "alert_456",
#       "alert_type": "SecurityBreach",
#       "status": "in_progress",
#       "started_at_us": 1734567890123456,
#       "duration_ms": 45000,
#       "chain": {
#         "id": "security-investigation-chain",
#         "type": "sequential",
#         "nodes": [
#           {"id": "initial-analysis", "agent": "SecurityAgent", "status": "completed"},
#           {"id": "threat-assessment", "agent": "ThreatAgent", "status": "active"},
#           {"id": "remediation", "agent": "RemediationAgent", "status": "pending"}
#         ]
#       }
#       // Progress derived from nodes: total=3, completed=1, active=1, pending=1, progress=33%
#     }
#   ]
# }

# Dashboard session detail - complete stage breakdown
curl GET /api/v1/history/sessions/sess_123
# Response: {
#   "session_id": "sess_123",
#   "alert_id": "alert_456",
#   "status": "completed",
#   "chain": {
#     "id": "security-investigation-chain",
#     "type": "sequential", 
#     "nodes": [
#       {"id": "initial-analysis", "agent": "SecurityAgent", "status": "completed"},
#       {"id": "threat-assessment", "agent": "ThreatAgent", "status": "completed"},
#       {"id": "remediation", "agent": "RemediationAgent", "status": "completed"}
#     ]
#   },
#   "stage_executions": [
#     // Phase 1 Example: Sequential execution
#     {
#       "stage_id": "initial-analysis",
#       "status": "completed",
#       "started_at_us": 1734567890123456,
#       "completed_at_us": 1734567905123456,
#       "duration_ms": 15000,
#       "llm_interaction_count": 3,
#       "mcp_communication_count": 5,
#       "stage_output": {"threat_level": "high", "indicators": [...]},
#       "execution_type": "sequential",
#       "agent": "SecurityAgent",
#       "agents": null,
#       "parallel_results": null,
#       "routing_decision": null
#     },
#     // Phase 2 Future Example: Parallel execution stage
#     {
#       "stage_id": "data-gathering",
#       "status": "completed",
#       "execution_type": "parallel", 
#       "agent": null,
#       "agents": ["LogAgent", "MetricsAgent", "EventAgent"],
#       "parallel_results": [
#         {"agent": "LogAgent", "result": {"logs_found": 1247}},
#         {"agent": "MetricsAgent", "result": {"cpu_spike": true}},
#         {"agent": "EventAgent", "result": {"events": [...]}}
#       ]
#     }
#   ],
#   "chronological_timeline": [
#     // Phase 1 Example: Sequential events
#     {
#       "event_id": "evt_001",
#       "type": "stage_start",
#       "timestamp_us": 1734567890123456,
#       "step_description": "Starting initial security analysis",
#       "stage_context": {"stage_id": "initial-analysis", "agent": "SecurityAgent", "execution_type": "sequential"},
#       "parallel_context": null,
#       "routing_context": null
#     },
#     // Phase 2 Future Example: Parallel execution events
#     {
#       "event_id": "evt_015",
#       "type": "parallel_start",
#       "timestamp_us": 1734567920123456,
#       "step_description": "Starting parallel data gathering with 3 agents",
#       "stage_context": {"stage_id": "data-gathering", "execution_type": "parallel"},
#       "parallel_context": {"agents": ["LogAgent", "MetricsAgent", "EventAgent"], "parallel_group": "data-gathering-group"}
#     },
#     // Phase 3 Future Example: Conditional routing events  
#     {
#       "event_id": "evt_025",
#       "type": "routing_decision",
#       "timestamp_us": 1734567950123456,
#       "step_description": "Routing decision: Taking network-analysis path based on threat indicators",
#       "routing_context": {"decision_point": "threat-triage", "chosen_path": "network-analysis", "skipped_paths": ["security-escalation"]}
#     }
#   ]
# }
```

**Dashboard Benefits:**
- **Rich Chain Visualization**: Complete chain graph with real-time node status
- **Stage Drill-Down**: Detailed execution info for each stage  
- **Progress Tracking**: Visual progress indicators and completion percentages
- **Timeline with Context**: Events tagged with stage information for filtering/grouping
- **Historical Comparison**: Compare chain executions across sessions
- **Real-time Updates**: WebSocket updates can target specific stages

**Extensibility Benefits:**
- **Phase 1**: Simple sequential execution with clean, minimal data
- **Phase 2**: Same API structure naturally accommodates parallel execution details
- **Phase 3**: Conditional routing information fits seamlessly into existing models
- **No Breaking Changes**: Dashboard clients get richer data automatically as phases evolve
- **Backward Compatible**: Phase 1 fields remain stable, extensions are additive
- **Future-Proof**: API structure designed to handle complex execution patterns

**Data Efficiency Benefits:**
- **Single Source of Truth**: `chain.nodes` contains all progress information
- **No Redundant Counters**: Progress derived from node statuses (total = nodes.length, completed = nodes.filter(n => n.status === 'completed').length)
- **No Sync Issues**: Cannot have mismatched counters vs actual node states
- **Smaller Payloads**: Less redundant data over the wire
- **Simpler Backend**: No counter maintenance logic required

### Database Design

**Schema Changes:**
- **Enhanced AlertSession**: Add chain definition and current stage tracking
- **New StageExecution Table**: Dedicated table for rich stage execution tracking  
- **Enhanced Interaction Tables**: Link interactions to specific stage executions
- **Breaking Changes OK**: Can clean existing DB data for cleaner schema

**Enhanced AlertSession Table:**
```python
class AlertSession(SQLModel, table=True):
    __tablename__ = "alert_sessions"
    
    # Existing fields (unchanged)
    session_id: str = Field(primary_key=True)
    alert_id: str = Field(unique=True, index=True)
    alert_data: dict = Field(sa_column=Column(JSON))
    alert_type: Optional[str]
    status: str
    started_at_us: int = Field(index=True)
    completed_at_us: Optional[int]
    error_message: Optional[str]
    final_analysis: Optional[str]
    session_metadata: Optional[dict] = Field(sa_column=Column(JSON))
    
    # NEW: Chain execution tracking
    chain_id: str = Field(description="Chain identifier reference")
    chain_definition: dict = Field(sa_column=Column(JSON), description="Complete chain definition at execution time (preserves history)")
    current_stage_index: Optional[int] = Field(description="Current stage index (0-based) for quick lookup")
    current_stage_id: Optional[str] = Field(description="Current stage ID for quick lookup")
    
    # Relationships
    llm_interactions: list["LLMInteraction"] = Relationship(back_populates="session")
    mcp_communications: list["MCPCommunication"] = Relationship(back_populates="session")
    stage_executions: list["StageExecution"] = Relationship(back_populates="session")  # NEW
```

**New StageExecution Table:**
```python
class StageExecution(SQLModel, table=True):
    __tablename__ = "stage_executions"
    
    execution_id: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(foreign_key="alert_sessions.session_id", index=True)
    
    # Stage identification
    stage_id: str = Field(description="Stage identifier (e.g., 'initial-analysis')")
    stage_index: int = Field(description="Stage position in chain (0-based)")
    
    # Phase 1: Sequential execution details
    agent: Optional[str] = Field(description="Single agent for this stage (Phase 1)")
    status: str = Field(description="pending|active|completed|failed|skipped")
    started_at_us: Optional[int] = Field(description="Stage start timestamp")
    completed_at_us: Optional[int] = Field(description="Stage completion timestamp")
    duration_ms: Optional[int] = Field(description="Stage duration in milliseconds")
    stage_output: Optional[dict] = Field(sa_column=Column(JSON), description="Enriched data produced by stage")
    error_message: Optional[str] = Field(description="Error message if stage failed")
    
    # Phase 2/3: Extensible execution model (not used in Phase 1)
    execution_type: str = Field(default="sequential", description="sequential|parallel|conditional")
    agents: Optional[dict] = Field(sa_column=Column(JSON), description="Multiple agents for parallel execution (Phase 2)")
    parallel_results: Optional[dict] = Field(sa_column=Column(JSON), description="Individual results from parallel agents (Phase 2)")
    routing_decision: Optional[dict] = Field(sa_column=Column(JSON), description="Conditional routing decision details (Phase 3)")
    execution_path: Optional[list] = Field(sa_column=Column(JSON), description="Actual execution path taken (Phase 3)")
    
    # Relationships
    session: AlertSession = Relationship(back_populates="stage_executions")
    llm_interactions: list["LLMInteraction"] = Relationship(back_populates="stage_execution")
    mcp_communications: list["MCPCommunication"] = Relationship(back_populates="stage_execution")
```

**Enhanced Interaction Tables:**
```python
class LLMInteraction(SQLModel, table=True):
    # ... existing fields unchanged ...
    
    # NEW: Link to stage execution for rich context
    stage_execution_id: Optional[str] = Field(
        foreign_key="stage_executions.execution_id",
        description="Link to stage execution for timeline context"
    )
    
    # Relationships
    session: AlertSession = Relationship(back_populates="llm_interactions")
    stage_execution: Optional[StageExecution] = Relationship(back_populates="llm_interactions")

class MCPCommunication(SQLModel, table=True):
    # ... existing fields unchanged ...
    
    # NEW: Link to stage execution for rich context
    stage_execution_id: Optional[str] = Field(
        foreign_key="stage_executions.execution_id", 
        description="Link to stage execution for timeline context"
    )
    
    # Relationships
    session: AlertSession = Relationship(back_populates="mcp_communications")
    stage_execution: Optional[StageExecution] = Relationship(back_populates="mcp_communications")
```

**Database Benefits:**
- **History Integrity**: Complete chain definitions preserved at execution time - configuration changes won't break historical data
- **Rich Stage Tracking**: Detailed per-stage execution data with timing, outputs, and error information
- **Phase 2/3 Ready**: Schema naturally extends for parallel execution and conditional routing
- **Query Flexibility**: Easy to query by stage, agent, execution pattern, or timeline
- **Timeline Context**: All LLM/MCP interactions linked to specific stage executions
- **Audit Trail**: Complete reconstruction of "what happened when and why"

**API-to-Database Mapping:**
```python
# ChainInfo API model populated from:
chain_info = ChainInfo(
    id=session.chain_id,
    type=session.chain_definition["type"], 
    nodes=[
        ChainNode(
            id=stage.stage_id,
            agent=stage.agent,
            status=stage.status
        ) for stage in session.stage_executions
    ]
)

# StageExecution API model directly maps to StageExecution DB model
stage_execution = StageExecution(
    stage_id=db_stage.stage_id,
    agent=db_stage.agent,
    status=db_stage.status,
    started_at_us=db_stage.started_at_us,
    stage_output=db_stage.stage_output,
    execution_type=db_stage.execution_type  # Phase 2/3 ready
)

# Timeline events enriched with stage context
timeline_event = TimelineEvent(
    event_id=interaction.interaction_id,
    type="llm_interaction",
    timestamp_us=interaction.timestamp_us,
    stage_context={
        "stage_id": interaction.stage_execution.stage_id,
        "agent": interaction.stage_execution.agent,
        "execution_type": interaction.stage_execution.execution_type
    }
)
```

### Integration Points

**Internal Integrations:**
- **AlertService**: Simplified to use only ChainRegistry for all alert processing (single agents become 1-stage chains)
- **AgentFactory**: No changes needed - creates agents the same way regardless of single-stage vs multi-stage usage  
- **BaseAgent Interface**: Updated to remove runbook_content parameter - agents extract runbook from accumulated_data structure if needed
- **WebSocketManager**: Enhanced to report stage-level progress for all processing (consistent for 1-stage and multi-stage)
- **HistoryService**: Enhanced to store stage-level detail for all alert processing

**External Integrations:**
- **Dashboard**: Enhanced to display chain progress visualization and stage-level history using new optional API fields
- **Existing API Clients**: Continue to work unchanged - can optionally access enhanced chain information through new response fields
- **New API Clients**: Can leverage rich chain and stage metadata for advanced monitoring and debugging

---

## BaseAgent Interface Changes

### Updated BaseAgent Interface (Breaking Change)

**Current Interface (TO BE REPLACED):**
```python
class BaseAgent(ABC):
    async def process_alert(
        self,
        alert_data: Dict[str, Any],      # ← Original alert data only
        runbook_content: str,            # ← Separate runbook parameter (REMOVED)
        session_id: str,
        callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
```

**New Interface (REQUIRED):**
```python
from tarsy.models.chain_models import AccumulatedAlertData

class BaseAgent(ABC):
    async def process_alert(
        self,
        alert_data: AccumulatedAlertData,  # ← NEW: Typed accumulated data structure
        session_id: str,
        callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Process alert with accumulated data from chain execution.
        
        Args:
            alert_data: Accumulated data containing:
                       - original_alert: Original alert data + runbook content
                       - stage_outputs: Results from previous stages (empty for single-stage)
            session_id: Session ID for timeline logging
            callback: Optional progress callback
            
        Returns:
            Dictionary containing analysis result and metadata
        """
```

**Agent Implementation Pattern:**
```python
class KubernetesAgent(BaseAgent):
    async def process_alert(self, alert_data: AccumulatedAlertData, session_id: str, callback=None):
        # Extract data using typed helper methods
        runbook_content = alert_data.get_runbook()
        original_alert = alert_data.get_original_data()
        
        # Check for data from previous stages (multi-stage chains)
        if previous_data := alert_data.get_stage_result("data-collection"):
            logger.info("Using enriched data from data-collection stage")
            # Use previous_data for enhanced analysis
        
        # Continue with existing agent logic using runbook_content...
        # All existing agent logic remains the same, just data access changes
```

### Updated Prompt Builder Integration

**Current PromptContext (TO BE REPLACED):**
```python
@dataclass
class PromptContext:
    agent_name: str
    alert_data: Dict[str, Any]      # ← Original alert only
    runbook_content: str            # ← Separate runbook (REMOVED)
    mcp_data: Dict[str, Any]
    # ... other fields
```

**New PromptContext (REQUIRED):**
```python
@dataclass
class PromptContext:
    agent_name: str
    accumulated_data: AccumulatedAlertData  # ← NEW: Full accumulated data structure
    mcp_data: Dict[str, Any]
    mcp_servers: List[str]
    server_guidance: str = ""
    agent_specific_guidance: str = ""
    available_tools: Optional[Dict] = None
    iteration_history: Optional[List[Dict]] = None
    # ... other fields (runbook_content removed)
```

**Updated BaseAgent Prompt Methods:**
```python
class BaseAgent(ABC):
    def build_analysis_prompt(self, accumulated_data: AccumulatedAlertData, mcp_data: Dict) -> str:
        """Build analysis prompt with accumulated data context."""
        context = self._create_prompt_context(
            accumulated_data=accumulated_data,  # ← No more separate runbook
            mcp_data=mcp_data
        )
        return self._prompt_builder.build_analysis_prompt(context)

    def _create_prompt_context(self, 
                             accumulated_data: AccumulatedAlertData,  # ← NEW parameter type
                             mcp_data: Dict,
                             available_tools: Optional[Dict] = None,
                             iteration_history: Optional[List[Dict]] = None,
                             # ... other params
                             ) -> PromptContext:
        """Create PromptContext with accumulated data structure."""
        return PromptContext(
            agent_name=self.__class__.__name__,
            accumulated_data=accumulated_data,  # ← Pass full accumulated data
            mcp_data=mcp_data,
            mcp_servers=self.mcp_servers(),
            server_guidance=self._get_server_specific_tool_guidance(),
            agent_specific_guidance=self.custom_instructions(),
            available_tools=available_tools,
            iteration_history=iteration_history,
            # ... other fields
        )
```

**Updated PromptBuilder Methods:**
```python
class PromptBuilder:
    def build_analysis_prompt(self, context: PromptContext) -> str:
        """Build comprehensive analysis prompt with stage context."""
        # Extract from accumulated data structure
        runbook_content = context.accumulated_data.get_runbook()
        original_alert = context.accumulated_data.get_original_data()
        stage_outputs = context.accumulated_data.stage_outputs
        
        prompt_parts = [
            self._build_context_section(context),
            self._build_alert_section(original_alert),  # ← Original alert only
            self._build_runbook_section(runbook_content),  # ← Extracted runbook
            self._build_stage_outputs_section(stage_outputs),  # ← NEW: Previous stage results
            self._build_mcp_data_section(context.mcp_data),
            self._build_agent_specific_analysis_guidance(context),
            self._build_analysis_instructions()
        ]
        
        return "\n\n".join(prompt_parts)
    
    def _build_stage_outputs_section(self, stage_outputs: Dict[str, Dict[str, Any]]) -> str:
        """NEW: Build section showing results from previous stages."""
        if not stage_outputs:
            return ""
        
        parts = ["## Previous Stage Results"]
        parts.append("The following stages have already been executed in this chain:")
        
        for stage_id, result in stage_outputs.items():
            parts.append(f"### Stage: {stage_id}")
            parts.append("```json")
            parts.append(json.dumps(result, indent=2))
            parts.append("```")
        
        parts.append("Use this information to build upon previous analysis and avoid duplicating work.")
        return "\n\n".join(parts)
```

### Migration Impact Summary

**Files Requiring Updates:**
1. `backend/tarsy/agents/base_agent.py` - Interface change, prompt method updates
2. `backend/tarsy/agents/prompt_builder.py` - PromptContext and method updates
3. `backend/tarsy/agents/kubernetes_agent.py` - Implementation updates for new interface
4. `backend/tarsy/agents/configurable_agent.py` - Implementation updates for new interface
5. `backend/tarsy/models/chain_models.py` - NEW: Add AccumulatedAlertData model

**Benefits:**
- **Type Safety**: Pydantic model prevents runtime errors
- **Stage Context**: Agents can access previous stage results for enhanced analysis
- **Cleaner Interface**: No more scattered runbook parameters
- **Extensible**: Easy to add more accumulated data types in future phases
- **IDE Support**: Full autocompletion and type checking

---

## Configuration Loading Implementation

### Extended ConfigurationLoader for Agent Chains

**Updated CombinedConfigModel (Required):**
```python
class CombinedConfigModel(BaseModel):
    """Extended configuration model with agent chains support."""
    agents: Dict[str, AgentConfigModel] = Field(default_factory=dict, description="Reusable processing components")
    mcp_servers: Dict[str, MCPServerConfigModel] = Field(default_factory=dict)
    agent_chains: Dict[str, ConfigurableChainModel] = Field(default_factory=dict, description="Alert type to workflow mappings")  # NEW
```

**Updated ConfigurationLoader.load_and_validate() Method:**
```python
class ConfigurationLoader:
    def load_and_validate(self) -> CombinedConfigModel:
        """Load and validate configuration with agent chains support."""
        try:
            # ... existing YAML loading logic ...
            
            # Validate with Pydantic models (now includes agent_chains)
            config = self._validate_configuration_structure(raw_config)
            
            # Enhanced validation steps
            self._validate_mcp_server_references(config)
            self._detect_circular_dependencies(config)
            self._detect_conflicts(config)  # Now includes chain conflicts
            self._validate_agent_chains(config)  # NEW: Chain-specific validation
            self._validate_configuration_completeness(config)
            
            return config
            
        except Exception as e:
            # ... existing error handling ...
    
    def _validate_agent_chains(self, config: CombinedConfigModel) -> None:
        """
        Validate agent chain definitions and references.
        
        Validates:
        1. All referenced agents exist (built-in or configured)
        2. No duplicate chain names with built-in chains
        3. Chain structure is valid
        4. Alert type mappings don't conflict
        
        Args:
            config: Validated configuration model
            
        Raises:
            ConfigurationError: If chain validation fails
        """
        if not config.agent_chains:
            logger.debug("No agent chains configured")
            return
        
        logger.debug(f"Validating {len(config.agent_chains)} agent chains")
        
        # 1. Validate chain names don't conflict with built-in chains
        self._validate_chain_name_conflicts(config.agent_chains)
        
        # 2. Validate agent references in chains
        self._validate_chain_agent_references(config.agent_chains, config.agents)
        
        # 3. Validate chain structure
        self._validate_chain_structures(config.agent_chains)
        
        # 4. Validate alert type mappings
        self._validate_chain_alert_type_conflicts(config.agent_chains)
        
        logger.info(f"Agent chain validation completed successfully")
    
    def _validate_chain_name_conflicts(self, yaml_chains: Dict[str, ConfigurableChainModel]) -> None:
        """Validate chain names don't conflict with built-in chains."""
        from tarsy.config.builtin_config import BUILTIN_CHAIN_DEFINITIONS
        
        conflicts = []
        for chain_name in yaml_chains.keys():
            if chain_name in BUILTIN_CHAIN_DEFINITIONS:
                conflicts.append(chain_name)
        
        if conflicts:
            raise ConfigurationError(
                f"YAML chain names conflict with built-in chains: {', '.join(conflicts)}. "
                f"Built-in chain names: {', '.join(BUILTIN_CHAIN_DEFINITIONS.keys())}"
            )
    
    def _validate_chain_agent_references(
        self, 
        yaml_chains: Dict[str, ConfigurableChainModel], 
        configured_agents: Dict[str, AgentConfigModel]
    ) -> None:
        """Validate all chain stages reference valid agents."""
        errors = []
        
        for chain_name, chain_def in yaml_chains.items():
            for stage_idx, stage in enumerate(chain_def.stages):
                agent_name = stage.get('agent')
                if not agent_name:
                    errors.append(f"Chain '{chain_name}' stage {stage_idx} missing 'agent' field")
                    continue
                
                # Check if agent exists (built-in or configured)
                if (agent_name not in self.BUILTIN_AGENT_CLASSES and 
                    agent_name not in configured_agents):
                    errors.append(
                        f"Chain '{chain_name}' stage '{stage.get('name', stage_idx)}' "
                        f"references unknown agent '{agent_name}'. "
                        f"Available agents: {', '.join(list(self.BUILTIN_AGENT_CLASSES) + list(configured_agents.keys()))}"
                    )
        
        if errors:
            raise ConfigurationError(f"Chain agent reference errors: {'; '.join(errors)}")
    
    def _validate_chain_structures(self, yaml_chains: Dict[str, ConfigurableChainModel]) -> None:
        """Validate chain structure requirements."""
        errors = []
        
        for chain_name, chain_def in yaml_chains.items():
            # Validate required fields
            if not chain_def.alert_types:
                errors.append(f"Chain '{chain_name}' must specify at least one alert_type")
            
            if not chain_def.stages:
                errors.append(f"Chain '{chain_name}' must specify at least one stage")
            
            # Validate stage structure
            for stage_idx, stage in enumerate(chain_def.stages):
                if not isinstance(stage, dict):
                    errors.append(f"Chain '{chain_name}' stage {stage_idx} must be a dictionary")
                    continue
                
                if 'name' not in stage:
                    errors.append(f"Chain '{chain_name}' stage {stage_idx} missing required 'name' field")
                
                if 'agent' not in stage:
                    errors.append(f"Chain '{chain_name}' stage {stage_idx} missing required 'agent' field")
        
        if errors:
            raise ConfigurationError(f"Chain structure errors: {'; '.join(errors)}")
    
    def _validate_chain_alert_type_conflicts(self, yaml_chains: Dict[str, ConfigurableChainModel]) -> None:
        """
        Validate alert types don't conflict between YAML chains or with built-in chains.
        
        STRICT RULE: No alert type can be mapped to multiple chains.
        Any conflict results in configuration error.
        """
        from tarsy.config.builtin_config import BUILTIN_CHAIN_DEFINITIONS
        
        # Build alert type mappings from built-in chains
        builtin_mappings = {}
        for chain_id, chain_data in BUILTIN_CHAIN_DEFINITIONS.items():
            for alert_type in chain_data.get('alert_types', []):
                builtin_mappings[alert_type] = chain_id
        
        # Check YAML chains for conflicts
        yaml_mappings = {}
        errors = []
        
        for chain_name, chain_def in yaml_chains.items():
            for alert_type in chain_def.alert_types:
                # STRICT: Any conflict is an error (built-in or YAML)
                if alert_type in builtin_mappings:
                    errors.append(
                        f"Alert type '{alert_type}' conflict: YAML chain '{chain_name}' "
                        f"cannot override built-in chain '{builtin_mappings[alert_type]}'"
                    )
                
                # STRICT: Multiple YAML chains for same alert type is an error
                if alert_type in yaml_mappings:
                    errors.append(
                        f"Alert type '{alert_type}' conflict: mapped to multiple YAML chains "
                        f"'{yaml_mappings[alert_type]}' and '{chain_name}'"
                    )
                
                yaml_mappings[alert_type] = chain_name
        
        if errors:
            raise ConfigurationError(
                f"Alert type mapping conflicts detected. Each alert type can only be mapped to ONE chain. "
                f"Conflicts: {'; '.join(errors)}"
            )
```

**Error Handling Examples:**
```python
# Example error messages for common mistakes:

# 1. Chain references unknown agent
# ConfigurationError: Chain agent reference errors: Chain 'security-chain' stage 'analysis' references unknown agent 'unknown-agent'. Available agents: KubernetesAgent, data-collector-agent, analysis-agent

# 2. Chain name conflicts with built-in
# ConfigurationError: YAML chain names conflict with built-in chains: kubernetes-agent-chain. Built-in chain names: kubernetes-agent-chain, kubernetes-troubleshooting-chain

# 3. Alert type conflicts (STRICT - no conflicts allowed)
# ConfigurationError: Alert type mapping conflicts detected. Each alert type can only be mapped to ONE chain. Conflicts: Alert type 'kubernetes' conflict: YAML chain 'custom-k8s-chain' cannot override built-in chain 'kubernetes-agent-chain'

# 4. Missing required fields
# ConfigurationError: Chain structure errors: Chain 'incomplete-chain' stage 0 missing required 'agent' field; Chain 'empty-chain' must specify at least one alert_type
```

### Integration with Existing Validation

**Updated _detect_conflicts() Method:**
```python
def _detect_conflicts(self, config: CombinedConfigModel) -> None:
    """Enhanced conflict detection including agent chains."""
    # Existing agent name conflict detection
    self._detect_agent_name_conflicts(config.agents)
    
    # Existing MCP server name conflict detection  
    self._detect_mcp_server_name_conflicts(config.mcp_servers)
    
    # NEW: Chain name conflict detection (handled in _validate_agent_chains)
    # Chain conflicts are validated separately for better error messages
```

---

## ChainRegistry Implementation

### Complete ChainRegistry Class

**ChainRegistry with Single Agent Conversion:**
```python
from typing import Dict, List, Optional
from tarsy.models.chain_models import ChainDefinitionModel, ChainStageModel
from tarsy.config.builtin_config import BUILTIN_CHAIN_DEFINITIONS
from tarsy.config.agent_config import ConfigurationLoader

class ChainRegistry:
    """
    Unified registry for all chain definitions (built-in and configurable).
    
    KEY PRINCIPLE: ALL agents execute through chains.
    Single agents are converted to 1-stage chains automatically.
    """
    
    def __init__(self, config_loader: Optional[ConfigurationLoader] = None):
        """
        Initialize ChainRegistry with built-in and YAML chain definitions.
        
        Args:
            config_loader: Optional configuration loader for YAML chains
        """
        # Load built-in chains (always available)
        self.builtin_chains = self._load_builtin_chains()
        
        # Load YAML chains (if configuration provided)
        self.yaml_chains = self._load_yaml_chains(config_loader) if config_loader else {}
        
        # Build unified alert type mappings (STRICT - no conflicts allowed)
        self.alert_type_mappings = self._build_alert_type_mappings()
        
        logger.info(
            f"ChainRegistry initialized: "
            f"{len(self.builtin_chains)} built-in chains, "
            f"{len(self.yaml_chains)} YAML chains, "
            f"{len(self.alert_type_mappings)} alert type mappings"
        )
    
    def get_chain_for_alert_type(self, alert_type: str) -> ChainDefinitionModel:
        """
        Get chain definition for alert type.
        
        Args:
            alert_type: Alert type to find chain for
            
        Returns:
            ChainDefinitionModel for the alert type
            
        Raises:
            ValueError: If no chain found for alert type (STRICT error handling)
        """
        chain_id = self.alert_type_mappings.get(alert_type)
        
        if not chain_id:
            available_types = sorted(self.alert_type_mappings.keys())
            raise ValueError(
                f"No chain found for alert type '{alert_type}'. "
                f"Available alert types: {', '.join(available_types)}"
            )
        
        # Get chain from appropriate source
        if chain_id in self.builtin_chains:
            return self.builtin_chains[chain_id]
        elif chain_id in self.yaml_chains:
            return self.yaml_chains[chain_id]
        else:
            # This should never happen if mappings are built correctly
            raise RuntimeError(f"Chain '{chain_id}' found in mappings but not in any chain source")
    
    def list_available_chains(self) -> List[str]:
        """List all available chain IDs."""
        all_chains = set()
        all_chains.update(self.builtin_chains.keys())
        all_chains.update(self.yaml_chains.keys())
        return sorted(all_chains)
    
    def list_available_alert_types(self) -> List[str]:
        """List all available alert types."""
        return sorted(self.alert_type_mappings.keys())
    
    def _load_builtin_chains(self) -> Dict[str, ChainDefinitionModel]:
        """Convert built-in chain definitions to ChainDefinitionModel objects."""
        chains = {}
        
        for chain_id, chain_data in BUILTIN_CHAIN_DEFINITIONS.items():
            chains[chain_id] = ChainDefinitionModel(
                chain_id=chain_id,
                alert_types=chain_data['alert_types'],
                stages=[
                    ChainStageModel(name=stage['name'], agent=stage['agent'])
                    for stage in chain_data['stages']
                ],
                description=chain_data.get('description')
            )
            
        logger.debug(f"Loaded {len(chains)} built-in chains")
        return chains
    
    def _load_yaml_chains(self, config_loader: ConfigurationLoader) -> Dict[str, ChainDefinitionModel]:
        """Load and convert YAML chain configurations to ChainDefinitionModel objects."""
        try:
            config = config_loader.load_and_validate()
            chains = {}
            
            for chain_id, chain_config in config.agent_chains.items():
                chains[chain_id] = ChainDefinitionModel(
                    chain_id=chain_id,
                    alert_types=chain_config.alert_types,
                    stages=[
                        ChainStageModel(name=stage['name'], agent=stage['agent'])
                        for stage in chain_config.stages
                    ],
                    description=chain_config.description
                )
                
            logger.debug(f"Loaded {len(chains)} YAML chains")
            return chains
            
        except Exception as e:
            logger.error(f"Failed to load YAML chains: {str(e)}")
            # Don't fail startup - continue with built-in chains only
            return {}
    
# REMOVED: _convert_legacy_agents_to_chains() method
# Clean new design - no legacy conversion needed
    
    def _build_alert_type_mappings(self) -> Dict[str, str]:
        """
        Build unified alert_type -> chain_id mappings.
        
        STRICT RULE: Each alert type can only map to ONE chain.
        Any conflicts result in startup error.
        """
        mappings = {}
        conflicts = []
        
        # Process all chain sources and detect conflicts
        all_chain_sources = [
            ("built-in", self.builtin_chains),
            ("YAML", self.yaml_chains)
        ]
        
        for source_name, chains in all_chain_sources:
            for chain_id, chain_def in chains.items():
                for alert_type in chain_def.alert_types:
                    if alert_type in mappings:
                        existing_chain = mappings[alert_type]
                        conflicts.append(
                            f"Alert type '{alert_type}' mapped to multiple chains: "
                            f"'{existing_chain}' and '{chain_id}' (from {source_name})"
                        )
                    else:
                        mappings[alert_type] = chain_id
        
        # STRICT: Any conflicts cause startup failure
        if conflicts:
            raise RuntimeError(
                f"Alert type mapping conflicts detected during ChainRegistry initialization. "
                f"Each alert type can only be mapped to ONE chain. "
                f"Conflicts: {'; '.join(conflicts)}"
            )
        
        logger.debug(f"Built {len(mappings)} alert type mappings")
        return mappings
```

### ChainRegistry Error Handling

**Error Scenarios:**
```python
# 1. No chain found for alert type
try:
    chain = chain_registry.get_chain_for_alert_type("unknown-type")
except ValueError as e:
    # Error: "No chain found for alert type 'unknown-type'. Available alert types: kubernetes, NamespaceTerminating, SecurityBreach"
    pass

# 2. Alert type conflicts during startup
# RuntimeError: Alert type mapping conflicts detected during ChainRegistry initialization. Each alert type can only be mapped to ONE chain. Conflicts: Alert type 'kubernetes' mapped to multiple chains: 'kubernetes-agent-chain' and 'custom-k8s-chain' (from YAML)

# 3. YAML chain loading failure (non-fatal)
# WARNING: Failed to load YAML chains: Chain agent reference errors: Chain 'bad-chain' stage 'analysis' references unknown agent 'missing-agent'
# ChainRegistry continues with built-in chains only
```

### Integration with AlertService

### Complete AlertService Integration

**Updated AlertService Constructor:**
```python
from tarsy.services.chain_registry import ChainRegistry
from tarsy.services.chain_orchestrator import ChainOrchestrator
# REMOVE: from tarsy.services.agent_registry import AgentRegistry

class AlertService:
    def __init__(self, settings: Settings):
        """Initialize AlertService with chain-based processing."""
        self.settings = settings
        
        # Initialize services
        self.runbook_service = RunbookService(settings)
        self.history_service = get_history_service()
        
        # REPLACE: AgentRegistry with ChainRegistry
        config_loader = ConfigurationLoader(settings.agent_config_file) if settings.agent_config_file else None
        self.chain_registry = ChainRegistry(config_loader)
        
        # Initialize MCP and LLM services (unchanged)
        self.mcp_server_registry = MCPServerRegistry(settings=settings)
        self.mcp_client = MCPClient(settings, self.mcp_server_registry)
        self.llm_manager = LLMManager(settings)
        
        # Initialize agent factory (unchanged)
        self.agent_factory = None  # Will be initialized in initialize()
        
        # NEW: Initialize ChainOrchestrator
        self.chain_orchestrator = ChainOrchestrator(
            agent_factory=None,  # Set in initialize()
            session_repo=self.history_service,  # Use history service for DB operations
            stage_repo=self.history_service     # Use history service for stage operations
        )
        
        logger.info("AlertService initialized with chain-based processing")

    async def initialize(self):
        """Initialize the service and all dependencies."""
        try:
            # Initialize LLM manager
            await self.llm_manager.initialize()
            
            # Initialize MCP client with server registry
            await self.mcp_client.initialize()
            
            # Initialize agent factory with all dependencies
            self.agent_factory = AgentFactory(
                llm_manager=self.llm_manager,
                mcp_client=self.mcp_client,
                mcp_server_registry=self.mcp_server_registry,
                chain_registry=self.chain_registry  # NEW: Pass chain registry instead of agent registry
            )
            
            # Update ChainOrchestrator with initialized agent factory
            self.chain_orchestrator.agent_factory = self.agent_factory
            
            logger.info("AlertService initialization completed successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize AlertService: {str(e)}")
            raise
```

**Updated Alert Processing Method:**
```python
async def _process_alert_internal(self, alert: AlertProcessingData, progress_callback):
    """Unified alert processing through chains (single agents = 1-stage chains)."""
    session_id = None
    try:
        # Step 1: Validate prerequisites (unchanged)
        if not self.llm_manager.is_available():
            raise Exception("Cannot process alert: No LLM providers are available")
            
        if not self.agent_factory:
            raise Exception("Agent factory not initialized - call initialize() first")
        
        # Step 2: Get chain for alert type (REPLACES agent selection)
        if progress_callback:
            await progress_callback(5, "Selecting chain for alert processing")
        
        try:
            chain_def = self.chain_registry.get_chain_for_alert_type(alert.alert_type)
            logger.info(f"Selected chain '{chain_def.chain_id}' for alert type '{alert.alert_type}'")
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"Chain selection failed: {error_msg}")
            
            if progress_callback:
                await progress_callback(100, f"Error: {error_msg}")
                
            return self._format_error_response(alert, error_msg)
        
        # Step 3: Download runbook (unchanged)
        if progress_callback:
            await progress_callback(10, "Downloading runbook")
            
        runbook_content = await self.runbook_service.download_runbook(alert.runbook)
        
        # Step 4: Create history session with chain info
        session_id = self._create_history_session(alert, chain_def.chain_id)
        
        # Step 5: Execute through ChainOrchestrator (UNIFIED PATH)
        if progress_callback:
            await progress_callback(20, f"Executing chain: {chain_def.chain_id}")
        
        result = await self.chain_orchestrator.execute_chain(
            chain_def=chain_def,
            alert_data=alert.alert_data,
            runbook_content=runbook_content,
            progress_callback=progress_callback
        )
        
        # Step 6: Extract final analysis from chain result
        final_analysis = result.get("final_analysis", "Chain completed successfully")
        
        # Step 7: Update history session with completion
        self._update_session_completion(session_id, final_analysis)
        
        if progress_callback:
            await progress_callback(100, "Processing completed")
            
        return final_analysis
        
    except Exception as e:
        # Error handling (similar to current implementation)
        error_msg = str(e)
        logger.error(f"Alert processing failed: {error_msg}")
        
        self._update_session_error(session_id, error_msg)
        
        if progress_callback:
            await progress_callback(100, f"Error: {error_msg}")
            
        return self._format_error_response(alert, error_msg)
```

**Key Changes Summary:**
- **Remove**: `self.agent_registry = AgentRegistry()`
- **Add**: `self.chain_registry = ChainRegistry(config_loader)`
- **Add**: `self.chain_orchestrator = ChainOrchestrator(...)`
- **Replace**: `agent_class_name = self.agent_registry.get_agent_for_alert_type(alert_type)` 
- **With**: `chain_def = self.chain_registry.get_chain_for_alert_type(alert.alert_type)`
- **Replace**: Direct agent execution with `chain_orchestrator.execute_chain()`

---

## Error Handling Strategy

### Graceful Error Handling with Full Observability

**Core Principles:**
1. **Graceful Degradation**: Stage failures don't stop chain execution - continue to next stage
2. **Full Recording**: All errors recorded as stage outputs for history/dashboard visibility
3. **Observability First**: Errors become part of the data flow, not exceptions that break it
4. **Partial Results**: Always preserve and return what was accomplished

### Enhanced ChainOrchestrator Error Handling

**Updated ChainOrchestrator.execute_chain() with Graceful Error Handling:**
```python
class ChainOrchestrator:
    async def execute_chain(
        self, 
        chain_def: ChainDefinitionModel, 
        alert_data: Dict[str, Any],
        runbook_content: str
    ) -> Dict[str, Any]:
        """Execute chain with graceful error handling - stage failures don't stop execution."""
        
        # Create session with chain definition snapshot
        session = AlertSession(
            alert_id=alert_data["alert_id"],
            chain_id=chain_def.id,
            chain_definition=chain_def.dict(),
            current_stage_index=0,
            status="processing"
        )
        await self.session_repo.create(session)
        
        # Start with original alert data + downloaded runbook
        accumulated_data = AccumulatedAlertData(
            original_alert={
                **alert_data,
                "runbook": runbook_content
            },
            stage_outputs={}
        )
        
        # Track execution statistics
        execution_stats = {
            "total_stages": len(chain_def.stages),
            "completed_stages": 0,
            "failed_stages": 0,
            "skipped_stages": 0,
            "stage_results": []
        }
        
        # Execute all stages - failures don't stop execution
        for i, stage in enumerate(chain_def.stages):
            # Create stage execution record
            stage_exec = StageExecution(
                session_id=session.session_id,
                stage_id=stage.name,
                stage_index=i,
                agent=stage.agent,
                status="active",
                started_at_us=now_us()
            )
            await self.stage_repo.create(stage_exec)
            
            # Update session current stage
            session.current_stage_index = i
            session.current_stage_id = stage.name
            await self.session_repo.update(session)
            
            try:
                # Execute stage with full accumulated history
                logger.info(f"Executing stage {i+1}/{len(chain_def.stages)}: {stage.name}")
                result = await self._execute_stage_with_error_handling(stage, accumulated_data, stage_exec)
                
                # Add stage result to accumulated data (even if it contains errors)
                accumulated_data.stage_outputs[stage.name] = result
                
                # Update stage as completed (even if it had errors - it completed execution)
                stage_exec.status = "completed"
                stage_exec.completed_at_us = now_us()
                stage_exec.duration_ms = (stage_exec.completed_at_us - stage_exec.started_at_us) // 1000
                stage_exec.stage_output = result
                
                # Track execution stats
                if result.get("error"):
                    execution_stats["failed_stages"] += 1
                    logger.warning(f"Stage {stage.name} completed with errors: {result.get('error')}")
                else:
                    execution_stats["completed_stages"] += 1
                    logger.info(f"Stage {stage.name} completed successfully")
                
                execution_stats["stage_results"].append({
                    "stage": stage.name,
                    "status": "completed_with_errors" if result.get("error") else "completed",
                    "duration_ms": stage_exec.duration_ms
                })
                
            except Exception as fatal_error:
                # Fatal stage error (agent not found, database failure, etc.)
                error_result = {
                    "error": f"Fatal stage error: {str(fatal_error)}",
                    "error_type": "fatal",
                    "stage_name": stage.name,
                    "timestamp": now_us()
                }
                
                # Record fatal error as stage output
                accumulated_data.stage_outputs[stage.name] = error_result
                
                # Update stage as failed
                stage_exec.status = "failed"
                stage_exec.completed_at_us = now_us()
                stage_exec.duration_ms = (stage_exec.completed_at_us - stage_exec.started_at_us) // 1000
                stage_exec.error_message = str(fatal_error)
                stage_exec.stage_output = error_result
                
                execution_stats["failed_stages"] += 1
                execution_stats["stage_results"].append({
                    "stage": stage.name,
                    "status": "failed",
                    "duration_ms": stage_exec.duration_ms,
                    "error": str(fatal_error)
                })
                
                logger.error(f"Fatal error in stage {stage.name}: {str(fatal_error)}")
                # Continue to next stage even after fatal error
                
            await self.stage_repo.update(stage_exec)
        
        # Determine final session status based on execution results
        final_status = self._determine_final_status(execution_stats)
        final_analysis = self._generate_final_analysis(accumulated_data, execution_stats)
        
        # Mark session as completed (even if some stages failed)
        session.status = final_status
        session.completed_at_us = now_us()
        session.final_analysis = final_analysis
        await self.session_repo.update(session)
        
        logger.info(
            f"Chain execution completed: {execution_stats['completed_stages']} successful, "
            f"{execution_stats['failed_stages']} failed, "
            f"{execution_stats['skipped_stages']} skipped"
        )
        
        return {
            "status": final_status,
            "final_analysis": final_analysis,
            "execution_stats": execution_stats,
            "accumulated_data": accumulated_data,  # Full history available
            "chain_id": chain_def.chain_id
        }
    
    async def _execute_stage_with_error_handling(
        self, 
        stage: ChainStageModel, 
        accumulated_data: AccumulatedAlertData,
        stage_exec: StageExecution
    ) -> Dict[str, Any]:
        """Execute single stage with comprehensive error handling."""
        try:
            # Get agent and execute
            agent = await self.agent_factory.get_agent(stage.agent)
            
            # Execute agent with timeout and error capture
            result = await asyncio.wait_for(
                agent.process_alert(
                    alert_data=accumulated_data,
                    session_id=stage_exec.session_id
                ),
                timeout=300  # 5 minute timeout per stage
            )
            
            # Validate result structure
            if not isinstance(result, dict):
                logger.warning(f"Stage {stage.name} returned non-dict result, wrapping")
                result = {"analysis": str(result), "metadata": {"wrapped": True}}
            
            # Add stage metadata
            result["stage_metadata"] = {
                "stage_name": stage.name,
                "agent": stage.agent,
                "execution_time_ms": stage_exec.duration_ms,
                "timestamp": now_us()
            }
            
            return result
            
        except asyncio.TimeoutError:
            # Stage timeout - record as error but continue
            return {
                "error": f"Stage {stage.name} timed out after 5 minutes",
                "error_type": "timeout",
                "stage_name": stage.name,
                "agent": stage.agent,
                "timestamp": now_us()
            }
            
        except Exception as e:
            # Agent execution error - record as error but continue
            return {
                "error": f"Agent execution failed: {str(e)}",
                "error_type": "agent_error",
                "stage_name": stage.name,
                "agent": stage.agent,
                "timestamp": now_us(),
                "error_details": {
                    "exception_type": type(e).__name__,
                    "exception_message": str(e)
                }
            }
    
    def _determine_final_status(self, execution_stats: Dict) -> str:
        """Determine final session status based on execution results."""
        if execution_stats["failed_stages"] == 0:
            return "completed"  # All stages successful
        elif execution_stats["completed_stages"] > 0:
            return "completed_with_errors"  # Some stages successful, some failed
        else:
            return "failed"  # All stages failed
    
    def _generate_final_analysis(self, accumulated_data: AccumulatedAlertData, execution_stats: Dict) -> str:
        """Generate final analysis from all stage results, including errors."""
        analysis_parts = []
        
        # Summary
        analysis_parts.append(f"Chain Execution Summary:")
        analysis_parts.append(f"- Total stages: {execution_stats['total_stages']}")
        analysis_parts.append(f"- Successful: {execution_stats['completed_stages']}")
        analysis_parts.append(f"- Failed: {execution_stats['failed_stages']}")
        analysis_parts.append("")
        
        # Stage-by-stage results
        analysis_parts.append("Stage Results:")
        for stage_name, stage_result in accumulated_data.stage_outputs.items():
            if stage_result.get("error"):
                analysis_parts.append(f"❌ {stage_name}: {stage_result['error']}")
            else:
                # Extract key insights from successful stages
                if "analysis" in stage_result:
                    analysis_parts.append(f"✅ {stage_name}: {stage_result['analysis'][:200]}...")
                else:
                    analysis_parts.append(f"✅ {stage_name}: Completed successfully")
        
        return "\n".join(analysis_parts)
```

### Database Error Handling

**StageExecution Status Values:**
- `active` - Stage currently executing
- `completed` - Stage finished (may contain errors in stage_output)
- `failed` - Stage had fatal error (couldn't execute)
- `skipped` - Stage skipped due to dependencies

**Error Recording in Database:**
```python
# Errors are stored as part of stage_output JSON field
stage_output_with_error = {
    "error": "Agent execution failed: Connection timeout",
    "error_type": "agent_error", 
    "stage_name": "data-collection",
    "timestamp": 1734567890123456,
    "error_details": {
        "exception_type": "ConnectionTimeout",
        "exception_message": "Could not connect to MCP server"
    }
}

# Stage is marked as "completed" but contains error information
# This allows dashboard to show stage as executed but with errors
```

### Dashboard Error Visualization

**Enhanced StageExecution Model for Dashboard:**
```python
class StageExecution(BaseModel):
    stage_id: str
    status: str  # "completed", "failed", "active", "skipped"
    stage_output: Optional[Dict[str, Any]]
    error_message: Optional[str]
    
    def has_errors(self) -> bool:
        """Check if stage completed with errors."""
        return (
            self.stage_output and 
            self.stage_output.get("error") is not None
        )
    
    def get_error_summary(self) -> Optional[str]:
        """Get human-readable error summary for dashboard."""
        if self.error_message:
            return self.error_message  # Fatal errors
        elif self.stage_output and self.stage_output.get("error"):
            return self.stage_output["error"]  # Execution errors
        return None
```

**Dashboard Chain Visualization with Errors:**
```python
# Dashboard shows chain progress with error indicators
{
  "chain": {
    "id": "security-investigation-chain",
    "nodes": [
      {"id": "data-collection", "agent": "DataAgent", "status": "completed", "has_errors": true},
      {"id": "analysis", "agent": "AnalysisAgent", "status": "completed", "has_errors": false},
      {"id": "remediation", "agent": "RemediationAgent", "status": "failed", "has_errors": true}
    ]
  },
  "stage_executions": [
    {
      "stage_id": "data-collection",
      "status": "completed",
      "stage_output": {
        "data": {...},
        "error": "Partial timeout on metrics collection",
        "error_type": "timeout"
      }
    }
  ]
}
```

### Benefits of This Error Handling Strategy

✅ **Full Observability**: All errors recorded and visible in dashboard
✅ **Graceful Degradation**: Chain continues even with stage failures  
✅ **Partial Results**: Always get value from successful stages
✅ **Rich Error Context**: Detailed error information for debugging
✅ **Historical Tracking**: All execution attempts preserved in database
✅ **Dashboard Integration**: Errors visualized alongside successful results

---

## Progress Reporting and Dashboard Visualization

### Simplified Progress Reporting Strategy

**Core Principles:**
1. **No Migration**: Switch directly to new WebSocket format - no backward compatibility needed
2. **No Progress Scale**: Remove 0-100 progress, show stage-by-stage progress instead  
3. **Real-time Updates**: Send WebSocket messages at key execution points
4. **Dashboard Focus**: Rich visualization in dashboard, simple progress in dev UI

### Enhanced WebSocket Message Format

**New AlertStatusUpdate (Breaking Change):**
```python
class AlertStatusUpdate(WebSocketMessage):
    """Enhanced progress update with stage-level context."""
    alert_id: str
    status: str  # "processing", "completed", "failed"
    current_step: str  # Human-readable current activity
    
    # NEW: Chain context (replaces progress: int field)
    chain_id: Optional[str] = None
    current_stage: Optional[str] = None  # Currently executing stage
    total_stages: Optional[int] = None
    completed_stages: Optional[int] = None
    
    # NEW: Stage-level progress details (for dashboard rich visualization)
    stage_progress: Optional[List[Dict[str, Any]]] = None  # All stage statuses
    
    # Existing fields (preserved)
    current_agent: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None
    
    # REMOVED: assigned_mcp_servers (not used in dashboard, not needed for dev UI)
```

**Progress Update Timing:**
```python
class ChainOrchestrator:
    async def execute_chain(self, chain_def, alert_data, progress_callback):
        # 1. Chain Start
        await self._send_progress_update("processing", "Starting chain execution", {
            "chain_id": chain_def.chain_id,
            "total_stages": len(chain_def.stages),
            "completed_stages": 0,
            "current_stage": None,
            "stage_progress": [
                {"stage": stage.name, "agent": stage.agent, "status": "pending"} 
                for stage in chain_def.stages
            ]
        })
        
        for i, stage in enumerate(chain_def.stages):
            # 2. Stage Start  
            await self._send_progress_update("processing", f"Starting {stage.name}", {
                "chain_id": chain_def.chain_id,
                "current_stage": stage.name,
                "current_agent": stage.agent,
                "completed_stages": i,
                "stage_progress": self._build_stage_progress_snapshot(chain_def, i, "active")
            })
            
            # Execute stage...
            result = await self._execute_stage(stage, accumulated_data)
            
            # 3. Stage Complete
            await self._send_progress_update("processing", f"Completed {stage.name}", {
                "chain_id": chain_def.chain_id,
                "completed_stages": i + 1,
                "stage_progress": self._build_stage_progress_snapshot(chain_def, i, "completed")
            })
        
        # 4. Chain Complete
        await self._send_progress_update("completed", "Chain execution finished", {
            "chain_id": chain_def.chain_id,
            "completed_stages": len(chain_def.stages),
            "current_stage": None
        })
    
    def _build_stage_progress_snapshot(self, chain_def, current_index, current_status):
        """Build current stage progress snapshot for WebSocket."""
        progress = []
        for i, stage in enumerate(chain_def.stages):
            if i < current_index:
                status = "completed"
            elif i == current_index:
                status = current_status  # "active", "completed", "failed"
            else:
                status = "pending"
            
            progress.append({
                "stage": stage.name,
                "agent": stage.agent,
                "status": status
            })
        return progress
```

### Dashboard Visualization - Vertical Card Stack

**Enhanced ActiveAlertCard with Chain Progress:**
```typescript
// dashboard/src/components/ActiveAlertCard.tsx - Enhanced for chains

interface ChainProgressProps {
  chainId: string;
  currentStage: string | null;
  stageProgress: StageProgressItem[];
  totalStages: number;
  completedStages: number;
}

interface StageProgressItem {
  stage: string;
  agent: string;
  status: 'pending' | 'active' | 'completed' | 'failed';
  duration?: number;
  error?: string;
}

const ChainProgressDisplay: React.FC<ChainProgressProps> = ({
  chainId,
  currentStage,
  stageProgress,
  totalStages,
  completedStages
}) => {
  return (
    <Box sx={{ mt: 2 }}>
      {/* Chain Header */}
      <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
        🔗 {chainId}
      </Typography>
      
      {/* Stage Cards - Vertical Stack */}
      <Stack spacing={1}>
        {stageProgress.map((stage, index) => (
          <Card 
            key={stage.stage}
            variant="outlined" 
            sx={{ 
              borderLeft: 4,
              borderLeftColor: getStageStatusColor(stage.status),
              backgroundColor: stage.status === 'active' ? 'action.hover' : 'background.paper'
            }}
          >
            <CardContent sx={{ py: 1.5, px: 2, '&:last-child': { pb: 1.5 } }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  {/* Status Icon */}
                  {getStageStatusIcon(stage.status)}
                  
                  {/* Stage Info */}
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      {stage.stage}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Agent: {stage.agent}
                    </Typography>
                  </Box>
                </Box>
                
                {/* Stage Status */}
                <Box sx={{ textAlign: 'right' }}>
                  {stage.status === 'completed' && stage.duration && (
                    <Typography variant="caption" color="text.secondary">
                      {formatDurationMs(stage.duration)}
                    </Typography>
                  )}
                  {stage.status === 'active' && (
                    <Typography variant="caption" color="primary.main">
                      Running...
                    </Typography>
                  )}
                  {stage.status === 'failed' && stage.error && (
                    <Tooltip title={stage.error}>
                      <Typography variant="caption" color="error.main">
                        Error
                      </Typography>
                    </Tooltip>
                  )}
                  {stage.status === 'pending' && (
                    <Typography variant="caption" color="text.disabled">
                      Pending
                    </Typography>
                  )}
                </Box>
              </Box>
              
              {/* Error Details (if failed) */}
              {stage.status === 'failed' && stage.error && (
                <Alert severity="error" sx={{ mt: 1, py: 0.5 }}>
                  <Typography variant="caption">
                    {stage.error}
                  </Typography>
                </Alert>
              )}
            </CardContent>
          </Card>
        ))}
      </Stack>
      
      {/* Chain Summary */}
      <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
        Progress: {completedStages} of {totalStages} stages completed
        {currentStage && ` • Currently: ${currentStage}`}
      </Typography>
    </Box>
  );
};

// Helper functions
const getStageStatusColor = (status: string) => {
  switch (status) {
    case 'completed': return 'success.main';
    case 'active': return 'primary.main';
    case 'failed': return 'error.main';
    case 'pending': return 'grey.300';
    default: return 'grey.300';
  }
};

const getStageStatusIcon = (status: string) => {
  switch (status) {
    case 'completed': return <CheckCircle sx={{ fontSize: 16, color: 'success.main' }} />;
    case 'active': return <PlayCircleFilled sx={{ fontSize: 16, color: 'primary.main' }} />;
    case 'failed': return <Error sx={{ fontSize: 16, color: 'error.main' }} />;
    case 'pending': return <Schedule sx={{ fontSize: 16, color: 'text.disabled' }} />;
    default: return <Circle sx={{ fontSize: 16, color: 'text.disabled' }} />;
  }
};
```

**Session Detail Page Enhancement:**
```typescript
// dashboard/src/components/SessionDetailPage.tsx - Enhanced for chain visualization

const ChainExecutionTimeline: React.FC<{ session: SessionDetail }> = ({ session }) => {
  return (
    <Paper sx={{ p: 3, mb: 3 }}>
      <Typography variant="h6" gutterBottom>
        Chain Execution Timeline
      </Typography>
      
      {/* Chain Header */}
      <Box sx={{ mb: 3, p: 2, bgcolor: 'background.default', borderRadius: 1 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          🔗 {session.chain?.id}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Started: {formatTimestamp(session.started_at_us)} | 
          Duration: {formatDuration(session.started_at_us, session.completed_at_us)} |
          Status: {session.status}
        </Typography>
      </Box>
      
      {/* Stage Execution Details - Vertical Cards */}
      <Stack spacing={2}>
        {session.stage_executions?.map((stageExec, index) => (
          <Card 
            key={stageExec.stage_id}
            variant="outlined"
            sx={{ 
              borderLeft: 4,
              borderLeftColor: getStageStatusColor(stageExec.status)
            }}
          >
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  {getStageStatusIcon(stageExec.status)}
                  <Typography variant="h6">
                    Stage {index + 1}: {stageExec.stage_id}
                  </Typography>
                </Box>
                <Chip 
                  label={stageExec.status} 
                  color={getStageStatusChipColor(stageExec.status)}
                  size="small"
                />
              </Box>
              
              {/* Stage Metadata */}
              <Grid container spacing={2} sx={{ mb: 2 }}>
                <Grid item xs={12} sm={6}>
                  <Typography variant="body2" color="text.secondary">
                    <strong>Agent:</strong> {stageExec.agent}
                  </Typography>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="body2" color="text.secondary">
                    <strong>Duration:</strong> {stageExec.duration_ms ? formatDurationMs(stageExec.duration_ms) : '-'}
                  </Typography>
                </Grid>
                {stageExec.started_at_us && (
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" color="text.secondary">
                      <strong>Started:</strong> {formatTimestamp(stageExec.started_at_us)}
                    </Typography>
                  </Grid>
                )}
                {stageExec.llm_interaction_count && (
                  <Grid item xs={12} sm={6}>
                    <Typography variant="body2" color="text.secondary">
                      <strong>LLM Calls:</strong> {stageExec.llm_interaction_count}
                    </Typography>
                  </Grid>
                )}
              </Grid>
              
              {/* Stage Output */}
              {stageExec.stage_output && (
                <Accordion sx={{ mt: 2 }}>
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Typography variant="subtitle2">
                      Stage Output {stageExec.stage_output.error ? '(With Errors)' : ''}
                    </Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <JsonDisplay data={stageExec.stage_output} />
                  </AccordionDetails>
                </Accordion>
              )}
              
              {/* Error Handling */}
              {stageExec.error_message && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  <Typography variant="body2">
                    <strong>Stage Error:</strong> {stageExec.error_message}
                  </Typography>
                </Alert>
              )}
            </CardContent>
          </Card>
        ))}
      </Stack>
    </Paper>
  );
};
```

### Phase 2/3 Extensibility 

**Scales perfectly for future phases:**

**Phase 2 - Parallel Stages:**
```typescript
// Parallel stages shown as side-by-side cards within the same stage slot
<Card>
  <CardContent>
    <Typography variant="h6">Stage 2: Data Gathering (Parallel)</Typography>
    <Grid container spacing={1} sx={{ mt: 1 }}>
      <Grid item xs={4}>
        <Card variant="outlined" sx={{ borderLeft: 4, borderLeftColor: 'success.main' }}>
          <CardContent sx={{ py: 1 }}>
            <Typography variant="body2">✅ Logs Agent</Typography>
            <Typography variant="caption">2.1s</Typography>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={4}>
        <Card variant="outlined" sx={{ borderLeft: 4, borderLeftColor: 'primary.main' }}>
          <CardContent sx={{ py: 1 }}>
            <Typography variant="body2">🔄 Metrics Agent</Typography>
            <Typography variant="caption">Running...</Typography>
          </CardContent>
        </Card>
      </Grid>
      <Grid item xs={4}>
        <Card variant="outlined" sx={{ borderLeft: 4, borderLeftColor: 'grey.300' }}>
          <CardContent sx={{ py: 1 }}>
            <Typography variant="body2">⏳ Events Agent</Typography>
            <Typography variant="caption">Pending</Typography>
          </CardContent>
        </Card>
      </Grid>
    </Grid>
  </CardContent>
</Card>
```

**Phase 3 - Conditional Routing:**
```typescript
// Conditional stages shown with branching indicators
<Card>
  <CardContent>
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <AccountTree sx={{ color: 'warning.main' }} />
      <Typography variant="h6">Stage 3: Threat Assessment (Conditional)</Typography>
    </Box>
    <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
      Route taken: High-severity path → Security escalation
    </Typography>
    <Typography variant="body2" color="text.disabled">
      Skipped: Low-severity path → Automated remediation
    </Typography>
  </CardContent>
</Card>
```

### Simplified Dev UI (alert-dev-ui)

**Clean Two-Page Design:**
1. **Page 1**: Alert submission form (unchanged)
2. **Page 2**: Generic progress + final result

**Dev UI Progress Display:**
```typescript
// alert-dev-ui/src/components/ProcessingStatus.tsx - Simplified

interface SimpleProgressProps {
  alertId: string;
  status: string;
  currentStep: string;
  result?: string;
  error?: string;
}

const SimpleProgress: React.FC<SimpleProgressProps> = ({
  status,
  currentStep,
  result,
  error
}) => {
  return (
    <div className="processing-status">
      <h2>Processing Alert...</h2>
      
      {/* Generic Progress Indicator */}
      {status === 'processing' && (
        <div className="progress">
          <div className="spinner"></div>
          <p>{currentStep}</p>
        </div>
      )}
      
      {/* Final Result */}
      {status === 'completed' && result && (
        <div className="result">
          <h3>✅ Processing Complete</h3>
          <pre>{result}</pre>
        </div>
      )}
      
      {/* Error State */}
      {status === 'failed' && error && (
        <div className="error">
          <h3>❌ Processing Failed</h3>
          <p>{error}</p>
        </div>
      )}
    </div>
  );
};
```

**Dev UI WebSocket Handling:**
```typescript
// alert-dev-ui - Simple WebSocket message handling
const handleProgressUpdate = (update: AlertStatusUpdate) => {
  // Ignore rich chain data - just use simple fields
  setStatus(update.status);
  setCurrentStep(update.current_step);
  setResult(update.result);
  setError(update.error);
  
  // Don't use: chain_id, stage_progress, etc. - dashboard only
};
```

**Benefits:**
✅ **Minimal Complexity**: No progress scales, no stage visualization
✅ **Clean UX**: Just "working..." → "done" or "failed"  
✅ **Future-Proof**: Ignores rich chain data, focuses on essentials
✅ **Easy Maintenance**: Simple two-page flow

### Complete Design Benefits

This design provides:
✅ **Real-time Progress**: Immediate WebSocket updates at each stage transition
✅ **Rich Visualization**: Vertical card stack perfect for current dashboard layout  
✅ **Future-Proof**: Seamlessly extends to parallel and conditional execution
✅ **No Migration**: Clean break to new format, dashboard updated accordingly
✅ **Scalable**: Handles 2 stages or 20 stages equally well
✅ **Clean Architecture**: Sophisticated dashboard, simple dev UI

---

## Implementation Design

### Core Logic Flow
1. **Alert Reception**: AlertService receives alert and looks up chain definition (single agents are 1-stage chains)
2. **Chain Lookup**: ChainRegistry returns chain definition for alert type (always returns a chain, even for single agents)
3. **Unified Execution**: ChainOrchestrator executes all processing through unified chain execution path
4. **Stage Execution**: Each stage (including single-agent "chains") runs with consistent orchestration
5. **Progress Reporting**: WebSocket updates sent for each stage start/completion (unified for single and multi-stage)
6. **Result Aggregation**: Final result processing identical for single-stage and multi-stage executions
7. **History Storage**: All executions stored with consistent stage-level detail format

**Phase 1 Chain Execution Flow (Graceful Error Handling):**
See the complete implementation in the "Error Handling Strategy" section above, which includes:
- **Graceful Degradation**: Stage failures don't stop chain execution - continue to next stage
- **Full Recording**: All errors recorded as stage outputs for history/dashboard visibility  
- **Database-Driven**: All execution state persisted using AlertSession and StageExecution tables
- **Progress Reporting**: Real-time WebSocket updates with stage-level context
- **Accumulated Data Flow**: Each stage receives original alert + runbook + all previous stage outputs

### Security Design
- **Agent-Level Security**: Each stage respects individual agent's MCP server access and data masking configuration
- **Chain Validation**: Chain configurations validated at startup to ensure all referenced agents exist and are properly configured
- **Data Flow Security**: Enriched data passed between stages follows same security model as single-agent processing
- **Access Control**: Chain execution uses same authentication/authorization as single-agent processing

### Performance Considerations
- **Database-Driven**: All state persisted in database - no in-memory state management complexity
- **Simple & Reliable**: Survives service restarts, easy debugging, full audit trail
- **Adequate Performance**: For ~10 concurrent alerts with 2-5 stage chains, database I/O is negligible
- **Linear Scaling**: Processing time scales linearly with chain length (as expected)

**ChainOrchestrator Implementation:**
The complete implementation with graceful error handling is provided in the "Error Handling Strategy" section above (lines 1465-1697). Key features:
- **Graceful Error Handling**: Stage failures don't stop execution, errors are recorded and chain continues
- **Database-Driven State**: Full persistence using AlertSession and StageExecution tables  
- **Accumulated Data Flow**: Each stage receives original alert + runbook + all previous stage outputs
- **Progress Reporting**: Real-time WebSocket updates with stage-level context
- **Full Observability**: All errors recorded as stage outputs for history/dashboard visibility

---

## File Structure

### Files to Create
```
backend/tarsy/
  services/
    chain_registry.py          # Registry for built-in and configurable chains
    chain_orchestrator.py      # Sequential chain execution engine
  models/
    chain_models.py           # Pydantic models for chains (no execution state - database-driven)
```

### Files to Modify
- `backend/tarsy/agents/base_agent.py`: **CRITICAL CHANGE** - Update BaseAgent interface for accumulated alert data structure (see BaseAgent Interface section below)
- `backend/tarsy/agents/prompt_builder.py`: **CRITICAL CHANGE** - Update PromptContext and methods for accumulated alert data structure (see BaseAgent Interface section below)
- `backend/tarsy/agents/kubernetes_agent.py`: Update implementation for new BaseAgent interface
- `backend/tarsy/agents/configurable_agent.py`: Update implementation for new BaseAgent interface
- `backend/tarsy/config/builtin_config.py`: Add built-in chain definitions (single source of truth, no separate mappings)
- `backend/tarsy/config/agent_config.py`: **CRITICAL CHANGE** - Extend ConfigurationLoader for agent_chains section (see Configuration Loading section below)
- `backend/tarsy/services/alert_service.py`: Simplify to use unified ChainRegistry lookup for all processing
- `backend/tarsy/services/history_service.py`: Enhance for stage-level detail storage
- `backend/tarsy/services/websocket_manager.py`: Enhance progress reporting for unified stage-based processing
- `backend/tarsy/models/api_models.py`: Add optional chain metadata fields to existing response models
- `backend/tarsy/main.py`: Add optional chain-specific endpoints and query parameters
- `dashboard/src/types/index.ts`: Add chain execution types for UI
- `dashboard/src/components/`: Enhance progress and history components for unified stage visualization

### Files to Replace/Delete
- `backend/tarsy/services/agent_registry.py`: Delete entirely - replaced by ChainRegistry
- Remove `BUILTIN_AGENT_MAPPINGS` from `backend/tarsy/config/builtin_config.py` - replaced by BUILTIN_CHAIN_DEFINITIONS

---

## Implementation Guidance

### Key Design Decisions
- **Unified Processing Model**: Single agents are treated as 1-stage chains, eliminating dual execution paths and simplifying the entire system architecture
- **Orchestration Layer Approach**: Chain execution is implemented as an orchestration layer that coordinates existing agents rather than modifying agent internals - preserves existing agent architecture
- **Accumulated Data Model**: Each stage receives full history (original alert + runbook + all previous stage outputs) and adds its own output to the accumulated data - enables sophisticated workflows with full context

### Implementation Priority (Simplified for Phase 1)
**Phase 1 Focus: Get Sequential Chains Working**
1. **Core Models**: Create AccumulatedAlertData and ChainDefinitionModel in chain_models.py
2. **BaseAgent Interface Update**: Update BaseAgent.process_alert() to use AccumulatedAlertData type
3. **Prompt Builder Rewrite**: Update PromptContext and PromptBuilder for accumulated data structure
4. **Agent Implementations**: Update KubernetesAgent and ConfigurableAgent for new interface
5. **Database Schema**: Enhanced AlertSession + new StageExecution table (fresh DB - no migration)
6. **ChainRegistry**: Basic chain lookup that treats single agents as 1-stage chains
7. **ChainOrchestrator**: Database-driven sequential execution with full persistence
8. **AlertService Integration**: Replace AgentRegistry lookup with ChainRegistry lookup
9. **Basic Progress Reporting**: Stage-level WebSocket updates using database state

**Implementation Scope:**
- Sequential execution only (Agent A → Agent B → Agent C)
- Accumulated data flow (each stage gets original alert + runbook + all previous stage outputs)
- Single agent per stage (no parallel execution)
- Built-in chains (code) + YAML chains (configuration)

**Implementation Requirements:**
- **Unified Path**: All alerts go through ChainOrchestrator (single agents = 1-stage chains)
- **Data Enrichment**: Each stage passes enriched alert data to the next stage
- **Sequential Only**: Implement only sequential execution, no parallel/conditional logic