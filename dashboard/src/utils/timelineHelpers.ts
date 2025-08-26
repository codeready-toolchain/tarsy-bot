import type { TimelineItem, LLMInteraction, MCPInteraction, StageExecution } from '../types';
import { formatTimestamp, formatDurationMs } from './timestamp';

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
      
      // EP-0010: Extract prompt from messages array
      const prompt = llmDetails.messages 
        ? llmDetails.messages.map((msg: any) => `${msg.role}: ${msg.content}`).join('\n')
        : 'N/A';
      content += `Prompt: ${prompt}\n`;
      
      // EP-0010: Extract response from assistant message
      const assistantMsg = llmDetails.messages?.find((m: any) => m?.role === 'assistant');
      const response = assistantMsg?.content || 'N/A';
      content += `Response: ${response}\n`;
      
      if (llmDetails.total_tokens) {
        content += `Tokens Used: ${llmDetails.total_tokens}\n`;
      }
    } else if (interaction.type === 'mcp') {
      const mcpDetails = interaction.details as MCPInteraction;
      content += `Server: ${mcpDetails.server_name || 'N/A'}\n`;
      content += `Tool: ${mcpDetails.tool_name || 'N/A'}\n`;
      content += `Success: ${mcpDetails.success}\n`;
      if (mcpDetails.parameters) {
        content += `Parameters: ${JSON.stringify(mcpDetails.parameters, null, 2)}\n`;
      }
      if (mcpDetails.result) {
        content += `Result: ${JSON.stringify(mcpDetails.result, null, 2)}\n`;
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
