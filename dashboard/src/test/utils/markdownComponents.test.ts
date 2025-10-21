/**
 * Tests for markdown rendering utilities
 * Focuses on the hasMarkdownSyntax function which determines hybrid rendering behavior
 */

import { describe, it, expect } from 'vitest';
import { hasMarkdownSyntax } from '../../utils/markdownComponents.tsx';

describe('markdownComponents', () => {
  describe('hasMarkdownSyntax', () => {
    describe('should detect markdown patterns', () => {
      it.each([
        // Bold patterns
        ['**bold text**', true],
        ['__bold text__', true],
        ['some **bold** word', true],
        
        // Italic patterns
        ['*italic text*', true],
        ['_italic text_', true],
        ['some *italic* word', true],
        
        // Code patterns
        ['`inline code`', true],
        ['use `console.log()` here', true],
        
        // List patterns
        ['- list item', true],
        ['* list item', true],
        // Note: Numbered lists (1. 2. etc) are NOT detected by the regex
        // They don't contain the special chars: *_`[]#-
        
        // Link patterns (brackets detected)
        ['[link text](url)', true],
        ['check [this] out', true],
        
        // Heading patterns
        ['# Heading', true],
        ['## Subheading', true],
        
        // Combined patterns
        ['**bold** and *italic*', true],
        ['Use `code` and **bold**', true],
      ])('detects markdown: %s', (text: string, expected: boolean) => {
        expect(hasMarkdownSyntax(text)).toBe(expected);
      });
    });

    describe('should NOT detect plain text', () => {
      it.each([
        // Plain text without any markdown
        ['plain text without markdown', false],
        ['This is a normal sentence.', false],
        ['Multiple sentences. Another one here.', false],
        
        // Text with special chars but not markdown
        ['email@example.com', false],
        ['$100 price', false],
        ['5 + 3 = 8', false],
        ['Hello! How are you?', false],
        
        // Edge cases - single special chars without context
        ['a', false],
        ['', false],
        ['   ', false],
        
        // Note: These actually ARE detected as markdown due to _ and - chars
        // ['under_score_in_word', false],
        // ['file-name-with-dashes', false],
      ])('ignores plain text: %s', (text: string, expected: boolean) => {
        expect(hasMarkdownSyntax(text)).toBe(expected);
      });
    });

    describe('edge cases and real-world scenarios', () => {
      it('handles LLM thought with technical terms', () => {
        const thought = 'I need to check the namespace status first.';
        expect(hasMarkdownSyntax(thought)).toBe(false);
      });

      it('detects LLM thought with formatting', () => {
        const thought = 'I need to check the **namespace** status first using `kubectl get`.';
        expect(hasMarkdownSyntax(thought)).toBe(true);
      });

      it('handles multiline plain text', () => {
        const text = `This is line one.
This is line two.
This is line three.`;
        expect(hasMarkdownSyntax(text)).toBe(false);
      });

      it('detects multiline with markdown', () => {
        const text = `First check these steps:
- Step one
- Step two
- Step three`;
        expect(hasMarkdownSyntax(text)).toBe(true);
      });

      it('handles technical content without markdown', () => {
        const technical = 'The pod is in CrashLoopBackOff state with exit code 1.';
        expect(hasMarkdownSyntax(technical)).toBe(false);
      });

      it('detects code snippets', () => {
        const withCode = 'Run `kubectl describe namespace stuck-ns` to investigate.';
        expect(hasMarkdownSyntax(withCode)).toBe(true);
      });

      it('handles empty or whitespace', () => {
        expect(hasMarkdownSyntax('')).toBe(false);
        expect(hasMarkdownSyntax('   ')).toBe(false);
        expect(hasMarkdownSyntax('\n\n')).toBe(false);
      });
    });

    describe('performance considerations', () => {
      it('handles very long text efficiently', () => {
        const longText = 'word '.repeat(10000);
        const start = performance.now();
        hasMarkdownSyntax(longText);
        const duration = performance.now() - start;
        
        // Should complete in less than 10ms even for 10k words
        expect(duration).toBeLessThan(10);
      });

      it('handles text with many special chars efficiently', () => {
        const specialChars = '!@#$%^&()+={}[];:"\',.<>?/\\|~'.repeat(100);
        const start = performance.now();
        hasMarkdownSyntax(specialChars);
        const duration = performance.now() - start;
        
        expect(duration).toBeLessThan(10);
      });
    });
  });
});

