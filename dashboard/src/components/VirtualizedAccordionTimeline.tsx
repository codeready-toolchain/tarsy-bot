import React, { useState, useMemo, useCallback, lazy, Suspense, useRef, useEffect } from 'react';
import { VariableSizeList as List } from 'react-window';
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
  Alert,
  CircularProgress,
  Skeleton,
  useTheme,
  alpha,
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
  NavigateNext,
  NavigateBefore,
} from '@mui/icons-material';
import type { ChainExecution, TimelineItem, LLMInteraction, MCPInteraction } from '../types';
import { formatTimestamp, formatDurationMs } from '../utils/timestamp';
import { 
  getStageStatusColor, 
  getInteractionColor,
  formatStageForCopy,
  getInteractionBackgroundColor
} from '../utils/timelineHelpers';
import InteractionCountBadges from './InteractionCountBadges';
// Auto-scroll is now handled by the centralized system in SessionDetailPageBase

// Lazy load heavy components
const LazyInteractionDetails = lazy(() => import('./LazyInteractionDetails'));
const LLMInteractionPreview = lazy(() => import('./LLMInteractionPreview'));
const MCPInteractionPreview = lazy(() => import('./MCPInteractionPreview'));
const CopyButton = lazy(() => import('./CopyButton'));
const TypingIndicator = lazy(() => import('./TypingIndicator'));

// Helper functions moved to shared utils (timelineHelpers.ts)

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

interface VirtualizedAccordionTimelineProps {
  chainExecution: ChainExecution;
  maxVisibleInteractions?: number; // Control virtualization threshold
  autoScroll?: boolean; // Enable auto-scroll to latest interaction
}

interface InteractionItemData {
  interactions: TimelineItem[];
  expandedInteractionDetails: Record<string, boolean>;
  toggleInteractionDetails: (itemId: string, index: number) => void;
  stageId: string;
  onHeightChange: (index: number, height: number) => void;
}

const ITEM_HEIGHT = 200; // Default height per interaction item
const MAX_NON_VIRTUALIZED_ITEMS = 50; // Threshold for enabling virtualization

