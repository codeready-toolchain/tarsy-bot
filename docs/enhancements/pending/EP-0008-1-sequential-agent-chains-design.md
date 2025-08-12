# EP-0008-1: Sequential Agent Chains - Design Document

**Status:** Draft  
**Created:** 2025-08-11  
**Requirements:** Multi-stage alert processing workflows  

---

## Overview

This enhancement introduces sequential agent chains to enable multi-stage alert processing workflows. Rather than single-agent analysis, alerts can flow through multiple specialized agents that build upon each other's work.

**Key Principles**: 
- Clean, simple implementation without backward compatibility concerns or legacy code preservation
- **Unified Type-Safe Models**: Enhanced `AlertProcessingData` serves as the single data model throughout the entire processing pipeline, eliminating `AccumulatedAlertData` and reducing data format mismatches
- **Progressive Data Enrichment**: The same model instance evolves through the pipeline: alert creation → runbook download → stage execution → final analysis

---

## Current Architecture Analysis

### Existing Components (To Build Upon)

**Agent Architecture:**
- `BaseAgent` abstract class with `process_alert(alert_data: AlertProcessingData, session_id: str)` interface
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
    iteration_strategy: Optional[str] = None  # Optional iteration strategy override (uses agent's default if not specified)

@dataclass
class ChainDefinitionModel:
    chain_id: str               # Unique chain identifier  
    alert_types: List[str]      # Alert types this chain handles
    stages: List[ChainStageModel]  # Sequential stages (1+ stages)
    description: Optional[str] = None
```

**Enhanced AlertProcessingData (Unified Chain Processing Model):**
```python
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
    
    def add_stage_result(self, stage_name: str, result: Dict[str, Any]):
        """Add results from a completed stage."""
        self.stage_outputs[stage_name] = result
    
    def set_runbook_content(self, content: str):
        """Set the downloaded runbook content."""
        self.runbook_content = content
    
    def set_chain_context(self, chain_id: str, current_stage: Optional[str] = None):
        """Set chain processing context."""
        self.chain_id = chain_id
        self.current_stage_name = current_stage
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
    stage_output: Optional[dict] = Field(sa_column=Column(JSON), description="Data produced by stage (only for successful completion)")
    error_message: Optional[str] = Field(description="Error message if stage failed (mutually exclusive with stage_output)")
    
    # Relationships
    session: AlertSession = Relationship(back_populates="stage_executions")
```

**Enhanced Interaction Models (Link to stages):**
```python
# Note: Existing LLMInteraction and MCPInteraction models are enhanced
# with stage_execution_id foreign key for chain traceability

class LLMInteraction(SQLModel, table=True):
    # ... existing fields ...
    
    # NEW: Link to stage execution (enables chain-aware hook processing)
    stage_execution_id: Optional[str] = Field(
        foreign_key="stage_executions.execution_id",
        description="Link to stage execution for chain context in hooks"
    )

class MCPInteraction(SQLModel, table=True):
    # ... existing fields ...
    
    # NEW: Link to stage execution (enables chain-aware hook processing)
    stage_execution_id: Optional[str] = Field(
        foreign_key="stage_executions.execution_id",
        description="Link to stage execution for chain context in hooks"
    )

# Hook system automatically uses stage_execution_id for enhanced progress tracking
# TypedHistoryHooks can group interactions by stage
# TypedDashboardHooks can show stage-specific progress
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
        
        # Validate chain_id uniqueness across built-in and YAML chains
        self._validate_chain_id_uniqueness()
        
        # Build unified alert type mappings (STRICT - no conflicts allowed)
        self.alert_type_mappings = self._build_alert_type_mappings()
    
    def _validate_chain_id_uniqueness(self):
        """Ensure chain_ids are unique across built-in and YAML chains."""
        builtin_ids = set(self.builtin_chains.keys())
        yaml_ids = set(self.yaml_chains.keys())
        
        conflicts = builtin_ids & yaml_ids
        if conflicts:
            conflict_list = sorted(conflicts)
            raise ValueError(
                f"Chain ID conflicts detected between built-in and YAML chains: {conflict_list}. "
                f"Each chain_id must be unique across all chain sources."
            )
        
        logger.info(f"Chain ID validation passed: {len(builtin_ids)} built-in, {len(yaml_ids)} YAML chains")
    
    def get_chain_for_alert_type(self, alert_type: str) -> ChainDefinitionModel:
        """Always returns a chain. Single agents become 1-stage chains."""
        chain_id = self.alert_type_mappings.get(alert_type)
        if not chain_id:
            available_types = sorted(self.alert_type_mappings.keys())
            raise ValueError(f"No chain found for alert type '{alert_type}'. Available: {', '.join(available_types)}")
        
        # Return chain from appropriate source (built-in or YAML)
        return self.builtin_chains.get(chain_id) or self.yaml_chains.get(chain_id)
