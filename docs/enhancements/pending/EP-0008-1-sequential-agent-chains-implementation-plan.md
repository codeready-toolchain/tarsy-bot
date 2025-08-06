# EP-0008-1: Sequential Agent Chains - Technical Implementation Guide

## Design Principles

**Core Guidelines from Design Document:**
- **Unified Architecture**: Replace single-agent processing with unified chain execution - all agents execute through chains (single agents become 1-stage chains)
- **Clean Interface Design**: Break and improve BaseAgent interface for accumulated data flow, enabling sophisticated multi-stage workflows
- **Maintainability**: Clear separation between chain orchestration (ChainOrchestrator) and individual agent execution logic (BaseAgent)
- **Strategic Breaking Changes**: Accept necessary breaking changes for cleaner long-term architecture - prioritize dashboard/backend over dev UI compatibility

## Implementation Strategy

**Approach**: Unified execution architecture where ChainRegistry replaces AgentRegistry, and BaseAgent interface is enhanced for accumulated data flow across stages. Single agents become 1-stage chains.

**Breaking Changes Strategy:**
- **External API**: Breaking changes to WebSocket message format (remove progress field, add chain fields) - dashboard updated accordingly, dev UI simplified
- **Database**: Fresh database approach - delete existing DB data for cleaner schema with stage-level tracking
- **Configuration**: Clean slate - remove BUILTIN_AGENT_MAPPINGS, add BUILTIN_CHAIN_DEFINITIONS and agent_chains section

**Objective:** Replace single-agent processing with unified chain execution where all agents execute through chains (single agents become 1-stage chains).

**Breaking Changes:** BaseAgent interface, WebSocket message format, and database schema.

**Dependencies:** Implementation must proceed in order due to interface changes.

## Core Logic Flow

**Unified Execution Path from Design Document:**
1. **Alert Reception**: AlertService receives alert and looks up chain definition (single agents are 1-stage chains)
2. **Chain Lookup**: ChainRegistry returns chain definition for alert type (always returns a chain, even for single agents)
3. **Unified Execution**: ChainOrchestrator executes all processing through unified chain execution path
4. **Stage Execution**: Each stage (including single-agent "chains") runs with consistent orchestration
5. **Progress Reporting**: WebSocket updates sent for each stage start/completion (unified for single and multi-stage)
6. **Result Aggregation**: Final result processing identical for single-stage and multi-stage executions
7. **History Storage**: All executions stored with consistent stage-level detail format

**Phase 1 Chain Execution Flow (Graceful Error Handling):**
- **Graceful Degradation**: Stage failures don't stop chain execution - continue to next stage
- **Full Recording**: All errors recorded as stage outputs for history/dashboard visibility  
- **Database-Driven**: All execution state persisted using AlertSession and StageExecution tables
- **Progress Reporting**: Real-time WebSocket updates with stage-level context
- **Accumulated Data Flow**: Each stage receives original alert + runbook + all previous stage outputs

## Security Design

**Security Considerations from Design Document:**
- **Agent-Level Security**: Each stage respects individual agent's MCP server access and data masking configuration
- **Chain Validation**: Chain configurations validated at startup to ensure all referenced agents exist and are properly configured
- **Data Flow Security**: Enriched data passed between stages follows same security model as single-agent processing
- **Access Control**: Chain execution uses same authentication/authorization as single-agent processing

## Performance Considerations

**Performance Design from Design Document:**
- **Database-Driven**: All state persisted in database - no in-memory state management complexity
- **Simple & Reliable**: Survives service restarts, easy debugging, full audit trail
- **Adequate Performance**: For ~10 concurrent alerts with 2-5 stage chains, database I/O is negligible
- **Linear Scaling**: Processing time scales linearly with chain length (as expected)

## Phase Breakdown

## Phase 1: Foundation - Core Models and Database

**Requirements:** Core data models and database schema for chain execution tracking.

#### 1.1 Core Data Models
**File:** `backend/tarsy/models/chain_models.py` (NEW)

**Complete Model Specifications:**
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

