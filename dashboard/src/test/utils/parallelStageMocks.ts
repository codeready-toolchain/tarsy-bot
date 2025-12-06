/**
 * Test utilities for parallel stage execution testing
 * Provides mock data factories for creating test fixtures
 */

import type { StageExecution } from '../../types';
import { STAGE_STATUS, type StageStatus } from '../../utils/statusConstants';
import { PARALLEL_TYPE } from '../../utils/parallelConstants';

/**
 * Create a mock parent stage with parallel executions
 */
export function createMockParallelStage(overrides?: Partial<StageExecution>): StageExecution {
  return {
    execution_id: 'parent-exec-1',
    session_id: 'session-1',
    stage_id: 'investigation',
    stage_index: 0,
    stage_name: 'Investigation',
    agent: 'ParallelInvestigator',
    status: STAGE_STATUS.COMPLETED,
    started_at_us: 1700000000000000,
    completed_at_us: 1700000060000000,
    duration_ms: 60000,
    stage_output: null,
    error_message: null,
    llm_interactions: [],
    mcp_communications: [],
    llm_interaction_count: 0,
    mcp_communication_count: 0,
    total_interactions: 0,
    stage_interactions_duration_ms: null,
    chronological_interactions: [],
    parallel_type: PARALLEL_TYPE.MULTI_AGENT,
    parallel_index: 0,
    parent_stage_execution_id: null,
    parallel_executions: [],
    ...overrides,
  };
}

/**
 * Create a mock child execution for parallel stages
 */
export function createMockChildExecution(
  index: number,
  agent: string,
  status: StageStatus,
  overrides?: Partial<StageExecution>
): StageExecution {
  return {
    execution_id: `child-exec-${index}`,
    session_id: 'session-1',
    stage_id: 'investigation',
    stage_index: 0,
    stage_name: 'Investigation',
    agent,
    status,
    started_at_us: 1700000000000000 + index * 1000,
    completed_at_us: status === STAGE_STATUS.COMPLETED ? 1700000030000000 + index * 1000 : null,
    duration_ms: status === STAGE_STATUS.COMPLETED ? 30000 : null,
    stage_output: null,
    error_message: status === STAGE_STATUS.FAILED ? 'Execution failed' : null,
    llm_interactions: [],
    mcp_communications: [],
    llm_interaction_count: 2,
    mcp_communication_count: 1,
    total_interactions: 3,
    stage_interactions_duration_ms: 5000,
    chronological_interactions: [],
    stage_input_tokens: 100,
    stage_output_tokens: 50,
    stage_total_tokens: 150,
    parallel_type: PARALLEL_TYPE.MULTI_AGENT,
    parallel_index: index,
    parent_stage_execution_id: 'parent-exec-1',
    parallel_executions: [],
    ...overrides,
  };
}

/**
 * Create a complete multi-agent parallel stage with children
 */
export function createMultiAgentParallelStage(
  agents: Array<{ name: string; status: StageStatus }> = [
    { name: 'KubernetesAgent', status: STAGE_STATUS.COMPLETED },
    { name: 'VMAgent', status: STAGE_STATUS.COMPLETED },
    { name: 'NetworkAgent', status: STAGE_STATUS.FAILED },
  ]
): StageExecution {
  const children = agents.map((agent, index) =>
    createMockChildExecution(index + 1, agent.name, agent.status)
  );

  return createMockParallelStage({
    parallel_type: PARALLEL_TYPE.MULTI_AGENT,
    parallel_executions: children,
  });
}

/**
 * Create a replica parallel stage (same agent, multiple executions)
 */
export function createReplicaParallelStage(
  agentName: string = 'KubernetesAgent',
  replicaCount: number = 3,
  allCompleted: boolean = true
): StageExecution {
  const children = Array.from({ length: replicaCount }, (_, index) =>
    createMockChildExecution(
      index + 1,
      agentName,
      allCompleted ? STAGE_STATUS.COMPLETED : (index === 0 ? STAGE_STATUS.FAILED : STAGE_STATUS.COMPLETED),
      { parallel_type: PARALLEL_TYPE.REPLICA }
    )
  );

  return createMockParallelStage({
    parallel_type: PARALLEL_TYPE.REPLICA,
    parallel_executions: children,
  });
}

/**
 * Create a single (non-parallel) stage for comparison testing
 */
export function createSingleStage(overrides?: Partial<StageExecution>): StageExecution {
  return {
    execution_id: 'single-exec-1',
    session_id: 'session-1',
    stage_id: 'analysis',
    stage_index: 0,
    stage_name: 'Analysis',
    agent: 'AnalysisAgent',
    status: STAGE_STATUS.COMPLETED,
    started_at_us: 1700000000000000,
    completed_at_us: 1700000030000000,
    duration_ms: 30000,
    stage_output: { result: 'Analysis complete' },
    error_message: null,
    llm_interactions: [],
    mcp_communications: [],
    llm_interaction_count: 5,
    mcp_communication_count: 3,
    total_interactions: 8,
    stage_interactions_duration_ms: 15000,
    chronological_interactions: [],
    stage_input_tokens: 200,
    stage_output_tokens: 100,
    stage_total_tokens: 300,
    parallel_type: PARALLEL_TYPE.SINGLE,
    parallel_index: 0,
    parent_stage_execution_id: null,
    parallel_executions: [],
    ...overrides,
  };
}

