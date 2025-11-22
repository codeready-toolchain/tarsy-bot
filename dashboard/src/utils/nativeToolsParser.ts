/**
 * Native Tools Parser
 * 
 * Extracts structured tool usage information from Google AI response_metadata.
 * Parses Google Search, URL Context, and Code Execution usage.
 */

import type { 
  NativeToolsUsage, 
  GoogleSearchUsage, 
  URLContextUsage, 
  CodeExecutionUsage,
  CodeBlock,
  OutputBlock
} from '../types';

/**
 * Main parser function to extract native tools usage from response metadata and content
 * 
 * @param responseMetadata - Response metadata from LLM interaction
 * @param responseContent - Response content (for code execution detection)
 * @returns Structured tool usage summary, or null if no tools were used
 */
export function parseNativeToolsUsage(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  responseMetadata: Record<string, any> | null | undefined,
  responseContent: string | null | undefined
): NativeToolsUsage | null {
  if (!responseMetadata && !responseContent) {
    return null;
  }

  const toolUsage: NativeToolsUsage = {};
  let hasAnyUsage = false;

  // Parse Google Search usage
  if (responseMetadata) {
    const googleSearch = parseGoogleSearch(responseMetadata);
    if (googleSearch) {
      toolUsage.google_search = googleSearch;
      hasAnyUsage = true;
    }

    // Parse URL Context usage
    const urlContext = parseURLContext(responseMetadata);
    if (urlContext) {
      toolUsage.url_context = urlContext;
      hasAnyUsage = true;
    }
  }

  // Parse Code Execution usage from both metadata (structured parts) and content (markdown)
  const codeExecution = parseCodeExecution(responseContent || '', responseMetadata || undefined);
  if (codeExecution) {
    toolUsage.code_execution = codeExecution;
    hasAnyUsage = true;
  }

  return hasAnyUsage ? toolUsage : null;
}

/**
 * Parse Google Search usage from grounding metadata
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function parseGoogleSearch(metadata: Record<string, any>): GoogleSearchUsage | null {
  const grounding = metadata?.grounding_metadata;
  if (!grounding) {
    return null;
  }

  const searchQueries = grounding.web_search_queries;
  if (!searchQueries || !Array.isArray(searchQueries) || searchQueries.length === 0) {
    return null;
  }

  return {
    queries: searchQueries,
    query_count: searchQueries.length,
    search_entry_point: grounding.search_entry_point || undefined
  };
}

/**
 * Parse URL Context usage from grounding chunks
 * 
 * Only detects URL Context if there are grounding chunks WITHOUT search queries
 * (to distinguish from Google Search with grounding)
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function parseURLContext(metadata: Record<string, any>): URLContextUsage | null {
  const grounding = metadata?.grounding_metadata;
  if (!grounding) {
    return null;
  }

  // If there are search queries, this is Google Search, not URL Context
  const searchQueries = grounding.web_search_queries;
  if (searchQueries && Array.isArray(searchQueries) && searchQueries.length > 0) {
    return null;
  }

  // Check for grounding chunks with web URIs
  const chunks = grounding.grounding_chunks;
  if (!chunks || !Array.isArray(chunks) || chunks.length === 0) {
    return null;
  }

  const urls: Array<{ uri: string; title: string }> = [];
  for (const chunk of chunks) {
    if (chunk?.web?.uri) {
      urls.push({
        uri: chunk.web.uri,
        title: chunk.web.title || ''
      });
    }
  }

  if (urls.length === 0) {
    return null;
  }

  return {
    urls,
    url_count: urls.length
  };
}

/**
 * Helper to parse language field (handles enum values, strings, or numbers)
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function parseLanguage(language: any): string {
  if (typeof language === 'string') {
    const lower = language.toLowerCase();
    if (lower === 'python' || lower === 'language.python') return 'python';
  }
  if (language === 1 || language === 'PYTHON') return 'python';
  return 'python'; // Default to python as it's the primary language for code execution
}

/**
 * Helper to parse outcome field (handles enum values, strings, or numbers)
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function parseOutcome(outcome: any): string {
  if (typeof outcome === 'string') {
    const lower = outcome.toLowerCase();
    if (lower === 'outcome_ok' || lower === 'ok') return 'ok';
    if (lower === 'outcome_error' || lower === 'error') return 'error';
  }
  if (outcome === 1 || outcome === 'OUTCOME_OK') return 'ok';
  if (outcome === 2 || outcome === 'OUTCOME_ERROR') return 'error';
  return 'unknown';
}

/**
 * Parse Code Execution usage from response metadata and content
 * 
 * Google's native code execution returns structured parts with types:
 * - executable_code/executableCode: Generated Python code
 * - code_execution_result/codeExecutionResult: Execution output
 * 
 * These can appear in response_metadata.parts or as markdown blocks in content
 * 
 * @see https://ai.google.dev/gemini-api/docs/code-execution
 */
