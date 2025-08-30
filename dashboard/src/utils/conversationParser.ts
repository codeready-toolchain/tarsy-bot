// EP-0014 Conversation Parser
// Converts session data with EP-0014 conversation structures into clean conversation flow

import type { DetailedSession, StageExecution, LLMMessage, LLMInteractionDetail, LLMEventDetails } from '../types';

export interface ConversationStepData {
  type: 'thought' | 'action' | 'analysis' | 'summarization' | 'error';
  content: string;
  actionName?: string;
  actionInput?: string;
  actionResult?: any;
  timestamp_us: number;
  success?: boolean;
  errorMessage?: string;
}

export interface StageConversation {
  stage_name: string;
  agent: string;
  status: 'completed' | 'failed' | 'active' | 'pending';
  execution_id: string;
  steps: ConversationStepData[];
  duration_ms?: number;
  started_at_us?: number;
  completed_at_us?: number;
  errorMessage?: string;
  // Token usage aggregations
  stage_input_tokens?: number;
  stage_output_tokens?: number;
  stage_total_tokens?: number;
}

export interface ParsedSession {
  session_id: string;
  status: 'completed' | 'failed' | 'in_progress' | 'pending';
  stages: StageConversation[];
  finalAnalysis?: string;
  alert_type?: string;
  chain_id?: string;
}

/**
 * Check if an LLM interaction is a summarization interaction based on system message
 */
function isSummarizationInteraction(messages: LLMMessage[]): boolean {
  const systemMessage = messages.find(msg => msg.role === 'system');
  if (!systemMessage) return false;
  
  const content = systemMessage.content.toLowerCase();
  return content.includes('summarizing technical output') ||
         content.includes('your specific task is to summarize') ||
         content.includes('expert at summarizing technical output');
}

/**
 * Parse ReAct message content to extract structured components
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
    // This handles cases where the assistant provides direct analysis without ReAct format
    const hasThoughtOrAction = content.match(/(?:^|\n)\s*(?:Thought|ACTION|Action):/i);
    if (!hasThoughtOrAction && content.trim().length > 50) {
      // Treat the entire content as final analysis if it doesn't contain ReAct elements
      result.finalAnswer = content.trim();
    }
  }

  return result;
}

/**
 * Union type for objects that may contain conversation/messages data
 * Can be either a full LLMInteractionDetail or just the details (LLMEventDetails)
 * or any partial object with optional conversation/messages fields
 */
type InteractionLike = 
  | LLMInteractionDetail 
  | LLMEventDetails 
  | { 
      details?: { conversation?: { messages?: LLMMessage[] }; messages?: LLMMessage[] }; 
      conversation?: { messages?: LLMMessage[] }; 
      messages?: LLMMessage[];
    }
  | null 
  | undefined;

/**
 * Get messages from EP-0014 conversation structure or fallback to legacy format
 * Safely handles both full interactions and interaction details with null/undefined guards
 */
export function getMessages(interactionOrDetails: InteractionLike): LLMMessage[] {
  // Handle null/undefined input
  if (!interactionOrDetails) {
    return [];
  }

  // Type guard for objects with details property (LLMInteractionDetail or similar)
  if ('details' in interactionOrDetails && interactionOrDetails.details) {
    // Try details.conversation.messages first (EP-0014)
    if (interactionOrDetails.details.conversation?.messages) {
      return interactionOrDetails.details.conversation.messages;
    }
    // Fall back to details.messages (legacy)
    if (interactionOrDetails.details.messages) {
      return interactionOrDetails.details.messages;
    }
  }

  // Type guard for objects with conversation property (LLMEventDetails or similar)
  if ('conversation' in interactionOrDetails && interactionOrDetails.conversation?.messages) {
    return interactionOrDetails.conversation.messages;
  }

  // Type guard for objects with messages property (LLMEventDetails legacy or similar)
  if ('messages' in interactionOrDetails && interactionOrDetails.messages) {
    return interactionOrDetails.messages;
  }

  // Default fallback
  return [];
}

/**
 * Find corresponding MCP result for an action
 */
function findMCPResult(
  stage: StageExecution,
  actionName: string,
  afterTimestamp: number
): { result: any; success: boolean } | null {
  const mcpCommunications = stage.mcp_communications || [];
  const [serverPart, toolPart] = actionName.includes('.')
    ? actionName.split('.', 2)
    : [undefined, actionName];
  const windowEnd = afterTimestamp + 30_000_000; // 30s

  const candidates = mcpCommunications.filter((mcp: any) => {
    const d = mcp.details ?? mcp;
    const ts = mcp.timestamp_us ?? d.timestamp_us;
    const typeIsToolCall = (d.communication_type ?? mcp.communication_type) === 'tool_call';
    const toolMatches = (d.tool_name ?? mcp.tool_name) === toolPart;
    const serverMatches =
      serverPart ? (d.server_name ?? mcp.server_name) === serverPart : true;
    const timeMatches = ts >= afterTimestamp && ts <= windowEnd;
    return typeIsToolCall && toolMatches && serverMatches && timeMatches;
  });

  if (candidates.length === 0) return null;
  candidates.sort((a: any, b: any) => (a.timestamp_us ?? 0) - (b.timestamp_us ?? 0));
  const match: any = candidates[0];
  const details = match.details ?? match;
  const success = details.success !== false;
  const result =
    details.result ??
    details.tool_result ??
    details.available_tools ??
    (success ? 'Action completed successfully' : null);
  return { result, success };
}

