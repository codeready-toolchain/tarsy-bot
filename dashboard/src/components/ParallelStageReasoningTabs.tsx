import React, { useState } from 'react';
import {
  Box,
  Typography,
  Chip,
  Alert,
  alpha,
} from '@mui/material';
import {
  CheckCircle,
  Error as ErrorIcon,
  PlayArrow,
  CallSplit,
} from '@mui/icons-material';
import type { ChatFlowItemData } from '../utils/chatFlowParser';
import type { StageExecution } from '../types';
import ChatFlowItem from './ChatFlowItem';
import { getParallelStageLabel } from '../utils/parallelStageHelpers';

interface ParallelStageReasoningTabsProps {
  items: ChatFlowItemData[];
  stage: StageExecution; // Stage object to get correct execution order
  collapsedStages: Map<string, boolean>;
  onToggleStage: (stageId: string) => void;
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

// Helper to get status icon (based on success/failure of items)
const getStatusIcon = (items: ChatFlowItemData[]) => {
  const hasErrors = items.some(item => item.type === 'tool_call' && !item.success);
  const hasCompleted = items.some(item => item.type === 'final_answer');
  
  if (hasErrors) return <ErrorIcon fontSize="small" />;
  if (hasCompleted) return <CheckCircle fontSize="small" />;
  return <PlayArrow fontSize="small" />;
};

// Helper to get status color
const getStatusColor = (items: ChatFlowItemData[]) => {
  const hasErrors = items.some(item => item.type === 'tool_call' && !item.success);
  const hasCompleted = items.some(item => item.type === 'final_answer');
  
  if (hasErrors) return 'error';
  if (hasCompleted) return 'success';
  return 'primary';
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
}) => {
  const [selectedTab, setSelectedTab] = useState(0);

  // Group items by executionId
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
    })
    .filter(exec => exec.items.length > 0); // Only show executions that have items

  // Safety check
  if (executions.length === 0) {
    return (
      <Alert severity="info">
        <Typography variant="body2">
          No parallel agent reasoning flows found for this stage.
        </Typography>
      </Alert>
    );
  }

  return (
    <Box>
      {/* Parallel Agent Selector - Card Style */}
      <Box sx={{ mb: 3 }}>
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

        {/* Agent Cards */}
        <Box
          sx={{
            display: 'flex',
            gap: 1.5,
            flexWrap: 'wrap',
          }}
        >
          {executions.map((execution, tabIndex) => {
            const statusColor = getStatusColor(execution.items);
            const statusIcon = getStatusIcon(execution.items);
            const label = getParallelStageLabel(
              execution.stageExecution,
              execution.index,
              stage.parallel_type
            );
            const thoughtCount = execution.items.filter(i => i.type === 'thought').length;
            const isSelected = selectedTab === tabIndex;

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
                <Box display="flex" alignItems="center" gap={1}>
                  <Typography variant="caption" color="text.secondary">
                    {thoughtCount} thought{thoughtCount !== 1 ? 's' : ''}
                  </Typography>
                  <Chip
                    label={statusColor === 'success' ? 'Complete' : statusColor === 'error' ? 'Failed' : 'Running'}
                    size="small"
                    color={statusColor as any}
                    sx={{ height: 18, fontSize: '0.65rem' }}
                  />
                </Box>
              </Box>
            );
          })}
        </Box>
      </Box>

      {/* Tab panels */}
      {executions.map((execution, index) => (
        <TabPanel key={execution.executionId} value={selectedTab} index={index}>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
            {execution.items.length === 0 ? (
              <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
                No reasoning steps available for this agent
              </Typography>
            ) : (
              execution.items.map((item) => (
                <ChatFlowItem
                  key={`${item.type}-${item.timestamp_us}`}
                  item={item}
                  isCollapsed={item.stageId ? collapsedStages.get(item.stageId) || false : false}
                  onToggleCollapse={item.stageId ? () => onToggleStage(item.stageId!) : undefined}
                />
              ))
            )}
          </Box>
        </TabPanel>
      ))}
    </Box>
  );
};

export default ParallelStageReasoningTabs;

