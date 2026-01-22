import type { TimelineItem, MCPInteraction, StageExecution } from '../types';
import { formatTimestamp, formatDurationMs } from './timestamp';
import { getMessages } from './conversationParser';
import { isLLMInteraction, isMCPInteraction } from './typeGuards';
import { LLM_INTERACTION_TYPES } from '../constants/llmInteractionTypes';
import { STAGE_STATUS } from './statusConstants';

/**
 * Shared helper functions for timeline components
 * Extracted to reduce duplication between NestedAccordionTimeline and VirtualizedAccordionTimeline
 */

// Stage status color mapping
export const getStageStatusColor = (status: string): 'success' | 'error' | 'primary' | 'warning' | 'default' => {
  switch (status) {
    case STAGE_STATUS.COMPLETED:
      return 'success';
    case STAGE_STATUS.FAILED:
    case STAGE_STATUS.TIMED_OUT:
      return 'error';
    case STAGE_STATUS.ACTIVE:
      return 'primary';
    case STAGE_STATUS.PENDING:
    case STAGE_STATUS.PAUSED:
    case STAGE_STATUS.CANCELLED:
      return 'warning';
    default:
      return 'default';
  }
};

// Interaction type color mapping
export const getInteractionColor = (type: string): 'primary' | 'secondary' | 'warning' => {
  switch (type) {
    case 'llm':
      return 'primary';    // Blue
    case 'mcp':
      return 'secondary';  // Purple  
    case 'system':
      return 'warning';    // Orange
    default:  
      return 'primary';
  }
};

// Helper function to check if an MCP interaction is a tool list operation
export const isToolList = (mcpDetails: MCPInteraction): boolean => {
  return mcpDetails.communication_type === 'tool_list' || 
         (mcpDetails.communication_type === 'tool_call' && mcpDetails.tool_name === 'list_tools');
};

// Format individual interaction for copying
export const formatInteractionForCopy = (interaction: TimelineItem): string => {
  const timestamp = formatTimestamp(interaction.timestamp_us, 'absolute');
  const duration = interaction.duration_ms ? ` (${formatDurationMs(interaction.duration_ms)})` : '';
  
  let content = `${interaction.step_description}${duration}\n`;
  content += `Type: ${interaction.type.toUpperCase()}\n`;
  content += `Time: ${timestamp}\n`;
  
  if (interaction.details) {
    if (interaction.type === 'llm' && isLLMInteraction(interaction.details)) {
      content += `Model: ${interaction.details.model_name || 'N/A'}\n`;
      
      // Show interaction type if it's a summarization, final analysis, or forced conclusion
      const interactionType = interaction.details.interaction_type || LLM_INTERACTION_TYPES.INVESTIGATION;
      if (interactionType === LLM_INTERACTION_TYPES.SUMMARIZATION) {
        content += `Interaction Type: Summarization${interaction.details.mcp_event_id ? ` (MCP Event: ${interaction.details.mcp_event_id})` : ''}\n`;
      } else if (interactionType === LLM_INTERACTION_TYPES.FINAL_ANALYSIS) {
        content += `Interaction Type: Final Analysis\n`;
      } else if (interactionType === LLM_INTERACTION_TYPES.FORCED_CONCLUSION) {
        content += `Interaction Type: Forced Conclusion (Max Iterations)\n`;
      }
      
      // EP-0014: Use getMessages helper to extract conversation messages properly
      const messages = getMessages(interaction.details);
      
      if (messages.length > 0) {
        content += `\n--- CONVERSATION ---\n`;
        messages.forEach((message) => {
          const role = message.role.toUpperCase();
          const messageContent = typeof message.content === 'string' ? message.content : 
                                (message.content == null || message.content === '') ? '' :
                                JSON.stringify(message.content);
          content += `${role}:\n${messageContent}\n\n`;
        });
      } else {
        content += `Conversation: No messages available\n`;
      }
      
      // Show error if failed
      if (interaction.details.success === false) {
        content += `ERROR: ${interaction.details.error_message || 'LLM request failed - no response received'}\n`;
      }
      
      if (interaction.details.total_tokens) {
        content += `Tokens Used: ${interaction.details.total_tokens}\n`;
      }
      if (interaction.details.temperature !== undefined) {
        content += `Temperature: ${interaction.details.temperature}\n`;
      }
    } else if (interaction.type === 'mcp' && isMCPInteraction(interaction.details)) {
      content += `Server: ${interaction.details.server_name || 'N/A'}\n`;
      content += `Communication Type: ${interaction.details.communication_type || 'N/A'}\n`;
      content += `Success: ${interaction.details.success}\n`;
      
      if (isToolList(interaction.details)) {
        // For tool list operations, show available tools instead of parameters/result
        content += `Tool: list_tools\n`;
        if (interaction.details.available_tools) {
          content += `\n--- AVAILABLE TOOLS ---\n`;
          content += `${JSON.stringify(interaction.details.available_tools, null, 2)}\n`;
        } else {
          content += `Available Tools: None listed\n`;
        }
      } else {
        // For regular tool calls, show tool name, parameters, and result
        content += `Tool: ${interaction.details.tool_name || 'N/A'}\n`;
        
        if (interaction.details.tool_arguments && Object.keys(interaction.details.tool_arguments).length > 0) {
          content += `\n--- PARAMETERS ---\n`;
          content += `${JSON.stringify(interaction.details.tool_arguments, null, 2)}\n`;
        } else {
          content += `Parameters: None\n`;
        }
        
        if (interaction.details.tool_result && Object.keys(interaction.details.tool_result).length > 0) {
          content += `\n--- RESULT ---\n`;
          content += `${JSON.stringify(interaction.details.tool_result, null, 2)}\n`;
        } else {
          content += `Result: ${interaction.details.success ? 'Success (no data)' : 'Failed'}\n`;
        }
      }
    }
  }
  
  return content;
};

