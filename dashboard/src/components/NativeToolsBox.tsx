import { useState, createElement } from 'react';
import {
  Box,
  Typography,
  Collapse,
  IconButton,
  alpha,
  Chip,
  useTheme
} from '@mui/material';
import {
  ExpandMore,
  ExpandLess,
  AutoFixHigh
} from '@mui/icons-material';
import { getToolIcon, getToolDisplayName } from '../utils/nativeToolsHelpers';
import type { NativeToolsUsage } from '../types';

interface NativeToolsBoxProps {
  usage: NativeToolsUsage;
}

/**
 * NativeToolsBox Component
 * Compact expandable box for displaying Google AI native tools usage
 * Styled similarly to ToolCallBox but with distinct color scheme
 */
function NativeToolsBox({ usage }: NativeToolsBoxProps) {
  const [expanded, setExpanded] = useState(false);
  const theme = useTheme();

  // Determine which tools are used
  const usedTools: Array<{ key: string; name: string }> = [];
  if (usage.google_search) {
    usedTools.push({ key: 'google_search', name: getToolDisplayName('google_search') });
  }
  if (usage.url_context) {
    usedTools.push({ key: 'url_context', name: getToolDisplayName('url_context') });
  }
  if (usage.code_execution) {
    usedTools.push({ key: 'code_execution', name: getToolDisplayName('code_execution') });
  }

  // Get title and icon based on what's used
  const getTitle = (): string => {
    if (usedTools.length === 1) {
      return usedTools[0].name;
    }
    return 'Google AI Tools';
  };

  const getIcon = () => {
    if (usedTools.length === 1) {
      return createElement(getToolIcon(usedTools[0].key));
    }
    return <AutoFixHigh sx={{ fontSize: 18, color: boxColor }} />;
  };

  // Build preview summary
  const getPreviewSummary = (): string => {
    const parts: string[] = [];
    
    if (usage.google_search) {
      parts.push(`${usage.google_search.query_count} ${usage.google_search.query_count === 1 ? 'query' : 'queries'}`);
    }
    if (usage.url_context) {
      parts.push(`${usage.url_context.url_count} ${usage.url_context.url_count === 1 ? 'URL' : 'URLs'}`);
    }
    if (usage.code_execution) {
      parts.push(`${usage.code_execution.code_blocks} code ${usage.code_execution.code_blocks === 1 ? 'block' : 'blocks'}`);
    }

    return parts.join(', ');
  };

  // Color scheme - using info/teal colors to differentiate from tool calls (blue) and success (green)
  const boxColor = theme.palette.info.main;

  return (
    <Box
      sx={{
        ml: 4,
        my: 1,
        mr: 1,
        border: `2px solid`,
        borderColor: alpha(boxColor, 0.5),
        borderRadius: 1.5,
        bgcolor: alpha(boxColor, 0.08),
        boxShadow: `0 1px 3px ${alpha(theme.palette.common.black, 0.08)}`
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
            bgcolor: alpha(boxColor, 0.2)
          }
        }}
        onClick={() => setExpanded(!expanded)}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', color: boxColor, fontSize: 18 }}>
          {getIcon()}
        </Box>
        <Typography
          variant="body2"
          sx={{
            fontFamily: 'monospace',
            fontWeight: 600,
            fontSize: '0.9rem',
            color: boxColor
          }}
        >
          {getTitle()}
        </Typography>
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ fontSize: '0.8rem', flex: 1, lineHeight: 1.4 }}
        >
          {getPreviewSummary()}
        </Typography>
        <IconButton size="small" sx={{ p: 0.25 }}>
          {expanded ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
        </IconButton>
      </Box>

      {/* Expandable details */}
      <Collapse in={expanded}>
        <Box sx={{ px: 1.5, pb: 1.5, pt: 0.5, borderTop: 1, borderColor: 'divider' }}>
          {/* Google Search */}
          {usage.google_search && (
            <Box sx={{ mb: 1.5 }}>
              {/* Only show header if multiple tools are used */}
              {usedTools.length > 1 && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.75 }}>
                  {createElement(getToolIcon('google_search'))}
                  <Typography variant="caption" sx={{ fontWeight: 600, fontSize: '0.85rem' }}>
                    {getToolDisplayName('google_search')}
                  </Typography>
                  <Chip
                    label={`${usage.google_search.query_count} ${usage.google_search.query_count === 1 ? 'query' : 'queries'}`}
                    size="small"
                    sx={{
                      height: 20,
                      fontSize: '0.7rem',
                      bgcolor: alpha(theme.palette.primary.main, 0.1),
                      color: theme.palette.primary.main
                    }}
                  />
                </Box>
              )}
              <Box
                sx={{
                  bgcolor: theme.palette.grey[50],
                  borderRadius: 1,
                  border: `1px solid ${theme.palette.divider}`,
                  p: 1.5
                }}
              >
                {usage.google_search.queries.map((query, idx) => (
                  <Typography
                    key={idx}
                    variant="body2"
                    sx={{
                      fontFamily: 'monospace',
                      fontSize: '0.85rem',
                      mb: idx < usage.google_search!.queries.length - 1 ? 0.75 : 0,
                      color: 'text.primary'
                    }}
                  >
                    {idx + 1}. "{query}"
                  </Typography>
                ))}
              </Box>
            </Box>
          )}

          {/* URL Context */}
          {usage.url_context && (
            <Box sx={{ mb: 1.5 }}>
              {/* Only show header if multiple tools are used */}
              {usedTools.length > 1 && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.75 }}>
                  {createElement(getToolIcon('url_context'))}
                  <Typography variant="caption" sx={{ fontWeight: 600, fontSize: '0.85rem' }}>
                    {getToolDisplayName('url_context')}
                  </Typography>
                  <Chip
                    label={`${usage.url_context.url_count} ${usage.url_context.url_count === 1 ? 'URL' : 'URLs'}`}
                    size="small"
                    sx={{
                      height: 20,
                      fontSize: '0.7rem',
                      bgcolor: alpha(theme.palette.info.main, 0.1),
                      color: theme.palette.info.main
                    }}
                  />
                </Box>
              )}
              <Box
                sx={{
                  bgcolor: theme.palette.grey[50],
                  borderRadius: 1,
                  border: `1px solid ${theme.palette.divider}`,
                  p: 1.5
                }}
              >
                {usage.url_context.urls.map((url, idx) => (
                  <Box
                    key={idx}
                    sx={{
                      mb: idx < usage.url_context!.urls.length - 1 ? 1 : 0
                    }}
                  >
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 600,
                        fontSize: '0.85rem',
                        mb: 0.25,
                        color: 'text.primary'
                      }}
                    >
                      {url.title || 'Untitled'}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{
                        fontFamily: 'monospace',
                        fontSize: '0.75rem',
                        color: 'text.secondary',
                        wordBreak: 'break-all'
                      }}
                    >
                      {url.uri}
                    </Typography>
                  </Box>
                ))}
              </Box>
            </Box>
          )}

          {/* Code Execution */}
          {usage.code_execution && (
            <Box>
              {/* Only show header if multiple tools are used */}
              {usedTools.length > 1 && (
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, mb: 0.75 }}>
                  {createElement(getToolIcon('code_execution'))}
                  <Typography variant="caption" sx={{ fontWeight: 600, fontSize: '0.85rem' }}>
                    {getToolDisplayName('code_execution')}
                  </Typography>
                  <Chip
                    label={`${usage.code_execution.code_blocks} ${usage.code_execution.code_blocks === 1 ? 'block' : 'blocks'}`}
                    size="small"
                    sx={{
                      height: 20,
                      fontSize: '0.7rem',
                      bgcolor: alpha(theme.palette.secondary.main, 0.1),
                      color: theme.palette.secondary.main
                    }}
                  />
                </Box>
              )}
              <Box
                sx={{
                  bgcolor: theme.palette.grey[50],
                  borderRadius: 1,
                  border: `1px solid ${theme.palette.divider}`,
                  p: 1.5
                }}
              >
                <Typography variant="body2" sx={{ fontSize: '0.85rem', color: 'text.primary' }}>
                  Code blocks: {usage.code_execution.code_blocks}
                </Typography>
                <Typography variant="body2" sx={{ fontSize: '0.85rem', color: 'text.primary' }}>
                  Output blocks: {usage.code_execution.output_blocks}
                </Typography>
              </Box>
            </Box>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}

export default NativeToolsBox;

