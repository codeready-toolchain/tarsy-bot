import { memo } from 'react';
import { Box, Typography, Chip } from '@mui/material';
import type { MCPInteraction } from '../types';

interface MCPInteractionPreviewProps {
  interaction: MCPInteraction;
  showFullPreview?: boolean;
}

/**
 * MCPInteractionPreview component
 * Shows preview of MCP interactions - tool list count or tool call details
 */
function MCPInteractionPreview({ 
  interaction
}: MCPInteractionPreviewProps) {

  const getToolListPreview = (): { count: number; examples: string[] } => {
    if (!interaction.available_tools) {
      return { count: 0, examples: [] };
    }

    // Count total tools across all servers
    let totalCount = 0;
    const examples: string[] = [];

          Object.entries(interaction.available_tools).forEach(([, tools]) => {
      if (Array.isArray(tools)) {
        totalCount += tools.length;
        // Get first few tool names as examples
        tools.slice(0, 3).forEach(tool => {
          if (tool && typeof tool === 'object' && tool.name) {
            examples.push(tool.name);
          }
        });
      }
    });

    return { count: totalCount, examples: examples.slice(0, 5) };
  };

  const formatToolParameters = (params: Record<string, any>): string => {
    if (!params || Object.keys(params).length === 0) {
      return 'No parameters';
    }

    // Show key parameter names and types
    const paramEntries = Object.entries(params).slice(0, 3);
    const formatted = paramEntries.map(([key, value]) => {
      if (typeof value === 'string' && value.length > 30) {
        return `${key}: "${value.substring(0, 30)}..."`;
      }
      if (typeof value === 'object') {
        return `${key}: {...}`;
      }
      return `${key}: ${value}`;
    });

    const hasMore = Object.keys(params).length > 3;
    return formatted.join(', ') + (hasMore ? ', ...' : '');
  };

  const isToolCall = interaction.communication_type === 'tool_call' && interaction.tool_name && interaction.tool_name !== 'list_tools';
  const isToolList = interaction.communication_type === 'tool_list' || (interaction.communication_type === 'tool_call' && interaction.tool_name === 'list_tools');

  return (
    <Box sx={{ fontSize: '0.875rem' }}>
      {/* MCP Server Badge */}
      <Box sx={{ mb: 1 }}>
        <Chip
          label={interaction.server_name}
          size="small"
          variant="outlined"
          sx={{
            fontSize: '0.7rem',
            height: '20px',
            borderColor: interaction.success ? 'success.main' : 'error.main',
            color: interaction.success ? 'success.main' : 'error.main',
            '& .MuiChip-label': {
              px: 0.75
            }
          }}
        />
      </Box>

      {/* Tool List Preview */}
      {isToolList && (
        <Box>
          <Typography variant="caption" sx={{ 
            fontWeight: 600, 
            color: 'info.main',
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
          }}>
            Tool Discovery
          </Typography>
          
          {(() => {
            const { count, examples } = getToolListPreview();
            return (
              <Box sx={{ 
                mt: 0.5,
                p: 0.75,
                bgcolor: 'grey.50',
                borderRadius: 1,
                border: 1,
                borderColor: 'divider'
              }}>
                <Typography variant="body2" sx={{ 
                  fontSize: '0.75rem',
                  color: 'text.primary',
                  fontWeight: 600
                }}>
                  {count} tools available
                </Typography>
                {examples.length > 0 && (
                  <Typography variant="body2" sx={{ 
                    fontSize: '0.7rem',
                    color: 'text.secondary',
                    mt: 0.25,
                    fontStyle: 'italic'
                  }}>
                    {examples.join(', ')}
                    {count > examples.length && ', ...'}
                  </Typography>
                )}
              </Box>
            );
          })()}
        </Box>
      )}

      {/* Tool Call Preview */}
      {isToolCall && (
        <Box>
          <Typography variant="caption" sx={{ 
            fontWeight: 600, 
            color: 'secondary.main',
            textTransform: 'uppercase',
            letterSpacing: '0.5px'
          }}>
            Tool Call
          </Typography>
          
          <Box sx={{ 
            mt: 0.5,
            p: 0.75,
            bgcolor: 'grey.50',
            borderRadius: 1,
            border: 1,
            borderColor: 'divider'
          }}>
            <Typography variant="body2" sx={{ 
              fontFamily: 'monospace',
              fontSize: '0.75rem',
              color: 'text.primary',
              fontWeight: 600,
              lineHeight: 1.3
            }}>
              {interaction.tool_name}
            </Typography>
            
            {interaction.parameters && Object.keys(interaction.parameters).length > 0 && (
              <Typography variant="body2" sx={{ 
                fontFamily: 'monospace',
                fontSize: '0.7rem',
                color: 'text.secondary',
                mt: 0.25,
                fontStyle: 'italic',
                lineHeight: 1.3
              }}>
                {formatToolParameters(interaction.parameters)}
              </Typography>
            )}
          </Box>
        </Box>
      )}

      {/* Execution Time removed in EP-0010 */}
    </Box>
  );
}

export default memo(MCPInteractionPreview);