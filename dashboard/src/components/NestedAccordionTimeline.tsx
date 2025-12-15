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
  LinearProgress,
  Breadcrumbs,
  Link,
  IconButton,
  alpha,
} from '@mui/material';
import {
  ExpandMore,
  CheckCircle,
  Error as ErrorIcon,
  Schedule,
  PlayArrow,
  Settings,
  Timeline as TimelineIcon,
  NavigateNext,
  NavigateBefore,
  CallSplit,
} from '@mui/icons-material';
import type { ChainExecution, TimelineItem } from '../types';
import { formatTimestamp, formatDurationMs } from '../utils/timestamp';
import { 
  getStageStatusColor, 
  formatStageForCopy
} from '../utils/timelineHelpers';
import CopyButton from './CopyButton';
import InteractionCountBadges from './InteractionCountBadges';
import TypingIndicator from './TypingIndicator';
import ParallelStageExecutionTabs from './ParallelStageExecutionTabs';
import InteractionCard from './InteractionCard';
import { STAGE_STATUS } from '../utils/statusConstants';
import { isParallelStage, getAggregateStatus } from '../utils/parallelStageHelpers';
import { PARALLEL_TYPE } from '../utils/parallelConstants';
// Auto-scroll is now handled by the centralized system in SessionDetailPageBase

interface NestedAccordionTimelineProps {
  chainExecution: ChainExecution;
  autoScroll?: boolean; // Kept for compatibility, but auto-scroll is now centralized
  progressStatus?: string;
}

// Helper function to get stage status icon
const getStageStatusIcon = (status: string) => {
  switch (status) {
    case STAGE_STATUS.COMPLETED:
      return <CheckCircle fontSize="small" />;
    case STAGE_STATUS.FAILED:
      return <ErrorIcon fontSize="small" />;
    case STAGE_STATUS.ACTIVE:
      return <PlayArrow fontSize="small" />;
    case STAGE_STATUS.PENDING:
    default:
      return <Schedule fontSize="small" />;
  }
};

// Helper functions moved to shared utils and InteractionCard component

// Helper function to format entire flow for copying
const formatEntireFlowForCopy = (chainExecution: ChainExecution): string => {
  let content = `====== CHAIN EXECUTION: ${chainExecution.chain_id} ======\n`;
  content += `Total Stages: ${chainExecution.stages.length}\n`;
  content += `Completed: ${chainExecution.stages.filter(s => s.status === STAGE_STATUS.COMPLETED).length}\n`;
  content += `Failed: ${chainExecution.stages.filter(s => s.status === STAGE_STATUS.FAILED).length}\n`;
  content += `Current Stage: ${chainExecution.current_stage_index !== null ? chainExecution.current_stage_index + 1 : 'None'}\n\n`;
  
  chainExecution.stages.forEach((stage, stageIndex) => {
    // EP-0010: Get interactions using the same logic as getStageInteractions
    const llmInteractions = (stage.llm_interactions || []).map(interaction => ({
      event_id: interaction.event_id,
      type: 'llm' as const,
      timestamp_us: interaction.timestamp_us,
      step_description: interaction.step_description,
      duration_ms: interaction.duration_ms,
      details: interaction.details
    }));
    
    const mcpInteractions = (stage.mcp_communications || []).map(interaction => ({
      event_id: interaction.event_id,
      type: 'mcp' as const,
      timestamp_us: interaction.timestamp_us,
      step_description: interaction.step_description,
      duration_ms: interaction.duration_ms,
      details: interaction.details
    }));
    
    const stageInteractions = [...llmInteractions, ...mcpInteractions]
      .sort((a, b) => a.timestamp_us - b.timestamp_us);
    
    content += `\n${'='.repeat(80)}\n`;
    content += formatStageForCopy(stage, stageIndex, stageInteractions);
    
    if (stageIndex < chainExecution.stages.length - 1) {
      content += `${'='.repeat(80)}\n`;
    }
  });
  
  return content;
};

