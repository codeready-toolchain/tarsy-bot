import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ThemeProvider } from '@mui/material/styles'
import { createTheme } from '@mui/material/styles'
import MCPInteractionPreview from '../../components/MCPInteractionPreview'
import type { MCPInteraction } from '../../types'

// Create a test theme
const theme = createTheme()

// Helper to wrap components with theme
const renderWithTheme = (component: React.ReactElement) => {
  return render(
    <ThemeProvider theme={theme}>
      {component}
    </ThemeProvider>
  )
}

describe('MCPInteractionPreview', () => {
  const mockSuccessfulInteraction: MCPInteraction = {
    tool_name: 'kubectl_get_pods',
    server_name: 'kubernetes-server',
    communication_type: 'tool_call',
    tool_arguments: { namespace: 'default' },
    tool_result: { pods: ['nginx-1', 'nginx-2'] },
    available_tools: {},
    success: true,
    error_message: null,
    duration_ms: 1500
  }

  const mockFailedInteraction: MCPInteraction = {
    tool_name: 'unhealthyApplications',
    server_name: 'argocd-server',
    communication_type: 'tool_call',
    tool_arguments: {},
    tool_result: {},
    available_tools: {},
    success: false,
    error_message: 'Failed to call tool unhealthyApplications on argocd-server: Type=McpError | Message=Get "https://argocd.example.com/api/v1/applications": net/http: invalid header field value for "Authorization"',
    duration_ms: 2
  }

  it('renders successful MCP interaction correctly', () => {
    renderWithTheme(
      <MCPInteractionPreview interaction={mockSuccessfulInteraction} />
    )

    // Should show server name
    expect(screen.getByText('kubernetes-server')).toBeInTheDocument()
    
    // Should show successful tool execution
    expect(screen.getByText('Tool Call')).toBeInTheDocument()
    
    // Should show tool name
    expect(screen.getByText('kubectl_get_pods')).toBeInTheDocument()
    
    // Should not show error styling
    expect(screen.queryByText('Failed Tool Call')).not.toBeInTheDocument()
  })

  it('renders failed MCP interaction with error message', () => {
    renderWithTheme(
      <MCPInteractionPreview interaction={mockFailedInteraction} />
    )

    // Should show server name with error styling
    expect(screen.getByText('argocd-server')).toBeInTheDocument()
    
    // Should show failed tool call
    expect(screen.getByText('Failed Tool Call')).toBeInTheDocument()
    
    // Should not show successful tool call text
    expect(screen.queryByText('Tool Call')).not.toBeInTheDocument()
    expect(screen.queryByText('Tool Execution')).not.toBeInTheDocument()
    
    // Should show error message (now with 300 char limit)
    const errorText = screen.getByText(/Failed to call tool unhealthyApplications/)
    expect(errorText).toBeInTheDocument()
    
    // Error message should not be truncated since it's under 300 chars
    expect(errorText.textContent).not.toMatch(/\.\.\.$/)
  })

  it('renders tool list interaction correctly', () => {
    const toolListInteraction: MCPInteraction = {
      tool_name: null,
      server_name: 'test-server',
      communication_type: 'tool_list',
      tool_arguments: {},
      tool_result: {},
      available_tools: {
        'server1': [
          { name: 'tool1', description: 'Tool 1' },
          { name: 'tool2', description: 'Tool 2' }
        ],
        'server2': [
          { name: 'tool3', description: 'Tool 3' }
        ]
      },
      success: true,
      error_message: null,
      duration_ms: 100
    }

    renderWithTheme(
      <MCPInteractionPreview interaction={toolListInteraction} />
    )

    // Should show server name
    expect(screen.getByText('test-server')).toBeInTheDocument()
    
    // Should show tool discovery
    expect(screen.getByText('Tool Discovery')).toBeInTheDocument()
    
    // Should show tool count (3 tools total from fixture)
    expect(screen.getByText('3 tools available')).toBeInTheDocument()
  })

  it('handles error message length correctly', () => {
    const veryLongErrorInteraction: MCPInteraction = {
      ...mockFailedInteraction,
      error_message: 'A'.repeat(650) // Over 600 char limit
    }

    renderWithTheme(
      <MCPInteractionPreview interaction={veryLongErrorInteraction} />
    )

    // Very long error message should be truncated at 600 chars
    const errorText = screen.getByText(new RegExp('A{1,}'))
    expect(errorText).toBeInTheDocument()
    expect(errorText.textContent).toMatch(/\.\.\.$/)
    expect(errorText.textContent!.length).toBeLessThan(650)
  })

  it('handles null error message for failed interaction', () => {
    const failedWithoutMessageInteraction: MCPInteraction = {
      ...mockFailedInteraction,
      error_message: null
    }

    renderWithTheme(
      <MCPInteractionPreview interaction={failedWithoutMessageInteraction} />
    )

    // Should still show failed tool call
    expect(screen.getByText('Failed Tool Call')).toBeInTheDocument()
    
    // For null error message, the component shows "Failed Tool Call" but no error box
    // This is the expected behavior based on our implementation
  })
})
