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
} from '@mui/material';
import {
  ExpandMore,
  CheckCircle,
  Error as ErrorIcon,
  Schedule,
  PlayArrow,
  Psychology,
  Build,
  Timeline as TimelineIcon,
} from '@mui/icons-material';
import type { ChainTimelineProps, StageExecution } from '../types';
import { formatTimestamp, formatDurationMs } from '../utils/timestamp';

// Helper function to get stage status icon
const getStageStatusIcon = (status: string) => {
  switch (status) {
    case 'completed':
      return <CheckCircle color="success" />;
    case 'failed':
      return <ErrorIcon color="error" />;
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

// Simplified: Stages now contain their own timelines
const prepareStagesWithTimelines = (stages: StageExecution[]) => {
  return [...stages]
    .sort((a, b) => a.stage_index - b.stage_index)
    .map(stage => ({
      stage,
             interactions: [...(stage.llm_interactions || []), ...(stage.mcp_communications || [])].sort((a, b) => a.timestamp_us - b.timestamp_us)
    }));
};

const ChainTimeline: React.FC<ChainTimelineProps> = ({
  chainExecution,
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

  const groupedTimeline = prepareStagesWithTimelines(chainExecution.stages);

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
              
              <Box display="flex" gap={1} alignItems="center" flexWrap="wrap">
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
                
                {/* Interaction count badges similar to session summary */}
                {stage.total_interactions > 0 && (
                  <Box display="flex" gap={0.5} alignItems="center">
                    {/* Total interactions badge */}
                    <Box sx={{ 
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.25,
                      px: 0.75,
                      py: 0.25,
                      backgroundColor: 'grey.100',
                      borderRadius: '12px',
                      border: '1px solid',
                      borderColor: 'grey.300'
                    }}>
                      <Typography variant="caption" sx={{ fontWeight: 600, fontSize: '0.7rem' }}>
                        {stage.total_interactions}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>
                        total
                      </Typography>
                    </Box>
                    
                    {/* LLM interactions badge */}
                    {stage.llm_interaction_count > 0 && (
                      <Box sx={{ 
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.25,
                        px: 0.75,
                        py: 0.25,
                        backgroundColor: 'primary.50',
                        borderRadius: '12px',
                        border: '1px solid',
                        borderColor: 'primary.200'
                      }}>
                        <Typography variant="caption" sx={{ fontWeight: 600, color: 'primary.main', fontSize: '0.7rem' }}>
                          🧠 {stage.llm_interaction_count}
                        </Typography>
                        <Typography variant="caption" color="primary.main" sx={{ fontSize: '0.65rem' }}>
                          LLM
                        </Typography>
                      </Box>
                    )}
                    
                    {/* MCP interactions badge */}
                    {stage.mcp_communication_count > 0 && (
                      <Box sx={{ 
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.25,
                        px: 0.75,
                        py: 0.25,
                        backgroundColor: 'secondary.50',
                        borderRadius: '12px',
                        border: '1px solid',
                        borderColor: 'secondary.200'
                      }}>
                        <Typography variant="caption" sx={{ fontWeight: 600, color: 'secondary.main', fontSize: '0.7rem' }}>
                          🔧 {stage.mcp_communication_count}
                        </Typography>
                        <Typography variant="caption" color="secondary.main" sx={{ fontSize: '0.65rem' }}>
                          MCP
                        </Typography>
                      </Box>
                    )}
                  </Box>
                )}
              </Box>
            </Box>
          </AccordionSummary>
          
          <AccordionDetails>
            {/* Stage metadata */}
            <Box mb={2}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                <strong>Agent:</strong> {stage.agent}
                {/* iteration_strategy removed in EP-0010 */}
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

    </Box>
  );
};

export default ChainTimeline;