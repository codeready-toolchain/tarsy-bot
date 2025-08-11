# EP-0008-1: Sequential Agent Chains - Design Document

**Status:** Draft  
**Created:** 2025-01-11  
**Requirements:** Multi-stage alert processing workflows  

---

## Overview

This enhancement introduces sequential agent chains to enable multi-stage alert processing workflows. Rather than single-agent analysis, alerts can flow through multiple specialized agents that build upon each other's work.

**Key Principle**: Clean, simple implementation without backward compatibility concerns or legacy code preservation.

---

## Current Architecture Analysis

### Existing Components (To Build Upon)

**Agent Architecture:**
- `BaseAgent` abstract class with `process_alert(alert_data, runbook_content, session_id)` interface
- `KubernetesAgent` and configurable agents via YAML
- `AgentRegistry` maps alert types → agent class names
- Agent factory creates agents dynamically

**Data Models:**
- `AlertSession` tracks individual alert processing sessions
- `LLMInteraction` and `MCPInteraction` models for detailed timeline tracking
- Unified interactions with session_id foreign keys

**Processing Flow:**
- `AlertService` handles alert submission and orchestration
- `HistoryService` provides database operations and timeline reconstruction
- Real-time WebSocket updates for dashboard visualization

---

## Design Goals

### Core Objectives
1. **Sequential Processing**: Agent A → Agent B → Agent C with data accumulation
2. **Clean Implementation**: No legacy code, no backward compatibility constraints
3. **Unified Architecture**: All alerts processed through chains (single agents = 1-stage chains)
4. **Simple Configuration**: Built-in chains in code, YAML chains for customization

### Non-Goals (Explicit Scope Limitations)
- Parallel agent execution (future enhancement)
- Conditional routing between agents (future enhancement)
- Complex workflow orchestration (future enhancement)
- Backward compatibility with existing agent configurations

---

## Technical Design

### Core Data Models

**Chain Definition:**
```python
@dataclass
class ChainStageModel:
    name: str                    # Human-readable stage name
    agent: str                   # Agent identifier (class name or "ConfigurableAgent:agent-name")

@dataclass
class ChainDefinitionModel:
    chain_id: str               # Unique chain identifier  
    alert_types: List[str]      # Alert types this chain handles
    stages: List[ChainStageModel]  # Sequential stages (1+ stages)
    description: Optional[str] = None
```

**Accumulated Data Flow:**
```python
@dataclass
class AccumulatedAlertData:
    original_alert: Dict[str, Any]          # Original alert + runbook content
    stage_outputs: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # Previous stage results
    
    def get_runbook(self) -> str:
        return self.original_alert.get("runbook", "")
    
    def get_original_data(self) -> Dict[str, Any]:
        data = self.original_alert.copy()
        data.pop("runbook", None)  # Remove runbook for clean alert data
        return data
    
    def get_stage_result(self, stage_id: str) -> Optional[Dict[str, Any]]:
        return self.stage_outputs.get(stage_id)
```

### Enhanced Database Schema

**Enhanced AlertSession (Add chain tracking):**
```python
class AlertSession(SQLModel, table=True):
    # ... existing fields ...
    
    # NEW: Chain execution tracking
    chain_id: str = Field(description="Chain identifier for this execution")
    chain_definition: dict = Field(sa_column=Column(JSON), description="Complete chain definition snapshot")
    current_stage_index: Optional[int] = Field(description="Current stage position (0-based)")
    current_stage_id: Optional[str] = Field(description="Current stage identifier")
```

**New StageExecution Table:**
```python
class StageExecution(SQLModel, table=True):
    execution_id: str = Field(primary_key=True, default_factory=lambda: str(uuid.uuid4()))
    session_id: str = Field(foreign_key="alert_sessions.session_id", index=True)
    
    # Stage identification
    stage_id: str = Field(description="Stage identifier (e.g., 'initial-analysis')")
    stage_index: int = Field(description="Stage position in chain (0-based)")
    agent: str = Field(description="Agent used for this stage")
    
    # Execution tracking
    status: str = Field(description="pending|active|completed|failed")
    started_at_us: Optional[int] = Field(description="Stage start timestamp")
    completed_at_us: Optional[int] = Field(description="Stage completion timestamp")
    duration_ms: Optional[int] = Field(description="Stage execution duration")
    stage_output: Optional[dict] = Field(sa_column=Column(JSON), description="Data produced by stage")
    error_message: Optional[str] = Field(description="Error message if stage failed")
    
    # Relationships
    session: AlertSession = Relationship(back_populates="stage_executions")
```

