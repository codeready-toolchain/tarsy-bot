import { useState } from 'react';
import {
  Box,
  Typography,
  Collapse,
  IconButton,
  alpha,
  useTheme
} from '@mui/material';
import {
  ExpandMore,
  ExpandLess,
  CheckCircle,
  Error as ErrorIcon
} from '@mui/icons-material';
import JsonDisplay from './JsonDisplay';
import CopyButton from './CopyButton';
import { formatDurationMs } from '../utils/timestamp';

interface ToolCallBoxProps {
  toolName: string;
  toolArguments: any;
  toolResult: any;
  serverName: string;
  success: boolean;
  errorMessage?: string;
  duration_ms?: number | null;
}

/**
 * ToolCallBox Component
 * Compact expandable box for displaying MCP tool calls
 */
function ToolCallBox({
  toolName,
  toolArguments,
  toolResult,
  serverName,
  success,
  errorMessage,
  duration_ms
}: ToolCallBoxProps) {
  const theme = useTheme();
  const [expanded, setExpanded] = useState(false);

  // Get preview of arguments (first 2-3 keys)
  const getArgumentsPreview = (): string => {
    if (!toolArguments || typeof toolArguments !== 'object') {
      return '';
    }

    const keys = Object.keys(toolArguments);
    if (keys.length === 0) {
      return '(no arguments)';
    }

    const previewKeys = keys.slice(0, 2);
    const preview = previewKeys.map(key => {
      const value = toolArguments[key];
      const valueStr = typeof value === 'string' ? value : JSON.stringify(value);
      const truncated = valueStr.length > 25 ? valueStr.substring(0, 25) + '...' : valueStr;
      return `${key}: ${truncated}`;
    }).join(', ');

    return keys.length > 2 ? `${preview}, ...` : preview;
  };

  const StatusIcon = success ? CheckCircle : ErrorIcon;
  
  // Use blue colors with more presence - professional but visible
  const statusColor = success ? '#1976d2' : '#d32f2f'; // Blue for success, muted red for errors
  const borderColor = success ? '#90caf9' : '#ffb3b3'; // More visible borders - light blue/pink
  const bgColor = success ? '#e3f2fd' : '#ffebee'; // Light blue/pink backgrounds
  const hoverBgColor = success ? '#bbdefb' : '#ffcdd2'; // Slightly darker on hover

  return (
    <Box
      sx={{
        ml: 4,
        my: 1,
        mr: 1, // Small right margin to prevent touching the edge
        border: `2px solid`, // Thicker border for more presence
        borderColor: borderColor,
        borderRadius: 1.5,
        bgcolor: bgColor,
        boxShadow: '0 1px 3px rgba(0,0,0,0.08)' // Slightly stronger shadow
      }}
    >
      {/* Compact header */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          px: 1.5,
          py: 0.75,
          cursor: 'pointer',
          borderRadius: 1.5,
          transition: 'background-color 0.2s ease',
          '&:hover': {
            bgcolor: hoverBgColor // Slightly darker grey on hover
          }
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <StatusIcon sx={{ fontSize: 18, color: statusColor }} />
        <Typography
          variant="body2"
          sx={{
            fontFamily: 'monospace',
            fontWeight: 600,
            fontSize: '0.9rem',
            color: statusColor
          }}
        >
          {toolName}
        </Typography>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ fontSize: '0.8rem', flex: 1, lineHeight: 1.4 }}
        >
          {getArgumentsPreview()}
        </Typography>
        {duration_ms != null && (
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.75rem' }}>
            {formatDurationMs(duration_ms)}
          </Typography>
        )}
        <IconButton size="small" sx={{ p: 0.25 }}>
          {expanded ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
        </IconButton>
      </Box>

      {/* Expandable details */}
      <Collapse in={expanded}>
        <Box sx={{ px: 1.5, pb: 1.5, pt: 0.5, borderTop: 1, borderColor: 'divider' }}>
          {/* Server info */}
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
            Server: {serverName}
          </Typography>

          {/* Error message */}
          {!success && errorMessage && (
            <Box
              sx={{
                mb: 1,
                p: 1,
                bgcolor: '#fff3e0', // Light amber background instead of pink
                borderRadius: 1,
                border: `1px solid #ffccbc` // Soft orange border
              }}
            >
              <Typography variant="caption" sx={{ fontWeight: 600, color: '#e64a19', fontSize: '0.8rem' }}>
                Error: {errorMessage}
              </Typography>
            </Box>
          )}

          {/* Arguments */}
          <Box sx={{ mb: 1 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
              <Typography variant="caption" sx={{ fontWeight: 600, fontSize: '0.75rem' }}>
                Arguments
              </Typography>
              <CopyButton
                text={JSON.stringify(toolArguments, null, 2)}
                variant="icon"
                size="small"
                tooltip="Copy arguments"
              />
            </Box>
            {toolArguments && Object.keys(toolArguments).length > 0 ? (
              <JsonDisplay data={toolArguments} collapsed={1} maxHeight={250} />
            ) : (
              <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                No arguments
              </Typography>
            )}
          </Box>

          {/* Result */}
          <Box>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.5 }}>
              <Typography variant="caption" sx={{ fontWeight: 600, fontSize: '0.75rem' }}>
                Result
              </Typography>
              <CopyButton
                text={typeof toolResult === 'string' ? toolResult : JSON.stringify(toolResult, null, 2)}
                variant="icon"
                size="small"
                tooltip="Copy result"
              />
            </Box>
            {toolResult ? (
              <JsonDisplay data={toolResult} collapsed={1} maxHeight={300} />
            ) : (
              <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                No result
              </Typography>
            )}
          </Box>
        </Box>
      </Collapse>
    </Box>
  );
}

export default ToolCallBox;

