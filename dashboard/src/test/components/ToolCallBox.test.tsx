import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ToolCallBox from '../../components/ToolCallBox';

/**
 * Tests for ToolCallBox component
 * 
 * Verifies that simple flat arguments are displayed as a clean list,
 * while complex arguments fall back to JSON display.
 */
describe('ToolCallBox - Argument Display', () => {
  
  it('should display simple flat arguments as a list', async () => {
    const simpleArgs = {
      username: 'testuser',
      resourceName: 'test-resource-123',
      componentName: 'main-component'
    };
    
    const user = userEvent.setup();
    const { container, getByRole } = render(
      <ToolCallBox
        toolName="execute_command"
        toolArguments={simpleArgs}
        toolResult={{ status: 'success' }}
        serverName="test-server"
        success={true}
      />
    );
    
    // Initially collapsed
    expect(container.textContent).toContain('execute_command');
    
    // Click to expand
    const expandButton = getByRole('button');
    await user.click(expandButton);
    
    // Should display arguments as a simple list with proper formatting
    expect(container.textContent).toContain('username:');
    expect(container.textContent).toContain('"testuser"'); // Simple list wraps strings in quotes
    expect(container.textContent).toContain('resourceName:');
    expect(container.textContent).toContain('"test-resource-123"');
    expect(container.textContent).toContain('componentName:');
    expect(container.textContent).toContain('"main-component"');
  });
  
  it('should display complex arguments with nested objects as JSON', async () => {
    const complexArgs = {
      filter: {
        namespace: 'default',
        labels: { app: 'myapp' }
      },
      options: {
        pretty: true
      }
    };
    
    const user = userEvent.setup();
    const { container, getByRole } = render(
      <ToolCallBox
        toolName="kubectl_get"
        toolArguments={complexArgs}
        toolResult={{ items: [] }}
        serverName="kubectl"
        success={true}
      />
    );
    
    // Click to expand
    const expandButton = getByRole('button');
    await user.click(expandButton);
    
    // Should display as JSON (JsonDisplay component should be used, fully expanded)
    // Check for JSON tree structure (react-json-view-lite uses role="tree")
    const jsonTrees = container.querySelectorAll('[role="tree"]');
    expect(jsonTrees.length).toBeGreaterThan(0);
  });
  
  it('should display arguments with small arrays as a list', async () => {
    const argsWithArray = {
      podName: 'test-pod',
      containers: ['container1', 'container2'],
      verbose: true
    };
    
    const user = userEvent.setup();
    const { container, getByRole } = render(
      <ToolCallBox
        toolName="kubectl_logs"
        toolArguments={argsWithArray}
        toolResult={{ logs: 'test logs' }}
        serverName="kubectl"
        success={true}
      />
    );
    
    // Click to expand
    const expandButton = getByRole('button');
    await user.click(expandButton);
    
    // Should display as a simple list (small arrays are allowed)
    expect(container.textContent).toContain('podName:');
    expect(container.textContent).toContain('containers:');
    expect(container.textContent).toContain('container1');
    expect(container.textContent).toContain('container2');
    expect(container.textContent).toContain('verbose:');
    expect(container.textContent).toContain('true');
  });
  
  it('should display arguments with large arrays as JSON', async () => {
    const argsWithLargeArray = {
      podNames: ['pod1', 'pod2', 'pod3', 'pod4', 'pod5', 'pod6', 'pod7']
    };
    
    const user = userEvent.setup();
    const { container, getByRole } = render(
      <ToolCallBox
        toolName="kubectl_delete"
        toolArguments={argsWithLargeArray}
        toolResult={{ deleted: 7 }}
        serverName="kubectl"
        success={true}
      />
    );
    
    // Click to expand
    const expandButton = getByRole('button');
    await user.click(expandButton);
    
    // Should fall back to JSON display for large arrays (fully expanded)
    // Check for JSON tree structure (react-json-view-lite uses role="tree")
    const jsonTrees = container.querySelectorAll('[role="tree"]');
    expect(jsonTrees.length).toBeGreaterThan(0);
  });
  
  it('should handle empty arguments gracefully', async () => {
    const user = userEvent.setup();
    const { container, getByRole } = render(
      <ToolCallBox
        toolName="list_tools"
        toolArguments={{}}
        toolResult={{ tools: [] }}
        serverName="mcp-server"
        success={true}
      />
    );
    
    // Click to expand
    const expandButton = getByRole('button');
    await user.click(expandButton);
    
    // Should show "No arguments"
    expect(container.textContent).toContain('No arguments');
  });
  
  it('should display primitive value types correctly', async () => {
    const mixedArgs = {
      stringValue: 'test',
      numberValue: 42,
      booleanValue: false,
      nullValue: null
    };
    
    const user = userEvent.setup();
    const { container, getByRole } = render(
      <ToolCallBox
        toolName="test_tool"
        toolArguments={mixedArgs}
        toolResult={{ status: 'ok' }}
        serverName="test-server"
        success={true}
      />
    );
    
    // Click to expand
    const expandButton = getByRole('button');
    await user.click(expandButton);
    
    // Should display all primitive types
    expect(container.textContent).toContain('stringValue:');
    expect(container.textContent).toContain('"test"');
    expect(container.textContent).toContain('numberValue:');
    expect(container.textContent).toContain('42');
    expect(container.textContent).toContain('booleanValue:');
    expect(container.textContent).toContain('false');
    expect(container.textContent).toContain('nullValue:');
    expect(container.textContent).toContain('null');
  });
  
  it('should show error state correctly', async () => {
    const user = userEvent.setup();
    const { container, getByRole } = render(
      <ToolCallBox
        toolName="failing_tool"
        toolArguments={{ param: 'value' }}
        toolResult={null}
        serverName="test-server"
        success={false}
        errorMessage="Connection timeout"
      />
    );
    
    // Click to expand
    const expandButton = getByRole('button');
    await user.click(expandButton);
    
    // Should display error message
    expect(container.textContent).toContain('Error: Connection timeout');
  });
  
  it('should be forgiving and not crash on unexpected argument types', async () => {
    const weirdArgs = {
      normalKey: 'value',
      // These would normally cause isSimpleArguments to return false
      weirdKey: new Date() // Non-serializable object
    };
    
    const user = userEvent.setup();
    
    // Should not throw error
    expect(() => {
      const { getByRole } = render(
        <ToolCallBox
          toolName="test_tool"
          toolArguments={weirdArgs}
          toolResult={{ status: 'ok' }}
          serverName="test-server"
          success={true}
        />
      );
      
      // Try to expand
      const expandButton = getByRole('button');
      user.click(expandButton);
    }).not.toThrow();
  });
});

