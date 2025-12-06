---
name: Parallel Agent Stages
overview: Implement parallel stage execution in agent chains with support for both multi-agent parallelism (different agents) and replica parallelism (same agent multiple times), with per-agent LLM provider selection, structured result aggregation, and automatic synthesis via built-in CommanderAgent.
todos:
  - id: data-models
    content: Add parallel stage configuration models and validation
    status: pending
  - id: parallel-result
    content: Create ParallelStageResult model with metadata structures
    status: pending
  - id: commander-agent
    content: Configure built-in CommanderAgent for parallel result synthesis
    status: pending
  - id: context-updates
    content: Update ChainContext to handle parallel stage results
    status: pending
  - id: db-schema
    content: Add parent-child stage execution database schema
    status: pending
  - id: execute-parallel
    content: Implement parallel execution in AlertService
    status: pending
  - id: auto-synthesis
    content: Add automatic CommanderAgent synthesis for final parallel stages
    status: pending
  - id: history-service
    content: Add parallel stage support to HistoryService
    status: pending
  - id: prompt-updates
    content: Update prompts to format parallel results for next stages
    status: pending
  - id: api-response
    content: Update API responses for parallel stage executions
    status: pending
  - id: dashboard-tabs
    content: Create parallel stage tabs component in dashboard
    status: pending
  - id: config-validation
    content: Add YAML configuration validation for parallel stages
    status: pending
  - id: testing
    content: Add unit, integration, and E2E tests for parallel execution
    status: pending
  - id: documentation
    content: Update configuration examples and architecture docs
    status: pending
---

# Parallel Agent Stages Implementation

## Overview

Add parallel execution capabilities to agent chains, supporting:

1. **Multi-agent parallelism**: Run different agents in parallel for independent domain investigation
2. **Simple replica parallelism**: Run same agent N times with identical config for accuracy via redundancy
3. **Comparison parallelism**: Run same agent multiple times with different LLM providers/strategies for A/B testing
4. **Per-agent configuration**: Each agent in `agents` list can specify its own LLM provider and iteration strategy
5. **Partial success**: Continue chain if at least one parallel execution succeeds
6. **Structured results**: Raw parallel outputs packaged for next stage consumption
7. **Automatic synthesis**: Built-in CommanderAgent synthesizes results when parallel stage is final

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
  
  - name: "command"
    agent: "CommanderAgent"                # Final analysis from parallel results (built-in)
```

### Replica Parallelism (Simple Redundancy)

```yaml
stages:
  - name: "analysis"
    agent: "kubernetes"
    replicas: 3                    # Run same agent 3 times with same config
    llm_provider: "openai"         # All replicas use same provider/strategy
    iteration_strategy: "react"
  
  - name: "command"
    agent: "CommanderAgent"        # Final analysis from all 3 parallel results
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
    agent: "CommanderAgent"
```

### Automatic Synthesis (No Explicit Judge)

```yaml
stages:
  - name: "investigation"
    agents:
      - name: "kubernetes"
      - name: "vm"
  # No follow-up stage → built-in CommanderAgent automatically synthesizes results
```

```yaml
stages:
  - name: "investigation"
    agent: "kubernetes"
    replicas: 3
  # No follow-up stage → built-in CommanderAgent automatically synthesizes results
