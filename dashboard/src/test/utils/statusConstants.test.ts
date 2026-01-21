/**
 * Tests for status constants and utilities
 * Focuses on pause/resume status handling
 */

import { describe, it, expect } from 'vitest';
import {
  SESSION_STATUS,
  STAGE_STATUS,
  ACTIVE_SESSION_STATUSES,
  TERMINAL_SESSION_STATUSES,
  TERMINAL_STAGE_STATUSES,
  ACTIVE_STAGE_STATUSES,
  isActiveSessionStatus,
  isTerminalSessionStatus,
  isActiveStageStatus,
  isTerminalStageStatus,
  canCancelSession,
  getSessionStatusDisplayName,
  getSessionStatusChipColor,
  getSessionStatusProgressColor,
  getStageStatusDisplayName,
  getStageStatusChipColor,
  getStageStatusProgressColor,
} from '../../utils/statusConstants';

describe('Status Constants - Pause/Resume', () => {
  describe('SESSION_STATUS constant', () => {
    it('should include PAUSED status', () => {
      expect(SESSION_STATUS.PAUSED).toBe('paused');
    });
  });

  describe('Status categorization', () => {
    it('should categorize paused as active session status', () => {
      expect(ACTIVE_SESSION_STATUSES).toContain(SESSION_STATUS.PAUSED);
    });

    it('should not categorize paused as terminal session status', () => {
      expect(TERMINAL_SESSION_STATUSES).not.toContain(SESSION_STATUS.PAUSED);
    });

    it('should verify paused is not in completed/failed/cancelled', () => {
      expect(SESSION_STATUS.PAUSED).not.toBe(SESSION_STATUS.COMPLETED);
      expect(SESSION_STATUS.PAUSED).not.toBe(SESSION_STATUS.FAILED);
      expect(SESSION_STATUS.PAUSED).not.toBe(SESSION_STATUS.CANCELLED);
    });
  });

  describe('isActiveSessionStatus', () => {
    it('should return true for paused sessions', () => {
      expect(isActiveSessionStatus('paused')).toBe(true);
    });

    it('should return true for in_progress sessions', () => {
      expect(isActiveSessionStatus('in_progress')).toBe(true);
    });

    it('should return true for pending sessions', () => {
      expect(isActiveSessionStatus('pending')).toBe(true);
    });

    it('should return true for canceling sessions', () => {
      expect(isActiveSessionStatus('canceling')).toBe(true);
    });

    it('should return false for terminal statuses', () => {
      expect(isActiveSessionStatus('completed')).toBe(false);
      expect(isActiveSessionStatus('failed')).toBe(false);
      expect(isActiveSessionStatus('cancelled')).toBe(false);
    });
  });

  describe('isTerminalSessionStatus', () => {
    it('should return false for paused sessions', () => {
      expect(isTerminalSessionStatus('paused')).toBe(false);
    });

    it('should return false for in_progress sessions', () => {
      expect(isTerminalSessionStatus('in_progress')).toBe(false);
    });

    it('should return true for completed sessions', () => {
      expect(isTerminalSessionStatus('completed')).toBe(true);
    });

    it('should return true for failed sessions', () => {
      expect(isTerminalSessionStatus('failed')).toBe(true);
    });

    it('should return true for cancelled sessions', () => {
      expect(isTerminalSessionStatus('cancelled')).toBe(true);
    });
  });

  describe('canCancelSession', () => {
    it('should return true for paused sessions (paused sessions can be cancelled)', () => {
      // Paused sessions are active and can be cancelled just like in_progress sessions
      // Mirrors backend behavior and ACTIVE_SESSION_STATUSES
      expect(canCancelSession('paused')).toBe(true);
    });

    it('should return true for pending sessions', () => {
      expect(canCancelSession('pending')).toBe(true);
    });

    it('should return true for in_progress sessions', () => {
      expect(canCancelSession('in_progress')).toBe(true);
    });

    it('should return true for canceling sessions', () => {
      expect(canCancelSession('canceling')).toBe(true);
    });

    it('should return false for terminal statuses', () => {
      expect(canCancelSession('completed')).toBe(false);
      expect(canCancelSession('failed')).toBe(false);
      expect(canCancelSession('cancelled')).toBe(false);
    });
  });

  describe('getSessionStatusDisplayName', () => {
    it('should return "Paused" for paused status', () => {
      expect(getSessionStatusDisplayName('paused')).toBe('Paused');
    });

    it('should return proper display names for all statuses', () => {
      expect(getSessionStatusDisplayName('pending')).toBe('Pending');
      expect(getSessionStatusDisplayName('in_progress')).toBe('In Progress');
      expect(getSessionStatusDisplayName('canceling')).toBe('Canceling');
      expect(getSessionStatusDisplayName('completed')).toBe('Completed');
      expect(getSessionStatusDisplayName('failed')).toBe('Failed');
      expect(getSessionStatusDisplayName('cancelled')).toBe('Cancelled');
    });

    it('should return original status for unknown status', () => {
      expect(getSessionStatusDisplayName('unknown')).toBe('unknown');
    });
  });

  describe('getSessionStatusChipColor', () => {
    it('should return warning color for paused status', () => {
      expect(getSessionStatusChipColor('paused')).toBe('warning');
    });

    it('should return appropriate colors for other statuses', () => {
      expect(getSessionStatusChipColor('completed')).toBe('success');
      expect(getSessionStatusChipColor('failed')).toBe('error');
      expect(getSessionStatusChipColor('cancelled')).toBe('default');
      expect(getSessionStatusChipColor('in_progress')).toBe('info');
      expect(getSessionStatusChipColor('pending')).toBe('warning');
      expect(getSessionStatusChipColor('canceling')).toBe('warning');
    });
  });

  describe('getSessionStatusProgressColor', () => {
    it('should return warning color for paused status', () => {
      expect(getSessionStatusProgressColor('paused')).toBe('warning');
    });

    it('should return appropriate colors for other statuses', () => {
      expect(getSessionStatusProgressColor('completed')).toBe('success');
      expect(getSessionStatusProgressColor('failed')).toBe('error');
      expect(getSessionStatusProgressColor('cancelled')).toBe('inherit');
      expect(getSessionStatusProgressColor('in_progress')).toBe('info');
      expect(getSessionStatusProgressColor('pending')).toBe('warning');
      expect(getSessionStatusProgressColor('canceling')).toBe('warning');
    });
  });

  describe('Status transition logic', () => {
    it('should verify paused is distinct from pending and in_progress', () => {
      // Paused is a special state - session was running but hit a limit
      // Not the same as pending (never started) or in_progress (actively running)
      expect(SESSION_STATUS.PAUSED).not.toBe(SESSION_STATUS.PENDING);
      expect(SESSION_STATUS.PAUSED).not.toBe(SESSION_STATUS.IN_PROGRESS);
    });

    it('should verify paused sessions are still active (can be resumed)', () => {
      // Paused sessions should be in active category because they can transition back to in_progress
      expect(isActiveSessionStatus(SESSION_STATUS.PAUSED)).toBe(true);
      expect(isTerminalSessionStatus(SESSION_STATUS.PAUSED)).toBe(false);
    });

    it('should verify terminal statuses cannot be resumed', () => {
      // Once a session reaches a terminal state, it cannot be resumed
      const terminalStatuses = ['completed', 'failed', 'cancelled'];
      terminalStatuses.forEach(status => {
        expect(isTerminalSessionStatus(status)).toBe(true);
        expect(isActiveSessionStatus(status)).toBe(false);
      });
    });
  });
});

