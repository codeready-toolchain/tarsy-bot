/**
 * Tests for useAdvancedAutoScroll hook
 * 
 * Focuses on the valuable calculation logic:
 * - isAtBottom calculations (container vs window mode)
 * - Threshold handling
 * 
 * Avoids testing complex async behaviors (event listeners, MutationObserver)
 * which are better suited for integration/E2E tests.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useAdvancedAutoScroll } from '../../hooks/useAdvancedAutoScroll';
import { createRef } from 'react';

describe('useAdvancedAutoScroll - Calculation Logic', () => {
  let mockContainer: HTMLDivElement;

  beforeEach(() => {
    // Create mock container
    mockContainer = document.createElement('div');
    Object.defineProperties(mockContainer, {
      scrollTop: { value: 0, writable: true, configurable: true },
      scrollHeight: { value: 1000, writable: true, configurable: true },
      clientHeight: { value: 500, writable: true, configurable: true },
    });

    // Mock minimal dependencies
    vi.spyOn(document, 'querySelector').mockReturnValue(mockContainer);
    global.MutationObserver = vi.fn(() => ({
      observe: vi.fn(),
      disconnect: vi.fn(),
    })) as any;
    global.requestAnimationFrame = vi.fn((cb) => {
      cb(0);
      return 1;
    }) as any;
    global.cancelAnimationFrame = vi.fn();
    mockContainer.scrollTo = vi.fn();
    window.scrollTo = vi.fn();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'log').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Container Mode - isAtBottom', () => {
    it('should return true when container is at bottom', () => {
      const containerRef = createRef<HTMLDivElement>();
      (containerRef as any).current = mockContainer;

      // At bottom: scrollTop (500) + clientHeight (500) = scrollHeight (1000)
      Object.defineProperty(mockContainer, 'scrollTop', { value: 500 });
      Object.defineProperty(mockContainer, 'scrollHeight', { value: 1000 });
      Object.defineProperty(mockContainer, 'clientHeight', { value: 500 });

      const { result } = renderHook(() =>
        useAdvancedAutoScroll({
          scrollMode: 'container',
          containerRef,
          threshold: 10,
        })
      );

      expect(result.current.isAtBottom()).toBe(true);
    });

    it('should return false when container is scrolled up', () => {
      const containerRef = createRef<HTMLDivElement>();
      (containerRef as any).current = mockContainer;

      // Scrolled up: 1000 - (400 + 500) = 100px from bottom
      Object.defineProperty(mockContainer, 'scrollTop', { value: 400 });
      Object.defineProperty(mockContainer, 'scrollHeight', { value: 1000 });
      Object.defineProperty(mockContainer, 'clientHeight', { value: 500 });

      const { result } = renderHook(() =>
        useAdvancedAutoScroll({
          scrollMode: 'container',
          containerRef,
          threshold: 10,
        })
      );

      expect(result.current.isAtBottom()).toBe(false);
    });

    it('should respect threshold parameter', () => {
      const containerRef = createRef<HTMLDivElement>();
      (containerRef as any).current = mockContainer;

      // 15px from bottom
      Object.defineProperty(mockContainer, 'scrollTop', { value: 485 });
      Object.defineProperty(mockContainer, 'scrollHeight', { value: 1000 });
      Object.defineProperty(mockContainer, 'clientHeight', { value: 500 });

      // threshold=10: should be false (15 > 10)
      const { result: result1 } = renderHook(() =>
        useAdvancedAutoScroll({
          scrollMode: 'container',
          containerRef,
          threshold: 10,
        })
      );
      expect(result1.current.isAtBottom()).toBe(false);

      // threshold=20: should be true (15 <= 20)
      const { result: result2 } = renderHook(() =>
        useAdvancedAutoScroll({
          scrollMode: 'container',
          containerRef,
          threshold: 20,
        })
      );
      expect(result2.current.isAtBottom()).toBe(true);
    });
  });

  describe('Window Mode - isAtBottom', () => {
    beforeEach(() => {
      Object.defineProperties(document.documentElement, {
        scrollTop: { value: 0, writable: true, configurable: true },
        scrollHeight: { value: 2000, writable: true, configurable: true },
      });
      Object.defineProperty(window, 'innerHeight', { value: 800, writable: true });
      Object.defineProperty(window, 'pageYOffset', { value: 0, writable: true });
    });

    it('should return true when window is at bottom', () => {
      // At bottom: 1200 + 800 = 2000
      Object.defineProperty(document.documentElement, 'scrollTop', { value: 1200 });
      Object.defineProperty(window, 'pageYOffset', { value: 1200 });

      const { result } = renderHook(() =>
        useAdvancedAutoScroll({
          scrollMode: 'window',
          threshold: 10,
        })
      );

      expect(result.current.isAtBottom()).toBe(true);
    });

    it('should return false when window is scrolled up', () => {
      // Scrolled up: 2000 - 500 - 800 = 700px from bottom
      Object.defineProperty(document.documentElement, 'scrollTop', { value: 500 });
      Object.defineProperty(window, 'pageYOffset', { value: 500 });

      const { result } = renderHook(() =>
        useAdvancedAutoScroll({
          scrollMode: 'window',
          threshold: 10,
        })
      );

      expect(result.current.isAtBottom()).toBe(false);
    });
  });

  describe('API Methods', () => {
    it('should provide all expected methods', () => {
      const { result } = renderHook(() =>
        useAdvancedAutoScroll({ scrollMode: 'window' })
      );

      expect(result.current.scrollToBottom).toBeDefined();
      expect(result.current.isAtBottom).toBeDefined();
      expect(result.current.getState).toBeDefined();
      expect(result.current.tryAutoScroll).toBeDefined();
    });

    it('should provide state via getState', () => {
      const { result } = renderHook(() =>
        useAdvancedAutoScroll({ scrollMode: 'window' })
      );

      const state = result.current.getState();
      expect(state).toHaveProperty('isUserAtBottom');
      expect(state).toHaveProperty('userScrolledAway');
      expect(state).toHaveProperty('isAutoScrolling');
    });
  });

  describe('Configuration', () => {
    it('should work when disabled', () => {
      const { result } = renderHook(() =>
        useAdvancedAutoScroll({
          enabled: false,
          scrollMode: 'window',
        })
      );

      expect(result.current.isAtBottom).toBeDefined();
      expect(() => result.current.isAtBottom()).not.toThrow();
    });

    it('should accept threshold configuration', () => {
      expect(() => {
        renderHook(() =>
          useAdvancedAutoScroll({
            scrollMode: 'window',
            threshold: 50,
          })
        );
      }).not.toThrow();
    });
  });
});
