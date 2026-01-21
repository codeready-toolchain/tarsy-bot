/**
 * Status message mapping utilities.
 * 
 * Maps backend event data to user-friendly progress status messages.
 * Supports regular stages, parallel stages, synthesis, and executive summary.
 */

import { SESSION_EVENTS, STAGE_EVENTS } from './eventTypes';

/**
 * Progress phase constants (matches backend ProgressPhase enum).
 */
export const ProgressPhase = {
  INVESTIGATING: 'investigating',
  GATHERING_INFO: 'gathering_info',  // MCP tool execution (collecting data from systems)
  SYNTHESIZING: 'synthesizing',
  DISTILLING: 'distilling',          // MCP tool result summarization
  CONCLUDING: 'concluding',          // Forced conclusion at iteration limit
  FINALIZING: 'finalizing',          // Executive summary generation
} as const;

/**
 * Type for progress phase values.
 */
export type ProgressPhaseValue = typeof ProgressPhase[keyof typeof ProgressPhase];

/**
 * Stage name constants.
 */
export const StageName = {
  SYNTHESIS: 'synthesis',
} as const;

/**
 * Progress status message constants.
 */
export const ProgressStatusMessage = {
  INVESTIGATING: 'Investigating...',
  GATHERING_INFO: 'Gathering information...',  // MCP tool execution (collecting data from systems)
  SYNTHESIZING: 'Synthesizing...',
  DISTILLING: 'Distilling...',        // MCP tool result summarization
  CONCLUDING: 'Concluding...',        // Forced conclusion at iteration limit
  FINALIZING: 'Finalizing...',        // Executive summary generation
  PROCESSING: 'Processing...',
  // Terminal status display strings (for UI display in progress cards)
  COMPLETED: 'Completed',
  FAILED: 'Failed',
  CANCELLED: 'Cancelled',
  TIMED_OUT: 'Timed Out',
} as const;

/**
 * Terminal progress status constants for checking if an agent has finished.
 * These are the display strings used in the UI progress cards.
 */
export const TERMINAL_PROGRESS_STATUSES = [
  ProgressStatusMessage.COMPLETED,
  ProgressStatusMessage.FAILED,
  ProgressStatusMessage.CANCELLED,
  ProgressStatusMessage.TIMED_OUT,
] as const;

/**
 * Helper to check if a progress status is terminal (agent finished).
 * @param status - Progress status string to check
 * @returns True if the status indicates the agent has finished
 */
export function isTerminalProgressStatus(status: string): boolean {
  return TERMINAL_PROGRESS_STATUSES.includes(status as any);
}

/**
 * Progress status with optional agent context for parallel execution.
 */
export interface ProgressStatusInfo {
  status: string;
  stageExecutionId?: string;
  parentStageExecutionId?: string;
  parallelIndex?: number;
  agentName?: string;
}

/**
 * Maps backend event data to user-friendly progress status messages.
 * Supports regular stages, parallel stages, synthesis, and executive summary.
 * 
 * @param event - WebSocket event data
 * @returns User-friendly status message (legacy) or status info with agent context
 */
export function mapEventToProgressStatus(event: any): string;
export function mapEventToProgressStatus(event: any, includeAgentContext: true): ProgressStatusInfo;
export function mapEventToProgressStatus(event: any, includeAgentContext?: boolean): string | ProgressStatusInfo {
  const eventType = event.type || '';
  let statusMessage: string = ProgressStatusMessage.PROCESSING;
  
  // Explicit progress update event (e.g., distilling, finalizing)
  if (eventType === SESSION_EVENTS.PROGRESS_UPDATE) {
    const phase = event.phase || event.data?.phase;
    if (phase === ProgressPhase.CONCLUDING) statusMessage = ProgressStatusMessage.CONCLUDING;        // Forced conclusion at iteration limit
    else if (phase === ProgressPhase.DISTILLING) statusMessage = ProgressStatusMessage.DISTILLING;        // MCP tool result summarization
    else if (phase === ProgressPhase.FINALIZING) statusMessage = ProgressStatusMessage.FINALIZING;        // Executive summary generation
    else if (phase === ProgressPhase.SYNTHESIZING) statusMessage = ProgressStatusMessage.SYNTHESIZING;
    else if (phase === ProgressPhase.GATHERING_INFO) statusMessage = ProgressStatusMessage.GATHERING_INFO;  // MCP tool execution
    else if (phase === ProgressPhase.INVESTIGATING) statusMessage = ProgressStatusMessage.INVESTIGATING;
  }
  
  // Stage-based detection
  else if (eventType === STAGE_EVENTS.STARTED) {
    const stageName = event.stage_name || event.data?.stage_name;
    
    // Synthesis stage
    if (stageName === StageName.SYNTHESIS) statusMessage = ProgressStatusMessage.SYNTHESIZING;
    // Any other stage (including parallel)
    else statusMessage = ProgressStatusMessage.INVESTIGATING;
  }
  
  // Return with agent context if requested
  if (includeAgentContext) {
    return {
      status: statusMessage,
      // Use same fallback logic as completion events: stage_execution_id || stage_id
      stageExecutionId: event.stage_execution_id || event.stage_id,
      parentStageExecutionId: event.parent_stage_execution_id,
      parallelIndex: event.parallel_index,
      agentName: event.agent_name
    };
  }
  
  // Legacy return: just the status string
  return statusMessage;
}

