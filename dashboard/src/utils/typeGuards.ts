import type { LLMInteraction, MCPInteraction, SystemEvent } from '../types';

/**
 * Type guards for safe type narrowing of interaction details
 * Used across components to validate interaction data before accessing type-specific fields
 */

/**
 * Type guard to check if details is an LLMInteraction
 * Validates by checking for the LLM-specific discriminator field
 */
export const isLLMInteraction = (details: unknown): details is LLMInteraction => {
  return (
    details !== null &&
    typeof details === 'object' &&
    'interaction_type' in details
  );
};

/**
 * Type guard to check if details is an MCPInteraction
 * Validates by checking for the MCP-specific discriminator field
 */
export const isMCPInteraction = (details: unknown): details is MCPInteraction => {
  return (
    details !== null &&
    typeof details === 'object' &&
    'communication_type' in details
  );
};

/**
 * Type guard to check if details is a SystemEvent
 * Validates by checking for the system event-specific discriminator field
 */
export const isSystemEvent = (details: unknown): details is SystemEvent => {
  return (
    details !== null &&
    typeof details === 'object' &&
    'event_type' in details
  );
};
