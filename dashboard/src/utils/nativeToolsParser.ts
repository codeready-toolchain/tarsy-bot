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
  CodeExecutionUsage 
} from '../types';

/**
 * Main parser function to extract native tools usage from response metadata and content
 * 
 * @param responseMetadata - Response metadata from LLM interaction
 * @param responseContent - Response content (for code execution detection)
 * @returns Structured tool usage summary, or null if no tools were used
 */
export function parseNativeToolsUsage(
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

  // Parse Code Execution usage from content
  if (responseContent) {
    const codeExecution = parseCodeExecution(responseContent);
    if (codeExecution) {
      toolUsage.code_execution = codeExecution;
      hasAnyUsage = true;
    }
  }

  return hasAnyUsage ? toolUsage : null;
}

/**
 * Parse Google Search usage from grounding metadata
 */
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
 * Parse Code Execution usage from response content
 * 
 * Detects Python code blocks and output blocks in the response
 */
function parseCodeExecution(content: string): CodeExecutionUsage | null {
  if (!content || typeof content !== 'string') {
    return null;
  }

  // Count code blocks (```python)
  const codeBlockMatches = content.match(/```python/gi);
  const codeBlocks = codeBlockMatches ? codeBlockMatches.length : 0;

  // Count output blocks (```output)
  const outputBlockMatches = content.match(/```output/gi);
  const outputBlocks = outputBlockMatches ? outputBlockMatches.length : 0;

  // Only consider it as code execution if we found at least one code or output block
  if (codeBlocks === 0 && outputBlocks === 0) {
    return null;
  }

  return {
    code_blocks: codeBlocks,
    output_blocks: outputBlocks,
    detected: true
  };
}

/**
 * Helper to get response content from LLM interaction details
 * Handles both conversation and legacy messages formats
 */
export function extractResponseContent(details: any): string | null {
  // Try conversation field first
  if (details?.conversation?.messages) {
    const messages = details.conversation.messages;
    const assistantMsg = messages.slice().reverse().find((m: any) => m?.role === 'assistant');
    if (assistantMsg?.content) {
      return typeof assistantMsg.content === 'string' ? assistantMsg.content : JSON.stringify(assistantMsg.content);
    }
  }

  // Try legacy messages field
  if (details?.messages) {
    const messages = details.messages;
    const assistantMsg = messages.slice().reverse().find((m: any) => m?.role === 'assistant');
    if (assistantMsg?.content) {
      return typeof assistantMsg.content === 'string' ? assistantMsg.content : JSON.stringify(assistantMsg.content);
    }
  }

  return null;
}

