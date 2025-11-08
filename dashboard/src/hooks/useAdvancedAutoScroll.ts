import { useEffect, useRef, useCallback, type RefObject } from 'react';

export interface AdvancedAutoScrollOptions {
  /** Whether auto-scroll is enabled */
  enabled?: boolean;
  /** Threshold distance from bottom (in pixels) to consider "at bottom" */
  threshold?: number;
  /** Delay before auto-scrolling after content change (ms) */
  scrollDelay?: number;
  /** CSS selector for the container to observe for changes */
  observeSelector?: string;
  /** Whether to enable debug logging */
  debug?: boolean;
  /** Scroll mode: 'window' for page scrolling, 'container' for element scrolling */
  scrollMode?: 'window' | 'container';
  /** Ref to scrollable container (required when scrollMode is 'container') */
  containerRef?: RefObject<HTMLElement | null>;
}

export interface AdvancedAutoScrollState {
  isUserAtBottom: boolean;
  userScrolledAway: boolean;
  isAutoScrolling: boolean;
}

/**
 * Advanced Auto-Scroll Hook
 * 
 * Uses MutationObserver to detect DOM changes and automatically scrolls to bottom
 * while respecting user interaction. Centralized approach to avoid conflicts.
 * 
 * Features:
 * - MutationObserver for reliable content change detection
 * - User interaction detection and respect
 * - Proper timing with requestAnimationFrame
 * - Configurable options
 * - Clean lifecycle management
 */
