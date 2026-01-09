import React, { useState, useMemo } from 'react';
import {
  Box,
  Typography,
  Chip,
  Alert,
  alpha,
  Button,
} from '@mui/material';
import {
  CheckCircle,
  Error as ErrorIcon,
  PlayArrow,
  CallSplit,
  CancelOutlined,
  PauseCircle,
} from '@mui/icons-material';
import type { ChatFlowItemData } from '../utils/chatFlowParser';
import type { StageExecution } from '../types';
import { apiClient, handleAPIError } from '../services/api';
import ChatFlowItem from './ChatFlowItem';
import StreamingContentRenderer, { type StreamingItem } from './StreamingContentRenderer';
import { getParallelStageLabel } from '../utils/parallelStageHelpers';
import TokenUsageDisplay from './TokenUsageDisplay';

// Extended streaming item type that includes parallel execution metadata
interface ParallelStreamingItem extends StreamingItem {
  executionId?: string;
  executionAgent?: string;
  isParallelStage?: boolean;
}

interface ParallelStageReasoningTabsProps {
  items: ChatFlowItemData[];
  stage: StageExecution; // Stage object to get correct execution order
  collapsedStages: Map<string, boolean>;
  onToggleStage: (stageId: string) => void;
  // Streaming items for real-time display (not yet in DB)
  streamingItems?: [string, ParallelStreamingItem][];
  // Auto-collapse props
  shouldAutoCollapse?: (item: ChatFlowItemData) => boolean;
  onToggleItemExpansion?: (item: ChatFlowItemData) => void;
  expandAllReasoning?: boolean;
  isItemCollapsible?: (item: ChatFlowItemData) => boolean;
}

interface TabPanelProps {
  children?: React.ReactNode;
  index: number;
  value: number;
}

