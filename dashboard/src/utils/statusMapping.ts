/**
 * Status message mapping utilities.
 * 
 * Maps backend event data to user-friendly progress status messages.
 * Supports regular stages, parallel stages, synthesis, and executive summary.
 */

/**
 * Progress phase constants (matches backend ProgressPhase enum).
 */
export const ProgressPhase = {
  INVESTIGATING: 'investigating',
  SYNTHESIZING: 'synthesizing',
  DISTILLING: 'distilling',      // MCP tool result summarization
  CONCLUDING: 'concluding',      // Forced conclusion at iteration limit
  FINALIZING: 'finalizing',      // Executive summary generation
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
  SYNTHESIZING: 'Synthesizing...',
  DISTILLING: 'Distilling...',        // MCP tool result summarization
  CONCLUDING: 'Concluding...',        // Forced conclusion at iteration limit
  FINALIZING: 'Finalizing...',        // Executive summary generation
  PROCESSING: 'Processing...',
} as const;

/**
 * Maps backend event data to user-friendly progress status messages.
 * Supports regular stages, parallel stages, synthesis, and executive summary.
 * 
 * @param event - WebSocket event data
 * @returns User-friendly status message
 */
export function mapEventToProgressStatus(event: any): string {
  const eventType = event.type || '';
  
  // Explicit progress update event (e.g., distilling, finalizing)
  if (eventType === 'session.progress_update') {
    const phase = event.phase || event.data?.phase;
    if (phase === ProgressPhase.CONCLUDING) return ProgressStatusMessage.CONCLUDING;        // Forced conclusion at iteration limit
    if (phase === ProgressPhase.DISTILLING) return ProgressStatusMessage.DISTILLING;        // MCP tool result summarization
    if (phase === ProgressPhase.FINALIZING) return ProgressStatusMessage.FINALIZING;        // Executive summary generation
    if (phase === ProgressPhase.SYNTHESIZING) return ProgressStatusMessage.SYNTHESIZING;
    if (phase === ProgressPhase.INVESTIGATING) return ProgressStatusMessage.INVESTIGATING;
  }
  
  // Stage-based detection
  if (eventType === 'stage.started') {
    const stageName = event.stage_name || event.data?.stage_name;
    
    // Synthesis stage
    if (stageName === StageName.SYNTHESIS) return ProgressStatusMessage.SYNTHESIZING;
    
    // Any other stage (including parallel)
    return ProgressStatusMessage.INVESTIGATING;
  }
  
  // Default fallback
  return ProgressStatusMessage.PROCESSING;
}

