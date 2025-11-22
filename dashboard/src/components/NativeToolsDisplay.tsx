/**
 * NativeToolsDisplay Component
 * 
 * Displays Google AI native tools configuration and usage.
 * Supports compact view (for timeline preview) and detailed view (for expanded interactions).
 */

import { memo, useMemo } from 'react';
import { Box, Chip, Typography, Accordion, AccordionSummary, AccordionDetails, Stack } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import type { NativeToolsUsage } from '../types';
import { parseNativeToolsUsage, extractResponseContent } from '../utils/nativeToolsParser';
import {
  getToolDisplayName,
  getToolIcon,
  getToolColor,
  getToolBackgroundColor,
  getToolBorderColor,
  isToolUsed,
  getToolUsageCount,
  getEnabledTools,
  getToolUsageSummary,
  TOOL_KEYS
} from '../utils/nativeToolsHelpers';

interface NativeToolsDisplayProps {
  config?: Record<string, boolean> | null;
  responseMetadata?: Record<string, any> | null;
  variant: 'compact' | 'detailed';
  interactionDetails?: any; // Full interaction details for content extraction
}

function NativeToolsDisplay({
  config,
  responseMetadata,
  variant,
  interactionDetails
}: NativeToolsDisplayProps) {
  // Parse tool usage from response metadata
  const toolUsage = useMemo(() => {
    const content = interactionDetails ? extractResponseContent(interactionDetails) : null;
    return parseNativeToolsUsage(responseMetadata, content);
  }, [responseMetadata, interactionDetails]);

  // Get list of enabled tools
  const enabledTools = useMemo(() => getEnabledTools(config), [config]);

  // If no config and no usage, don't render anything
  if (enabledTools.length === 0 && !toolUsage) {
    return null;
  }

  // All tools to display (enabled or used)
  const allTools = useMemo(() => {
    const tools = new Set(enabledTools);
    if (toolUsage) {
      if (toolUsage.google_search) tools.add(TOOL_KEYS.GOOGLE_SEARCH);
      if (toolUsage.code_execution) tools.add(TOOL_KEYS.CODE_EXECUTION);
      if (toolUsage.url_context) tools.add(TOOL_KEYS.URL_CONTEXT);
    }
    return Array.from(tools);
  }, [enabledTools, toolUsage]);

  if (variant === 'compact') {
    return <CompactView tools={allTools} toolUsage={toolUsage} />;
  }

  return <DetailedView tools={allTools} toolUsage={toolUsage} />;
}

/**
 * Compact view for timeline preview
 */
function CompactView({ 
  tools, 
  toolUsage 
}: { 
  tools: string[]; 
  toolUsage: NativeToolsUsage | null;
}) {
  if (tools.length === 0) {
    return null;
  }

  return (
    <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
      {tools.map(toolKey => {
        const Icon = getToolIcon(toolKey);
        const used = isToolUsed(toolUsage, toolKey);
        const count = getToolUsageCount(toolUsage, toolKey);
        const displayName = getToolDisplayName(toolKey);
        const color = getToolColor(toolKey, used);

        return (
          <Chip
            key={toolKey}
            icon={<Icon sx={{ fontSize: '0.875rem' }} />}
            label={count ? `${displayName} (${count})` : displayName}
            size="small"
            color={color}
            variant={used ? 'filled' : 'outlined'}
            sx={{ 
              fontSize: '0.7rem',
              height: '20px',
              '& .MuiChip-label': {
                px: 0.75
              },
              '& .MuiChip-icon': {
                ml: 0.5
              }
            }}
          />
        );
      })}
    </Box>
  );
}

/**
 * Detailed view for expanded interaction
 */