**Enhanced Interaction Models (Link to stages):**
```python
class LLMInteraction(SQLModel, table=True):
    # ... existing fields ...
    
    # NEW: Link to stage execution
    stage_execution_id: Optional[str] = Field(
        foreign_key="stage_executions.execution_id",
        description="Link to stage execution for context"
    )
    stage_execution: Optional[StageExecution] = Relationship(back_populates="llm_interactions")

class MCPInteraction(SQLModel, table=True):
    # ... existing fields ...
    
    # NEW: Link to stage execution  
    stage_execution_id: Optional[str] = Field(
        foreign_key="stage_executions.execution_id",
        description="Link to stage execution for context"
    )
    stage_execution: Optional[StageExecution] = Relationship(back_populates="mcp_interactions")
```

### Configuration

**Built-in Chain Definitions (Replace BUILTIN_AGENT_MAPPINGS):**
```python
# backend/tarsy/config/builtin_config.py

# REMOVE: BUILTIN_AGENT_MAPPINGS
# ADD: Built-in chain definitions as single source of truth
BUILTIN_CHAIN_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    # Convert existing single-agent mappings to 1-stage chains
    "kubernetes-agent-chain": {
        "alert_types": ["kubernetes", "NamespaceTerminating"],
        "stages": [
            {"name": "analysis", "agent": "KubernetesAgent"}
        ],
        "description": "Single-stage Kubernetes analysis"
    },
    
    # Example multi-agent chain (future capability)
    "kubernetes-troubleshooting-chain": {
        "alert_types": ["KubernetesIssue", "PodFailure"],
        "stages": [
            {"name": "data-collection", "agent": "KubernetesAgent"},
            {"name": "root-cause-analysis", "agent": "KubernetesAgent"}
        ],
        "description": "Multi-stage Kubernetes troubleshooting workflow"
    }
}
```

**YAML Chain Configuration:**
```yaml
# config/agents.yaml
mcp_servers:
  kubernetes-server:
    # ... existing MCP server config ...

agents:
  # Agents become pure processing components (no alert_types)
  data-collector-agent:
    mcp_servers: ["kubernetes-server"]
    custom_instructions: "Collect comprehensive data for next stage. Do not analyze."
    
  analysis-agent:
    mcp_servers: ["kubernetes-server"] 
    custom_instructions: "Analyze data from previous stage and provide recommendations."

agent_chains:
  # NEW: Chain definitions map alert types to workflows
  security-incident-chain:
    alert_types: ["SecurityBreach"]
    stages:  # YAML order preserved for execution
      - name: "data-collection"        # Executes first
        agent: "data-collector-agent"
      - name: "analysis"               # Executes second with accumulated data
        agent: "analysis-agent"
    description: "Simple 2-stage security workflow"
```

### Core Implementation Components

**ChainRegistry (Replace AgentRegistry):**
```python
class ChainRegistry:
    def __init__(self, config_loader: Optional[ConfigurationLoader] = None):
        # Load built-in chains (always available)
        self.builtin_chains = self._load_builtin_chains()
        
        # Load YAML chains (if configuration provided)
        self.yaml_chains = self._load_yaml_chains(config_loader) if config_loader else {}
        
        # Build unified alert type mappings (STRICT - no conflicts allowed)
        self.alert_type_mappings = self._build_alert_type_mappings()
    
    def get_chain_for_alert_type(self, alert_type: str) -> ChainDefinitionModel:
        """Always returns a chain. Single agents become 1-stage chains."""
        chain_id = self.alert_type_mappings.get(alert_type)
        if not chain_id:
            available_types = sorted(self.alert_type_mappings.keys())
            raise ValueError(f"No chain found for alert type '{alert_type}'. Available: {', '.join(available_types)}")
        
        # Return chain from appropriate source (built-in or YAML)
        return self.builtin_chains.get(chain_id) or self.yaml_chains.get(chain_id)
```

