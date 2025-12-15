# Parallel Agent Stages Implementation

## Overview

Add parallel execution capabilities to agent chains, supporting:

1. **Multi-agent parallelism**: Run different agents in parallel for independent domain investigation
2. **Simple replica parallelism**: Run same agent N times with identical config for accuracy via redundancy
3. **Comparison parallelism**: Run same agent multiple times with different LLM providers/strategies for A/B testing
4. **Per-agent configuration**: Each agent in `agents` list can specify its own LLM provider and iteration strategy
5. **Partial success**: Continue chain if at least one parallel execution succeeds
6. **Structured results**: Raw parallel outputs packaged for next stage consumption
7. **Automatic synthesis**: Built-in SynthesisAgent synthesizes results when parallel stage is final
8. **Configurable synthesis**: Optional `synthesis` field allows customizing synthesis agent, iteration strategy, and LLM provider
9. **Rich investigation history**: Synthesis strategies receive full conversation history (thoughts, tool observations) for comprehensive analysis
10. **Pause/Resume support**: Individual agents can pause at max_iterations while others complete; resume re-executes only paused agents

## Configuration Syntax

### Multi-Agent Parallelism

```yaml
stages:
  - name: "investigation"
    agents:  # List of agents to run in parallel
      - name: "kubernetes"                 # Agent to execute
        llm_provider: "openai"              # Optional per-agent provider
        iteration_strategy: "react"         # Optional per-agent strategy
      - name: "vm"
        llm_provider: "anthropic"
        iteration_strategy: "native-thinking"  # Compare strategies
    failure_policy: "any"                  # Continue if any succeeds (default: "all")
    # Optional: Configure synthesis behavior (uses defaults if omitted)
    synthesis:
      agent: "SynthesisAgent"              # Agent to use for synthesis (default: SynthesisAgent)
      iteration_strategy: "react-synthesis" # Synthesis strategy (default: react-synthesis)
      llm_provider: "anthropic-default"    # Optional provider override for synthesis
  
  - name: "command"
    agent: "SynthesisAgent"                # Final analysis from parallel results (built-in)
```

### Replica Parallelism (Simple Redundancy)

```yaml
stages:
  - name: "analysis"
    agent: "kubernetes"
    replicas: 3                    # Run same agent 3 times with same config
    llm_provider: "openai"         # All replicas use same provider/strategy
    iteration_strategy: "react"
    # Optional: Configure synthesis with custom strategy
    synthesis:
      iteration_strategy: "native-thinking-synthesis"  # Use Gemini thinking for synthesis
      llm_provider: "google-default"
  
  - name: "command"
    agent: "SynthesisAgent"        # Final analysis from all 3 parallel results
```

### Replica Parallelism (Comparison - Use agents list instead)

```yaml
stages:
  - name: "analysis"
    agents:                        # Explicit config per agent for comparison
      - name: "kubernetes"
        llm_provider: "openai"
        iteration_strategy: "react"
      - name: "kubernetes"
        llm_provider: "anthropic"
        iteration_strategy: "react-stage"
      - name: "kubernetes"
        llm_provider: "gemini"
        iteration_strategy: "native-thinking"
  
  - name: "command"
    agent: "SynthesisAgent"
```

### Automatic Synthesis (No Explicit Judge)

When a parallel stage is the final stage, synthesis is automatically invoked using the stage's `synthesis` configuration (or defaults if not specified).

```yaml
stages:
  - name: "investigation"
    agents:
      - name: "kubernetes"
      - name: "vm"
    # Optional: Configure automatic synthesis
    synthesis:
      agent: "SynthesisAgent"              # Default
      iteration_strategy: "react-synthesis" # Default (or use "native-thinking-synthesis")
      llm_provider: "anthropic-default"    # Optional
  # No follow-up stage → synthesis automatically invoked with above config
```

```yaml
stages:
  - name: "investigation"
    agent: "kubernetes"
    replicas: 3
    synthesis:
      iteration_strategy: "native-thinking-synthesis"  # Use Gemini thinking
  # No follow-up stage → synthesis automatically invoked
```