/**
 * Normalize content for comparison by removing extra whitespace and common variations
 */
function normalizeContentForComparison(content: string): string {
  return content
    .toLowerCase()
    .replace(/\s+/g, ' ') // Replace multiple whitespace with single space
    .replace(/[^\w\s]/g, '') // Remove punctuation
    .trim();
}

/**
 * Check if two steps are essentially the same content
 */
function areStepsSimilar(step1: ConversationStepData, step2: ConversationStepData): boolean {
  // Must be the same type
  if (step1.type !== step2.type) {
    return false;
  }
  
  // Compare normalized content
  const content1 = normalizeContentForComparison(step1.content);
  const content2 = normalizeContentForComparison(step2.content);
  
  // For actions, prioritize comparing action name and input over content
  if (step1.type === 'action' && step2.type === 'action') {
    const action1 = normalizeContentForComparison(step1.actionName || '');
    const action2 = normalizeContentForComparison(step2.actionName || '');
    const input1 = normalizeContentForComparison(step1.actionInput || '');
    const input2 = normalizeContentForComparison(step2.actionInput || '');
    
    // If actions and inputs are the same, it's a duplicate regardless of thought content
    if (action1 === action2 && input1 === input2) {
      return true;
    }
  }
  
  // For exact content matches
  if (content1 === content2) {
    return true;
  }
  
  // For longer content, check if they're substantially similar
  if (content1.length > 30 && content2.length > 30) {
    const shorter = content1.length < content2.length ? content1 : content2;
    const longer = content1.length >= content2.length ? content1 : content2;
    
    // If the shorter content is substantially contained in the longer one
    if (longer.includes(shorter) && shorter.length / longer.length > 0.8) {
      return true;
    }
    
    // Check for word-level similarity for thoughts that might have small variations
    const words1 = shorter.split(' ');
    const words2 = longer.split(' ');
    const commonWords = words1.filter(word => word.length > 3 && words2.includes(word));
    
    // If more than 80% of words from shorter content appear in longer content
    if (commonWords.length / words1.length > 0.8) {
      return true;
    }
  }
  
  return false;
}



/**
 * Parse a single stage execution into conversation format with intra-stage deduplication
 */
