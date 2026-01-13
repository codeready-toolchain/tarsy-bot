/**
 * Chat Flow Item Type Constants
 * 
 * These constants define the different types of items that can appear in the chat flow timeline.
 * Used for type checking and rendering different UI components for each item type.
 */

/**
 * Chat flow item types for timeline rendering
 * 
 * THOUGHT: ReAct pattern thought
 * TOOL_CALL: MCP tool execution
 * FINAL_ANSWER: Final answer/result
 * FORCED_CONCLUSION: Forced conclusion when max iterations reached
 * STAGE_START: Stage execution marker
 * SUMMARIZATION: Tool result summarization
 * USER_MESSAGE: User's chat message
 * NATIVE_TOOL_USAGE: Native tools usage info (Gemini)
 * NATIVE_THINKING: Native thinking content (Gemini)
 * INTERMEDIATE_RESPONSE: Assistant response during intermediate iterations (native thinking)
 */
export const CHAT_FLOW_ITEM_TYPES = {
  THOUGHT: 'thought',
  TOOL_CALL: 'tool_call',
  FINAL_ANSWER: 'final_answer',
  FORCED_CONCLUSION: 'forced_conclusion',
  STAGE_START: 'stage_start',
  SUMMARIZATION: 'summarization',
  USER_MESSAGE: 'user_message',
  NATIVE_TOOL_USAGE: 'native_tool_usage',
  NATIVE_THINKING: 'native_thinking',
  INTERMEDIATE_RESPONSE: 'intermediate_response',
} as const;

/**
 * Type for chat flow item type values
 */
export type ChatFlowItemType = typeof CHAT_FLOW_ITEM_TYPES[keyof typeof CHAT_FLOW_ITEM_TYPES];
