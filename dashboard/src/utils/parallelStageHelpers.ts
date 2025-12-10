import { STAGE_STATUS } from './statusConstants';
import { PARALLEL_TYPE, isParallelType } from './parallelConstants';

/**
 * Utility functions for working with parallel stage executions
 */

/**
 * Minimal interface for stages with parallel execution support
 * Can be satisfied by both StageExecution and StageConversation
 */
interface ParallelStageBase {
  agent: string;
  status: string;
  parallel_type?: string;
  parallel_executions?: ParallelStageBase[];
  stage_input_tokens?: number | null;
  stage_output_tokens?: number | null;
  stage_total_tokens?: number | null;
  duration_ms?: number | null;
  llm_interaction_count?: number;
  mcp_communication_count?: number;
}

/**
 * Check if a stage has parallel executions
 */
export function isParallelStage(stage: ParallelStageBase): boolean {
  return (
    (stage.parallel_executions !== undefined && 
     stage.parallel_executions !== null && 
     stage.parallel_executions.length > 0) ||
    isParallelType(stage.parallel_type)
  );
}

/**
 * Generate tab label for a parallel execution
 * For replica mode, appends replica number to agent name
 * For multi-agent mode, uses agent name directly from backend
 */
export function getParallelStageLabel(
  stage: ParallelStageBase, 
  index: number, 
  parallelType: string = PARALLEL_TYPE.MULTI_AGENT
): string {
  // For replica mode, if the agent name doesn't already have a replica number,
  // append it using 1-based indexing (index + 1)
  if (parallelType === PARALLEL_TYPE.REPLICA) {
    // Check if agent name already has a replica number (e.g., "Agent-1")
    if (stage.agent.match(/-\d+$/)) {
      return stage.agent;
    }
    // Add 1-based replica number
    return `${stage.agent}-${index + 1}`;
  }
  
  // For multi-agent mode, return agent name directly
  return stage.agent;
}

/**
 * Calculate aggregate status from parallel executions
 * Returns a human-readable status like "2/3 Completed" or "All Succeeded"
 * 
 * Priority order (matching backend logic):
 * 1. If any paused -> Show paused count prominently
 * 2. All completed -> "All Completed"
 * 3. All failed -> "All Failed"
 * 4. Mixed states -> Show primary status with counts
 */
export function getAggregateStatus(parallelExecutions: ParallelStageBase[]): string {
  if (!parallelExecutions || parallelExecutions.length === 0) {
    return 'No executions';
  }
  
  const counts = getSuccessFailureCounts(parallelExecutions);
  const total = parallelExecutions.length;
  
  // PAUSED takes priority (matching backend behavior where any paused agent pauses the stage)
  if (counts.paused > 0) {
    if (counts.paused === total) {
      return 'All Paused';
    } else if (counts.completed > 0) {
      return `${counts.completed} Completed, ${counts.paused} Paused`;
    } else {
      return `${counts.paused}/${total} Paused`;
    }
  }
  
  // No paused agents - original logic
  if (counts.completed === total) {
    return 'All Completed';
  } else if (counts.failed === total) {
    return 'All Failed';
  } else if (counts.completed > 0) {
    return `${counts.completed}/${total} Completed`;
  } else if (counts.active > 0) {
    return `${counts.active}/${total} Running`;
  } else {
    return `${counts.pending}/${total} Pending`;
  }
}

/**
 * Get success and failure counts from parallel executions
 */
export function getSuccessFailureCounts(parallelExecutions: ParallelStageBase[]): {
  completed: number;
  failed: number;
  active: number;
  pending: number;
  paused: number;
  total: number;
} {
  const counts = {
    completed: 0,
    failed: 0,
    active: 0,
    pending: 0,
    paused: 0,
    total: parallelExecutions.length
  };
  
  for (const execution of parallelExecutions) {
    switch (execution.status) {
      case STAGE_STATUS.COMPLETED:
        counts.completed++;
        break;
      case STAGE_STATUS.FAILED:
        counts.failed++;
        break;
      case STAGE_STATUS.ACTIVE:
        counts.active++;
        break;
      case STAGE_STATUS.PENDING:
        counts.pending++;
        break;
      case STAGE_STATUS.PAUSED:
        counts.paused++;
        break;
    }
  }
  
  return counts;
}

