import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ThemeProvider } from '@mui/material/styles'
import { createTheme } from '@mui/material/styles'
import InteractionDetails from '../../components/InteractionDetails'
import type { MCPInteraction, LLMInteraction } from '../../types'

// Mock the CopyButton component to avoid clipboard API issues in tests
vi.mock('../../components/CopyButton', () => ({
  default: ({ text, tooltip }: { text: string; tooltip: string }) => (
    <button data-testid="copy-button" title={tooltip}>
      Copy ({text ? text.length : 0} chars)
    </button>
  )
}))

// Mock JsonDisplay component
vi.mock('../../components/JsonDisplay', () => ({
  default: ({ data }: { data: any }) => (
    <div data-testid="json-display">
      {JSON.stringify(data)}
    </div>
  )
}))

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

describe('InteractionDetails - MCP Error Handling', () => {
  const mockFailedMCPInteraction: MCPInteraction = {
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

  const mockSuccessfulMCPInteraction: MCPInteraction = {
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

  it('displays MCP error message prominently when interaction fails', () => {
    renderWithTheme(
      <InteractionDetails 
        type="mcp" 
        details={mockFailedMCPInteraction} 
        expanded={true} 
      />
    )

    // Should show MCP Error badge
    expect(screen.getByText('MCP Error')).toBeInTheDocument()
    
    // Should show the full error message
    const errorMessage = screen.getByText(/Failed to call tool unhealthyApplications/)
    expect(errorMessage).toBeInTheDocument()
    expect(errorMessage.textContent).toContain('net/http: invalid header field value')
    expect(errorMessage.textContent).toContain('Authorization')
    
    // Should have copy button for error message
    const copyButton = screen.getByTitle('Copy error message')
    expect(copyButton).toBeInTheDocument()
    
    // Error should be displayed before other content
    const errorSection = screen.getByText('MCP Error').closest('div')
    const toolCallSection = screen.queryByText('Tool Call')?.closest('div')
    
    if (errorSection && toolCallSection) {
      // Error section should come first in DOM order
      expect(errorSection.compareDocumentPosition(toolCallSection)).toBe(
        Node.DOCUMENT_POSITION_FOLLOWING
      )
    }
  })

  it('does not display error section for successful MCP interaction', () => {
    renderWithTheme(
      <InteractionDetails 
        type="mcp" 
        details={mockSuccessfulMCPInteraction} 
        expanded={true} 
      />
    )

    // Should not show MCP Error badge
    expect(screen.queryByText('MCP Error')).not.toBeInTheDocument()
    
    // Should show successful tool call section
    expect(screen.getByText('Tool Call')).toBeInTheDocument()
    expect(screen.getByText('kubectl_get_pods')).toBeInTheDocument()
  })

  it('handles null error message for failed interaction', () => {
    const failedWithNullError: MCPInteraction = {
      ...mockFailedMCPInteraction,
      error_message: null
    }

    renderWithTheme(
      <InteractionDetails 
        type="mcp" 
        details={failedWithNullError} 
        expanded={true} 
      />
    )

    // Should still show MCP Error badge
    expect(screen.getByText('MCP Error')).toBeInTheDocument()
    
    // Should show fallback error message
    expect(screen.getByText('MCP tool call failed - no response received')).toBeInTheDocument()
    
    // Copy button should have fallback text
    const copyButton = screen.getByTitle('Copy error message')
    expect(copyButton).toBeInTheDocument()
  })

  it('displays tool information section with server name', () => {
    renderWithTheme(
      <InteractionDetails 
        type="mcp" 
        details={mockFailedMCPInteraction} 
        expanded={true} 
      />
    )

    // Should show tool information section
    expect(screen.getByText('Tool Information')).toBeInTheDocument()
    expect(screen.getByText('argocd-server')).toBeInTheDocument()
  })

  it('provides copy functionality for complete interaction details', () => {
    renderWithTheme(
      <InteractionDetails 
        type="mcp" 
        details={mockFailedMCPInteraction} 
        expanded={true} 
      />
    )

    // Should have copy buttons for formatted and raw text (using mock implementation)
    expect(screen.getByTitle('Copy all interaction details in formatted, human-readable format')).toBeInTheDocument()
    expect(screen.getByTitle('Copy raw interaction data (unformatted)')).toBeInTheDocument()
  })

  it('handles tool list communication type', () => {
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
        ]
      },
      success: true,
      error_message: null,
      duration_ms: 100
    }

    renderWithTheme(
      <InteractionDetails 
        type="mcp" 
        details={toolListInteraction} 
        expanded={true} 
      />
    )

    // Should show Available Tools instead of Result
    expect(screen.getByText('Available Tools')).toBeInTheDocument()
    expect(screen.queryByText('Tool Call')).not.toBeInTheDocument()
    
    // Should show tool count badge
    expect(screen.getByText('2 tools')).toBeInTheDocument()
  })

  it('applies correct styling to error message text', () => {
    renderWithTheme(
      <InteractionDetails 
        type="mcp" 
        details={mockFailedMCPInteraction} 
        expanded={true} 
      />
    )

    const errorMessage = screen.getByText(/Failed to call tool unhealthyApplications/)
    
    // Should have error styling classes applied
    expect(errorMessage).toHaveClass('MuiTypography-root')
    expect(errorMessage).toHaveClass('MuiTypography-body2')
  })
})
