import { useEffect, useLayoutEffect, useRef, useState } from 'react';

interface UseAutoCollapseOptions {
  isAutoCollapsed: boolean;
  expandAll: boolean;
  isCollapsible: boolean;
  content: string;
  onToggleAutoCollapse?: () => void;
}

interface UseAutoCollapseReturn {
  shouldCollapse: boolean;
  shouldClampPreview: boolean;
  isTruncated: boolean;
  wasTruncated: boolean;
  isAutoCollapsing: boolean;
  isClickable: boolean;
  contentRef: React.RefObject<HTMLDivElement | null>;
  handleToggle: () => void;
}

/**
 * Hook to manage auto-collapse behavior for content items.
 * Handles:
 * - Auto-collapse detection (streaming → DB transition)
 * - Manual expand/collapse
 * - Truncation detection
 * - Smooth animations
 */
export function useAutoCollapse({
  isAutoCollapsed,
  expandAll,
  isCollapsible,
  content,
  onToggleAutoCollapse,
}: UseAutoCollapseOptions): UseAutoCollapseReturn {
  const shouldCollapse = isAutoCollapsed && !expandAll;
  const contentRef = useRef<HTMLDivElement | null>(null);
  const [isTruncated, setIsTruncated] = useState(false);
  const [wasTruncated, setWasTruncated] = useState(false);
  const [isAutoCollapsing, setIsAutoCollapsing] = useState(false);
  const [isCollapsing, setIsCollapsing] = useState(false);
  const prevShouldCollapseRef = useRef(shouldCollapse);
  const manualInteractionRef = useRef(false);
  const isStartingCollapse = !prevShouldCollapseRef.current && shouldCollapse;

  // Track when we're actively collapsing (for delayed clamp).
  // Must run in layout effect so the clamp is disabled before the browser paints the collapsed frame.
  useLayoutEffect(() => {
    if (!prevShouldCollapseRef.current && shouldCollapse) {
      setIsCollapsing(true);
      const timer = setTimeout(() => setIsCollapsing(false), 300); // Match Collapse timeout
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [shouldCollapse]);

  // Detect auto-collapse (streaming → DB transition)
  useEffect(() => {
    const wasExpanded = !prevShouldCollapseRef.current;
    const isNowCollapsed = shouldCollapse;

    if (wasExpanded && isNowCollapsed && !manualInteractionRef.current) {
      // This is an auto-collapse (not manual) - trigger fade animation
      setIsAutoCollapsing(true);
      const timer = setTimeout(() => setIsAutoCollapsing(false), 600);
      return () => clearTimeout(timer);
    }

    // Reset manual interaction flag after processing
    manualInteractionRef.current = false;
    prevShouldCollapseRef.current = shouldCollapse;
  }, [shouldCollapse]);

  // Detect if content is visually truncated
  useEffect(() => {
    // Only check truncation when collapsed AND clamp is active (not during collapse animation)
    if (shouldCollapse && !isCollapsing && contentRef.current) {
      // Small delay to ensure DOM is ready
      const timer = setTimeout(() => {
        if (contentRef.current) {
          // Check if scrollHeight > clientHeight (means content is clamped)
          const truncated =
            contentRef.current.scrollHeight > contentRef.current.clientHeight;
          setIsTruncated(truncated);
          if (truncated) {
            setWasTruncated(true); // Remember that it was truncated
          }
        }
      }, 10);
      return () => clearTimeout(timer);
    } else {
      setIsTruncated(false);
    }
  }, [shouldCollapse, isCollapsing, content]);

  // Show collapse button if content was ever truncated
  const isClickable = isCollapsible && !expandAll && (wasTruncated || isTruncated);

  // Wrap toggle handler to prevent fade animation on manual interaction
  const handleToggle = () => {
    manualInteractionRef.current = true; // Mark as manual interaction
    setIsAutoCollapsing(false); // Stop any ongoing fade animation
    if (onToggleAutoCollapse) {
      onToggleAutoCollapse();
    }
  };

  // Only apply clamp when collapsed AND not actively collapsing.
  // Also disable clamp on the very first render where we *start* collapsing, to avoid a one-frame snap.
  const shouldClampPreview = shouldCollapse && !isCollapsing && !isStartingCollapse;

  return {
    shouldCollapse,
    shouldClampPreview,
    isTruncated,
    wasTruncated,
    isAutoCollapsing,
    isClickable,
    contentRef,
    handleToggle,
  };
}
