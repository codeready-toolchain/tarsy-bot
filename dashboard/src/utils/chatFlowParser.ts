// Chat Flow Parser for Reasoning Tab
// Converts session data into a continuous chat-like flow with thoughts, tool calls, and final answers

import type { DetailedSession } from '../types';
import { getMessages } from './conversationParser';
import { parseReActMessage } from './reactParser';
import { parseNativeToolsUsage } from './nativeToolsParser';
import type { NativeToolsUsage } from '../types';

export interface ChatFlowItemData {
  type: 'thought' | 'tool_call' | 'final_answer' | 'stage_start' | 'summarization' | 'user_message' | 'native_tool_usage';
  timestamp_us: number;
  stageId?: string; // Stage execution_id - used for grouping and collapse functionality
  content?: string; // For thought/final_answer/summarization/user_message
  stageName?: string; // For stage_start
  stageAgent?: string; // For stage_start
  toolName?: string; // For tool_call
  toolArguments?: any; // For tool_call
  toolResult?: any; // For tool_call
  serverName?: string; // For tool_call
  success?: boolean; // For tool_call
  errorMessage?: string; // For tool_call
  duration_ms?: number | null; // For tool_call
  mcp_event_id?: string; // For tool_call and summarization - used for deduplication
  // For user_message type
  author?: string; // User who sent the message
  messageId?: string; // Message identifier
  // For native_tool_usage type
  nativeToolsUsage?: NativeToolsUsage;
  llmInteractionId?: string; // Link to the LLM interaction
}


/**
 * Parse a session into a continuous chat flow
 */
export function parseSessionChatFlow(session: DetailedSession): ChatFlowItemData[] {
  const chatItems: ChatFlowItemData[] = [];

  // Process each stage in order
  for (const stage of session.stages || []) {
    const stageStartTimestamp = stage.started_at_us || Date.now() * 1000;
    const stageId = stage.execution_id;
    
    // Add stage start marker
    chatItems.push({
      type: 'stage_start',
      timestamp_us: stageStartTimestamp,
      stageId,
      stageName: stage.stage_name,
      stageAgent: stage.agent
    });

    // Add user message if this is a chat stage (Option 4: separate item with badge)
    // Ensure user message timestamp is at least equal to stage_start to keep it within the stage
    if (stage.chat_user_message) {
      const userMessageTimestamp = Math.max(
        stage.chat_user_message.created_at_us,
        stageStartTimestamp + 1 // +1 to ensure it appears after stage_start marker
      );
      
      chatItems.push({
        type: 'user_message',
        timestamp_us: userMessageTimestamp,
        stageId,
        content: stage.chat_user_message.content,
        author: stage.chat_user_message.author,
        messageId: stage.chat_user_message.message_id
      });
    }

    // Process LLM interactions
    const llmInteractions = (stage.llm_interactions || [])
      .sort((a, b) => a.timestamp_us - b.timestamp_us);

    for (const interaction of llmInteractions) {
      const messages = getMessages(interaction);
      const interactionType = interaction.details.interaction_type;

      // Get the last assistant message
      const assistantMessages = messages.filter(msg => msg.role === 'assistant');
      const lastAssistantMessage = assistantMessages[assistantMessages.length - 1];

      if (!lastAssistantMessage) continue;

      const parsed = parseReActMessage(lastAssistantMessage.content);

      // Track the last timestamp used for this interaction
      let lastTimestamp = interaction.timestamp_us;

      // Extract based on interaction type
      if (interactionType === 'investigation' && parsed.thought) {
        chatItems.push({
          type: 'thought',
          timestamp_us: interaction.timestamp_us,
          stageId,
          content: parsed.thought
        });
      } else if (interactionType === 'final_analysis') {
        // Final analysis may have both thought AND final answer - show both
        if (parsed.thought) {
          chatItems.push({
            type: 'thought',
            timestamp_us: interaction.timestamp_us,
            stageId,
            content: parsed.thought
          });
        }
        if (parsed.finalAnswer) {
          lastTimestamp = interaction.timestamp_us + 1;
          chatItems.push({
            type: 'final_answer',
            timestamp_us: lastTimestamp, // +1 to ensure it comes after thought
            stageId,
            content: parsed.finalAnswer
          });
        }
      } else if (interactionType === 'summarization') {
        // Summarization interactions have plain text in the last assistant message
        // Use the lastAssistantMessage already computed earlier (not messages[messages.length - 1])
        if (lastAssistantMessage && lastAssistantMessage.content) {
          chatItems.push({
            type: 'summarization',
            timestamp_us: interaction.timestamp_us,
            stageId,
            content: lastAssistantMessage.content,
            mcp_event_id: (interaction.details as any).mcp_event_id // Link to the tool call being summarized
          });
        }
      }

      // Check for native tools usage in this interaction
      const nativeToolsConfig = (interaction.details as any).native_tools_config;
      const responseMetadata = (interaction.details as any).response_metadata;
      
      if (nativeToolsConfig || responseMetadata) {
        const toolsUsage = parseNativeToolsUsage(
          responseMetadata,
          lastAssistantMessage.content
        );
        
        // Only add if tools were actually used (not just enabled)
        if (toolsUsage) {
          chatItems.push({
            type: 'native_tool_usage',
            timestamp_us: lastTimestamp + 2, // +2 to ensure it comes after other items
            stageId,
            nativeToolsUsage: toolsUsage,
            llmInteractionId: interaction.id
          });
        }
      }
    }

    // Process MCP communications (actual tool calls)
    const mcpCommunications = (stage.mcp_communications || [])
      .filter(mcp => mcp.details.communication_type === 'tool_call')
      .sort((a, b) => a.timestamp_us - b.timestamp_us);

    for (const mcp of mcpCommunications) {
      // API returns 'id' or 'event_id' (maps to communication_id in DB)
      const mcpEventId = mcp.event_id || mcp.id;
      
      chatItems.push({
        type: 'tool_call',
        timestamp_us: mcp.timestamp_us,
        stageId,
        toolName: mcp.details.tool_name || 'unknown',
        toolArguments: mcp.details.tool_arguments || {},
        toolResult: mcp.details.tool_result || null,
        serverName: mcp.details.server_name,
        success: mcp.details.success !== false,
        errorMessage: mcp.details.error_message || undefined,
        duration_ms: mcp.duration_ms,
        mcp_event_id: mcpEventId // For deduplication with streaming items
      });
    }
  }

  // Sort all items chronologically
  chatItems.sort((a, b) => a.timestamp_us - b.timestamp_us);

  // Parsed chat flow: ${chatItems.length} items from ${session.stages?.length || 0} stages

  return chatItems;
}

/**
 * Get statistics from chat flow
 */
export function getChatFlowStats(chatItems: ChatFlowItemData[]): {
  totalItems: number;
  thoughtsCount: number;
  toolCallsCount: number;
  finalAnswersCount: number;
  successfulToolCalls: number;
} {
  return {
    totalItems: chatItems.length,
    thoughtsCount: chatItems.filter(i => i.type === 'thought').length,
    toolCallsCount: chatItems.filter(i => i.type === 'tool_call').length,
    finalAnswersCount: chatItems.filter(i => i.type === 'final_answer').length,
    successfulToolCalls: chatItems.filter(i => i.type === 'tool_call' && i.success).length
  };
}

