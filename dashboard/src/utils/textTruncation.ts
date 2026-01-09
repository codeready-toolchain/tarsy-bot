/**
 * Text truncation utilities for auto-collapse feature
 * Used to truncate reasoning items (thoughts, final answers, etc.) to first 2 lines
 */

import type { ChatFlowItemData } from './chatFlowParser';

/**
 * Result of text truncation operation
 */
export interface TruncationResult {
  truncated: string;
  isTruncated: boolean;
  fullText: string;
}

/**
 * Truncate text to first 2 complete lines, with fallback to character limit for extremely long lines
 * 
 * @param text - The text to truncate
 * @param maxLineChars - Maximum characters per line before falling back to character-based truncation (default 500)
 * @returns TruncationResult with truncated text, truncation status, and original text
 * 
 * @example
 * // Short text (2 lines, under char limit)
 * truncateText("Line 1\nLine 2\nLine 3")
 * // Returns: { truncated: "Line 1\nLine 2...", isTruncated: true, fullText: "..." }
 * 
 * @example
 * // Long single line (over char limit)
 * truncateText("a".repeat(600))
 * // Returns: { truncated: "aaa...aaa...", isTruncated: true, fullText: "..." }
 */
export function truncateText(text: string, maxLineChars = 500): TruncationResult {
  if (!text) {
    return {
      truncated: '',
      isTruncated: false,
      fullText: text
    };
  }

  // Split text into lines
  const lines = text.split('\n');
  
  // Filter out empty lines (whitespace-only lines)
  const nonEmptyLines = lines.filter(line => line.trim().length > 0);
  
  // Special case: only empty lines but more than 2 lines total
  if (nonEmptyLines.length === 0 && lines.length > 2) {
    return {
      truncated: '\n...',
      isTruncated: true,
      fullText: text
    };
  }
  
  // If only 1-2 non-empty lines total, check if they're short enough
  if (nonEmptyLines.length <= 2) {
    const totalText = lines.join('\n');
    
    // Check if any line exceeds the character limit
    const hasLongLine = lines.some(line => line.length > maxLineChars);
    
    if (!hasLongLine) {
      // All lines are short enough, no truncation needed
      return {
        truncated: totalText,
        isTruncated: false,
        fullText: text
      };
    }
    
    // Fall through to character-based truncation
  }
  
  // Find first 2 non-empty lines and their positions in original array
  const firstTwoNonEmpty: Array<{ line: string; index: number }> = [];
  
  for (let i = 0; i < lines.length && firstTwoNonEmpty.length < 2; i++) {
    if (lines[i].trim().length > 0) {
      firstTwoNonEmpty.push({ line: lines[i], index: i });
    }
  }
  
  // If we don't have 2 non-empty lines, check if we need character-based truncation
  if (firstTwoNonEmpty.length < 2) {
    // If we have a single very long line, truncate it
    if (firstTwoNonEmpty.length === 1 && firstTwoNonEmpty[0].line.length > maxLineChars) {
      const line = firstTwoNonEmpty[0].line;
      const cutoff = line.lastIndexOf(' ', maxLineChars);
      const truncatedLine = line.substring(0, cutoff > 0 ? cutoff : maxLineChars) + '...';
      return {
        truncated: truncatedLine,
        isTruncated: true,
        fullText: text
      };
    }
    // Otherwise return as-is (short single line or only empty lines)
    return {
      truncated: text,
      isTruncated: false,
      fullText: text
    };
  }
  
  // Truncate each line if it's too long (for display purposes, use ~200 chars per line)
  const displayLineLength = 200;
  const truncatedLines: string[] = [];
  
  for (const { line } of firstTwoNonEmpty) {
    if (line.length > displayLineLength) {
      // Truncate at word boundary
      const cutoff = line.lastIndexOf(' ', displayLineLength);
      truncatedLines.push(line.substring(0, cutoff > 0 ? cutoff : displayLineLength) + '...');
    } else {
      truncatedLines.push(line);
    }
  }
  
  // Reconstruct with original empty lines preserved between the two non-empty lines
  const resultLines: string[] = [];
  const firstIndex = firstTwoNonEmpty[0].index;
  const secondIndex = firstTwoNonEmpty[1].index;
  
  // Add first non-empty line (truncated if needed)
  resultLines.push(truncatedLines[0]);
  
  // Add all lines between first and second non-empty lines (preserves empty lines)
  for (let i = firstIndex + 1; i <= secondIndex; i++) {
    if (i === secondIndex) {
      // Add second non-empty line (truncated if needed)
      resultLines.push(truncatedLines[1]);
    } else {
      // Preserve empty lines between
      resultLines.push(lines[i]);
    }
  }
  
  const twoLinesText = resultLines.join('\n');
  
  // Check if there's more content after the second non-empty line
  const hasMoreContent = secondIndex + 1 < lines.length;
  
  return {
    truncated: hasMoreContent ? twoLinesText + '...' : twoLinesText,
    isTruncated: hasMoreContent || truncatedLines.some(line => line.endsWith('...')),
    fullText: text
  };
}

/**
 * Generate a unique key for a chat flow item
 * Used for tracking auto-collapse state and manual expansions
 * 
 * @param item - Chat flow item (or partial item with identifying fields)
 * @returns Unique string key for the item
 * 
 * Priority:
 * 1. llm_interaction_id (for thoughts, final answers, native thinking)
 * 2. mcp_event_id + type (for tool calls, summarizations)
 * 3. messageId (for user messages)
 * 4. timestamp_us (fallback)
 */
export function generateItemKey(item: ChatFlowItemData | Partial<ChatFlowItemData>): string {
  // LLM interaction items (thought, final_answer, native_thinking)
  if (item.llm_interaction_id) {
    return `llm-${item.llm_interaction_id}`;
  }
  
  // MCP event items (tool_call, summarization) - include type to distinguish
  if (item.mcp_event_id && item.type) {
    return `mcp-${item.mcp_event_id}-${item.type}`;
  }
  
  // User messages
  if ('messageId' in item && item.messageId) {
    return `msg-${item.messageId}`;
  }
  
  // Fallback to timestamp
  if (item.timestamp_us) {
    return `ts-${item.timestamp_us}`;
  }
  
  // Last resort fallback
  return `unknown-${Date.now()}-${Math.random()}`;
}