```

**Chain Execution Logic (Integrated into AlertService):**
```python
# ChainOrchestrator merged into AlertService as private methods
# Eliminates unnecessary abstraction and simplifies initialization
```

### Updated BaseAgent Interface

**Enhanced BaseAgent.process_alert() Method:**
```python
class BaseAgent(ABC):
    async def process_alert(
        self,
        alert_data: AlertProcessingData,  # Unified alert processing model
        session_id: str
    ) -> Dict[str, Any]:
        """
        Process alert with unified alert processing model using configured iteration strategy.
        
        Args:
            alert_data: Unified alert processing model containing:
                       - alert_type, alert_data: Original alert information
                       - runbook_content: Downloaded runbook content
                       - stage_outputs: Results from previous chain stages (empty for single-stage)
            session_id: Session ID for timeline logging
        
        Returns:
            Dictionary containing analysis result and metadata
        """
        # Basic validation
        if not session_id:
            raise ValueError("session_id is required for alert processing")
        
        try:
            # Extract data using type-safe helper methods
            runbook_content = alert_data.get_runbook_content()
            original_alert = alert_data.get_original_alert_data()
            
            # Get accumulated MCP data from all previous stages
            initial_mcp_data = alert_data.get_all_mcp_results()
            
            # Log enriched data usage from previous stages
            if previous_data := alert_data.get_stage_result("data-collection"):
                logger.info("Using enriched data from data-collection stage")
                # MCP results are already merged via get_all_mcp_results()
            
            # Configure MCP client with agent-specific servers
            await self._configure_mcp_client()
            
            # Get available tools from assigned MCP servers
            available_tools = await self._get_available_tools(session_id)
            
            # Create iteration context for controller
            context = IterationContext(
                alert_data=original_alert,
                runbook_content=runbook_content,
                available_tools=available_tools,
                session_id=session_id,
                agent=self
            )
            
            # If we have initial MCP data from previous stages, add it to context
            if initial_mcp_data:
                context.initial_mcp_data = initial_mcp_data
            
            # Delegate to appropriate iteration controller
            analysis_result = await self._iteration_controller.execute_analysis_loop(context)
            
            return {
                "status": "success",
                "agent": self.__class__.__name__,
                "analysis": analysis_result,
                "strategy": self.iteration_strategy.value,
                "mcp_results": getattr(context, 'final_mcp_data', {}),
                "timestamp_us": now_us()
            }
            
        except AgentError as e:
            # Handle structured agent errors with recovery information
            logger.error(f"Agent processing failed with structured error: {e.to_dict()}", exc_info=True)
            
            return {
                "status": "error",
                "agent": self.__class__.__name__,
                "error": str(e),
                "error_details": e.to_dict(),
                "recoverable": e.recoverable,
                "timestamp_us": now_us()
            }
        except Exception as e:
            # Handle unexpected errors
            error_msg = f"Agent processing failed with unexpected error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            return {
                "status": "error",
                "agent": self.__class__.__name__,
                "error": error_msg,
                "recoverable": False,
                "timestamp_us": now_us()
            }
```

### Enhanced Iteration Controller Architecture

**New Iteration Controller Types:**
The chain architecture enables specialized iteration controllers for different stage purposes:

```python
class IterationStrategy(Enum):
    # Existing strategies
    REGULAR = "regular"
    REACT = "react"
    
    # NEW: Tool-focused strategies (data collection only)
    REACT_TOOLS = "react-tools"           # ReAct pattern, tools only, no analysis
    
    # NEW: Analysis-focused strategies  
    REACT_TOOLS_PARTIAL = "react-tools-partial"     # ReAct + tools + partial analysis
    REACT_FINAL_ANALYSIS = "react-final-analysis"   # ReAct final analysis only, no tools
