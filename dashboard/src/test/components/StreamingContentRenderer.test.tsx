/**
 * Smoke tests for StreamingContentRenderer
 * 
 * This component orchestrates TypewriterText with markdown rendering.
 * Complex animation behavior is tested visually/manually.
 * We only verify it renders different item types without crashing.
 */

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import StreamingContentRenderer, { type StreamingItem } from '../../components/StreamingContentRenderer';

describe('StreamingContentRenderer - Smoke Tests', () => {
  it('should render thought items', () => {
    const item: StreamingItem = {
      type: 'thought',
      content: 'Analyzing the issue...',
    };

    expect(() => {
      render(<StreamingContentRenderer item={item} />);
    }).not.toThrow();
  });

  it('should render final_answer items', () => {
    const item: StreamingItem = {
      type: 'final_answer',
      content: 'The issue is resolved.',
    };

    expect(() => {
      render(<StreamingContentRenderer item={item} />);
    }).not.toThrow();
  });

  it('should render native_thinking items', () => {
    const item: StreamingItem = {
      type: 'native_thinking',
      content: 'Analyzing with native thinking mode...',
    };

    expect(() => {
      render(<StreamingContentRenderer item={item} />);
    }).not.toThrow();
  });

  it('should render summarization items', () => {
    const item: StreamingItem = {
      type: 'summarization',
      content: 'Tool returned successfully.',
    };

    expect(() => {
      render(<StreamingContentRenderer item={item} />);
    }).not.toThrow();
  });

  it('should handle empty content', () => {
    const item: StreamingItem = {
      type: 'thought',
      content: '',
    };

    expect(() => {
      render(<StreamingContentRenderer item={item} />);
    }).not.toThrow();
  });

  it('should return null for unsupported types', () => {
    const item: StreamingItem = {
      type: 'tool_call',
      content: 'Some content',
    };

    const { container } = render(<StreamingContentRenderer item={item} />);
    expect(container.firstChild).toBeNull();
  });
});

