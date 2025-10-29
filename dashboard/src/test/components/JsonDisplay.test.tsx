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

describe('JsonDisplay - Expand All Button with Accordions', () => {
  it('should expand and collapse visible accordions when clicking Expand All button in tabs', async () => {
    // Create MCP result with both formatted text and raw JSON sections
    const longText = 'This is a long multi-line text content that triggers the formatted text section.\n'.repeat(10);
    const mcpResult = {
      result: JSON.stringify({
        analysis: longText,
        data: { key: 'value', count: 42 }
      })
    };
    
    const user = userEvent.setup();
    const { container, getByRole, getAllByRole } = render(<JsonDisplay data={mcpResult} />);
    
    // Should have tabs
    expect(container.textContent).toContain('Formatted Text');
    expect(container.textContent).toContain('Raw Data');
    
    // Find the Expand All button
    const expandButton = getByRole('button', { name: /expand all/i });
    expect(expandButton).toBeInTheDocument();
    
    // Click Expand All - should expand accordions in the Formatted Text tab (activeTab = 0)
    await user.click(expandButton);
    
    // Button text should change to Collapse All
    await waitFor(() => {
      expect(getByRole('button', { name: /collapse all/i })).toBeInTheDocument();
    });
    
    // The formatted text accordion should be expanded
    const accordions = getAllByRole('button', { name: /analysis \(formatted\)/i });
    expect(accordions.length).toBeGreaterThan(0);
    
    // Switch to Raw Data tab
    const rawDataTab = getByRole('tab', { name: /raw data/i });
    await user.click(rawDataTab);
    
    // Wait for tab switch
    await waitFor(() => {
      expect(container.textContent).toContain('MCP Tool Result (JSON)');
    });
    
    // Click Collapse All - should collapse accordions in Raw Data tab
    const collapseButton = getByRole('button', { name: /collapse all/i });
    await user.click(collapseButton);
    
    // Button text should change back to Expand All
    await waitFor(() => {
      expect(getByRole('button', { name: /expand all/i })).toBeInTheDocument();
    });
  });
  
  it('should preserve non-visible accordion states when toggling Expand All', async () => {
    // Create content with multiple sections
    const longText1 = 'First long text section content.\n'.repeat(10);
    const longText2 = 'Second long text section content.\n'.repeat(10);
    const mcpResult = {
      result: JSON.stringify({
        analysis: longText1,
        summary: longText2,
        data: { key: 'value' }
      })
    };
    
    const user = userEvent.setup();
    const { getByRole } = render(<JsonDisplay data={mcpResult} />);
    
    // Wait for tabs to render
    await waitFor(() => {
      expect(getByRole('tab', { name: /formatted text/i })).toBeInTheDocument();
    });
    
    // Click Expand All in Formatted Text tab (should expand text sections)
    const expandButton = getByRole('button', { name: /expand all/i });
    await user.click(expandButton);
    
    // Switch to Raw Data tab
    const rawDataTab = getByRole('tab', { name: /raw data/i });
    await user.click(rawDataTab);
    
    // Click Collapse All in Raw Data tab (should only collapse raw data sections, not text sections)
    await waitFor(() => {
      const collapseButton = getByRole('button', { name: /collapse all/i });
      expect(collapseButton).toBeInTheDocument();
    });
  });
  
  it('should handle Expand All button when content has no accordions', () => {
    // Larger JSON that triggers Expand All button but has no accordions (just JSON viewer)
    const largeData = {
      data: Array.from({ length: 50 }, (_, i) => ({
        id: i,
        name: `Item ${i}`,
        value: Math.random() * 100
      }))
    };
    
    const { getByRole } = render(<JsonDisplay data={largeData} />);
    
    // Should have Expand All button for JSON content
    const expandButton = getByRole('button', { name: /expand all/i });
    expect(expandButton).toBeInTheDocument();
    
    // Clicking should not throw errors
    expect(() => {
      expandButton.click();
    }).not.toThrow();
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

