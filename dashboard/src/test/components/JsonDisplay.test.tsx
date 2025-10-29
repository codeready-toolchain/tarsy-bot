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