**ChainOrchestrator (Sequential Execution Engine):**
```python
class ChainOrchestrator:
    def __init__(self, agent_factory: AgentFactory, history_service: HistoryService):
        self.agent_factory = agent_factory
        self.history_service = history_service
    
    async def execute_chain(
        self, 
        chain_def: ChainDefinitionModel, 
        alert_data: Dict[str, Any],
        runbook_content: str,
        session_id: str
    ) -> Dict[str, Any]:
        """Execute stages sequentially with accumulated data flow."""
        
        # Start with original alert data + runbook
        accumulated_data = AccumulatedAlertData(
            original_alert={**alert_data, "runbook": runbook_content},
            stage_outputs={}
        )
        
        # Execute each stage sequentially
        for i, stage in enumerate(chain_def.stages):
            # Create stage execution record
            stage_exec = StageExecution(
                session_id=session_id,
                stage_id=stage.name,
                stage_index=i,
                agent=stage.agent,
                status="active",
                started_at_us=now_us()
            )
            await self.history_service.create_stage_execution(stage_exec)
            
            try:
                # Execute stage with accumulated data
                agent = await self.agent_factory.get_agent(stage.agent)
                result = await agent.process_alert(accumulated_data, session_id)
                
                # Add stage result to accumulated data
                accumulated_data.stage_outputs[stage.name] = result
                
                # Update stage execution as completed
                stage_exec.status = "completed"
                stage_exec.completed_at_us = now_us()
                stage_exec.duration_ms = (stage_exec.completed_at_us - stage_exec.started_at_us) // 1000
                stage_exec.stage_output = result
                await self.history_service.update_stage_execution(stage_exec)
                
            except Exception as e:
                # Mark stage as failed but continue to next stage
                stage_exec.status = "failed"
                stage_exec.completed_at_us = now_us()
                stage_exec.error_message = str(e)
                await self.history_service.update_stage_execution(stage_exec)
                
                # Add error as stage output for next stages
                accumulated_data.stage_outputs[stage.name] = {
                    "error": str(e),
                    "stage_name": stage.name,
                    "timestamp": now_us()
                }
        
        # Generate final analysis from all stage outputs
        final_analysis = self._generate_final_analysis(accumulated_data)
        
        return {
            "status": "completed",
            "final_analysis": final_analysis,
            "accumulated_data": accumulated_data,
            "chain_id": chain_def.chain_id
        }
```

### Updated BaseAgent Interface

**Enhanced BaseAgent.process_alert() Method:**
```python
class BaseAgent(ABC):
    async def process_alert(
        self,
        alert_data: AccumulatedAlertData,  # NEW: Typed accumulated data structure
        session_id: str
    ) -> Dict[str, Any]:
        """
        Process alert with accumulated data from chain execution.
        
        Args:
            alert_data: Accumulated data containing:
                       - original_alert: Original alert data + runbook content  
                       - stage_outputs: Results from previous stages (empty for single-stage)
            session_id: Session ID for timeline logging
        
        Returns:
            Dictionary containing analysis result and metadata
        """
        # Extract data using typed helper methods
        runbook_content = alert_data.get_runbook()
        original_alert = alert_data.get_original_data()
        
        # Check for data from previous stages (multi-stage chains)
        if previous_data := alert_data.get_stage_result("data-collection"):
            logger.info("Using enriched data from data-collection stage")
            # Use previous_data for enhanced analysis
        
        # Continue with existing agent logic...
        # All existing agent logic remains the same, just data access changes
```

### Integration Points

**Updated AlertService:**
```python
class AlertService:
    def __init__(self, settings: Settings):
        # ... existing initialization ...
        
        # REPLACE: AgentRegistry with ChainRegistry
        config_loader = ConfigurationLoader(settings.agent_config_file) if settings.agent_config_file else None
        self.chain_registry = ChainRegistry(config_loader)
        
        # NEW: Initialize ChainOrchestrator
        self.chain_orchestrator = ChainOrchestrator(
            agent_factory=None,  # Set in initialize()
            history_service=self.history_service
        )
    
    async def _process_alert_internal(self, alert: AlertProcessingData, progress_callback):
        """Unified alert processing through chains (single agents = 1-stage chains)."""
        
        # Get chain for alert type (REPLACES agent selection)
        try:
            chain_def = self.chain_registry.get_chain_for_alert_type(alert.alert_type)
            logger.info(f"Selected chain '{chain_def.chain_id}' for alert type '{alert.alert_type}'")
        except ValueError as e:
            return self._format_error_response(alert, str(e))
        
        # Download runbook (unchanged)
        runbook_content = await self.runbook_service.download_runbook(alert.runbook)
        
        # Create history session with chain info
        session_id = self._create_history_session(alert, chain_def.chain_id)
        
        # Execute through ChainOrchestrator (UNIFIED PATH)
        result = await self.chain_orchestrator.execute_chain(
            chain_def=chain_def,
            alert_data=alert.alert_data,
            runbook_content=runbook_content,
            session_id=session_id
        )
        
        return result.get("final_analysis", "Chain completed successfully")
```

### Progress Reporting and Dashboard

