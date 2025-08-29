import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  CardHeader,
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
} from '@mui/material';
import {
  ExpandMore,
  ExpandLess,
  CheckCircle,
  Error as ErrorIcon,
  Schedule,
  PlayArrow,
  Psychology,
  Build,
  Settings,
  Timeline as TimelineIcon,
  NavigateNext,
  NavigateBefore,
} from '@mui/icons-material';
import type { ChainExecution, TimelineItem, LLMInteraction, MCPInteraction } from '../types';
import { formatTimestamp, formatDurationMs } from '../utils/timestamp';
import { 
  getStageStatusColor, 
  getInteractionColor, 
  getInteractionBackgroundColor,
  formatStageForCopy
} from '../utils/timelineHelpers';
import InteractionDetails from './InteractionDetails';
import LLMInteractionPreview from './LLMInteractionPreview';
import MCPInteractionPreview from './MCPInteractionPreview';
import CopyButton from './CopyButton';
import InteractionCountBadges from './InteractionCountBadges';
import TypingIndicator from './TypingIndicator';
// Auto-scroll is now handled by the centralized system in SessionDetailPageBase

interface NestedAccordionTimelineProps {
  chainExecution: ChainExecution;
  autoScroll?: boolean; // Kept for compatibility, but auto-scroll is now centralized
}

// Helper function to get stage status icon
const getStageStatusIcon = (status: string) => {
  switch (status) {
    case 'completed':
      return <CheckCircle fontSize="small" />;
    case 'failed':
      return <ErrorIcon fontSize="small" />;
    case 'active':
      return <PlayArrow fontSize="small" />;
    case 'pending':
    default:
      return <Schedule fontSize="small" />;
  }
};

// Helper functions moved to shared utils

// Helper function to get interaction type icon
const getInteractionIcon = (type: string) => {
  switch (type) {
    case 'llm':
    case 'llm_interaction':
      return <Psychology />;
    case 'mcp':
    case 'mcp_communication':
      return <Build />;
    case 'system':
      return <Settings />;
    default:
      return <Settings />;
  }
};



// Removed duplicate helper functions - now imported from shared utils

