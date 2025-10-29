import type { ParsedContent, SectionType } from '../types';

/**
 * Parse Python LLMMessage objects from string representation
 * Example: "[LLMMessage(role='user', content='...'), ...]"
 */
export const parsePythonLLMMessages = (content: string): ParsedContent => {
  try {
    const messages: Array<{ role: string; content: string }> = [];

    // Use a more robust approach: split by LLMMessage and parse each separately
    const messageParts = content.split('LLMMessage(').slice(1); // Remove empty first element
    
    messageParts.forEach((part) => {
      // Find the role
      const roleMatch = part.match(/role='([^']+)'/);
      if (!roleMatch) {
        return;
      }
      
      const role = roleMatch[1];
      
      // For content, we need to be more careful about finding the end
      // Look for content=' and then find the matching closing quote
      const contentStartMatch = part.match(/content='(.*)$/s);
      if (!contentStartMatch) {
        return;
      }
      
      let rawContent = contentStartMatch[1];
      let messageContent = '';
      
      // The content ends when we hit ')' that's not escaped and not inside nested quotes
      // This is tricky, so let's use a character-by-character approach
      let i = 0;
      let escapeNext = false;
      
      while (i < rawContent.length) {
        const char = rawContent[i];
        
        if (escapeNext) {
          messageContent += char;
          escapeNext = false;
        } else if (char === '\\') {
          messageContent += char;
          escapeNext = true;
        } else if (char === "'") {
          // This might be the end of the content
          // Look ahead to see if we have ')' or ', ' next
          const nextChars = rawContent.substring(i + 1, i + 5);
          if (nextChars.startsWith(')') || nextChars.match(/^,\s*[a-zA-Z_]+=/) || i === rawContent.length - 1) {
            // This is likely the end of content
            break;
          }
          messageContent += char;
        } else {
          messageContent += char;
        }
        i++;
      }
      
      // Clean up escaped characters
      messageContent = messageContent
        .replace(/\\n/g, '\n')
        .replace(/\\'/g, "'")
        .replace(/\\"/g, '"')
        .replace(/\\\\/g, '\\')
        .replace(/\\t/g, '\t');
      
      messages.push({
        role,
        content: messageContent
      });
    });

    if (messages.length > 0) {
      const sections = messages.map((msg, index) => {
        let sectionType: SectionType;
        if (msg.role === 'system') {
          sectionType = 'system-prompt';
        } else if (msg.role === 'assistant') {
          sectionType = 'assistant-prompt';
        } else {
          sectionType = 'user-prompt';
        }
        
        return {
          id: `llm-message-${msg.role}-${index}`,
          title: `${msg.role.charAt(0).toUpperCase() + msg.role.slice(1)} Message`,
          type: sectionType,
          content: msg.content,
          raw: `Role: ${msg.role}\n\n${msg.content}`
        };
      });

      return {
        type: 'python-objects',
        content: messages,
        sections
      };
    }
  } catch (error) {
    console.warn('Failed to parse Python LLMMessage objects:', error);
  }

  return { type: 'plain-text', content };
};

/**
 * Parse mixed content with JSON snippets, markdown, code blocks, etc.
 */
export const parseMixedContent = (content: string): ParsedContent => {
  const sections = [];
  let remainingContent = content;
  let sectionIndex = 0;

  // Extract JSON code blocks
  const jsonRegex = /```json\s*([\s\S]*?)\s*```/g;
  let jsonMatch;
  while ((jsonMatch = jsonRegex.exec(content)) !== null) {
    try {
      const jsonContent = JSON.parse(jsonMatch[1]);
      sections.push({
        id: `json-block-${sectionIndex + 1}`,
        title: `JSON Block ${sectionIndex + 1}`,
        type: 'json' as SectionType,
        content: jsonContent,
        raw: jsonMatch[1]
      });
      sectionIndex++;
      remainingContent = remainingContent.replace(jsonMatch[0], `[JSON_BLOCK_${sectionIndex}]`);
    } catch {
      // Invalid JSON, skip
    }
  }

  // Extract other code blocks
  const codeRegex = /```(\w*)\s*([\s\S]*?)\s*```/g;
  let codeMatch;
  while ((codeMatch = codeRegex.exec(content)) !== null) {
    if (codeMatch[1] !== 'json') { // Skip JSON blocks (already handled above)
      sections.push({
        id: `code-block-${sectionIndex + 1}`,
        title: `${codeMatch[1] || 'Code'} Block ${sectionIndex + 1}`,
        type: 'code' as SectionType,
        content: codeMatch[2],
        raw: codeMatch[2]
      });
      sectionIndex++;
      remainingContent = remainingContent.replace(codeMatch[0], `[CODE_BLOCK_${sectionIndex}]`);
    }
  }

  // If we found structured sections, return mixed content
  if (sections.length > 0) {
    return {
      type: 'mixed',
      content: { text: remainingContent, sections },
      sections
    };
  }

  // Check if it's markdown-like
  if (content.includes('##') || content.includes('**') || content.includes('- ')) {
    return { type: 'markdown', content };
  }

  return { type: 'plain-text', content };
};

/**
 * Main content parser - intelligently detects and parses different content types
 * Supports JSON, YAML, text, Python objects, and mixed content
 */
export const parseContent = (value: any): ParsedContent => {
  if (value === null || value === undefined) {
    return { type: 'plain-text', content: String(value) };
  }

  // Special handling for MCP results that contain YAML/text/JSON content
  if (typeof value === 'object' && value !== null) {
    // Check if this is an MCP result with a nested text/YAML/JSON result
    // Handle string result fields first (they have special parsing logic)
    if ('result' in value && typeof value.result === 'string') {
      const resultContent = value.result.trim();
      
      // First, try to parse as JSON (most common case)
      try {
        const parsedJson = JSON.parse(resultContent);
        
        // Successfully parsed as JSON
        // Check if it's a nested object with multi-line text fields
        if (typeof parsedJson === 'object' && parsedJson !== null) {
          // Recursively find ALL fields that contain multi-line text
          const multiLineFields: Array<{ path: string; fieldName: string; content: string }> = [];
          
          const findMultiLineFields = (obj: any, path: string[] = []) => {
            if (typeof obj === 'string' && obj.length > 200 && obj.includes('\n')) {
              // Found a multi-line text field
              const fieldName = path[path.length - 1] || 'content';
              const fullPath = path.join(' → ');
              multiLineFields.push({ 
                path: fullPath, 
                fieldName, 
                content: obj 
              });
            } else if (Array.isArray(obj)) {
              // Search through array elements
              obj.forEach((item, index) => {
                findMultiLineFields(item, [...path, `[${index}]`]);
              });
            } else if (typeof obj === 'object' && obj !== null) {
              // Search through object properties
              for (const [key, value] of Object.entries(obj)) {
                findMultiLineFields(value, [...path, key]);
              }
            }
          };
          
          findMultiLineFields(parsedJson);
          
          if (multiLineFields.length > 0) {
            // Create sections: First the JSON, then each multi-line field formatted
            const sections = [
              {
                id: 'mcp-json',
                title: 'MCP Tool Result (JSON)',
                type: 'json' as SectionType,
                content: parsedJson,
                raw: JSON.stringify(parsedJson, null, 2)
              }
            ];
            
            // Add a formatted section for each multi-line field
            for (const { path, fieldName, content } of multiLineFields) {
              // Create a readable title from the path
              const title = path 
                ? `${fieldName.charAt(0).toUpperCase() + fieldName.slice(1)} (Formatted)`
                : 'Formatted Text';
              const id = `mlf:${path || fieldName}`;
              
              sections.push({
                id,
                title,
                type: 'text' as SectionType,
                content: content,
                raw: content
              });
            }
            
            return {
              type: 'mixed',
              content: { text: '', sections: [] },
              sections
            };
          }
          
          // Regular JSON object without special formatting
          return {
            type: 'mixed',
            content: { text: '', sections: [] },
            sections: [
              {
                id: 'mcp-json',
                title: 'MCP Tool Result (JSON)',
                type: 'json' as SectionType,
                content: parsedJson,
                raw: JSON.stringify(parsedJson, null, 2)
              }
            ]
          };
        }
        
        // Parsed JSON is a simple value (string, number, etc.)
        return {
          type: 'mixed',
          content: { text: '', sections: [] },
          sections: [
            {
              id: 'mcp-json-simple',
              title: 'MCP Tool Result',
              type: 'json' as SectionType,
              content: parsedJson,
              raw: JSON.stringify(parsedJson, null, 2)
            }
          ]
        };
      } catch {
        // Not valid JSON (possibly malformed escape sequences), try other formats
      }
      
      // Check if the result contains YAML content
      if (resultContent.includes('apiVersion:') || 
          resultContent.includes('kind:') || 
          resultContent.includes('metadata:') ||
          resultContent.includes('\n') && (resultContent.includes(':') || resultContent.includes('-'))) {
        
        // This looks like YAML - format it nicely
        return {
          type: 'mixed',
          content: { text: '', sections: [] },
          sections: [
            {
              id: 'mcp-yaml',
              title: 'MCP Tool Result (YAML)',
              type: 'yaml' as SectionType,
              content: resultContent,
              raw: resultContent
            }
          ]
        };
      }
      
      // Check if it's other structured text content
      if (resultContent.length > 50 && (resultContent.includes('\n') || resultContent.includes('\t'))) {
        return {
          type: 'mixed',
          content: { text: '', sections: [] },
          sections: [
            {
              id: 'mcp-text',
              title: 'MCP Tool Result (Text)',
              type: 'text' as SectionType,
              content: resultContent,
              raw: resultContent
            }
          ]
        };
      }
    }
    
    // Check if this is a wrapper object with a single "result" field (non-string)
    // If so, unwrap it and process the result value instead
    const keys = Object.keys(value);
    if (keys.length === 1 && keys[0] === 'result') {
      // Unwrap and recursively parse the result value
      return parseContent(value.result);
    }
    
    // Fall through to normal JSON handling for other objects
  }

  if (typeof value === 'string') {
    // Try to detect and parse different content types
    const content = value.trim();
    
    // Check for Python list/object representations
    if (content.startsWith('[') && content.includes('LLMMessage(') && content.includes('role=')) {
      return parsePythonLLMMessages(content);
    }
    
    // Check for pure JSON
    try {
      const parsed = JSON.parse(content);
      if (typeof parsed === 'object') {
        return { type: 'json', content: parsed };
      }
    } catch {
      // Not pure JSON, continue parsing
    }
    
    // Check for mixed content with JSON snippets
    const jsonMatches = content.match(/```json\s*([\s\S]*?)\s*```/g);
    const codeMatches = content.match(/```\w*\s*([\s\S]*?)\s*```/g);
    
    if (jsonMatches || codeMatches || content.includes('##') || content.includes('**')) {
      return parseMixedContent(content);
    }
    
    // Try to parse as JSON one more time for edge cases
    try {
      const parsed = JSON.parse(content);
      return { type: 'json', content: parsed };
    } catch {
      return { type: 'plain-text', content };
    }
  }

  // Handle objects directly
  return { type: 'json', content: value };
};
