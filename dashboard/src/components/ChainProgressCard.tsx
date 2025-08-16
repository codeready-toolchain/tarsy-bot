import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  Typography,
  Box,
  Chip,
  IconButton,
  Tooltip,
  LinearProgress,
  Collapse,
  Divider,
} from '@mui/material';
import {
  Error as ErrorIcon,
  Warning,
  Refresh,
  Schedule,
  OpenInNew,
  CheckCircle,
  ExpandMore,
  ExpandLess,
  Link as LinkIcon,
} from '@mui/icons-material';
import type { ChainProgressCardProps, Session } from '../types';
import { formatTimestamp, formatDuration, getCurrentTimestampUs, formatDurationMs } from '../utils/timestamp';
import ProgressIndicator from './ProgressIndicator';
import StageProgressBar from './StageProgressBar';

// Helper function to get status chip configuration
const getStatusChipConfig = (status: string) => {
  switch (status) {
    case 'in_progress':
    case 'processing':
      return {
        color: 'info' as const,
        icon: <Refresh sx={{ fontSize: 16 }} />,
        label: 'In Progress',
      };
    case 'pending':
      return {
        color: 'warning' as const,
        icon: <Schedule sx={{ fontSize: 16 }} />,
        label: 'Pending',
      };
    case 'failed':
      return {
        color: 'error' as const,
        icon: <ErrorIcon sx={{ fontSize: 16 }} />,
        label: 'Failed',
      };
    case 'completed':
      return {
        color: 'success' as const,
        icon: <CheckCircle sx={{ fontSize: 16 }} />,
        label: 'Completed',
      };
    case 'partial':
      return {
        color: 'warning' as const,
        icon: <Warning sx={{ fontSize: 16 }} />,
        label: 'Partial',
      };
    default:
      return {
        color: 'default' as const,
        icon: <Warning sx={{ fontSize: 16 }} />,
        label: status,
      };
  }
};

// Helper function to calculate chain progress percentage
const calculateChainProgress = (completed: number = 0, failed: number = 0, total: number = 0): number => {
  if (total === 0) return 0;
  return Math.round(((completed + failed) / total) * 100);
};

// Helper function to get current stage name
const getCurrentStageName = (
  session: Session, 
  chainProgress: { current_stage?: string } | null
): string => {
  if (chainProgress?.current_stage) {
    return chainProgress.current_stage;
  }
  if (session.status === 'completed') {
    return 'All stages completed';
  }
  if (session.status === 'failed') {
    return 'Processing failed';
  }
  return 'Starting...';
};