## Result Handling Logic

### Automatic Synthesis After ALL Parallel Stages

**IMPORTANT**: Synthesis is ALWAYS invoked automatically after ANY parallel stage completes successfully, regardless of whether there are follow-up stages or not.

#### Rationale

Parallel execution produces multiple independent analyses that need to be synthesized into a coherent, unified result. Without synthesis:
- Next stages receive raw parallel data structure (difficult to process)
- Final output is fragmented across multiple agent results
- Users must manually reconcile conflicting findings

By always synthesizing, we ensure:
- Consistent output format (single coherent analysis)
- Quality-filtered results (low-evidence findings deprioritized)
- Reconciled conflicts between parallel agents
- Clean input for subsequent stages

#### Synthesis Configuration

The `synthesis` field in stage configuration is **optional**. If not provided, defaults are used:

```yaml
synthesis:
  agent: "SynthesisAgent"           # Default
  iteration_strategy: "synthesis"   # Default
  llm_provider: null                # Uses stage/chain/system default
```

#### Result Flow Examples

**Case 1: Parallel Stage + Follow-up Stage**
1. Multiple agents execute in parallel → `ParallelStageResult`
2. **Synthesis automatically invoked** → Synthesized `AgentExecutionResult`
3. Next stage receives synthesized result (clean, unified analysis)

**Case 2: Parallel Stage is Final Stage**
1. Multiple agents execute in parallel → `ParallelStageResult`
2. **Synthesis automatically invoked** → Synthesized `AgentExecutionResult`
3. Synthesized result used as final analysis

**Case 3: Single Agent Stage (Existing Behavior)**
- Use agent's own result directly (unchanged)

## Pause/Resume Behavior

### Pause Detection

When any parallel agent hits `max_iterations` without reaching a Final Answer:
1. Agent raises `SessionPaused` exception (same as single-agent stages)
2. Exception caught in `execute_single()` (parallel execution handler)
3. Child stage marked as `PAUSED` (not `FAILED`)
4. Other parallel agents continue running naturally
5. Parent stage status determined by priority: `PAUSED > FAILED > COMPLETED`
6. Session enters `PAUSED` state if any agent is paused

### Status Priority

Overall parallel stage status follows this priority:
1. **PAUSED** - If any agent is paused, stage is PAUSED (user can resume)
2. **COMPLETED/FAILED** - Determined by `failure_policy` if no agents paused

Examples:
- 2 completed + 1 paused → Stage is PAUSED
- 1 completed + 1 failed + 1 paused → Stage is PAUSED
- 2 completed + 1 failed (no pauses) + policy=ANY → Stage is COMPLETED
- 2 completed + 1 failed (no pauses) + policy=ALL → Stage is FAILED

### Resume Behavior

When resuming a paused parallel stage:
1. Load all child stage executions from database
2. Separate by status: completed, paused, failed
3. Reconstruct results from completed children (preserved)
4. Reconstruct results from failed children (preserved)
5. Build execution configs for ONLY paused children
6. Restore paused conversation states to chain context
7. Re-execute paused agents using existing parallel execution logic
8. Merge all results: completed + failed + resumed
9. Determine final status (may pause again if agents hit max_iterations)
10. Update parent stage with merged result

### Key Features

- **Completed results preserved**: Agents that finished successfully don't re-execute
- **Failed results preserved**: Agents that failed remain failed (resume only pauses)
- **Independent iteration counts**: Each agent tracks its own iteration count
- **Multiple resume cycles**: Can pause and resume multiple times
- **Synthesis integration**: Final synthesis includes all agent results (completed + resumed)

## Implementation Tasks

### 1. Data Models ([backend/tarsy/models/agent_config.py](backend/tarsy/models/agent_config.py))