```

**Strategy Behaviors:**

1. **Tool-Only Strategies** (`react-tools`):
   - Focus on ReAct-style data collection via MCP tools
   - No analysis output - just enriched MCP results
   - Pass accumulated data to next stage

2. **Partial Analysis Strategies** (`react-tools-partial`):
   - Collect data AND provide ReAct-style stage-specific analysis
   - Output includes both MCP results and analysis
   - Good for incremental insights

3. **Final Analysis Strategy** (`react-final-analysis`):
   - No tool calling - pure ReAct-style analysis
   - Gets full context from all previous stages
   - Produces comprehensive final analysis

**Example Chain Configurations:**

```yaml
# Multi-stage data collection + final analysis
kubernetes-deep-troubleshooting:
  alert_types: ["KubernetesCritical", "PodCrashLoop"] 
  stages:
    - name: "system-data-collection"
      agent: "ConfigurableAgent:k8s"                # K8s agent with k8s tools
      iteration_strategy: "react-tools"             # Data collection only
    - name: "log-analysis"  
      agent: "ConfigurableAgent:k8s-logs"           # K8s agent with logs specific tools
      iteration_strategy: "react-tools"             # More data collection
    - name: "final-diagnosis"
      agent: "ConfigurableAgent:k8s-analysis"       # Same k8s agent, analysis mode
      iteration_strategy: "react-final-analysis"    # Analysis with full context

# Mixed approach with incremental analysis
security-incident-investigation:
  alert_types: ["SecurityBreach"]
  stages:
    - name: "evidence-collection"
      agent: "ConfigurableAgent:security"           # Single security agent
      iteration_strategy: "react-tools-partial"     # Collect + partial analysis of collected data
    - name: "k8s-data-collection"
      agent: "ConfigurableAgent:k8s"                # K8s agent with k8s tools
      iteration_strategy: "react-tools-partial"     # Collect + partial analysis of collected data
    - name: "aws-data-collection"
      agent: "ConfigurableAgent:aws"                # AWS agent
      iteration_strategy: "react-tools-partial"     # More data + partial analysis of collected data
    - name: "final-report"
      agent: "ConfigurableAgent:security-analysis"  # Security agent, no tools, final analysis only
      iteration_strategy: "react-final-analysis"    # Comprehensive report
```

**Example Agent Configuration for New Strategies:**
```yaml
# agents.yaml - Hybrid approach: agents can define default strategy, stages can override
agents:
  k8s:
    mcp_servers: ["kubernetes-server"]
    # No iteration_strategy = uses system default (react)
    custom_instructions: "General Kubernetes expert. Adapts behavior based on stage requirements."

  k8s-logs:
    mcp_servers: ["logs-server"]
    iteration_strategy: "react-tools"    # Default: Optimized for data collection
    custom_instructions: "Kubernetes logs data collection expert. Focus on gathering comprehensive logs."

  k8s-analysis:
    # No mcp_servers
    iteration_strategy: "react-final-analysis" # Default: Optimized for final analysis
    custom_instructions: "Kubernetes analysis expert. Diagnose issues and provide recommendations."
