import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Tabs,
  Tab,
  Typography,
  Chip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  Divider,
  Alert,
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
  CallSplit,
} from '@mui/icons-material';
import type { StageExecution, InteractionDetail } from '../types';
import { formatTimestamp, formatDurationMs } from '../utils/timestamp';
import { STAGE_STATUS, getStageStatusDisplayName } from '../utils/statusConstants';
import {
  isParallelStage,
  getParallelStageLabel,
  getAggregateStatus,
  getSuccessFailureCounts,
  getTotalTokenUsage,
  getAggregateDuration,
  getAggregateInteractionCounts,
} from '../utils/parallelStageHelpers';
import { PARALLEL_TYPE } from '../utils/parallelConstants';
import TokenUsageDisplay from './TokenUsageDisplay';
import InteractionCard from './InteractionCard';

interface ParallelStageExecutionTabsProps {
  stage: StageExecution;
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
      id={`parallel-tabpanel-${index}`}
      aria-labelledby={`parallel-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ pt: 2 }}>{children}</Box>}
    </div>
  );
}

// Helper to get status icon
const getStatusIcon = (status: string) => {
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

// Helper to get status color
const getStatusColor = (status: string) => {
  switch (status) {
    case STAGE_STATUS.COMPLETED:
      return 'success';
    case STAGE_STATUS.FAILED:
      return 'error';
    case STAGE_STATUS.ACTIVE:
      return 'primary';
    case STAGE_STATUS.PENDING:
    default:
      return 'default';
  }
};

/**
 * Component for displaying parallel stage executions in a tabbed interface
 */
const ParallelStageExecutionTabs: React.FC<ParallelStageExecutionTabsProps> = ({
  stage,
}) => {
  const [selectedTab, setSelectedTab] = useState(0);
  const [metadataExpanded, setMetadataExpanded] = useState(false);
  const [expandedInteractionDetails, setExpandedInteractionDetails] = useState<Record<string, boolean>>({});

  // Safety check
  if (!isParallelStage(stage) || !stage.parallel_executions || stage.parallel_executions.length === 0) {
    return (
      <Alert severity="warning">
        <Typography variant="body2">
          No parallel executions found for this stage.
        </Typography>
      </Alert>
    );
  }

  const parallelExecutions = stage.parallel_executions;
  const parallelType = stage.parallel_type || PARALLEL_TYPE.MULTI_AGENT;
  const counts = getSuccessFailureCounts(parallelExecutions);
  const aggregateStatus = getAggregateStatus(parallelExecutions);
  const totalTokens = getTotalTokenUsage(parallelExecutions);
  const aggregateDuration = getAggregateDuration(parallelExecutions);
  const aggregateInteractions = getAggregateInteractionCounts(parallelExecutions);

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setSelectedTab(newValue);
  };

  const toggleInteractionDetails = (itemId: string) => {
    setExpandedInteractionDetails(prev => ({
      ...prev,
      [itemId]: !prev[itemId]
    }));
  };

  return (
    <Box>
      {/* Aggregate Status Summary */}
      <Box
        sx={{
          mb: 2,
          p: 2,
          backgroundColor: (theme) => alpha(theme.palette.primary.main, 0.05),
          borderRadius: 1,
          border: '1px solid',
          borderColor: 'primary.main',
        }}
      >
        <Box display="flex" alignItems="center" gap={1} mb={1}>
          <CallSplit color="primary" />
          <Typography variant="subtitle2" fontWeight={600}>
            Parallel Execution Summary
          </Typography>
          <Chip
            label={parallelType === PARALLEL_TYPE.REPLICA ? 'Replica Mode' : 'Multi-Agent Mode'}
            size="small"
            color="primary"
            variant="outlined"
          />
        </Box>

        <Box display="flex" gap={2} flexWrap="wrap" alignItems="center">
          <Box>
            <Typography variant="caption" color="text.secondary">
              Status:
            </Typography>
            <Typography variant="body2" fontWeight={600}>
              {aggregateStatus}
            </Typography>
          </Box>

          <Divider orientation="vertical" flexItem />

          <Box>
            <Typography variant="caption" color="text.secondary">
              Executions:
            </Typography>
            <Box display="flex" gap={0.5} alignItems="center" flexWrap="wrap">
              {counts.completed > 0 && (
                <Chip
                  size="small"
                  icon={<CheckCircle fontSize="small" />}
                  label={`${counts.completed} completed`}
                  color="success"
                  variant="outlined"
                />
              )}
              {counts.failed > 0 && (
                <Chip
                  size="small"
                  icon={<ErrorIcon fontSize="small" />}
                  label={`${counts.failed} failed`}
                  color="error"
                  variant="outlined"
                />
              )}
              {counts.active > 0 && (
                <Chip
                  size="small"
                  icon={<PlayArrow fontSize="small" />}
                  label={`${counts.active} running`}
                  color="primary"
                  variant="outlined"
                />
              )}
              {counts.pending > 0 && (
                <Chip
                  size="small"
                  icon={<Schedule fontSize="small" />}
                  label={`${counts.pending} pending`}
                  color="default"
                  variant="outlined"
                />
              )}
            </Box>
          </Box>

          {aggregateDuration && (
            <>
              <Divider orientation="vertical" flexItem />
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Duration:
                </Typography>
                <Typography variant="body2" fontWeight={600}>
                  {formatDurationMs(aggregateDuration)}
                </Typography>
              </Box>
            </>
          )}

          {aggregateInteractions.total_count > 0 && (
            <>
              <Divider orientation="vertical" flexItem />
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Interactions:
                </Typography>
                <Box display="flex" gap={0.5}>
                  {aggregateInteractions.llm_count > 0 && (
                    <Chip
                      size="small"
                      icon={<Psychology fontSize="small" />}
                      label={aggregateInteractions.llm_count}
                      color="primary"
                      variant="outlined"
                    />
                  )}
                  {aggregateInteractions.mcp_count > 0 && (
                    <Chip
                      size="small"
                      icon={<Build fontSize="small" />}
                      label={aggregateInteractions.mcp_count}
                      color="secondary"
                      variant="outlined"
                    />
                  )}
                </Box>
              </Box>
            </>
          )}

          {(totalTokens.total_tokens !== null) && (
            <>
              <Divider orientation="vertical" flexItem />
              <Box>
                <Typography variant="caption" color="text.secondary">
                  Total Tokens:
                </Typography>
                <TokenUsageDisplay
                  tokenData={totalTokens}
                  variant="inline"
                  size="small"
                />
              </Box>
            </>
          )}
        </Box>
      </Box>

      {/* Expandable Metadata Section */}
      <Accordion
        expanded={metadataExpanded}
        onChange={() => setMetadataExpanded(!metadataExpanded)}
        sx={{ mb: 2 }}
      >
        <AccordionSummary expandIcon={<ExpandMore />}>
          <Typography variant="subtitle2">Execution Metadata</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <List dense>
            {parallelExecutions.map((execution, index) => (
              <ListItem key={execution.execution_id} sx={{ pl: 0 }}>
                <ListItemIcon sx={{ minWidth: 36 }}>
                  {getStatusIcon(execution.status)}
                </ListItemIcon>
                <ListItemText
                  primary={
                    <Box display="flex" gap={1} alignItems="center">
                      <Typography variant="body2" fontWeight={600}>
                        {getParallelStageLabel(execution, index, parallelType)}
                      </Typography>
                      <Chip
                        label={getStageStatusDisplayName(execution.status)}
                        size="small"
                        color={getStatusColor(execution.status) as any}
                      />
                    </Box>
                  }
                  secondary={
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Agent: {execution.agent}
                      </Typography>
                      {execution.duration_ms && (
                        <>
                          {' • '}
                          <Typography variant="caption" color="text.secondary">
                            Duration: {formatDurationMs(execution.duration_ms)}
                          </Typography>
                        </>
                      )}
                      {execution.stage_total_tokens && (
                        <>
                          {' • '}
                          <Typography variant="caption" color="text.secondary">
                            Tokens: {execution.stage_total_tokens}
                          </Typography>
                        </>
                      )}
                    </Box>
                  }
                />
              </ListItem>
            ))}
          </List>
        </AccordionDetails>
      </Accordion>

      {/* Tabs for Individual Executions */}
      <Card variant="outlined">
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs
            value={selectedTab}
            onChange={handleTabChange}
            variant="scrollable"
            scrollButtons="auto"
            aria-label="parallel execution tabs"
          >
            {parallelExecutions.map((execution, index) => (
              <Tab
                key={execution.execution_id}
                label={
                  <Box display="flex" alignItems="center" gap={1}>
                    {getStatusIcon(execution.status)}
                    <span>{getParallelStageLabel(execution, index, parallelType)}</span>
                  </Box>
                }
                id={`parallel-tab-${index}`}
                aria-controls={`parallel-tabpanel-${index}`}
              />
            ))}
          </Tabs>
        </Box>

        {/* Tab Panels */}
        {parallelExecutions.map((execution, index) => (
          <TabPanel key={execution.execution_id} value={selectedTab} index={index}>
            <CardContent>
              {/* Execution Details */}
              <Box mb={2}>
                <Typography variant="subtitle2" gutterBottom>
                  Execution Details
                </Typography>
                <Box
                  sx={{
                    p: 1.5,
                    backgroundColor: 'grey.50',
                    borderRadius: 1,
                  }}
                >
                  <Box display="flex" gap={3} flexWrap="wrap">
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Agent:
                      </Typography>
                      <Typography variant="body2">{execution.agent}</Typography>
                    </Box>
                    <Box>
                      <Typography variant="caption" color="text.secondary">
                        Status:
                      </Typography>
                      <Typography variant="body2">
                        {getStageStatusDisplayName(execution.status)}
                      </Typography>
                    </Box>
                    {execution.started_at_us && (
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          Started:
                        </Typography>
                        <Typography variant="body2">
                          {formatTimestamp(execution.started_at_us)}
                        </Typography>
                      </Box>
                    )}
                    {execution.completed_at_us && (
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          Completed:
                        </Typography>
                        <Typography variant="body2">
                          {formatTimestamp(execution.completed_at_us)}
                        </Typography>
                      </Box>
                    )}
                    {execution.duration_ms && (
                      <Box>
                        <Typography variant="caption" color="text.secondary">
                          Duration:
                        </Typography>
                        <Typography variant="body2">
                          {formatDurationMs(execution.duration_ms)}
                        </Typography>
                      </Box>
                    )}
                  </Box>

                  {/* Token Usage */}
                  {(execution.stage_input_tokens !== null || 
                    execution.stage_output_tokens !== null || 
                    execution.stage_total_tokens !== null) && (
                    <Box mt={1.5}>
                      <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>
                        Token Usage:
                      </Typography>
                      <TokenUsageDisplay
                        tokenData={{
                          input_tokens: execution.stage_input_tokens,
                          output_tokens: execution.stage_output_tokens,
                          total_tokens: execution.stage_total_tokens,
                        }}
                        variant="inline"
                        size="small"
                      />
                    </Box>
                  )}
                </Box>
              </Box>

              {/* Error Message */}
              {execution.error_message && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  <Typography variant="body2">
                    <strong>Error:</strong> {execution.error_message}
                  </Typography>
                </Alert>
              )}

              {/* Interactions Timeline */}
              {(execution.llm_interactions.length > 0 || execution.mcp_communications.length > 0) && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom sx={{ mb: 2 }}>
                    Interactions Timeline ({execution.total_interactions})
                  </Typography>

                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                    {/* Merge and sort all interactions by timestamp */}
                    {[...execution.llm_interactions, ...execution.mcp_communications]
                      .sort((a, b) => a.timestamp_us - b.timestamp_us)
                      .map((interaction: InteractionDetail, interactionIndex: number) => {
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
                </Box>
              )}

              {/* No Interactions Message */}
              {execution.llm_interactions.length === 0 && 
               execution.mcp_communications.length === 0 && (
                <Card variant="outlined" sx={{ p: 3, textAlign: 'center', bgcolor: 'grey.50' }}>
                  <Typography variant="body2" color="text.secondary" fontStyle="italic">
                    No interactions recorded for this execution
                  </Typography>
                </Card>
              )}
            </CardContent>
          </TabPanel>
        ))}
      </Card>
    </Box>
  );
};

export default ParallelStageExecutionTabs;

