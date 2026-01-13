// Chat Flow Parser for Reasoning Tab
// Converts session data into a continuous chat-like flow with thoughts, tool calls, and final answers

import type { DetailedSession } from '../types';
import { getMessages } from './conversationParser';
import { parseReActMessage } from './reactParser';
import { parseNativeToolsUsage } from './nativeToolsParser';
import type { NativeToolsUsage } from '../types';
import { LLM_INTERACTION_TYPES } from '../constants/llmInteractionTypes';
import { CHAT_FLOW_ITEM_TYPES, type ChatFlowItemType } from '../constants/chatFlowItemTypes';
import { isNativeThinkingStrategy } from '../constants/iterationStrategies';

export interface ChatFlowItemData {
  type: ChatFlowItemType;
  timestamp_us: number;
  stageId?: string; // Stage execution_id - used for grouping and collapse functionality
  executionId?: string; // For parallel stages - identifies which parallel execution this item belongs to
  executionAgent?: string; // For parallel stages - the agent name for this execution
  isParallelStage?: boolean; // Indicates if this item is part of a parallel stage
  isChatStage?: boolean; // Indicates if this item is from a chat/follow-up stage
  content?: string; // For thought/final_answer/summarization/user_message/intermediate_response
  stageName?: string; // For stage_start
  stageAgent?: string; // For stage_start
  stageStatus?: string; // For stage_start - stage status ('pending'|'active'|'completed'|'failed')
  stageErrorMessage?: string; // For stage_start - error message if stage failed
  toolName?: string; // For tool_call
  toolArguments?: any; // For tool_call
  toolResult?: any; // For tool_call
  serverName?: string; // For tool_call
  success?: boolean; // For tool_call
  errorMessage?: string; // For tool_call
  duration_ms?: number | null; // For tool_call
  interaction_duration_ms?: number | null; // For thought/native_thinking/intermediate_response/final_answer (LLM interaction duration)
  mcp_event_id?: string; // For tool_call and summarization - used for deduplication
  // For user_message type
  author?: string; // User who sent the message
  messageId?: string; // Message identifier
  // For native_tool_usage type
  nativeToolsUsage?: NativeToolsUsage;
  // LLM interaction ID for deduplication of thought/final_answer/native_thinking/intermediate_response
  llm_interaction_id?: string;
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
    
    // Determine if this is a chat stage (has user message = follow-up chat)
    const isChatStage = !!stage.chat_user_message;
    
    // Add stage start marker (with status and error message for failed stages)
    chatItems.push({
      type: CHAT_FLOW_ITEM_TYPES.STAGE_START,
      timestamp_us: stageStartTimestamp,
      stageId,
      stageName: stage.stage_name,
      stageAgent: stage.agent,
      stageStatus: stage.status,
      stageErrorMessage: stage.error_message || undefined,
      isChatStage
    });

    // Add user message if this is a chat stage (Option 4: separate item with badge)
    // Ensure user message timestamp is at least equal to stage_start to keep it within the stage
    if (stage.chat_user_message) {
      const createdAtUs = stage.chat_user_message.created_at_us ?? stageStartTimestamp + 1;
      const userMessageTimestamp = Math.max(
        createdAtUs,
        stageStartTimestamp + 1 // +1 to ensure it appears after stage_start marker
      );
      
      chatItems.push({
        type: CHAT_FLOW_ITEM_TYPES.USER_MESSAGE,
        timestamp_us: userMessageTimestamp,
        stageId,
        content: stage.chat_user_message.content,
        author: stage.chat_user_message.author,
        messageId: stage.chat_user_message.message_id,
        isChatStage
      });
    }

    // Check if this is a parallel stage (has parallel_executions)
    const isParallelStage = stage.parallel_executions && stage.parallel_executions.length > 0;
    const executionsToProcess = isParallelStage
      ? (stage.parallel_executions || []) // Process parallel executions
      : [stage]; // Process the stage itself as a single execution

