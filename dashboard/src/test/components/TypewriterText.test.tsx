/**
 * Minimal smoke tests for TypewriterText component
 * 
 * This is a visual/animation component that's better validated through:
 * - Visual review during development
 * - E2E/browser tests
 * - Manual testing
 * 
 * We only test that it doesn't crash with basic inputs.
 */

import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import TypewriterText from '../../components/TypewriterText';

describe('TypewriterText - Smoke Tests', () => {
  it('should render without crashing', () => {
    expect(() => {
      render(
        <TypewriterText text="Hello World">
          {(displayText) => <div>{displayText}</div>}
        </TypewriterText>
      );
    }).not.toThrow();
  });

  it('should handle empty text', () => {
    expect(() => {
      render(
        <TypewriterText text="">
          {(displayText) => <div>{displayText}</div>}
        </TypewriterText>
      );
    }).not.toThrow();
  });

  it('should work without children (default rendering)', () => {
    expect(() => {
      render(<TypewriterText text="Test" />);
    }).not.toThrow();
  });

  it('should accept speed and onComplete props', () => {
    const onComplete = () => {};
    expect(() => {
      render(
        <TypewriterText text="Test" speed={10} onComplete={onComplete}>
          {(displayText) => <div>{displayText}</div>}
        </TypewriterText>
      );
    }).not.toThrow();
  });
});
