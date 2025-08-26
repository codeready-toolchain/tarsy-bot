import type { TimelineItem, LLMInteraction, MCPInteraction, StageExecution } from '../types';
import { formatTimestamp, formatDurationMs } from './timestamp';
import { getMessages } from './conversationParser';

/**
 * Shared helper functions for timeline components
 * Extracted to reduce duplication between NestedAccordionTimeline and VirtualizedAccordionTimeline
 */

// Stage status color mapping
export const getStageStatusColor = (status: string): 'success' | 'error' | 'primary' | 'warning' | 'default' => {
  switch (status) {
    case 'completed':
      return 'success';
    case 'failed':
      return 'error';
    case 'active':
      return 'primary';
    case 'pending':
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
    if (interaction.type === 'llm') {
      const llmDetails = interaction.details as LLMInteraction;
      content += `Model: ${llmDetails.model_name || 'N/A'}\n`;
      
      // EP-0014: Use getMessages helper to extract conversation messages properly
      const messages = getMessages(llmDetails);
      
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
      if (llmDetails.success === false) {
        content += `ERROR: ${llmDetails.error_message || 'LLM request failed - no response received'}\n`;
      }
      
      if (llmDetails.total_tokens) {
        content += `Tokens Used: ${llmDetails.total_tokens}\n`;
      }
      if (llmDetails.temperature !== undefined) {
        content += `Temperature: ${llmDetails.temperature}\n`;
      }
    } else if (interaction.type === 'mcp') {
      const mcpDetails = interaction.details as MCPInteraction;
      content += `Server: ${mcpDetails.server_name || 'N/A'}\n`;
      content += `Communication Type: ${mcpDetails.communication_type || 'N/A'}\n`;
      content += `Success: ${mcpDetails.success}\n`;
      
      if (isToolList(mcpDetails)) {
        // For tool list operations, show available tools instead of parameters/result
        content += `Tool: list_tools\n`;
        if (mcpDetails.available_tools) {
          content += `\n--- AVAILABLE TOOLS ---\n`;
          content += `${JSON.stringify(mcpDetails.available_tools, null, 2)}\n`;
        } else {
          content += `Available Tools: None listed\n`;
        }
      } else {
        // For regular tool calls, show tool name, parameters, and result
        content += `Tool: ${mcpDetails.tool_name || 'N/A'}\n`;
        
        if (mcpDetails.parameters && Object.keys(mcpDetails.parameters).length > 0) {
          content += `\n--- PARAMETERS ---\n`;
          content += `${JSON.stringify(mcpDetails.parameters, null, 2)}\n`;
        } else {
          content += `Parameters: None\n`;
        }
        
        if (mcpDetails.result && Object.keys(mcpDetails.result).length > 0) {
          content += `\n--- RESULT ---\n`;
          content += `${JSON.stringify(mcpDetails.result, null, 2)}\n`;
        } else {
          content += `Result: ${mcpDetails.success ? 'Success (no data)' : 'Failed'}\n`;
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
    case 'completed':
      return '✓';
    case 'failed':
      return '✗';
    case 'active':
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
