/**
 * Utility functions for creating placeholder parallel agent stages
 * Placeholders are shown immediately when a parallel parent stage starts,
 * then replaced with real data as individual child stages begin executing
 */

import type { StageExecution } from '../types';
import { STAGE_STATUS } from './statusConstants';
import { PARALLEL_TYPE } from './parallelConstants';

/**
 * Create placeholder stages for parallel agents
 * 
 * @param parentStage - The parent parallel stage
 * @param expectedCount - Number of expected parallel children
 * @returns Array of placeholder stage objects
 */
export function createParallelPlaceholders(
  parentStage: StageExecution,
  expectedCount: number
): StageExecution[] {
  if (!parentStage.parallel_type || expectedCount <= 0) {
    return [];
  }

  const placeholders: StageExecution[] = [];
  
  for (let i = 0; i < expectedCount; i++) {
    const placeholderName = parentStage.parallel_type === PARALLEL_TYPE.REPLICA
      ? `${parentStage.agent}-${i + 1}` // Replica naming: Agent-1, Agent-2, ...
      : `Agent ${i + 1}`; // Multi-agent: Will be replaced with real agent name
    
    placeholders.push({
      execution_id: `placeholder-${parentStage.execution_id}-${i}`,
      session_id: parentStage.session_id,
      stage_id: `${parentStage.stage_id}-placeholder-${i}`,
      stage_index: parentStage.stage_index,
      stage_name: `${parentStage.stage_name} - ${placeholderName}`,
      agent: placeholderName,
      status: STAGE_STATUS.PENDING,
      started_at_us: null,
      completed_at_us: null,
      duration_ms: null,
      stage_output: null,
      error_message: null,
      current_iteration: null,
      parent_stage_execution_id: parentStage.execution_id,
      parallel_index: i + 1,
      parallel_type: parentStage.parallel_type,
      expected_parallel_count: null,
      // Required arrays for StageExecution interface
      llm_interactions: [],
      mcp_communications: [],
      llm_interaction_count: 0,
      mcp_communication_count: 0,
      total_interactions: 0,
      stage_interactions_duration_ms: null,
      chronological_interactions: [],
      // Mark as placeholder for UI rendering
      is_placeholder: true,
    } as StageExecution & { is_placeholder: boolean });
  }
  
  return placeholders;
}

/**
 * Check if a stage is a placeholder
 */
export function isPlaceholderStage(stage: StageExecution): boolean {
  return (stage as any).is_placeholder === true;
}

/**
 * Replace a placeholder with real stage data
 * Finds the matching placeholder and returns the real stage
 * 
 * @param stages - Current stages array
 * @param realStage - Real stage data from backend
 * @returns Updated stages array with placeholder replaced
 */
export function replacePlaceholderWithRealStage(
  stages: StageExecution[],
  realStage: StageExecution
): StageExecution[] {
  // Find matching placeholder by parent_stage_execution_id and parallel_index
  const placeholderIndex = stages.findIndex(
    s => 
      isPlaceholderStage(s) &&
      s.parent_stage_execution_id === realStage.parent_stage_execution_id &&
      s.parallel_index === realStage.parallel_index
  );
  
  if (placeholderIndex === -1) {
    // No placeholder found - this might be a late-arriving stage
    // Add it in the correct position (after parent, sorted by parallel_index)
    const parentIndex = stages.findIndex(
      s => s.execution_id === realStage.parent_stage_execution_id
    );
    
    if (parentIndex === -1) {
      // Parent not found, add at end
      return [...stages, realStage];
    }
    
    // Find insertion point: after parent and any existing children with lower parallel_index
    let insertIndex = parentIndex + 1;
    while (insertIndex < stages.length) {
      const currentStage = stages[insertIndex];
      if (
        !currentStage ||
        currentStage.parent_stage_execution_id !== realStage.parent_stage_execution_id ||
        !currentStage.parallel_index ||
        !realStage.parallel_index ||
        currentStage.parallel_index >= realStage.parallel_index
      ) {
        break;
      }
      insertIndex++;
    }
    
    return [
      ...stages.slice(0, insertIndex),
      realStage,
      ...stages.slice(insertIndex)
    ];
  }
  
  // Replace placeholder with real stage
  return [
    ...stages.slice(0, placeholderIndex),
    realStage,
    ...stages.slice(placeholderIndex + 1)
  ];
}

/**
 * Remove all placeholders for a given parent stage
 * Used when parent stage completes or fails
 */
export function removePlaceholdersForParent(
  stages: StageExecution[],
  parentExecutionId: string
): StageExecution[] {
  return stages.filter(
    s => !(isPlaceholderStage(s) && s.parent_stage_execution_id === parentExecutionId)
  );
}