    // Process each execution (either parallel executions or the stage itself)
    for (const execution of executionsToProcess) {
      const executionId = execution.execution_id;
      const executionAgent = execution.agent;
      // Get the iteration strategy to distinguish native thinking from ReAct
      const iterationStrategy = (execution as any).iteration_strategy;
      const isNativeThinking = isNativeThinkingStrategy(iterationStrategy);
      
    // Process LLM interactions
      const llmInteractions = (execution.llm_interactions || [])
      .sort((a, b) => a.timestamp_us - b.timestamp_us);

    // Track previous interaction's assistant messages to detect inherited messages
    let previousAssistantMessageContents = new Set<string>();

    for (const interaction of llmInteractions) {
      const messages = getMessages(interaction);
      const interactionType = interaction.details.interaction_type;

      // Get the last assistant message
      const assistantMessages = messages.filter(msg => msg.role === 'assistant');
      const lastAssistantMessage = assistantMessages[assistantMessages.length - 1];

      // Track the last timestamp used for this interaction
      let lastTimestamp = interaction.timestamp_us;

      // Check for native thinking content (Gemini 3.0+ native thinking mode)
      // This is separate from ReAct thoughts - it's the model's internal reasoning
      const thinkingContent = (interaction.details as any).thinking_content;
      if (thinkingContent) {
        chatItems.push({
          type: CHAT_FLOW_ITEM_TYPES.NATIVE_THINKING,
          timestamp_us: lastTimestamp,
          stageId,
            executionId,
            executionAgent,
            isParallelStage,
            isChatStage,
          content: thinkingContent,
          interaction_duration_ms: interaction.duration_ms ?? null,
          llm_interaction_id: interaction.id || interaction.event_id // For deduplication
        });
        lastTimestamp = lastTimestamp + 1; // Ensure subsequent items come after
      }

      if (!lastAssistantMessage) continue;

      const parsed = parseReActMessage(lastAssistantMessage.content);

      // Extract based on interaction type
      // Include llm_interaction_id for deduplication with streaming events
      const llmInteractionId = interaction.id || interaction.event_id;
      
      if (interactionType === LLM_INTERACTION_TYPES.INVESTIGATION && parsed.thought) {
        chatItems.push({
          type: CHAT_FLOW_ITEM_TYPES.THOUGHT,
          timestamp_us: interaction.timestamp_us,
          stageId,
            executionId,
            executionAgent,
            isParallelStage,
            isChatStage,
          content: parsed.thought,
          interaction_duration_ms: interaction.duration_ms ?? null,
          llm_interaction_id: llmInteractionId
        });
      } else if (interactionType === LLM_INTERACTION_TYPES.INVESTIGATION && isNativeThinking) {
        // For native thinking investigation iterations, extract intermediate response from the last assistant message
        // IF it's new to this interaction (not inherited from previous iteration)
        // Note: thinking_content may be null in some iterations (empty thinking, only tool calls)
        if (lastAssistantMessage && lastAssistantMessage.content) {
          // Check if this assistant message existed in the previous interaction
          // If it did, it's inherited and we shouldn't extract it again
          const isInheritedMessage = previousAssistantMessageContents.has(lastAssistantMessage.content);
          
          if (!isInheritedMessage) {
            // This is a NEW assistant message in this iteration - extract it
            const itemTimestamp = thinkingContent ? lastTimestamp : interaction.timestamp_us;
            chatItems.push({
              type: CHAT_FLOW_ITEM_TYPES.INTERMEDIATE_RESPONSE,
              timestamp_us: itemTimestamp,
              stageId,
                executionId,
                executionAgent,
                isParallelStage,
                isChatStage,
              content: lastAssistantMessage.content,
              interaction_duration_ms: interaction.duration_ms ?? null,
              llm_interaction_id: llmInteractionId
            });
            if (thinkingContent) {
              lastTimestamp = lastTimestamp + 1; // Ensure subsequent items come after
            }
          }
        }
      } else if (interactionType === LLM_INTERACTION_TYPES.FINAL_ANALYSIS) {
        // Final analysis may have both thought AND final answer - show both
        if (parsed.thought) {
          chatItems.push({
            type: CHAT_FLOW_ITEM_TYPES.THOUGHT,
            timestamp_us: interaction.timestamp_us,
            stageId,
              executionId,
              executionAgent,
              isParallelStage,
              isChatStage,
            content: parsed.thought,
            interaction_duration_ms: interaction.duration_ms ?? null,
            llm_interaction_id: llmInteractionId
          });
        }
        if (parsed.finalAnswer) {
          lastTimestamp = interaction.timestamp_us + 1;
          chatItems.push({
            type: CHAT_FLOW_ITEM_TYPES.FINAL_ANSWER,
            timestamp_us: lastTimestamp, // +1 to ensure it comes after thought
            stageId,
              executionId,
              executionAgent,
              isParallelStage,
              isChatStage,
            content: parsed.finalAnswer,
            interaction_duration_ms: interaction.duration_ms ?? null,
            llm_interaction_id: llmInteractionId
          });
        }
      } else if (interactionType === LLM_INTERACTION_TYPES.FORCED_CONCLUSION) {
        // Forced conclusion at max iterations - similar to final analysis but marked differently
        if (parsed.thought) {
          chatItems.push({
            type: CHAT_FLOW_ITEM_TYPES.THOUGHT,
            timestamp_us: interaction.timestamp_us,
            stageId,
            executionId,
            executionAgent,
            isParallelStage,
            isChatStage,
            content: parsed.thought,
            interaction_duration_ms: interaction.duration_ms ?? null,
            llm_interaction_id: llmInteractionId
          });
        }
        if (parsed.finalAnswer) {
          lastTimestamp = interaction.timestamp_us + 1;
          chatItems.push({
            type: CHAT_FLOW_ITEM_TYPES.FORCED_CONCLUSION,  // Different type for visual distinction
            timestamp_us: lastTimestamp,
            stageId,
            executionId,
            executionAgent,
            isParallelStage,
            isChatStage,
            content: parsed.finalAnswer,
            interaction_duration_ms: interaction.duration_ms ?? null,
            llm_interaction_id: llmInteractionId
          });
        }
      } else if (interactionType === LLM_INTERACTION_TYPES.SUMMARIZATION) {
        // Summarization interactions have plain text in the last assistant message
        // Use the lastAssistantMessage already computed earlier (not messages[messages.length - 1])
        if (lastAssistantMessage && lastAssistantMessage.content) {
          chatItems.push({
            type: CHAT_FLOW_ITEM_TYPES.SUMMARIZATION,
            timestamp_us: interaction.timestamp_us,
            stageId,
              executionId,
              executionAgent,
              isParallelStage,
              isChatStage,
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
            type: CHAT_FLOW_ITEM_TYPES.NATIVE_TOOL_USAGE,
            timestamp_us: lastTimestamp + 2, // +2 to ensure it comes after other items
            stageId,
              executionId,
              executionAgent,
              isParallelStage,
              isChatStage,
            nativeToolsUsage: toolsUsage,
            llm_interaction_id: llmInteractionId
          });
        }
      }
      
      // Update the set of assistant message contents for the next iteration
      // This allows us to detect inherited messages in subsequent interactions
      previousAssistantMessageContents = new Set(
        assistantMessages.map(msg => msg.content)
      );
    }

    // Process MCP communications (actual tool calls)
      const mcpCommunications = (execution.mcp_communications || [])
      .filter(mcp => mcp.details.communication_type === 'tool_call')
      .sort((a, b) => a.timestamp_us - b.timestamp_us);

    for (const mcp of mcpCommunications) {
      // API returns 'id' or 'event_id' (maps to communication_id in DB)
      const mcpEventId = mcp.event_id || mcp.id;
      
      chatItems.push({
        type: CHAT_FLOW_ITEM_TYPES.TOOL_CALL,
        timestamp_us: mcp.timestamp_us,
        stageId,
          executionId,
          executionAgent,
          isParallelStage,
          isChatStage,
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
  forcedConclusionsCount: number;
  successfulToolCalls: number;
  nativeThinkingCount: number;
  intermediateResponsesCount: number;
} {
  return {
    totalItems: chatItems.length,
    thoughtsCount: chatItems.filter(i => i.type === CHAT_FLOW_ITEM_TYPES.THOUGHT).length,
    toolCallsCount: chatItems.filter(i => i.type === CHAT_FLOW_ITEM_TYPES.TOOL_CALL).length,
    finalAnswersCount: chatItems.filter(i => i.type === CHAT_FLOW_ITEM_TYPES.FINAL_ANSWER).length,
    forcedConclusionsCount: chatItems.filter(i => i.type === CHAT_FLOW_ITEM_TYPES.FORCED_CONCLUSION).length,
    successfulToolCalls: chatItems.filter(i => i.type === CHAT_FLOW_ITEM_TYPES.TOOL_CALL && i.success).length,
    nativeThinkingCount: chatItems.filter(i => i.type === CHAT_FLOW_ITEM_TYPES.NATIVE_THINKING).length,
    intermediateResponsesCount: chatItems.filter(i => i.type === CHAT_FLOW_ITEM_TYPES.INTERMEDIATE_RESPONSE).length
  };
}