const NestedAccordionTimeline: React.FC<NestedAccordionTimelineProps> = ({
  chainExecution,
  autoScroll: _autoScroll = true, // Kept for compatibility, but not used
}) => {
  const [expandedStages, setExpandedStages] = useState<Set<string>>(
    new Set(
      chainExecution.current_stage_index !== null && 
      chainExecution.current_stage_index < chainExecution.stages.length &&
      chainExecution.stages[chainExecution.current_stage_index]?.execution_id
        ? [chainExecution.stages[chainExecution.current_stage_index].execution_id]
        : []
    )
  );
  const [currentStageIndex, setCurrentStageIndex] = useState<number>(
    chainExecution.current_stage_index ?? 0
  );
  const [expandedInteractionDetails, setExpandedInteractionDetails] = useState<Record<string, boolean>>({});

  // Auto-scroll is now handled by the centralized system


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

  const toggleInteractionDetails = (itemId: string) => {
    setExpandedInteractionDetails(prev => ({
      ...prev,
      [itemId]: !prev[itemId]
    }));
  };

  // Auto-scroll setup is now handled by the centralized system

  const getStageInteractions = (stageId: string) => {
    const stage = chainExecution.stages.find(s => s.execution_id === stageId);
    if (!stage) return [];
    
    // EP-0010: Combine LLM and MCP interactions into chronological timeline
    const llmInteractions = (stage.llm_interactions || []).map(interaction => ({
      event_id: interaction.event_id,
      type: 'llm' as const,
      timestamp_us: interaction.timestamp_us,
      step_description: interaction.step_description,
      duration_ms: interaction.duration_ms,
      details: interaction.details
    }));
    
    const mcpInteractions = (stage.mcp_communications || []).map(interaction => ({
      event_id: interaction.event_id,
      type: 'mcp' as const,
      timestamp_us: interaction.timestamp_us,
      step_description: interaction.step_description,
      duration_ms: interaction.duration_ms,
      details: interaction.details
    }));
    
    // Combine and sort chronologically
    return [...llmInteractions, ...mcpInteractions]
      .sort((a, b) => a.timestamp_us - b.timestamp_us);
  };

  // Auto-scroll detection is now handled by the centralized system

  return (
    <Card>
      {/* Chain Progress Header */}
      <CardContent sx={{ bgcolor: 'grey.50', borderBottom: 1, borderColor: 'divider' }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6" color="primary.main">
            Chain: {chainExecution.chain_id}
          </Typography>
          <Box display="flex" alignItems="center" gap={1}>
            <CopyButton
              text={formatEntireFlowForCopy(chainExecution)}
              variant="button"
              buttonVariant="outlined"
              size="small"
              label="Copy Entire Flow"
              tooltip="Copy all stages and interactions to clipboard"
            />
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
            value={(chainExecution.stages.filter(s => s.status === STAGE_STATUS.COMPLETED).length / chainExecution.stages.length) * 100}
            sx={{ height: 6, borderRadius: 3, flex: 1 }}
          />
          <Typography variant="body2" color="text.secondary">
            {chainExecution.stages.filter(s => s.status === STAGE_STATUS.COMPLETED).length} / {chainExecution.stages.length} completed
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
            label={`${chainExecution.stages.filter(s => s.status === STAGE_STATUS.COMPLETED).length} completed`} 
            color="success" 
            variant="outlined" 
            size="small"
          />
          {chainExecution.stages.filter(s => s.status === STAGE_STATUS.FAILED).length > 0 && (
            <Chip 
              label={`${chainExecution.stages.filter(s => s.status === STAGE_STATUS.FAILED).length} failed`} 
              color="error" 
              variant="outlined" 
              size="small"
            />
          )}
          {chainExecution.current_stage_index !== null && 
           !chainExecution.stages.every(stage => stage.status === STAGE_STATUS.COMPLETED) && (
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
          
          // Check if this is a parallel stage
          const isParallel = isParallelStage(stage);
          const aggregateStatusLabel = isParallel && stage.parallel_executions
            ? getAggregateStatus(stage.parallel_executions)
            : null;

          return (
            <Accordion
              key={stage.execution_id}
              expanded={isExpanded}
              onChange={() => handleStageToggle(stage.execution_id, stageIndex)}
              sx={(theme) => ({
                mb: 1,
                '&:before': { display: 'none' },
                boxShadow: isCurrentStage ? 3 : 1,
                bgcolor: isCurrentStage ? alpha(theme.palette.primary.main, 0.05) : 'inherit',
                border: isCurrentStage ? 2 : 1,
                borderColor: isCurrentStage ? 'primary.main' : 'divider'
              })}
            >
              <AccordionSummary 
                expandIcon={<ExpandMore />}
                sx={(theme) => ({ 
                  bgcolor: isCurrentStage ? alpha(theme.palette.primary.main, 0.1) : 'grey.50',
                  '&.Mui-expanded': {
                    bgcolor: isCurrentStage ? alpha(theme.palette.primary.main, 0.1) : 'grey.100'
                  }
                })}
              >
                <Box display="flex" alignItems="center" gap={2} width="100%">
                  <Avatar sx={{
                    width: 40,
                    height: 40,
                    bgcolor: (theme) => {
                      const key = getStageStatusColor(stage.status);
                      // @ts-expect-error palette indexing by key is runtime-safe
                      return theme.palette[key]?.main ?? theme.palette.grey[500];
                    },
                    color: 'white'
                  }}>
                    {getStageStatusIcon(stage.status)}
                  </Avatar>
                  
                  <Box flex={1}>
                    <Box display="flex" alignItems="center" gap={1}>
                      <Typography variant="h6" fontWeight={600}>
                        {stage.chat_id 
                          ? `Chat: ${stage.stage_name}`
                          : `Stage ${stage.stage_index + 1}: ${stage.stage_name}`
                        }
                      </Typography>
                      {isParallel && stage.parallel_executions && (
                        <Chip
                          icon={<CallSplit fontSize="small" />}
                          label={`${stage.parallel_executions.length}x`}
                          size="small"
                          color="primary"
                          variant="outlined"
                        />
                      )}
                    </Box>
                    <Box display="flex" alignItems="center" gap={1} flexWrap="wrap">
                      <Typography variant="body2" color="text.secondary">
                        {isParallel 
                          ? `Parallel Execution (${stage.parallel_type === PARALLEL_TYPE.REPLICA ? 'Replica Mode' : 'Multi-Agent Mode'})`
                          : stage.agent
                        }
                      </Typography>
                      
                      {/* Interaction count badges similar to session summary */}
                      {stageInteractions.length > 0 && (
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
                              {stageInteractions.length}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.65rem' }}>
                              total
                            </Typography>
                          </Box>
                          
                          {/* LLM and MCP interaction count badges */}
                          <InteractionCountBadges stage={stage} />
                        </Box>
                      )}
                      
                      {stage.started_at_us && (
                        <Typography variant="body2" color="text.secondary">
                          • Started: {formatTimestamp(stage.started_at_us, 'short')}
                        </Typography>
                      )}
                    </Box>
                  </Box>

                  <Box display="flex" gap={1} alignItems="center">
                    <Chip 
                      label={isParallel && aggregateStatusLabel ? aggregateStatusLabel : stage.status} 
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

              <AccordionDetails sx={{ pt: 1, px: 1 }}>
                {/* Parallel Stage Tabs */}
                {isParallel && stage.parallel_executions && stage.parallel_executions.length > 0 ? (
                  <ParallelStageExecutionTabs 
                    stage={stage}
                  />
                ) : (
                  <>
                    {/* Stage Metadata */}
                    <Card
                      variant="outlined"
                      sx={{ mb: 1, bgcolor: (theme) => theme.palette.grey[50] }}
                    >
                      <CardContent>
                        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                          <Typography variant="subtitle2">
                            Stage Information
                          </Typography>
                          <CopyButton
                            text={formatStageForCopy(stage, stageIndex, stageInteractions)}
                            variant="icon"
                            size="small"
                            tooltip="Copy stage timeline to clipboard"
                          />
                        </Box>
                    <Box display="flex" gap={1} flexWrap="wrap" alignItems="center">
                      {(() => {
                        const metadataItems = [
                          { label: 'Agent', value: stage.agent },
                          { label: 'Interactions', value: stageInteractions.length },
                        ];

                        if (stage.llm_interaction_count > 0) {
                          metadataItems.push({ 
                            label: 'LLM Calls', 
                            value: stage.llm_interaction_count 
                          });
                        }

                        if (stage.mcp_communication_count > 0) {
                          metadataItems.push({ 
                            label: 'MCP Calls', 
                            value: stage.mcp_communication_count 
                          });
                        }

                        if (stage.duration_ms != null) {
                          metadataItems.push({ 
                            label: 'Duration', 
                            value: formatDurationMs(stage.duration_ms) 
                          });
                        }

                        return metadataItems.map((item, index) => (
                          <React.Fragment key={index}>
                            <Typography variant="body2">
                              <strong>{item.label}:</strong> {item.value}
                            </Typography>
                            {index < metadataItems.length - 1 && (
                              <Typography variant="body2" color="text.disabled">
                                •
                              </Typography>
                            )}
                          </React.Fragment>
                        ));
                      })()}
                    </Box>
                    
                    {stage.error_message && (
                      <Box mt={2} p={2} sx={(theme) => ({ bgcolor: alpha(theme.palette.error.main, 0.05) })} borderRadius={1}>
                        <Typography variant="body2" color="error.main">
                          <strong>Error:</strong> {stage.error_message}
                        </Typography>
                      </Box>
                    )}
                  </CardContent>
                </Card>

                {/* Chronological Interactions Timeline within Stage */}
                <Typography variant="subtitle1" sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <TimelineIcon color="primary" fontSize="small" />
                  Interactions Timeline
                </Typography>

                {stageInteractions.length > 0 ? (
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {stageInteractions.map((interaction: TimelineItem, interactionIndex: number) => {
                      const itemKey = interaction.event_id || `interaction-${interactionIndex}`;
                      const isDetailsExpanded = expandedInteractionDetails[itemKey];
                      
                      return (
                        <InteractionCard
                          key={itemKey}
                          interaction={interaction}
                          isExpanded={isDetailsExpanded}
                          onToggle={() => toggleInteractionDetails(itemKey)}
                        />
                      );
                    })}
                  </Box>
                ) : (
                  <Card variant="outlined" sx={{ p: 3, textAlign: 'center', bgcolor: 'grey.50' }}>
                    <Typography variant="body2" color="text.secondary" fontStyle="italic">
                      No interactions recorded for this stage yet
                    </Typography>
                  </Card>
                )}

                    {/* Show typing indicator for active or pending stages */}
                    {(() => {
                      const shouldShow = stage.status === STAGE_STATUS.ACTIVE || stage.status === STAGE_STATUS.PENDING;
                      
                      if (shouldShow) {
                        return (
                          <Box sx={{ mt: 2 }}>
                            <TypingIndicator
                              dotsOnly={true}
                              size="small"
                            />
                          </Box>
                        );
                      }
                      return null;
                    })()}

                    {/* Stage Summary/Next Steps */}
                    <Box mt={1.5} display="flex" justifyContent="space-between" alignItems="center">
                      <Typography variant="body2" color="text.secondary">
                        {stage.status === STAGE_STATUS.COMPLETED 
                          ? `Stage completed in ${formatDurationMs(stage.duration_ms || 0)}`
                          : stage.status === STAGE_STATUS.ACTIVE
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
                  </>
                )}
              </AccordionDetails>
            </Accordion>
          );
        })}

        {/* Session-Level Interactions Section */}
        {chainExecution.session_level_interactions && chainExecution.session_level_interactions.length > 0 && (
          <Box sx={{ mt: 3, pt: 3, borderTop: '2px solid', borderColor: 'divider' }}>
            <Typography 
              variant="h6" 
              sx={{ 
                mb: 2, 
                display: 'flex', 
                alignItems: 'center', 
                gap: 1,
                color: 'info.main'
              }}
            >
              <Settings sx={{ fontSize: 24 }} />
              Session-Level Interactions
              <Chip 
                label={chainExecution.session_level_interactions.length}
                size="small"
                color="info"
                sx={{ ml: 1 }}
              />
            </Typography>
            
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              These interactions are not associated with any specific stage (e.g., executive summary generation).
            </Typography>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {chainExecution.session_level_interactions.map((interaction: TimelineItem, index: number) => {
                const itemKey = interaction.event_id || `session-interaction-${index}`;
                const isDetailsExpanded = expandedInteractionDetails[itemKey];
                
                return (
                  <InteractionCard
                    key={itemKey}
                    interaction={interaction}
                    isExpanded={isDetailsExpanded}
                    onToggle={() => toggleInteractionDetails(itemKey)}
                  />
                );
              })}
            </Box>
          </Box>
        )}

      </Box>

      {/* Future: Add interaction details modal here */}
    </Card>
  );
};

export default NestedAccordionTimeline;
