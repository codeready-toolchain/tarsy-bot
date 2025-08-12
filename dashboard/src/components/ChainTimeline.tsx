import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  Divider,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Badge,
} from '@mui/material';
import {
  ExpandMore,
  CheckCircle,
  Error,
  Schedule,
  PlayArrow,
  Psychology,
  Build,
  Timeline as TimelineIcon,
} from '@mui/icons-material';
import type { ChainTimelineProps, TimelineItem } from '../types';
import { formatTimestamp, formatDurationMs } from '../utils/timestamp';
import InteractionDetails from './InteractionDetails';

// Helper function to get stage status icon
const getStageStatusIcon = (status: string) => {
  switch (status) {
    case 'completed':
      return <CheckCircle color="success" />;
    case 'failed':
      return <Error color="error" />;
    case 'active':
      return <PlayArrow color="primary" />;
    case 'pending':
    default:
      return <Schedule color="disabled" />;
  }
};

// Helper function to get stage status color
const getStageStatusColor = (status: string): 'success' | 'error' | 'primary' | 'default' => {
  switch (status) {
    case 'completed':
      return 'success';
    case 'failed':
      return 'error';
    case 'active':
      return 'primary';
    case 'pending':
    default:
      return 'default';
  }
};

// Helper function to get interaction type icon
const getInteractionIcon = (type: string) => {
  switch (type) {
    case 'llm':
    case 'llm_interaction':
      return <Psychology fontSize="small" />;
    case 'mcp':
    case 'mcp_communication':
      return <Build fontSize="small" />;
    default:
      return <TimelineIcon fontSize="small" />;
  }
};

// Group timeline items by stage
const groupTimelineByStage = (timelineItems: TimelineItem[], stages: any[]) => {
  const stageMap = new Map();
  
  // Initialize stages
  stages.forEach(stage => {
    stageMap.set(stage.execution_id, {
      stage,
      interactions: [],
    });
  });
  
  // Group interactions by stage
  timelineItems.forEach(item => {
    if (item.stage_execution_id && stageMap.has(item.stage_execution_id)) {
      stageMap.get(item.stage_execution_id).interactions.push(item);
    }
  });
  
  // Sort stages by stage_index
  return Array.from(stageMap.values()).sort((a, b) => 
    a.stage.stage_index - b.stage.stage_index
  );
};