const ChainProgressCard: React.FC<ChainProgressCardProps> = ({ 
  session, 
  chainProgress, 
  stageProgress, 
  onClick, 
  compact = false 
}) => {
  const [expanded, setExpanded] = useState(false);
  const [currentTime, setCurrentTime] = useState(getCurrentTimestampUs());

  // Update current time every second for active sessions
  useEffect(() => {
    if (session.status === 'in_progress') {
      const interval = setInterval(() => {
        setCurrentTime(getCurrentTimestampUs());
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [session.status]);

  const handleCardClick = () => {
    if (onClick) {
      onClick(session.session_id);
    }
  };

  const handleExpandClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    setExpanded(!expanded);
  };

  const statusConfig = getStatusChipConfig(session.status);
  const isChainSession = session.chain_id;
  const totalStages = chainProgress?.total_stages || session.total_stages || 0;
  const completedStages = chainProgress?.completed_stages || session.completed_stages || 0;
  const failedStages = chainProgress?.failed_stages || session.failed_stages || 0;
  const currentStageIndex = chainProgress?.current_stage_index ?? session.current_stage_index;
  const chainProgressPercent = calculateChainProgress(completedStages, failedStages, totalStages);
  const currentStageName = getCurrentStageName(session, chainProgress ? {
    current_stage: chainProgress.current_stage || undefined
  } : null);

  return (
    <Card 
      sx={{ 
        mb: 2, 
        cursor: 'pointer',
        '&:hover': {
          boxShadow: 4,
        },
        border: isChainSession ? '2px solid' : '1px solid',
        borderColor: isChainSession ? 'primary.main' : 'divider',
      }}
      onClick={handleCardClick}
    >
      <CardContent sx={{ pb: compact ? 1 : 2 }}>
        {/* Header with chain indicator */}
        <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={1}>
          <Box flex={1}>
            <Box display="flex" alignItems="center" gap={1} mb={1}>
              <Typography variant="h6" component="div" sx={{ fontWeight: 600 }}>
                {session.alert_type}
              </Typography>
              {isChainSession && (
                <Tooltip title={`Chain: ${session.chain_id}`}>
                  <Chip
                    icon={<LinkIcon />}
                    label="Chain"
                    size="small"
                    color="primary"
                    variant="outlined"
                  />
                </Tooltip>
              )}
            </Box>
            <Typography variant="body2" color="text.secondary">
              {session.alert_id}
            </Typography>
          </Box>
          
          <Box display="flex" alignItems="center" gap={1}>
            <Chip
              icon={statusConfig.icon}
              label={statusConfig.label}
              color={statusConfig.color}
              size="small"
              variant="filled"
            />
            <Tooltip title="View Details">
              <IconButton 
                size="small" 
                onClick={(e) => {
                  e.stopPropagation();
                  handleCardClick();
                }}
                aria-label="View details"
                sx={{ p: 0.5 }}
              >
                <OpenInNew fontSize="small" />
              </IconButton>
            </Tooltip>
            {(isChainSession && totalStages > 0) && (
              <Tooltip title={expanded ? "Collapse stages" : "Expand stages"}>
                <IconButton 
                  size="small" 
                  onClick={handleExpandClick}
                  sx={{ p: 0.5 }}
                >
                  {expanded ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
                </IconButton>
              </Tooltip>
            )}
          </Box>
        </Box>

        {/* Chain progress overview */}
        {isChainSession && totalStages > 0 && (
          <Box mb={2}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
              <Typography variant="body2" color="text.secondary">
                Current Stage: {currentStageName}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {completedStages + failedStages}/{totalStages} stages
              </Typography>
            </Box>
            
            <LinearProgress 
              variant="determinate" 
              value={chainProgressPercent}
              sx={{ 
                height: 6, 
                borderRadius: 3,
                backgroundColor: 'grey.200',
                '& .MuiLinearProgress-bar': {
                  backgroundColor: failedStages > 0 ? 'warning.main' : 'success.main',
                },
              }}
            />
            
            {failedStages > 0 && (
              <Typography variant="caption" color="warning.main" sx={{ mt: 0.5, display: 'block' }}>
                {failedStages} stage{failedStages !== 1 ? 's' : ''} failed
              </Typography>
            )}
          </Box>
        )}

        {/* Standard session info */}
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
          <Typography variant="body2" color="text.secondary">
            Agent: {session.agent_type}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {formatTimestamp(session.started_at_us)}
          </Typography>
        </Box>

        {/* Duration and progress */}
        <Box display="flex" justifyContent="space-between" alignItems="center">
          <Box>
            {session.status === 'in_progress' ? (
              <Typography variant="caption" color="text.secondary">
                Running for {formatDuration(session.started_at_us, currentTime)}
              </Typography>
            ) : session.duration_ms ? (
              <Typography variant="caption" color="text.secondary">
                Duration: {formatDurationMs(session.duration_ms)}
              </Typography>
            ) : null}
          </Box>
          
          {session.status === 'in_progress' && (
            <ProgressIndicator 
              status="in_progress" 
              startedAt={session.started_at_us}
              variant="circular"
              size="small"
            />
          )}
        </Box>

        {/* Error message */}
        {session.error_message && (
          <Box mt={1}>
            <Typography variant="caption" color="error" sx={{ 
              fontStyle: 'italic',
              display: '-webkit-box',
              WebkitLineClamp: compact ? 2 : 3,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}>
              Error: {session.error_message}
            </Typography>
          </Box>
        )}

        {/* Expandable stage details */}
        {isChainSession && totalStages > 0 && (
          <Collapse in={expanded}>
            <Divider sx={{ my: 2 }} />
            <Typography variant="subtitle2" gutterBottom>
              Stage Progress
            </Typography>
            <StageProgressBar
              stages={stageProgress?.map(sp => ({
                execution_id: sp.stage_execution_id,
                session_id: session.session_id,
                stage_id: sp.stage_id,
                stage_index: sp.stage_index,
                stage_name: sp.stage_name,
                agent: sp.agent,
                status: sp.status,
                started_at_us: sp.started_at_us ?? null,
                completed_at_us: sp.completed_at_us ?? null,
                duration_ms: sp.duration_ms ?? null,
                stage_output: null,
                error_message: sp.error_message ?? null,
                // EP-0010: Add required fields for new API structure
                llm_interactions: [],
                mcp_communications: [],
                llm_interaction_count: 0,
                mcp_communication_count: 0,
                total_interactions: 0,
                stage_interactions_duration_ms: sp.duration_ms ?? null,
                chronological_interactions: []
              })) ?? []}
              currentStageIndex={currentStageIndex}
              showLabels={true}
              size="medium"
            />
          </Collapse>
        )}
      </CardContent>
    </Card>
  );
};

export default ChainProgressCard;