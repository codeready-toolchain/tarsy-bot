/**
 * Tests for event type constants and utilities
 * Focuses on streaming content type validation and parsing
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  LLM_EVENTS,
  STREAMING_CONTENT_TYPES,
  ALL_STREAMING_CONTENT_TYPES,
  isValidStreamingContentType,
  parseStreamingContentType,
  isTerminalSessionEvent,
  isSessionEvent,
  isStageEvent,
  isLLMEvent,
  isMCPEvent,
  type StreamingContentType,
} from '../../utils/eventTypes';

describe('Event Types - Streaming Content', () => {
  describe('STREAMING_CONTENT_TYPES constant', () => {
    it('should define all expected streaming content types', () => {
      expect(STREAMING_CONTENT_TYPES.THOUGHT).toBe('thought');
      expect(STREAMING_CONTENT_TYPES.FINAL_ANSWER).toBe('final_answer');
      expect(STREAMING_CONTENT_TYPES.SUMMARIZATION).toBe('summarization');
      expect(STREAMING_CONTENT_TYPES.NATIVE_THINKING).toBe('native_thinking');
    });

    it('should have exactly 4 streaming content types', () => {
      expect(Object.keys(STREAMING_CONTENT_TYPES)).toHaveLength(4);
    });
  });

  describe('ALL_STREAMING_CONTENT_TYPES array', () => {
    it('should include all streaming content types', () => {
      expect(ALL_STREAMING_CONTENT_TYPES).toContain('thought');
      expect(ALL_STREAMING_CONTENT_TYPES).toContain('final_answer');
      expect(ALL_STREAMING_CONTENT_TYPES).toContain('summarization');
      expect(ALL_STREAMING_CONTENT_TYPES).toContain('native_thinking');
    });

    it('should have exactly 4 entries', () => {
      expect(ALL_STREAMING_CONTENT_TYPES).toHaveLength(4);
    });

    it('should match STREAMING_CONTENT_TYPES values', () => {
      const constantValues = Object.values(STREAMING_CONTENT_TYPES);
      expect(ALL_STREAMING_CONTENT_TYPES).toEqual(expect.arrayContaining(constantValues));
      expect(constantValues).toEqual(expect.arrayContaining([...ALL_STREAMING_CONTENT_TYPES]));
    });
  });

  describe('LLM_EVENTS.STREAM_CHUNK', () => {
    it('should have the correct event type string', () => {
      expect(LLM_EVENTS.STREAM_CHUNK).toBe('llm.stream.chunk');
    });
  });

  describe('isValidStreamingContentType', () => {
    it.each([
      ['thought', true],
      ['final_answer', true],
      ['summarization', true],
      ['native_thinking', true],
    ])('should return true for valid type "%s"', (type, expected) => {
      expect(isValidStreamingContentType(type)).toBe(expected);
    });

    it.each([
      ['invalid', false],
      ['THOUGHT', false],  // Case sensitive
      ['Thought', false],
      ['thinking', false],  // Similar but not exact
      ['answer', false],
      ['', false],
      ['tool_call', false],  // Not a streaming content type
      ['user_message', false],  // Not a streaming content type
    ])('should return false for invalid type "%s"', (type, expected) => {
      expect(isValidStreamingContentType(type)).toBe(expected);
    });

    it('should work as type guard', () => {
      const type: string = 'thought';
      if (isValidStreamingContentType(type)) {
        // TypeScript should narrow type to StreamingContentType
        const narrowed: StreamingContentType = type;
        expect(narrowed).toBe('thought');
      }
    });
  });

  describe('parseStreamingContentType', () => {
    let consoleWarnSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    });

    afterEach(() => {
      consoleWarnSpy.mockRestore();
    });

    it.each([
      ['thought', 'thought'],
      ['final_answer', 'final_answer'],
      ['summarization', 'summarization'],
      ['native_thinking', 'native_thinking'],
    ])('should return "%s" unchanged for valid type', (input, expected) => {
      expect(parseStreamingContentType(input)).toBe(expected);
      expect(consoleWarnSpy).not.toHaveBeenCalled();
    });

    it('should return "thought" as fallback for invalid types', () => {
      expect(parseStreamingContentType('invalid')).toBe('thought');
      expect(parseStreamingContentType('')).toBe('thought');
      expect(parseStreamingContentType('unknown_type')).toBe('thought');
    });

    it('should log warning for invalid types', () => {
      parseStreamingContentType('invalid_type');
      
      expect(consoleWarnSpy).toHaveBeenCalledOnce();
      expect(consoleWarnSpy).toHaveBeenCalledWith(
        expect.stringContaining('Unknown streaming content type: invalid_type')
      );
    });

    it('should not log warning for valid types', () => {
      parseStreamingContentType('thought');
      parseStreamingContentType('native_thinking');
      
      expect(consoleWarnSpy).not.toHaveBeenCalled();
    });

    it('should handle case sensitivity correctly', () => {
      expect(parseStreamingContentType('THOUGHT')).toBe('thought');
      expect(consoleWarnSpy).toHaveBeenCalled();
    });
  });
});

describe('Event Types - Event Category Helpers', () => {
  describe('isTerminalSessionEvent', () => {
    it('should return true for terminal session events', () => {
      expect(isTerminalSessionEvent('session.completed')).toBe(true);
      expect(isTerminalSessionEvent('session.failed')).toBe(true);
      expect(isTerminalSessionEvent('session.cancelled')).toBe(true);
    });

    it('should return false for non-terminal session events', () => {
      expect(isTerminalSessionEvent('session.started')).toBe(false);
      expect(isTerminalSessionEvent('session.paused')).toBe(false);
      expect(isTerminalSessionEvent('session.resumed')).toBe(false);
    });
  });

  describe('isSessionEvent', () => {
    it('should return true for session events', () => {
      expect(isSessionEvent('session.created')).toBe(true);
      expect(isSessionEvent('session.started')).toBe(true);
      expect(isSessionEvent('session.completed')).toBe(true);
    });

    it('should return false for non-session events', () => {
      expect(isSessionEvent('stage.started')).toBe(false);
      expect(isSessionEvent('llm.call.started')).toBe(false);
    });
  });

  describe('isStageEvent', () => {
    it('should return true for stage events', () => {
      expect(isStageEvent('stage.started')).toBe(true);
      expect(isStageEvent('stage.completed')).toBe(true);
      expect(isStageEvent('stage.failed')).toBe(true);
    });

    it('should return false for non-stage events', () => {
      expect(isStageEvent('session.started')).toBe(false);
      expect(isStageEvent('llm.call.started')).toBe(false);
    });
  });

  describe('isLLMEvent', () => {
    it('should return true for LLM events', () => {
      expect(isLLMEvent('llm.call.started')).toBe(true);
      expect(isLLMEvent('llm.call.completed')).toBe(true);
      expect(isLLMEvent('llm.stream.chunk')).toBe(true);
    });

    it('should return false for non-LLM events', () => {
      expect(isLLMEvent('session.started')).toBe(false);
      expect(isLLMEvent('mcp.tool_call.started')).toBe(false);
    });
  });

  describe('isMCPEvent', () => {
    it('should return true for MCP events', () => {
      expect(isMCPEvent('mcp.tool_call.started')).toBe(true);
      expect(isMCPEvent('mcp.tool_call.completed')).toBe(true);
      expect(isMCPEvent('mcp.tool_call.failed')).toBe(true);
    });

    it('should return false for non-MCP events', () => {
      expect(isMCPEvent('session.started')).toBe(false);
      expect(isMCPEvent('llm.call.started')).toBe(false);
    });
  });
});