const ChainTimeline: React.FC<ChainTimelineProps> = ({
  chainExecution,
  timelineItems,
  expandedStages = [],
  onStageToggle,
}) => {
  const [localExpandedStages, setLocalExpandedStages] = useState<Set<string>>(
    new Set(expandedStages)
  );

  const handleStageToggle = (stageId: string) => {
    if (onStageToggle) {
      onStageToggle(stageId);
    } else {
      const newExpanded = new Set(localExpandedStages);
      if (newExpanded.has(stageId)) {
        newExpanded.delete(stageId);
      } else {
        newExpanded.add(stageId);
      }
      setLocalExpandedStages(newExpanded);
    }
  };

  const isStageExpanded = (stageId: string) => {
    return onStageToggle 
      ? expandedStages.includes(stageId)
      : localExpandedStages.has(stageId);
  };

  const groupedTimeline = groupTimelineByStage(timelineItems, chainExecution.stages);
  const ungroupedItems = timelineItems.filter(item => !item.stage_execution_id);

  return (
    <Box>
      {/* Chain overview */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            Chain: {chainExecution.chain_id}
          </Typography>
          <Box display="flex" gap={2} flexWrap="wrap">
            <Chip 
              label={`${chainExecution.stages.length} stages`} 
              color="primary" 
              variant="outlined" 
            />
            <Chip 
              label={`${chainExecution.stages.filter(s => s.status === 'completed').length} completed`} 
              color="success" 
              variant="outlined" 
            />
            <Chip 
              label={`${chainExecution.stages.filter(s => s.status === 'failed').length} failed`} 
              color="error" 
              variant="outlined" 
            />
            {chainExecution.current_stage_index !== null && (
              <Chip 
                label={`Current: Stage ${chainExecution.current_stage_index + 1}`} 
                color="primary" 
              />
            )}
          </Box>
        </CardContent>
      </Card>

      {/* Stage-by-stage timeline */}
      <Typography variant="h6" gutterBottom>
        Stage Execution Timeline
      </Typography>
      
      {groupedTimeline.map(({ stage, interactions }) => (
        <Accordion
          key={stage.execution_id}
          expanded={isStageExpanded(stage.execution_id)}
          onChange={() => handleStageToggle(stage.execution_id)}
          sx={{ 
            mb: 2,
            '&:before': { display: 'none' },
            boxShadow: 1,
          }}
        >
          <AccordionSummary expandIcon={<ExpandMore />}>
            <Box display="flex" alignItems="center" gap={2} width="100%">
              <Box display="flex" alignItems="center" gap={1}>
                {getStageStatusIcon(stage.status)}
                <Typography variant="subtitle1" fontWeight={600}>
                  Stage {stage.stage_index + 1}: {stage.stage_name}
                </Typography>
              </Box>
              
              <Box flex={1} />
              
              <Box display="flex" gap={1} alignItems="center">
                <Chip
                  label={stage.status}
                  color={getStageStatusColor(stage.status)}
                  size="small"
                />
                <Chip
                  label={stage.agent}
                  variant="outlined"
                  size="small"
                />
                {interactions.length > 0 && (
                  <Badge badgeContent={interactions.length} color="primary">
                    <TimelineIcon fontSize="small" />
                  </Badge>
                )}
              </Box>
            </Box>
          </AccordionSummary>
          
          <AccordionDetails>
            {/* Stage metadata */}
            <Box mb={2}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                <strong>Agent:</strong> {stage.agent}
                {stage.iteration_strategy && (
                  <>
                    {' | '}
                    <strong>Strategy:</strong> {stage.iteration_strategy}
                  </>
                )}
              </Typography>
              
              {stage.started_at_us && (
                <Typography variant="body2" color="text.secondary">
                  <strong>Started:</strong> {formatTimestamp(stage.started_at_us)}
                  {stage.completed_at_us && (
                    <>
                      {' | '}
                      <strong>Completed:</strong> {formatTimestamp(stage.completed_at_us)}
                    </>
                  )}
                  {stage.duration_ms && (
                    <>
                      {' | '}
                      <strong>Duration:</strong> {formatDurationMs(stage.duration_ms)}
                    </>
                  )}
                </Typography>
              )}
              
              {stage.error_message && (
                <Typography
                  variant="body2"
                  color="error"
                  sx={{
                    mt: 1,
                    p: 1,
                    backgroundColor: 'error.light',
                    borderRadius: 1,
                    opacity: 0.8,
                  }}
                >
                  <strong>Error:</strong> {stage.error_message}
                </Typography>
              )}
            </Box>
            
            <Divider sx={{ mb: 2 }} />
            
            {/* Stage interactions */}
            {interactions.length > 0 ? (
              <>
                <Typography variant="subtitle2" gutterBottom>
                  LLM & MCP Interactions ({interactions.length})
                </Typography>
                <List dense sx={{ pt: 0 }}>
                  {interactions
                    .sort((a, b) => a.timestamp_us - b.timestamp_us)
                    .map((item, index) => (
                      <ListItem 
                        key={item.event_id || index}
                        sx={{ 
                          pl: 0,
                          mb: 1,
                          backgroundColor: 'grey.50',
                          borderRadius: 1,
                        }}
                      >
                        <ListItemIcon sx={{ minWidth: 36 }}>
                          {getInteractionIcon(item.type)}
                        </ListItemIcon>
                        <ListItemText
                          primary={
                            <Box display="flex" justifyContent="space-between" alignItems="center">
                              <Typography variant="body2">
                                {item.step_description}
                              </Typography>
                              <Typography variant="caption" color="text.secondary">
                                {formatTimestamp(item.timestamp_us)}
                              </Typography>
                            </Box>
                          }
                          secondary={
                            item.duration_ms && (
                              <Typography variant="caption" color="text.secondary">
                                Duration: {formatDurationMs(item.duration_ms)}
                              </Typography>
                            )
                          }
                        />
                      </ListItem>
                    ))}
                </List>
              </>
            ) : (
              <Typography variant="body2" color="text.secondary" fontStyle="italic">
                No interactions recorded for this stage
              </Typography>
            )}
          </AccordionDetails>
        </Accordion>
      ))}
      
      {/* Ungrouped interactions (if any) */}
      {ungroupedItems.length > 0 && (
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" gutterBottom>
              Other Interactions
            </Typography>
            <List dense>
              {ungroupedItems
                .sort((a, b) => a.timestamp_us - b.timestamp_us)
                .map((item, index) => (
                  <ListItem key={item.event_id || index} sx={{ pl: 0 }}>
                    <ListItemIcon sx={{ minWidth: 36 }}>
                      {getInteractionIcon(item.type)}
                    </ListItemIcon>
                    <ListItemText
                      primary={
                        <Box display="flex" justifyContent="space-between" alignItems="center">
                          <Typography variant="body2">
                            {item.step_description}
                          </Typography>
                          <Typography variant="caption" color="text.secondary">
                            {formatTimestamp(item.timestamp_us)}
                          </Typography>
                        </Box>
                      }
                      secondary={
                        item.duration_ms && (
                          <Typography variant="caption" color="text.secondary">
                            Duration: {formatDurationMs(item.duration_ms)}
                          </Typography>
                        )
                      }
                    />
                  </ListItem>
                ))}
            </List>
          </CardContent>
        </Card>
      )}
    </Box>
  );
};

export default ChainTimeline;