function parseCodeExecution(
  content: string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  responseMetadata?: Record<string, any>
): CodeExecutionUsage | null {
  let codeBlocks = 0;
  let outputBlocks = 0;
  const codeBlockContents: CodeBlock[] = [];
  const outputBlockContents: OutputBlock[] = [];

  // First, check for structured parts in response metadata (Google native format)
  if (responseMetadata) {
    const parts = responseMetadata.parts || [];
    
    if (Array.isArray(parts)) {
      for (const part of parts) {
        // Skip null/undefined parts
        if (!part || typeof part !== 'object') {
          continue;
        }
        
        // Check for executable_code (snake_case)
        if (part.executable_code) {
          codeBlocks++;
          // Handle both flat structure (code is the string) and nested structure (code is in .code field)
          const code = typeof part.executable_code === 'string' 
            ? part.executable_code 
            : (part.executable_code.code || '');
          const language = parseLanguage(part.language || part.executable_code?.language);
          codeBlockContents.push({
            code,
            language
          });
        }
        // Check for executableCode (camelCase)
        else if (part.executableCode) {
          codeBlocks++;
          // Handle both flat structure (code is the string) and nested structure (code is in .code field)
          const code = typeof part.executableCode === 'string'
            ? part.executableCode
            : (part.executableCode.code || '');
          const language = parseLanguage(part.language || part.executableCode?.language);
          codeBlockContents.push({
            code,
            language
          });
        }
        
        // Check for code_execution_result (snake_case)
        if (part.code_execution_result) {
          outputBlocks++;
          // Handle both flat structure (result is the string) and nested structure (result is in .output field)
          const output = typeof part.code_execution_result === 'string'
            ? part.code_execution_result
            : (part.code_execution_result.output || '');
          const outcome = parseOutcome(part.outcome || part.code_execution_result?.outcome);
          outputBlockContents.push({
            output,
            outcome
          });
        }
        // Check for codeExecutionResult (camelCase)
        else if (part.codeExecutionResult) {
          outputBlocks++;
          // Handle both flat structure (result is the string) and nested structure (result is in .output field)
          const output = typeof part.codeExecutionResult === 'string'
            ? part.codeExecutionResult
            : (part.codeExecutionResult.output || '');
          const outcome = parseOutcome(part.outcome || part.codeExecutionResult?.outcome);
          outputBlockContents.push({
            output,
            outcome
          });
        }
      }
    }
  }

  // Also check content for markdown code blocks (fallback or legacy format)
  if (content && typeof content === 'string') {
    // Extract Python code blocks
    // Tolerates \r?\n (Windows/Unix line endings) and optional whitespace after language tag
    const pythonRegex = /```python\s*\r?\n([\s\S]*?)```/gi;
    const pythonMatches = [...content.matchAll(pythonRegex)];
    
    // Extract output blocks
    // Tolerates \r?\n (Windows/Unix line endings) and optional whitespace after language tag
    const outputRegex = /```output\s*\r?\n([\s\S]*?)```/gi;
    const outputMatches = [...content.matchAll(outputRegex)];

    // If no structured parts were found, use markdown as fallback
    if (codeBlocks === 0 && pythonMatches.length > 0) {
      codeBlocks = pythonMatches.length;
      for (const match of pythonMatches) {
        codeBlockContents.push({
          code: match[1] || '',
          language: 'python'
        });
      }
    }

    if (outputBlocks === 0 && outputMatches.length > 0) {
      outputBlocks = outputMatches.length;
      for (const match of outputMatches) {
        outputBlockContents.push({
          output: match[1] || '',
          outcome: 'ok'
        });
      }
    }
  }

  // Only consider it as code execution if we found at least one code or output block
  if (codeBlocks === 0 && outputBlocks === 0) {
    return null;
  }

  return {
    code_blocks: codeBlocks,
    output_blocks: outputBlocks,
    detected: true,
    code_block_contents: codeBlockContents.length > 0 ? codeBlockContents : undefined,
    output_block_contents: outputBlockContents.length > 0 ? outputBlockContents : undefined
  };
}

/**
 * Helper to get response content from LLM interaction details
 * Handles both conversation and legacy messages formats
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function extractResponseContent(details: any): string | null {
  // Try conversation field first
  if (details?.conversation?.messages) {
    const messages = details.conversation.messages;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const assistantMsg = messages.slice().reverse().find((m: any) => m?.role === 'assistant');
    if (assistantMsg?.content) {
      return typeof assistantMsg.content === 'string' ? assistantMsg.content : JSON.stringify(assistantMsg.content);
    }
  }

  // Try legacy messages field
  if (details?.messages) {
    const messages = details.messages;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const assistantMsg = messages.slice().reverse().find((m: any) => m?.role === 'assistant');
    if (assistantMsg?.content) {
      return typeof assistantMsg.content === 'string' ? assistantMsg.content : JSON.stringify(assistantMsg.content);
    }
  }

  return null;
}