# No ChainExecutionState needed - database-driven execution using AlertSession and StageExecution tables
# All execution state persisted in database for reliability, debugging, and audit trail
```

**Validation Required:**
- All Pydantic models validate correctly
- Data serialization/deserialization works
- Model relationships function properly

#### 1.2 Fresh Database Schema (No Migration)
**Files:** 
- `backend/tarsy/models/database.py` (MODIFY)

**Complete Database Table Definitions:**
```python
from sqlmodel import SQLModel, Field, Relationship, Column
from sqlalchemy import JSON
from typing import Optional, List
import uuid

# Enhanced AlertSession Table
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

# New StageExecution Table
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
    error_message: Optional[str] = Field(description="Stage error message if failed")
    
    # Phase 2/3: Extensible execution model (for future use)
    execution_type: str = Field(default="sequential", description="sequential|parallel|conditional")
    agents: Optional[List[str]] = Field(sa_column=Column(JSON), description="Multiple agents for parallel execution (Phase 2)")
    routing_decision: Optional[dict] = Field(sa_column=Column(JSON), description="Conditional routing logic (Phase 3)")
    
    # Relationships
    session: AlertSession = Relationship(back_populates="stage_executions")
    llm_interactions: list["LLMInteraction"] = Relationship(back_populates="stage_execution")  # NEW
    mcp_communications: list["MCPCommunication"] = Relationship(back_populates="stage_execution")  # NEW

# Enhanced LLMInteraction Table (add stage tracking)
class LLMInteraction(SQLModel, table=True):
    # ... existing fields ...
    stage_execution_id: Optional[str] = Field(foreign_key="stage_executions.execution_id", index=True, description="Stage execution reference")
    stage_execution: Optional[StageExecution] = Relationship(back_populates="llm_interactions")

# Enhanced MCPCommunication Table (add stage tracking)  
class MCPCommunication(SQLModel, table=True):
    # ... existing fields ...
    stage_execution_id: Optional[str] = Field(foreign_key="stage_executions.execution_id", index=True, description="Stage execution reference")  
    stage_execution: Optional[StageExecution] = Relationship(back_populates="mcp_communications")
```

**Implementation:**
- Update database models for fresh schema
- **Fresh Database Approach:** Existing database will be deleted for cleaner schema
- Create new tables with proper relationships and indexes

**Validation Required:**
- New schema creates successfully
- Model relationships work correctly
- Database performance adequate

#### 1.3 Environment Configuration
**Files:**
- `.env.example` (MODIFY)  
- Settings validation

```bash
# Enhanced logging for development:
LOG_LEVEL=DEBUG  # Enable debug logging for chain execution details
```

---

## Phase 2A: BaseAgent Interface Changes

**Requirements:** Update BaseAgent interface for accumulated data flow.

#### 2.1 BaseAgent Interface Update (BREAKING CHANGE)
**Files:**
- `backend/tarsy/agents/base_agent.py` (CRITICAL CHANGE)

```python
# Key changes:
1. Update process_alert() method signature:
   OLD: process_alert(alert_data: Dict, runbook_content: str, session_id: str, callback)
   NEW: process_alert(alert_data: AccumulatedAlertData, session_id: str, callback)

2. Update helper methods:
   - build_analysis_prompt() takes AccumulatedAlertData
   - _create_prompt_context() uses accumulated data structure
   
3. Add backward compatibility helpers:
   - extract_runbook() method for easy runbook access
   - get_original_alert() method for original data
   - get_stage_result() method for previous stage data
```



**Validation Required:**
- BaseAgent interface signature updated correctly
- Helper methods work with AccumulatedAlertData  
- Interface compiles without errors

---

## Phase 2B: PromptBuilder Integration

**Requirements:** Update PromptBuilder for accumulated data and stage context.

#### 2B.1 PromptBuilder Rewrite (CRITICAL CHANGE)
**Files:**
- `backend/tarsy/agents/prompt_builder.py` (CRITICAL CHANGE)

**PromptContext Update:**
```python
# OLD PromptContext (TO BE REPLACED):
@dataclass
class PromptContext:
    agent_name: str
    alert_data: Dict[str, Any]      # ← Original alert only
    runbook_content: str            # ← Separate runbook (REMOVED)
    mcp_data: Dict[str, Any]
    # ... other fields