describe('Stage Status Constants - Cancelled Support', () => {
  describe('STAGE_STATUS constant', () => {
    it('should include CANCELLED status', () => {
      expect(STAGE_STATUS.CANCELLED).toBe('cancelled');
    });
  });

  describe('Status categorization', () => {
    it('should categorize cancelled as terminal stage status', () => {
      expect(TERMINAL_STAGE_STATUSES).toContain(STAGE_STATUS.CANCELLED);
    });

    it('should not categorize cancelled as active stage status', () => {
      expect(ACTIVE_STAGE_STATUSES).not.toContain(STAGE_STATUS.CANCELLED);
    });
  });

  describe('isTerminalStageStatus', () => {
    it('should return true for cancelled stages', () => {
      expect(isTerminalStageStatus('cancelled')).toBe(true);
    });

    it('should return true for completed stages', () => {
      expect(isTerminalStageStatus('completed')).toBe(true);
    });

    it('should return true for failed stages', () => {
      expect(isTerminalStageStatus('failed')).toBe(true);
    });

    it('should return false for active statuses', () => {
      expect(isTerminalStageStatus('pending')).toBe(false);
      expect(isTerminalStageStatus('active')).toBe(false);
      expect(isTerminalStageStatus('paused')).toBe(false);
    });
  });

  describe('isActiveStageStatus', () => {
    it('should return false for cancelled stages', () => {
      expect(isActiveStageStatus('cancelled')).toBe(false);
    });

    it('should return true for active statuses', () => {
      expect(isActiveStageStatus('pending')).toBe(true);
      expect(isActiveStageStatus('active')).toBe(true);
      expect(isActiveStageStatus('paused')).toBe(true);
    });
  });

  describe('getStageStatusDisplayName', () => {
    it('should return "Cancelled" for cancelled status', () => {
      expect(getStageStatusDisplayName('cancelled')).toBe('Cancelled');
    });

    it('should return proper display names for all statuses', () => {
      expect(getStageStatusDisplayName('pending')).toBe('Pending');
      expect(getStageStatusDisplayName('active')).toBe('Active');
      expect(getStageStatusDisplayName('paused')).toBe('Paused');
      expect(getStageStatusDisplayName('completed')).toBe('Completed');
      expect(getStageStatusDisplayName('failed')).toBe('Failed');
    });

    it('should return original status for unknown status', () => {
      expect(getStageStatusDisplayName('unknown')).toBe('unknown');
    });
  });

  describe('getStageStatusChipColor', () => {
    it('should return warning color for cancelled status', () => {
      expect(getStageStatusChipColor('cancelled')).toBe('warning');
    });

    it('should return appropriate colors for other statuses', () => {
      expect(getStageStatusChipColor('completed')).toBe('success');
      expect(getStageStatusChipColor('failed')).toBe('error');
      expect(getStageStatusChipColor('active')).toBe('primary');
      expect(getStageStatusChipColor('pending')).toBe('warning');
      expect(getStageStatusChipColor('paused')).toBe('warning');
    });

    it('should return default for unknown status', () => {
      expect(getStageStatusChipColor('unknown')).toBe('default');
    });
  });

  describe('getStageStatusProgressColor', () => {
    it('should return warning color for cancelled status', () => {
      expect(getStageStatusProgressColor('cancelled')).toBe('warning');
    });

    it('should return appropriate colors for other statuses', () => {
      expect(getStageStatusProgressColor('completed')).toBe('success');
      expect(getStageStatusProgressColor('failed')).toBe('error');
      expect(getStageStatusProgressColor('active')).toBe('primary');
      expect(getStageStatusProgressColor('pending')).toBe('warning');
      expect(getStageStatusProgressColor('paused')).toBe('warning');
    });

    it('should return inherit for unknown status', () => {
      expect(getStageStatusProgressColor('unknown')).toBe('inherit');
    });
  });
});