- Add `ParallelAgentConfig` model for multi-agent stages with per-agent configuration:
  - `name: str` - agent identifier (changed from `agent` for consistency)
  - `llm_provider: Optional[str]` - optional LLM provider override for this agent
  - `iteration_strategy: Optional[str]` - optional iteration strategy override for this agent
- Add `SynthesisConfig` model for configurable synthesis behavior:
  - `agent: str` - agent to use for synthesis (default: "SynthesisAgent")
  - `iteration_strategy: str` - synthesis strategy (default: "react-synthesis")
  - `llm_provider: Optional[str]` - optional LLM provider for synthesis
- Add `replicas` field to `ChainStageConfigModel` with validation (≥1, default 1)
- Add `failure_policy` field: `Literal["all", "any"]` (default "all")
- Add `agents` field: `Optional[List[ParallelAgentConfig]]` as alternative to single `agent`
- Add `synthesis` field: `Optional[SynthesisConfig]` for configurable synthesis
- Add validation: Either `agent` OR `agents` must be specified, not both
- Add validation: If `replicas > 1`, must use single `agent`, not `agents` list
- Add validation: Replicas with `agent` run with same config; use `agents` list for per-agent variety

### 2. Parallel Execution Results ([backend/tarsy/models/agent_execution_result.py](backend/tarsy/models/agent_execution_result.py))

- Update `AgentExecutionResult` model:
  - Add `investigation_history: Optional[str]` field - rich conversation history for synthesis strategies (includes all assistant messages, tool observations, excludes system messages and first user message)
  - Keep `complete_conversation_history: Optional[str]` for backward compatibility with sequential stages
- Create `AgentExecutionMetadata` model for individual agent execution details:
  - `agent_name: str` - e.g., "KubernetesAgent" or "KubernetesAgent-1" for replicas
  - `llm_provider: str` - provider used for this agent
  - `iteration_strategy: str` - strategy used (e.g., "react", "native-thinking", "react-stage", "react-synthesis", "native-thinking-synthesis")
  - `started_at_us: int`, `completed_at_us: int` - timing info
  - `duration_ms: int` - calculated duration
  - `status: StageStatus` - COMPLETED, FAILED, etc.
  - `error_message: Optional[str]` - error if failed
  - `token_usage: Optional[Dict[str, int]]` - token counts: `{"input_tokens": X, "output_tokens": Y, "total_tokens": Z}`
- Create `ParallelStageMetadata` model for stage-level orchestration:
  - Configuration fields: `parallel_type: Literal["multi_agent", "replica"]`, `failure_policy: Literal["all", "any"]`
  - Stage timing: `started_at_us: int`, `completed_at_us: int`
  - Individual executions: `agent_metadatas: List[AgentExecutionMetadata]`
  - Properties: `duration_ms`, `successful_count`, `failed_count`, `total_count`
- Create `ParallelStageResult` model (pure data container, Option B):
  - `results: List[AgentExecutionResult]` - full investigation results for each agent
  - `metadata: ParallelStageMetadata` - structured execution metadata (config + agent details)
  - `status: StageStatus` - aggregated stage status based on failure policy
  - **No `aggregated_summary` field** - synthesis happens in judge agent, not here

### 3. Built-in SynthesisAgent Configuration & Iteration Strategies

#### Built-in SynthesisAgent ([backend/tarsy/config/builtin_config.py](backend/tarsy/config/builtin_config.py))

- Add `SynthesisAgent` entry to `BUILTIN_AGENTS` dictionary:
  - Uses `ConfigurableAgent` (no custom class needed - pure analysis agent)
  - Define custom instructions for synthesizing parallel investigation results:
    - **Critically evaluate** the quality and reliability of each investigation result
    - Prioritize higher-quality analyses with stronger evidence and reasoning
    - Disregard or deprioritize low-quality results that lack supporting evidence or contain errors
    - Analyze the original alert using the best available data from parallel investigations
    - Integrate findings from high-quality investigations into a unified understanding
    - Reconcile conflicting information by assessing which analysis provides better evidence
    - Provide definitive root cause analysis based on the most reliable evidence
    - Generate actionable recommendations leveraging insights from the strongest investigations
    - Focus on solving the original alert/issue, not on meta-analyzing agent performance
  - No MCP servers required (empty mcp_servers list)
  - iteration_strategy: "react-synthesis" (default synthesis strategy)