function DetailedView({
  tools,
  toolUsage
}: {
  tools: string[];
  toolUsage: NativeToolsUsage | null;
}) {
  if (tools.length === 0) {
    return null;
  }

  return (
    <Stack spacing={1.5}>
      {/* Tool badges summary */}
      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center' }}>
        {tools.map(toolKey => {
          const Icon = getToolIcon(toolKey);
          const used = isToolUsed(toolUsage, toolKey);
          const displayName = getToolDisplayName(toolKey);
          const bgColor = getToolBackgroundColor(toolKey, used);
          const borderColor = getToolBorderColor(toolKey, used);

          return (
            <Box
              key={toolKey}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 0.5,
                px: 1.5,
                py: 0.5,
                bgcolor: bgColor,
                border: 1,
                borderColor: borderColor,
                borderRadius: 1,
                fontSize: '0.75rem',
                fontWeight: used ? 600 : 500
              }}
            >
              <Icon sx={{ fontSize: '1rem' }} />
              <Typography variant="caption" sx={{ fontWeight: 'inherit' }}>
                {displayName}
              </Typography>
              {used && (
                <Chip
                  label="Used"
                  size="small"
                  color="success"
                  sx={{ 
                    height: '16px', 
                    fontSize: '0.65rem',
                    '& .MuiChip-label': { px: 0.5 }
                  }}
                />
              )}
            </Box>
          );
        })}
      </Box>

      {/* Detailed usage sections */}
      {toolUsage && (
        <Stack spacing={1}>
          {/* Google Search details */}
          {toolUsage.google_search && (
            <Accordion defaultExpanded sx={{ boxShadow: 'none', border: 1, borderColor: 'divider' }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    Google Search Usage
                  </Typography>
                  <Chip
                    label={getToolUsageSummary(toolUsage, TOOL_KEYS.GOOGLE_SEARCH)}
                    size="small"
                    color="primary"
                    sx={{ height: '20px', fontSize: '0.7rem' }}
                  />
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={1}>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                    Queries:
                  </Typography>
                  {toolUsage.google_search.queries.map((query, idx) => (
                    <Box
                      key={idx}
                      sx={{
                        p: 1,
                        bgcolor: 'grey.50',
                        borderRadius: 1,
                        border: 1,
                        borderColor: 'divider'
                      }}
                    >
                      <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                        {query}
                      </Typography>
                    </Box>
                  ))}
                </Stack>
              </AccordionDetails>
            </Accordion>
          )}

          {/* URL Context details */}
          {toolUsage.url_context && (
            <Accordion defaultExpanded sx={{ boxShadow: 'none', border: 1, borderColor: 'divider' }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    URL Context Usage
                  </Typography>
                  <Chip
                    label={getToolUsageSummary(toolUsage, TOOL_KEYS.URL_CONTEXT)}
                    size="small"
                    color="info"
                    sx={{ height: '20px', fontSize: '0.7rem' }}
                  />
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={1}>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600 }}>
                    URLs:
                  </Typography>
                  {toolUsage.url_context.urls.map((url, idx) => (
                    <Box
                      key={idx}
                      sx={{
                        p: 1,
                        bgcolor: 'grey.50',
                        borderRadius: 1,
                        border: 1,
                        borderColor: 'divider'
                      }}
                    >
                      {url.title && (
                        <Typography variant="body2" sx={{ fontWeight: 600, mb: 0.5 }}>
                          {url.title}
                        </Typography>
                      )}
                      <Typography
                        variant="body2"
                        sx={{
                          fontFamily: 'monospace',
                          fontSize: '0.75rem',
                          color: 'primary.main',
                          wordBreak: 'break-all'
                        }}
                      >
                        {url.uri}
                      </Typography>
                    </Box>
                  ))}
                </Stack>
              </AccordionDetails>
            </Accordion>
          )}

          {/* Code Execution details */}
          {toolUsage.code_execution && (
            <Accordion defaultExpanded sx={{ boxShadow: 'none', border: 1, borderColor: 'divider' }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    Code Execution Usage
                  </Typography>
                  <Chip
                    label={getToolUsageSummary(toolUsage, TOOL_KEYS.CODE_EXECUTION)}
                    size="small"
                    color="secondary"
                    sx={{ height: '20px', fontSize: '0.7rem' }}
                  />
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={1}>
                  <Box sx={{ display: 'flex', gap: 2 }}>
                    <Typography variant="body2" color="text.secondary">
                      <strong>Code Blocks:</strong> {toolUsage.code_execution.code_blocks}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      <strong>Output Blocks:</strong> {toolUsage.code_execution.output_blocks}
                    </Typography>
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                    Python code was executed during response generation
                  </Typography>
                </Stack>
              </AccordionDetails>
            </Accordion>
          )}
        </Stack>
      )}
    </Stack>
  );
}

export default memo(NativeToolsDisplay);

