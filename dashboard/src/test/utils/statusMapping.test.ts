/**
 * Tests for statusMapping utility functions
 * Testing progress phase mapping and status message generation
 */

import { describe, it, expect } from 'vitest';
import {
  ProgressPhase,
  ProgressStatusMessage,
  mapEventToProgressStatus,
} from '../../utils/statusMapping';

describe('statusMapping', () => {
  describe('ProgressPhase constants', () => {
    it('should have all required phase values', () => {
      expect(ProgressPhase.INVESTIGATING).toBe('investigating');
      expect(ProgressPhase.SYNTHESIZING).toBe('synthesizing');
      expect(ProgressPhase.DISTILLING).toBe('distilling');
      expect(ProgressPhase.CONCLUDING).toBe('concluding');
      expect(ProgressPhase.FINALIZING).toBe('finalizing');
    });
  });

  describe('ProgressStatusMessage constants', () => {
    it('should have all required status messages', () => {
      expect(ProgressStatusMessage.INVESTIGATING).toBe('Investigating...');
      expect(ProgressStatusMessage.SYNTHESIZING).toBe('Synthesizing...');
      expect(ProgressStatusMessage.DISTILLING).toBe('Distilling...');
      expect(ProgressStatusMessage.CONCLUDING).toBe('Concluding...');
      expect(ProgressStatusMessage.FINALIZING).toBe('Finalizing...');
      expect(ProgressStatusMessage.PROCESSING).toBe('Processing...');
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
  });
});
