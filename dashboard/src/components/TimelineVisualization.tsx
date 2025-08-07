import { useState, memo } from 'react';
import { 
  Box, 
  Paper, 
  Typography, 
  Card, 
  CardHeader, 
  CardContent,
  Chip,
  IconButton,
  CircularProgress,
  Avatar
} from '@mui/material';
import { 
  Psychology, 
  Build, 
  Settings, 
  ExpandMore, 
  ExpandLess
} from '@mui/icons-material';
import type { TimelineItem as TimelineItemType } from '../types';
import { formatTimestamp, formatDurationMs } from '../utils/timestamp';
import InteractionDetails from './InteractionDetails';

import CopyButton from './CopyButton';

interface TimelineVisualizationProps {
  timelineItems: TimelineItemType[];
  isActive?: boolean;
  sessionId?: string;
}

/**
 * TimelineVisualization component - Phase 5  
 * Enhanced timeline with Material-UI Timeline components and expandable interactions
 */
function TimelineVisualization({ 
  timelineItems, 
  isActive = false
}: TimelineVisualizationProps) {
  const [expandedItems, setExpandedItems] = useState<Record<string, boolean>>({});

  // Enhanced timeline formatter for human-readable copy - NO TRUNCATION
  const getFormattedTimelineText = (): string => {
    const header = '=== ALERT PROCESSING TIMELINE ===\n\n';
    const summary = `Timeline Overview:\n- Total Steps: ${timelineItems.length}\n- Duration: ${timelineItems.length > 0 ? formatDurationMs((timelineItems[timelineItems.length - 1].timestamp_us - timelineItems[0].timestamp_us) / 1000) : 'N/A'}\n\n`;
    
    const formattedItems = timelineItems.map((item, index) => {
      const timestamp = formatTimestamp(item.timestamp_us, 'absolute');
      const duration = item.duration_ms ? ` (${formatDurationMs(item.duration_ms)})` : '';
      const stepNumber = `STEP ${index + 1}`;
      
      let formatted = `${stepNumber}: ${item.step_description}\n`;
      formatted += `Time: ${timestamp}${duration}\n`;
      formatted += `Type: ${item.type.toUpperCase()}\n`;
      
      // Add detailed information based on interaction type
      if (item.details) {
        formatted += '\nDetails:\n';
        
        switch (item.type) {
          case 'llm':
            const llmDetails = item.details as any;
            if (llmDetails.prompt) {
              // Parse LLM messages if they're in Python format
              const prompt = llmDetails.prompt.trim();
              if (prompt.startsWith('[') && prompt.includes('LLMMessage(') && prompt.includes('role=')) {
                // Parse Python LLMMessage objects
                const messageParts = prompt.split('LLMMessage(').slice(1);
                messageParts.forEach((part: string) => {
                  const roleMatch = part.match(/role='([^']+)'/);
                  if (!roleMatch) return;
                  
                  const role = roleMatch[1];
                  const contentStartMatch = part.match(/content='(.*)$/s);
                  if (!contentStartMatch) return;
                  
                  let rawContent = contentStartMatch[1];
                  let messageContent = '';
                  
                  // Parse content character by character (same logic as InteractionDetails)
                  let i = 0;
                  let escapeNext = false;
                  
                  while (i < rawContent.length) {
                    const char = rawContent[i];
                    
                    if (escapeNext) {
                      messageContent += char;
                      escapeNext = false;
                    } else if (char === '\\') {
                      messageContent += char;
                      escapeNext = true;
                    } else if (char === "'") {
                      const nextChars = rawContent.substring(i + 1, i + 5);
                      if (nextChars.startsWith(')') || nextChars.match(/^,\s*[a-zA-Z_]+=/) || i === rawContent.length - 1) {
                        break;
                      }
                      messageContent += char;
                    } else {
                      messageContent += char;
                    }
                    i++;
                  }
                  
                  // Clean up escaped characters
                  messageContent = messageContent
                    .replace(/\\n/g, '\n')
                    .replace(/\\'/g, "'")
                    .replace(/\\"/g, '"')
                    .replace(/\\\\/g, '\\')
                    .replace(/\\t/g, '\t');
                  
                  // NO TRUNCATION - Full content
                  formatted += `  ${role.toUpperCase()} MESSAGE:\n  ${messageContent.replace(/\n/g, '\n  ')}\n\n`;
                });
              } else {
                // NO TRUNCATION - Full prompt
                formatted += `  PROMPT: ${llmDetails.prompt.replace(/\n/g, '\n  ')}\n`;
              }
              
              if (llmDetails.response) {
                // NO TRUNCATION - Full response
                formatted += `  RESPONSE: ${llmDetails.response.replace(/\n/g, '\n  ')}\n`;
              }
              
              if (llmDetails.model_name) formatted += `  MODEL: ${llmDetails.model_name}\n`;
              if (llmDetails.tokens_used) formatted += `  TOKENS: ${llmDetails.tokens_used}\n`;
              if (llmDetails.temperature !== undefined) formatted += `  TEMPERATURE: ${llmDetails.temperature}\n`;
            }
            break;
            
          case 'mcp':
            const mcpDetails = item.details as any;
            if (mcpDetails.tool_name) formatted += `  TOOL: ${mcpDetails.tool_name}\n`;
            if (mcpDetails.server_name) formatted += `  SERVER: ${mcpDetails.server_name}\n`;
            if (mcpDetails.execution_time_ms) formatted += `  EXECUTION TIME: ${mcpDetails.execution_time_ms}ms\n`;
            
            if (mcpDetails.parameters && Object.keys(mcpDetails.parameters).length > 0) {
              formatted += `  PARAMETERS: ${JSON.stringify(mcpDetails.parameters, null, 2).replace(/\n/g, '\n  ')}\n`;
            }
            
            if (mcpDetails.result) {
              const resultStr = typeof mcpDetails.result === 'string' 
                ? mcpDetails.result 
                : JSON.stringify(mcpDetails.result, null, 2);
              // NO TRUNCATION - Full result
              formatted += `  RESULT: ${resultStr.replace(/\n/g, '\n  ')}\n`;
            }
            break;
            
          case 'system':
            const systemDetails = item.details as any;
            if (systemDetails.description) {
              formatted += `  DESCRIPTION: ${systemDetails.description}\n`;
            }
            if (systemDetails.metadata && Object.keys(systemDetails.metadata).length > 0) {
              formatted += `  METADATA: ${JSON.stringify(systemDetails.metadata, null, 2).replace(/\n/g, '\n  ')}\n`;
            }
            break;
        }
      }
      
      return formatted;
    }).join('\n' + '='.repeat(80) + '\n\n');
    
    const footer = isActive ? '\n[TIMELINE ACTIVE - Processing continues...]\n' : '\n[TIMELINE COMPLETE]\n';
    
    return header + summary + formattedItems + footer;
  };

  const toggleExpansion = (itemId: string) => {
    setExpandedItems(prev => ({
      ...prev,
      [itemId]: !prev[itemId]
    }));
  };

  const getInteractionIcon = (type: string) => {
    switch (type) {
      case 'llm':
        return <Psychology />;
      case 'mcp':
        return <Build />;
      case 'system':
        return <Settings />;
      default:
        return <Settings />;
    }
  };

  const getInteractionColor = (type: string): 'primary' | 'secondary' | 'warning' => {
    switch (type) {
      case 'llm':
        return 'primary';    // Blue
      case 'mcp':
        return 'secondary';  // Purple  
      case 'system':
        return 'warning';    // Orange
      default:  
        return 'primary';
    }
  };



  if (!timelineItems || timelineItems.length === 0) {
    return (
      <Paper sx={{ p: 3 }}>
        <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
          Processing Timeline
        </Typography>
        <Typography variant="body2" color="text.secondary">
          No timeline data available
        </Typography>
      </Paper>
    );
  }

  return (
    <Paper sx={{ p: 3 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          Processing Timeline
        </Typography>
        <CopyButton
          text={getFormattedTimelineText()}
          size="small"
          label="Copy Timeline"
          tooltip="Copy comprehensive timeline with all interaction details (no truncation)"
        />
      </Box>

      {/* Custom Clean Timeline */}
      <Box sx={{ position: 'relative' }}>
        {timelineItems.map((item, index) => {
          const itemKey = item.id || `item-${index}`;
          return (
          <Box key={itemKey} sx={{ display: 'flex', position: 'relative' }}>
            {/* Timeline Line and Dot */}
            <Box sx={{ 
              display: 'flex', 
              flexDirection: 'column', 
              alignItems: 'center',
              mr: 3,
              position: 'relative'
            }}>
              {/* Timeline Dot */}
              <Avatar
                sx={{
                  width: 36,
                  height: 36,
                  bgcolor: `${getInteractionColor(item.type)}.main`,
                  color: 'white',
                  fontSize: '1rem',
                  zIndex: 2
                }}
              >
                {getInteractionIcon(item.type)}
              </Avatar>
              
              {/* Connecting Line */}
              {index < timelineItems.length - 1 && (
                <Box
                  sx={{
                    width: 2,
                    backgroundColor: 'divider',
                    flexGrow: 1,
                    minHeight: 32,
                    mt: 1,
                    mb: 1
                  }}
                />
              )}
            </Box>

            {/* Timeline Content */}
            <Box sx={{ flex: 1, mb: index < timelineItems.length - 1 ? 3 : 0 }}>
              <Card variant="outlined" sx={{ 
                transition: 'all 0.2s ease-in-out',
                '&:hover': {
                  boxShadow: 2,
                  borderColor: `${getInteractionColor(item.type)}.main`
                }
              }}>
                <CardHeader
                  title={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                      <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                        {item.step_description}
                      </Typography>
                      {item.duration_ms && (
                        <Chip 
                          label={formatDurationMs(item.duration_ms)} 
                          size="small" 
                          variant="filled"
                          color={getInteractionColor(item.type)}
                          sx={{ fontSize: '0.75rem', height: 24 }}
                        />
                      )}
                    </Box>
                  }
                  subheader={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
                      <Typography variant="body2" color="text.secondary">
                        {formatTimestamp(item.timestamp_us, 'short')}
                      </Typography>
                      <Typography variant="body2" sx={{ color: `${getInteractionColor(item.type)}.main`, fontWeight: 500 }}>
                        • {item.type.toUpperCase()}
                      </Typography>
                    </Box>
                  }
                  action={
                    item.details && (
                      <IconButton 
                        onClick={() => toggleExpansion(itemKey)}
                        size="small"
                        sx={{ 
                          color: `${getInteractionColor(item.type)}.main`,
                          '&:hover': { bgcolor: `${getInteractionColor(item.type)}.light` }
                        }}
                      >
                        {expandedItems[itemKey] ? <ExpandLess /> : <ExpandMore />}
                      </IconButton>
                    )
                  }
                  sx={{ pb: item.details && !expandedItems[itemKey] ? 2 : 1 }}
                />
                
                {/* Expandable interaction details */}
                {item.details && (
                  <CardContent sx={{ pt: 0 }}>
                    <InteractionDetails
                      type={item.type}
                      details={item.details}
                      expanded={expandedItems[itemKey]}
                    />
                  </CardContent>
                )}
              </Card>
            </Box>
          </Box>
          );
        })}
      </Box>

      {/* Real-time indicator for active sessions */}
      {isActive && (
        <Box sx={{ 
          mt: 2, 
          p: 2, 
          bgcolor: 'info.50', 
          borderRadius: 1, 
          border: 1, 
          borderColor: 'info.200',
          display: 'flex', 
          alignItems: 'center', 
          gap: 1 
        }}>
          <CircularProgress size={16} color="info" />
          <Typography variant="body2" color="info.main" sx={{ fontWeight: 500 }}>
            Waiting for next interaction...
          </Typography>
        </Box>
      )}

      {/* Timeline summary */}
      <Box sx={{ mt: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
        <Typography variant="body2" color="text.secondary">
          Timeline shows {timelineItems.length} interaction{timelineItems.length !== 1 ? 's' : ''} in chronological order
          {isActive && ' • Updates automatically for active sessions'}
        </Typography>
      </Box>
    </Paper>
  );
}

// Custom comparison function for memo to prevent unnecessary re-renders
const arePropsEqual = (prevProps: TimelineVisualizationProps, nextProps: TimelineVisualizationProps) => {
  // Check if timeline items array has the same length and items
  if (prevProps.timelineItems.length !== nextProps.timelineItems.length) {
    return false;
  }
  
  // Check if isActive status changed
  if (prevProps.isActive !== nextProps.isActive) {
    return false;
  }
  
  // For timeline items, we only need to check if new items were added
  // Individual item changes are handled by their own keys in React
  for (let i = 0; i < prevProps.timelineItems.length; i++) {
    if (prevProps.timelineItems[i]?.id !== nextProps.timelineItems[i]?.id) {
      return false;
    }
  }
  
  return true;
};

export default memo(TimelineVisualization, arePropsEqual); 