# NEW PromptContext (REQUIRED):
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

**PromptBuilder Methods:**
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

**BaseAgent Integration:**
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

**Validation Required:**
- PromptBuilder handles accumulated data correctly
- Stage outputs section renders properly
- Prompt structure maintains existing functionality

---

## Phase 2C: Agent Implementation Updates  

**Requirements:** Update agent implementations for new BaseAgent interface.

#### 2C.1 Agent Updates
**Files:**
- `backend/tarsy/agents/kubernetes_agent.py` (MODIFY)
- `backend/tarsy/agents/configurable_agent.py` (MODIFY)

```python
# Update implementations for new interface:
1. Use AccumulatedAlertData parameter
2. Extract runbook using helper methods
3. Access previous stage results when available
4. Preserve all existing functionality
```

**Migration Pattern:**
```python
# OLD CODE:
async def process_alert(self, alert_data: Dict, runbook_content: str, session_id: str, callback=None):
    # Use alert_data and runbook_content directly

# NEW CODE:
async def process_alert(self, alert_data: AccumulatedAlertData, session_id: str, callback=None):
    runbook_content = alert_data.get_runbook()
    original_alert = alert_data.get_original_data()
    
    # Check for previous stage results (multi-stage chains)
    if previous_data := alert_data.get_stage_result("data-collection"):
        logger.info("Using enriched data from data-collection stage")
        # Use previous_data for enhanced analysis
    
    # Rest of logic remains the same
```

**Validation Required:**
- All existing agents work with new interface
- No regression in single-agent functionality
- Stage result access works correctly

---

## Phase 3: Chain Services - Registry and Orchestrator

**Requirements:** Implement ChainRegistry and ChainOrchestrator services for unified chain execution.

#### 3.1 ChainRegistry Implementation
**File:** `backend/tarsy/services/chain_registry.py` (NEW)

**Complete Implementation:**
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
        """Initialize ChainRegistry with built-in and YAML chain definitions."""
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
        """Get chain definition for alert type."""
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
    
    def _build_alert_type_mappings(self) -> Dict[str, str]:
        """Build unified alert_type -> chain_id mappings with strict conflict detection."""
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

#### 3.2 ChainOrchestrator Implementation
**File:** `backend/tarsy/services/chain_orchestrator.py` (NEW)