function TabPanel(props: TabPanelProps) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`reasoning-tabpanel-${index}`}
      aria-labelledby={`reasoning-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 2 }}>{children}</Box>}
    </div>
  );
}

// Helper to get status icon from stage execution status (stable, doesn't blink)
const getStatusIcon = (status: string) => {
  if (status === 'failed') return <ErrorIcon fontSize="small" />;
  if (status === 'completed') return <CheckCircle fontSize="small" />;
  if (status === 'cancelled') return <CancelOutlined fontSize="small" />;
  if (status === 'paused') return <PauseCircle fontSize="small" />;
  return <PlayArrow fontSize="small" />;
};

// Helper to get status color from stage execution status (stable, doesn't blink)
const getStatusColor = (status: string) => {
  if (status === 'failed') return 'error';
  if (status === 'completed') return 'success';
  if (status === 'cancelled') return 'default';
  if (status === 'paused') return 'warning';
  return 'primary';
};

// Helper to get user-friendly status label
const getStatusLabel = (status: string) => {
  if (status === 'failed') return 'Failed';
  if (status === 'completed') return 'Complete';
  if (status === 'cancelled') return 'Cancelled';
  if (status === 'paused') return 'Paused';
  if (status === 'active') return 'Running';
  return 'Pending';
};

/**
 * Component for displaying parallel stage reasoning flows in a tabbed interface
 * Groups chat flow items by execution and shows them in separate tabs
 */
const ParallelStageReasoningTabs: React.FC<ParallelStageReasoningTabsProps> = ({
  items,
  stage,
  collapsedStages,
  onToggleStage,
  streamingItems = [],
  shouldAutoCollapse,
  onToggleItemExpansion,
  expandAllReasoning = false,
  isItemCollapsible,
}) => {
  const [selectedTab, setSelectedTab] = useState(0);
  const [cancelingAgents, setCancelingAgents] = useState<Set<string>>(new Set());
  const [cancelError, setCancelError] = useState<string | null>(null);

  // Handler to cancel an individual agent
  const handleCancelAgent = async (executionId: string) => {
    setCancelingAgents(prev => new Set(prev).add(executionId));
    setCancelError(null);
    
    try {
      await apiClient.cancelAgent(stage.session_id, executionId);
      // UI will update via WebSocket events
    } catch (error) {
      const errorMessage = handleAPIError(error);
      setCancelError(errorMessage);
      // Remove from canceling set on error
      setCancelingAgents(prev => {
        const next = new Set(prev);
        next.delete(executionId);
        return next;
      });
    }
  };

  // Group DB items by executionId
  const executionGroups = new Map<string, ChatFlowItemData[]>();
  const executionAgents = new Map<string, string>();
  
  for (const item of items) {
    // Skip stage_start and user_message items (they're shared across all executions)
    if (item.type === 'stage_start' || item.type === 'user_message') {
      continue;
    }
    
    if (item.executionId && item.isParallelStage) {
      if (!executionGroups.has(item.executionId)) {
        executionGroups.set(item.executionId, []);
        executionAgents.set(item.executionId, item.executionAgent || 'Unknown Agent');
      }
      executionGroups.get(item.executionId)!.push(item);
    }
  }
  
  // Group streaming items by their child execution ID (stage_execution_id)
  // For parallel stages, stage_execution_id is the child's execution ID
  const streamingByExecution = useMemo(() => {
    const byExecution = new Map<string, [string, ParallelStreamingItem][]>();
    
    for (const entry of streamingItems) {
      const [, item] = entry;
      // Use stage_execution_id (child execution ID) for grouping
      const executionId = item.stage_execution_id;
      
      if (executionId && item.isParallelStage) {
        if (!byExecution.has(executionId)) {
          byExecution.set(executionId, []);
        }
        byExecution.get(executionId)!.push(entry);
      }
    }
    
    return byExecution;
  }, [streamingItems]);

  // Convert to array and sort by the same order as stage.parallel_executions
  // This ensures the tabs match the Debug view order
  // Also map to include the full stage execution object for proper labeling
  const parallelExecutions = stage.parallel_executions || [];
  const executions = parallelExecutions
    .map((stageExecution, index) => {
      const executionId = stageExecution.execution_id;
      const items = executionGroups.get(executionId) || [];
      return {
        executionId,
        stageExecution,
        index,
        items,
      };
    });
    // NOTE: Do NOT filter by items.length > 0 to avoid tab flickering during streaming
    // Tabs should remain stable even when streaming items are being deduplicated

  // Safety check - only show alert if there are truly no parallel executions
  if (executions.length === 0 && parallelExecutions.length === 0) {
    return (
      <Alert severity="info">
        <Typography variant="body2">
          No parallel agent reasoning flows found for this stage.
        </Typography>
      </Alert>
    );
  }
  
  // If we have executions but no items yet, still render the tabs (streaming will populate them)
  if (executions.length === 0 && parallelExecutions.length > 0) {
    return (
      <Alert severity="info">
        <Typography variant="body2">
          Waiting for parallel agent data...
        </Typography>
      </Alert>
    );
  }

  return (
    <Box>
      {/* Parallel Agent Selector - Card Style with Container-Level Padding */}
      <Box sx={{ mb: 3, pl: 4, pr: 1 }}>
        {/* Header with Parallel Indicator */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            mb: 1.5,
          }}
        >
          <CallSplit color="secondary" fontSize="small" />
          <Typography variant="caption" color="secondary" fontWeight={600} letterSpacing={0.5}>
            PARALLEL EXECUTION
          </Typography>
          <Chip
            label={`${executions.length} agent${executions.length > 1 ? 's' : ''}`}
            size="small"
            color="secondary"
            variant="outlined"
            sx={{ height: 20, fontSize: '0.7rem' }}
          />
        </Box>

        {/* Error Display */}
        {cancelError && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {cancelError}
          </Alert>
        )}

        {/* Agent Cards */}
        <Box
          sx={{
            display: 'flex',
            gap: 1.5,
            flexWrap: 'wrap',
          }}
        >
          {executions.map((execution, tabIndex) => {
            // Use actual execution status (stable) instead of deriving from items (changes during streaming)
            const statusColor = getStatusColor(execution.stageExecution.status);
            const statusIcon = getStatusIcon(execution.stageExecution.status);
            const label = getParallelStageLabel(
              execution.stageExecution,
              execution.index,
              stage.parallel_type
            );
            const isSelected = selectedTab === tabIndex;
            
            // Extract model and iteration strategy from the execution
            // These are now provided directly from the backend via computed fields
            const llmInteractions = execution.stageExecution.llm_interactions || [];
            const modelName = llmInteractions.length > 0 ? llmInteractions[0].details.model_name : null;
            const iterationStrategy = execution.stageExecution.iteration_strategy;

            return (
              <Box
                key={execution.executionId}
                onClick={() => setSelectedTab(tabIndex)}
                sx={{
                  flex: 1,
                  minWidth: 180,
                  p: 1.5,
                  border: 2,
                  borderColor: isSelected ? 'secondary.main' : 'divider',
                  borderRadius: 1.5,
                  backgroundColor: isSelected
                    ? (theme) => alpha(theme.palette.secondary.main, 0.08)
                    : 'background.paper',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  '&:hover': {
                    borderColor: isSelected ? 'secondary.main' : (theme) => alpha(theme.palette.secondary.main, 0.4),
                    backgroundColor: isSelected
                      ? (theme) => alpha(theme.palette.secondary.main, 0.08)
                      : (theme) => alpha(theme.palette.secondary.main, 0.03),
                  },
                }}
              >
                <Box display="flex" alignItems="center" justifyContent="space-between" mb={0.5}>
                  <Typography variant="body2" fontWeight={600} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    {statusIcon}
                    {label}
                  </Typography>
                </Box>
                <Box display="flex" alignItems="center" gap={1} flexWrap="wrap">
                  {modelName && (
                    <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                      {modelName}
                    </Typography>
                  )}
                  {iterationStrategy && (
                    <Typography variant="caption" color="text.secondary">
                      {iterationStrategy}
                    </Typography>
                  )}
                  <Chip
                    label={getStatusLabel(execution.stageExecution.status)}
                    size="small"
                    color={statusColor as any}
                    sx={{ height: 18, fontSize: '0.65rem' }}
                  />
                </Box>
                
                {/* Token Usage */}
                {(execution.stageExecution.stage_input_tokens !== null || 
                  execution.stageExecution.stage_output_tokens !== null || 
                  execution.stageExecution.stage_total_tokens !== null) && (
                  <Box mt={1} display="flex" alignItems="center" gap={0.5}>
                    <Typography variant="body2" sx={{ fontSize: '0.9rem' }}>
                      🪙
                    </Typography>
                    <TokenUsageDisplay
                      tokenData={{
                        input_tokens: execution.stageExecution.stage_input_tokens,
                        output_tokens: execution.stageExecution.stage_output_tokens,
                        total_tokens: execution.stageExecution.stage_total_tokens,
                      }}
                      variant="inline"
                      size="small"
                    />
                    <Typography variant="caption" color="text.secondary">
                      tokens
                    </Typography>
                  </Box>
                )}
              </Box>
            );
          })}
        </Box>
      </Box>

      {/* Tab panels */}
      {executions.map((execution, index) => {
        // Get streaming items for this specific execution
        const executionStreamingItems = streamingByExecution.get(execution.executionId) || [];
        const hasDbItems = execution.items.length > 0;
        const hasStreamingItems = executionStreamingItems.length > 0;
        const isFailed = execution.stageExecution.status === 'failed';
        const hasError = isFailed && Boolean(execution.stageExecution.error_message);
        
        return (
          <TabPanel key={execution.executionId} value={selectedTab} index={index}>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
              {/* Show error message for failed executions */}
              {hasError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  <Typography variant="body2">
                    <strong>Execution Failed:</strong> {execution.stageExecution.error_message}
                  </Typography>
                </Alert>
              )}
              
              {/* Render DB items */}
              {execution.items.map((item) => (
                <ChatFlowItem
                  key={`${item.type}-${item.timestamp_us}`}
                  item={item}
                  isCollapsed={item.stageId ? collapsedStages.get(item.stageId) || false : false}
                  onToggleCollapse={item.stageId ? () => onToggleStage(item.stageId!) : undefined}
                  isAutoCollapsed={shouldAutoCollapse ? shouldAutoCollapse(item) : false}
                  onToggleAutoCollapse={onToggleItemExpansion ? () => onToggleItemExpansion(item) : undefined}
                  expandAll={expandAllReasoning}
                  isCollapsible={isItemCollapsible ? isItemCollapsible(item) : false}
                />
              ))}
              
              {/* Render streaming items (not yet in DB) */}
              {executionStreamingItems.map(([entryKey, entryValue]) => (
                <StreamingContentRenderer key={entryKey} item={entryValue} />
              ))}
              
              {/* Show placeholder if no items at all */}
              {!hasDbItems && !hasStreamingItems && (
                <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
                  No reasoning steps available for this agent
                </Typography>
              )}

              {/* Agent-Level Cancel Button - Only for paused agents */}
              {execution.stageExecution.status === 'paused' && (
                <Box 
                  sx={{ 
                    mt: 3, 
                    pt: 2.5,
                    borderTop: 1,
                    borderColor: 'divider',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: 1,
                  }}
                >
                  <Typography 
                    variant="caption" 
                    color="text.secondary" 
                    sx={{ 
                      textAlign: 'center',
                      fontWeight: 500,
                    }}
                  >
                    Agent-Level Action for <strong>{getParallelStageLabel(execution.stageExecution, execution.index, stage.parallel_type)}</strong>
                  </Typography>
                  
                  <Button
                    size="medium"
                    color="error"
                    variant="outlined"
                    startIcon={<CancelOutlined />}
                    onClick={() => handleCancelAgent(execution.stageExecution.execution_id)}
                    disabled={cancelingAgents.has(execution.stageExecution.execution_id)}
                    sx={{ 
                      minWidth: 200,
                      fontWeight: 600,
                      borderWidth: 1.5,
                      '&:hover': {
                        backgroundColor: 'error.main',
                        borderColor: 'error.main',
                        color: 'white',
                        borderWidth: 1.5,
                      }
                    }}
                  >
                    {cancelingAgents.has(execution.stageExecution.execution_id) 
                      ? 'Canceling Agent...' 
                      : 'Cancel This Agent'}
                  </Button>
                  
                  <Typography 
                    variant="caption" 
                    color="text.secondary" 
                    sx={{ 
                      textAlign: 'center',
                      maxWidth: 450,
                      fontSize: '0.7rem',
                    }}
                  >
                    This will cancel only this specific agent. Other parallel agents will continue running.
                  </Typography>
                </Box>
              )}
            </Box>
          </TabPanel>
        );
      })}
    </Box>
  );
};

export default ParallelStageReasoningTabs;