```

**Strategy Resolution Hierarchy:**
1. **Stage Strategy** (highest priority): `stage.iteration_strategy` if specified
2. **Agent Default Strategy**: `agent.iteration_strategy` if defined  
3. **System Default**: `IterationStrategy.REACT` as fallback

### Integration Points

**Updated AlertService (Complete Integration):**
```python
class AlertService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.history_service = HistoryService()
        self.runbook_service = RunbookService()
        self.websocket_manager = WebSocketManager()
        
        # REPLACE: AgentRegistry with ChainRegistry
        config_loader = ConfigurationLoader(settings.agent_config_file) if settings.agent_config_file else None
        self.chain_registry = ChainRegistry(config_loader)
        
        # Initialize AgentFactory (needed for chain stage execution)
        self.agent_factory = AgentFactory(
            llm_client=None,  # Set in initialize()
            mcp_client=None,  # Set in initialize() 
            mcp_registry=None  # Set in initialize()
        )
        
        # Chain execution logic integrated directly into AlertService
        # No separate orchestrator needed - simplifies architecture
    
    async def initialize(self):
        """Initialize all services with their dependencies."""
        # Initialize LLM and MCP clients
        llm_client = LLMClient(self.settings)
        mcp_client = MCPClient()
        mcp_registry = MCPServerRegistry()
        
        # Configure agent factory
        self.agent_factory.llm_client = llm_client
        self.agent_factory.mcp_client = mcp_client
        self.agent_factory.mcp_registry = mcp_registry
        
        # Initialize services
        await self.history_service.initialize()
        await mcp_client.initialize()
    
    async def process_alert(self, alert_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main entry point - completely rewritten for chain processing."""
        
        # Create unified alert processing model
        alert_processing_data = AlertProcessingData(
            alert_type=alert_data.get("alert_type", "unknown"),
            alert_data=alert_data,
            runbook_url=alert_data.get("runbook")
        )
        
        alert_id = alert_data.get("alert_id", str(uuid.uuid4()))
        
        try:
            # Get chain for alert type (REPLACES agent selection)
            chain_def = self.chain_registry.get_chain_for_alert_type(alert_processing_data.alert_type)
            logger.info(f"Selected chain '{chain_def.chain_id}' for alert type '{alert_processing_data.alert_type}'")
            
            # Download runbook once per chain (not per stage)
            if runbook_url := alert_processing_data.get_runbook_url():
                runbook_content = await self.runbook_service.download_runbook(runbook_url)
                alert_processing_data.set_runbook_content(runbook_content)
            
            # Create history session with chain info
            session_id = await self._create_chain_session(alert_processing_data, chain_def)
            
            # Execute chain stages directly (UNIFIED PATH)
            # Progress tracking handled automatically via existing hook system
            result = await self._execute_chain_stages(
                chain_def=chain_def,
                alert_processing_data=alert_processing_data,
                session_id=session_id
            )
            
            # Update session as completed
            await self._complete_session(session_id, result)
            
            return {
                "alert_id": alert_id,
                "status": "success",
                "chain_id": chain_def.chain_id,
                "final_analysis": result.get("final_analysis"),
                "session_id": session_id
            }
            
        except Exception as e:
            # Handle chain execution errors
            error_msg = f"Chain execution failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            # Update session as failed if it exists
            if 'session_id' in locals():
                await self._fail_session(session_id, error_msg)
            
            return {
                "alert_id": alert_id,
                "status": "error",
                "error": error_msg
            }
    
    async def _create_chain_session(self, alert_data: AlertProcessingData, chain_def: ChainDefinitionModel) -> str:
        """Create history session with chain metadata."""
        session = AlertSession(
            alert_id=alert_data.alert_data.get("alert_id", str(uuid.uuid4())),
            alert_data=alert_data.alert_data,  # Store original alert data
            alert_type=alert_data.alert_type,
            agent_type=f"chain:{chain_def.chain_id}",  # Mark as chain execution
            status=AlertSessionStatus.PROCESSING,
            chain_id=chain_def.chain_id,
            chain_definition={  # Snapshot of chain definition
                "chain_id": chain_def.chain_id,
                "stages": [stage.__dict__ for stage in chain_def.stages],
                "description": chain_def.description
            },
            current_stage_index=0,
            current_stage_id=chain_def.stages[0].name if chain_def.stages else None
        )
        
        return await self.history_service.create_session(session)
    
    async def _execute_chain_stages(
        self, 
        chain_def: ChainDefinitionModel, 
        alert_processing_data: AlertProcessingData,
        session_id: str
    ) -> Dict[str, Any]:
        """Execute chain stages sequentially with accumulated data flow."""
        
        logger.info(f"Starting chain execution '{chain_def.chain_id}' with {len(chain_def.stages)} stages")
        
        # Set chain context for tracking
        alert_processing_data.set_chain_context(chain_def.chain_id)
        
        successful_stages = 0
        failed_stages = 0
        
        # Execute each stage sequentially
        for i, stage in enumerate(chain_def.stages):
            logger.info(f"Executing stage {i+1}/{len(chain_def.stages)}: '{stage.name}' with agent '{stage.agent}'")
            
            # Update session current stage
            await self._update_session_current_stage(session_id, i, stage.name)
            
            # Create stage execution record
            stage_exec = StageExecution(
                session_id=session_id,
                stage_id=stage.name,
                stage_index=i,
                agent=stage.agent,
                status="active",
                started_at_us=now_us()
            )
            execution_id = await self.history_service.create_stage_execution(stage_exec)
            
            try:
                # Get agent instance with stage-specific strategy
                agent = await self.agent_factory.get_agent(stage.agent, iteration_strategy=stage.iteration_strategy)
                
                # Update current stage context
                alert_processing_data.set_chain_context(chain_def.chain_id, stage.name)
                
                # Execute stage with unified alert model
                result = await agent.process_alert(alert_processing_data, session_id)
                
                # Validate stage result format
                if not isinstance(result, dict) or "status" not in result:
                    raise ValueError(f"Invalid stage result format from agent '{stage.agent}'")
                
                # Add stage result to unified alert model
                alert_processing_data.add_stage_result(stage.name, result)
                
                # Update stage execution as completed
                stage_exec.status = "completed"
                stage_exec.completed_at_us = now_us()
                stage_exec.duration_ms = (stage_exec.completed_at_us - stage_exec.started_at_us) // 1000
                stage_exec.stage_output = result  # Success: store result in JSON
                stage_exec.error_message = None   # Ensure error_message is None for success
                await self.history_service.update_stage_execution(stage_exec)
                
                successful_stages += 1
                logger.info(f"Stage '{stage.name}' completed successfully in {stage_exec.duration_ms}ms")
                
            except Exception as e:
                # Log the error with full context
                error_msg = f"Stage '{stage.name}' failed with agent '{stage.agent}': {str(e)}"
                logger.error(error_msg, exc_info=True)
                
                # Mark stage as failed
                stage_exec.status = "failed"
                stage_exec.completed_at_us = now_us()
                stage_exec.duration_ms = (stage_exec.completed_at_us - stage_exec.started_at_us) // 1000
                stage_exec.stage_output = None     # Failed: no output data
                stage_exec.error_message = str(e)  # Failed: store error message
                await self.history_service.update_stage_execution(stage_exec)
                
                # Add structured error as stage output for next stages
                error_result = {
                    "status": "error",
                    "error": str(e),
                    "stage_name": stage.name,
                    "agent": stage.agent,
                    "timestamp_us": now_us(),
                    "recoverable": True  # Next stages can still execute
                }
                alert_processing_data.add_stage_result(stage.name, error_result)
                
                failed_stages += 1
                
                # DECISION: Continue to next stage even if this one failed
                # This allows data collection stages to fail while analysis stages still run
                logger.warning(f"Continuing chain execution despite stage failure: {error_msg}")
        
        # AlertService doesn't generate analysis - that's the job of LLMs in analysis stages
        # Final analysis comes from the last stage that produces analysis
        final_analysis = self._extract_final_analysis_from_stages(alert_processing_data)
        
        # Determine overall chain status
        overall_status = "completed"
        if failed_stages == len(chain_def.stages):
            overall_status = "failed"  # All stages failed
        elif failed_stages > 0:
            overall_status = "partial"  # Some stages failed
        
        logger.info(f"Chain execution completed: {successful_stages} successful, {failed_stages} failed")
        
        return {
            "status": overall_status,
            "final_analysis": final_analysis,
            "chain_id": chain_def.chain_id,
            "successful_stages": successful_stages,
            "failed_stages": failed_stages,
            "total_stages": len(chain_def.stages),
            "accumulated_data": alert_processing_data  # Full context for downstream use
        }
    
    async def _update_session_current_stage(self, session_id: str, stage_index: int, stage_name: str):
        """Update the current stage information in the session."""
        await self.history_service.update_session_current_stage(
            session_id=session_id,
            current_stage_index=stage_index,
            current_stage_id=stage_name
        )
    
    def _extract_final_analysis_from_stages(self, alert_data: AlertProcessingData) -> str:
        """
        Extract final analysis from stages.
        
        Final analysis should come from LLM-based analysis stages.
        """
        # Look for analysis from the last successful stage (typically a final-analysis stage)
        for stage_name in reversed(list(alert_data.stage_outputs.keys())):
            stage_result = alert_data.stage_outputs[stage_name]
            if stage_result.get("status") == "success" and "analysis" in stage_result:
                return stage_result["analysis"]
        
        # Fallback: look for any analysis from any successful stage
        for stage_result in alert_data.stage_outputs.values():
            if stage_result.get("status") == "success" and "analysis" in stage_result:
                return stage_result["analysis"]
        
        # If no analysis found, return a simple summary (this should be rare)
        return f"Chain {alert_data.chain_id} completed with {len(alert_data.stage_outputs)} stages. Use accumulated_data for detailed results."
    
    async def _complete_session(self, session_id: str, result: Dict[str, Any]):
        """Mark session as completed with final analysis."""
        await self.history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.COMPLETED,
            final_analysis=result.get("final_analysis"),
            completed_at_us=now_us()
        )
    
    async def _fail_session(self, session_id: str, error_message: str):
        """Mark session as failed with error message."""
        await self.history_service.update_session_status(
            session_id=session_id,
            status=AlertSessionStatus.FAILED,
            error_message=error_message,
            completed_at_us=now_us()
        )
```

### Supporting Infrastructure Updates

**Enhanced AgentFactory (Support for ConfigurableAgent resolution):**
```python
class AgentFactory:
    def __init__(self, llm_client: LLMClient, mcp_client: MCPClient, mcp_registry: MCPServerRegistry):
        self.llm_client = llm_client
        self.mcp_client = mcp_client
        self.mcp_registry = mcp_registry
        self._agent_cache: Dict[str, BaseAgent] = {}
    
    async def get_agent(self, agent_identifier: str, iteration_strategy: Optional[str] = None) -> BaseAgent:
        """
        Get agent instance by identifier with optional strategy override.
        
        Args:
            agent_identifier: Either class name (e.g., "KubernetesAgent") 
                            or "ConfigurableAgent:agent-name" format
            iteration_strategy: Strategy to use for this stage (overrides agent default)
        
        Returns:
            Agent instance configured with appropriate strategy
        """
        # Create cache key including strategy for stage-specific caching
        cache_key = f"{agent_identifier}:{iteration_strategy or 'default'}"
        if cache_key in self._agent_cache:
            return self._agent_cache[cache_key]
        
        # Parse agent identifier
        if ":" in agent_identifier:
            # ConfigurableAgent format: "ConfigurableAgent:agent-name"
            agent_type, agent_name = agent_identifier.split(":", 1)
            if agent_type != "ConfigurableAgent":
                raise ValueError(f"Invalid agent identifier format: {agent_identifier}")
            
            # Load configurable agent configuration
            config_loader = ConfigurationLoader()  # Get from settings
            agent_config = config_loader.get_agent_config(agent_name)
            if not agent_config:
                raise ValueError(f"Configurable agent '{agent_name}' not found in configuration")
            
            # Create ConfigurableAgent with specific configuration and strategy
            strategy = IterationStrategy(iteration_strategy) if iteration_strategy else IterationStrategy.REACT
            agent = ConfigurableAgent(
                agent_name=agent_name,
                agent_config=agent_config,
                llm_client=self.llm_client,
                mcp_client=self.mcp_client,
                mcp_registry=self.mcp_registry,
                iteration_strategy=strategy
            )
        else:
            # Built-in agent class name with strategy
            agent_class = self._get_builtin_agent_class(agent_identifier)
            strategy = IterationStrategy(iteration_strategy) if iteration_strategy else IterationStrategy.REACT
            agent = agent_class(
                llm_client=self.llm_client,
                mcp_client=self.mcp_client,
                mcp_registry=self.mcp_registry,
                iteration_strategy=strategy
            )
        
        # Cache the agent instance with strategy-specific key
        self._agent_cache[cache_key] = agent
        return agent
    
    def _get_builtin_agent_class(self, class_name: str) -> Type[BaseAgent]:
        """Get built-in agent class by name."""
        builtin_agents = {
            "KubernetesAgent": KubernetesAgent,
            # Add other built-in agents here
        }
        
        if class_name not in builtin_agents:
            raise ValueError(f"Unknown built-in agent class: {class_name}")
        
        return builtin_agents[class_name]
```

**Enhanced HistoryService (Chain and stage support):**
```python
class HistoryService:
    # ... existing methods ...
    
    async def create_stage_execution(self, stage_execution: StageExecution) -> str:
        """Create a new stage execution record."""
        async with self.get_session() as session:
            session.add(stage_execution)
            await session.commit()
            await session.refresh(stage_execution)
            return stage_execution.execution_id
    
    async def update_stage_execution(self, stage_execution: StageExecution):
        """Update an existing stage execution record."""
        async with self.get_session() as session:
            await session.merge(stage_execution)
            await session.commit()
    
    async def update_session_current_stage(
        self, 
        session_id: str, 
        current_stage_index: int, 
        current_stage_id: str
    ):
        """Update the current stage information for a session."""
        async with self.get_session() as session:
            stmt = (
                update(AlertSession)
                .where(AlertSession.session_id == session_id)
                .values(
                    current_stage_index=current_stage_index,
                    current_stage_id=current_stage_id
                )
            )
            await session.execute(stmt)
            await session.commit()
    
    async def update_session_status(
        self,
        session_id: str,
        status: str,
        final_analysis: Optional[str] = None,
        error_message: Optional[str] = None,
        completed_at_us: Optional[int] = None
    ):
        """Update session status and completion information."""
        update_values = {"status": status}
        
        if final_analysis is not None:
            update_values["final_analysis"] = final_analysis
        if error_message is not None:
            update_values["error_message"] = error_message
        if completed_at_us is not None:
            update_values["completed_at_us"] = completed_at_us
        
        async with self.get_session() as session:
            stmt = (
                update(AlertSession)
                .where(AlertSession.session_id == session_id)
                .values(**update_values)
            )
            await session.execute(stmt)
            await session.commit()
    
    async def get_session_with_stages(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session with all stage execution details."""
        async with self.get_session() as session:
            # Get session
            stmt = select(AlertSession).where(AlertSession.session_id == session_id)
            result = await session.execute(stmt)
            alert_session = result.scalar_one_or_none()
            
            if not alert_session:
                return None
            
            # Get stage executions
            stmt = (
                select(StageExecution)
                .where(StageExecution.session_id == session_id)
                .order_by(StageExecution.stage_index)
            )
            result = await session.execute(stmt)
            stage_executions = result.scalars().all()
            
            return {
                "session": alert_session,
                "stages": [stage.dict() for stage in stage_executions]
            }
```

### Progress Reporting via Existing Hook System

**Chain Progress Tracking:**
The existing typed hook system automatically handles all progress reporting without requiring new progress callback mechanisms. Chain execution progress is tracked through:

1. **LLM Interaction Hooks**: Every agent LLM call within a stage triggers `TypedLLMDashboardHook`
2. **MCP Interaction Hooks**: Every MCP tool call within a stage triggers `TypedMCPDashboardHook`  
3. **Stage Execution Records**: Database records provide stage-level progress via `StageExecution` table
4. **Session Updates**: AlertSession current_stage tracking shows overall chain progress

**Enhanced WebSocket Messages (Existing Pattern):**
```python
# Existing AlertStatusUpdate gets enhanced with chain context
class AlertStatusUpdate(WebSocketMessage):
    alert_id: str
    status: str  # "processing", "completed", "failed"
    current_step: str  # Human-readable current activity
    
    # NEW: Chain context (backward compatible addition)
    chain_id: Optional[str] = None
    current_stage: Optional[str] = None  # Currently executing stage
    total_stages: Optional[int] = None
    completed_stages: Optional[int] = None
```

**Hook System Integration:**
- **No New Progress Callbacks**: Existing hooks provide all necessary WebSocket updates
- **Automatic Dashboard Updates**: TypedDashboardHooks broadcast stage progress
- **Database Logging**: TypedHistoryHooks log all interactions with stage_execution_id links
- **Error Handling**: Hook error recovery ensures dashboard updates even during stage failures

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

### Phase 1: Foundation Models and Database
1. **Data Models**: Enhance `AlertProcessingData`, create `ChainDefinitionModel`, `StageExecution` models
2. **Database Schema**: Add chain fields to `AlertSession`, create `StageExecution` table with migrations
3. **Iteration Controllers**: Implement new iteration strategies (`REACT_TOOLS`, `REACT_TOOLS_PARTIAL`, `REACT_FINAL_ANALYSIS`)

### Phase 2: Agent Infrastructure Updates
1. **BaseAgent Interface**: Update `process_alert()` method to use `AlertProcessingData` with stage context
2. **AgentFactory Enhancement**: Add strategy override support for stage-specific agent creation
3. **Agent Implementations**: Update `KubernetesAgent` and configurable agents for new interface
4. **HistoryService**: Add stage execution tracking methods

### Phase 3: Chain Registry and Execution
1. **ChainRegistry**: Replace `AgentRegistry` with chain-based lookup system
2. **Built-in Chain Definitions**: Replace `BUILTIN_AGENT_MAPPINGS` with `BUILTIN_CHAIN_DEFINITIONS`
3. **YAML Configuration**: Extend `ConfigurationLoader` for `agent_chains` section
4. **AlertService Integration**: Implement chain execution logic with stage-by-stage processing

### Phase 4: Monitoring and Dashboard
1. **Enhanced WebSocket Messages**: Add chain context and stage progress to existing hook system
2. **Dashboard Components**: Chain progress visualization with stage-by-stage cards
3. **History API**: Enhanced session detail endpoints with stage execution data

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