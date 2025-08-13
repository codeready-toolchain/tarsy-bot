import React from 'react';
import {
  Box,
  Typography,
  Step,
  StepLabel,
  Stepper,
  StepContent,
  Chip,
} from '@mui/material';
import {
  CheckCircle,
  Error as ErrorIcon,
  Schedule,
  PlayArrow,
  Timer,
} from '@mui/icons-material';
import type { StageProgressBarProps } from '../types';
import { formatDurationMs } from '../utils/timestamp';

// Helper function to get step icon based on status
const getStepIcon = (status: string, isActive: boolean = false) => {
  switch (status) {
    case 'completed':
      return <CheckCircle color="success" />;
    case 'failed':
      return <ErrorIcon color="error" />;
    case 'active':
      return <PlayArrow color="primary" />;
    case 'pending':
    default:
      return <Schedule color={isActive ? 'primary' : 'disabled'} />;
  }
};

// Helper function to get step color
const getStepColor = (status: string): string => {
  switch (status) {
    case 'completed':
      return 'success';
    case 'failed':
      return 'error';
    case 'active':
      return 'primary';
    case 'pending':
    default:
      return 'grey';
  }
};

// Helper function to format stage status
const formatStageStatus = (status: string): string => {
  switch (status) {
    case 'completed':
      return 'Completed';
    case 'failed':
      return 'Failed';
    case 'active':
      return 'Running';
    case 'pending':
    default:
      return 'Pending';
  }
};

const StageProgressBar: React.FC<StageProgressBarProps> = ({
  stages,
  currentStageIndex,
  showLabels = true,
  size = 'medium',
}) => {
  if (!stages || stages.length === 0) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" p={2}>
        <Typography variant="body2" color="text.secondary">
          No stages available
        </Typography>
      </Box>
    );
  }

  const sortedStages = [...stages].sort((a, b) => a.stage_index - b.stage_index);

  return (
    <Box width="100%">
      <Stepper
        orientation="vertical"
        sx={{
          '& .MuiStepConnector-line': {
            minHeight: size === 'small' ? '20px' : '30px',
          },
        }}
      >
        {sortedStages.map((stage, index) => {
          const isActive = typeof currentStageIndex === 'number' && index === currentStageIndex;
          const isCompleted = stage.status === 'completed';
          const isRunning = stage.status === 'active';

          return (
            <Step key={stage.execution_id} active={isActive} completed={isCompleted}>
              <StepLabel
                icon={getStepIcon(stage.status, isActive)}
                sx={{
                  '& .MuiStepLabel-label': {
                    fontSize: size === 'small' ? '0.75rem' : '0.875rem',
                    fontWeight: isActive || isRunning ? 600 : 400,
                  },
                }}
              >
                <Box display="flex" alignItems="center" gap={1} flexWrap="wrap">
                  <Typography
                    variant={size === 'small' ? 'caption' : 'body2'}
                    sx={{
                      fontWeight: isActive || isRunning ? 600 : 400,
                      color: isActive || isRunning ? 'primary.main' : 'text.primary',
                    }}
                  >
                    {stage.stage_name}
                  </Typography>
                  
                  {showLabels && (
                    <>
                      <Chip
                        label={formatStageStatus(stage.status)}
                        size="small"
                        color={getStepColor(stage.status) as any}
                        variant={isActive ? 'filled' : 'outlined'}
                        sx={{ height: 20, fontSize: '0.65rem' }}
                      />
                      
                      {stage.agent && (
                        <Chip
                          label={`Agent: ${stage.agent}`}
                          size="small"
                          variant="outlined"
                          sx={{ height: 20, fontSize: '0.65rem' }}
                        />
                      )}
                    </>
                  )}
                </Box>
              </StepLabel>
              
              {(showLabels && size !== 'small') && (
                <StepContent>
                  <Box ml={1} mb={1}>
                    {/* Stage details */}
                    <Box display="flex" gap={2} flexWrap="wrap" mb={1}>
                      {stage.iteration_strategy && (
                        <Typography variant="caption" color="text.secondary">
                          Strategy: {stage.iteration_strategy}
                        </Typography>
                      )}
                      
                      {stage.duration_ms && (
                        <Box display="flex" alignItems="center" gap={0.5}>
                          <Timer sx={{ fontSize: 12 }} color="disabled" />
                          <Typography variant="caption" color="text.secondary">
                            {formatDurationMs(stage.duration_ms)}
                          </Typography>
                        </Box>
                      )}
                    </Box>
                    
                    {/* Error message */}
                    {stage.error_message && (
                      <Typography
                        variant="caption"
                        color="error"
                        sx={{
                          fontStyle: 'italic',
                          display: 'block',
                          mt: 0.5,
                          p: 1,
                          backgroundColor: 'error.light',
                          borderRadius: 1,
                          opacity: 0.8,
                        }}
                      >
                        Error: {stage.error_message}
                      </Typography>
                    )}
                    
                    {/* Success indicator */}
                    {stage.status === 'completed' && stage.stage_output && (
                      <Typography
                        variant="caption"
                        color="success.main"
                        sx={{
                          fontStyle: 'italic',
                          display: 'block',
                          mt: 0.5,
                        }}
                      >
                        Stage completed successfully
                      </Typography>
                    )}
                  </Box>
                </StepContent>
              )}
            </Step>
          );
        })}
      </Stepper>
      
      {/* Overall progress summary */}
      <Box sx={{ mt: 2, p: 1, backgroundColor: 'grey.50', borderRadius: 1 }}>
        <Typography variant="caption" color="text.secondary" align="center" display="block">
          {stages.filter(s => s.status === 'completed').length} completed, {' '}
          {stages.filter(s => s.status === 'failed').length} failed, {' '}
          {stages.filter(s => s.status === 'active').length} active, {' '}
          {stages.filter(s => s.status === 'pending').length} pending
        </Typography>
      </Box>
    </Box>
  );
};

export default StageProgressBar;