- Make user-accessible: Can be used explicitly in chains or automatically invoked

#### Synthesis Iteration Strategies ([backend/tarsy/models/constants.py](backend/tarsy/models/constants.py))

- Add new iteration strategies to `IterationStrategy` enum:
  - `REACT_SYNTHESIS = "react-synthesis"` - ReAct-based synthesis without MCP tools (default)
  - `NATIVE_THINKING_SYNTHESIS = "native-thinking-synthesis"` - Gemini native thinking for synthesis

#### Synthesis Controllers ([backend/tarsy/agents/iteration_controllers/](backend/tarsy/agents/iteration_controllers/))

- Create `ReactSynthesisController` extending `ReactController`:
  - Synthesis-specific prompts
  - `needs_mcp_tools() -> False` (no tool access needed)
- Create `NativeThinkingSynthesisController` extending `NativeThinkingController`:
  - Gemini thinking-based synthesis
  - `needs_mcp_tools() -> False`
- Update controller factory to map new strategies to synthesis controllers

### 4. ChainContext Updates ([backend/tarsy/models/processing_context.py](backend/tarsy/models/processing_context.py))

- Update `stage_outputs` type to: `Dict[str, Union[AgentExecutionResult, ParallelStageResult]]`
- Add `get_previous_stage_results()` helper that handles both single and parallel results
- Add `is_parallel_stage(stage_name: str)` helper to check if a stage has parallel execution
- Add `get_last_stage_result()` helper for automatic synthesis logic
- Update `format_previous_stages_context()` to use `investigation_history` for synthesis strategies:
  - Detect if current agent uses synthesis strategy (react-synthesis, native-thinking-synthesis)
  - For synthesis contexts: Use `investigation_history` field (rich conversation history)
  - For non-synthesis contexts: Use `complete_conversation_history` (backward compatible)

### 5. Stage Execution in AlertService ([backend/tarsy/services/alert_service.py](backend/tarsy/services/alert_service.py))

- Create `_execute_parallel_agents()` method for multi-agent parallelism:
  - Use `asyncio.gather()` with `return_exceptions=True` for concurrent execution
  - Create separate stage execution records for each parallel agent (parent-child relationship)
  - Handle per-agent LLM provider resolution
  - Handle per-agent iteration strategy resolution
  - Track individual agent metadata (timing, token usage, errors, strategy used)
  - Aggregate results into `ParallelStageResult` with `ParallelStageMetadata`
  - Apply failure policy to determine overall stage status
- Create `_execute_replicated_agent()` method for simple replica parallelism:
  - Run same agent N times with identical configuration (for redundancy)
  - Label replicas as "AgentName-1", "AgentName-2", etc.
  - All replicas use stage-level `llm_provider` and `iteration_strategy`
  - For comparison with different configs, users should use `agents` list instead
- Update `_execute_chain_stages()` to:
  - Detect parallel stages (check for `agents` list or `replicas > 1`)
  - Route to appropriate executor (`_execute_parallel_agents()` or `_execute_replicated_agent()`)
  - **ALWAYS invoke synthesis immediately after parallel stage completion**
  - Replace parallel result with synthesized result in chain context
  - Pass synthesized result to next stages (not raw parallel data)
- Add `synthesize_parallel_results()` method in `ParallelStageExecutor`:
  - Automatically invoke synthesis agent after ANY parallel stage completion
  - Use stage's `synthesis` config (agent, iteration_strategy, llm_provider)
  - Default to `SynthesisAgent` with `synthesis` iteration strategy if no config provided
  - Resolve effective LLM provider: synthesis.llm_provider → stage.llm_provider → chain.llm_provider
  - Pass `ParallelStageResult` to synthesis agent
  - Return synthesized final analysis as `AgentExecutionResult`
