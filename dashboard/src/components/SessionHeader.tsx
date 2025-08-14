import { Paper, Typography, Box } from '@mui/material';
import StatusBadge from './StatusBadge';
import ProgressIndicator from './ProgressIndicator';
import type { SessionHeaderProps } from '../types';
import { formatTimestamp } from '../utils/timestamp';

// Animation styles for processing sessions
const animationStyles = {
  breathingGlow: {
    '@keyframes breathingGlow': {
      '0%': { 
        boxShadow: '0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24), 0 0 8px 1px rgba(2, 136, 209, 0.2)'
      },
      '50%': { 
        boxShadow: '0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24), 0 0 24px 4px rgba(2, 136, 209, 0.45)'
      },
      '100%': { 
        boxShadow: '0 1px 3px rgba(0,0,0,0.12), 0 1px 2px rgba(0,0,0,0.24), 0 0 8px 1px rgba(2, 136, 209, 0.2)'
      },
    },
    animation: 'breathingGlow 2.8s ease-in-out infinite',
  },
};

/**
 * SessionHeader component - Phase 3
 * Displays session metadata including status, timing, and summary information
 */
function SessionHeader({ session }: SessionHeaderProps) {
  // Apply breathing glow animation for processing sessions
  const getAnimationStyle = () => {
    if (session.status !== 'in_progress') return {};
    return animationStyles.breathingGlow;
  };

  return (
    <Paper sx={{ 
      p: 3,
      ...getAnimationStyle(), // Apply animation for in-progress status
    }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        {/* Status Badge */}
        <Box>
          <StatusBadge status={session.status} size="medium" />
        </Box>

        {/* Session ID and Summary */}
        <Box sx={{ flex: 1 }}>
          <Typography variant="h5" gutterBottom sx={{ fontWeight: 600 }}>
            {session.session_id}
            {session.status === 'in_progress' && (
              <Typography component="span" variant="body2" color="info.main" sx={{ ml: 2, fontWeight: 400 }}>
                • Processing...
              </Typography>
            )}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {session.alert_type} • {session.agent_type} agent • Started at {formatTimestamp(session.started_at_us, 'absolute')}
          </Typography>
          {session.summary && typeof session.summary === 'object' && (
            <Typography variant="body2" sx={{ mt: 1 }}>
              {JSON.stringify(session.summary, null, 2)}
            </Typography>
          )}
        </Box>

        {/* Duration and Progress Info */}
        <Box sx={{ textAlign: 'right', minWidth: 150 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 1 }}>
            <Typography 
              variant="h6" 
              color={session.status === 'completed' ? 'success.main' : session.status === 'failed' ? 'error.main' : 'text.primary'}
              sx={{ fontWeight: 600 }}
            >
              Duration:
            </Typography>
            <ProgressIndicator 
              status={session.status}
              startedAt={session.started_at_us}
              duration={session.duration_ms}
              variant="linear"
              showDuration={true}
              size="medium"
            />
          </Box>
          {session.completed_at_us && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              Completed at {formatTimestamp(session.completed_at_us, 'absolute')}
            </Typography>
          )}
          {session.status === 'in_progress' && (
            <Typography variant="body2" color="info.main" sx={{ mt: 0.5 }}>
              Live updates enabled
            </Typography>
          )}
          {session.status === 'pending' && (
            <Typography variant="body2" color="warning.main" sx={{ mt: 0.5 }}>
              Waiting in queue...
            </Typography>
          )}
        </Box>
      </Box>
    </Paper>
  );
}

export default SessionHeader; 