**Core Implementation:**
```python
class ChainOrchestrator:
    async def execute_chain(
        self, 
        chain_def: ChainDefinitionModel, 
        alert_data: Dict[str, Any],
        runbook_content: str,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Execute chain with graceful error handling - stage failures don't stop execution."""
        
        # Create session with chain definition snapshot
        session = AlertSession(
            alert_id=alert_data["alert_id"],
            chain_id=chain_def.chain_id,
            chain_definition=chain_def.dict(),
            current_stage_index=0,
            status="processing"
        )
        await self.session_repo.create(session)
        
        # Start with original alert data + downloaded runbook
        accumulated_data = AccumulatedAlertData(
            original_alert={**alert_data, "runbook": runbook_content},
            stage_outputs={}
        )
        
        # Track execution statistics
        execution_stats = {
            "total_stages": len(chain_def.stages),
            "completed_stages": 0,
            "failed_stages": 0,
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
            
            # Send progress update
            if progress_callback:
                await progress_callback({
                    "status": "processing",
                    "current_step": f"Starting {stage.name}",
                    "chain_id": chain_def.chain_id,
                    "current_stage": stage.name,
                    "completed_stages": i,
                    "total_stages": len(chain_def.stages)
                })
            
            try:
                result = await self._execute_stage_with_error_handling(stage, accumulated_data, stage_exec)
                accumulated_data.stage_outputs[stage.name] = result
                
                # Update stage as completed (even if it had errors)
                stage_exec.status = "completed"
                stage_exec.completed_at_us = now_us()
                stage_exec.duration_ms = (stage_exec.completed_at_us - stage_exec.started_at_us) // 1000
                stage_exec.stage_output = result
                
                if result.get("error"):
                    execution_stats["failed_stages"] += 1
                else:
                    execution_stats["completed_stages"] += 1
                    
            except Exception as fatal_error:
                # Fatal stage error - record but continue
                error_result = {
                    "error": f"Fatal stage error: {str(fatal_error)}",
                    "error_type": "fatal",
                    "stage_name": stage.name,
                    "timestamp": now_us()
                }
                accumulated_data.stage_outputs[stage.name] = error_result
                
                stage_exec.status = "failed"
                stage_exec.completed_at_us = now_us()
                stage_exec.duration_ms = (stage_exec.completed_at_us - stage_exec.started_at_us) // 1000
                stage_exec.error_message = str(fatal_error)
                stage_exec.stage_output = error_result
                execution_stats["failed_stages"] += 1
                
            await self.stage_repo.update(stage_exec)
        
        # Determine final status and generate analysis
        final_status = self._determine_final_status(execution_stats)
        final_analysis = self._generate_final_analysis(accumulated_data, execution_stats)
        
        # Complete session
        session.status = final_status
        session.completed_at_us = now_us()
        session.final_analysis = final_analysis
        await self.session_repo.update(session)
        
        return {
            "status": final_status,
            "final_analysis": final_analysis,
            "execution_stats": execution_stats,
            "accumulated_data": accumulated_data,
            "chain_id": chain_def.chain_id
        }

    async def _execute_stage_with_error_handling(
        self, stage: ChainStageModel, accumulated_data: AccumulatedAlertData, stage_exec: StageExecution
    ) -> Dict[str, Any]:
        """Execute single stage with comprehensive error handling."""
        try:
            agent = await self.agent_factory.get_agent(stage.agent)
            result = await asyncio.wait_for(
                agent.process_alert(accumulated_data, stage_exec.session_id),
                timeout=300  # 5 minute timeout per stage
            )
            
            if not isinstance(result, dict):
                result = {"analysis": str(result), "metadata": {"wrapped": True}}
                
            result["stage_metadata"] = {
                "stage_name": stage.name,
                "agent": stage.agent,
                "execution_time_ms": stage_exec.duration_ms,
                "timestamp": now_us()
            }
            return result
            
        except asyncio.TimeoutError:
            return {
                "error": f"Stage {stage.name} timed out after 5 minutes",
                "error_type": "timeout",
                "stage_name": stage.name,
                "agent": stage.agent,
                "timestamp": now_us()
            }
        except Exception as e:
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
        
        analysis_parts.append(f"Chain Execution Summary:")
        analysis_parts.append(f"- Total stages: {execution_stats['total_stages']}")
        analysis_parts.append(f"- Successful: {execution_stats['completed_stages']}")
        analysis_parts.append(f"- Failed: {execution_stats['failed_stages']}")
        analysis_parts.append("")
        
        analysis_parts.append("Stage Results:")
        for stage_name, stage_result in accumulated_data.stage_outputs.items():
            if stage_result.get("error"):
                analysis_parts.append(f"❌ {stage_name}: {stage_result['error']}")
            else:
                if "analysis" in stage_result:
                    analysis_parts.append(f"✅ {stage_name}: {stage_result['analysis'][:200]}...")
                else:
                    analysis_parts.append(f"✅ {stage_name}: Completed successfully")
        
        return "\n".join(analysis_parts)

# CRITICAL: Stage Status Values and Error Handling Format
"""
StageExecution Status Values:
- 'active': Stage currently executing
- 'completed': Stage finished (may contain errors in stage_output)
- 'failed': Stage had fatal error (couldn't execute)
- 'skipped': Stage skipped due to dependencies

Error Recording in Database (stage_output JSON field):
stage_output_with_error = {
    "error": "Agent execution failed: Connection timeout",
    "error_type": "agent_error",  # Types: "timeout", "agent_error", "fatal"
    "stage_name": "data-collection",
    "timestamp": 1734567890123456,
    "error_details": {
        "exception_type": "ConnectionTimeout",
        "exception_message": "Could not connect to MCP server"
    }
}

# Stage is marked as "completed" but contains error information
# This allows dashboard to show stage as executed but with errors
"""
```

#### 3.3 Integration Helpers
**Files:**
- `backend/tarsy/services/history_service.py` (MODIFY)

