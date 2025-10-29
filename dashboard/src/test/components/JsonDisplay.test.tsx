import { describe, it, expect } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import JsonDisplay from '../../components/JsonDisplay';

/**
 * Tests for enhanced MCP tool result rendering in JsonDisplay component
 * 
 * These tests verify that MCP tool results with nested JSON strings
 * are safely parsed and displayed in a user-friendly format.
 */
describe('JsonDisplay - MCP Tool Result Rendering', () => {
  
  it('should parse and display MCP result with nested JSON object', () => {
    // Example from user: {"result": "{\"pods\":[...]}"}
    const mcpResult = {
      result: '{"pods":[{"containers":["devworkspace-telemetry-amplitude-plugin","universal-developer-image","che-gateway"],"name":"workspacee878db8c624946ac-5d9c499c46-mjwfc"}]}'
    };
    
    const { container } = render(<JsonDisplay data={mcpResult} />);
    
    // Should display as "MCP Tool Result (JSON)"
    expect(container.textContent).toContain('MCP Tool Result (JSON)');
    
    // The parsed JSON should be displayed, not the string representation
    const parsedResult = JSON.parse(mcpResult.result);
    expect(parsedResult.pods).toHaveLength(1);
    expect(parsedResult.pods[0].name).toBe('workspacee878db8c624946ac-5d9c499c46-mjwfc');
  });
  
  it('should parse and display MCP result with nested JSON containing formatted text', async () => {
    // Example from user: {"result": "{\"analysis\":\"CPU consumption analysis...\"}"}
    const mcpResult = {
      result: '{"analysis":"CPU consumption analysis for EC2 instance \'i-0f6db88b1b51b00c9\' (looking back 2h):\\n\\n\\nThe **i-0f6db88b1b51b00c9** EC2 instance is running the **ip-10-0-87-9.ec2.internal** node on our **rm3** cluster.\\n\\nNothing suspicious pods detected ¯_(ツ)_/¯\\n\\n\\n"}'
    };

    const user = userEvent.setup();
    const { container, getByRole } = render(<JsonDisplay data={mcpResult} />);

    // Should create tabs for "Formatted Text" and "Raw Data"
    expect(container.textContent).toContain('Formatted Text');
    expect(container.textContent).toContain('Raw Data');

    // Should create a separate "Analysis (Formatted)" section for the long text (visible in Formatted Text tab)
    expect(container.textContent).toContain('Analysis (Formatted)');

    // Click on the "Raw Data" tab to see the JSON section
    const rawDataTab = getByRole('tab', { name: /raw data/i });
    await user.click(rawDataTab);

    // Wait for the tab content to update and display "MCP Tool Result (JSON)" section
    await waitFor(() => {
      expect(container.textContent).toContain('MCP Tool Result (JSON)');
    });

    // Verify the parsed content
    const parsedResult = JSON.parse(mcpResult.result);
    expect(parsedResult.analysis).toContain('CPU consumption analysis');
    expect(parsedResult.analysis).toContain('i-0f6db88b1b51b00c9');
  });
  
  it('should handle MCP result with simple JSON string', () => {
    const mcpResult = {
      result: '{"status":"success","count":42}'
    };
    
    const { container } = render(<JsonDisplay data={mcpResult} />);
    
    // Should display as structured JSON
    expect(container.textContent).toContain('MCP Tool Result (JSON)');
    
    const parsedResult = JSON.parse(mcpResult.result);
    expect(parsedResult.status).toBe('success');
    expect(parsedResult.count).toBe(42);
  });
  
  it('should safely handle invalid JSON and fall back to text rendering', () => {
    // Test data that triggers text fallback (not YAML):
    // - More than 50 characters
    // - Contains newlines
    // - No : or - characters (to avoid YAML detection)
    // - Invalid JSON
    const mcpResult = {
      result: 'This text contains {invalid JSON syntax}\nIt has multiple lines here\nMore than fifty characters total in length\nThis triggers the text rendering path not YAML'
    };
    
    const { getByText } = render(<JsonDisplay data={mcpResult} />);
    
    // Should fall back to text rendering with the appropriate label
    expect(getByText('MCP Tool Result (Text)')).toBeInTheDocument();
    
    // Should also display the actual content
    expect(getByText(/This text contains/)).toBeInTheDocument();
  });
  
  it('should handle YAML content correctly', () => {
    const mcpResult = {
      result: 'apiVersion: v1\nkind: Pod\nmetadata:\n  name: test-pod'
    };
    
    const { container } = render(<JsonDisplay data={mcpResult} />);
    
    // Should detect and display as YAML
    expect(container.textContent).toContain('MCP Tool Result (YAML)');
  });
  
  it('should handle multi-line text content', () => {
    const mcpResult = {
      result: 'Line 1 - Some information here\nLine 2 - More information here\nLine 3 - Even more information\nLine 4 - Final line with details'
    };
    
    const { container } = render(<JsonDisplay data={mcpResult} />);
    
    // Should display as formatted text (checking for the actual content)
    expect(container.textContent).toContain('Some information here');
  });
  
  it('should handle deeply nested JSON safely', () => {
    const mcpResult = {
      result: JSON.stringify({
        level1: {
          level2: {
            level3: {
              data: [1, 2, 3],
              message: 'Deep nesting test'
            }
          }
        }
      })
    };
    
    const { container } = render(<JsonDisplay data={mcpResult} />);
    
    // Should parse and display the nested structure
    expect(container.textContent).toContain('MCP Tool Result (JSON)');
    
    const parsedResult = JSON.parse(mcpResult.result);
    expect(parsedResult.level1.level2.level3.message).toBe('Deep nesting test');
  });
  
  it('should handle empty or minimal result fields', () => {
    const testCases = [
      { result: '{}' },
      { result: '[]' },
      { result: '{"empty":true}' },
    ];
    
    testCases.forEach(testCase => {
      const { container } = render(<JsonDisplay data={testCase} />);
      // Should not throw errors
      expect(container).toBeTruthy();
    });
  });
  
  it('should properly escape and display special characters in text', () => {
    const mcpResult = {
      result: '{"message":"Test with special chars: \\n newline \\t tab \\" quote"}'
    };
    
    const { container } = render(<JsonDisplay data={mcpResult} />);
    
    // Should safely parse and display
    expect(container).toBeTruthy();
    
    const parsedResult = JSON.parse(mcpResult.result);
    expect(parsedResult.message).toContain('special chars');
  });
  
  it('should display main text in Tab Panel 0 (Formatted Text) when tabs are shown', async () => {
    // Test case with MCP result that has both JSON data and a long text field
    // This triggers tabs: one for formatted text, one for raw JSON
    const longText = 'This is a long multi-line text that should appear in the Formatted Text tab.\n'.repeat(10);
    const mcpResult = {
      result: JSON.stringify({
        status: 'success',
        description: longText,
        data: { key: 'value', count: 42 }
      })
    };
    
    const user = userEvent.setup();
    const { container, getByRole } = render(<JsonDisplay data={mcpResult} />);
    
    // Should create tabs for "Formatted Text" and "Raw Data"
    expect(container.textContent).toContain('Formatted Text');
    expect(container.textContent).toContain('Raw Data');
    
    // Formatted Text tab should be active by default (activeTab = 0)
    const formattedTextTab = getByRole('tab', { name: /formatted text/i });
    expect(formattedTextTab).toHaveAttribute('aria-selected', 'true');
    
    // The formatted description text should be visible in Tab 0
    expect(container.textContent).toContain('Description (Formatted)');
    expect(container.textContent).toContain('This is a long multi-line text');
    
    // Switch to Raw Data tab
    const rawDataTab = getByRole('tab', { name: /raw data/i });
    await user.click(rawDataTab);
    
    // Wait for tab change and verify JSON section appears
    await waitFor(() => {
      expect(container.textContent).toContain('MCP Tool Result (JSON)');
    });
  });
});

