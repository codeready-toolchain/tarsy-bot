import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

interface TypewriterTextProps {
  text: string;
  speed?: number; // ms per character (default: 15)
  onComplete?: () => void;
  children?: (displayText: string, isAnimating: boolean) => ReactNode;
}

/**
 * Typewriter effect component for streaming content
 * 
 * Features:
 * - Updates target text immediately when new content arrives (no queuing)
 * - Continues animation smoothly from current position to new target
 * - Fast speed (~15ms per char) for ChatGPT-like feel
 * - Handles markdown content without flickering (passes full text to renderer)
 * - Efficient: only animates visible text, full content passed to ReactMarkdown
 * 
 * Behavior:
 * - Growing text (e.g., "Hello" → "Hello World"): continues from current position
 * - Non-growing text (e.g., "Hello" → "Goodbye"): resets and starts fresh animation
 * 
 * Usage:
 * ```tsx
 * <TypewriterText text={content} speed={15}>
 *   {(displayText, isAnimating) => (
 *     <Typography>{displayText}</Typography>
 *   )}
 * </TypewriterText>
 * ```
 */
export default function TypewriterText({ 
  text, 
  speed = 15, 
  onComplete,
  children 
}: TypewriterTextProps) {
  const [displayedText, setDisplayedText] = useState('');
  const [isAnimating, setIsAnimating] = useState(false);
  
  // Refs for animation state (avoids stale closures)
  const targetTextRef = useRef('');
  const displayedLengthRef = useRef(0);
  const animationFrameRef = useRef<number | null>(null);
  const lastUpdateTimeRef = useRef<number>(0);
  const completedRef = useRef(false);
  
  useEffect(() => {
    // Handle empty text - clear state and cancel RAF
    if (!text) {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
      setDisplayedText('');
      setIsAnimating(false);
      displayedLengthRef.current = 0;
      completedRef.current = true;
      targetTextRef.current = text;
      return;
    }
    
    // Get previous target and update ref
    const previousTarget = targetTextRef.current;
    targetTextRef.current = text;
    
    // If text hasn't changed, do nothing
    if (previousTarget === text) {
      return;
    }
    
    // Cancel any existing RAF before starting new animation
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
    
    // Check if text is growing (new content) or completely different (reset)
    const isGrowing = text.startsWith(previousTarget);
    
    if (!isGrowing) {
      // Completely new text - reset animation state
      displayedLengthRef.current = 0;
      completedRef.current = false;
    }
    
    // Always start animation (including on initial mount)
    setIsAnimating(true);
    completedRef.current = false;
    lastUpdateTimeRef.current = performance.now();
    
    const animate = (currentTime: number) => {
      const elapsed = currentTime - lastUpdateTimeRef.current;
      const target = targetTextRef.current;
      
      // Calculate how many characters to add based on elapsed time
      const charsToAdd = Math.floor(elapsed / speed);
      
      if (charsToAdd > 0) {
        const currentLength = displayedLengthRef.current;
        const newLength = Math.min(currentLength + charsToAdd, target.length);
        
        displayedLengthRef.current = newLength;
        setDisplayedText(target.slice(0, newLength));
        lastUpdateTimeRef.current = currentTime;
        
        // Check if animation is complete
        if (newLength >= target.length) {
          setIsAnimating(false);
          completedRef.current = true;
          animationFrameRef.current = null;
          
          // Call onComplete callback
          if (onComplete) {
            onComplete();
          }
          return;
        }
      }
      
      // Continue animation
      animationFrameRef.current = requestAnimationFrame(animate);
    };
    
    animationFrameRef.current = requestAnimationFrame(animate);
  }, [text, speed, onComplete]);
  
  // Cleanup animation on unmount
  useEffect(() => {
    return () => {
      if (animationFrameRef.current) {
        cancelAnimationFrame(animationFrameRef.current);
        animationFrameRef.current = null;
      }
    };
  }, []);
  
  // Render using children render prop
  if (children) {
    return <>{children(displayedText, isAnimating)}</>;
  }
  
  // Default rendering
  return <>{displayedText}</>;
}