// Helper function to format entire flow for copying
const formatEntireFlowForCopy = (chainExecution: ChainExecution): string => {
  let content = `====== CHAIN EXECUTION: ${chainExecution.chain_id} ======\n`;
  content += `Total Stages: ${chainExecution.stages.length}\n`;
  content += `Completed: ${chainExecution.stages.filter(s => s.status === 'completed').length}\n`;
  content += `Failed: ${chainExecution.stages.filter(s => s.status === 'failed').length}\n`;
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
            value={(chainExecution.stages.filter(s => s.status === 'completed').length / chainExecution.stages.length) * 100}
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
          {chainExecution.current_stage_index !== null && 
           !chainExecution.stages.every(stage => stage.status === 'completed') && (
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
                    <Typography variant="h6" fontWeight={600}>
                      Stage {stageIndex + 1}: {stage.stage_name}
                    </Typography>
                    <Box display="flex" alignItems="center" gap={1} flexWrap="wrap">
                      <Typography variant="body2" color="text.secondary">
                        {stage.agent}
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
                    <Box display="flex" gap={3} flexWrap="wrap">
                      <Typography variant="body2">
                        <strong>Agent:</strong> {stage.agent}
                      </Typography>

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
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                    {stageInteractions.map((interaction: TimelineItem, interactionIndex: number) => {
                      const itemKey = interaction.event_id || `interaction-${interactionIndex}`;
                      const isDetailsExpanded = expandedInteractionDetails[itemKey];
                      
                      return (
                        <Card
                          key={itemKey}
                          elevation={2}
                          sx={{ 
                            bgcolor: 'background.paper',
                            borderRadius: 2,
                            overflow: 'hidden',
                            transition: 'all 0.2s ease-in-out',
                            border: interaction.type === 'llm' 
                              ? '2px solid #90caf9' 
                              : interaction.type === 'mcp'
                              ? '2px solid #ce93d8'
                              : '2px solid #ffcc02',
                            '&:hover': {
                              elevation: 4,
                              transform: 'translateY(-1px)',
                              border: interaction.type === 'llm' 
                                ? '2px solid #42a5f5' 
                                : interaction.type === 'mcp'
                                ? '2px solid #ba68c8'
                                : '2px solid #ffa000'
                            }
                          }}
                        >
                          <CardHeader
                            avatar={
                              <Avatar
                                sx={{
                                  bgcolor: `${getInteractionColor(interaction.type)}.main`,
                                  color: 'white',
                                  width: 40,
                                  height: 40
                                }}
                              >
                                {getInteractionIcon(interaction.type)}
                              </Avatar>
                            }
                            title={
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
                                <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                                  {interaction.step_description}
                                </Typography>
                                {interaction.duration_ms && (
                                  <Chip 
                                    label={formatDurationMs(interaction.duration_ms)} 
                                    size="small" 
                                    variant="filled"
                                    color={getInteractionColor(interaction.type)}
                                    sx={{ fontSize: '0.75rem', height: 24 }}
                                  />
                                )}
                              </Box>
                            }
                            subheader={
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5 }}>
                                <Typography variant="body2" color="text.secondary">
                                  {formatTimestamp(interaction.timestamp_us, 'short')}
                                </Typography>
                                <Typography variant="body2" sx={{ color: `${getInteractionColor(interaction.type)}.main`, fontWeight: 500 }}>
                                  • {interaction.type.toUpperCase()}
                                </Typography>
                              </Box>
                            }
                            action={null}
                            sx={{ 
                              pb: interaction.details && !isDetailsExpanded ? 2 : 1,
                              bgcolor: getInteractionBackgroundColor(interaction.type)
                            }}
                          />
                              
                          
                          {/* Expandable interaction details */}
                          {interaction.details && (
                            <CardContent sx={{ 
                              pt: 2,
                              bgcolor: 'background.paper'
                            }}>
                              {/* Show LLM preview when not expanded */}
                              {interaction.type === 'llm' && !isDetailsExpanded && (
                                <LLMInteractionPreview 
                                  interaction={interaction.details as LLMInteraction}
                                  showFullPreview={true}
                                />
                              )}
                              
                              {/* Show MCP preview when not expanded */}
                              {interaction.type === 'mcp' && !isDetailsExpanded && (
                                <MCPInteractionPreview 
                                  interaction={interaction.details as MCPInteraction}
                                  showFullPreview={true}
                                />
                              )}
                              
                              {/* Expand/Collapse button */}
                              <Box sx={{ 
                                display: 'flex', 
                                justifyContent: 'center', 
                                mt: 2,
                                mb: 1
                              }}>
                                                                    <Box 
                                  onClick={() => toggleInteractionDetails(itemKey)}
                                  sx={{ 
                                    display: 'flex', 
                                    alignItems: 'center', 
                                    gap: 0.5,
                                    cursor: 'pointer',
                                    py: 0.75,
                                    px: 1.5,
                                    borderRadius: 1,
                                    bgcolor: interaction.type === 'llm' 
                                      ? 'rgba(25, 118, 210, 0.04)' 
                                      : interaction.type === 'mcp'
                                      ? 'rgba(156, 39, 176, 0.04)'
                                      : 'rgba(255, 152, 0, 0.04)',
                                    border: interaction.type === 'llm' 
                                      ? '1px solid rgba(25, 118, 210, 0.12)' 
                                      : interaction.type === 'mcp'
                                      ? '1px solid rgba(156, 39, 176, 0.12)'
                                      : '1px solid rgba(255, 152, 0, 0.12)',
                                    '&:hover': { 
                                      bgcolor: interaction.type === 'llm' 
                                        ? 'rgba(25, 118, 210, 0.08)' 
                                        : interaction.type === 'mcp'
                                        ? 'rgba(156, 39, 176, 0.08)'
                                        : 'rgba(255, 152, 0, 0.08)',
                                      border: interaction.type === 'llm' 
                                        ? '1px solid rgba(25, 118, 210, 0.2)' 
                                        : interaction.type === 'mcp'
                                        ? '1px solid rgba(156, 39, 176, 0.2)'
                                        : '1px solid rgba(255, 152, 0, 0.2)',
                                      '& .expand-text': {
                                        textDecoration: 'underline'
                                      }
                                    },
                                    transition: 'all 0.2s ease-in-out'
                                  }}
                                >
                                  <Typography 
                                    className="expand-text"
                                    variant="body2" 
                                    sx={{ 
                                      color: interaction.type === 'llm' 
                                        ? '#1976d2' 
                                        : interaction.type === 'mcp'
                                        ? '#9c27b0'
                                        : '#f57c00',
                                      fontWeight: 500,
                                      fontSize: '0.875rem'
                                    }}
                                  >
                                    {isDetailsExpanded ? 'Show Less' : 'Show Full Details'}
                                  </Typography>
                                  <Box sx={{ 
                                    color: interaction.type === 'llm' 
                                      ? '#1976d2' 
                                      : interaction.type === 'mcp'
                                      ? '#9c27b0'
                                      : '#f57c00',
                                    display: 'flex',
                                    alignItems: 'center'
                                  }}>
                                    {isDetailsExpanded ? <ExpandLess /> : <ExpandMore />}
                                  </Box>
                                </Box>
                              </Box>
                              
                              {/* Full interaction details when expanded */}
                              <InteractionDetails
                                type={interaction.type as 'llm' | 'mcp' | 'system'}
                                details={interaction.details}
                                expanded={isDetailsExpanded}
                              />
                            </CardContent>
                          )}
                        </Card>
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
                  const shouldShow = stage.status === 'active' || stage.status === 'pending';
                  
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
