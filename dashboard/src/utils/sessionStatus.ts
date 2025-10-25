/**
 * Session status constants and utilities
 * Centralizes all session status-related logic across the dashboard
 */

// Session status constants
export const SESSION_STATUS = {
  PENDING: 'pending',
  IN_PROGRESS: 'in_progress',
  CANCELING: 'canceling',
  COMPLETED: 'completed',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
} as const;

// Type for session status values
export type SessionStatus = typeof SESSION_STATUS[keyof typeof SESSION_STATUS];

// Status groups
export const TERMINAL_STATUSES: SessionStatus[] = [
  SESSION_STATUS.COMPLETED,
  SESSION_STATUS.FAILED,
  SESSION_STATUS.CANCELLED,
];

export const ACTIVE_STATUSES: SessionStatus[] = [
  SESSION_STATUS.IN_PROGRESS,
  SESSION_STATUS.PENDING,
  SESSION_STATUS.CANCELING,
];

export const HISTORICAL_STATUSES: SessionStatus[] = TERMINAL_STATUSES;

// All possible status values as array - ordered logically (terminal first, then active)
export const ALL_STATUSES: SessionStatus[] = [
  ...TERMINAL_STATUSES,
  ...ACTIVE_STATUSES,
];

/**
 * Get human-readable display name for a status
 */
export function getStatusDisplayName(status: string): string {
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
    case SESSION_STATUS.CANCELING:
      return 'Canceling';
    default:
      return status;
  }
}

/**
 * Get MUI color for a status
 * Note: 'cancelled' uses 'default' but has custom dark styling in StatusBadge
 */
export function getStatusColor(
  status: string
): 'success' | 'error' | 'info' | 'warning' | 'default' {
  switch (status) {
    case SESSION_STATUS.COMPLETED:
      return 'success';
    case SESSION_STATUS.FAILED:
      return 'error';
    case SESSION_STATUS.CANCELLED:
      return 'default'; // Custom dark styling applied in StatusBadge component
    case SESSION_STATUS.IN_PROGRESS:
      return 'info';
    case SESSION_STATUS.PENDING:
      return 'warning';
    case SESSION_STATUS.CANCELING:
      return 'warning';
    default:
      return 'default';
  }
}

/**
 * Check if a status is terminal (processing finished)
 */
export function isTerminalStatus(status: string): boolean {
  return TERMINAL_STATUSES.includes(status as SessionStatus);
}

/**
 * Check if a status is active (still processing)
 */
export function isActiveStatus(status: string): boolean {
  return ACTIVE_STATUSES.includes(status as SessionStatus);
}

/**
 * Check if a session can be cancelled
 */
export function canCancelSession(status: string): boolean {
  return (
    status === SESSION_STATUS.PENDING ||
    status === SESSION_STATUS.IN_PROGRESS ||
    status === SESSION_STATUS.CANCELING
  );
}

/**
 * Check if a session is in a cancelling state
 */
export function isCancellingSession(status: string): boolean {
  return status === SESSION_STATUS.CANCELING;
}

/**
 * Validate if a string is a valid session status
 */
export function isValidStatus(status: string): status is SessionStatus {
  return ALL_STATUSES.includes(status as SessionStatus);
}

