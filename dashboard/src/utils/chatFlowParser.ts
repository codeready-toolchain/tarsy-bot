// Chat Flow Parser for Reasoning Tab
// Converts session data into a continuous chat-like flow with thoughts, tool calls, and final answers

import type { DetailedSession, StageExecution, LLMMessage, LLMInteractionDetail, MCPInteractionDetail } from '../types';

export interface ChatFlowItemData {
  type: 'thought' | 'tool_call' | 'final_answer' | 'stage_start';
  timestamp_us: number;
  content?: string; // For thought/final_answer
  stageName?: string; // For stage_start
  stageAgent?: string; // For stage_start
  toolName?: string; // For tool_call
  toolArguments?: any; // For tool_call
  toolResult?: any; // For tool_call
  serverName?: string; // For tool_call
  success?: boolean; // For tool_call
  errorMessage?: string; // For tool_call
  duration_ms?: number | null; // For tool_call
}

/**
 * Parse ReAct message content to extract structured components
 * Reused from conversationParser.ts
 */
function parseReActMessage(content: string): {
  thought?: string;
  action?: string;
  actionInput?: string;
  finalAnswer?: string;
} {
  const result: {
    thought?: string;
    action?: string;
    actionInput?: string;
    finalAnswer?: string;
  } = {};

  // Extract Thought
  const thoughtMatch = content.match(/(?:^|\n)\s*(?:Thought|THOUGHT):\s*(.*?)(?=\n\s*(?:Action|ACTION|Final Answer|FINAL ANSWER):|$)/s);
  if (thoughtMatch) {
    result.thought = thoughtMatch[1].trim();
  }

  // Extract Action
  const actionMatch = content.match(/(?:^|\n)\s*(?:Action|ACTION):\s*(.*?)(?=\n\s*(?:Action Input|ACTION INPUT|Thought|THOUGHT|Final Answer|FINAL ANSWER|Observation|OBSERVATION):|$)/s);
  if (actionMatch) {
    result.action = actionMatch[1].trim();
  }

  // Extract Action Input
  const actionInputMatch = content.match(/(?:^|\n)\s*(?:Action Input|ACTION INPUT):\s*(.*?)(?=\n\s*(?:Thought|THOUGHT|Action|ACTION|Final Answer|FINAL ANSWER|Observation|OBSERVATION):|$)/s);
  if (actionInputMatch) {
    result.actionInput = actionInputMatch[1].trim();
  }

  // Extract Final Answer
  const finalAnswerMatch = content.match(/(?:^|\n)\s*(?:Final Answer|FINAL ANSWER):\s*(.*?)$/s);
  if (finalAnswerMatch) {
    result.finalAnswer = finalAnswerMatch[1].trim();
  } else {
    // If no explicit "Final Answer:" is found, check if the entire content is an analysis
    const hasThoughtOrAction = content.match(/(?:^|\n)\s*(?:Thought|ACTION|Action):/i);
    if (!hasThoughtOrAction && content.trim().length > 50) {
      // Treat the entire content as final analysis if it doesn't contain ReAct elements
      result.finalAnswer = content.trim();
    }
  }

  return result;
}

/**
 * Get messages from conversation structure or fallback to legacy format
 */
function getMessages(interaction: LLMInteractionDetail): LLMMessage[] {
  // Try new conversation field first (EP-0014)
  if (interaction.details.conversation?.messages) {
    return interaction.details.conversation.messages;
  }
  // Fall back to legacy messages field
  if (interaction.details.messages) {
    return interaction.details.messages;
  }
  return [];
}

/**
 * Parse a session into a continuous chat flow
 */
export function parseSessionChatFlow(session: DetailedSession): ChatFlowItemData[] {
  const chatItems: ChatFlowItemData[] = [];

  // Process each stage in order
  for (const stage of session.stages || []) {
    // Add stage start marker
    chatItems.push({
      type: 'stage_start',
      timestamp_us: stage.started_at_us || Date.now() * 1000,
      stageName: stage.stage_name,
      stageAgent: stage.agent
    });

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

      // Extract based on interaction type
      if (interactionType === 'investigation' && parsed.thought) {
        chatItems.push({
          type: 'thought',
          timestamp_us: interaction.timestamp_us,
          content: parsed.thought
        });
      } else if (interactionType === 'final_analysis' && parsed.finalAnswer) {
        chatItems.push({
          type: 'final_answer',
          timestamp_us: interaction.timestamp_us,
          content: parsed.finalAnswer
        });
      }
    }

    // Process MCP communications (actual tool calls)
    const mcpCommunications = (stage.mcp_communications || [])
      .filter(mcp => mcp.details.communication_type === 'tool_call')
      .sort((a, b) => a.timestamp_us - b.timestamp_us);

    for (const mcp of mcpCommunications) {
      chatItems.push({
        type: 'tool_call',
        timestamp_us: mcp.timestamp_us,
        toolName: mcp.details.tool_name || 'unknown',
        toolArguments: mcp.details.tool_arguments || {},
        toolResult: mcp.details.tool_result || null,
        serverName: mcp.details.server_name,
        success: mcp.details.success !== false,
        errorMessage: mcp.details.error_message || undefined,
        duration_ms: mcp.duration_ms
      });
    }
  }

  // Sort all items chronologically
  chatItems.sort((a, b) => a.timestamp_us - b.timestamp_us);

  console.log(`📋 Parsed chat flow: ${chatItems.length} items from ${session.stages?.length || 0} stages`);
  console.log(`  - Thoughts: ${chatItems.filter(i => i.type === 'thought').length}`);
  console.log(`  - Tool calls: ${chatItems.filter(i => i.type === 'tool_call').length}`);
  console.log(`  - Final answers: ${chatItems.filter(i => i.type === 'final_answer').length}`);

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