**Required HistoryService Methods:**
```python
# Add methods for stage execution tracking:

async def create_stage_execution(self, stage_exec: StageExecution) -> StageExecution:
    """Create a new stage execution record."""
    # Implementation: Insert into stage_executions table
    pass

async def update_stage_execution(self, stage_exec: StageExecution) -> StageExecution:
    """Update existing stage execution record."""
    # Implementation: Update stage_executions table with new status/output/timing
    pass
    
async def get_stage_executions_for_session(self, session_id: str) -> List[StageExecution]:
    """Get all stage executions for a session, ordered by stage_index."""
    # Implementation: Query stage_executions table filtered by session_id
    pass

async def create_timeline_event_with_stage_context(
    self, 
    event_type: str, 
    session_id: str,
    stage_execution_id: Optional[str] = None,
    stage_context: Optional[Dict[str, Any]] = None,
    details: Dict[str, Any] = None
) -> None:
    """Create timeline event with stage context for rich dashboard visualization."""
    # Implementation: Insert into timeline events with stage_execution_id link
    pass

# Enhanced session retrieval with stage data
async def get_session_with_stage_executions(self, session_id: str) -> DashboardSessionDetail:
    """Get complete session details with stage execution breakdown."""
    # Implementation: Join AlertSession with StageExecution records
    pass
```