- Update `_extract_final_analysis_from_stages()`:
  - Extract from synthesis stage result if present
  - Otherwise: extract from last stage as normal

### 6. Database Schema ([backend/tarsy/models/db_models.py](backend/tarsy/models/db_models.py))

- Add `parent_stage_execution_id: Optional[str] `to `StageExecution` model for parallel execution grouping
- Add `parallel_index: int` field to track position in parallel group (0 for single stages, 1-N for parallel)
- Add `parallel_type: str` field: `single`, `multi_agent`, `replica`
- Update `StageExecution` queries to support parent-child relationships
- Add index on `parent_stage_execution_id` for efficient hierarchical queries

### 7. History Service Updates ([backend/tarsy/services/history_service.py](backend/tarsy/services/history_service.py))

- Add `create_parallel_stage_execution()` to create parent stage with children:
  - Create parent record with `parallel_type` set
  - Create N child records with `parent_stage_execution_id` pointing to parent
  - Set `parallel_index` on each child (1, 2, 3, ...)
- Update `get_stage_executions()` to return nested structure for parallel stages:
  - Parent stage includes `parallel_executions: List[StageExecution]` field with children embedded
  - Maps directly to UI pattern (parent stage → tabs for child executions)
  - Reduces frontend complexity by providing ready-to-render structure
- Add `get_parallel_stage_children(parent_id: str)` to retrieve child executions

### 8. Prompt Building for Parallel Results ([backend/tarsy/agents/prompts/](backend/tarsy/agents/prompts/))

- Update `PromptBuilder` to format `ParallelStageResult` for next stages:
  - Method: `format_parallel_stage_results(parallel_result: ParallelStageResult) -> str`
  - For multi-agent: Organize with clear sections and headers (e.g., "## Kubernetes Investigation", "## VM Investigation")
  - For replicas: Label clearly (e.g., "## Run 1 (openai)", "## Run 2 (anthropic)", "## Run 3 (gemini)") - NO pre-analysis
  - Include metadata for each execution: timing, status, LLM provider, iteration strategy
  - For synthesis strategies: Use `investigation_history` field (rich conversation with tool observations)
  - For non-synthesis: Use `complete_conversation_history` (last assistant message)
  - Present raw results - let the next agent (SynthesisAgent) do all analysis and comparison
- Add specific prompt template for `SynthesisAgent`:
  - "You are the Incident Commander analyzing the alert using data from N parallel investigations..."
  - "Critically evaluate the quality of each investigation - prioritize results with strong evidence and reasoning"
  - "Your task: synthesize the best findings into a unified analysis of the original issue..."
- Update existing stage transition prompts to handle `ParallelStageResult` in previous stages
- Update iteration controllers to generate `investigation_history`:
  - Add `build_synthesis_conversation()` method to `IterationController` base class
  - Implement in `ReactController` and `NativeThinkingController`
  - Exclude system messages and first user message (alert data already in context)
  - Include all assistant messages, tool observations, and final answers

### 9. Dashboard Stage Display - Backend ([backend/tarsy/controllers/history_controller.py](backend/tarsy/controllers/history_controller.py))

- Update `GET /api/sessions/{session_id}/stages` endpoint response:
  - Add `parallel_type: Optional[str]` field to stage execution response
  - Add `parallel_executions: Optional[List[StageExecution]]` for child executions
  - Add `is_parallel: bool` flag for frontend detection
  - Include individual agent metadata in each parallel execution
- Update `GET /api/sessions/{session_id}/stages/{stage_id}` for detailed parallel stage view

### 10. Dashboard Stage Display - Frontend ([dashboard/src/components/](dashboard/src/components/))

- Create `ParallelStageExecutionTabs.tsx` component:
  - Use Material-UI `Tabs` component for switching between parallel executions
  - Tab labels: `{agent_name} ({llm_provider})` or `{agent_name}-{replica_index} ({llm_provider})`
  - Each tab shows individual agent's timeline (tools, iterations, results)
  - Parent stage shows aggregate status badge (e.g., "2/3 succeeded")
  - Display `ParallelStageMetadata` in expandable section (timing, providers, iteration counts)
