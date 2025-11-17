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

