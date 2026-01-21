/**
 * Comprehensive status constants for all components
 * Centralizes all status-related strings and utilities across the dashboard
 */

// ============================================================================
// SESSION STATUS CONSTANTS
// ============================================================================

export const SESSION_STATUS = {
  PENDING: 'pending',
  IN_PROGRESS: 'in_progress',
  PAUSED: 'paused',
  CANCELING: 'canceling',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
} as const;

export type SessionStatus = typeof SESSION_STATUS[keyof typeof SESSION_STATUS];

// ============================================================================
// STAGE STATUS CONSTANTS
// ============================================================================

export const STAGE_STATUS = {
  PENDING: 'pending',
  ACTIVE: 'active',
  PAUSED: 'paused',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
  TIMED_OUT: 'timed_out',
} as const;

export type StageStatus = typeof STAGE_STATUS[keyof typeof STAGE_STATUS];

// ============================================================================
// ALERT PROCESSING STATUS CONSTANTS (Manual Alert Submission)
// ============================================================================

export const ALERT_PROCESSING_STATUS = {
  QUEUED: 'queued',
  PROCESSING: 'processing',
  COMPLETED: 'completed',
  ERROR: 'error',
  CANCELLED: 'cancelled',
} as const;

export type AlertProcessingStatus = typeof ALERT_PROCESSING_STATUS[keyof typeof ALERT_PROCESSING_STATUS];

// ============================================================================
// CHAIN OVERALL STATUS CONSTANTS
// ============================================================================

export const CHAIN_OVERALL_STATUS = {
  PENDING: 'pending',
  PROCESSING: 'processing',
  PAUSED: 'paused',
  COMPLETED: 'completed',
  FAILED: 'failed',
} as const;

export type ChainOverallStatus = typeof CHAIN_OVERALL_STATUS[keyof typeof CHAIN_OVERALL_STATUS];

// ============================================================================
// MANUAL ALERT APP STATE CONSTANTS
// ============================================================================

export const MANUAL_ALERT_APP_STATE = {
  FORM: 'form',
} as const;

export type ManualAlertAppState = typeof MANUAL_ALERT_APP_STATE[keyof typeof MANUAL_ALERT_APP_STATE];

// ============================================================================
// STATUS GROUPS
// ============================================================================

export const TERMINAL_SESSION_STATUSES: SessionStatus[] = [
  SESSION_STATUS.COMPLETED,
  SESSION_STATUS.FAILED,
  SESSION_STATUS.CANCELLED,
];

export const ACTIVE_SESSION_STATUSES: SessionStatus[] = [
  SESSION_STATUS.IN_PROGRESS,
  SESSION_STATUS.PENDING,
  SESSION_STATUS.PAUSED,
  SESSION_STATUS.CANCELING,
];

export const ALL_SESSION_STATUSES: SessionStatus[] = [
  ...TERMINAL_SESSION_STATUSES,
  ...ACTIVE_SESSION_STATUSES,
];

export const TERMINAL_STAGE_STATUSES: StageStatus[] = [
  STAGE_STATUS.COMPLETED,
  STAGE_STATUS.FAILED,
  STAGE_STATUS.CANCELLED,
  STAGE_STATUS.TIMED_OUT,
];

export const ACTIVE_STAGE_STATUSES: StageStatus[] = [
  STAGE_STATUS.PENDING,
  STAGE_STATUS.ACTIVE,
  STAGE_STATUS.PAUSED,
];

export const ALL_STAGE_STATUSES: StageStatus[] = [
  ...TERMINAL_STAGE_STATUSES,
  ...ACTIVE_STAGE_STATUSES,
];

// ============================================================================
// STATUS CHECKING UTILITIES
// ============================================================================

/**
 * Check if a session status is terminal (processing finished)
 */
export function isTerminalSessionStatus(status: string): boolean {
  return TERMINAL_SESSION_STATUSES.includes(status as SessionStatus);
}

/**
 * Check if a session status is active (still processing)
 */
export function isActiveSessionStatus(status: string): boolean {
  return ACTIVE_SESSION_STATUSES.includes(status as SessionStatus);
}