/**
 * Calculate total token usage across all parallel executions
 */
export function getTotalTokenUsage(parallelExecutions: ParallelStageBase[]): {
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
} {
  let inputTokens = 0;
  let outputTokens = 0;
  let totalTokens = 0;
  let hasAnyTokenData = false;
  
  for (const execution of parallelExecutions) {
    if (execution.stage_input_tokens !== null && execution.stage_input_tokens !== undefined) {
      inputTokens += execution.stage_input_tokens;
      hasAnyTokenData = true;
    }
    if (execution.stage_output_tokens !== null && execution.stage_output_tokens !== undefined) {
      outputTokens += execution.stage_output_tokens;
      hasAnyTokenData = true;
    }
    if (execution.stage_total_tokens !== null && execution.stage_total_tokens !== undefined) {
      totalTokens += execution.stage_total_tokens;
      hasAnyTokenData = true;
    }
  }
  
  return hasAnyTokenData ? {
    input_tokens: inputTokens > 0 ? inputTokens : null,
    output_tokens: outputTokens > 0 ? outputTokens : null,
    total_tokens: totalTokens > 0 ? totalTokens : null
  } : {
    input_tokens: null,
    output_tokens: null,
    total_tokens: null
  };
}

/**
 * Get aggregate duration from parallel executions
 * Returns the maximum duration (parallel executions run concurrently)
 */
export function getAggregateDuration(parallelExecutions: ParallelStageBase[]): number | null {
  let maxDuration = 0;
  let hasAnyDuration = false;
  
  for (const execution of parallelExecutions) {
    if (execution.duration_ms !== null && execution.duration_ms !== undefined) {
      maxDuration = Math.max(maxDuration, execution.duration_ms);
      hasAnyDuration = true;
    }
  }
  
  return hasAnyDuration ? maxDuration : null;
}

/**
 * Get aggregate interaction counts from parallel executions
 */
export function getAggregateInteractionCounts(parallelExecutions: ParallelStageBase[]): {
  llm_count: number;
  mcp_count: number;
  total_count: number;
} {
  let llmCount = 0;
  let mcpCount = 0;
  
  for (const execution of parallelExecutions) {
    llmCount += execution.llm_interaction_count || 0;
    mcpCount += execution.mcp_communication_count || 0;
  }
  
  return {
    llm_count: llmCount,
    mcp_count: mcpCount,
    total_count: llmCount + mcpCount
  };
}

/**
 * Check if a session has any stages with parallel executions
 * Useful for showing indicators in session lists and headers
 */
export function sessionHasParallelStages(stages?: ParallelStageBase[]): boolean {
  if (!stages || stages.length === 0) {
    return false;
  }
  
  return stages.some(stage => isParallelStage(stage));
}

/**
 * Count total number of parallel stages in a session
 * Returns both count of stages with parallel execution and total parallel agents
 */
export function getParallelStageStats(stages?: ParallelStageBase[]): {
  parallelStageCount: number;
  totalParallelAgents: number;
} {
  if (!stages || stages.length === 0) {
    return { parallelStageCount: 0, totalParallelAgents: 0 };
  }
  
  let parallelStageCount = 0;
  let totalParallelAgents = 0;
  
  for (const stage of stages) {
    if (isParallelStage(stage)) {
      parallelStageCount++;
      if (stage.parallel_executions && stage.parallel_executions.length > 0) {
        totalParallelAgents += stage.parallel_executions.length;
      }
    }
  }
  
  return { parallelStageCount, totalParallelAgents };
}