describe('JsonDisplay - Python LLM Message Parsing', () => {
  it('should correctly parse and display system, user, and assistant messages', () => {
    const pythonLLMMessages = "[LLMMessage(role='system', content='You are a helpful assistant.'), LLMMessage(role='user', content='What is 2+2?'), LLMMessage(role='assistant', content='The answer is 4.')]";
    
    const { container } = render(<JsonDisplay data={pythonLLMMessages} />);
    
    // Should display LLM Messages label
    expect(container.textContent).toContain('LLM Messages');
    expect(container.textContent).toContain('3 messages');
    
    // Should display all three role labels
    expect(container.textContent).toContain('System');
    expect(container.textContent).toContain('User');
    expect(container.textContent).toContain('Assistant');
  });
  
  it('should assign correct section types to different message roles', () => {
    const pythonLLMMessages = "[LLMMessage(role='system', content='System prompt here'), LLMMessage(role='user', content='User query here'), LLMMessage(role='assistant', content='Assistant response here')]";
    
    const { container, getByText } = render(<JsonDisplay data={pythonLLMMessages} />);
    
    // Verify that each message type is displayed with correct label
    expect(getByText('System')).toBeInTheDocument();
    expect(getByText('User')).toBeInTheDocument();
    expect(getByText('Assistant')).toBeInTheDocument();
    
    // Verify content is present
    expect(container.textContent).toContain('System prompt here');
    expect(container.textContent).toContain('User query here');
    expect(container.textContent).toContain('Assistant response here');
  });
  
  it('should handle multi-line content in assistant messages', () => {
    const pythonLLMMessages = "[LLMMessage(role='assistant', content='Line 1: First line\\nLine 2: Second line\\nLine 3: Third line')]";
    
    const { container } = render(<JsonDisplay data={pythonLLMMessages} />);
    
    // Should display the Assistant label
    expect(container.textContent).toContain('Assistant');
    
    // Should handle multi-line content (checking for presence of content)
    expect(container.textContent).toContain('First line');
    expect(container.textContent).toContain('Second line');
    expect(container.textContent).toContain('Third line');
  });
  
  it('should handle escaped characters in message content', () => {
    const pythonLLMMessages = "[LLMMessage(role='user', content='Test with \\'quotes\\' and \\\"double quotes\\\"'), LLMMessage(role='assistant', content='Response with \\ttab and \\nnewline')]";
    
    const { container } = render(<JsonDisplay data={pythonLLMMessages} />);
    
    // Should properly unescape content
    expect(container.textContent).toContain("Test with 'quotes'");
    expect(container.textContent).toContain('Response with');
  });
  
  it('should handle empty or very short assistant messages', () => {
    const pythonLLMMessages = "[LLMMessage(role='assistant', content='')]";
    
    const { container } = render(<JsonDisplay data={pythonLLMMessages} />);
    
    // Should still display the Assistant label even with empty content
    expect(container.textContent).toContain('Assistant');
  });
  
  it('should handle multiple assistant messages in a conversation', () => {
    const pythonLLMMessages = "[LLMMessage(role='user', content='First question'), LLMMessage(role='assistant', content='First answer'), LLMMessage(role='user', content='Follow-up question'), LLMMessage(role='assistant', content='Follow-up answer')]";
    
    const { container, getAllByText } = render(<JsonDisplay data={pythonLLMMessages} />);
    
    // Should display correct count
    expect(container.textContent).toContain('4 messages');
    
    // Should have Assistant labels (checking for the chip labels specifically)
    const assistantChips = getAllByText('Assistant');
    expect(assistantChips.length).toBeGreaterThanOrEqual(2);
    
    // Verify content is present
    expect(container.textContent).toContain('First answer');
    expect(container.textContent).toContain('Follow-up answer');
  });
});