/**
 * Check if a session can be cancelled
 * Includes all active statuses that haven't reached terminal state
 */
export function canCancelSession(status: string): boolean {
  return (
    status === SESSION_STATUS.PENDING ||
    status === SESSION_STATUS.IN_PROGRESS ||
    status === SESSION_STATUS.PAUSED ||
    status === SESSION_STATUS.CANCELING
  );
}

/**
 * Check if a session is in a canceling state
 */
export function isCancelingSession(status: string): boolean {
  return status === SESSION_STATUS.CANCELING;
}

/**
 * Check if a stage status is terminal
 */
export function isTerminalStageStatus(status: string): boolean {
  return TERMINAL_STAGE_STATUSES.includes(status as StageStatus);
}

/**
 * Check if a stage status is active
 */
export function isActiveStageStatus(status: string): boolean {
  return ACTIVE_STAGE_STATUSES.includes(status as StageStatus);
}

/**
 * Validate if a string is a valid session status
 */
export function isValidSessionStatus(status: string): status is SessionStatus {
  return ALL_SESSION_STATUSES.includes(status as SessionStatus);
}

/**
 * Validate if a string is a valid stage status
 */
export function isValidStageStatus(status: string): status is StageStatus {
  return ALL_STAGE_STATUSES.includes(status as StageStatus);
}

// ============================================================================
// DISPLAY NAME UTILITIES
// ============================================================================

/**
 * Get human-readable display name for a session status
 */
export function getSessionStatusDisplayName(status: string): string {
  switch (status) {
    case SESSION_STATUS.COMPLETED:
      return 'Completed';
    case SESSION_STATUS.FAILED:
      return 'Failed';
    case SESSION_STATUS.CANCELLED:
      return 'Cancelled';
    case SESSION_STATUS.IN_PROGRESS:
      return 'In Progress';
    case SESSION_STATUS.PENDING:
      return 'Pending';
    case SESSION_STATUS.PAUSED:
      return 'Paused';
    case SESSION_STATUS.CANCELING:
      return 'Canceling';
    default:
      return status;
  }
}

/**
 * Get human-readable display name for a stage status
 */
export function getStageStatusDisplayName(status: string): string {
  switch (status) {
    case STAGE_STATUS.COMPLETED:
      return 'Completed';
    case STAGE_STATUS.FAILED:
      return 'Failed';
    case STAGE_STATUS.CANCELLED:
      return 'Cancelled';
    case STAGE_STATUS.TIMED_OUT:
      return 'Timed Out';
    case STAGE_STATUS.ACTIVE:
      return 'Active';
    case STAGE_STATUS.PENDING:
      return 'Pending';
    case STAGE_STATUS.PAUSED:
      return 'Paused';
    default:
      return status;
  }
}

/**
 * Get human-readable display name for alert processing status
 */
export function getAlertProcessingStatusDisplayName(status: string): string {
  switch (status) {
    case ALERT_PROCESSING_STATUS.QUEUED:
      return 'Queued';
    case ALERT_PROCESSING_STATUS.PROCESSING:
      return 'Processing';
    case ALERT_PROCESSING_STATUS.COMPLETED:
      return 'Completed';
    case ALERT_PROCESSING_STATUS.ERROR:
      return 'Error';
    case ALERT_PROCESSING_STATUS.CANCELLED:
      return 'Cancelled';
    default:
      return status;
  }
}

// ============================================================================
// COLOR UTILITIES (for MUI components)
// ============================================================================

/**
 * Get MUI Chip color for a session status
 * Returns colors compatible with MUI Chip component
 */
export function getSessionStatusChipColor(
  status: string
): 'success' | 'error' | 'info' | 'warning' | 'default' {
  switch (status) {
    case SESSION_STATUS.COMPLETED:
      return 'success';
    case SESSION_STATUS.FAILED:
      return 'error';
    case SESSION_STATUS.CANCELLED:
      return 'default';
    case SESSION_STATUS.IN_PROGRESS:
      return 'info';
    case SESSION_STATUS.PENDING:
      return 'warning';
    case SESSION_STATUS.PAUSED:
      return 'warning';
    case SESSION_STATUS.CANCELING:
      return 'warning';
    default:
      return 'default';
  }
}

