import React, { useState } from 'react';
import {
  Paper,
  Typography,
  Box,
  Chip,
  Tabs,
  Tab,
  Alert,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from '@mui/material';
import { 
  Psychology,
  Timeline,
  ExpandMore,
  Info
} from '@mui/icons-material';
import ReasoningStepCard from './ReasoningStepCard';
import IterationSummaryCard from './IterationSummaryCard';
import type { ReactSession, ReasoningTrace } from '../types';

interface ReactReasoningPanelProps {
  session: ReactSession;
  currentReasoningSteps?: ReasoningTrace[];
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
      id={`react-tabpanel-${index}`}
      aria-labelledby={`react-tab-${index}`}
      {...other}
    >
      {value === index && (
        <Box sx={{ py: 2 }}>
          {children}
        </Box>
      )}
    </div>
  );
}

const ReactReasoningPanel: React.FC<ReactReasoningPanelProps> = ({ 
  session,
  currentReasoningSteps = []
}) => {
  const [tabValue, setTabValue] = useState(0);
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());

  // Don't render if ReAct is not enabled
  if (!session.react_enabled) {
    return null;
  }

  const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
    setTabValue(newValue);
  };

  const toggleStepExpansion = (stepId: string) => {
    const newExpanded = new Set(expandedSteps);
    if (newExpanded.has(stepId)) {
      newExpanded.delete(stepId);
    } else {
      newExpanded.add(stepId);
    }
    setExpandedSteps(newExpanded);
  };

  const getStatusColor = (): 'primary' | 'success' | 'error' | 'default' => {
    switch (session.status) {
      case 'in_progress':
        return 'primary';
      case 'completed':
        return 'success';
      case 'failed':
        return 'error';
      default:
        return 'default';
    }
  };

  return (
    <Paper sx={{ p: 0, mb: 2 }}>
      {/* Header */}
      <Box sx={{ p: 3, pb: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
          <Psychology color="primary" sx={{ fontSize: '2rem' }} />
          <Typography variant="h5" sx={{ fontWeight: 600 }}>
            ReAct Reasoning Analysis
          </Typography>
          <Chip
            label="Enhanced AI"
            color="primary"
            size="small"
            variant="outlined"
          />
        </Box>

        {/* Status Summary */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
          {session.current_iteration && (
            <Chip
              label={`Iteration ${session.current_iteration}`}
              color={getStatusColor()}
              variant="filled"
              size="small"
            />
          )}
          
          {session.total_iterations !== undefined && (
            <Chip
              label={`${session.total_iterations} iterations completed`}
              color="default"
              variant="outlined"
              size="small"
            />
          )}

          {session.latest_reasoning_step && (
            <Chip
              label={`Latest: ${session.latest_reasoning_step.step_type}`}
              color="info"
              variant="outlined"
              size="small"
            />
          )}
        </Box>

        {/* Info Alert */}
        <Alert 
          severity="info" 
          sx={{ mb: 2 }}
          icon={<Info />}
        >
          <Typography variant="body2">
            This alert is being processed with ReAct (Reasoning + Acting) methodology, 
            providing explicit reasoning traces for each decision and action.
          </Typography>
        </Alert>
      </Box>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
        <Tabs value={tabValue} onChange={handleTabChange} sx={{ px: 3 }}>
          <Tab 
            label="Live Reasoning" 
            icon={<Psychology />} 
            iconPosition="start"
          />
          <Tab 
            label="Iteration Summaries" 
            icon={<Timeline />} 
            iconPosition="start"
          />
        </Tabs>
      </Box>

      {/* Live Reasoning Tab */}
      <TabPanel value={tabValue} index={0}>
        <Box sx={{ px: 3 }}>
          {session.latest_reasoning_step && (
            <Box sx={{ mb: 3 }}>
              <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Psychology color="primary" sx={{ fontSize: '1.2rem' }} />
                Latest Reasoning Step
              </Typography>
              <ReasoningStepCard
                step={session.latest_reasoning_step}
                expanded={expandedSteps.has(`latest-${session.latest_reasoning_step.timestamp_us}`)}
                onToggle={() => toggleStepExpansion(`latest-${session.latest_reasoning_step.timestamp_us}`)}
              />
            </Box>
          )}

          {currentReasoningSteps.length > 0 && (
            <Box>
              <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Timeline color="primary" sx={{ fontSize: '1.2rem' }} />
                All Reasoning Steps
              </Typography>
              
              {/* Group by iteration */}
              {Array.from(new Set(currentReasoningSteps.map(step => step.iteration_number)))
                .sort((a, b) => b - a) // Most recent first
                .map(iterationNumber => {
                  const iterationSteps = currentReasoningSteps
                    .filter(step => step.iteration_number === iterationNumber)
                    .sort((a, b) => b.step_sequence - a.step_sequence); // Most recent step first

                  return (
                    <Accordion key={iterationNumber} defaultExpanded={iterationNumber === session.current_iteration}>
                      <AccordionSummary expandIcon={<ExpandMore />}>
                        <Typography variant="subtitle1">
                          Iteration {iterationNumber} ({iterationSteps.length} steps)
                        </Typography>
                      </AccordionSummary>
                      <AccordionDetails>
                        {iterationSteps.map(step => (
                          <ReasoningStepCard
                            key={`${step.iteration_number}-${step.step_sequence}-${step.timestamp_us}`}
                            step={step}
                            expanded={expandedSteps.has(`${step.iteration_number}-${step.step_sequence}-${step.timestamp_us}`)}
                            onToggle={() => toggleStepExpansion(`${step.iteration_number}-${step.step_sequence}-${step.timestamp_us}`)}
                          />
                        ))}
                      </AccordionDetails>
                    </Accordion>
                  );
                })}
            </Box>
          )}

          {!session.latest_reasoning_step && currentReasoningSteps.length === 0 && (
            <Alert severity="info">
              <Typography variant="body2">
                No reasoning steps available yet. ReAct reasoning will appear here as the agent processes the alert.
              </Typography>
            </Alert>
          )}
        </Box>
      </TabPanel>

      {/* Iteration Summaries Tab */}
      <TabPanel value={tabValue} index={1}>
        <Box sx={{ px: 3 }}>
          {session.iteration_summaries && session.iteration_summaries.length > 0 ? (
            <>
              <Typography variant="h6" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1 }}>
                <Timeline color="primary" sx={{ fontSize: '1.2rem' }} />
                Completed Iterations
              </Typography>
              
              {session.iteration_summaries
                .sort((a, b) => b.iteration_number - a.iteration_number) // Most recent first
                .map(summary => (
                  <IterationSummaryCard
                    key={summary.iteration_number}
                    summary={summary}
                  />
                ))
              }
            </>
          ) : (
            <Alert severity="info">
              <Typography variant="body2">
                No iteration summaries available yet. Summaries will appear here as iterations complete.
              </Typography>
            </Alert>
          )}
        </Box>
      </TabPanel>
    </Paper>
  );
};

export default ReactReasoningPanel;