**Validation Required:**
- ChainRegistry correctly maps alert types to chains
- ChainOrchestrator executes sequential chains successfully
- Error handling works gracefully (failures don't stop execution)
- Database state tracking works correctly
- Progress reporting functions properly

---

## Phase 4: AlertService Integration

**Requirements:** Integrate chain execution into AlertService, replacing direct agent execution.

#### 4.1 AlertService Refactoring
**File:** `backend/tarsy/services/alert_service.py` (MODIFY)

```python
# Key changes:
1. Replace AgentRegistry with ChainRegistry
2. Replace direct agent execution with ChainOrchestrator.execute_chain()
3. Update initialization with chain services
4. Simplify processing flow (unified execution path)
5. Remove legacy agent selection logic
```

**Updated Processing Flow:**
```python
# OLD FLOW:
alert_type -> AgentRegistry -> Agent class -> Direct execution

# NEW FLOW:  
alert_type -> ChainRegistry -> Chain definition -> ChainOrchestrator -> Unified execution
```

#### 4.2 AgentFactory Integration
**File:** `backend/tarsy/services/agent_factory.py` (MODIFY)

```python
# Updates needed:
1. Pass ChainRegistry instead of AgentRegistry
2. Ensure agent creation works with chain orchestration
3. Maintain existing agent instantiation logic
4. Add error handling for agents referenced in chains
```

**Validation Required:**
- AlertService uses unified chain execution for all processing
- Single-agent processing works through 1-stage chains
- Multi-stage chains execute correctly
- No regression in alert processing functionality

---

## Phase 5: Configuration and Built-ins

**Requirements:** Add built-in chain definitions and extend configuration loading for agent_chains.

#### 5.1 Built-in Chain Definitions
**File:** `backend/tarsy/config/builtin_config.py` (MODIFY)

**Specific Built-in Chains:**
```python
# DELETE ENTIRELY: BUILTIN_AGENT_MAPPINGS = {...}  # Remove legacy mappings

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

**Implementation:**
1. **DELETE** `BUILTIN_AGENT_MAPPINGS` entirely
2. **ADD** `BUILTIN_CHAIN_DEFINITIONS` as single source of truth  
3. ChainRegistry becomes the only mapping system

#### 5.2 Configuration Loading Extension
**File:** `backend/tarsy/config/agent_config.py` (CRITICAL CHANGE)

**Extended CombinedConfigModel:**
```python
class CombinedConfigModel(BaseModel):
    """Extended configuration model with agent chains support."""
    agents: Dict[str, AgentConfigModel] = Field(default_factory=dict, description="Reusable processing components")
    mcp_servers: Dict[str, MCPServerConfigModel] = Field(default_factory=dict)
    agent_chains: Dict[str, ConfigurableChainModel] = Field(default_factory=dict, description="Alert type to workflow mappings")  # NEW
```

**ConfigurationLoader Updates:**
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
        """Validate agent chain definitions and references."""
        if not config.agent_chains:
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
    
    def _validate_chain_alert_type_conflicts(self, yaml_chains: Dict[str, ConfigurableChainModel]) -> None:
        """Validate alert types don't conflict between YAML chains or with built-in chains."""
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
```

#### 5.3 YAML Configuration Support
**File:** `config/agents.yaml` (EXAMPLE UPDATES)

```yaml
# Add example agent_chains section:
agent_chains:
  security-incident-chain:
    alert_types: ["SecurityBreach", "SuspiciousActivity"]  
    stages:
      - name: "data-collection"
        agent: "data-collector-agent"
      - name: "analysis" 
        agent: "analysis-agent"
    description: "Two-stage security incident workflow"
    
  # Single-agent chain example (alternative to built-in)  
  custom-kubernetes-chain:
    alert_types: ["CustomK8sAlert"]
    stages:
      - name: "analysis"
        agent: "KubernetesAgent" 
    description: "Custom single-stage Kubernetes handling"
```

**Validation Required:**
- Built-in chain definitions work correctly
- ConfigurationLoader handles agent_chains section
- Validation provides clear error messages
- YAML chain configurations load and execute properly
- No conflicts between built-in and YAML chains

---

## Phase 6: API and Dashboard Updates

**Requirements:** Enhance dashboard API and WebSocket messaging for rich chain visualization.

#### 6.1 Enhanced WebSocket Messages (BREAKING CHANGE)
**File:** `backend/tarsy/services/websocket_manager.py` (MODIFY)

**New AlertStatusUpdate Model:**
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

**Progress Update Timing in ChainOrchestrator:**
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

#### 6.2 Enhanced Dashboard API
**Files:**
- `backend/tarsy/api/history.py` (MODIFY)
- `backend/tarsy/models/api_models.py` (MODIFY)

**API Model Specifications:**
```python
# Enhanced API models for dashboard chain visualization
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
```

**Enhanced Endpoints:**
```python
# Enhanced session list for dashboard
@app.get("/api/v1/history/sessions", response_model=DashboardSessionsListResponse)
async def list_sessions_for_dashboard() -> DashboardSessionsListResponse:
    """List sessions with rich chain information for dashboard visualization."""

# Enhanced session detail for dashboard  
@app.get("/api/v1/history/sessions/{session_id}", response_model=DashboardSessionDetail)
async def get_session_detail_for_dashboard(session_id: str) -> DashboardSessionDetail:
    """Get complete session details with stage-by-stage breakdown for dashboard."""
```

#### 6.3 Dashboard UI Enhancements
**Files:**
- `dashboard/src/types/index.ts` (MODIFY) - See Additional Files section for details
- `dashboard/src/components/ActiveAlertCard.tsx` (MODIFY)  
- `dashboard/src/components/SessionDetailPage.tsx` (MODIFY)

**Enhanced ActiveAlertCard Component:**
```typescript
// Add ChainProgressDisplay component for real-time visualization:

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
  chainId, currentStage, stageProgress, totalStages, completedStages
}) => {
  return (
    <Box sx={{ mt: 2 }}>
      {/* Chain Header */}
      <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
        🔗 {chainId}
      </Typography>
      
      {/* Vertical Stack of Stage Cards */}
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
            <CardContent sx={{ py: 1.5, px: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  {getStageStatusIcon(stage.status)}
                  <Box>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      {stage.stage}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Agent: {stage.agent}
                    </Typography>
                  </Box>
                </Box>
                
                {/* Status Display */}
                <Box sx={{ textAlign: 'right' }}>
                  {stage.status === 'completed' && stage.duration && (
                    <Typography variant="caption" color="text.secondary">
                      {formatDurationMs(stage.duration)}
                    </Typography>
                  )}
                  {stage.status === 'failed' && stage.error && (
                    <Alert severity="error" sx={{ mt: 1, py: 0.5 }}>
                      <Typography variant="caption">{stage.error}</Typography>
                    </Alert>
                  )}
                </Box>
              </Box>
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
```

**Enhanced SessionDetailPage Component:**
```typescript
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
      
      {/* Stage Execution Details - Vertical Cards with drill-down */}
      <Stack spacing={2}>
        {session.stage_executions?.map((stageExec, index) => (
          <Card key={stageExec.stage_id} variant="outlined">
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
                <Typography variant="h6">
                  Stage {index + 1}: {stageExec.stage_id}
                </Typography>
                <Chip label={stageExec.status} color={getStageStatusChipColor(stageExec.status)} size="small" />
              </Box>
              
              {/* Stage Metadata Grid */}
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
              </Grid>
              
              {/* Stage Output Accordion */}
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
            </CardContent>
          </Card>
        ))}
      </Stack>
    </Paper>
  );
};
```

**Dashboard Features:**
- Real-time stage progress with status indicators
- Vertical card layout for stages (2 stages or 20 stages)
- Error visualization alongside successful results
- Stage drill-down with execution details and outputs
- Timeline view with stage context

**Validation Required:**
- WebSocket messages include rich chain progress data
- Dashboard API provides complete stage execution information
- Dashboard UI shows real-time chain progress visualization
- Error scenarios display correctly in UI
- No breaking changes to simple alert APIs

---

## Phase 7: Testing and Validation

**Requirements:** Comprehensive testing of complete chain execution system.

#### 7.1 Integration Testing Suite
**Files:**
- `tests/integration/test_chain_execution.py` (NEW)
- `tests/integration/test_chain_registry.py` (NEW)

```python
# Comprehensive integration tests:
1. Full chain execution workflows:
   - Single-stage chains (backward compatibility)
   - Multi-stage chains with data flow
   - Error scenarios and graceful degradation
   
2. Configuration loading and validation:
   - Built-in chain definitions
   - YAML chain configurations  
   - Error handling and conflict detection
   
3. API and WebSocket integration:
   - Dashboard API with chain data
   - Real-time progress updates
   - Error reporting through all channels
```

#### 7.2 Performance Testing
**Files:**
- `tests/performance/test_chain_performance.py` (NEW)

```python
# Performance validation:
1. Single vs multi-stage execution time comparison
2. Database performance with stage tracking
3. Memory usage during chain execution
4. Concurrent chain execution (multiple alerts)
```

#### 7.3 Compatibility Testing
**Files:**
- `tests/compatibility/test_fresh_db_compatibility.py` (NEW)

```python
# Fresh database compatibility tests:
1. Fresh database schema validation
2. Existing alert processing compatibility with new schema
3. Configuration file compatibility
4. WebSocket message format changes
```

#### 7.4 End-to-End Validation
**Testing Scenarios:**
- Complete alert processing from submission to result
- Dashboard real-time updates during processing
- Error handling at each stage with proper visualization
- Configuration loading with various YAML setups
- Performance under typical load (10 concurrent alerts)

**Validation Required:**
- All integration tests pass
- Performance meets requirements (no significant degradation)
- End-to-end workflows function correctly
- Error handling works gracefully in all scenarios
- Fresh database schema works correctly

---

## Files to Delete

**Files to Remove Entirely:**
- `backend/tarsy/services/agent_registry.py` - Delete entirely, replaced by ChainRegistry
- Remove `BUILTIN_AGENT_MAPPINGS` from `backend/tarsy/config/builtin_config.py` - replaced by BUILTIN_CHAIN_DEFINITIONS

---

## Additional Files to Modify

**Files Requiring Updates Not Covered in Phases:**

### backend/tarsy/main.py (MODIFY)
```python
# Add optional chain-specific endpoints:

@app.get("/api/v1/chains", response_model=List[str])
async def list_available_chains():
    """List all available chain IDs for debugging/monitoring."""
    return chain_registry.list_available_chains()

@app.get("/api/v1/chains/{chain_id}", response_model=ChainDefinitionModel)  
async def get_chain_definition(chain_id: str):
    """Get chain definition details for debugging/monitoring."""
    # Implementation: Return chain definition from ChainRegistry

@app.get("/api/v1/alert-types", response_model=List[str])
async def list_available_alert_types():
    """List all available alert types for debugging/monitoring."""
    return chain_registry.list_available_alert_types()

# Add chain_id query parameter to existing endpoints
@app.get("/api/v1/history/sessions")
async def list_sessions(chain_id: Optional[str] = Query(None)):
    """Enhanced session list with optional chain_id filtering."""
    # Implementation: Filter by chain_id if provided
```

### backend/tarsy/models/database.py (MODIFY)
```python
# Update imports to include new StageExecution model:
from tarsy.models.chain_models import StageExecution

# Ensure proper SQLModel table relationships are established
# Update any existing database connection/migration code to handle new tables
```

### backend/tarsy/services/websocket_manager.py (MODIFY)
```python
# Update WebSocketManager class to handle enhanced AlertStatusUpdate:

class WebSocketManager:
    async def send_chain_progress_update(
        self,
        alert_id: str,
        status: str,
        current_step: str,
        chain_context: Optional[Dict[str, Any]] = None
    ):
        """Send enhanced progress update with chain context."""
        update = AlertStatusUpdate(
            alert_id=alert_id,
            status=status,
            current_step=current_step,
            chain_id=chain_context.get("chain_id") if chain_context else None,
            current_stage=chain_context.get("current_stage") if chain_context else None,
            total_stages=chain_context.get("total_stages") if chain_context else None,
            completed_stages=chain_context.get("completed_stages") if chain_context else None,
            stage_progress=chain_context.get("stage_progress") if chain_context else None
        )
        await self.broadcast_to_alert_subscribers(alert_id, update)
```

### dashboard/src/types/index.ts (MODIFY)  
```typescript
// Add chain execution types:

export interface ChainNode {
  id: string;
  agent: string;  
  status: 'pending' | 'active' | 'completed' | 'failed' | 'skipped';
}

export interface ChainInfo {
  id: string;
  type: 'sequential';
  nodes: ChainNode[];
}

export interface StageExecution {
  stage_id: string;
  status: 'pending' | 'active' | 'completed' | 'failed' | 'skipped';
  started_at_us?: number;
  completed_at_us?: number;
  duration_ms?: number;
  agent?: string;
  stage_output?: any;
  error_message?: string;
  execution_type: 'sequential';
}

export interface DashboardSessionSummary extends SessionSummary {
  chain: ChainInfo;  // Enhanced with chain visualization data
}

export interface DashboardSessionDetail extends SessionDetail {
  chain: ChainInfo;
  stage_executions: StageExecution[];
  chronological_timeline: TimelineEvent[];
}

// Enhanced WebSocket message type
export interface AlertStatusUpdate {
  alert_id: string;
  status: string;
  current_step: string;
  chain_id?: string;
  current_stage?: string;
  total_stages?: number;
  completed_stages?: number;
  stage_progress?: Array<{
    stage: string;
    agent: string;
    status: string;
  }>;
  current_agent?: string;
  result?: string;
  error?: string;
}
```

---

## Breaking Changes

### Database Changes
**Impact:** Fresh database schema - existing database will be deleted
**Approach:** Clean slate database for optimal schema design

### BaseAgent Interface Changes
**Impact:** All custom agents need interface updates
**Files Affected:**
- `backend/tarsy/agents/base_agent.py`
- `backend/tarsy/agents/kubernetes_agent.py`
- `backend/tarsy/agents/configurable_agent.py`
- Any custom agent implementations

**Migration Pattern:**
```python
# OLD
async def process_alert(self, alert_data: Dict, runbook_content: str, session_id: str, callback=None):

# NEW  
async def process_alert(self, alert_data: AccumulatedAlertData, session_id: str, callback=None):
    runbook_content = alert_data.get_runbook()
    original_alert = alert_data.get_original_data()
```

### WebSocket Message Format Changes
**Impact:** Dashboard needs updates for new message structure
**Mitigation:**
- Dashboard updated as part of implementation
- Dev UI simplified to ignore new fields
- No backward compatibility maintained (clean break)

### Configuration Changes
**Impact:** Configuration files need updates
**Changes:**
- Remove `BUILTIN_AGENT_MAPPINGS`
- Add `BUILTIN_CHAIN_DEFINITIONS`
- Add `agent_chains` section to YAML