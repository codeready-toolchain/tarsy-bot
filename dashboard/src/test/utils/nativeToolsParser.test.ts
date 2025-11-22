/**
 * Tests for native tools parser
 */

import { describe, it, expect } from 'vitest';
import { parseNativeToolsUsage, extractResponseContent } from '../../utils/nativeToolsParser';

describe('parseNativeToolsUsage', () => {
  describe('Google Search', () => {
    it('should parse single search query', () => {
      const metadata = {
        grounding_metadata: {
          web_search_queries: ['kubernetes pod status']
        }
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result).not.toBeNull();
      expect(result?.google_search).toEqual({
        queries: ['kubernetes pod status'],
        query_count: 1,
        search_entry_point: undefined
      });
    });

    it('should parse multiple search queries', () => {
      const metadata = {
        grounding_metadata: {
          web_search_queries: ['query 1', 'query 2', 'query 3']
        }
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result).not.toBeNull();
      expect(result?.google_search?.query_count).toBe(3);
      expect(result?.google_search?.queries).toHaveLength(3);
    });

    it('should include search_entry_point when present', () => {
      const metadata = {
        grounding_metadata: {
          web_search_queries: ['test query'],
          search_entry_point: { rendered_content: 'some data' }
        }
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result?.google_search?.search_entry_point).toEqual({ rendered_content: 'some data' });
    });

    it('should return null when no search queries', () => {
      const metadata = {
        grounding_metadata: {
          web_search_queries: []
        }
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result).toBeNull();
    });
  });

  describe('URL Context', () => {
    it('should parse single URL', () => {
      const metadata = {
        grounding_metadata: {
          grounding_chunks: [
            {
              web: {
                uri: 'https://example.com',
                title: 'Example Title'
              }
            }
          ]
        }
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result).not.toBeNull();
      expect(result?.url_context).toEqual({
        urls: [{ uri: 'https://example.com', title: 'Example Title' }],
        url_count: 1
      });
    });

    it('should parse multiple URLs', () => {
      const metadata = {
        grounding_metadata: {
          grounding_chunks: [
            { web: { uri: 'https://example.com', title: 'Example 1' } },
            { web: { uri: 'https://test.com', title: 'Example 2' } }
          ]
        }
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result?.url_context?.url_count).toBe(2);
      expect(result?.url_context?.urls).toHaveLength(2);
    });

    it('should handle URLs without titles', () => {
      const metadata = {
        grounding_metadata: {
          grounding_chunks: [
            { web: { uri: 'https://example.com' } }
          ]
        }
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result?.url_context?.urls[0]).toEqual({
        uri: 'https://example.com',
        title: ''
      });
    });

    it('should not detect URL context when search queries present', () => {
      const metadata = {
        grounding_metadata: {
          web_search_queries: ['test query'],
          grounding_chunks: [
            { web: { uri: 'https://example.com', title: 'Example' } }
          ]
        }
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result?.url_context).toBeUndefined();
      expect(result?.google_search).not.toBeUndefined();
    });

    it('should return null when no web chunks', () => {
      const metadata = {
        grounding_metadata: {
          grounding_chunks: []
        }
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result).toBeNull();
    });
  });

  describe('Code Execution', () => {
    it('should detect Python code blocks in content (markdown format)', () => {
      const content = `Here's some code:
\`\`\`python
print("hello")
\`\`\`
Done.`;

      const result = parseNativeToolsUsage(null, content);

      expect(result).not.toBeNull();
      expect(result?.code_execution).toEqual({
        code_blocks: 1,
        output_blocks: 0,
        detected: true
      });
    });

    it('should detect structured code execution parts in metadata (Google native format)', () => {
      const metadata = {
        parts: [
          {
            text: 'Let me calculate that'
          },
          {
            executable_code: {
              language: 'PYTHON',
              code: 'print("hello")'
            }
          },
          {
            code_execution_result: {
              outcome: 'OUTCOME_OK',
              output: 'hello\n'
            }
          }
        ]
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result).not.toBeNull();
      expect(result?.code_execution).toEqual({
        code_blocks: 1,
        output_blocks: 1,
        detected: true
      });
    });

    it('should detect camelCase structured parts (JavaScript SDK format)', () => {
      const metadata = {
        parts: [
          {
            executableCode: {
              language: 'PYTHON',
              code: 'x = 5'
            }
          },
          {
            codeExecutionResult: {
              outcome: 'OUTCOME_OK',
              output: ''
            }
          }
        ]
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result?.code_execution).toEqual({
        code_blocks: 1,
        output_blocks: 1,
        detected: true
      });
    });

    it('should count multiple structured code execution parts', () => {
      const metadata = {
        parts: [
          { executable_code: { code: 'code1' } },
          { code_execution_result: { output: 'output1' } },
          { executable_code: { code: 'code2' } },
          { code_execution_result: { output: 'output2' } }
        ]
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result?.code_execution).toEqual({
        code_blocks: 2,
        output_blocks: 2,
        detected: true
      });
    });

    it('should detect output blocks in content', () => {
      const content = `Result:
\`\`\`output
hello world
\`\`\``;

      const result = parseNativeToolsUsage(null, content);

      expect(result?.code_execution).toEqual({
        code_blocks: 0,
        output_blocks: 1,
        detected: true
      });
    });

    it('should count multiple code and output blocks in content', () => {
      const content = `
\`\`\`python
code1()
\`\`\`
\`\`\`output
output1
\`\`\`
\`\`\`python
code2()
\`\`\`
\`\`\`output
output2
\`\`\``;

      const result = parseNativeToolsUsage(null, content);

      expect(result?.code_execution).toEqual({
        code_blocks: 2,
        output_blocks: 2,
        detected: true
      });
    });

    it('should prefer structured parts over markdown when both present', () => {
      const metadata = {
        parts: [
          { executable_code: { code: 'structured' } },
          { code_execution_result: { output: 'result' } }
        ]
      };
      const content = '```python\nmarkdown\n```';

      const result = parseNativeToolsUsage(metadata, content);

      // Should use structured count (1) not markdown count (1)
      expect(result?.code_execution?.code_blocks).toBe(1);
    });

    it('should return null when no code blocks found', () => {
      const content = 'Just regular text without code blocks';

      const result = parseNativeToolsUsage(null, content);

      expect(result).toBeNull();
    });

    it('should be case-insensitive for code block detection in content', () => {
      const content = '```PYTHON\ncode()\n```';

      const result = parseNativeToolsUsage(null, content);

      expect(result?.code_execution?.code_blocks).toBe(1);
    });

    it('should handle metadata without parts array', () => {
      const metadata = {
        other_field: 'value'
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result).toBeNull();
    });

    it('should handle malformed parts array', () => {
      const metadata = {
        parts: [
          { text: 'just text' },
          null,
          { unknown_field: 'value' }
        ]
      };

      const result = parseNativeToolsUsage(metadata, null);

      expect(result).toBeNull();
    });
  });

  describe('Combined tools', () => {
    it('should detect multiple tools used together', () => {
      const metadata = {
        grounding_metadata: {
          web_search_queries: ['test query']
        }
      };
      const content = '```python\nprint("test")\n```';

      const result = parseNativeToolsUsage(metadata, content);

      expect(result?.google_search).not.toBeUndefined();
      expect(result?.code_execution).not.toBeUndefined();
    });

    it('should handle URL context and code execution together', () => {
      const metadata = {
        grounding_metadata: {
          grounding_chunks: [
            { web: { uri: 'https://example.com', title: 'Test' } }
          ]
        }
      };
      const content = '```python\ncode()\n```';

      const result = parseNativeToolsUsage(metadata, content);
      expect(result?.url_context).not.toBeUndefined();
      expect(result?.code_execution).not.toBeUndefined();
    });
  });

  describe('Edge cases', () => {
    it('should handle null metadata and content', () => {
      const result = parseNativeToolsUsage(null, null);
      expect(result).toBeNull();
    });

    it('should handle undefined metadata and content', () => {
      const result = parseNativeToolsUsage(undefined, undefined);
      expect(result).toBeNull();
    });

    it('should handle empty metadata object', () => {
      const result = parseNativeToolsUsage({}, null);
      expect(result).toBeNull();
    });

    it('should handle metadata without grounding_metadata', () => {
      const metadata = { some_other_field: 'value' };
      const result = parseNativeToolsUsage(metadata, null);
      expect(result).toBeNull();
    });

    it('should handle malformed grounding chunks', () => {
      const metadata = {
        grounding_metadata: {
          grounding_chunks: [
            { something: 'else' },  // No web field
            { web: null },  // Null web
            { web: {} }  // Empty web
          ]
        }
      };

      const result = parseNativeToolsUsage(metadata, null);
      expect(result).toBeNull();
    });

    it('should handle empty content string', () => {
      const result = parseNativeToolsUsage(null, '');
      expect(result).toBeNull();
    });

    it('should handle content with only whitespace', () => {
      const result = parseNativeToolsUsage(null, '   \n\n  ');
      expect(result).toBeNull();
    });
  });
});

