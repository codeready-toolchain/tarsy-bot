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
  SUMMARIZING: 'summarizing',
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
  SUMMARIZING: 'Summarizing...',
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
  
  // Explicit progress update event (e.g., summarizing)
  if (eventType === 'session.progress_update') {
    const phase = event.phase || event.data?.phase;
    if (phase === ProgressPhase.SUMMARIZING) return ProgressStatusMessage.SUMMARIZING;
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