// Format stage with all interactions for copying
export const formatStageForCopy = (stage: StageExecution, stageIndex: number, interactions: TimelineItem[]): string => {
  let content = `STAGE ${stageIndex + 1}: ${stage.stage_name.toUpperCase()}\n`;
  content += `${'='.repeat(50)}\n`;
  content += `Agent: ${stage.agent}\n`;
  content += `Status: ${stage.status.toUpperCase()}\n`;
  if (stage.started_at_us) {
    content += `Started: ${formatTimestamp(stage.started_at_us, 'absolute')}\n`;
  }
  if (stage.duration_ms) {
    content += `Duration: ${formatDurationMs(stage.duration_ms)}\n`;
  }
  if (stage.error_message) {
    content += `Error: ${stage.error_message}\n`;
  }
  content += `Interactions: ${interactions.length}\n\n`;
  
  if (interactions.length > 0) {
    content += `--- INTERACTIONS ---\n\n`;
    interactions.forEach((interaction, index) => {
      content += `┌─── INTERACTION ${index + 1} ───────────────────────────────────────────\n`;
      content += `${formatInteractionForCopy(interaction)}`;
      content += `└─────────────────────────────────────────────────────────────\n\n`;
    });
  } else {
    content += `No interactions recorded for this stage.\n\n`;
  }
  
  return content;
};

// Stage status icons (string version for text formatting)
export const getStageStatusIcon = (status: string) => {
  switch (status) {
    case STAGE_STATUS.COMPLETED:
      return '✓';
    case STAGE_STATUS.FAILED:
    case STAGE_STATUS.TIMED_OUT:
      return '✗';
    case STAGE_STATUS.CANCELLED:
      return '⊘';
    case STAGE_STATUS.ACTIVE:
      return '🔧';
    default:
      return '⏸';
  }
};

// Interaction background colors (consistent across components)
export const getInteractionBackgroundColor = (type: string): string => {
  switch (type) {
    case 'llm':
      return '#f0f8ff';  // Light blue
    case 'mcp':
      return '#f5f0fa';  // Light purple
    case 'system':
      return '#fef9e7';  // Light yellow
    default:
      return '#f5f5f5';  // Light gray
  }
};