**Enhanced WebSocket Messages:**
```python
class AlertStatusUpdate(WebSocketMessage):
    alert_id: str
    status: str  # "processing", "completed", "failed"
    current_step: str  # Human-readable current activity
    
    # NEW: Chain context (replaces progress: int field)
    chain_id: Optional[str] = None
    current_stage: Optional[str] = None  # Currently executing stage
    total_stages: Optional[int] = None
    completed_stages: Optional[int] = None
    
    # NEW: Stage-level progress details (for dashboard)
    stage_progress: Optional[List[Dict[str, Any]]] = None  # All stage statuses
```

**Dashboard Chain Visualization:**
```typescript
// Vertical card stack showing stage-by-stage progress
interface StageProgressItem {
  stage: string;
  agent: string;
  status: 'pending' | 'active' | 'completed' | 'failed';
  duration?: number;
  error?: string;
}

const ChainProgressDisplay: React.FC = ({ chainId, stageProgress }) => {
  return (
    <Stack spacing={1}>
      {stageProgress.map((stage) => (
        <Card 
          key={stage.stage}
          sx={{ 
            borderLeft: 4,
            borderLeftColor: getStageStatusColor(stage.status)
          }}
        >
          <CardContent sx={{ py: 1.5 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {getStageStatusIcon(stage.status)}
              <Typography variant="body2">{stage.stage}</Typography>
              <Typography variant="caption" color="text.secondary">
                Agent: {stage.agent}
              </Typography>
            </Box>
          </CardContent>
        </Card>
      ))}
    </Stack>
  );
};
```

---

## Implementation Plan

### Phase 1: Core Chain Infrastructure
1. **Data Models**: Create `AccumulatedAlertData`, `ChainDefinitionModel`, `StageExecution` models
2. **Database Schema**: Add chain tracking to `AlertSession`, create `StageExecution` table
3. **ChainRegistry**: Replace `AgentRegistry` with chain-based lookup (single agents = 1-stage chains)
4. **ChainOrchestrator**: Sequential execution engine with database-driven state tracking

### Phase 2: Agent Interface Updates
1. **BaseAgent Interface**: Update `process_alert()` method to use `AccumulatedAlertData`
2. **Agent Implementations**: Update `KubernetesAgent` and configurable agents for new interface  
3. **Prompt Builder**: Update to handle accumulated data structure

### Phase 3: Configuration and Integration
1. **Built-in Chain Definitions**: Replace `BUILTIN_AGENT_MAPPINGS` with `BUILTIN_CHAIN_DEFINITIONS`
2. **YAML Configuration**: Extend `ConfigurationLoader` for `agent_chains` section
3. **AlertService Integration**: Update to use `ChainRegistry` and `ChainOrchestrator`

### Phase 4: Progress Reporting and Dashboard
1. **Enhanced WebSocket Messages**: Add chain context to progress updates
2. **Dashboard Components**: Chain progress visualization with stage-by-stage cards
3. **History API**: Enhanced session detail with stage execution data

---

## Benefits

### Immediate Value
- **Multi-Stage Workflows**: Enable sophisticated alert processing workflows
- **Data Accumulation**: Each stage builds upon previous stage results  
- **Unified Architecture**: Consistent processing path for single and multi-agent scenarios
- **Rich Observability**: Stage-level tracking and visualization

### Long-Term Benefits
- **Workflow Flexibility**: Easy to configure new multi-stage alert processing workflows
- **Specialized Agents**: Agents can focus on specific tasks (data collection vs analysis)
- **Extensible Design**: Framework ready for parallel execution and conditional routing
- **Operational Insights**: Detailed stage-level performance and error analysis

### Implementation Benefits
- **Clean Architecture**: No legacy code or backward compatibility constraints
- **Simple Configuration**: Built-in chains in code, YAML chains for customization
- **Database-Driven State**: Reliable execution state management with full audit trail
- **Graceful Error Handling**: Stage failures don't stop chain execution

---

## Constraints and Considerations

### Scope Limitations
- **Sequential Only**: No parallel agent execution in this phase
- **No Conditional Routing**: No branching logic between stages
- **Breaking Changes**: Agent interface changes require agent updates

### Performance Considerations
- **Database I/O**: Each stage creates database records (acceptable for ~10 concurrent alerts)
- **Linear Scaling**: Processing time scales linearly with chain length
- **Memory Usage**: Accumulated data grows with chain length

### Configuration Validation
- **Strict Conflict Detection**: No alert type can map to multiple chains
- **Agent Reference Validation**: All referenced agents must exist (built-in or configured)
- **Chain Structure Validation**: Chains must have valid stage definitions

---

This design provides a clean, simple foundation for sequential agent chains while maintaining the flexibility to extend to more sophisticated workflows in the future. The implementation prioritizes clarity and maintainability over complex orchestration features.