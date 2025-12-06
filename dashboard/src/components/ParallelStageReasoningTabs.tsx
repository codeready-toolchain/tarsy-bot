import React, { useState } from 'react';
import {
  Box,
  Tabs,
  Tab,
  Typography,
  Chip,
  Alert,
} from '@mui/material';
import {
  CheckCircle,
  Error as ErrorIcon,
  PlayArrow,
} from '@mui/icons-material';
import type { ChatFlowItemData } from '../utils/chatFlowParser';
import ChatFlowItem from './ChatFlowItem';

interface ParallelStageReasoningTabsProps {
  items: ChatFlowItemData[];
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

  // Convert to array for rendering
  const executions = Array.from(executionGroups.entries()).map(([executionId, items]) => ({
    executionId,
    agent: executionAgents.get(executionId) || 'Unknown Agent',
    items,
  }));

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

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setSelectedTab(newValue);
  };

  return (
    <Box>
      {/* Tabs for each parallel execution */}
      <Tabs 
        value={selectedTab} 
        onChange={handleTabChange}
        variant="scrollable"
        scrollButtons="auto"
        sx={{ 
          borderBottom: 1, 
          borderColor: 'divider',
          mb: 2
        }}
      >
        {executions.map((execution, index) => {
          const statusColor = getStatusColor(execution.items);
          const statusIcon = getStatusIcon(execution.items);
          
          return (
            <Tab
              key={execution.executionId}
              label={
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  {statusIcon}
                  <span>{execution.agent}</span>
                  <Chip 
                    label={`${execution.items.filter(i => i.type === 'thought').length} thoughts`}
                    size="small"
                    color={statusColor as any}
                    variant="outlined"
                  />
                </Box>
              }
              id={`reasoning-tab-${index}`}
              aria-controls={`reasoning-tabpanel-${index}`}
              sx={{ textTransform: 'none' }}
            />
          );
        })}
      </Tabs>

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

