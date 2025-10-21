/**
 * Tests for search utility functions
 * Testing highlighting and filter logic
 */

import { describe, it, expect } from 'vitest';
import React from 'react';
import {
  highlightSearchTermNodes,
  hasActiveFilters,
} from '../../utils/search';

describe('search utilities', () => {
  describe('highlightSearchTermNodes', () => {
    it('should return original text in fragment when search term is empty', () => {
      const result = highlightSearchTermNodes('hello world', '');
      expect(result).toHaveLength(1);
      expect(result[0]).toBe('hello world');
    });

    it('should return empty string fragment for empty text', () => {
      const result = highlightSearchTermNodes('', 'test');
      expect(result).toHaveLength(1);
      expect(result[0]).toBe('');
    });

    it('should return original text when search term is whitespace', () => {
      const result = highlightSearchTermNodes('hello world', '   ');
      expect(result).toHaveLength(1);
      expect(result[0]).toBe('hello world');
    });

    it('should create React nodes for highlighting', () => {
      const result = highlightSearchTermNodes('hello world', 'world');
      expect(result.length).toBeGreaterThan(1);
      
      // Check that one of the nodes is a mark element
      const hasMarkNode = result.some((node: any) => {
        return React.isValidElement(node) && node.type === 'mark';
      });
      expect(hasMarkNode).toBe(true);
    });

    it('should be case insensitive', () => {
      const result = highlightSearchTermNodes('Hello World', 'world');
      expect(result.length).toBeGreaterThan(1);
    });

    it('should highlight multiple occurrences', () => {
      const result = highlightSearchTermNodes('test test test', 'test');
      // Should have: text, mark, text, mark, text, mark, text (7 parts)
      // Or: mark, text, mark, text, mark (5 parts) depending on position
      expect(result.length).toBeGreaterThanOrEqual(5);
    });

    it('should escape special regex characters', () => {
      const result = highlightSearchTermNodes('hello (world)', '(world)');
      expect(result.length).toBeGreaterThan(1);
    });

    it('should handle partial matches', () => {
      const result = highlightSearchTermNodes('testing', 'test');
      expect(result.length).toBeGreaterThan(1);
    });

    it('should preserve text before and after match', () => {
      const result = highlightSearchTermNodes('before match after', 'match');
      expect(result.length).toBe(3);
      
      // First should be Fragment with 'before '
      expect((result[0] as any).props?.children).toBe('before ');
      
      // Second should be mark with 'match'
      expect(React.isValidElement(result[1])).toBe(true);
      expect((result[1] as any).type).toBe('mark');
      
      // Third should be Fragment with ' after'
      expect((result[2] as any).props?.children).toBe(' after');
    });

    it('should apply correct styles to mark elements', () => {
      const result = highlightSearchTermNodes('test', 'test');
      const markNode = result.find((node: any) => 
        React.isValidElement(node) && node.type === 'mark'
      ) as React.ReactElement;
      
      expect(markNode).toBeDefined();
      expect((markNode.props as any).style).toEqual({
        backgroundColor: '#ffeb3b',
        padding: '1px 2px',
        borderRadius: 2,
      });
    });

    it('should handle consecutive matches', () => {
      const result = highlightSearchTermNodes('testtest', 'test');
      // Should have multiple marks
      const markCount = result.filter((node: any) => 
        React.isValidElement(node) && node.type === 'mark'
      ).length;
      expect(markCount).toBe(2);
    });

    it('should handle text with no matches', () => {
      const result = highlightSearchTermNodes('hello world', 'xyz');
      expect(result).toHaveLength(1);
      // The result is a React.Fragment with the text, not a plain string
      const fragment = result[0] as React.ReactElement;
      expect(React.isValidElement(fragment)).toBe(true);
      expect((fragment.props as any).children).toBe('hello world');
    });

    it('should not be vulnerable to XSS', () => {
      const result = highlightSearchTermNodes(
        '<script>alert("xss")</script>',
        'script'
      );
      
      // Should contain React nodes, not raw HTML
      const hasMarkNode = result.some((node: any) => 
        React.isValidElement(node) && node.type === 'mark'
      );
      expect(hasMarkNode).toBe(true);
      
      // Content should be properly escaped as text content
      const markNode = result.find((node: any) => 
        React.isValidElement(node) && node.type === 'mark'
      ) as React.ReactElement;
      expect((markNode?.props as any)?.children).toBe('script');
    });
  });

  describe('hasActiveFilters', () => {
    it('should return false when all filters are empty', () => {
      const filters = {
        search: '',
        status: [],
        agent_type: [],
        alert_type: [],
      };
      expect(hasActiveFilters(filters)).toBe(false);
    });

    it('should return true when search has value', () => {
      const filters = {
        search: 'test query',
        status: [],
        agent_type: [],
        alert_type: [],
      };
      expect(hasActiveFilters(filters)).toBe(true);
    });

    it('should return false when search is only whitespace', () => {
      const filters = {
        search: '   ',
        status: [],
        agent_type: [],
        alert_type: [],
      };
      expect(hasActiveFilters(filters)).toBe(false);
    });

    it('should return true when status has values', () => {
      const filters = {
        search: '',
        status: ['completed'],
        agent_type: [],
        alert_type: [],
      };
      expect(hasActiveFilters(filters)).toBe(true);
    });

    it('should return true when agent_type has values', () => {
      const filters = {
        search: '',
        status: [],
        agent_type: ['kubernetes'],
        alert_type: [],
      };
      expect(hasActiveFilters(filters)).toBe(true);
    });

    it('should return true when alert_type has values', () => {
      const filters = {
        search: '',
        status: [],
        agent_type: [],
        alert_type: ['critical'],
      };
      expect(hasActiveFilters(filters)).toBe(true);
    });

    it('should return true when multiple filters are active', () => {
      const filters = {
        search: 'test',
        status: ['completed', 'failed'],
        agent_type: ['kubernetes'],
        alert_type: ['critical'],
      };
      expect(hasActiveFilters(filters)).toBe(true);
    });

    it('should handle undefined values', () => {
      const filters = {
        search: undefined,
        status: undefined,
        agent_type: undefined,
        alert_type: undefined,
      };
      expect(hasActiveFilters(filters)).toBe(false);
    });

    it('should handle missing properties', () => {
      const filters = {};
      expect(hasActiveFilters(filters)).toBe(false);
    });

    it('should handle partial filter objects', () => {
      const filters = {
        search: 'test',
      };
      expect(hasActiveFilters(filters)).toBe(true);
    });

    it('should handle null arrays', () => {
      const filters = {
        search: '',
        status: null,
        agent_type: null,
        alert_type: null,
      } as any;
      expect(hasActiveFilters(filters)).toBe(false);
    });

    it('should handle arrays with empty strings', () => {
      const filters = {
        search: '',
        status: [''],
        agent_type: [],
        alert_type: [],
      };
      // Array has length > 0, so should return true
      expect(hasActiveFilters(filters)).toBe(true);
    });
  });
});

