import { useState, useEffect } from 'react';
import { Box, LinearProgress, CircularProgress, Typography } from '@mui/material';
import { formatDurationMs } from '../utils/timestamp';
import { SESSION_STATUS } from '../utils/statusConstants';
import type { ProgressIndicatorProps } from '../types';

/**
 * ProgressIndicator component - Phase 5
 * Shows progress indicators for active sessions and duration for completed ones
 */
function ProgressIndicator({ 
  status, 
  startedAt, 
  duration, 
  variant = 'linear',
  showDuration = true,
  size = 'medium'
}: ProgressIndicatorProps) {
  // State for live duration updates
  const [liveDuration, setLiveDuration] = useState<number | null>(null);

  // Calculate live duration for active sessions or as fallback for completed sessions
  const getLiveDuration = () => {
    if (duration !== undefined && duration !== null) return duration; // Use final duration if available
    if (startedAt !== undefined && startedAt !== null) {
      const now = Date.now() * 1000; // Convert to microseconds
      return Math.max(0, (now - startedAt) / 1000); // Convert to milliseconds
    }
    return null;
  };

  // Live ticking timer for active sessions
  useEffect(() => {
    // Only start timer for active sessions without final duration
    if ((status === SESSION_STATUS.IN_PROGRESS || status === SESSION_STATUS.PENDING || status === SESSION_STATUS.CANCELING) && startedAt !== undefined && startedAt !== null && !duration) {
      // Update immediately
      setLiveDuration(getLiveDuration());
      
      // Then update every second
      const timer = setInterval(() => {
        setLiveDuration(getLiveDuration());
      }, 1000);

      return () => clearInterval(timer);
    } else {
      // For completed sessions, always calculate and display duration
      setLiveDuration(getLiveDuration());
    }
  }, [status, startedAt, duration]);

  // Use live duration for display, fallback to calculated duration
  const currentDuration = liveDuration ?? getLiveDuration();
  const sizeMap = {
    small: 16,
    medium: 24,
    large: 32
  };

  // For active sessions, show progress indicator
  if (status === SESSION_STATUS.IN_PROGRESS || status === SESSION_STATUS.CANCELING) {
    const progressColor = status === SESSION_STATUS.CANCELING ? 'warning' : 'info';
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        {variant === 'circular' ? (
          <CircularProgress 
            size={sizeMap[size]} 
            color={progressColor}
            variant="indeterminate"
          />
        ) : (
          <LinearProgress 
            variant="indeterminate" 
            sx={{ 
              flexGrow: 1, 
              height: size === 'small' ? 6 : 8,
              borderRadius: 1,
              '& .MuiLinearProgress-bar': {
                borderRadius: 1,
              }
            }} 
            color={progressColor}
          />
        )}
        {showDuration && currentDuration && (
          <Typography variant="caption" color="text.secondary">
            {formatDurationMs(currentDuration)}
          </Typography>
        )}
      </Box>
    );
  }

  // For pending sessions, show waiting indicator
  if (status === SESSION_STATUS.PENDING) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        {variant === 'circular' ? (
          <CircularProgress 
            size={sizeMap[size]} 
            color="warning"
            variant="indeterminate"
          />
        ) : (
          <LinearProgress 
            variant="indeterminate" 
            sx={{ 
              flexGrow: 1, 
              height: size === 'small' ? 6 : 8,
              borderRadius: 1,
              '& .MuiLinearProgress-bar': {
                borderRadius: 1,
              }
            }} 
            color="warning"
          />
        )}
        {showDuration && currentDuration && (
          <Typography variant="caption" color="text.secondary">
            {formatDurationMs(currentDuration)}
          </Typography>
        )}
      </Box>
    );
  }

  // For paused sessions, show a paused indicator with frozen duration
  if (status === SESSION_STATUS.PAUSED) {
    return (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        {variant === 'circular' ? (
          <CircularProgress 
            size={sizeMap[size]} 
            color="warning"
            variant="determinate"
            value={0}
          />
        ) : (
          <LinearProgress 
            variant="determinate"
            value={0}
            sx={{ 
              flexGrow: 1, 
              height: size === 'small' ? 6 : 8,
              borderRadius: 1,
              '& .MuiLinearProgress-bar': {
                borderRadius: 1,
              }
            }} 
            color="warning"
          />
        )}
        {showDuration && currentDuration !== null && (
          <Typography variant="caption" color="text.secondary">
            {formatDurationMs(currentDuration)}
          </Typography>
        )}
        <Typography variant="caption" color="warning.main" sx={{ fontWeight: 600 }}>
          Paused
        </Typography>
      </Box>
    );
  }

  // For completed/failed/cancelled sessions, show duration if available
  if (showDuration && currentDuration) {
    const color = 
      status === SESSION_STATUS.COMPLETED ? 'success.main' : 
      status === SESSION_STATUS.FAILED ? 'error.main' : 
      status === SESSION_STATUS.CANCELLED ? 'text.disabled' : 
      'text.secondary';
    
    return (
      <Typography 
        variant="caption" 
        color={color}
        sx={{ fontWeight: 500 }}
      >
        {formatDurationMs(currentDuration)}
      </Typography>
    );
  }

  return null;
}

export default ProgressIndicator; 