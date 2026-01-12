/**
 * WebSocket event type constants
 * Centralizes all event type strings to avoid hardcoding across the dashboard
 */

// Session lifecycle events
export const SESSION_EVENTS = {
  CREATED: 'session.created',
  STARTED: 'session.started',
  PAUSED: 'session.paused',
  RESUMED: 'session.resumed',
  COMPLETED: 'session.completed',
  FAILED: 'session.failed',
  CANCELLED: 'session.cancelled',
  CANCEL_REQUESTED: 'session.cancel_requested',
  STATUS_CHANGE: 'session.status_change',
} as const;

// Stage lifecycle events
export const STAGE_EVENTS = {
  STARTED: 'stage.started',
  COMPLETED: 'stage.completed',
  FAILED: 'stage.failed',
} as const;

// LLM interaction events
export const LLM_EVENTS = {
  CALL_STARTED: 'llm.call.started',
  CALL_COMPLETED: 'llm.call.completed',
  CALL_FAILED: 'llm.call.failed',
  STREAMING_CHUNK: 'llm.streaming.chunk',
  STREAMING_COMPLETE: 'llm.streaming.complete',
  STREAM_CHUNK: 'llm.stream.chunk',  // Real-time streaming event type
} as const;

// MCP tool interaction events
export const MCP_EVENTS = {
  TOOL_CALL_STARTED: 'mcp.tool_call.started',
  TOOL_CALL_COMPLETED: 'mcp.tool_call.completed',
  TOOL_CALL_FAILED: 'mcp.tool_call.failed',
} as const;

// Chain progress events
export const CHAIN_EVENTS = {
  PROGRESS: 'chain.progress',
} as const;

// Agent lifecycle events (for parallel agents)
export const AGENT_EVENTS = {
  CANCELLED: 'agent.cancelled',
} as const;

// LLM streaming content types (stream_type field in llm.stream.chunk events)
export const STREAMING_CONTENT_TYPES = {
  THOUGHT: 'thought',
  FINAL_ANSWER: 'final_answer',
  INTERMEDIATE_RESPONSE: 'intermediate_response',
  SUMMARIZATION: 'summarization',
  NATIVE_THINKING: 'native_thinking',
} as const;

// Type for streaming content types
export type StreamingContentType = typeof STREAMING_CONTENT_TYPES[keyof typeof STREAMING_CONTENT_TYPES];

// All valid streaming content types (for type checking)
export const ALL_STREAMING_CONTENT_TYPES = [
  STREAMING_CONTENT_TYPES.THOUGHT,
  STREAMING_CONTENT_TYPES.FINAL_ANSWER,
  STREAMING_CONTENT_TYPES.INTERMEDIATE_RESPONSE,
  STREAMING_CONTENT_TYPES.SUMMARIZATION,
  STREAMING_CONTENT_TYPES.NATIVE_THINKING,
] as const;

// All terminal session events (session has finished processing)
export const TERMINAL_SESSION_EVENTS = [
  SESSION_EVENTS.COMPLETED,
  SESSION_EVENTS.FAILED,
  SESSION_EVENTS.CANCELLED,
] as const;

/**
 * Check if event type represents a terminal session state
 */
export function isTerminalSessionEvent(eventType: string): boolean {
  return TERMINAL_SESSION_EVENTS.includes(eventType as any);
}

/**
 * Check if event type is a session event
 */
export function isSessionEvent(eventType: string): boolean {
  return eventType.startsWith('session.');
}

/**
 * Check if event type is a stage event
 */
export function isStageEvent(eventType: string): boolean {
  return eventType.startsWith('stage.');
}

/**
 * Check if event type is an LLM event
 */
export function isLLMEvent(eventType: string): boolean {
  return eventType.startsWith('llm.');
}

/**
 * Check if event type is an MCP event
 */
export function isMCPEvent(eventType: string): boolean {
  return eventType.startsWith('mcp.');
}

/**
 * Check if a string is a valid streaming content type
 */
export function isValidStreamingContentType(type: string): type is StreamingContentType {
  return ALL_STREAMING_CONTENT_TYPES.includes(type as StreamingContentType);
}

/**
 * Safely cast a stream_type string to StreamingContentType
 * Returns the type if valid, or 'thought' as fallback
 */
export function parseStreamingContentType(streamType: string): StreamingContentType {
  if (isValidStreamingContentType(streamType)) {
    return streamType;
  }
  console.warn(`Unknown streaming content type: ${streamType}, defaulting to 'thought'`);
  return STREAMING_CONTENT_TYPES.THOUGHT;
}

