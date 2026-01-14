/**
 * Tests for statusMapping utility functions
 * Testing progress phase mapping and status message generation
 */

import { describe, it, expect } from 'vitest';
import {
  ProgressPhase,
  ProgressStatusMessage,
  TERMINAL_PROGRESS_STATUSES,
  isTerminalProgressStatus,
  mapEventToProgressStatus,
} from '../../utils/statusMapping';

describe('statusMapping', () => {
  describe('ProgressPhase constants', () => {
    it('should have all required phase values', () => {
      expect(ProgressPhase.INVESTIGATING).toBe('investigating');
      expect(ProgressPhase.GATHERING_INFO).toBe('gathering_info');
      expect(ProgressPhase.SYNTHESIZING).toBe('synthesizing');
      expect(ProgressPhase.DISTILLING).toBe('distilling');
      expect(ProgressPhase.CONCLUDING).toBe('concluding');
      expect(ProgressPhase.FINALIZING).toBe('finalizing');
    });
  });

  describe('ProgressStatusMessage constants', () => {
    it('should have all required status messages', () => {
      expect(ProgressStatusMessage.INVESTIGATING).toBe('Investigating...');
      expect(ProgressStatusMessage.GATHERING_INFO).toBe('Gathering information...');
      expect(ProgressStatusMessage.SYNTHESIZING).toBe('Synthesizing...');
      expect(ProgressStatusMessage.DISTILLING).toBe('Distilling...');
      expect(ProgressStatusMessage.CONCLUDING).toBe('Concluding...');
      expect(ProgressStatusMessage.FINALIZING).toBe('Finalizing...');
      expect(ProgressStatusMessage.PROCESSING).toBe('Processing...');
    });

    it('should have terminal status display strings', () => {
      expect(ProgressStatusMessage.COMPLETED).toBe('Completed');
      expect(ProgressStatusMessage.FAILED).toBe('Failed');
      expect(ProgressStatusMessage.CANCELLED).toBe('Cancelled');
    });
  });

  describe('TERMINAL_PROGRESS_STATUSES array', () => {
    it('should contain all terminal progress statuses', () => {
      expect(TERMINAL_PROGRESS_STATUSES).toEqual([
        'Completed',
        'Failed',
        'Cancelled',
      ]);
    });
  });

  describe('isTerminalProgressStatus', () => {
    it('should return true for terminal progress statuses', () => {
      expect(isTerminalProgressStatus('Completed')).toBe(true);
      expect(isTerminalProgressStatus('Failed')).toBe(true);
      expect(isTerminalProgressStatus('Cancelled')).toBe(true);
    });

    it('should return false for non-terminal progress statuses', () => {
      expect(isTerminalProgressStatus('Investigating...')).toBe(false);
      expect(isTerminalProgressStatus('Gathering information...')).toBe(false);
      expect(isTerminalProgressStatus('Synthesizing...')).toBe(false);
      expect(isTerminalProgressStatus('Distilling...')).toBe(false);
      expect(isTerminalProgressStatus('Concluding...')).toBe(false);
      expect(isTerminalProgressStatus('Finalizing...')).toBe(false);
      expect(isTerminalProgressStatus('Processing...')).toBe(false);
    });

    it('should return false for unknown statuses', () => {
      expect(isTerminalProgressStatus('Unknown Status')).toBe(false);
      expect(isTerminalProgressStatus('')).toBe(false);
      expect(isTerminalProgressStatus('completed')).toBe(false); // case-sensitive
    });
  });

  describe('mapEventToProgressStatus', () => {
    describe('session.progress_update events', () => {
      it('should map INVESTIGATING phase', () => {
        const event = {
          type: 'session.progress_update',
          phase: 'investigating',
        };
        expect(mapEventToProgressStatus(event)).toBe('Investigating...');
      });

      it('should map SYNTHESIZING phase', () => {
        const event = {
          type: 'session.progress_update',
          phase: 'synthesizing',
        };
        expect(mapEventToProgressStatus(event)).toBe('Synthesizing...');
      });

      it('should map DISTILLING phase', () => {
        const event = {
          type: 'session.progress_update',
          phase: 'distilling',
        };
        expect(mapEventToProgressStatus(event)).toBe('Distilling...');
      });

      it('should map CONCLUDING phase for forced conclusion', () => {
        const event = {
          type: 'session.progress_update',
          phase: 'concluding',
        };
        expect(mapEventToProgressStatus(event)).toBe('Concluding...');
      });

      it('should map FINALIZING phase', () => {
        const event = {
          type: 'session.progress_update',
          phase: 'finalizing',
        };
        expect(mapEventToProgressStatus(event)).toBe('Finalizing...');
      });

      it('should map GATHERING_INFO phase for tool execution', () => {
        const event = {
          type: 'session.progress_update',
          phase: 'gathering_info',
        };
        expect(mapEventToProgressStatus(event)).toBe('Gathering information...');
      });

      it('should handle phase in nested data object', () => {
        const event = {
          type: 'session.progress_update',
          data: {
            phase: 'concluding',
          },
        };
        expect(mapEventToProgressStatus(event)).toBe('Concluding...');
      });

      it('should prioritize top-level phase over data.phase', () => {
        const event = {
          type: 'session.progress_update',
          phase: 'concluding',
          data: {
            phase: 'investigating',
          },
        };
        expect(mapEventToProgressStatus(event)).toBe('Concluding...');
      });
    });

    describe('stage.started events', () => {
      it('should map synthesis stage to SYNTHESIZING', () => {
        const event = {
          type: 'stage.started',
          stage_name: 'synthesis',
        };
        expect(mapEventToProgressStatus(event)).toBe('Synthesizing...');
      });

      it('should map other stages to INVESTIGATING', () => {
        const event = {
          type: 'stage.started',
          stage_name: 'investigation',
        };
        expect(mapEventToProgressStatus(event)).toBe('Investigating...');
      });

      it('should handle stage_name in nested data object', () => {
        const event = {
          type: 'stage.started',
          data: {
            stage_name: 'synthesis',
          },
        };
        expect(mapEventToProgressStatus(event)).toBe('Synthesizing...');
      });

      it('should map parallel stages to INVESTIGATING', () => {
        const event = {
          type: 'stage.started',
          stage_name: 'parallel-investigation',
        };
        expect(mapEventToProgressStatus(event)).toBe('Investigating...');
      });
    });

    describe('fallback behavior', () => {
      it('should return PROCESSING for unknown event type', () => {
        const event = {
          type: 'unknown.event',
        };
        expect(mapEventToProgressStatus(event)).toBe('Processing...');
      });

      it('should return PROCESSING for empty event', () => {
        const event = {};
        expect(mapEventToProgressStatus(event)).toBe('Processing...');
      });

      it('should return PROCESSING for null/undefined phase', () => {
        const event = {
          type: 'session.progress_update',
          phase: null,
        };
        expect(mapEventToProgressStatus(event)).toBe('Processing...');
      });
    });

    describe('forced conclusion workflow', () => {
      it('should show correct sequence: investigating -> concluding -> processing', () => {
        // Stage starts - investigating
        const startEvent = {
          type: 'stage.started',
          stage_name: 'investigation',
        };
        expect(mapEventToProgressStatus(startEvent)).toBe('Investigating...');

        // Max iterations reached - concluding
        const concludingEvent = {
          type: 'session.progress_update',
          phase: 'concluding',
          metadata: { iteration: 50 },
        };
        expect(mapEventToProgressStatus(concludingEvent)).toBe('Concluding...');

        // After conclusion completes, no specific phase
        const afterEvent = {
          type: 'stage.completed',
        };
        expect(mapEventToProgressStatus(afterEvent)).toBe('Processing...');
      });
    });

    describe('agent context support for parallel execution', () => {
      it('should return ProgressStatusInfo when includeAgentContext is true', () => {
        const event = {
          type: 'session.progress_update',
          phase: 'investigating',
          stage_execution_id: 'exec-123',
          parent_stage_execution_id: 'parent-456',
          parallel_index: 2,
          agent_name: 'kubernetes-agent',
        };
        
        const result = mapEventToProgressStatus(event, true);
        
        expect(result).toEqual({
          status: 'Investigating...',
          stageExecutionId: 'exec-123',
          parentStageExecutionId: 'parent-456',
          parallelIndex: 2,
          agentName: 'kubernetes-agent',
        });
      });

      it('should include stageExecutionId for consistent Map key lookups', () => {
        const event = {
          type: 'session.progress_update',
          phase: 'distilling',
          stage_execution_id: 'exec-789',
        };
        
        const result = mapEventToProgressStatus(event, true);
        
        expect(result).toHaveProperty('stageExecutionId', 'exec-789');
        expect(result).toHaveProperty('status', 'Distilling...');
      });

      it('should handle missing optional fields gracefully', () => {
        const event = {
          type: 'session.progress_update',
          phase: 'synthesizing',
        };
        
        const result = mapEventToProgressStatus(event, true);
        
        expect(result).toEqual({
          status: 'Synthesizing...',
          stageExecutionId: undefined,
          parentStageExecutionId: undefined,
          parallelIndex: undefined,
          agentName: undefined,
        });
      });

      it('should work with stage.started events', () => {
        const event = {
          type: 'stage.started',
          stage_name: 'investigation',
          stage_execution_id: 'exec-456',
          agent_name: 'database-agent',
        };
        
        const result = mapEventToProgressStatus(event, true);
        
        expect(result).toEqual({
          status: 'Investigating...',
          stageExecutionId: 'exec-456',
          parentStageExecutionId: undefined,
          parallelIndex: undefined,
          agentName: 'database-agent',
        });
      });

      it('should use stage_id as fallback when stage_execution_id is missing', () => {
        const event = {
          type: 'session.progress_update',
          phase: 'concluding',
          stage_id: 'stage-abc-123',
          parent_stage_execution_id: 'parent-xyz',
          parallel_index: 1,
          agent_name: 'kubernetes-agent',
        };
        
        const result = mapEventToProgressStatus(event, true);
        
        expect(result).toEqual({
          status: 'Concluding...',
          stageExecutionId: 'stage-abc-123', // Falls back to stage_id
          parentStageExecutionId: 'parent-xyz',
          parallelIndex: 1,
          agentName: 'kubernetes-agent',
        });
      });

      it('should prefer stage_execution_id over stage_id when both present', () => {
        const event = {
          type: 'session.progress_update',
          phase: 'investigating',
          stage_execution_id: 'exec-primary',
          stage_id: 'stage-secondary',
        };
        
        const result = mapEventToProgressStatus(event, true);
        
        expect(result).toHaveProperty('stageExecutionId', 'exec-primary');
      });

      it('should handle GATHERING_INFO phase with agent context', () => {
        const event = {
          type: 'session.progress_update',
          phase: 'gathering_info',
          stage_execution_id: 'exec-tool-123',
          parent_stage_execution_id: 'parent-456',
          parallel_index: 1,
          agent_name: 'kubernetes-agent',
        };
        
        const result = mapEventToProgressStatus(event, true);
        
        expect(result).toEqual({
          status: 'Gathering information...',
          stageExecutionId: 'exec-tool-123',
          parentStageExecutionId: 'parent-456',
          parallelIndex: 1,
          agentName: 'kubernetes-agent',
        });
      });
    });
  });
});