/**
 * Get MUI LinearProgress color for a session status
 * Returns colors compatible with MUI LinearProgress component (uses 'inherit' instead of 'default')
 */
export function getSessionStatusProgressColor(
  status: string
): 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' | 'inherit' {
  switch (status) {
    case SESSION_STATUS.COMPLETED:
      return 'success';
    case SESSION_STATUS.FAILED:
      return 'error';
    case SESSION_STATUS.CANCELLED:
      return 'inherit';
    case SESSION_STATUS.IN_PROGRESS:
      return 'info';
    case SESSION_STATUS.PENDING:
      return 'warning';
    case SESSION_STATUS.PAUSED:
      return 'warning';
    case SESSION_STATUS.CANCELING:
      return 'warning';
    default:
      return 'primary';
  }
}

/**
 * Get MUI Chip color for a stage status
 */
export function getStageStatusChipColor(
  status: string
): 'success' | 'error' | 'info' | 'warning' | 'default' | 'primary' {
  switch (status) {
    case STAGE_STATUS.COMPLETED:
      return 'success';
    case STAGE_STATUS.FAILED:
      return 'error';
    case STAGE_STATUS.TIMED_OUT:
      return 'error';
    case STAGE_STATUS.CANCELLED:
      return 'warning';
    case STAGE_STATUS.ACTIVE:
      return 'primary';
    case STAGE_STATUS.PENDING:
      return 'warning';
    case STAGE_STATUS.PAUSED:
      return 'warning';
    default:
      return 'default';
  }
}

/**
 * Get MUI LinearProgress color for a stage status
 */
export function getStageStatusProgressColor(
  status: string
): 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' | 'inherit' {
  switch (status) {
    case STAGE_STATUS.COMPLETED:
      return 'success';
    case STAGE_STATUS.FAILED:
      return 'error';
    case STAGE_STATUS.TIMED_OUT:
      return 'error';
    case STAGE_STATUS.CANCELLED:
      return 'warning';
    case STAGE_STATUS.ACTIVE:
      return 'primary';
    case STAGE_STATUS.PENDING:
      return 'warning';
    case STAGE_STATUS.PAUSED:
      return 'warning';
    default:
      return 'inherit';
  }
}

/**
 * Get MUI Chip color for alert processing status
 */
export function getAlertProcessingStatusChipColor(
  status: string
): 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' {
  switch (status) {
    case ALERT_PROCESSING_STATUS.QUEUED:
    case ALERT_PROCESSING_STATUS.PROCESSING:
      return 'info';
    case ALERT_PROCESSING_STATUS.COMPLETED:
      return 'success';
    case ALERT_PROCESSING_STATUS.ERROR:
      return 'error';
    case ALERT_PROCESSING_STATUS.CANCELLED:
      return 'default';
    default:
      return 'primary';
  }
}

/**
 * Get MUI LinearProgress color for alert processing status
 */
export function getAlertProcessingStatusProgressColor(
  status: string
): 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' | 'inherit' {
  switch (status) {
    case ALERT_PROCESSING_STATUS.QUEUED:
    case ALERT_PROCESSING_STATUS.PROCESSING:
      return 'info';
    case ALERT_PROCESSING_STATUS.COMPLETED:
      return 'success';
    case ALERT_PROCESSING_STATUS.ERROR:
      return 'error';
    case ALERT_PROCESSING_STATUS.CANCELLED:
      return 'inherit';
    default:
      return 'primary';
  }
}

/**
 * Get MUI Chip color for chain overall status
 */
export function getChainOverallStatusChipColor(
  status: string
): 'success' | 'error' | 'info' | 'warning' | 'default' | 'primary' {
  switch (status) {
    case CHAIN_OVERALL_STATUS.COMPLETED:
      return 'success';
    case CHAIN_OVERALL_STATUS.FAILED:
      return 'error';
    case CHAIN_OVERALL_STATUS.PAUSED:
      return 'warning';
    case CHAIN_OVERALL_STATUS.PROCESSING:
      return 'info';
    case CHAIN_OVERALL_STATUS.PENDING:
      return 'warning';
    default:
      return 'default';
  }
}
