import { useState } from 'react';
import {
  Box,
  Typography,
  Collapse,
  IconButton,
  alpha
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
 * Check if the arguments are simple (flat key-value pairs with primitive values)
 * Returns true if we can display as a simple list
 */
const isSimpleArguments = (args: any): boolean => {
  if (!args || typeof args !== 'object' || Array.isArray(args)) {
    return false;
  }
  
  const keys = Object.keys(args);
  if (keys.length === 0) {
    return false;
  }
  
  // Check if all values are primitives or simple arrays
  return keys.every(key => {
    const value = args[key];
    const type = typeof value;
    
    // Allow primitives
    if (value === null || type === 'string' || type === 'number' || type === 'boolean') {
      return true;
    }
    
    // Allow arrays only if they're small and contain primitives
    if (Array.isArray(value)) {
      return value.length <= 5 && value.every(item => {
        const itemType = typeof item;
        return item === null || itemType === 'string' || itemType === 'number' || itemType === 'boolean';
      });
    }
    
    // Reject objects and complex types
    return false;
  });
};

/**
 * Render simple arguments as a clean list
 */
const SimpleArgumentsList = ({ args }: { args: any }) => {
  return (
    <Box
      sx={(theme) => ({
        bgcolor: theme.palette.grey[50],
        borderRadius: 1,
        border: `1px solid ${theme.palette.divider}`,
        p: 1.5,
        fontFamily: 'monospace',
        fontSize: '0.875rem'
      })}
    >
      {Object.entries(args).map(([key, value], index) => (
        <Box
          key={key}
          sx={{
            display: 'flex',
            mb: index < Object.keys(args).length - 1 ? 0.75 : 0,
            alignItems: 'flex-start'
          }}
        >
          <Typography
            component="span"
            sx={(theme) => ({
              fontFamily: 'monospace',
              fontSize: '0.875rem',
              fontWeight: 600,
              color: theme.palette.primary.main,
              mr: 1,
              minWidth: '100px',
              flexShrink: 0
            })}
          >
            {key}:
          </Typography>
          <Typography
            component="span"
            sx={(theme) => ({
              fontFamily: 'monospace',
              fontSize: '0.875rem',
              color: theme.palette.text.primary,
              wordBreak: 'break-word',
              whiteSpace: 'pre-wrap'
            })}
          >
            {Array.isArray(value) 
              ? `[${value.map(v => typeof v === 'string' ? `"${v}"` : String(v)).join(', ')}]`
              : typeof value === 'string' 
                ? `"${value}"`
                : String(value)
            }
          </Typography>
        </Box>
      ))}
    </Box>
  );
};

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

  return (
    <Box
      sx={(theme) => ({
        ml: 4,
        my: 1,
        mr: 1, // Small right margin to prevent touching the edge
        border: `2px solid`, // Thicker border for more presence
        borderColor: success
          ? alpha(theme.palette.primary.main, 0.5)
          : alpha(theme.palette.error.main, 0.5),
        borderRadius: 1.5,
        bgcolor: success
          ? alpha(theme.palette.primary.main, 0.08)
          : alpha(theme.palette.error.main, 0.08),
        boxShadow: `0 1px 3px ${alpha(theme.palette.common.black, 0.08)}` // Slightly stronger shadow
      })}
    >
      {/* Compact header */}
      <Box
        sx={(theme) => ({
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          px: 1.5,
          py: 0.75,
          cursor: 'pointer',
          borderRadius: 1.5,
          transition: 'background-color 0.2s ease',
          '&:hover': {
            bgcolor: success
              ? alpha(theme.palette.primary.main, 0.2)
              : alpha(theme.palette.error.main, 0.2)
          }
        })}
        onClick={() => setExpanded(!expanded)}
      >
        <StatusIcon
          sx={(theme) => ({
            fontSize: 18,
            color: success ? theme.palette.primary.main : theme.palette.error.main
          })}
        />
        <Typography
          variant="body2"
          sx={(theme) => ({
            fontFamily: 'monospace',
            fontWeight: 600,
            fontSize: '0.9rem',
            color: success ? theme.palette.primary.main : theme.palette.error.main
          })}
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
              sx={(theme) => ({
                mb: 1,
                p: 1,
                bgcolor: alpha(theme.palette.error.main, 0.1),
                borderRadius: 1,
                border: `1px solid ${alpha(theme.palette.error.main, 0.3)}`
              })}
            >
              <Typography
                variant="caption"
                sx={(theme) => ({
                  fontWeight: 600,
                  color: theme.palette.error.dark,
                  fontSize: '0.8rem'
                })}
              >
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
              isSimpleArguments(toolArguments) ? (
                <SimpleArgumentsList args={toolArguments} />
              ) : (
                <JsonDisplay data={toolArguments} collapsed={false} maxHeight={250} />
              )
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
              <JsonDisplay data={toolResult} collapsed={false} maxHeight={300} />
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