export function parseStageConversation(stage: StageExecution): StageConversation {
  const steps: ConversationStepData[] = [];
  let stageSeenSteps: ConversationStepData[] = []; // Track steps seen within THIS stage only
  
  // Process LLM interactions in chronological order
  const sortedInteractions = (stage.llm_interactions || [])
    .sort((a, b) => a.timestamp_us - b.timestamp_us);
    
  for (const interaction of sortedInteractions) {
    const timestamp = interaction.timestamp_us;
    
    // Handle failed LLM interactions
    if (interaction.details?.success === false) {
      const errorStep: ConversationStepData = {
        type: 'error',
        content: 'LLM request failed with error',
        timestamp_us: timestamp,
        success: false,
        errorMessage: interaction.details.error_message ?? undefined
      };
      steps.push(errorStep);
      stageSeenSteps.push(errorStep);
      continue;
    }

    const messages = getMessages(interaction.details ?? interaction);
    
    // Process assistant messages (thoughts, actions, analysis) 
    // Each interaction contains the FULL conversation history, so we need to extract only NEW content
    const assistantMessages = messages.filter(msg => msg.role === 'assistant');
    
    // Check if this is a summarization interaction
    const isSummarization = isSummarizationInteraction(messages);
    
    if (isSummarization) {
      // For summarization interactions, only process the last assistant message
      const lastAssistantMessage = assistantMessages[assistantMessages.length - 1];
      if (lastAssistantMessage) {
        const candidateSteps: ConversationStepData[] = [];
        
        // Create summarization step from the last assistant message
        candidateSteps.push({
          type: 'summarization',
          content: lastAssistantMessage.content,
          timestamp_us: timestamp,
          success: true
        });
        console.log(`📝 Found summarization content in stage "${stage.stage_name}" (last message): ${lastAssistantMessage.content.length} characters`);
        
        // Only add steps that are truly new (not seen before in any previous interaction within this stage)
        for (const candidateStep of candidateSteps) {
          const isDuplicate = stageSeenSteps.some(seenStep => 
            areStepsSimilar(candidateStep, seenStep)
          );
          
          if (!isDuplicate) {
            steps.push(candidateStep);
            stageSeenSteps.push(candidateStep);
          }
        }
      }
    } else {
      // Regular ReAct interactions - process all assistant messages
      for (const message of assistantMessages) {
        const candidateSteps: ConversationStepData[] = [];
        
        // Regular ReAct interaction - parse for thoughts, actions, analysis
        const parsed = parseReActMessage(message.content);
        
        // Debug logging for parsing (only for analysis steps)
        if (parsed.finalAnswer) {
          console.log(`🔍 Found analysis content in stage "${stage.stage_name}": ${parsed.finalAnswer.length} characters`);
        }
        
        // Build candidate steps from this message
        if (parsed.thought) {
          candidateSteps.push({
            type: 'thought',
            content: parsed.thought,
            timestamp_us: timestamp,
            success: true
          });
        }
        
        if (parsed.action) {
          const mcpResult = findMCPResult(stage, parsed.action, timestamp);
          candidateSteps.push({
            type: 'action',
            content: `${parsed.action}${parsed.actionInput ? ` ${parsed.actionInput}` : ''}`,
            actionName: parsed.action,
            actionInput: parsed.actionInput || '',
            actionResult: mcpResult?.result || null,
            timestamp_us: timestamp,
            success: mcpResult?.success ?? true
          });
        }
        
        if (parsed.finalAnswer) {
          candidateSteps.push({
            type: 'analysis',
            content: parsed.finalAnswer,
            timestamp_us: timestamp,
            success: true
          });
        }
        
        // Only add steps that are truly new (not seen before in any previous interaction within this stage)
        for (const candidateStep of candidateSteps) {
          const isDuplicate = stageSeenSteps.some(seenStep => 
            areStepsSimilar(candidateStep, seenStep)
          );
          
          if (!isDuplicate) {
            steps.push(candidateStep);
            stageSeenSteps.push(candidateStep);
          }
        }
      }
    }
  }

  // If no steps were found, create a placeholder
  if (steps.length === 0 && stage.status === 'active') {
    steps.push({
      type: 'thought',
      content: 'Stage is starting...',
      timestamp_us: stage.started_at_us || Date.now() * 1000,
      success: true
    });
  }

  console.log(`📋 Stage "${stage.stage_name}": Processed ${sortedInteractions.length} LLM interactions, extracted ${steps.length} unique steps (intra-stage deduplication)`);

  return {
    stage_name: stage.stage_name,
    agent: stage.agent,
    status: stage.status,
    execution_id: stage.execution_id,
    steps,
    duration_ms: stage.duration_ms ?? undefined,
    started_at_us: stage.started_at_us ?? undefined,
    completed_at_us: stage.completed_at_us ?? undefined,
    errorMessage: stage.error_message ?? undefined,
    // Token usage aggregations
    stage_input_tokens: stage.stage_input_tokens ?? undefined,
    stage_output_tokens: stage.stage_output_tokens ?? undefined,
    stage_total_tokens: stage.stage_total_tokens ?? undefined
  };
}

/**
 * Parse entire session into conversation format (stages are independent)
 */
export function parseSessionConversation(session: DetailedSession): ParsedSession {
  // Process each stage independently - no deduplication between stages
  const stages = (session.stages || []).map(stageExecution => 
    parseStageConversation(stageExecution)
  );
  
  return {
    session_id: session.session_id,
    status: session.status as ParsedSession['status'],
    stages,
    finalAnalysis: session.final_analysis || undefined,
    alert_type: session.alert_type || undefined,
    chain_id: session.chain_id || undefined
  };
}

/**
 * Get conversation summary statistics
 */
export function getConversationStats(parsedSession: ParsedSession): {
  totalSteps: number;
  thoughtsCount: number;
  actionsCount: number;
  analysisCount: number;
  errorsCount: number;
  successfulActions: number;
} {
  let totalSteps = 0;
  let thoughtsCount = 0;
  let actionsCount = 0;
  let analysisCount = 0;
  let errorsCount = 0;
  let successfulActions = 0;

  for (const stage of parsedSession.stages) {
    totalSteps += stage.steps.length;
    
    for (const step of stage.steps) {
      switch (step.type) {
        case 'thought':
          thoughtsCount++;
          break;
        case 'action':
          actionsCount++;
          if (step.success) {
            successfulActions++;
          }
          break;
        case 'analysis':
          analysisCount++;
          break;
        case 'error':
          errorsCount++;
          break;
      }
    }
  }

  return {
    totalSteps,
    thoughtsCount,
    actionsCount,
    analysisCount,
    errorsCount,
    successfulActions
  };
}