export function useAdvancedAutoScroll(options: AdvancedAutoScrollOptions = {}) {
  const {
    enabled = true,
    threshold = 10,
    scrollDelay = 300,
    observeSelector = '[data-autoscroll-container]',
    debug = false,
    scrollMode = 'window',
    containerRef
  } = options;

  // State tracking
  const stateRef = useRef<AdvancedAutoScrollState>({
    isUserAtBottom: true,
    userScrolledAway: false,
    isAutoScrolling: false
  });

  // Refs for cleanup
  const mutationObserverRef = useRef<MutationObserver | null>(null);
  const scrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const userScrollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rafIdRef = useRef<number | null>(null);
  const autoScrollMonitorRafRef = useRef<number | null>(null);
  const autoScrollStartTimeRef = useRef<number | null>(null);
  const userInteractionRef = useRef<boolean>(false);
  const clearUserInteractionTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const characterDataThrottleRef = useRef<number>(0); // Timestamp of last characterData scroll

  // Check if user is at bottom of page or container
  const isAtBottom = useCallback((): boolean => {
    if (scrollMode === 'container') {
      const container = containerRef?.current;
      if (!container) {
        if (debug) {
          console.warn('⚠️ Container ref is null, cannot check if at bottom');
        }
        return false;
      }
      
      const { scrollTop, scrollHeight, clientHeight } = container;
      const distanceFromBottom = scrollHeight - (scrollTop + clientHeight);
      
      if (debug) {
        console.log('📏 isAtBottom check (container):', {
          scrollTop,
          clientHeight,
          scrollHeight,
          distanceFromBottom,
          threshold,
          atBottom: distanceFromBottom <= threshold
        });
      }
      
      return distanceFromBottom <= threshold;
    } else {
      // Window mode
      const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
      const windowHeight = window.innerHeight;
      const documentHeight = document.documentElement.scrollHeight;
      const distanceFromBottom = documentHeight - scrollTop - windowHeight;
      
      if (debug) {
        console.log('📏 isAtBottom check (window):', {
          scrollTop,
          windowHeight,
          documentHeight,
          distanceFromBottom,
          threshold,
          atBottom: distanceFromBottom <= threshold
        });
      }
      
      return distanceFromBottom <= threshold;
    }
  }, [scrollMode, containerRef, threshold, debug]);

  // Scroll to bottom smoothly
  const scrollToBottom = useCallback((smooth: boolean = true): void => {
    if (rafIdRef.current) {
      cancelAnimationFrame(rafIdRef.current);
    }
    if (autoScrollMonitorRafRef.current) {
      cancelAnimationFrame(autoScrollMonitorRafRef.current);
      autoScrollMonitorRafRef.current = null;
    }

    // Start scroll on next frame for layout stability
    rafIdRef.current = requestAnimationFrame(() => {
      stateRef.current.isAutoScrolling = true;
      autoScrollStartTimeRef.current = performance.now();

      if (scrollMode === 'container') {
        const container = containerRef?.current;
        if (!container) {
          if (debug) {
            console.warn('⚠️ Container ref is null, cannot scroll');
          }
          stateRef.current.isAutoScrolling = false;
          return;
        }
        
        const targetTop = container.scrollHeight;
        if (smooth) {
          container.scrollTo({ top: targetTop, behavior: 'smooth' });
        } else {
          container.scrollTop = targetTop;
        }

        // Monitor until we actually reach (and remain at) the bottom
        const monitor = () => {
          const now = performance.now();
          const reachedBottom = (container.scrollHeight - container.scrollTop - container.clientHeight) <= threshold;

          if (reachedBottom) {
            stateRef.current.isAutoScrolling = false;
            autoScrollMonitorRafRef.current = null;
            return;
          }

          // Safety timeout (2s) to avoid getting stuck in auto-scrolling state
          if (autoScrollStartTimeRef.current !== null && now - autoScrollStartTimeRef.current > 2000) {
            stateRef.current.isAutoScrolling = false;
            autoScrollMonitorRafRef.current = null;
            return;
          }

          autoScrollMonitorRafRef.current = requestAnimationFrame(monitor);
        };

        autoScrollMonitorRafRef.current = requestAnimationFrame(monitor);
      } else {
        // Window mode
        const targetTop = document.documentElement.scrollHeight;
        if (smooth) {
          window.scrollTo({ top: targetTop, behavior: 'smooth' });
        } else {
          window.scrollTo(0, targetTop);
        }

        // Monitor until we actually reach (and remain at) the bottom
        const monitor = () => {
          const now = performance.now();
          const reachedBottom = (document.documentElement.scrollHeight - (window.pageYOffset || document.documentElement.scrollTop) - window.innerHeight) <= threshold;

          if (reachedBottom) {
            stateRef.current.isAutoScrolling = false;
            autoScrollMonitorRafRef.current = null;
            return;
          }

          // Safety timeout (2s) to avoid getting stuck in auto-scrolling state
          if (autoScrollStartTimeRef.current !== null && now - autoScrollStartTimeRef.current > 2000) {
            stateRef.current.isAutoScrolling = false;
            autoScrollMonitorRafRef.current = null;
            return;
          }

          autoScrollMonitorRafRef.current = requestAnimationFrame(monitor);
        };

        autoScrollMonitorRafRef.current = requestAnimationFrame(monitor);
      }
    });
  }, [scrollMode, containerRef, threshold, debug]);

  // Handle user scroll events
  const handleScroll = useCallback(() => {
    // Ignore scroll events caused by our own auto-scroll
    if (stateRef.current.isAutoScrolling) {
      if (debug) {
        console.log('🤖 AdvancedAutoScroll: Ignoring own scroll event');
      }
      return;
    }

    const wasAtBottom = stateRef.current.isUserAtBottom;
    const isNowAtBottom = isAtBottom();
    
    stateRef.current.isUserAtBottom = isNowAtBottom;

    if (wasAtBottom && !isNowAtBottom) {
      // Only treat as user intent if there was recent user interaction
      if (userInteractionRef.current) {
        stateRef.current.userScrolledAway = true;
        if (debug) {
          console.log('👆 AdvancedAutoScroll: User scrolled away from bottom');
        }
      } else if (debug) {
        console.log('↕️ AdvancedAutoScroll: Non-user scroll away detected, ignoring');
      }
    } else if (!wasAtBottom && isNowAtBottom) {
      // User scrolled back to bottom
      stateRef.current.userScrolledAway = false;
      if (debug) {
        console.log('👇 AdvancedAutoScroll: User scrolled back to bottom');
      }
    }

    // Clear any existing timeout
    if (userScrollTimeoutRef.current) {
      clearTimeout(userScrollTimeoutRef.current);
    }

    // Set a timeout to detect when user stops scrolling
    userScrollTimeoutRef.current = setTimeout(() => {
      if (debug) {
        console.log('⏸️ AdvancedAutoScroll: User scroll activity ended');
      }
    }, 1000);

  }, [isAtBottom, debug]);

  // Track user interactions that typically indicate an intent to scroll manually
  const markUserInteraction = useCallback(() => {
    userInteractionRef.current = true;
    if (clearUserInteractionTimeoutRef.current) {
      clearTimeout(clearUserInteractionTimeoutRef.current);
    }
    clearUserInteractionTimeoutRef.current = setTimeout(() => {
      userInteractionRef.current = false;
    }, 1500);
  }, []);

  // Track pointer interactions that might lead to scrolling (unified mouse/touch/pen)
  const handlePointerDown = useCallback((_e: PointerEvent) => {
    userInteractionRef.current = true;
    // Clear existing timeout but don't start a new one
    if (clearUserInteractionTimeoutRef.current) {
      clearTimeout(clearUserInteractionTimeoutRef.current);
      clearUserInteractionTimeoutRef.current = null;
    }
  }, []);

  const handlePointerUp = useCallback((_e: PointerEvent) => {
    // Start the TTL timer when pointer is released
    if (clearUserInteractionTimeoutRef.current) {
      clearTimeout(clearUserInteractionTimeoutRef.current);
    }
    clearUserInteractionTimeoutRef.current = setTimeout(() => {
      userInteractionRef.current = false;
    }, 1500);
  }, []);

  const handleKeydown = useCallback((e: KeyboardEvent) => {
    const scrollKeys = ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ', 'Spacebar'];
    if (scrollKeys.includes(e.key)) {
      markUserInteraction();
    }
  }, [markUserInteraction]);

  // Try to auto-scroll if conditions are met
  const tryAutoScroll = useCallback((delay: number = scrollDelay): Promise<boolean> => {
    return new Promise((resolve) => {
      if (!enabled) {
        if (debug) {
          console.log('🚫 AdvancedAutoScroll: Disabled');
        }
        resolve(false);
        return;
      }

      if (stateRef.current.userScrolledAway) {
        if (debug) {
          console.log('🚫 AdvancedAutoScroll: User scrolled away, skipping');
        }
        resolve(false);
        return;
      }

      // Clear any existing scroll timeout
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }

      scrollTimeoutRef.current = setTimeout(() => {
        // Double-check conditions before scrolling
        if (enabled && !stateRef.current.userScrolledAway) {
          scrollToBottom(true);
          if (debug) {
            console.log('🔄 AdvancedAutoScroll: Scrolled to bottom');
          }
          resolve(true);
        } else {
          if (debug) {
            console.log('🚫 AdvancedAutoScroll: Conditions changed, cancelled');
          }
          resolve(false);
        }
      }, delay);
    });
  }, [enabled, scrollDelay, scrollToBottom, debug]);

  // Setup MutationObserver to watch for content changes
  const setupMutationObserver = useCallback(() => {
    if (!enabled) return;

    // Clean up existing observer
    if (mutationObserverRef.current) {
      mutationObserverRef.current.disconnect();
    }

    // Find container to observe
    const container = document.querySelector(observeSelector);
    if (!container) {
      if (debug) {
        console.warn(`⚠️ AdvancedAutoScroll: Container not found: ${observeSelector}`);
      }
      return;
    }

    // Create new observer
    mutationObserverRef.current = new MutationObserver((mutations) => {
      let hasChildListChanges = false;
      let hasCharacterDataChanges = false;

      mutations.forEach((mutation) => {
        if (mutation.type === 'childList') {
          // New nodes added - always trigger immediately
          if (mutation.addedNodes.length > 0) {
            hasChildListChanges = true;
            if (debug) {
              console.log('📄 AdvancedAutoScroll: Content added', mutation.addedNodes.length, 'nodes');
            }
          }
        } else if (mutation.type === 'characterData' || mutation.type === 'attributes') {
          // Content or attributes changed - throttle to avoid typewriter spam
          hasCharacterDataChanges = true;
          if (debug) {
            console.log('📝 AdvancedAutoScroll: Content modified');
          }
        }
      });

      // Immediate scroll for new nodes (important content)
      if (hasChildListChanges) {
        tryAutoScroll();
      }
      // Throttled scroll for character changes (typewriter animation)
      else if (hasCharacterDataChanges) {
        const now = Date.now();
        const timeSinceLastScroll = now - characterDataThrottleRef.current;
        
        // Only scroll every 500ms for characterData changes
        if (timeSinceLastScroll >= 500) {
          characterDataThrottleRef.current = now;
          tryAutoScroll();
        }
      }
    });

    // Start observing
    mutationObserverRef.current.observe(container, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: false // Don't watch attributes to avoid noise
    });

    if (debug) {
      console.log('👀 AdvancedAutoScroll: MutationObserver started on', observeSelector);
    }
  }, [enabled, observeSelector, tryAutoScroll, debug]);

  // Initialize auto-scroll state
  useEffect(() => {
    if (!enabled) return;

    // Validate container ref for container mode
    if (scrollMode === 'container' && !containerRef?.current) {
      if (debug) {
        console.warn('⚠️ AdvancedAutoScroll: Container mode requires a valid containerRef');
      }
      return;
    }

    // Set initial state
    stateRef.current.isUserAtBottom = isAtBottom();
    stateRef.current.userScrolledAway = !stateRef.current.isUserAtBottom;

    if (debug) {
      console.log('🚀 AdvancedAutoScroll: Initialized', {
        scrollMode,
        isUserAtBottom: stateRef.current.isUserAtBottom,
        userScrolledAway: stateRef.current.userScrolledAway
      });
    }

    // Setup scroll and interaction listeners based on mode
    const scrollTarget = scrollMode === 'container' ? containerRef?.current : window;
    if (!scrollTarget) return;

    // Cast handlers to EventListener once for consistent add/remove
    const scrollListener = handleScroll as EventListener;
    const wheelListener = markUserInteraction as EventListener;
    const pointerDownListener = handlePointerDown as EventListener;
    const pointerUpListener = handlePointerUp as EventListener;
    const keydownListener = handleKeydown as EventListener;

    // Setup scroll listener
    scrollTarget.addEventListener('scroll', scrollListener, { passive: true });
    // Setup user interaction listeners
    scrollTarget.addEventListener('wheel', wheelListener, { passive: true });
    scrollTarget.addEventListener('pointerdown', pointerDownListener, { passive: true });
    scrollTarget.addEventListener('pointerup', pointerUpListener, { passive: true });
    scrollTarget.addEventListener('keydown', keydownListener);

    // Setup mutation observer
    setupMutationObserver();

    // Cleanup
    return () => {
      scrollTarget.removeEventListener('scroll', scrollListener);
      scrollTarget.removeEventListener('wheel', wheelListener);
      scrollTarget.removeEventListener('pointerdown', pointerDownListener);
      scrollTarget.removeEventListener('pointerup', pointerUpListener);
      scrollTarget.removeEventListener('keydown', keydownListener);
      
      if (mutationObserverRef.current) {
        mutationObserverRef.current.disconnect();
        mutationObserverRef.current = null;
      }
      
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
      
      if (userScrollTimeoutRef.current) {
        clearTimeout(userScrollTimeoutRef.current);
      }
      
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
      }
      if (autoScrollMonitorRafRef.current) {
        cancelAnimationFrame(autoScrollMonitorRafRef.current);
        autoScrollMonitorRafRef.current = null;
      }
      if (clearUserInteractionTimeoutRef.current) {
        clearTimeout(clearUserInteractionTimeoutRef.current);
        clearUserInteractionTimeoutRef.current = null;
      }

      if (debug) {
        console.log('🧹 AdvancedAutoScroll: Cleaned up');
      }
    };
  }, [enabled, scrollMode, containerRef, handleScroll, markUserInteraction, handlePointerDown, handlePointerUp, handleKeydown, setupMutationObserver, isAtBottom, debug]);

  // Re-setup observer when selector changes
  useEffect(() => {
    setupMutationObserver();
  }, [setupMutationObserver]);

  // Return control functions
  return {
    tryAutoScroll,
    scrollToBottom: () => scrollToBottom(true),
    getState: () => ({ ...stateRef.current }),
    isAtBottom
  };
}
