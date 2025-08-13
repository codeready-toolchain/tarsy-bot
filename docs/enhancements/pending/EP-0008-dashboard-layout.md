# EP-0008-1: Dashboard Layout Integration for Agent Chains

## Overview

The current agent chain dashboard layout suffers from a disconnect between stage visualization and timeline display. The `ChainTimeline` and `TimelineVisualization` components are rendered separately, creating a fragmented user experience where users must mentally correlate stage progress with chronological interaction flow.

## Current Issues

### Component Separation
- **ChainTimeline**: Groups interactions by stage in expandable accordions
- **TimelineVisualization**: Shows chronological flow with visual timeline
- **Result**: Two disconnected views of the same data

### User Experience Problems
1. **Context Switching**: Users jump between stage-focused and time-focused views
2. **Information Duplication**: Same interactions shown in different formats
3. **Visual Disconnect**: No clear relationship between stage progress and timeline flow
4. **Cognitive Load**: Users must manually correlate stage boundaries with timeline events

## Current Layout Issues

The current implementation renders two separate components sequentially, creating a disconnect between stage context and timeline flow:

- **ChainTimeline Component**: Groups interactions by stage in expandable accordions
- **TimelineVisualization Component**: Shows all interactions in chronological order

This separation forces users to mentally correlate information across two different organizational paradigms.

## Visual Comparison

The diagrams above illustrate the key differences between approaches:

1. **Current Layout**: Shows the problematic separation between ChainTimeline and TimelineVisualization components
2. **Unified Timeline**: Demonstrates how stage markers can be integrated into a single chronological flow
3. **Split-Pane Layout**: Shows the fallback approach with synchronized side-by-side views
4. **Detailed Flow**: Illustrates how actual interactions would appear in the unified timeline with stage context

## Design Options

### Option 1: Unified Timeline with Stage Markers - REJECTED
### Option 2: Tabbed Interface - REJECTED
### Option 3: Split-Pane Layout - REJECTED

### Option 4: Nested Accordion Timeline - IMPLEMENTED

## Future-Ready Extensions for Phase 2 & 3

Based on your preference for Option 4 and upcoming requirements, here are enhanced design options that can evolve to support:
- **Phase 2**: Multiple agents/timelines running in parallel within each stage
- **Phase 3**: Conditional workflows and branching logic in stages

## Design Inspiration Research

### Key Patterns Found:
1. **Swimlane Diagrams**: Horizontal tracks for parallel processes
2. **BPMN Workflows**: Parallel gateways and conditional branching
3. **Gantt Chart Patterns**: Multi-track timeline visualization
4. **Kanban Boards**: Column-based parallel workflow management
5. **Process Flow Diagrams**: Conditional branching with decision nodes

### Option 4-1 Extended: Multi-Agent Nested Accordion

This evolution of Option 4 maintains your preferred accordion structure while supporting parallel agents and future conditional workflows.