```

## Result Handling Logic

### Case 1: Parallel Stage + Follow-up Stage

- Pass raw `ParallelStageResult` (pure data, no synthesis) to next stage
- Next stage (user's judge/analysis agent) performs all analysis

### Case 2: Parallel Stage is Final Stage

- Automatically invoke built-in `CommanderAgent` to synthesize results
- Generates unified final analysis from multiple parallel investigations

### Case 3: Single Agent Final Stage (Existing Behavior)

- Use agent's own final analysis (unchanged)

## Implementation Tasks

### 1. Data Models ([backend/tarsy/models/agent_config.py](backend/tarsy/models/agent_config.py))

- Add `ParallelAgentConfig` model for multi-agent stages with per-agent configuration:
  - `name: str` - agent identifier (changed from `agent` for consistency)
  - `llm_provider: Optional[str]` - optional LLM provider override for this agent
  - `iteration_strategy: Optional[str]` - optional iteration strategy override for this agent
- Add `replicas` field to `ChainStageConfigModel` with validation (≥1, default 1)
- Add `failure_policy` field: `Literal["all", "any"]` (default "all")
- Add `agents` field: `Optional[List[ParallelAgentConfig]]` as alternative to single `agent`
- Add validation: Either `agent` OR `agents` must be specified, not both
- Add validation: If `replicas > 1`, must use single `agent`, not `agents` list
- Add validation: Replicas with `agent` run with same config; use `agents` list for per-agent variety

### 2. Parallel Execution Results ([backend/tarsy/models/agent_execution_result.py](backend/tarsy/models/agent_execution_result.py))

- Create `AgentExecutionMetadata` model for individual agent execution details:
  - `agent_name: str` - e.g., "KubernetesAgent" or "KubernetesAgent-1" for replicas
  - `llm_provider: str` - provider used for this agent
  - `iteration_strategy: str` - strategy used (e.g., "react", "native-thinking", "react-stage")
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

### 3. Built-in CommanderAgent Configuration ([backend/tarsy/config/builtin_config.py](backend/tarsy/config/builtin_config.py))

- Add `CommanderAgent` entry to `BUILTIN_AGENTS` dictionary:
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
  - iteration_strategy: "react" (for structured analysis)
- Make user-accessible: Can be used explicitly in chains or automatically invoked

### 4. ChainContext Updates ([backend/tarsy/models/processing_context.py](backend/tarsy/models/processing_context.py))

- Update `stage_outputs` type to: `Dict[str, Union[AgentExecutionResult, ParallelStageResult]]`
- Add `get_previous_stage_results()` helper that handles both single and parallel results
- Add `is_parallel_stage(stage_name: str)` helper to check if a stage has parallel execution
- Add `get_last_stage_result()` helper for automatic synthesis logic

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
  - Handle `ParallelStageResult` status aggregation
- Add `_is_final_stage_parallel()` helper to check if last stage is parallel
- Add `_synthesize_parallel_results()` method:
  - Automatically invoke built-in `CommanderAgent` when parallel stage is final
  - Pass `ParallelStageResult` to CommanderAgent for synthesis
  - Return synthesized final analysis
- Update `_extract_final_analysis_from_stages()`:
  - Check if final stage is parallel
  - If yes and no follow-up stage: invoke automatic synthesis
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
  - Present raw results - let the next agent (CommanderAgent) do all analysis and comparison
- Add specific prompt template for `CommanderAgent`:
  - "You are the Incident Commander analyzing the alert using data from N parallel investigations..."
  - "Critically evaluate the quality of each investigation - prioritize results with strong evidence and reasoning"
  - "Your task: synthesize the best findings into a unified analysis of the original issue..."
- Update existing stage transition prompts to handle `ParallelStageResult` in previous stages

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
7. **Automatic Commander**: Built-in `CommanderAgent` auto-invoked for final parallel stages, critically evaluates result quality
8. **User-Accessible Commander**: Built-in `CommanderAgent` can also be explicitly used in chains
9. **Database Hierarchy**: Parent-child relationship for stage executions enables clean queries and UI grouping
10. **Consistent Naming**: Use `name` field in `ParallelAgentConfig` (not `agent`) for consistency with stage naming
11. **Metadata Separation**: Configuration metadata vs execution metadata clearly separated in `ParallelStageMetadata`

## Files to Modify

### Core Models

- [`backend/tarsy/models/agent_config.py`](backend/tarsy/models/agent_config.py)
- [`backend/tarsy/models/agent_execution_result.py`](backend/tarsy/models/agent_execution_result.py)
- [`backend/tarsy/models/processing_context.py`](backend/tarsy/models/processing_context.py)
- [`backend/tarsy/models/db_models.py`](backend/tarsy/models/db_models.py)

### Configuration

- Update [`backend/tarsy/config/builtin_config.py`](backend/tarsy/config/builtin_config.py) - Add CommanderAgent definition

### Services

- [`backend/tarsy/services/alert_service.py`](backend/tarsy/services/alert_service.py)
- [`backend/tarsy/services/history_service.py`](backend/tarsy/services/history_service.py)
- [`backend/tarsy/services/chain_registry.py`](backend/tarsy/services/chain_registry.py)

### Prompts

- [`backend/tarsy/agents/prompts/prompt_builder.py`](backend/tarsy/agents/prompts/prompt_builder.py)

### API & Controllers

- [`backend/tarsy/controllers/history_controller.py`](backend/tarsy/controllers/history_controller.py)

### Dashboard Components

- Create `dashboard/src/components/AlertHistory/ParallelStageExecutionTabs.tsx`
- Update stage timeline/detail components (TBD based on current structure)

### Configuration & Documentation

- TBD