describe('extractResponseContent', () => {
  it('should extract content from conversation field', () => {
    const details = {
      conversation: {
        messages: [
          { role: 'system', content: 'system msg' },
          { role: 'user', content: 'user msg' },
          { role: 'assistant', content: 'assistant response' }
        ]
      }
    };

    const result = extractResponseContent(details);
    expect(result).toBe('assistant response');
  });

  it('should extract content from legacy messages field', () => {
    const details = {
      messages: [
        { role: 'system', content: 'system msg' },
        { role: 'assistant', content: 'assistant response' }
      ]
    };

    const result = extractResponseContent(details);
    expect(result).toBe('assistant response');
  });

  it('should get latest assistant message', () => {
    const details = {
      conversation: {
        messages: [
          { role: 'assistant', content: 'first response' },
          { role: 'user', content: 'follow-up' },
          { role: 'assistant', content: 'second response' }
        ]
      }
    };

    const result = extractResponseContent(details);
    expect(result).toBe('second response');
  });

  it('should handle non-string content', () => {
    const details = {
      conversation: {
        messages: [
          { role: 'assistant', content: { structured: 'data' } }
        ]
      }
    };

    const result = extractResponseContent(details);
    expect(result).toBe('{"structured":"data"}');
  });

  it('should return null when no assistant message', () => {
    const details = {
      conversation: {
        messages: [
          { role: 'system', content: 'system' },
          { role: 'user', content: 'user' }
        ]
      }
    };

    const result = extractResponseContent(details);
    expect(result).toBeNull();
  });

  it('should return null when no messages', () => {
    const details = { conversation: { messages: [] } };
    const result = extractResponseContent(details);
    expect(result).toBeNull();
  });

  it('should return null when details is null', () => {
    const result = extractResponseContent(null);
    expect(result).toBeNull();
  });
});