- Update stage list component to detect parallel stages:
  - Show visual indicator (e.g., icon with "2x" or "3x" badge)
  - Show aggregate status for parent stage
- Update stage detail view to render `ParallelStageExecutionTabs` when `is_parallel=true`

### 11. Configuration Validation ([backend/tarsy/config/agent_config.py](backend/tarsy/config/agent_config.py))

- Add validation for `agents` list:
    - Minimum 2 items (parallelism with 1 agent doesn't make sense)
    - All agent names must be valid (exist in registry or as built-ins)
    - Can include duplicate agent names (for running same agent with different configs)
- Add validation for `replicas`:
    - Must be ≥1, default to 1
    - If `replicas > 1`, `agents` list must not be present
    - Replicas inherit stage-level `llm_provider` and `iteration_strategy` if specified
- Add validation for `failure_policy`:
    - Must be one of: "all", "any"
- Ensure backward compatibility: single `agent` field still works, no breaking changes

### 12. Testing

- **Unit Tests**
- **Integration Tests**
- **E2E Tests**
- **Dashboard Tests**

### 13. Documentation


## Key Design Decisions

1. **Backward Compatibility**: Existing single `agent` configurations continue to work unchanged
2. **Explicit Parallelism**: Only use parallelism when explicitly configured (no automatic detection)
3. **Two Parallel Modes**:
    - **Simple replicas**: `agent` + `replicas: N` → same agent, same config, N times (redundancy)
    - **Comparison**: `agents: [...]` → explicit per-agent config for LLM/strategy variety (A/B testing)
4. **No Array Configs**: Removed `llm_providers` and `iteration_strategies` arrays - use `agents` list for variety
5. **Partial Success**: Default to `all` policy (strict), but allow `any` for resilient pipelines
6. **Pure Data Container**: `ParallelStageResult` is raw data only, no synthesis (Option B)
7. **Automatic Synthesis**: Built-in `SynthesisAgent` auto-invoked for final parallel stages, critically evaluates result quality
8. **Configurable Synthesis**: Optional `synthesis` field on stages allows configuring:
    - Agent to use for synthesis (default: `SynthesisAgent`)
    - Iteration strategy: `react-synthesis` (default) or `native-thinking-synthesis` for Gemini thinking
    - LLM provider override for synthesis (inherits from stage/chain if not specified)
9. **Rich Investigation History**: New `investigation_history` field captures full conversation (minus system/first user message) for synthesis strategies, while `complete_conversation_history` preserved for backward compatibility
10. **User-Accessible Synthesis**: Built-in `SynthesisAgent` can also be explicitly used in chains
11. **Database Hierarchy**: Parent-child relationship for stage executions enables clean queries and UI grouping
12. **Consistent Naming**: Use `name` field in `ParallelAgentConfig` (not `agent`) for consistency with stage naming
13. **Metadata Separation**: Configuration metadata vs execution metadata clearly separated in `ParallelStageMetadata`
14. **Pause/Resume Compatibility**: 
    - When any parallel agent pauses, entire stage marked as PAUSED (pause priority over success/failure)
    - Other agents allowed to complete naturally (preserve their work)
    - Resume re-executes only paused agents (completed/failed results preserved)
    - Multiple pause/resume cycles supported

## Files to Modify

### Core Models

- [`backend/tarsy/models/agent_config.py`](backend/tarsy/models/agent_config.py)
- [`backend/tarsy/models/agent_execution_result.py`](backend/tarsy/models/agent_execution_result.py)
- [`backend/tarsy/models/processing_context.py`](backend/tarsy/models/processing_context.py)
- [`backend/tarsy/models/db_models.py`](backend/tarsy/models/db_models.py)

### Configuration

- Update [`backend/tarsy/config/builtin_config.py`](backend/tarsy/config/builtin_config.py) - Add SynthesisAgent definition
- Update [`backend/tarsy/models/constants.py`](backend/tarsy/models/constants.py) - Add synthesis iteration strategies

### Services

- [`backend/tarsy/services/alert_service.py`](backend/tarsy/services/alert_service.py)
- [`backend/tarsy/services/history_service.py`](backend/tarsy/services/history_service.py)
- [`backend/tarsy/services/chain_registry.py`](backend/tarsy/services/chain_registry.py)

### Agents & Iteration Controllers

- [`backend/tarsy/agents/base_agent.py`](backend/tarsy/agents/base_agent.py) - Generate investigation_history field
- [`backend/tarsy/agents/iteration_controllers/base_controller.py`](backend/tarsy/agents/iteration_controllers/base_controller.py) - Add build_synthesis_conversation method
- Create [`backend/tarsy/agents/iteration_controllers/react_synthesis_controller.py`](backend/tarsy/agents/iteration_controllers/react_synthesis_controller.py) - ReAct synthesis controller
- Create [`backend/tarsy/agents/iteration_controllers/native_thinking_synthesis_controller.py`](backend/tarsy/agents/iteration_controllers/native_thinking_synthesis_controller.py) - Gemini synthesis controller
- Update [`backend/tarsy/agents/iteration_controllers/__init__.py`](backend/tarsy/agents/iteration_controllers/__init__.py) - Register synthesis controllers

### Prompts

- [`backend/tarsy/agents/prompts/prompt_builder.py`](backend/tarsy/agents/prompts/prompt_builder.py)

### API & Controllers

- [`backend/tarsy/controllers/history_controller.py`](backend/tarsy/controllers/history_controller.py)

### Dashboard Components

- Create `dashboard/src/components/AlertHistory/ParallelStageExecutionTabs.tsx`
- Update stage timeline/detail components (TBD based on current structure)

### Configuration & Documentation

- [`config/agents.yaml`](config/agents.yaml) - Add example parallel stage configurations
- [`docs/architecture/agent-chains.md`](docs/architecture/agent-chains.md) - Document parallel execution
- [`README.md`](README.md) - Update with parallel stage examples

### Testing

- Unit tests for all new models and validation logic
- Integration tests for parallel execution in `AlertService`
- E2E tests for full chain execution with parallel stages
- Dashboard component tests for `ParallelStageExecutionTabs`

## Implementation Phases

### Phase 1: Core Data Models & Configuration

**Goal**: Establish foundational data structures and SynthesisAgent configuration

**Tasks**:
- ✅ TODO `data-models`: Add `ParallelAgentConfig`, `ParallelStageConfig` models and validation
- ✅ TODO `parallel-result`: Create `ParallelStageResult`, `AgentExecutionMetadata`, `ParallelStageMetadata` models
- ✅ TODO `context-updates`: Update `ChainContext` to handle `ParallelStageResult` in previous stages
- ✅ TODO `config-validation`: Add YAML schema validation for parallel stage configurations
- ✅ TODO `synthesis-agent`: Add `SynthesisAgent` entry to `BUILTIN_AGENTS` in `builtin_config.py`

**Dependencies**: None (foundational work)

**Deliverables**:
- Data models in `backend/tarsy/models/agent_config.py` and `agent_execution_result.py`
- Updated `ChainContext` in `backend/tarsy/models/processing_context.py`
- Configuration validation logic
- `SynthesisAgent` configuration in `backend/tarsy/config/builtin_config.py`

**Impact on Tests**: ⚠️ Will break existing tests that depend on `ChainContext` structure - **do not fix yet**

---

### Phase 2: Parallel Execution Engine & Prompts

**Goal**: Implement concurrent agent execution with result formatting

**Tasks**:
- ✅ TODO `execute-parallel`: Implement parallel execution logic in `AlertService`
  - Detect parallel vs single-agent stages
  - Execute agents concurrently using asyncio
  - Aggregate results into `ParallelStageResult`
  - Handle partial success policies
- ✅ TODO `auto-synthesis`: Add automatic SynthesisAgent invocation for final parallel stages
- ✅ TODO `prompt-updates`: Update `PromptBuilder` to format `ParallelStageResult`
  - Implement `format_parallel_stage_results()` method
  - Add SynthesisAgent prompt template

**Dependencies**: Phase 1 (data models, SynthesisAgent config)

**Deliverables**:
- Updated `AlertService._execute_stage()` with parallel execution support
- Automatic SynthesisAgent synthesis logic
- Updated `backend/tarsy/agents/prompts/prompt_builder.py`

**Impact on Tests**: ⚠️ Will break existing `AlertService` and `PromptBuilder` tests - **do not fix yet**

---

### Phase 3: Database Schema & Persistence

**Goal**: Persist parallel execution results with parent-child relationships

**Tasks**:
- ✅ TODO `db-schema`: Add parent-child stage execution schema
  - Add `parent_execution_id` foreign key to `stage_executions` table
  - Create database migration
- ✅ TODO `history-service`: Update `HistoryService` to support parallel stages
  - Save parent stage execution
  - Save child executions with parent reference
  - Query methods for retrieving parent-child hierarchies

**Dependencies**: Phase 2 (parallel execution generates data to persist)

**Deliverables**:
- Database migration for `stage_executions` table
- Updated `HistoryService` with parent-child support
- Updated `HistoryRepository` query methods

**Impact on Tests**: ⚠️ Will break existing `HistoryService` and repository tests - **do not fix yet**

---

### Phase 4: Dashboard UI

**Goal**: Display parallel stage executions in the dashboard

**Tasks**:
- ✅ TODO `dashboard-tabs`: Create `ParallelStageExecutionTabs` component
  - Tab-based interface for parallel executions
  - Display agent names, LLM providers, iteration strategies
  - Show timing, status, and metadata for each execution
  - Handle both multi-agent and replica scenarios

**Dependencies**: Phases 1-3

**Deliverables**:
- `dashboard/src/components/AlertHistory/ParallelStageExecutionTabs.tsx`
- Updated stage detail views to integrate tabs component

**Impact on Tests**: ⚠️ Dashboard component tests may need updates

---

### Phase 5: Fix Tests & Add Coverage

**Goal**: Fix all broken tests and add comprehensive test coverage for parallel execution

**Tasks**:
- ✅ TODO `testing`: Fix broken tests and add coverage for parallel execution
  - **Fix broken tests**: `ChainContext`, `AlertService`, `PromptBuilder`, `HistoryService`, API controllers
  - **Unit tests**: Model validation, serialization, configuration validation, prompt formatting
  - **Integration tests**: Parallel execution in `AlertService`, database operations, API endpoints
  - **E2E tests**: Full chain execution with parallel stages (both replicas and multi-agent)
  - **Dashboard tests**: Component tests for `ParallelStageExecutionTabs`

**Dependencies**: Phases 1-4 (all implementation complete, now we fix and extend tests)

**Deliverables**:
- All existing tests passing
- Comprehensive test coverage for new parallel execution functionality (>80% coverage)

**Testing Strategy**:
- Start by fixing tests broken by `ChainContext` changes (Phase 1 impact)
- Then fix `AlertService`, `PromptBuilder`, `HistoryService` tests
- Finally add new tests for parallel-specific functionality

---

### Phase 6: Documentation & Examples

**Goal**: Complete user-facing documentation and configuration examples

**Tasks**:
- ✅ TODO `documentation`: Update project documentation
  - Configuration examples in `config/agents.yaml`
  - Architecture documentation for parallel execution
  - README examples for common use cases (replicas vs multi-agent)
  - Update API documentation for nested parallel responses

**Dependencies**: Phases 1-5 (feature is tested and stable)

**Deliverables**:
- Updated configuration examples demonstrating both parallelism modes
- Architecture documentation explaining parallel execution design
- README with practical use cases (redundancy, A/B testing, multi-perspective analysis)
- API documentation updates