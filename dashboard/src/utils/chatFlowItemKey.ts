/**
 * Utilities for generating unique keys for chat flow items
 * Used for tracking auto-collapse state and manual expansions
 */

import type { ChatFlowItemData } from './chatFlowParser';

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
  // Include type to distinguish thought/native_thinking from final_answer in same interaction
  if (item.llm_interaction_id && item.type) {
    return `llm-${item.llm_interaction_id}-${item.type}`;
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