// Enhanced loading skeleton for interaction items with glowing effect
const InteractionSkeleton = () => (
  <Card elevation={2} sx={{ mb: 2, overflow: 'hidden' }}>
    <CardContent sx={{ pb: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
        <Skeleton variant="circular" width={32} height={32} />
        <Box sx={{ flex: 1 }}>
          <Skeleton variant="text" width="70%" height={24} />
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Skeleton variant="text" width={100} height={16} />
            <Skeleton variant="text" width={80} height={16} />
            <Skeleton variant="rectangular" width={60} height={20} sx={{ borderRadius: 1 }} />
          </Box>
        </Box>
      </Box>
      
      {/* Preview section skeleton */}
      <Box sx={{ mt: 1 }}>
        <Skeleton variant="rectangular" width="100%" height={60} sx={{ borderRadius: 1, mb: 1 }} />
        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
          <Skeleton variant="rectangular" width={100} height={24} sx={{ borderRadius: 1 }} />
        </Box>
      </Box>
    </CardContent>
  </Card>
);

// Virtualized interaction item component
const InteractionItem = React.memo(({ index, style, data }: { 
  index: number; 
  style: React.CSSProperties; 
  data: InteractionItemData;
}) => {
  const { interactions, expandedInteractionDetails, toggleInteractionDetails, onHeightChange } = data;
  const itemRef = useRef<HTMLDivElement>(null);
  const interaction = interactions[index];
  
  if (!interaction) {
    return (
      <div style={style}>
        <InteractionSkeleton />
      </div>
    );
  }

  const itemKey = interaction.event_id || `interaction-${index}`;
  const isDetailsExpanded = expandedInteractionDetails[itemKey];
  
  // Measure and report height changes
  React.useEffect(() => {
    if (itemRef.current) {
      const height = itemRef.current.offsetHeight;
      onHeightChange(index, height);
    }
  }, [isDetailsExpanded, index, onHeightChange]);

  // Helper functions
  const getInteractionIcon = (type: string) => {
    switch (type) {
      case 'llm':
      case 'llm_interaction':
        return <Psychology />;
      case 'mcp':
      case 'mcp_communication':
        return <Build />;
      default:
        return <TimelineIcon />;
    }
  };



  return (
    <div style={style} ref={itemRef}>
      <Card
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
          mx: 1, // Add margin for virtualized items
          mb: 1,
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
        <CardContent sx={{ pb: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
            <Avatar
              sx={{
                bgcolor: `${getInteractionColor(interaction.type)}.main`,
                color: 'white',
                width: 32,
                height: 32
              }}
            >
              {getInteractionIcon(interaction.type)}
            </Avatar>
            
            <Box sx={{ flex: 1 }}>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
                {interaction.step_description}
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography variant="caption" color="text.secondary">
                  {formatTimestamp(interaction.timestamp_us, 'short')}
                </Typography>
                <Typography variant="caption" sx={{ 
                  color: `${getInteractionColor(interaction.type)}.main`, 
                  fontWeight: 500 
                }}>
                  • {interaction.type.toUpperCase()}
                </Typography>
                {interaction.duration_ms && (
                  <Chip 
                    label={formatDurationMs(interaction.duration_ms)} 
                    size="small" 
                    variant="filled"
                    color={getInteractionColor(interaction.type)}
                    sx={{ fontSize: '0.7rem', height: 20 }}
                  />
                )}
              </Box>
            </Box>
          </Box>
          
          {/* Interaction preview when not expanded */}
          {interaction.details && !isDetailsExpanded && (
            <Box sx={{ mt: 1 }}>
              <Suspense fallback={<InteractionSkeleton />}>
                {interaction.type === 'llm' && (
                  <LLMInteractionPreview 
                    interaction={interaction.details as LLMInteraction}
                    showFullPreview={true} // Show full preview like original
                  />
                )}
                {interaction.type === 'mcp' && (
                  <MCPInteractionPreview 
                    interaction={interaction.details as MCPInteraction}
                    showFullPreview={true} // Show full preview like original
                  />
                )}
              </Suspense>
            </Box>
          )}
          
          {/* Expand/Collapse button */}
          {interaction.details && (
            <Box sx={{ 
              display: 'flex', 
              justifyContent: 'center', 
              mt: 1,
              pt: 0.5
            }}>
              <Box 
                onClick={() => toggleInteractionDetails(itemKey, index)}
                sx={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: 0.5,
                  cursor: 'pointer',
                  py: 0.5,
                  px: 1,
                  borderRadius: 1,
                  bgcolor: getInteractionBackgroundColor(interaction.type),
                  '&:hover': { 
                    bgcolor: interaction.type === 'llm' 
                      ? 'rgba(25, 118, 210, 0.08)' 
                      : interaction.type === 'mcp'
                      ? 'rgba(156, 39, 176, 0.08)'
                      : 'rgba(255, 152, 0, 0.08)',
                  },
                  transition: 'all 0.2s ease-in-out'
                }}
              >
                <Typography 
                  variant="caption" 
                  sx={{ 
                    color: interaction.type === 'llm' 
                      ? '#1976d2' 
                      : interaction.type === 'mcp'
                      ? '#9c27b0'
                      : '#f57c00',
                    fontWeight: 500,
                    fontSize: '0.75rem'
                  }}
                >
                  {isDetailsExpanded ? 'Show Less' : 'Show Details'}
                </Typography>
              </Box>
            </Box>
          )}
          
          {/* Expanded details */}
          {isDetailsExpanded && interaction.details && (
            <Box sx={{ mt: 1, pt: 1 }}>
              <LazyInteractionDetails
                type={interaction.type as 'llm' | 'mcp' | 'system'}
                details={interaction.details}
                expanded={isDetailsExpanded}
              />
            </Box>
          )}
        </CardContent>
      </Card>
    </div>
  );
});

/**
 * VirtualizedAccordionTimeline component - Performance Optimized
 * Uses virtualization for large numbers of interactions
 */
function VirtualizedAccordionTimeline({
  chainExecution,
  maxVisibleInteractions = MAX_NON_VIRTUALIZED_ITEMS,
  autoScroll = true
}: VirtualizedAccordionTimelineProps) {
  const theme = useTheme();
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
  const listRef = useRef<List>(null);
  const sizeMapRef = useRef<Map<number, number>>(new Map());
  
  // Auto-scroll is now handled by the centralized system via MutationObserver
  // No need for local auto-scroll logic
  
  // Helper function to resolve stage status to actual theme colors
  const getResolvedStageStatusColor = useCallback((status: string) => {
    switch (status) {
      case 'completed':
        return theme.palette.success.main;
      case 'failed':
        return theme.palette.error.main;
      case 'active':
        return theme.palette.primary.main;
      case 'pending':
      default:
        return theme.palette.grey[600];
    }
  }, [theme]);

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

  const toggleInteractionDetails = useCallback((itemId: string, index: number) => {
    setExpandedInteractionDetails(prev => ({
      ...prev,
      [itemId]: !prev[itemId]
    }));
    
    // Reset the list layout from this index onward
    if (listRef.current) {
      listRef.current.resetAfterIndex(index, true);
    }
  }, []);
  
  // Callback to handle height changes
  const handleHeightChange = useCallback((index: number, height: number) => {
    if (sizeMapRef.current.get(index) !== height) {
      sizeMapRef.current.set(index, height);
      // Trigger re-render of the list item if needed
      if (listRef.current) {
        listRef.current.resetAfterIndex(index, true);
      }
    }
  }, []);






  
  // Item size resolver for VariableSizeList
  const getItemSize = useCallback((index: number) => {
    const storedSize = sizeMapRef.current.get(index);
    if (storedSize !== undefined) {
      return storedSize;
    }
    
    // Estimate size based on expansion state if we have the data
    // This is a fallback for initial render before measurements
    return ITEM_HEIGHT;
  }, []);

  // Memoized stage interactions
  const getStageInteractions = useCallback((stageId: string) => {
    const stage = chainExecution.stages.find(s => s.execution_id === stageId);
    if (!stage) return [];
    
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
    
    return [...llmInteractions, ...mcpInteractions]
      .sort((a, b) => a.timestamp_us - b.timestamp_us);
  }, [chainExecution.stages]);

  // Calculate total interactions for performance warnings
  const totalInteractions = useMemo(() => {
    return chainExecution.stages.reduce((total, stage) => {
      return total + (stage.llm_interactions?.length || 0) + (stage.mcp_communications?.length || 0);
    }, 0);
  }, [chainExecution.stages]);

  // Effect to automatically expand the current active stage
  useEffect(() => {
    if (!autoScroll) return;

    const currentStageIndex = chainExecution.current_stage_index ?? 0;
    
    // Auto-expand the current active stage
    if (chainExecution.stages[currentStageIndex]) {
      const newStage = chainExecution.stages[currentStageIndex];
      
      if (process.env.NODE_ENV !== 'production') {
        console.log(`🎯 Auto-expanding active stage: ${newStage.stage_name} (stage ${currentStageIndex + 1})`);
      }
      
      // Add the current stage to expanded stages (keep previous ones expanded)
      setExpandedStages(prev => new Set([...prev, newStage.execution_id]));
      setCurrentStageIndex(currentStageIndex);
    }
  }, [chainExecution.current_stage_index, chainExecution.stages, autoScroll]);

  // Auto-scroll is now handled by the centralized system - no setup needed

  // Helper functions now imported from shared utils
  
  // JSX icon helper (can't be in shared utils as it returns JSX)
  const getStageStatusIconJSX = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle fontSize="small" />;
      case 'failed':
        return <ErrorIcon fontSize="small" />;
      case 'active':
        return <PlayArrow fontSize="small" />;
      default:
        return <Schedule fontSize="small" />;
    }
  };

  const shouldUseVirtualization = totalInteractions > maxVisibleInteractions;

  return (
    <Card>
      {/* Chain Progress Header */}
      <CardContent sx={{ bgcolor: 'grey.50', borderBottom: 1, borderColor: 'divider' }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6" color="primary.main">
            Chain: {chainExecution.chain_id}
          </Typography>
          <Box display="flex" alignItems="center" gap={1}>
            {totalInteractions > maxVisibleInteractions && (
              <Alert severity="info" sx={{ py: 0.5, px: 1 }}>
                <Typography variant="caption">
                  {totalInteractions} interactions - using optimized rendering
                </Typography>
              </Alert>
            )}

            <Suspense fallback={<CircularProgress size={20} />}>
              <CopyButton
                text={formatEntireFlowForCopy(chainExecution)}
                variant="button"
                buttonVariant="outlined"
                size="small"
                label="Copy Entire Flow"
                tooltip="Copy all stages and interactions to clipboard"
              />
            </Suspense>
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
      </CardContent>

      {/* Nested Accordion Stages */}
      <Box sx={{ p: 2 }}>
        {chainExecution.stages.map((stage, stageIndex) => {
          const stageInteractions = getStageInteractions(stage.execution_id);
          const isExpanded = expandedStages.has(stage.execution_id);
          const isCurrentStage = stageIndex === currentStageIndex;
          const useVirtualization = shouldUseVirtualization && stageInteractions.length > 20;

          return (
            <Accordion
              key={stage.execution_id}
              expanded={isExpanded}
              onChange={() => handleStageToggle(stage.execution_id, stageIndex)}
              sx={{
                mb: 1,
                '&:before': { display: 'none' },
                boxShadow: isCurrentStage ? 3 : 1,
                bgcolor: isCurrentStage ? alpha(theme.palette.primary.main, 0.06) : 'inherit',
                border: isCurrentStage ? 2 : 1,
                borderColor: isCurrentStage ? 'primary.main' : 'divider'
              }}
            >
              <AccordionSummary 
                expandIcon={<ExpandMore />}
                sx={{ 
                  bgcolor: isCurrentStage ? alpha(theme.palette.primary.main, 0.12) : 'grey.50',
                  '&.Mui-expanded': {
                    bgcolor: isCurrentStage ? alpha(theme.palette.primary.main, 0.12) : 'grey.100'
                  }
                }}
              >
                <Box display="flex" alignItems="center" gap={2} width="100%">
                  <Avatar sx={{ 
                    width: 40, 
                    height: 40,
                    bgcolor: getResolvedStageStatusColor(stage.status),
                    color: 'white'
                  }}>
                    {getStageStatusIconJSX(stage.status)}
                  </Avatar>
                  
                  <Box flex={1}>
                    <Typography variant="h6" fontWeight={600}>
                      Stage {stageIndex + 1}: {stage.stage_name}
                    </Typography>
                    <Box display="flex" alignItems="center" gap={1} flexWrap="wrap">
                      <Typography variant="body2" color="text.secondary">
                        {stage.agent}
                      </Typography>
                      
                      {/* LLM and MCP Interaction Counts */}
                      <InteractionCountBadges stage={stage} />
                      
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
                <Card
                  variant="outlined"
                  sx={theme => ({ mb: 3, bgcolor: theme.palette.grey[50] })}
                >
                  <CardContent>
                    <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
                      <Typography variant="subtitle2">
                        Stage Information
                      </Typography>
                      <Suspense fallback={<CircularProgress size={16} />}>
                        <CopyButton
                          text={formatStageForCopy(stage, stageIndex, stageInteractions)}
                          variant="icon"
                          size="small"
                          tooltip="Copy stage timeline to clipboard"
                        />
                      </Suspense>
                    </Box>
                    <Box display="flex" gap={3} flexWrap="wrap">
                      <Typography variant="body2">
                        <strong>Agent:</strong> {stage.agent}
                      </Typography>

                      <Typography variant="body2">
                        <strong>Interactions:</strong> {stageInteractions.length}
                      </Typography>

                      {stage.llm_interaction_count > 0 && (
                        <Typography variant="body2">
                          <strong>LLM Calls:</strong> {stage.llm_interaction_count}
                        </Typography>
                      )}

                      {stage.mcp_communication_count > 0 && (
                        <Typography variant="body2">
                          <strong>MCP Calls:</strong> {stage.mcp_communication_count}
                        </Typography>
                      )}

                      {stage.duration_ms && (
                        <Typography variant="body2">
                          <strong>Duration:</strong> {formatDurationMs(stage.duration_ms)}
                        </Typography>
                      )}
                    </Box>
                    
                    {stage.error_message && (
                      <Box
                        mt={2}
                        p={2}
                        sx={theme => ({ bgcolor: alpha(theme.palette.error.main, 0.06), borderRadius: 1 })}
                      >
                        <Typography variant="body2" color="error.main">
                          <strong>Error:</strong> {stage.error_message}
                        </Typography>
                      </Box>
                    )}
                  </CardContent>
                </Card>

                {/* Interactions Timeline */}
                <Typography variant="subtitle1" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <TimelineIcon color="primary" fontSize="small" />
                  Interactions Timeline
                  {useVirtualization && (
                    <Chip label="Virtualized" size="small" color="info" variant="outlined" />
                  )}
                </Typography>

                {stageInteractions.length > 0 ? (
                  useVirtualization ? (
                    // Virtualized rendering for large interaction lists
                    <Box sx={{ height: Math.min(600, stageInteractions.length * 60), width: '100%' }}>
                      <List
                        ref={listRef}
                        height={Math.min(600, stageInteractions.length * 60)}
                        width="100%"
                        itemCount={stageInteractions.length}
                        itemSize={getItemSize}
                        itemData={{
                          interactions: stageInteractions,
                          expandedInteractionDetails,
                          toggleInteractionDetails,
                          stageId: stage.execution_id,
                          onHeightChange: handleHeightChange
                        }}
                        overscanCount={5} // Pre-render 5 items above/below visible area
                      >
                        {InteractionItem}
                      </List>
                    </Box>
                  ) : (
                    // Regular rendering for smaller lists
                    <Box 
                      sx={{ 
                        display: 'flex', 
                        flexDirection: 'column', 
                        gap: 2
                      }}
                    >
                      {stageInteractions.map((interaction: TimelineItem, interactionIndex: number) => {
                        const itemKey = interaction.event_id || `interaction-${interactionIndex}`;
                        
                        return (
                          <InteractionItem
                            key={itemKey}
                            index={interactionIndex}
                            style={{}} // No style needed for non-virtualized
                            data={{
                              interactions: stageInteractions,
                              expandedInteractionDetails,
                              toggleInteractionDetails: (itemId: string) => toggleInteractionDetails(itemId, interactionIndex),
                              stageId: stage.execution_id,
                              onHeightChange: () => {} // No-op for non-virtualized items
                            }}
                          />
                        );
                      })}
                    </Box>
                  )
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
                        <Suspense fallback={null}>
                          <TypingIndicator
                            dotsOnly={true}
                            size="small"
                          />
                        </Suspense>
                      </Box>
                    );
                  }
                  return null;
                })()}
              </AccordionDetails>
            </Accordion>
          );
        })}

      </Box>
    </Card>
  );
}

export default VirtualizedAccordionTimeline;
