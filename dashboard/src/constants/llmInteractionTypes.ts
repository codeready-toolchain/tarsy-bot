/**
 * LLM Interaction Type Constants
 * 
 * These values must match the backend constants defined in:
 * backend/tarsy/models/constants.py (LLMInteractionType enum)
 */

/**
 * LLM interaction types for categorization and rendering.
 * 
 * INVESTIGATION: ReAct investigation/reasoning iterations (thought/action/observation loops)
 * SUMMARIZATION: MCP result summarization calls (reduce large tool outputs)
 * FINAL_ANALYSIS: Stage conclusion with "Final Answer:" (any stage, any strategy)
 * FINAL_ANALYSIS_SUMMARY: Executive summary of final analysis (dashboard display, notifications)
 */
export const LLM_INTERACTION_TYPES = {
  INVESTIGATION: 'investigation',
  SUMMARIZATION: 'summarization',
  FINAL_ANALYSIS: 'final_analysis',
  FINAL_ANALYSIS_SUMMARY: 'final_analysis_summary',
} as const;

/**
 * Type for LLM interaction type values
 */
export type LLMInteractionType = typeof LLM_INTERACTION_TYPES[keyof typeof LLM_INTERACTION_TYPES];