describe('JsonDisplay - Single Field Result Unwrapping', () => {
  it('should unwrap single-field result object with string value', () => {
    const wrappedResult = {
      result: 'Simple text value'
    };
    
    const { container } = render(<JsonDisplay data={wrappedResult} />);
    
    // Should display the unwrapped string value directly
    expect(container.textContent).toContain('Simple text value');
    // Should not show the wrapper object
    expect(container.textContent).not.toContain('"result"');
  });
  
  it('should unwrap single-field result object with direct JSON object', () => {
    const wrappedResult = {
      result: {
        status: 'success',
        count: 42,
        items: ['item1', 'item2']
      }
    };
    
    const { container } = render(<JsonDisplay data={wrappedResult} />);
    
    // Should display the unwrapped object with its actual structure
    expect(container.textContent).toContain('status');
    expect(container.textContent).toContain('success');
    expect(container.textContent).toContain('count');
    // Should not show the "result" wrapper key
    expect(container.textContent).not.toMatch(/^result/);
  });
  
  it('should unwrap single-field result object with array value', () => {
    const wrappedResult = {
      result: ['item1', 'item2', 'item3']
    };
    
    const { container } = render(<JsonDisplay data={wrappedResult} />);
    
    // Should display the array directly
    expect(container.textContent).toContain('item1');
    expect(container.textContent).toContain('item2');
    expect(container.textContent).toContain('item3');
  });
  
  it('should unwrap nested single-field result objects recursively', () => {
    const nestedWrappedResult = {
      result: {
        result: 'Deeply nested value'
      }
    };
    
    const { container } = render(<JsonDisplay data={nestedWrappedResult} />);
    
    // Should unwrap recursively to the innermost value
    expect(container.textContent).toContain('Deeply nested value');
  });
  
  it('should not unwrap result when there are multiple fields', () => {
    const multiFieldResult = {
      result: 'value',
      otherField: 'other value'
    };
    
    const { container } = render(<JsonDisplay data={multiFieldResult} />);
    
    // Should keep the wrapper object intact since it has multiple fields
    expect(container.textContent).toContain('result');
    expect(container.textContent).toContain('otherField');
  });
  
  it('should preserve existing behavior for string result fields', () => {
    // This is the existing behavior - result field with stringified JSON
    const mcpResult = {
      result: '{"status":"success","count":42}'
    };
    
    const { container } = render(<JsonDisplay data={mcpResult} />);
    
    // Should unwrap and then parse the JSON string
    expect(container.textContent).toContain('status');
    expect(container.textContent).toContain('success');
    expect(container.textContent).toContain('count');
  });
});

describe('JsonDisplay - Security Tests', () => {
  it('should safely handle potentially malicious JSON strings', () => {
    const maliciousInputs = [
      { result: '{"__proto__":{"polluted":true}}' },
      { result: '{"constructor":{"prototype":{"polluted":true}}}' },
      { result: '<script>alert("xss")</script>' },
    ];
    
    maliciousInputs.forEach(input => {
      // Should not throw errors and should safely render
      expect(() => {
        render(<JsonDisplay data={input} />);
      }).not.toThrow();
    });
  });
  
  it('should handle extremely large JSON strings without crashing', () => {
    const largeArray = Array.from({ length: 1000 }, (_, i) => ({
      id: i,
      data: `Item ${i}`,
    }));
    
    const mcpResult = {
      result: JSON.stringify(largeArray)
    };
    
    // Should render without crashing (may be slow, but shouldn't error)
    expect(() => {
      render(<JsonDisplay data={mcpResult} />);
    }).not.toThrow();
  });
});

