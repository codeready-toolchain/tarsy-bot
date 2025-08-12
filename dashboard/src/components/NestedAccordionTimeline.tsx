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
  Avatar,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Divider,
  LinearProgress,
  Breadcrumbs,
  Link,
  IconButton,
  Collapse,
} from '@mui/material';
import {
  ExpandMore,
  ExpandLess,
  CheckCircle,
  Error,
  Schedule,
  PlayArrow,
  Psychology,
  Build,
  Timeline as TimelineIcon,
  NavigateNext,
  NavigateBefore,
} from '@mui/icons-material';
import type { ChainExecution, TimelineItem } from '../types';
import { formatTimestamp, formatDurationMs } from '../utils/timestamp';
// InteractionDetails can be added later for detailed modal views

interface NestedAccordionTimelineProps {
  chainExecution: ChainExecution;
  timelineItems: TimelineItem[];
}

// Helper function to get stage status icon
const getStageStatusIcon = (status: string) => {
  switch (status) {
    case 'completed':
      return <CheckCircle fontSize="small" />;
    case 'failed':
      return <Error fontSize="small" />;
    case 'active':
      return <PlayArrow fontSize="small" />;
    case 'pending':
    default:
      return <Schedule fontSize="small" />;
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

const NestedAccordionTimeline: React.FC<NestedAccordionTimelineProps> = ({
  chainExecution,
  timelineItems,
}) => {
  const [expandedStages, setExpandedStages] = useState<Set<string>>(
    new Set([chainExecution.current_stage_index !== null ? chainExecution.stages[chainExecution.current_stage_index]?.execution_id : ''])
  );
  const [currentStageIndex, setCurrentStageIndex] = useState<number>(
    chainExecution.current_stage_index ?? 0
  );
  const [expandedInteractions, setExpandedInteractions] = useState<Set<string>>(new Set());


  const handleStageToggle = (stageId: string, stageIndex: number) => {
    const newExpanded = new Set(expandedStages);
    if (newExpanded.has(stageId)) {
      newExpanded.delete(stageId);
    } else {
      newExpanded.add(stageId);
    }
    setExpandedStages(newExpanded);
    setCurrentStageIndex(stageIndex);
  };

  const navigateToStage = (direction: 'next' | 'prev') => {
    const newIndex = direction === 'next' 
      ? Math.min(currentStageIndex + 1, chainExecution.stages.length - 1)
      : Math.max(currentStageIndex - 1, 0);
    
    setCurrentStageIndex(newIndex);
    const stageId = chainExecution.stages[newIndex].execution_id;
    setExpandedStages(new Set([stageId]));
  };

  const handleInteractionToggle = (eventId: string) => {
    const newExpanded = new Set(expandedInteractions);
    if (newExpanded.has(eventId)) {
      newExpanded.delete(eventId);
    } else {
      newExpanded.add(eventId);
    }
    setExpandedInteractions(newExpanded);
  };

  const getStageInteractions = (stageId: string) =>
    timelineItems
      .filter(item => item.stage_execution_id === stageId)
      .sort((a, b) => a.timestamp_us - b.timestamp_us);

  return (
    <Card>
      {/* Chain Progress Header */}
      <CardContent sx={{ bgcolor: 'grey.50', borderBottom: 1, borderColor: 'divider' }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6" color="primary.main">
            Chain: {chainExecution.chain_id}
          </Typography>
          <Box display="flex" alignItems="center" gap={1}>
            <IconButton 
              size="small" 
              onClick={() => navigateToStage('prev')}
              disabled={currentStageIndex === 0}
            >
              <NavigateBefore />
            </IconButton>
            <Chip 
              label={`Stage ${currentStageIndex + 1} of ${chainExecution.stages.length}`}
              color="primary"
              variant="outlined"
            />
            <IconButton 
              size="small" 
              onClick={() => navigateToStage('next')}
              disabled={currentStageIndex === chainExecution.stages.length - 1}
            >
              <NavigateNext />
            </IconButton>
          </Box>
        </Box>

        {/* Stage Navigation Breadcrumbs */}
        <Breadcrumbs separator="•" sx={{ mb: 2 }}>
          {chainExecution.stages.map((stage, index) => (
            <Link
              key={stage.execution_id}
              component="button"
              variant="body2"
              onClick={() => {
                setCurrentStageIndex(index);
                setExpandedStages(new Set([stage.execution_id]));
              }}
              sx={{
                color: index === currentStageIndex ? 'primary.main' : 'text.secondary',
                fontWeight: index === currentStageIndex ? 600 : 400,
                textDecoration: 'none',
                cursor: 'pointer',
                '&:hover': { textDecoration: 'underline' }
              }}
            >
              {stage.stage_name}
            </Link>
          ))}
        </Breadcrumbs>

        {/* Overall Progress */}
        <Box display="flex" gap={2} alignItems="center" mb={2}>
          <LinearProgress 
            variant="determinate" 
            value={((currentStageIndex + 1) / chainExecution.stages.length) * 100}
            sx={{ height: 6, borderRadius: 3, flex: 1 }}
          />
          <Typography variant="body2" color="text.secondary">
            {chainExecution.stages.filter(s => s.status === 'completed').length} / {chainExecution.stages.length} completed
          </Typography>
        </Box>

        {/* Chain Status Chips */}
        <Box display="flex" gap={1} flexWrap="wrap">
          <Chip 
            label={`${chainExecution.stages.length} stages`} 
            color="primary" 
            variant="outlined" 
            size="small"
          />
          <Chip 
            label={`${chainExecution.stages.filter(s => s.status === 'completed').length} completed`} 
            color="success" 
            variant="outlined" 
            size="small"
          />
          {chainExecution.stages.filter(s => s.status === 'failed').length > 0 && (
            <Chip 
              label={`${chainExecution.stages.filter(s => s.status === 'failed').length} failed`} 
              color="error" 
              variant="outlined" 
              size="small"
            />
          )}
          {chainExecution.current_stage_index !== null && (
            <Chip 
              label={`Current: Stage ${chainExecution.current_stage_index + 1}`} 
              color="primary" 
              size="small"
            />
          )}
        </Box>
      </CardContent>

      {/* Nested Accordion Stages */}
      <Box sx={{ p: 2 }}>
        {chainExecution.stages.map((stage, stageIndex) => {
          const stageInteractions = getStageInteractions(stage.execution_id);
          const isExpanded = expandedStages.has(stage.execution_id);
          const isCurrentStage = stageIndex === currentStageIndex;

          return (
            <Accordion
              key={stage.execution_id}
              expanded={isExpanded}
              onChange={() => handleStageToggle(stage.execution_id, stageIndex)}
              sx={{
                mb: 1,
                '&:before': { display: 'none' },
                boxShadow: isCurrentStage ? 3 : 1,
                bgcolor: isCurrentStage ? 'primary.50' : 'inherit',
                border: isCurrentStage ? 2 : 1,
                borderColor: isCurrentStage ? 'primary.main' : 'divider'
              }}
            >
              <AccordionSummary 
                expandIcon={<ExpandMore />}
                sx={{ 
                  bgcolor: isCurrentStage ? 'primary.100' : 'grey.50',
                  '&.Mui-expanded': {
                    bgcolor: isCurrentStage ? 'primary.100' : 'grey.100'
                  }
                }}
              >
                <Box display="flex" alignItems="center" gap={2} width="100%">
                  <Avatar sx={{ 
                    width: 40, 
                    height: 40,
                    bgcolor: getStageStatusColor(stage.status) + '.main',
                    color: 'white'
                  }}>
                    {getStageStatusIcon(stage.status)}
                  </Avatar>
                  
                  <Box flex={1}>
                    <Typography variant="h6" fontWeight={600}>
                      Stage {stageIndex + 1}: {stage.stage_name}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {stage.agent} • {stageInteractions.length} interactions
                      {stage.started_at_us && ` • Started: ${formatTimestamp(stage.started_at_us, 'short')}`}
                    </Typography>
                  </Box>

                  <Box display="flex" gap={1} alignItems="center" onClick={(e) => e.stopPropagation()}>
                    <Chip 
                      label={stage.status} 
                      color={getStageStatusColor(stage.status)}
                      size="small"
                    />
                    {stage.duration_ms && (
                      <Chip 
                        label={formatDurationMs(stage.duration_ms)} 
                        variant="outlined"
                        size="small"
                      />
                    )}
                  </Box>
                </Box>
              </AccordionSummary>

              <AccordionDetails sx={{ pt: 0 }}>
                {/* Stage Metadata */}
                <Card variant="outlined" sx={{ mb: 3, bgcolor: 'grey.25' }}>
                  <CardContent>
                    <Typography variant="subtitle2" gutterBottom>
                      Stage Information
                    </Typography>
                    <Box display="flex" gap={3} flexWrap="wrap">
                      <Typography variant="body2">
                        <strong>Agent:</strong> {stage.agent}
                      </Typography>
                      {stage.iteration_strategy && (
                        <Typography variant="body2">
                          <strong>Strategy:</strong> {stage.iteration_strategy}
                        </Typography>
                      )}
                      <Typography variant="body2">
                        <strong>Interactions:</strong> {stageInteractions.length}
                      </Typography>
                    </Box>
                    
                    {stage.error_message && (
                      <Box mt={2} p={2} bgcolor="error.50" borderRadius={1}>
                        <Typography variant="body2" color="error.main">
                          <strong>Error:</strong> {stage.error_message}
                        </Typography>
                      </Box>
                    )}
                  </CardContent>
                </Card>

                {/* Chronological Interactions Timeline within Stage */}
                <Typography variant="subtitle1" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <TimelineIcon color="primary" fontSize="small" />
                  Interactions Timeline
                </Typography>

                {stageInteractions.length > 0 ? (
                  <List dense sx={{ bgcolor: 'background.paper', borderRadius: 1, border: 1, borderColor: 'divider' }}>
                    {stageInteractions.map((interaction, interactionIndex) => {
                      const isExpanded = expandedInteractions.has(interaction.event_id);
                      
                      return (
                        <React.Fragment key={interaction.event_id}>
                          <ListItem
                            onClick={() => handleInteractionToggle(interaction.event_id)}
                            sx={{
                              py: 2,
                              cursor: 'pointer',
                              '&:hover': { bgcolor: 'action.hover' }
                            }}
                          >
                            <ListItemIcon sx={{ minWidth: 48 }}>
                              <Box sx={{ position: 'relative' }}>
                                <Avatar sx={{ 
                                  width: 32, 
                                  height: 32,
                                  bgcolor: interaction.type === 'llm' ? 'primary.main' : 'secondary.main'
                                }}>
                                  {getInteractionIcon(interaction.type)}
                                </Avatar>
                                
                                {/* Timeline connecting line - only if not last item OR expanded */}
                                {(interactionIndex < stageInteractions.length - 1 || isExpanded) && (
                                  <Box sx={{
                                    position: 'absolute',
                                    left: '50%',
                                    top: 32,
                                    width: 2,
                                    height: isExpanded ? 80 : 32,
                                    bgcolor: 'divider',
                                    transform: 'translateX(-50%)'
                                  }} />
                                )}
                              </Box>
                            </ListItemIcon>

                            <ListItemText
                              primary={
                                <Box display="flex" justifyContent="space-between" alignItems="center">
                                  <Typography variant="body1" fontWeight={500}>
                                    {interaction.step_description}
                                  </Typography>
                                  <IconButton size="small" sx={{ ml: 1 }}>
                                    {isExpanded ? <ExpandLess /> : <ExpandMore />}
                                  </IconButton>
                                </Box>
                              }
                              secondary={`${formatTimestamp(interaction.timestamp_us)} • ${interaction.type.toUpperCase()}${interaction.duration_ms ? ` • ${interaction.duration_ms}ms` : ''}`}
                            />
                          </ListItem>

                          <Collapse in={isExpanded} timeout="auto" unmountOnExit>
                            <Box sx={{ pl: 6, pr: 2, pb: 2, pt: 1 }}>
                              <Card variant="outlined" sx={{ bgcolor: 'grey.50', border: '1px solid', borderColor: 'divider' }}>
                                <CardContent sx={{ p: 2 }}>
                                  <Typography variant="subtitle2" gutterBottom color="primary.main" sx={{ mb: 2 }}>
                                    Interaction Details
                                  </Typography>
                                  
                                  <Box sx={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 1, mb: 2 }}>
                                    <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>ID:</Typography>
                                    <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>{interaction.event_id}</Typography>
                                    
                                    <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>Type:</Typography>
                                    <Typography variant="body2">{interaction.type.toUpperCase()}</Typography>
                                    
                                    <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>Timestamp:</Typography>
                                    <Typography variant="body2">{formatTimestamp(interaction.timestamp_us)}</Typography>
                                    
                                    {interaction.duration_ms && (
                                      <>
                                        <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>Duration:</Typography>
                                        <Typography variant="body2">{interaction.duration_ms}ms</Typography>
                                      </>
                                    )}
                                  </Box>
                                  
                                  <Typography variant="body2" sx={{ mb: 1, fontWeight: 600, color: 'text.secondary' }}>Description:</Typography>
                                  <Typography variant="body2" sx={{ mb: 2, p: 1, bgcolor: 'background.paper', borderRadius: 1, border: '1px solid', borderColor: 'divider' }}>
                                    {interaction.step_description}
                                  </Typography>
                                  
                                  {interaction.details && (
                                    <Box>
                                      <Typography variant="body2" sx={{ mb: 1, fontWeight: 600, color: 'text.secondary' }}>
                                        Additional Details:
                                      </Typography>
                                      <Card variant="outlined" sx={{ 
                                        bgcolor: 'background.paper', 
                                        p: 2, 
                                        fontSize: '0.75rem', 
                                        fontFamily: 'monospace', 
                                        overflow: 'auto', 
                                        maxHeight: 300,
                                        border: '1px solid',
                                        borderColor: 'divider'
                                      }}>
                                        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                                          {JSON.stringify(interaction.details, null, 2)}
                                        </pre>
                                      </Card>
                                    </Box>
                                  )}
                                </CardContent>
                              </Card>
                            </Box>
                          </Collapse>
                          
                          {interactionIndex < stageInteractions.length - 1 && !isExpanded && (
                            <Divider variant="inset" component="li" />
                          )}
                        </React.Fragment>
                      );
                    })}
                  </List>
                ) : (
                  <Card variant="outlined" sx={{ p: 3, textAlign: 'center', bgcolor: 'grey.50' }}>
                    <Typography variant="body2" color="text.secondary" fontStyle="italic">
                      No interactions recorded for this stage yet
                    </Typography>
                  </Card>
                )}

                {/* Stage Summary/Next Steps */}
                <Box mt={3} display="flex" justifyContent="space-between" alignItems="center">
                  <Typography variant="body2" color="text.secondary">
                    {stage.status === 'completed' 
                      ? `Stage completed in ${formatDurationMs(stage.duration_ms || 0)}`
                      : stage.status === 'active'
                      ? 'Stage in progress...'
                      : 'Waiting for stage to begin'
                    }
                  </Typography>
                  
                  {stageIndex < chainExecution.stages.length - 1 && (
                    <Chip 
                      label={`Next: ${chainExecution.stages[stageIndex + 1].stage_name}`}
                      variant="outlined"
                      size="small"
                      onClick={() => navigateToStage('next')}
                      clickable
                    />
                  )}
                </Box>
              </AccordionDetails>
            </Accordion>
          );
        })}
      </Box>

      {/* Future: Add interaction details modal here */}
    </Card>
  );
};

export default NestedAccordionTimeline;
