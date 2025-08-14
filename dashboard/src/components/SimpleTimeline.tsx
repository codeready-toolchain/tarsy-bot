import { Paper, Typography, Box, List, ListItem, ListItemText, Avatar } from '@mui/material';
import { Psychology, Build, Settings } from '@mui/icons-material';
import type { SimpleTimelineProps } from '../types';
import { formatTimestamp, formatDurationMs } from '../utils/timestamp';

/**
 * Get icon for interaction type
 */
const getInteractionIcon = (type: string) => {
  switch (type) {
    case 'llm':
      return <Psychology sx={{ fontSize: 18 }} />;
    case 'mcp':
      return <Build sx={{ fontSize: 18 }} />;
    case 'system':
      return <Settings sx={{ fontSize: 18 }} />;
    default:
      return <Settings sx={{ fontSize: 18 }} />;
  }
};

/**
 * Get color for interaction type
 */
const getInteractionColor = (type: string): string => {
  switch (type) {
    case 'llm':
      return '#1976d2'; // primary blue
    case 'mcp':
      return '#9c27b0'; // purple
    case 'system':
      return '#ed6c02'; // orange
    default:
      return '#757575'; // grey
  }
};

/**
 * Format duration in milliseconds
 */
const formatDuration = (durationMs: number | null): string => {
  if (!durationMs) return '';
  return formatDurationMs(durationMs);
};

/**
 * SimpleTimeline component - Phase 3
 * Displays chronological timeline of processing events with timestamps and durations
 */
function SimpleTimeline({ timelineItems }: SimpleTimelineProps) {
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
      <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
        Processing Timeline
      </Typography>
      
      <List sx={{ pt: 1 }}>
        {timelineItems.map((item, index) => (
          <ListItem 
            key={item.event_id || index} 
            sx={{ 
              alignItems: 'flex-start',
              pl: 0,
              pb: index === timelineItems.length - 1 ? 0 : 2,
              position: 'relative',
              // Timeline connector line
              ...(index < timelineItems.length - 1 && {
                '&::after': {
                  content: '""',
                  position: 'absolute',
                  left: '19px', // Center of the avatar
                  top: '48px',
                  bottom: '-8px',
                  width: '2px',
                  backgroundColor: 'divider',
                  zIndex: 0,
                }
              })
            }}
          >
            {/* Timeline Icon */}
            <Avatar 
              sx={{ 
                width: 38, 
                height: 38, 
                mr: 2, 
                mt: 0.5,
                backgroundColor: getInteractionColor(item.type),
                zIndex: 1,
              }}
            >
              {getInteractionIcon(item.type)}
            </Avatar>

            {/* Timeline Content */}
            <ListItemText
              sx={{ m: 0 }}
              primary={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                  <Typography variant="subtitle1" sx={{ fontWeight: 500 }}>
                    {item.step_description}
                  </Typography>
                  {item.duration_ms && (
                    <Typography variant="caption" color="text.secondary" sx={{ 
                      backgroundColor: 'grey.100', 
                      px: 1, 
                      py: 0.25, 
                      borderRadius: 1,
                      fontWeight: 500 
                    }}>
                      {formatDuration(item.duration_ms)}
                    </Typography>
                  )}
                </Box>
              }
              secondary={
                <Box component="div">
                  <Typography variant="caption" color="text.secondary" component="span" sx={{ fontWeight: 500, display: 'block' }}>
                    {formatTimestamp(item.timestamp_us, 'time-only')} • {item.type.toUpperCase()}
                  </Typography>
                  {item.details && (
                    <Typography variant="body2" color="text.secondary" component="div" sx={{ mt: 0.5, fontStyle: 'italic' }}>
                      {item.type === 'llm' && 'details' in item.details && 
                        `Model: ${(item.details as any).model_name || 'Unknown'}`
                      }
                      {item.type === 'mcp' && 'details' in item.details && 
                        `Tool: ${(item.details as any).tool_name || 'Unknown'}`
                      }
                      {item.type === 'system' && 'details' in item.details && 
                        `Event: ${(item.details as any).event_type || 'Unknown'}`
                      }
                    </Typography>
                  )}
                </Box>
              }
              secondaryTypographyProps={{
                component: 'div',
                variant: 'body2'
              }}
            />
          </ListItem>
        ))}
      </List>
      
      <Box sx={{ mt: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
        <Typography variant="body2" color="text.secondary">
          Timeline shows {timelineItems.length} interaction{timelineItems.length !== 1 ? 's' : ''} in chronological order
        </Typography>
      </Box>
    </Paper>
  );
}

export default SimpleTimeline; 