/**
 * Shared ReAct message parsing utilities
 * 
 * This module provides common parsing logic for extracting structured components
 * (Thought, Action, Action Input, Final Answer) from ReAct-formatted messages.
 * 
 * Used by:
 * - conversationParser.ts - Stage timeline parsing
 * - chatFlowParser.ts - Chat flow display
 * - LLMInteractionPreview.tsx - Preview cards
 */

export interface ParsedReActMessage {
  thought?: string;
  action?: string;
  actionInput?: string;
  finalAnswer?: string;
}

/**
 * Parse ReAct message content to extract structured components
 * 
 * Handles both standard format (with colons) and malformed format (without colons):
 * - Standard: "Thought: content here"
 * - Malformed: "Thought\ncontent here" (LLM sometimes forgets the colon)
 * 
 * @param content - The message content to parse
 * @returns Parsed components with optional thought, action, actionInput, and finalAnswer
 */
export function parseReActMessage(content: string): ParsedReActMessage {
  const result: ParsedReActMessage = {};

  // Extract Thought - handles both "Thought:" (with colon) and "Thought" (without colon, malformed)
  // Try standard format with colon first
  let thoughtMatch = content.match(/(?:^|\n)\s*(?:Thought|THOUGHT):\s*(.*?)(?=\n\s*(?:Action|ACTION|Final Answer|FINAL ANSWER):|$)/s);
  if (thoughtMatch) {
    let thought = thoughtMatch[1].trim();
    
    // Handle cases where LLM doesn't put "Final Answer:" or "Action:" on new lines
    // Strip them from the end of thought content
    if (thought.includes('Final Answer:')) {
      thought = thought.substring(0, thought.indexOf('Final Answer:')).trim();
    } else if (thought.includes('Action:')) {
      thought = thought.substring(0, thought.indexOf('Action:')).trim();
    }
    
    result.thought = thought;
  } else {
    // Try malformed format: "Thought" on its own line without colon
    thoughtMatch = content.match(/(?:^|\n)\s*(?:Thought|THOUGHT)\s*\n(.*?)(?=\n\s*(?:Action|ACTION|Final Answer|FINAL ANSWER):|$)/s);
    if (thoughtMatch) {
      result.thought = thoughtMatch[1].trim();
    }
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
 * Simple imperative-style parser for extracting thought and action
 * Used primarily for preview displays where we need basic extraction
 * 
 * @param responseText - The response text to parse
 * @returns Object with thought and action strings
 */
export function parseThoughtAndAction(responseText: string): { thought: string; action: string } {
  let thought = '';
  let action = '';
  
  // Find Thought section at line start only - handles both "Thought:" and "Thought" (malformed)
  let thoughtMatch = responseText.match(/^\s*(?:Thought|THOUGHT):/m);
  if (thoughtMatch) {
    const thoughtIndex = thoughtMatch.index!;
    // Find the start of content after "Thought:"
    const thoughtStart = responseText.indexOf(':', thoughtIndex) + 1;
    
    // Find where Action starts (or end of text) using anchored regex
    const actionMatch = responseText.substring(thoughtStart).match(/^\s*(?:Action|ACTION):/m);
    const thoughtEnd = actionMatch 
      ? thoughtStart + actionMatch.index! 
      : responseText.length;
    
    // Extract and clean thought content
    thought = responseText.substring(thoughtStart, thoughtEnd).trim();
  } else {
    // Try malformed format: "Thought" on its own line without colon
    thoughtMatch = responseText.match(/^\s*(?:Thought|THOUGHT)\s*$/m);
    if (thoughtMatch) {
      const thoughtIndex = thoughtMatch.index!;
      // Find the start of content (next line after "Thought")
      const thoughtStart = thoughtIndex + thoughtMatch[0].length;
      
      // Find where Action starts (or end of text)
      const actionMatch = responseText.substring(thoughtStart).match(/^\s*(?:Action|ACTION):/m);
      const thoughtEnd = actionMatch 
        ? thoughtStart + actionMatch.index! 
        : responseText.length;
      
      // Extract and clean thought content
      thought = responseText.substring(thoughtStart, thoughtEnd).trim();
    }
  }
  
  // Find Action section at line start only
  const actionMatch = responseText.match(/^\s*(?:Action|ACTION):/m);
  if (actionMatch) {
    const actionIndex = actionMatch.index!;
    // Find the start of content after "Action:"
    const actionStart = responseText.indexOf(':', actionIndex) + 1;
    
    // Find where next section starts (or end of text) using anchored regex
    const nextSectionMatch = responseText.substring(actionStart).match(/^\s*(?:Thought|THOUGHT|Observation|OBSERVATION|Final Answer|FINAL ANSWER):/m);
    const actionEnd = nextSectionMatch 
      ? actionStart + nextSectionMatch.index! 
      : responseText.length;
    
    // Extract and clean action content
    action = responseText.substring(actionStart, actionEnd).trim();
  }
  
  // If no explicit Thought/Action format, try to extract structured content
  if (!thought && !action) {
    // Look for tool calls or structured responses
    if (responseText.includes('```json') || responseText.includes('"tool_name"')) {
      action = responseText;
    } else {
      thought = responseText;
    }
  }

  return { thought, action };
}

