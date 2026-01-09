/**
 * Tests for text truncation utilities
 */

import { describe, it, expect } from 'vitest';
import { truncateText, generateItemKey } from '../../utils/textTruncation';
import type { ChatFlowItemData } from '../../utils/chatFlowParser';

describe('textTruncation', () => {
  describe('truncateText', () => {
    it('should not truncate short single line text', () => {
      const text = 'Short text';
      const result = truncateText(text);
      
      expect(result.truncated).toBe('Short text');
      expect(result.isTruncated).toBe(false);
      expect(result.fullText).toBe(text);
    });

    it('should not truncate two short lines', () => {
      const text = 'Line 1\nLine 2';
      const result = truncateText(text);
      
      expect(result.truncated).toBe('Line 1\nLine 2');
      expect(result.isTruncated).toBe(false);
      expect(result.fullText).toBe(text);
    });

    it('should truncate three lines to first two lines', () => {
      const text = 'Line 1\nLine 2\nLine 3';
      const result = truncateText(text);
      
      expect(result.truncated).toBe('Line 1\nLine 2...');
      expect(result.isTruncated).toBe(true);
      expect(result.fullText).toBe(text);
    });

    it('should truncate many lines to first two lines', () => {
      const text = 'Line 1\nLine 2\nLine 3\nLine 4\nLine 5';
      const result = truncateText(text);
      
      expect(result.truncated).toBe('Line 1\nLine 2...');
      expect(result.isTruncated).toBe(true);
      expect(result.fullText).toBe(text);
    });

    it('should fall back to character truncation for extremely long single line', () => {
      const text = 'a'.repeat(600);
      const result = truncateText(text, 500);
      
      expect(result.truncated).toContain('...');
      expect(result.truncated.length).toBeLessThanOrEqual(504); // 500 + "..." = 503
      expect(result.isTruncated).toBe(true);
      expect(result.fullText).toBe(text);
    });

    it('should fall back to character truncation when first line exceeds limit', () => {
      const text = 'a'.repeat(600) + '\nLine 2';
      const result = truncateText(text, 500);
      
      expect(result.truncated).toContain('...');
      expect(result.truncated.length).toBeLessThanOrEqual(504);
      expect(result.isTruncated).toBe(true);
      expect(result.fullText).toBe(text);
    });

    it('should fall back to character truncation when second line exceeds limit', () => {
      const text = 'Line 1\n' + 'b'.repeat(600);
      const result = truncateText(text, 500);
      
      expect(result.truncated).toContain('...');
      expect(result.truncated.length).toBeLessThanOrEqual(504);
      expect(result.isTruncated).toBe(true);
      expect(result.fullText).toBe(text);
    });

    it('should truncate at word boundary for character truncation', () => {
      const text = 'This is a very long line that needs to be truncated ' + 'word '.repeat(100);
      const result = truncateText(text, 100);
      
      expect(result.truncated).toContain('...');
      // Check that truncation happens and result is reasonable length
      expect(result.truncated.length).toBeLessThanOrEqual(104); // 100 + "..." = 103
      expect(result.isTruncated).toBe(true);
      // Verify it tries to break at word boundary (space before ellipsis)
      const beforeEllipsis = result.truncated.slice(-4, -3);
      expect(beforeEllipsis === ' ' || beforeEllipsis === 'd').toBe(true); // Either space or last char of 'word'
    });

    it('should handle empty text', () => {
      const result = truncateText('');
      
      expect(result.truncated).toBe('');
      expect(result.isTruncated).toBe(false);
      expect(result.fullText).toBe('');
    });

    it('should handle text with only newlines', () => {
      const text = '\n\n\n';
      const result = truncateText(text);
      
      expect(result.truncated).toBe('\n...');
      expect(result.isTruncated).toBe(true);
      expect(result.fullText).toBe(text);
    });

    it('should preserve exact two lines without adding ellipsis', () => {
      const text = 'Exactly two lines\nNo more no less';
      const result = truncateText(text);
      
      expect(result.truncated).toBe(text);
      expect(result.isTruncated).toBe(false);
      expect(result.fullText).toBe(text);
    });

    it('should handle markdown formatting in lines', () => {
      const text = '**Bold text** on line 1\n*Italic text* on line 2\nLine 3 should be truncated';
      const result = truncateText(text);
      
      expect(result.truncated).toBe('**Bold text** on line 1\n*Italic text* on line 2...');
      expect(result.isTruncated).toBe(true);
    });
  });

  describe('generateItemKey', () => {
    it('should generate key from llm_interaction_id', () => {
      const item: Partial<ChatFlowItemData> = {
        llm_interaction_id: 'llm-123',
        type: 'thought',
      };
      
      const key = generateItemKey(item);
      expect(key).toBe('llm-llm-123');
    });

    it('should generate key from mcp_event_id and type', () => {
      const item: Partial<ChatFlowItemData> = {
        mcp_event_id: 'mcp-456',
        type: 'summarization',
      };
      
      const key = generateItemKey(item);
      expect(key).toBe('mcp-mcp-456-summarization');
    });

    it('should prioritize llm_interaction_id over mcp_event_id', () => {
      const item: Partial<ChatFlowItemData> = {
        llm_interaction_id: 'llm-123',
        mcp_event_id: 'mcp-456',
        type: 'thought',
      };
      
      const key = generateItemKey(item);
      expect(key).toBe('llm-llm-123');
    });

    it('should generate key from messageId', () => {
      const item: Partial<ChatFlowItemData> = {
        messageId: 'msg-789',
        type: 'user_message',
      };
      
      const key = generateItemKey(item);
      expect(key).toBe('msg-msg-789');
    });

    it('should fall back to timestamp_us', () => {
      const item: Partial<ChatFlowItemData> = {
        timestamp_us: 1234567890,
        type: 'thought',
      };
      
      const key = generateItemKey(item);
      expect(key).toBe('ts-1234567890');
    });

    it('should generate unique fallback key for items without identifiers', () => {
      const item: Partial<ChatFlowItemData> = {
        type: 'thought',
      };
      
      const key1 = generateItemKey(item);
      const key2 = generateItemKey(item);
      
      expect(key1).toContain('unknown-');
      expect(key2).toContain('unknown-');
      // Keys should be different due to random component
      expect(key1).not.toBe(key2);
    });

    it('should distinguish tool_call and summarization with same mcp_event_id', () => {
      const toolCall: Partial<ChatFlowItemData> = {
        mcp_event_id: 'mcp-123',
        type: 'tool_call',
      };
      
      const summarization: Partial<ChatFlowItemData> = {
        mcp_event_id: 'mcp-123',
        type: 'summarization',
      };
      
      const key1 = generateItemKey(toolCall);
      const key2 = generateItemKey(summarization);
      
      expect(key1).toBe('mcp-mcp-123-tool_call');
      expect(key2).toBe('mcp-mcp-123-summarization');
      expect(key1).not.toBe(key2);
    });
  });
});