describe('Stage Status Constants - Timed Out Support', () => {
  describe('STAGE_STATUS constant', () => {
    it('should include TIMED_OUT status', () => {
      expect(STAGE_STATUS.TIMED_OUT).toBe('timed_out');
    });
  });

  describe('Status categorization', () => {
    it('should categorize timed_out as terminal stage status', () => {
      expect(TERMINAL_STAGE_STATUSES).toContain(STAGE_STATUS.TIMED_OUT);
    });

    it('should not categorize timed_out as active stage status', () => {
      expect(ACTIVE_STAGE_STATUSES).not.toContain(STAGE_STATUS.TIMED_OUT);
    });
  });

  describe('isTerminalStageStatus', () => {
    it('should return true for timed_out stages', () => {
      expect(isTerminalStageStatus('timed_out')).toBe(true);
    });
  });

  describe('isActiveStageStatus', () => {
    it('should return false for timed_out stages', () => {
      expect(isActiveStageStatus('timed_out')).toBe(false);
    });
  });

  describe('getStageStatusDisplayName', () => {
    it('should return "Timed Out" for timed_out status', () => {
      expect(getStageStatusDisplayName('timed_out')).toBe('Timed Out');
    });
  });

  describe('getStageStatusChipColor', () => {
    it('should return error color for timed_out status', () => {
      expect(getStageStatusChipColor('timed_out')).toBe('error');
    });
  });

  describe('getStageStatusProgressColor', () => {
    it('should return error color for timed_out status', () => {
      expect(getStageStatusProgressColor('timed_out')).toBe('error');
    });
  });
});