```tsx
// EnhancedNestedAccordionTimeline.tsx - Phase 2 Ready
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
  Grid,
  Paper,
  Tabs,
  Tab,
  Badge,
  Stack
} from '@mui/material';
import {
  ExpandMore,
  CheckCircle,
  Error,
  Schedule,
  PlayArrow,
  Psychology,
  Build,
  Timeline as TimelineIcon,
  NavigateNext,
  NavigateBefore,
  Launch,
  GroupWork,
  AccountTree,
  CallSplit,
  Sync
} from '@mui/icons-material';

const EnhancedNestedAccordionTimeline = ({ chainExecution, timelineItems }) => {
  const [expandedStages, setExpandedStages] = useState(new Set([chainExecution.current_stage_index]));
  const [currentStageIndex, setCurrentStageIndex] = useState(chainExecution.current_stage_index || 0);
  const [selectedAgentTab, setSelectedAgentTab] = useState({});

  // Group interactions by stage and agent for parallel visualization
  const getStageAgentGroups = (stageId) => {
    const stageInteractions = timelineItems.filter(item => item.stage_execution_id === stageId);
    const agentGroups = new Map();
    
    stageInteractions.forEach(interaction => {
      const agentId = interaction.agent_id || 'default';
      if (!agentGroups.has(agentId)) {
        agentGroups.set(agentId, {
          agentId,
          agentName: interaction.agent_name || 'Primary Agent',
          interactions: []
        });
      }
      agentGroups.get(agentId).interactions.push(interaction);
    });
    
    return Array.from(agentGroups.values()).map(group => ({
      ...group,
      interactions: group.interactions.sort((a, b) => a.timestamp_us - b.timestamp_us)
    }));
  };

  return (
    <Card>
      {/* Enhanced Chain Progress Header */}
      <CardContent sx={{ bgcolor: 'grey.50', borderBottom: 1, borderColor: 'divider' }}>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Typography variant="h6" color="primary.main">
            {chainExecution.chain_id}
          </Typography>
          <Box display="flex" alignItems="center" gap={1}>
            <Chip 
              icon={<GroupWork />}
              label="Multi-Agent Support" 
              color="secondary" 
              variant="outlined" 
              size="small"
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

        {/* Stage Navigation Breadcrumbs with Agent Counts */}
        <Breadcrumbs separator="•" sx={{ mb: 2 }}>
          {chainExecution.stages.map((stage, index) => {
            const agentCount = getStageAgentGroups(stage.execution_id).length;
            return (
              <Badge 
                key={stage.execution_id}
                badgeContent={agentCount > 1 ? agentCount : 0}
                color="secondary"
                overlap="rectangular"
              >
                <Link
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
              </Badge>
            );
          })}
        </Breadcrumbs>

        {/* Overall Progress with Multi-Agent Indicator */}
        <LinearProgress 
          variant="determinate" 
          value={((currentStageIndex + 1) / chainExecution.stages.length) * 100}
          sx={{ height: 6, borderRadius: 3 }}
        />
      </CardContent>

      {/* Enhanced Nested Accordion Stages */}
      <Box sx={{ p: 2 }}>
        {chainExecution.stages.map((stage, stageIndex) => {
          const agentGroups = getStageAgentGroups(stage.execution_id);
          const isExpanded = expandedStages.has(stage.execution_id);
          const isCurrentStage = stageIndex === currentStageIndex;
          const hasMultipleAgents = agentGroups.length > 1;

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
                    {hasMultipleAgents ? <GroupWork /> : getStageStatusIcon(stage.status)}
                  </Avatar>
                  
                  <Box flex={1}>
                    <Typography variant="h6" fontWeight={600}>
                      Stage {stageIndex + 1}: {stage.stage_name}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {hasMultipleAgents 
                        ? `${agentGroups.length} agents • ${timelineItems.filter(item => item.stage_execution_id === stage.execution_id).length} total interactions`
                        : `${stage.agent} • ${agentGroups[0]?.interactions.length || 0} interactions`
                      }
                      {stage.started_at_us && ` • Started: ${formatTimestamp(stage.started_at_us, 'short')}`}
                    </Typography>
                  </Box>

                  <Box display="flex" gap={1} alignItems="center" onClick={(e) => e.stopPropagation()}>
                    {hasMultipleAgents && (
                      <Chip 
                        icon={<Sync />}
                        label="Parallel" 
                        color="secondary"
                        size="small"
                        variant="outlined"
                      />
                    )}
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
                {/* Multi-Agent Support */}
                {hasMultipleAgents ? (
                  <Box>
                    {/* Agent Tabs for Parallel Execution */}
                    <Card variant="outlined" sx={{ mb: 3 }}>
                      <Tabs 
                        value={selectedAgentTab[stage.execution_id] || 0}
                        onChange={(e, newValue) => setSelectedAgentTab({
                          ...selectedAgentTab,
                          [stage.execution_id]: newValue
                        })}
                        variant="scrollable"
                        scrollButtons="auto"
                      >
                        <Tab 
                          label="All Agents Timeline"
                          icon={<AccountTree />}
                        />
                        {agentGroups.map((agentGroup, index) => (
                          <Tab 
                            key={agentGroup.agentId}
                            label={
                              <Box display="flex" alignItems="center" gap={1}>
                                {agentGroup.agentName}
                                <Badge badgeContent={agentGroup.interactions.length} color="primary" max={99} />
                              </Box>
                            }
                            icon={<Psychology />}
                          />
                        ))}
                      </Tabs>
                    </Card>

                    {/* Agent Timeline Content */}
                    {(selectedAgentTab[stage.execution_id] || 0) === 0 ? (
                      // Combined view - All agents with swimlanes
                      <ParallelAgentTimeline agentGroups={agentGroups} />
                    ) : (
                      // Individual agent view
                      <SingleAgentTimeline 
                        agentGroup={agentGroups[(selectedAgentTab[stage.execution_id] || 1) - 1]}
                      />
                    )}
                  </Box>
                ) : (
                  // Single agent - existing timeline
                  <SingleAgentTimeline agentGroup={agentGroups[0]} />
                )}

                {/* Future: Conditional Workflow Placeholder */}
                {stage.has_conditions && (
                  <Card sx={{ mt: 2, bgcolor: 'warning.50', border: 1, borderColor: 'warning.200' }}>
                    <CardContent>
                      <Box display="flex" alignItems="center" gap={1} mb={1}>
                        <CallSplit color="warning" />
                        <Typography variant="subtitle2" color="warning.dark">
                          Conditional Workflow (Phase 3)
                        </Typography>
                      </Box>
                      <Typography variant="body2" color="text.secondary">
                        This stage includes conditional branching logic that will be visualized in Phase 3.
                      </Typography>
                    </CardContent>
                  </Card>
                )}

                {/* Stage Error Handling */}
                {stage.error_message && (
                  <Card sx={{ mt: 2, bgcolor: 'error.50', border: 1, borderColor: 'error.200' }}>
                    <CardContent>
                      <Typography variant="body2" color="error.main">
                        <strong>Error:</strong> {stage.error_message}
                      </Typography>
                    </CardContent>
                  </Card>
                )}
              </AccordionDetails>
            </Accordion>
          );
        })}
      </Box>
    </Card>
  );
};

// Component for parallel agent timeline visualization (swimlanes)
const ParallelAgentTimeline = ({ agentGroups }) => (
  <Box>
    <Typography variant="subtitle1" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <GroupWork color="primary" fontSize="small" />
      Parallel Agent Execution
    </Typography>
    
    {agentGroups.map((agentGroup, index) => (
      <Card key={agentGroup.agentId} variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Box display="flex" alignItems="center" gap={2} mb={2}>
            <Avatar sx={{ bgcolor: 'secondary.main', width: 32, height: 32 }}>
              <Psychology fontSize="small" />
            </Avatar>
            <Typography variant="h6">{agentGroup.agentName}</Typography>
            <Chip 
              label={`${agentGroup.interactions.length} interactions`}
              size="small" 
              variant="outlined"
            />
          </Box>
          
          {/* Horizontal timeline for parallel view */}
          <Box sx={{ 
            display: 'flex', 
            gap: 1, 
            overflowX: 'auto', 
            pb: 1,
            '&::-webkit-scrollbar': { height: 6 },
            '&::-webkit-scrollbar-thumb': { backgroundColor: 'divider', borderRadius: 3 }
          }}>
            {agentGroup.interactions.map((interaction, idx) => (
              <Paper 
                key={interaction.event_id}
                elevation={1}
                sx={{ 
                  p: 1, 
                  minWidth: 150,
                  bgcolor: interaction.type === 'llm' ? 'primary.50' : 'secondary.50',
                  border: 1,
                  borderColor: interaction.type === 'llm' ? 'primary.200' : 'secondary.200'
                }}
              >
                <Typography variant="caption" display="block" fontWeight={500}>
                  {interaction.step_description}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {formatTimestamp(interaction.timestamp_us, 'short')}
                </Typography>
                {interaction.duration_ms && (
                  <Chip 
                    label={`${interaction.duration_ms}ms`}
                    size="small"
                    variant="outlined"
                    sx={{ mt: 0.5, fontSize: '0.6rem', height: 16 }}
                  />
                )}
              </Paper>
            ))}
          </Box>
        </CardContent>
      </Card>
    ))}
  </Box>
);

// Component for single agent detailed timeline
const SingleAgentTimeline = ({ agentGroup }) => (
  <Box>
    <Typography variant="subtitle1" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <TimelineIcon color="primary" fontSize="small" />
      {agentGroup?.agentName || 'Agent'} Timeline
    </Typography>

    {agentGroup?.interactions?.length > 0 ? (
      <List dense sx={{ bgcolor: 'background.paper', borderRadius: 1, border: 1, borderColor: 'divider' }}>
        {agentGroup.interactions.map((interaction, interactionIndex) => (
          <React.Fragment key={interaction.event_id}>
            <ListItem
              sx={{
                py: 2,
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
                    {interaction.type === 'llm' ? 
                      <Psychology fontSize="small" /> : 
                      <Build fontSize="small" />
                    }
                  </Avatar>
                  
                  {interactionIndex < agentGroup.interactions.length - 1 && (
                    <Box sx={{
                      position: 'absolute',
                      left: '50%',
                      top: 32,
                      width: 2,
                      height: 32,
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
                    <IconButton 
                      size="small" 
                      title="View interaction details"
                      onClick={() => {/* Handle interaction detail modal */}}
                    >
                      <Launch fontSize="small" />
                    </IconButton>
                  </Box>
                }
                secondary={
                  <Box mt={1} display="flex" gap={1} alignItems="center" flexWrap="wrap">
                    <Typography variant="caption" color="text.secondary">
                      {formatTimestamp(interaction.timestamp_us)}
                    </Typography>
                    <Chip 
                      label={interaction.type.toUpperCase()} 
                      size="small"
                      color={interaction.type === 'llm' ? 'primary' : 'secondary'}
                      variant="outlined"
                    />
                    {interaction.duration_ms && (
                      <Chip 
                        label={`${interaction.duration_ms}ms`} 
                        size="small"
                        variant="outlined"
                      />
                    )}
                  </Box>
                }
              />
            </ListItem>
            
            {interactionIndex < agentGroup.interactions.length - 1 && (
              <Divider variant="inset" component="li" />
            )}
          </React.Fragment>
        ))}
      </List>
    ) : (
      <Card variant="outlined" sx={{ p: 3, textAlign: 'center', bgcolor: 'grey.50' }}>
        <Typography variant="body2" color="text.secondary" fontStyle="italic">
          No interactions recorded for this agent yet
        </Typography>
      </Card>
    )}
  </Box>
);
```

